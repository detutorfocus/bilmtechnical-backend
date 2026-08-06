"""
Image Upload — Cloudinary integration for equipment photos.

WHY A SEPARATE FILE: this is a genuinely new capability, not a fix to
existing code. Kept isolated here rather than folded into resources.py
so it can be registered independently in main.py without needing the
full current resources.py in hand to edit safely.

SETUP REQUIRED (one-time):
  1. Sign up free at https://cloudinary.com
  2. From your Cloudinary dashboard, copy: Cloud Name, API Key, API Secret
  3. Add to Render environment variables (and local .env):
       CLOUDINARY_CLOUD_NAME=your_cloud_name
       CLOUDINARY_API_KEY=your_api_key
       CLOUDINARY_API_SECRET=your_api_secret
  4. Add to requirements.txt:  cloudinary>=1.36.0
"""
from __future__ import annotations

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.config import settings
from app.core.auth import require_staff_or_admin
from app.models import User

router = APIRouter(prefix="/upload", tags=["Uploads"])

_cloudinary_configured = False


def _ensure_cloudinary_configured():
    """
    Lazy-configure Cloudinary on first use rather than at import time —
    avoids crashing app startup if the env vars aren't set yet, and gives
    a clear error message pointing at exactly what's missing instead of
    a raw import/config exception.
    """
    global _cloudinary_configured
    if _cloudinary_configured:
        return
    missing = []
    if not settings.CLOUDINARY_CLOUD_NAME: missing.append("CLOUDINARY_CLOUD_NAME")
    if not settings.CLOUDINARY_API_KEY:    missing.append("CLOUDINARY_API_KEY")
    if not settings.CLOUDINARY_API_SECRET: missing.append("CLOUDINARY_API_SECRET")
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Image upload is not configured — missing: {', '.join(missing)}. "
                   f"Set these in Render's environment variables (from your Cloudinary dashboard).",
        )
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    _cloudinary_configured = True


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB — generous for equipment photos, keeps free-tier usage reasonable


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    _: User = Depends(require_staff_or_admin),
):
    """
    Accepts an image file from the admin dashboard's file picker, uploads
    it to Cloudinary, and returns the resulting public URL. The frontend
    then stores that URL in the equipment's existing `image_url` field —
    no other schema or database changes needed, this only replaces HOW
    the URL gets populated (upload vs. manually pasting a link).
    """
    _ensure_cloudinary_configured()

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: JPEG, PNG, WEBP, GIF.",
        )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(contents) / 1024 / 1024:.1f}MB). Maximum is 8MB.",
        )

    try:
        result = cloudinary.uploader.upload(
            contents,
            folder="bilm_equipment",   # keeps uploads organized in Cloudinary's dashboard
            resource_type="image",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cloudinary upload failed: {e}")

    return {"url": result["secure_url"]}
