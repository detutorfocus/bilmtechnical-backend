"""
Bilm Technical Services — All resource routers
leads · clients · equipment · quotes · rentals · maintenance · email logs · reports

Quotes are AUTO-GENERATED from rental records — creating a rental
automatically calculates and creates a linked draft quote
(amount = equipment.monthly_rate x rental duration in months).
Admin reviews the draft in the Quotes panel and clicks SEND when ready.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    Client, EmailLog, EmailStatus, Equipment, Lead, LeadStatus,
    MaintenanceRecord, MaintStatus, Quote, QuoteStatus,
    Rental, RentalStatus, User,
)
from app.schemas import (
    ClientCreate, ClientOut, ClientUpdate,
    EmailLogOut,
    EquipmentCreate, EquipmentOut, EquipmentUpdate,
    KPIReport, LeadCreate, LeadOut, LeadUpdate,
    MaintenanceCreate, MaintenanceOut, MaintenanceUpdate,
    Page, QuoteCreate, QuoteOut, QuoteUpdate,
    RentalCreate, RentalOut, RentalUpdate, RentalWithRelations,
    RevenuePoint, ServiceBreakdown,
)
from app.core.auth import get_current_user, require_admin, require_staff_or_admin


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-QUOTE GENERATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _calculate_rental_months(start: date, end: date) -> Decimal:
    """Duration in whole months, rounded up — fair billing for partial months."""
    total_days = (end - start).days
    if total_days <= 0:
        return Decimal("1")
    months = Decimal(total_days) / Decimal("30.44")
    rounded = months.to_integral_value(rounding=ROUND_HALF_UP)
    return rounded if rounded >= 1 else Decimal("1")


async def _auto_generate_quote_for_rental(db: AsyncSession, rental: Rental) -> Quote:
    """
    Auto-creates a draft Quote from a newly created Rental.
    amount = monthly_rate x duration_in_months (rounded up).
    Admin reviews this draft in the Quotes panel and clicks SEND —
    no manual quote entry required.
    """
    equipment = await db.get(Equipment, rental.equipment_id)
    monthly_rate = rental.monthly_rate or (equipment.monthly_rate if equipment else None)
    months = _calculate_rental_months(rental.start_date, rental.end_date)
    amount = (monthly_rate * months) if monthly_rate else None

    duration_label = f"{months} month{'s' if months != 1 else ''}"
    service_desc = (
        f"{equipment.name if equipment else 'Equipment'} Rental — {duration_label} "
        f"({rental.start_date.strftime('%d %b %Y')} to {rental.end_date.strftime('%d %b %Y')})"
    )

    quote = Quote(
        client_id=rental.client_id,
        rental_id=rental.id,
        service_desc=service_desc,
        equipment_type=equipment.category.value if equipment else None,
        duration=duration_label,
        amount=amount,
        status=QuoteStatus.draft,
        valid_until=date.today() + timedelta(days=30),
        notes="Auto-generated from rental record — review amount before sending.",
    )
    db.add(quote)
    await db.flush()
    return quote


# ═══════════════════════════════════════════════════════════════════════════════
# LEADS
# ═══════════════════════════════════════════════════════════════════════════════

leads_router = APIRouter(prefix="/leads", tags=["Leads"])


@leads_router.post("/", response_model=LeadOut, status_code=201)
async def create_lead(
    payload: LeadCreate,
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — form submission from website. Fires automation."""
    lead = Lead(**payload.model_dump())
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    bg.add_task(_trigger_lead_automation, lead.id)
    return lead


def _trigger_lead_automation(lead_id: int):
    from app.workers.tasks import trigger_lead_automation
    trigger_lead_automation(lead_id)


@leads_router.get("/", response_model=Page[LeadOut])
async def list_leads(
    page:     int = Query(1, ge=1),
    size:     int = Query(20, ge=1, le=100),
    status:   Optional[str] = None,
    search:   Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff_or_admin),
):
    q = select(Lead)
    if status:
        q = q.where(Lead.status == status)
    if search:
        q = q.where(Lead.company_name.ilike(f"%{search}%"))
    q = q.order_by(desc(Lead.created_at))

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    return Page(items=items, total=total, page=page, size=size, pages=math.ceil(total / size) if total else 0)


@leads_router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@leads_router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: int, payload: LeadUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(lead, field, val)
    await db.commit()
    await db.refresh(lead)
    return lead


