"""
Bilm Technical Services — Email Service
Fixed:
  1. SMTP now uses synchronous smtplib correctly (not wrapped in async — 
     smtplib is blocking; run it in a thread executor from async callers)
  2. Detailed error logging — full traceback captured and stored in email_log
  3. SMTP_PORT cast to int explicitly — prevents string/int type errors
  4. Celery-safe sync version (send_template_email_sync) for task workers
  5. Brevo / Gmail / any SMTP supported
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from jinja2 import BaseLoader, Environment
from sqlalchemy import select

from app.config import settings

# Thread pool for running blocking SMTP calls without blocking the event loop
_smtp_executor = ThreadPoolExecutor(max_workers=4)


# ─── Jinja2 string loader ─────────────────────────────────────────────────────

class StringLoader(BaseLoader):
    def __init__(self, source: str):
        self._source = source

    def get_source(self, environment, template):
        return self._source, None, lambda: True


def render_template(template_str: str, context: Dict[str, Any]) -> str:
    """Render a Jinja2 template string with the given context."""
    env = Environment(loader=StringLoader(template_str), autoescape=True)
    tmpl = env.get_template("")
    return tmpl.render(**context)


# ─── LOW-LEVEL SYNC SMTP (runs in thread) ─────────────────────────────────────

def _smtp_send_sync(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Pure synchronous SMTP send.
    Returns (success: bool, error_message: str).
    Runs in a thread pool — never call directly from async code.
    """
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    # ── Validate config before attempting ────────────────────────────────────
    missing = []
    if not settings.SMTP_USER:     missing.append("SMTP_USER")
    if not settings.SMTP_PASSWORD: missing.append("SMTP_PASSWORD")
    if not settings.EMAIL_FROM_ADDRESS: missing.append("EMAIL_FROM_ADDRESS")
    if missing:
        msg = f"SMTP config incomplete — missing: {', '.join(missing)}. Check your .env file."
        print(f"[EMAIL][CONFIG ERROR] {msg}")
        return False, msg

    # ── Build message ─────────────────────────────────────────────────────────
    email_msg = MIMEMultipart("alternative")
    email_msg["Subject"] = subject
    email_msg["From"]    = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
    email_msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
    email_msg["Reply-To"]= settings.EMAIL_FROM_ADDRESS

    if text_body:
        email_msg.attach(MIMEText(text_body, "plain", "utf-8"))
    email_msg.attach(MIMEText(html_body, "html", "utf-8"))

    # ── Send ──────────────────────────────────────────────────────────────────
    try:
        port = int(settings.SMTP_PORT)   # explicit int cast — env vars are strings
        ctx  = ssl.create_default_context()

        with smtplib.SMTP(settings.SMTP_HOST, port, timeout=30) as server:
            server.ehlo()
            if settings.SMTP_USE_TLS:
                server.starttls(context=ctx)
                server.ehlo()
            server.login(settings.SMTP_USER, str(settings.SMTP_PASSWORD))
            server.sendmail(
                settings.EMAIL_FROM_ADDRESS,
                [to_email],
                email_msg.as_string(),
            )

        print(f"[EMAIL][OK] Sent '{subject}' → {to_email}")
        return True, ""

    except smtplib.SMTPAuthenticationError as e:
        msg = (
            f"SMTP Authentication failed. "
            f"If using Gmail, you need an App Password (not your account password). "
            f"Go to: https://myaccount.google.com/apppasswords  — Detail: {e}"
        )
        print(f"[EMAIL][AUTH ERROR] {msg}")
        return False, msg

    except smtplib.SMTPConnectError as e:
        msg = f"Cannot connect to {settings.SMTP_HOST}:{settings.SMTP_PORT}. Check SMTP_HOST and SMTP_PORT. Detail: {e}"
        print(f"[EMAIL][CONNECT ERROR] {msg}")
        return False, msg

    except smtplib.SMTPRecipientsRefused as e:
        msg = f"Recipient refused: {to_email}. Detail: {e}"
        print(f"[EMAIL][RECIPIENT ERROR] {msg}")
        return False, msg

    except smtplib.SMTPException as e:
        msg = f"SMTP error: {e}"
        print(f"[EMAIL][SMTP ERROR] {msg}")
        return False, msg

    except TimeoutError:
        msg = f"SMTP connection timed out connecting to {settings.SMTP_HOST}:{settings.SMTP_PORT}"
        print(f"[EMAIL][TIMEOUT] {msg}")
        return False, msg

    except Exception as e:
        msg = f"Unexpected error: {e}\n{traceback.format_exc()}"
        print(f"[EMAIL][UNKNOWN ERROR] {msg}")
        return False, msg


