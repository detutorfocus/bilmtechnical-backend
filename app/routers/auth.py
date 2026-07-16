"""
Auth endpoints — now with email-based OTP as a second factor on login.

NEW LOGIN FLOW:
  1. POST /auth/login          — verify email+password. If correct, generate
                                  a 6-digit OTP, email it via Brevo, store it
                                  on the user record with a 10-minute expiry.
                                  Returns {"otp_required": true, "message": ...}
                                  — NOT a JWT yet.
  2. POST /auth/verify-otp     — takes {email, code}. If it matches and hasn't
                                  expired, issues the real JWT exactly as the
                                  old single-step /login used to.

WHY THIS SHAPE: the existing create_access_token/decode_token/get_current_user
dependency chain in app/core/auth.py is completely untouched — OTP verification
happens strictly BEFORE token issuance, so everything downstream of "user has
a valid JWT" keeps working exactly as before. No other router needs to change.

DEPENDS ON: app/models/__init__.py needs two new nullable columns on User:
    otp_code:       Optional[str]  (6-digit code, stored as string)
    otp_expires_at: Optional[datetime]
These are NOT yet added — see the accompanying model patch. This file will
fail at runtime (AttributeError on user.otp_code) until that model change
is applied.
"""
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserRole
from app.schemas import Token, UserCreate, UserOut, OTPVerify, LoginPending
from app.core.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin,
)
from app.services.email_service import send_email_raw

router = APIRouter(prefix="/auth", tags=["Auth"])

OTP_EXPIRY_MINUTES = 10

# Separate Limiter instance, bound the same way as main.py's (key_func=
# get_remote_address = rate-limit by client IP). slowapi's @limiter.limit(...)
# decorator reads the actual enforcement state from request.app.state.limiter
# at call time — NOT from this local `limiter` object — so this instance only
# needs to exist so the decorator has something to attach to; the real
# rate-limit storage/counting is still the single shared limiter registered
# in main.py via app.state.limiter. This is the standard slowapi pattern for
# using rate limiting inside a router file separate from where Limiter() was
# first constructed.
limiter = Limiter(key_func=get_remote_address)


def _generate_otp() -> str:
    """6-digit numeric code, zero-padded (e.g. '042613')."""
    return f"{random.randint(0, 999999):06d}"


@router.post("/login", response_model=LoginPending)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1 of 2. Verifies password, then emails a one-time code instead of
    issuing a JWT directly. The frontend must follow up with POST /auth/verify-otp
    to actually complete login.

    Rate limited to 5 attempts/minute per IP — protects the password check
    itself from brute-force guessing, independent of the OTP layer below.
    """
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    code = _generate_otp()
    user.otp_code = code
    user.otp_expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    await db.commit()

    # Reuses the same Brevo-backed send_email_raw already used elsewhere
    # in this codebase (diagnostics test-send, template previews, etc.) —
    # no new email infrastructure introduced.
    success, error = await send_email_raw(
        to_email=user.email,
        to_name=user.full_name or user.email,
        subject="Your Bilm Technical Services login code",
        html_body=(
            f"<p>Hi {user.full_name or ''},</p>"
            f"<p>Your login verification code is:</p>"
            f"<h2 style='letter-spacing:4px'>{code}</h2>"
            f"<p>This code expires in {OTP_EXPIRY_MINUTES} minutes. "
            f"If you didn't request this, you can safely ignore this email.</p>"
        ),
        text_body=f"Your login code is {code}. It expires in {OTP_EXPIRY_MINUTES} minutes.",
    )
    if not success:
        # Don't leave the account in a half-authenticated state if the
        # email genuinely failed to send — surface it clearly instead of
        # silently returning "check your email" for a code that never arrived.
        raise HTTPException(
            status_code=502,
            detail=f"Could not send verification code: {error}. Please try again or contact support.",
        )

    return LoginPending(
        otp_required=True,
        message=f"A verification code was sent to {user.email}.",
    )


@router.post("/verify-otp", response_model=Token)
@limiter.limit("10/minute")
async def verify_otp(
    request: Request,
    payload: OTPVerify,
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2 of 2. Checks the emailed code and, if valid, issues the real JWT —
    identical token shape/contents to what the old single-step /login returned.

    Rate limited to 10 attempts/minute per IP. This is the more important of
    the two limits: a 6-digit OTP is only ~1,000,000 possible values, and
    without this limit an attacker who obtained a valid password (e.g. from
    a leak) could brute-force the 10-minute-lived code with unlimited rapid
    guesses. 10/minute over a 10-minute window caps a single attacker to
    ~100 guesses per code lifetime — not zero risk, but reduces the attack
    from "trivial" to "impractical" without materially slowing down a real
    user who mistypes their code once or twice.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or code")

    if not user.otp_code or not user.otp_expires_at:
        raise HTTPException(status_code=400, detail="No pending verification for this account. Please log in again.")

    if datetime.utcnow() > user.otp_expires_at:
        user.otp_code = None
        user.otp_expires_at = None
        await db.commit()
        raise HTTPException(status_code=400, detail="Code expired. Please log in again to receive a new code.")

    if payload.code != user.otp_code:
        raise HTTPException(status_code=401, detail="Incorrect code")

    # Consume the code — one-time use, can't be replayed
    user.otp_code = None
    user.otp_expires_at = None
    await db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return Token(access_token=token)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole(payload.role),
        client_id=payload.client_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")
    current_user.hashed_password = hash_password(new_password)
    await db.commit()
    return {"message": "Password updated successfully"}
