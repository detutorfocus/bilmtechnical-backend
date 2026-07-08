"""
Bilm Technical Services — FastAPI Main Application
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.database import create_all_tables
from app.routers.auth import router as auth_router
from app.routers.settings import router as settings_router
from app.routers.email_templates import router as templates_router
from app.routers.diagnostics import router as diagnostics_router
from app.routers.chat import router as chat_router
from app.routers.resources import (
    leads_router, clients_router, equipment_router,
    quotes_router, rentals_router, maintenance_router,
    email_logs_router, reports_router,
)

from app.routers.public_quotes import router as public_quotes_router
from app.routers.chat import router as chat_router



limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    # redirect_slashes=True (the default) — a request to /api/leads without
    # a trailing slash gets a 307 redirect to /api/leads/ and still carries
    # CORS headers correctly, as long as CORSMiddleware is registered first
    # (see below). This means the frontend can call endpoints with OR
    # without a trailing slash and both will work.
    redirect_slashes=True,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── CORS — registered BEFORE routers so it applies to redirects too ─────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bilmtechnical.com",
        "https://www.bilmtechnical.com",
        settings.FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static files ─────────────────────────────────────────────────────────────
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ─── Routers ──────────────────────────────────────────────────────────────────
PREFIX = "/api"

app.include_router(auth_router,         prefix=PREFIX)
app.include_router(settings_router,     prefix=PREFIX)
app.include_router(templates_router,    prefix=PREFIX)
app.include_router(diagnostics_router,  prefix=PREFIX)
app.include_router(chat_router,         prefix=PREFIX)
app.include_router(leads_router,        prefix=PREFIX)
app.include_router(clients_router,      prefix=PREFIX)
app.include_router(equipment_router,    prefix=PREFIX)
app.include_router(quotes_router,       prefix=PREFIX)
app.include_router(rentals_router,      prefix=PREFIX)
app.include_router(maintenance_router,  prefix=PREFIX)
app.include_router(email_logs_router,   prefix=PREFIX)
app.include_router(reports_router,      prefix=PREFIX)
app.include_router(public_quotes_router, prefix=PREFIX)
app.include_router(chat_router,          prefix=PREFIX)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/", tags=["Root"])
async def root():
    return {"message": "Bilm Technical Services API", "docs": "/docs", "health": "/health"}