@leads_router.post("/{lead_id}/convert", response_model=ClientOut)
async def convert_lead_to_client(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff_or_admin),
):
    """Convert a lead into a client record."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    client = Client(
        company_name=lead.company_name,
        contact_person=lead.contact_person,
        email=lead.email,
        phone=lead.phone,
    )
    db.add(client)
    lead.status = LeadStatus.converted
    lead.converted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(client)
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════════════════════════════════════════

clients_router = APIRouter(prefix="/clients", tags=["Clients"])


@clients_router.post("/", response_model=ClientOut, status_code=201)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff_or_admin),
):
    """
    Creates a new client.

    Guards against ACCIDENTAL duplicate creation (same email submitted
    twice by mistake) — but does NOT block a client from renting again.
    Repeat business is handled by creating a new Rental against the
    SAME existing client_id, not by creating a second Client row.

    If a client with this email already exists, we return 409 with the
    existing client's data attached, so the frontend can offer to reuse
    it instead of erroring out with no path forward.
    """
    existing = await db.execute(select(Client).where(Client.email == payload.email))
    existing_client = existing.scalar_one_or_none()
    if existing_client:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"A client with email '{payload.email}' already exists.",
                "existing_client": {
                    "id": existing_client.id,
                    "company_name": existing_client.company_name,
                    "contact_person": existing_client.contact_person,
                    "email": existing_client.email,
                },
            },
        )

    client = Client(**payload.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


@clients_router.get("/", response_model=Page[ClientOut])
async def list_clients(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    q = select(Client).where(Client.is_active == True)
    if search:
        q = q.where(Client.company_name.ilike(f"%{search}%"))
    q = q.order_by(Client.company_name)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    return Page(items=items, total=total, page=page, size=size, pages=math.ceil(total / size) if total else 0)


@clients_router.get("/me", response_model=ClientOut)
async def get_my_client_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client portal — get own profile."""
    if not current_user.client_id:
        raise HTTPException(403, "No client profile linked to this account")
    client = await db.get(Client, current_user.client_id)
    if not client:
        raise HTTPException(404, "Client profile not found")
    return client


@clients_router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return client


@clients_router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int, payload: ClientUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, val)
    await db.commit()
    await db.refresh(client)
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# EQUIPMENT
# ═══════════════════════════════════════════════════════════════════════════════

equipment_router = APIRouter(prefix="/equipment", tags=["Equipment"])


