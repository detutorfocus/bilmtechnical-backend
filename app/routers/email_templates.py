"""
Email Templates — full CRUD.
Templates are stored in the DB as Jinja2 HTML strings.
Admins can edit subject, body_html, body_text from the dashboard.
"""
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, EmailTemplate
from app.schemas import (
    EmailTemplateCreate, EmailTemplateOut, EmailTemplateUpdate, EmailTemplatePreview,
)
from app.core.auth import require_admin
from app.services.email_service import send_email_raw, render_template, _get_company_context

router = APIRouter(prefix="/email-templates", tags=["Email Templates"])


@router.get("/", response_model=List[EmailTemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).order_by(EmailTemplate.slug))
    return result.scalars().all()


@router.get("/{slug}", response_model=EmailTemplateOut)
async def get_template(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    return tmpl


@router.post("/", response_model=EmailTemplateOut, status_code=201)
async def create_template(
    payload: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    existing = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Template slug '{payload.slug}' already exists")
    tmpl = EmailTemplate(**payload.model_dump())
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.put("/{slug}", response_model=EmailTemplateOut)
async def update_template(
    slug: str,
    payload: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(tmpl, field, val)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.delete("/{slug}", status_code=204)
async def delete_template(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    await db.delete(tmpl)
    await db.commit()


@router.post("/{slug}/preview", response_model=dict)
async def preview_template(
    slug: str,
    payload: EmailTemplatePreview,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Render the template with provided context and return rendered HTML — no email sent."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    company_ctx = await _get_company_context(db)
    ctx = {**company_ctx, **payload.context}
    rendered_subject = render_template(tmpl.subject, ctx)
    rendered_html    = render_template(tmpl.body_html, ctx)
    return {"subject": rendered_subject, "html": rendered_html}


@router.post("/{slug}/send-test", status_code=200)
async def send_test_email(
    slug: str,
    payload: EmailTemplatePreview,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Render and send a real test email to the provided address.
    Runs synchronously (not backgrounded) so the caller sees the real
    success/failure result instead of a fire-and-forget guess.
    """
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    company_ctx = await _get_company_context(db)
    ctx = {**company_ctx, "recipient_name": "Test Recipient", **payload.context}
    rendered_subject = render_template(tmpl.subject, ctx)
    rendered_html    = render_template(tmpl.body_html, ctx)
    rendered_text     = render_template(tmpl.body_text, ctx) if tmpl.body_text else None

    success, error = await send_email_raw(
        payload.recipient_email, "Test Recipient",
        f"[TEST] {rendered_subject}",
        rendered_html, rendered_text,
    )

    if not success:
        raise HTTPException(
            status_code=502,
            detail=f"Email failed to send: {error}",
        )

    return {"message": f"Test email sent to {payload.recipient_email}"}