def _sendgrid_send_sync(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> tuple[bool, str]:
    """Synchronous SendGrid send — runs in thread pool."""
    if not settings.SENDGRID_API_KEY:
        return False, "SENDGRID_API_KEY is not set in .env"
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, To

        message = Mail(
            from_email=(settings.EMAIL_FROM_ADDRESS, settings.EMAIL_FROM_NAME),
            to_emails=To(to_email, to_name),
            subject=subject,
            html_content=html_body,
        )
        sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code in (200, 202):
            print(f"[EMAIL][SENDGRID OK] Sent '{subject}' → {to_email}")
            return True, ""
        msg = f"SendGrid returned status {response.status_code}: {response.body}"
        print(f"[EMAIL][SENDGRID ERROR] {msg}")
        return False, msg
    except Exception as e:
        msg = f"SendGrid error: {e}"
        print(f"[EMAIL][SENDGRID ERROR] {msg}")
        return False, msg


def _brevo_api_send_sync(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Synchronous Brevo send via their HTTPS REST API — NOT smtplib.

    WHY THIS EXISTS: Render.com's free web service tier blocks all
    outbound traffic on SMTP ports (25, 465, 587) as an anti-spam
    measure — confirmed in Render's own changelog. This produces
    "OSError: [Errno 101] Network is unreachable" from smtplib, even
    with fully correct SMTP credentials that work everywhere else
    (locally, in Gmail's "Send As", etc.) — it's a network-level block,
    not a credentials problem, and no amount of fixing SMTP_HOST/
    SMTP_PORT/SMTP_PASSWORD can work around it.

    This function sends over HTTPS (port 443) instead, which Render
    never blocks (doing so would break the entire platform, including
    Render's own services). Uses requests via httpx, run synchronously
    in the same thread-pool pattern as _smtp_send_sync — safe to call
    from both the async wrapper below and the Celery sync path.

    AUTH: needs BREVO_API_KEY (from Brevo's "API Keys" tab under
    SMTP & API — a DIFFERENT key from the SMTP key used by
    _smtp_send_sync above). Set in .env / Render environment variables.
    """
    if not settings.BREVO_API_KEY:
        msg = "BREVO_API_KEY is not set. Get one from Brevo → SMTP & API → API Keys tab (not the SMTP tab)."
        print(f"[EMAIL][CONFIG ERROR] {msg}")
        return False, msg
    if not settings.EMAIL_FROM_ADDRESS:
        msg = "EMAIL_FROM_ADDRESS is not set in .env"
        print(f"[EMAIL][CONFIG ERROR] {msg}")
        return False, msg

    payload = {
        "sender":      {"name": settings.EMAIL_FROM_NAME, "email": settings.EMAIL_FROM_ADDRESS},
        "to":          [{"email": to_email, "name": to_name or to_email}],
        "subject":     subject,
        "htmlContent": html_body,
    }
    if text_body:
        payload["textContent"] = text_body

    try:
        # timeout=30 matches the same 30s timeout used by _smtp_send_sync
        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={
                "api-key":      settings.BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept":       "application/json",
            },
            timeout=30,
        )
        if response.status_code in (200, 201):
            print(f"[EMAIL][BREVO API OK] Sent '{subject}' → {to_email}")
            return True, ""

        # Brevo returns structured JSON errors — surface the real message
        # rather than a bare status code, same detail level as the SMTP
        # exception handlers below.
        try:
            detail = response.json()
            error_text = detail.get("message", str(detail))
        except Exception:
            error_text = response.text

        if response.status_code == 401:
            msg = f"Brevo API authentication failed — check BREVO_API_KEY is correct and active. Detail: {error_text}"
        elif response.status_code == 400:
            msg = f"Brevo API rejected the request — often means the sender email isn't verified in Brevo yet. Detail: {error_text}"
        else:
            msg = f"Brevo API returned status {response.status_code}: {error_text}"

        print(f"[EMAIL][BREVO API ERROR] {msg}")
        return False, msg

    except httpx.TimeoutException:
        msg = "Brevo API request timed out after 30s."
        print(f"[EMAIL][TIMEOUT] {msg}")
        return False, msg
    except Exception as e:
        msg = f"Unexpected error calling Brevo API: {e}\n{traceback.format_exc()}"
        print(f"[EMAIL][UNKNOWN ERROR] {msg}")
        return False, msg


# ─── Async wrapper (for FastAPI routes) ───────────────────────────────────────

async def send_email_raw(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Non-blocking email send for use inside FastAPI async routes.
    Runs the blocking SMTP call in a thread pool.
    Returns (success, error_message).
    """
    loop = asyncio.get_event_loop()
    if settings.EMAIL_PROVIDER == "sendgrid":
        fn = _sendgrid_send_sync
    elif settings.EMAIL_PROVIDER == "brevo_api":
        fn = _brevo_api_send_sync
    else:
        fn = _smtp_send_sync

    success, error = await loop.run_in_executor(
        _smtp_executor,
        fn,
        to_email, to_name, subject, html_body, text_body,
    )
    return success, error


# ─── Sync version (for Celery workers — no event loop) ───────────────────────

def send_email_raw_sync(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Blocking email send for use inside Celery tasks.
    Celery workers are synchronous — do NOT use asyncio here.
    """
    if settings.EMAIL_PROVIDER == "sendgrid":
        return _sendgrid_send_sync(to_email, to_name, subject, html_body, text_body)
    elif settings.EMAIL_PROVIDER == "brevo_api":
        return _brevo_api_send_sync(to_email, to_name, subject, html_body, text_body)
    return _smtp_send_sync(to_email, to_name, subject, html_body, text_body)


# ─── Company context helper ───────────────────────────────────────────────────

async def _get_company_context(db) -> Dict[str, Any]:
    """Fetch company settings from DB for email template rendering."""
    from app.models import CompanySettings
    result = await db.execute(select(CompanySettings))
    rows   = result.scalars().all()
    ctx    = {row.key: row.value for row in rows}
    return {
        "company_name":    ctx.get("company_name",    settings.COMPANY_NAME),
        "company_phone":   ctx.get("company_phone",   settings.COMPANY_PHONE),
        "company_email":   ctx.get("company_email",   settings.EMAIL_FROM_ADDRESS),
        "company_address": ctx.get("company_address", settings.COMPANY_ADDRESS),
        "company_website": ctx.get("company_website", settings.COMPANY_WEBSITE),
        "company_ref":     ctx.get("company_ref",     settings.COMPANY_REF),
        "logo_url":        ctx.get("logo_url",        f"{settings.COMPANY_WEBSITE}/static/logo.png"),
    }


def _get_company_context_sync(db_session) -> Dict[str, Any]:
    """Synchronous company context fetch — for Celery tasks."""
    from app.models import CompanySettings
    from sqlalchemy import select as sa_select
    rows = db_session.execute(sa_select(CompanySettings)).scalars().all()
    ctx  = {row.key: row.value for row in rows}
    return {
        "company_name":    ctx.get("company_name",    settings.COMPANY_NAME),
        "company_phone":   ctx.get("company_phone",   settings.COMPANY_PHONE),
        "company_email":   ctx.get("company_email",   settings.EMAIL_FROM_ADDRESS),
        "company_address": ctx.get("company_address", settings.COMPANY_ADDRESS),
        "company_website": ctx.get("company_website", settings.COMPANY_WEBSITE),
        "company_ref":     ctx.get("company_ref",     settings.COMPANY_REF),
        "logo_url":        ctx.get("logo_url",        f"{settings.COMPANY_WEBSITE}/static/logo.png"),
    }


# ─── High-level async (FastAPI routes + email_templates router) ───────────────

async def send_template_email(
    db,
    template_slug: str,
    to_email: str,
    to_name: str,
    context: Dict[str, Any],
    lead_id: Optional[int] = None,
    client_id: Optional[int] = None,
    scheduled_at: Optional[datetime] = None,
):
    """
    Async version — for FastAPI route handlers.
    1. Load template from DB
    2. Render Jinja2 with context + company vars
    3. Send via thread pool (non-blocking)
    4. Log result with full error message if failed
    """
    from app.models import EmailLog, EmailTemplate, EmailStatus

    # Load template
    result = await db.execute(
        select(EmailTemplate).where(
            EmailTemplate.slug == template_slug,
            EmailTemplate.is_active == True,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise ValueError(f"Email template '{template_slug}' not found or inactive")

    # Build context
    company_ctx  = await _get_company_context(db)
    full_ctx     = {**company_ctx, "recipient_name": to_name, "recipient_email": to_email, **context}
    rendered_sub = render_template(tmpl.subject,   full_ctx)
    rendered_html= render_template(tmpl.body_html, full_ctx)
    rendered_text= render_template(tmpl.body_text, full_ctx) if tmpl.body_text else None

    # Send (non-blocking)
    success, error_msg = await send_email_raw(to_email, to_name, rendered_sub, rendered_html, rendered_text)

    # Log with full error detail
    log = EmailLog(
        lead_id=lead_id,
        client_id=client_id,
        template_slug=template_slug,
        recipient_email=to_email,
        recipient_name=to_name,
        subject=rendered_sub,
        status=EmailStatus.sent if success else EmailStatus.failed,
        scheduled_at=scheduled_at,
        sent_at=datetime.utcnow() if success else None,
        error_message=error_msg if not success else None,
        context_data=context,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


# ─── High-level SYNC (Celery tasks) ──────────────────────────────────────────

def send_template_email_sync(
    db_session,
    template_slug: str,
    to_email: str,
    to_name: str,
    context: Dict[str, Any],
    lead_id: Optional[int] = None,
    client_id: Optional[int] = None,
):
    """
    Synchronous version for Celery workers.
    Uses a SQLAlchemy sync session (NOT async session).
    """
    from app.models import EmailLog, EmailTemplate, EmailStatus
    from sqlalchemy import select as sa_select

    # Load template
    tmpl = db_session.execute(
        sa_select(EmailTemplate).where(
            EmailTemplate.slug == template_slug,
            EmailTemplate.is_active == True,
        )
    ).scalar_one_or_none()

    if not tmpl:
        print(f"[EMAIL][TEMPLATE NOT FOUND] slug='{template_slug}'")
        return None

    # Build context
    company_ctx  = _get_company_context_sync(db_session)
    full_ctx     = {**company_ctx, "recipient_name": to_name, "recipient_email": to_email, **context}
    rendered_sub = render_template(tmpl.subject,   full_ctx)
    rendered_html= render_template(tmpl.body_html, full_ctx)
    rendered_text= render_template(tmpl.body_text, full_ctx) if tmpl.body_text else None

    # Send (blocking — OK in Celery worker)
    success, error_msg = send_email_raw_sync(to_email, to_name, rendered_sub, rendered_html, rendered_text)

    # Log
    log = EmailLog(
        lead_id=lead_id,
        template_slug=template_slug,
        recipient_email=to_email,
        recipient_name=to_name,
        subject=rendered_sub,
        status=EmailStatus.sent if success else EmailStatus.failed,
        sent_at=datetime.utcnow() if success else None,
        error_message=error_msg if not success else None,
        context_data=context,
    )
    db_session.add(log)
    db_session.commit()
    return log
