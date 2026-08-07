"""
Company Settings — admin-editable key/value store.
Replaces all hardcoded company info across templates and responses.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CompanySettings, User
from app.schemas import SettingItem, SettingUpdate
from app.core.auth import require_admin

router = APIRouter(prefix="/settings", tags=["Settings"])

# Keys the admin can configure
ALLOWED_KEYS = {
    "company_name":        "Full company name",
    "company_ref":         "Official reference number",
    "company_phone":       "Primary phone number",
    "company_email":       "Public contact email",
    "company_address":     "Physical address",
    "company_website":     "Website URL",
    "company_rc_number":   "CAC RC Number",
    "company_tagline":     "Tagline / slogan",
    "logo_url":            "Logo image URL",
    "profile_pdf_url":     "Company profile PDF URL",
    "established_year":    "Year company was established",
    "years_experience":    "Years of experience (for website stats)",
    "projects_completed":  "Total projects completed",
    "fleet_size":          "Total equipment fleet size",
    "staff_count":         "Technical staff count",
    "social_linkedin":     "LinkedIn profile URL",
    "social_facebook":     "Facebook page URL",
    "social_twitter":      "Twitter/X profile URL",
    "email_signature":     "Default email signature HTML",
}


@router.get("/", response_model=List[SettingItem])
async def get_all_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(CompanySettings))
    rows = result.scalars().all()
    existing = {r.key: r for r in rows}
    return [
        SettingItem(
            key=k,
            value=existing[k].value if k in existing else None,
            description=desc,
        )
        for k, desc in ALLOWED_KEYS.items()
    ]


@router.get("/public", response_model=Dict[str, str])
async def get_public_settings(db: AsyncSession = Depends(get_db)):
    """Public endpoint — returns non-sensitive company info for frontend."""
    public_keys = {
        "company_name", "company_tagline", "company_phone", "company_email",
        "company_address", "company_website", "logo_url", "years_experience",
        "projects_completed", "fleet_size", "staff_count",
        "established_year", "social_linkedin", "social_facebook",
    }
    result = await db.execute(
        select(CompanySettings).where(CompanySettings.key.in_(public_keys))
    )
    rows = result.scalars().all()
    return {r.key: r.value for r in rows if r.value}


@router.put("/{key}", response_model=SettingItem)
async def update_setting(
    key: str,
    payload: SettingUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    if key not in ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown setting key: '{key}'")
    result = await db.execute(select(CompanySettings).where(CompanySettings.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = payload.value
    else:
        row = CompanySettings(key=key, value=payload.value, description=ALLOWED_KEYS[key])
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return SettingItem(key=row.key, value=row.value, description=row.description)


@router.put("/bulk", response_model=List[SettingItem])
async def bulk_update_settings(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Update multiple settings at once.

    """
    invalid = [k for k in payload if k not in ALLOWED_KEYS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown keys: {invalid}")


    coerced_payload: Dict[str, str] = {
        k: ("" if v is None else str(v))
        for k, v in payload.items()
    }

    result = await db.execute(select(CompanySettings))
    existing = {r.key: r for r in result.scalars().all()}

    updated = []
    for key, value in coerced_payload.items():
        if key in existing:
            existing[key].value = value
            updated.append(existing[key])
        else:
            row = CompanySettings(key=key, value=value, description=ALLOWED_KEYS[key])
            db.add(row)
            updated.append(row)

    await db.commit()
    return [SettingItem(key=r.key, value=r.value, description=r.description) for r in updated]