@equipment_router.get("/", response_model=List[EquipmentOut])
async def list_equipment(
    category:  Optional[str] = None,
    available: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — used by website to render equipment showcase."""
    q = select(Equipment)
    if category:
        q = q.where(Equipment.category == category)
    if available is not None:
        q = q.where(Equipment.is_available == available)
    q = q.order_by(Equipment.category, Equipment.name)
    result = await db.execute(q)
    return result.scalars().all()


@equipment_router.post("/", response_model=EquipmentOut, status_code=201)
async def create_equipment(
    payload: EquipmentCreate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    eq = Equipment(**payload.model_dump())
    db.add(eq)
    await db.commit()
    await db.refresh(eq)
    return eq


@equipment_router.patch("/{eq_id}", response_model=EquipmentOut)
async def update_equipment(
    eq_id: int, payload: EquipmentUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    eq = await db.get(Equipment, eq_id)
    if not eq:
        raise HTTPException(404, "Equipment not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(eq, field, val)
    await db.commit()
    await db.refresh(eq)
    return eq


@equipment_router.delete("/{eq_id}", status_code=204)
async def delete_equipment(eq_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    eq = await db.get(Equipment, eq_id)
    if not eq:
        raise HTTPException(404, "Equipment not found")
    await db.delete(eq)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# QUOTES  (auto-generated from rentals — see RENTALS section below)
# ═══════════════════════════════════════════════════════════════════════════════

quotes_router = APIRouter(prefix="/quotes", tags=["Quotes"])


@quotes_router.post("/", response_model=QuoteOut, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    """
    Manual quote creation — kept available for edge cases (e.g. one-off
    service quotes not tied to a rental). The primary flow is automatic:
    creating a rental via POST /api/rentals/ auto-generates a quote.
    """
    quote = Quote(**payload.model_dump())
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


@quotes_router.get("/", response_model=Page[QuoteOut])
async def list_quotes(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    rental_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    q = select(Quote)
    if status:
        q = q.where(Quote.status == status)
    if client_id:
        q = q.where(Quote.client_id == client_id)
    if rental_id:
        q = q.where(Quote.rental_id == rental_id)
    q = q.order_by(desc(Quote.created_at))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    return Page(items=items, total=total, page=page, size=size, pages=math.ceil(total / size) if total else 0)


@quotes_router.get("/my", response_model=List[QuoteOut])
async def my_quotes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client portal — own quotes only."""
    if not current_user.client_id:
        raise HTTPException(403, "No client profile")
    result = await db.execute(
        select(Quote).where(Quote.client_id == current_user.client_id).order_by(desc(Quote.created_at))
    )
    return result.scalars().all()


@quotes_router.get("/{quote_id}", response_model=QuoteOut)
async def get_quote(quote_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    quote = await db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    return quote


@quotes_router.patch("/{quote_id}", response_model=QuoteOut)
async def update_quote(
    quote_id: int, payload: QuoteUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    quote = await db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(quote, field, val)
    await db.commit()
    await db.refresh(quote)
    return quote


@quotes_router.post("/{quote_id}/send", response_model=QuoteOut)
async def send_quote(
    quote_id: int, bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    quote = await db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.status = QuoteStatus.sent
    quote.sent_at = datetime.utcnow()
    await db.commit()
    await db.refresh(quote)
    bg.add_task(_trigger_quote_automation, quote.id)
    return quote


def _trigger_quote_automation(quote_id: int):
    from app.workers.tasks import trigger_quote_automation
    trigger_quote_automation(quote_id)


@quotes_router.post("/{quote_id}/accept", response_model=QuoteOut)
async def accept_quote(
    quote_id: int,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    quote = await db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    quote.status = QuoteStatus.accepted
    quote.accepted_at = datetime.utcnow()
    await db.commit()
    await db.refresh(quote)
    return quote


# ═══════════════════════════════════════════════════════════════════════════════
# RENTALS  — creating a rental auto-generates a linked draft Quote
# ═══════════════════════════════════════════════════════════════════════════════

rentals_router = APIRouter(prefix="/rentals", tags=["Rentals"])


@rentals_router.post("/", response_model=RentalOut, status_code=201)
async def create_rental(
    payload: RentalCreate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    """
    Creates a Rental AND automatically generates a linked draft Quote,
    calculated as equipment.monthly_rate x rental duration in months.
    Admin reviews the auto-generated quote in the Quotes panel and
    clicks SEND when ready — no manual quote entry required.
    """
    rental = Rental(**payload.model_dump())
    db.add(rental)
    await db.flush()  # assign rental.id before generating the quote

    eq = await db.get(Equipment, payload.equipment_id)
    if eq:
        eq.is_available = False

    await _auto_generate_quote_for_rental(db, rental)

    await db.commit()
    await db.refresh(rental)
    return rental


@rentals_router.get("/", response_model=Page[RentalWithRelations])
async def list_rentals(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    q = select(Rental).options(selectinload(Rental.client), selectinload(Rental.equipment))
    if status:
        q = q.where(Rental.status == status)
    if client_id:
        q = q.where(Rental.client_id == client_id)
    q = q.order_by(desc(Rental.created_at))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    return Page(items=items, total=total, page=page, size=size, pages=math.ceil(total / size) if total else 0)


@rentals_router.get("/my", response_model=List[RentalWithRelations])
async def my_rentals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Client portal — own rentals with full equipment details."""
    if not current_user.client_id:
        raise HTTPException(403, "No client profile")
    result = await db.execute(
        select(Rental)
        .options(selectinload(Rental.equipment))
        .where(Rental.client_id == current_user.client_id)
        .order_by(desc(Rental.created_at))
    )
    return result.scalars().all()


@rentals_router.get("/overdue", response_model=List[RentalWithRelations])
async def overdue_rentals(db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    result = await db.execute(
        select(Rental)
        .options(selectinload(Rental.client), selectinload(Rental.equipment))
        .where(Rental.status == RentalStatus.overdue)
    )
    return result.scalars().all()


@rentals_router.get("/{rental_id}", response_model=RentalWithRelations)
async def get_rental(rental_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(
        select(Rental)
        .options(selectinload(Rental.client), selectinload(Rental.equipment))
        .where(Rental.id == rental_id)
    )
    rental = result.scalar_one_or_none()
    if not rental:
        raise HTTPException(404, "Rental not found")
    return rental


@rentals_router.get("/{rental_id}/quote", response_model=QuoteOut)
async def get_rental_quote(
    rental_id: int,
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user),
):
    """Fetch the auto-generated quote linked to a rental, if one exists."""
    result = await db.execute(select(Quote).where(Quote.rental_id == rental_id))
    quote = result.scalar_one_or_none()
    if not quote:
        raise HTTPException(404, "No quote linked to this rental")
    return quote


@rentals_router.patch("/{rental_id}", response_model=RentalOut)
async def update_rental(
    rental_id: int, payload: RentalUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    rental = await db.get(Rental, rental_id)
    if not rental:
        raise HTTPException(404, "Rental not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(rental, field, val)
    if payload.status == "completed":
        eq = await db.get(Equipment, rental.equipment_id)
        if eq:
            eq.is_available = True
    await db.commit()
    await db.refresh(rental)
    return rental


# ═══════════════════════════════════════════════════════════════════════════════
# MAINTENANCE
# ═══════════════════════════════════════════════════════════════════════════════

maintenance_router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


@maintenance_router.post("/", response_model=MaintenanceOut, status_code=201)
async def schedule_maintenance(
    payload: MaintenanceCreate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    record = MaintenanceRecord(**payload.model_dump())
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@maintenance_router.get("/", response_model=Page[MaintenanceOut])
async def list_maintenance(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    equipment_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    q = select(MaintenanceRecord)
    if status:
        q = q.where(MaintenanceRecord.status == status)
    if equipment_id:
        q = q.where(MaintenanceRecord.equipment_id == equipment_id)
    q = q.order_by(desc(MaintenanceRecord.scheduled_date))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    return Page(items=items, total=total, page=page, size=size, pages=math.ceil(total / size) if total else 0)


@maintenance_router.get("/due-this-week", response_model=List[MaintenanceOut])
async def due_this_week(db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    today = date.today()
    result = await db.execute(
        select(MaintenanceRecord).where(
            and_(
                MaintenanceRecord.scheduled_date >= today,
                MaintenanceRecord.scheduled_date <= today + timedelta(days=7),
                MaintenanceRecord.status == MaintStatus.scheduled,
            )
        ).order_by(MaintenanceRecord.scheduled_date)
    )
    return result.scalars().all()


@maintenance_router.patch("/{record_id}/start", response_model=MaintenanceOut)
async def start_maintenance(
    record_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    record = await db.get(MaintenanceRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    record.status = MaintStatus.in_progress
    eq = await db.get(Equipment, record.equipment_id)
    if eq:
        record.health_before = eq.health_score
    await db.commit()
    await db.refresh(record)
    return record


@maintenance_router.patch("/{record_id}/complete", response_model=MaintenanceOut)
async def complete_maintenance(
    record_id: int, payload: MaintenanceUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    record = await db.get(MaintenanceRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    record.status = MaintStatus.completed
    record.completed_date = date.today()
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, val)
    if payload.health_after and record.equipment_id:
        eq = await db.get(Equipment, record.equipment_id)
        if eq:
            eq.health_score = payload.health_after
    await db.commit()
    await db.refresh(record)
    return record


@maintenance_router.patch("/{record_id}", response_model=MaintenanceOut)
async def update_maintenance(
    record_id: int, payload: MaintenanceUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    record = await db.get(MaintenanceRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, val)
    await db.commit()
    await db.refresh(record)
    return record


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL LOGS
# ═══════════════════════════════════════════════════════════════════════════════

email_logs_router = APIRouter(prefix="/email-logs", tags=["Email Logs"])


@email_logs_router.get("/", response_model=Page[EmailLogOut])
async def list_email_logs(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    lead_id: Optional[int] = None,
    client_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    q = select(EmailLog)
    if status:
        q = q.where(EmailLog.status == status)
    if lead_id:
        q = q.where(EmailLog.lead_id == lead_id)
    if client_id:
        q = q.where(EmailLog.client_id == client_id)
    q = q.order_by(desc(EmailLog.created_at))
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    return Page(items=items, total=total, page=page, size=size, pages=math.ceil(total / size) if total else 0)


@email_logs_router.get("/queue", response_model=List[EmailLogOut])
async def queued_emails(db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    result = await db.execute(
        select(EmailLog)
        .where(EmailLog.status == EmailStatus.queued)
        .order_by(EmailLog.scheduled_at)
    )
    return result.scalars().all()


@email_logs_router.patch("/{log_id}/cancel", response_model=EmailLogOut)
async def cancel_email(
    log_id: int,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    log = await db.get(EmailLog, log_id)
    if not log:
        raise HTTPException(404, "Email log not found")
    if log.status != EmailStatus.queued:
        raise HTTPException(400, "Only queued emails can be cancelled")
    log.status = EmailStatus.cancelled
    await db.commit()
    await db.refresh(log)
    return log


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTS / KPIs
# ═══════════════════════════════════════════════════════════════════════════════

reports_router = APIRouter(prefix="/reports", tags=["Reports"])


@reports_router.get("/overview", response_model=KPIReport)
async def get_kpi_overview(db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    total_leads     = await db.scalar(select(func.count(Lead.id)))
    hot_leads       = await db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.hot))
    open_q_rows     = (await db.execute(
        select(func.count(Quote.id), func.coalesce(func.sum(Quote.amount), 0))
        .where(Quote.status.in_([QuoteStatus.sent, QuoteStatus.negotiating, QuoteStatus.draft]))
    )).one()
    active_rentals  = await db.scalar(select(func.count(Rental.id)).where(Rental.status == RentalStatus.active))
    overdue_rentals = await db.scalar(select(func.count(Rental.id)).where(Rental.status == RentalStatus.overdue))
    queued_emails   = await db.scalar(select(func.count(EmailLog.id)).where(EmailLog.status == EmailStatus.queued))
    fleet_total     = await db.scalar(select(func.count(Equipment.id)))
    fleet_available = await db.scalar(select(func.count(Equipment.id)).where(Equipment.is_available == True))

    return KPIReport(
        total_leads=total_leads or 0,
        hot_leads=hot_leads or 0,
        open_quotes=open_q_rows[0] or 0,
        open_quotes_value=Decimal(str(open_q_rows[1] or 0)),
        active_rentals=active_rentals or 0,
        overdue_rentals=overdue_rentals or 0,
        queued_emails=queued_emails or 0,
        fleet_total=fleet_total or 0,
        fleet_available=fleet_available or 0,
    )


@reports_router.get("/revenue", response_model=List[RevenuePoint])
async def revenue_report(
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin),
):
    """
    Monthly accepted-quote revenue for the last N months.

    FIX: Postgres rejected the previous query with:
      "column quotes.accepted_at must appear in the GROUP BY clause
       or be used in an aggregate function"
    Root cause: ORDER BY used min(accepted_at) while GROUP BY used a
    different expression (to_char(accepted_at, ...)) over the same
    column — Postgres' strict grouping validator rejects mixing two
    different expressions derived from an ungrouped column, even when
    both are wrapped in aggregates/functions.

    Fix: select min(accepted_at) as its own labeled column, group by
    BOTH the period string and that min value, and order by the label
    itself. This keeps every expression in SELECT/ORDER BY consistent
    with what's in GROUP BY.
    """
    period_expr = func.to_char(Quote.accepted_at, "Mon YYYY")
    min_date_expr = func.min(Quote.accepted_at)

    result = await db.execute(
        select(
            period_expr.label("period"),
            func.sum(Quote.amount).label("revenue"),
            func.count(Quote.id).label("count"),
            min_date_expr.label("sort_date"),
        )
        .where(Quote.status == QuoteStatus.accepted)
        .group_by(period_expr)
        .order_by("sort_date")
        .limit(months)
    )
    return [RevenuePoint(period=r.period, revenue=r.revenue or 0, count=r.count) for r in result]


@reports_router.get("/fleet-utilization")
async def fleet_utilization(db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    total     = await db.scalar(select(func.count(Equipment.id))) or 1
    available = await db.scalar(select(func.count(Equipment.id)).where(Equipment.is_available == True)) or 0
    in_use    = total - available
    avg_health = await db.scalar(select(func.avg(Equipment.health_score))) or 0
    return {
        "total":        total,
        "in_use":       in_use,
        "available":    available,
        "utilization_pct": round(in_use / total * 100, 1),
        "avg_health_score": round(float(avg_health), 1),
    }


@reports_router.get("/leads-pipeline")
async def leads_pipeline(db: AsyncSession = Depends(get_db), _: User = Depends(require_staff_or_admin)):
    result = await db.execute(
        select(Lead.status, func.count(Lead.id).label("count"))
        .group_by(Lead.status)
    )
    rows = result.all()
    return {r.status: r.count for r in rows}
