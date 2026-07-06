"""
Diagnostics — test email configuration directly.
Hit this endpoint to see EXACTLY why email is failing, with no guessing.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.core.auth import require_admin
from app.models import User
from app.services.email_service import send_email_raw

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics"])


@router.get("/email-config")
async def check_email_config(_: User = Depends(require_admin)):
    """
    Shows current email configuration (masked) and flags any missing values.
    Call this FIRST before testing actual sends.
    """
    issues = []

    if settings.EMAIL_PROVIDER not in ("smtp", "sendgrid"):
        issues.append(f"EMAIL_PROVIDER is '{settings.EMAIL_PROVIDER}' — must be 'smtp' or 'sendgrid'")

    if settings.EMAIL_PROVIDER == "smtp":
        if not settings.SMTP_HOST:
            issues.append("SMTP_HOST is empty")
        if not settings.SMTP_USER:
            issues.append("SMTP_USER is empty — this is your email login")
        if not settings.SMTP_PASSWORD:
            issues.append("SMTP_PASSWORD is empty — Gmail needs an App Password, not your normal password")
        try:
            port = int(settings.SMTP_PORT)
            if port not in (587, 465, 25, 2525):
                issues.append(f"SMTP_PORT is {port} — unusual, common values are 587 (TLS) or 465 (SSL)")
        except (ValueError, TypeError):
            issues.append(f"SMTP_PORT '{settings.SMTP_PORT}' is not a valid integer")
    else:
        if not settings.SENDGRID_API_KEY:
            issues.append("SENDGRID_API_KEY is empty")

    if not settings.EMAIL_FROM_ADDRESS:
        issues.append("EMAIL_FROM_ADDRESS is empty — emails need a From address")

    def mask(value: str, keep: int = 3) -> str:
        if not value:
            return "(empty)"
        if len(value) <= keep:
            return "*" * len(value)
        return value[:keep] + "*" * (len(value) - keep)

    return {
        "provider":            settings.EMAIL_PROVIDER,
        "smtp_host":           settings.SMTP_HOST,
        "smtp_port":           settings.SMTP_PORT,
        "smtp_user":           mask(settings.SMTP_USER, keep=4),
        "smtp_password_set":   bool(settings.SMTP_PASSWORD),
        "smtp_password_length":len(settings.SMTP_PASSWORD) if settings.SMTP_PASSWORD else 0,
        "smtp_use_tls":        settings.SMTP_USE_TLS,
        "sendgrid_key_set":    bool(settings.SENDGRID_API_KEY),
        "from_address":        settings.EMAIL_FROM_ADDRESS or "(empty)",
        "from_name":           settings.EMAIL_FROM_NAME,
        "admin_email":         settings.ADMIN_EMAIL or "(empty)",
        "issues_found":        issues,
        "status":              "❌ NOT READY" if issues else "✅ CONFIG LOOKS VALID — try /test-send next",
    }


class TestSendRequest(BaseModel):
    to_email: EmailStr


@router.post("/test-send")
async def test_send_email(payload: TestSendRequest, _: User = Depends(require_admin)):
    """
    Sends a real, raw test email bypassing templates entirely.
    This isolates whether the problem is SMTP/SendGrid connectivity
    vs. something in the template rendering or Celery layer.
    """
    success, error = await send_email_raw(
        to_email=payload.to_email,
        to_name="Test Recipient",
        subject="✅ Bilm Technical Services — SMTP Test",
        html_body="<h2>It works!</h2><p>If you're reading this, your email configuration is correct.</p>",
        text_body="It works! If you're reading this, your email configuration is correct.",
    )

    if success:
        return {"status": "✅ SUCCESS", "message": f"Email sent to {payload.to_email}. Check the inbox (and spam folder)."}

    return {
        "status": "❌ FAILED",
        "message": "Email failed to send. See 'error_detail' below for the exact cause.",
        "error_detail": error,
        "next_steps": _suggest_fix(error),
    }


def _suggest_fix(error: str) -> str:
    error_lower = error.lower()
    if "authentication" in error_lower or "auth" in error_lower:
        return (
            "This is a login/password problem. "
            "If using Gmail: create an App Password at https://myaccount.google.com/apppasswords "
            "(requires 2-Step Verification enabled first) and use that 16-character code as SMTP_PASSWORD. "
            "If using Brevo: copy the SMTP key from https://app.brevo.com/settings/keys/smtp"
        )
    if "connect" in error_lower or "timeout" in error_lower:
        return (
            "Cannot reach the SMTP server. Check: "
            "1) SMTP_HOST is spelled correctly, "
            "2) SMTP_PORT matches your provider (587 for TLS), "
            "3) your network/firewall isn't blocking outbound port 587, "
            "4) if running in Docker, the container has internet access."
        )
    if "missing" in error_lower or "not set" in error_lower or "config" in error_lower:
        return "Required environment variables are missing. Check your .env file has SMTP_USER, SMTP_PASSWORD, and EMAIL_FROM_ADDRESS all filled in, then restart: docker compose down && docker compose up -d"
    if "recipient refused" in error_lower:
        return "The recipient email address was rejected by the server — double check it's a valid, real email address."
    return "Check the error_detail above for specifics, or check container logs: docker compose logs api"
