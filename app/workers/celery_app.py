"""
Bilm Technical Services — Celery Application
Uses built-in Celery beat scheduler (no Django dependency).
"""
from __future__ import annotations

import asyncio
from typing import Any

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# ─── Celery app ───────────────────────────────────────────────────────────────
celery_app = Celery(
    "bilm_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],   # auto-discover tasks
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Lagos",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # Beat schedule — built-in scheduler, no Django needed
    beat_schedule={
        "check-rental-due-dates-daily": {
            "task": "app.workers.tasks.check_rental_due_dates",
            "schedule": crontab(hour=7, minute=0),
        },
        "check-maintenance-due-daily": {
            "task": "app.workers.tasks.check_maintenance_due",
            "schedule": crontab(hour=7, minute=15),
        },
        "send-invoice-reminders-daily": {
            "task": "app.workers.tasks.send_invoice_reminders",
            "schedule": crontab(hour=8, minute=0),
        },
        "update-rental-statuses-daily": {
            "task": "app.workers.tasks.update_rental_statuses",
            "schedule": crontab(hour=6, minute=0),
        },
    },
)


# ─── Async helper ─────────────────────────────────────────────────────────────
def _run_async(coro) -> Any:
    """Run an async coroutine from within a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _get_db_session():
    from app.database import AsyncSessionLocal
    return AsyncSessionLocal()
