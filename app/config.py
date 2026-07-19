"""
Bilm Technical Services — Application Settings
All sensitive values come from .env — never hardcode credentials.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ────────────────────────────────────────────────────────────────────
    APP_NAME: str = "Bilm Technical Services API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Database ───────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://bilm:bilmpass@localhost:5432/bilmdb"

    # ── Redis / Celery ─────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── JWT Auth ───────────────────────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE-THIS-IN-PRODUCTION-USE-SECRETS-OR-VAULT"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # ── Email ──────────────────────────────────────────────────────────────────
    # Choose ONE provider: sendgrid | smtp | brevo_api
    #
    # brevo_api sends over Brevo's HTTPS REST API (port 443) instead of raw
    # SMTP (port 587). This exists specifically because Render.com's FREE
    # web service tier blocks all outbound traffic on SMTP ports 25/465/587
    # as an anti-spam policy — confirmed directly in Render's own changelog.
    # HTTPS on 443 is never blocked (the whole platform would break), so this
    # is the free-tier-compatible way to send transactional email from Render
    # without upgrading to a paid instance. Uses the SAME Brevo account, just
    # a different API key (from Brevo's "API Keys" tab, NOT the SMTP tab).
    EMAIL_PROVIDER: str = "smtp"               # "sendgrid", "smtp", or "brevo_api"
    SENDGRID_API_KEY: str = ""
    BREVO_API_KEY: str = ""

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    @property
    def smtp_port_int(self) -> int:
        """Defensive cast — env vars always arrive as strings from Docker."""
        try:
            return int(self.SMTP_PORT)
        except (ValueError, TypeError):
            return 587

    EMAIL_FROM_NAME: str = "Bilm Technical Services"
    EMAIL_FROM_ADDRESS: str = ""
    ADMIN_EMAIL: str = ""

    # ── Company (loaded from DB settings table at runtime; these are fallback) ──
    COMPANY_NAME: str = "Bilm Technical Services"
    COMPANY_REF: str = "BTS/IL/0069"
    COMPANY_PHONE: str = ""
    COMPANY_ADDRESS: str = "Trans Amadi Industrial Layout, Port Harcourt, Rivers State"
    COMPANY_WEBSITE: str = "https://bilmtechnical.com"
    COMPANY_PROFILE_PDF_URL: str = ""

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
