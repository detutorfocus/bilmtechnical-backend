"""
Bilm Technical Services — Celery Tasks (SYNCHRONOUS)

Root cause fix: previously each task created a brand-new asyncio event loop
to run a single async DB call, which is unreliable for asyncpg connection
pooling inside Celery workers and silently swallowed errors.

This version uses plain synchronous SQLAlchemy (psycopg2) — the standard,
battle-tested pattern for Celery + Postgres. No event loops, no hidden failures.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select, and_

from app.workers.celery_app import celery_app
from app.workers.sync_db import get_sync_db


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD AUTOMATION SEQUENCE
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="app.workers.tasks.send_lead_welcome", bind=True, max_retries=3, default_retry_delay=60)
def send_lead_welcome(self, lead_id: int):
    """T+0: Welcome email — thank-you, company profile, service catalog."""
    from app.models import Lead
    from app.services.email_service import send_template_email_sync

    db = get_sync_db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            print(f"[TASK][send_lead_welcome] Lead {lead_id} not found — skipping")
            return

        log = send_template_email_sync(
            db_session=db,
            template_slug="lead_welcome",
            to_email=lead.email,
            to_name=lead.contact_person or lead.company_name,
            context={
                "lead_company": lead.company_name,
                "lead_contact": lead.contact_person or "",
                "service_type": lead.service_type or "our services",
                "equipment":    lead.equipment_type or "",
                "ref_code":     lead.ref_code,
            },
            lead_id=lead_id,
        )
        if log and log.status.value == "failed":
            print(f"[TASK][send_lead_welcome] FAILED: {log.error_message}")
            raise Exception(log.error_message)
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_lead_welcome] ERROR: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.send_admin_lead_notification", bind=True, max_retries=3, default_retry_delay=60)
def send_admin_lead_notification(self, lead_id: int):
    """T+0: Notify admin of new lead with full details."""
    from app.models import Lead
    from app.services.email_service import send_template_email_sync
    from app.config import settings

    db = get_sync_db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return
        if not settings.ADMIN_EMAIL:
            print("[TASK][send_admin_lead_notification] ADMIN_EMAIL not configured — skipping")
            return

        log = send_template_email_sync(
            db_session=db,
            template_slug="admin_lead_notification",
            to_email=settings.ADMIN_EMAIL,
            to_name="Admin",
            context={
                "lead_company":  lead.company_name,
                "lead_contact":  lead.contact_person or "—",
                "lead_email":    lead.email,
                "lead_phone":    lead.phone or "—",
                "service_type":  lead.service_type or "—",
                "equipment":     lead.equipment_type or "—",
                "duration":      lead.rental_duration or "—",
                "description":   lead.description or "—",
                "ref_code":      lead.ref_code,
                "submitted_at":  lead.created_at.strftime("%d %b %Y %H:%M"),
                "dashboard_url": f"{settings.FRONTEND_URL}/admin/leads/{lead_id}",
            },
            lead_id=lead_id,
        )
        if log and log.status.value == "failed":
            raise Exception(log.error_message)
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_admin_lead_notification] ERROR: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.send_lead_followup_24h", bind=True, max_retries=3, default_retry_delay=120)
def send_lead_followup_24h(self, lead_id: int):
    """T+24h: Friendly follow-up."""
    from app.models import Lead
    from app.services.email_service import send_template_email_sync

    db = get_sync_db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead or lead.status.value in ("converted", "lost"):
            return
        send_template_email_sync(
            db_session=db,
            template_slug="lead_followup_24h",
            to_email=lead.email,
            to_name=lead.contact_person or lead.company_name,
            context={
                "lead_company": lead.company_name,
                "lead_contact": lead.contact_person or lead.company_name,
                "service_type": lead.service_type or "your equipment needs",
                "ref_code":     lead.ref_code,
            },
            lead_id=lead_id,
        )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_lead_followup_24h] ERROR: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.send_lead_followup_3d", bind=True, max_retries=3, default_retry_delay=120)
def send_lead_followup_3d(self, lead_id: int):
    """T+3 days: Case studies, availability nudge."""
    from app.models import Lead
    from app.services.email_service import send_template_email_sync

    db = get_sync_db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead or lead.status.value in ("converted", "lost"):
            return
        send_template_email_sync(
            db_session=db,
            template_slug="lead_followup_3d",
            to_email=lead.email,
            to_name=lead.contact_person or lead.company_name,
            context={
                "lead_company": lead.company_name,
                "lead_contact": lead.contact_person or lead.company_name,
                "service_type": lead.service_type or "industrial services",
                "ref_code":     lead.ref_code,
            },
            lead_id=lead_id,
        )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_lead_followup_3d] ERROR: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.send_lead_proposal_7d", bind=True, max_retries=3, default_retry_delay=120)
def send_lead_proposal_7d(self, lead_id: int):
    """T+7 days: Formal proposal email."""
    from app.models import Lead
    from app.services.email_service import send_template_email_sync
    from app.config import settings

    db = get_sync_db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead or lead.status.value in ("converted", "lost"):
            return
        send_template_email_sync(
            db_session=db,
            template_slug="lead_proposal_7d",
            to_email=lead.email,
            to_name=lead.contact_person or lead.company_name,
            context={
                "lead_company": lead.company_name,
                "lead_contact": lead.contact_person or lead.company_name,
                "service_type": lead.service_type or "industrial services",
                "ref_code":     lead.ref_code,
                "quote_url":    f"{settings.FRONTEND_URL}/quote?ref={lead.ref_code}",
                "profile_url":  settings.COMPANY_PROFILE_PDF_URL,
            },
            lead_id=lead_id,
        )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_lead_proposal_7d] ERROR: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


def trigger_lead_automation(lead_id: int):
    """Fire the complete lead email sequence."""
    send_lead_welcome.apply_async(args=[lead_id])
    send_admin_lead_notification.apply_async(args=[lead_id])
    send_lead_followup_24h.apply_async(args=[lead_id], countdown=86_400)
    send_lead_followup_3d.apply_async(args=[lead_id],  countdown=259_200)
    send_lead_proposal_7d.apply_async(args=[lead_id],  countdown=604_800)


# ═══════════════════════════════════════════════════════════════════════════════
# QUOTE AUTOMATION
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="app.workers.tasks.send_quote_sent_notification", bind=True, max_retries=3)
def send_quote_sent_notification(self, quote_id: int):
    """Notify client/lead that a quote has been sent."""
    from app.models import Quote
    from app.services.email_service import send_template_email_sync
    from app.config import settings

    db = get_sync_db()
    try:
        quote = db.get(Quote, quote_id)
        if not quote:
            return

        if quote.client:
            to_email, to_name, company = quote.client.email, quote.client.contact_person or quote.client.company_name, quote.client.company_name
            cid, lid = quote.client_id, None
        elif quote.lead:
            to_email, to_name, company = quote.lead.email, quote.lead.contact_person or quote.lead.company_name, quote.lead.company_name
            cid, lid = None, quote.lead_id
        else:
            print(f"[TASK][send_quote_sent_notification] Quote {quote_id} has no client or lead")
            return

        send_template_email_sync(
            db_session=db,
            template_slug="quote_sent",
            to_email=to_email,
            to_name=to_name,
            context={
                "client_company": company,
                "client_contact": to_name,
                "quote_number":   quote.quote_number,
                "service_desc":   quote.service_desc or "—",
                "amount":         f"₦{quote.amount:,.2f}" if quote.amount else "TBD",
                "valid_until":    quote.valid_until.strftime("%d %b %Y") if quote.valid_until else "—",
                "quote_url":      f"{settings.FRONTEND_URL}/portal/quotes/{quote.quote_number}",
            },
            client_id=cid,
            lead_id=lid,
        )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_quote_sent_notification] ERROR: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.send_quote_followup", bind=True, max_retries=3)
def send_quote_followup(self, quote_id: int):
    """Follow up on unanswered quote after 3 days."""
    from app.models import Quote
    from app.services.email_service import send_template_email_sync
    from app.config import settings

    db = get_sync_db()
    try:
        quote = db.get(Quote, quote_id)
        if not quote or quote.status.value != "sent":
            return

        if quote.client:
            to_email, to_name, company = quote.client.email, quote.client.contact_person or quote.client.company_name, quote.client.company_name
        elif quote.lead:
            to_email, to_name, company = quote.lead.email, quote.lead.contact_person or quote.lead.company_name, quote.lead.company_name
        else:
            return

        send_template_email_sync(
            db_session=db,
            template_slug="quote_followup",
            to_email=to_email,
            to_name=to_name,
            context={
                "client_company": company,
                "client_contact": to_name,
                "quote_number":   quote.quote_number,
                "amount":         f"₦{quote.amount:,.2f}" if quote.amount else "TBD",
                "valid_until":    quote.valid_until.strftime("%d %b %Y") if quote.valid_until else "—",
                "quote_url":      f"{settings.FRONTEND_URL}/portal/quotes/{quote.quote_number}",
            },
            client_id=quote.client_id,
            lead_id=quote.lead_id,
        )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_quote_followup] ERROR: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


def trigger_quote_automation(quote_id: int):
    send_quote_sent_notification.apply_async(args=[quote_id])
    send_quote_followup.apply_async(args=[quote_id], countdown=259_200)


# ═══════════════════════════════════════════════════════════════════════════════
# CRON JOBS
# ═══════════════════════════════════════════════════════════════════════════════

@celery_app.task(name="app.workers.tasks.check_rental_due_dates", bind=True)
def check_rental_due_dates(self):
    """Daily: Email client 14 days before rental expiry."""
    from app.models import Rental
    from app.services.email_service import send_template_email_sync
    from app.config import settings

    db = get_sync_db()
    try:
        target = date.today() + timedelta(days=14)
        rentals = db.execute(
            select(Rental).where(and_(Rental.end_date == target, Rental.status == "active"))
        ).scalars().all()

        for rental in rentals:
            send_template_email_sync(
                db_session=db,
                template_slug="rental_expiry_reminder",
                to_email=rental.client.email,
                to_name=rental.client.contact_person or rental.client.company_name,
                context={
                    "client_company": rental.client.company_name,
                    "rental_code":    rental.rental_code,
                    "equipment_name": rental.equipment.name,
                    "end_date":       rental.end_date.strftime("%d %b %Y"),
                    "renewal_url":    f"{settings.FRONTEND_URL}/portal/rentals/{rental.rental_code}",
                },
                client_id=rental.client_id,
            )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][check_rental_due_dates] ERROR: {exc}")
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.check_maintenance_due", bind=True)
def check_maintenance_due(self):
    """Daily: Email admin + client 7 days before scheduled maintenance."""
    from app.models import MaintenanceRecord
    from app.services.email_service import send_template_email_sync
    from app.config import settings

    db = get_sync_db()
    try:
        target = date.today() + timedelta(days=7)
        records = db.execute(
            select(MaintenanceRecord).where(
                and_(MaintenanceRecord.scheduled_date == target, MaintenanceRecord.status == "scheduled")
            )
        ).scalars().all()

        for rec in records:
            context = {
                "maint_code":     rec.maint_code,
                "equipment_name": rec.equipment.name,
                "maint_type":     rec.maint_type.value.title(),
                "scheduled_date": rec.scheduled_date.strftime("%d %b %Y"),
                "technician":     rec.technician or "To be assigned",
            }
            if settings.ADMIN_EMAIL:
                send_template_email_sync(
                    db_session=db, template_slug="maintenance_reminder_admin",
                    to_email=settings.ADMIN_EMAIL, to_name="Admin",
                    context={**context, "dashboard_url": f"{settings.FRONTEND_URL}/admin/maintenance/{rec.id}"},
                )
            if rec.rental and rec.rental.client:
                client = rec.rental.client
                send_template_email_sync(
                    db_session=db, template_slug="maintenance_reminder_client",
                    to_email=client.email, to_name=client.contact_person or client.company_name,
                    context={**context, "client_company": client.company_name},
                    client_id=client.id,
                )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][check_maintenance_due] ERROR: {exc}")
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.send_invoice_reminders", bind=True)
def send_invoice_reminders(self):
    """Daily: Email clients 7 days before monthly rental payment due."""
    from app.models import Rental
    from app.services.email_service import send_template_email_sync
    from app.config import settings

    db = get_sync_db()
    try:
        rentals = db.execute(select(Rental).where(Rental.status == "active")).scalars().all()
        today = date.today()

        for rental in rentals:
            due_day = rental.start_date.day
            try:
                due_this_month = today.replace(day=due_day)
            except ValueError:
                continue
            if (due_this_month - today).days == 7:
                send_template_email_sync(
                    db_session=db,
                    template_slug="invoice_reminder",
                    to_email=rental.client.email,
                    to_name=rental.client.contact_person or rental.client.company_name,
                    context={
                        "client_company": rental.client.company_name,
                        "rental_code":    rental.rental_code,
                        "equipment_name": rental.equipment.name,
                        "amount":         f"₦{rental.monthly_rate:,.2f}" if rental.monthly_rate else "TBD",
                        "due_date":       due_this_month.strftime("%d %b %Y"),
                        "portal_url":     f"{settings.FRONTEND_URL}/portal/rentals",
                    },
                    client_id=rental.client_id,
                )
    except Exception as exc:
        db.rollback()
        print(f"[TASK][send_invoice_reminders] ERROR: {exc}")
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.update_rental_statuses", bind=True)
def update_rental_statuses(self):
    """Daily: Auto-update rental statuses (active → due → overdue)."""
    from app.models import Rental

    db = get_sync_db()
    try:
        today = date.today()
        rentals = db.execute(select(Rental).where(Rental.status.in_(["active", "due"]))).scalars().all()
        for rental in rentals:
            if rental.end_date < today:
                rental.status = "overdue"
            elif rental.end_date <= today + timedelta(days=14):
                rental.status = "due"
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[TASK][update_rental_statuses] ERROR: {exc}")
    finally:
        db.close()
