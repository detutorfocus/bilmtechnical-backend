"""
Bilm Technical Services — ORM Models
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Integer, JSON, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class LeadStatus(str, enum.Enum):
    new       = "new"
    warm      = "warm"
    hot       = "hot"
    cold      = "cold"
    converted = "converted"
    lost      = "lost"


class QuoteStatus(str, enum.Enum):
    draft       = "draft"
    sent        = "sent"
    negotiating = "negotiating"
    accepted    = "accepted"
    expired     = "expired"
    cancelled   = "cancelled"


class RentalStatus(str, enum.Enum):
    active    = "active"
    due       = "due"
    overdue   = "overdue"
    completed = "completed"
    cancelled = "cancelled"


class MaintType(str, enum.Enum):
    scheduled  = "scheduled"
    preventive = "preventive"
    corrective = "corrective"
    emergency  = "emergency"


class MaintStatus(str, enum.Enum):
    scheduled   = "scheduled"
    in_progress = "in_progress"
    completed   = "completed"
    cancelled   = "cancelled"


class EmailStatus(str, enum.Enum):
    queued  = "queued"
    sent    = "sent"
    failed  = "failed"
    opened  = "opened"
    replied = "replied"
    cancelled = "cancelled"


class UserRole(str, enum.Enum):
    admin  = "admin"
    staff  = "staff"
    client = "client"


class EquipmentCategory(str, enum.Enum):
    generator    = "generator"
    forklift     = "forklift"
    construction = "construction"
    other        = "other"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _short_uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


# ─── Models ───────────────────────────────────────────────────────────────────

class CompanySettings(Base):
    """Admin-editable company profile stored in DB (not hardcoded)."""
    __tablename__ = "company_settings"

    id              = Column(Integer, primary_key=True)
    key             = Column(String(100), unique=True, nullable=False)
    value           = Column(Text)
    description     = Column(String(300))
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailTemplate(Base):
    """Fully editable email templates stored in DB."""
    __tablename__ = "email_templates"

    id              = Column(Integer, primary_key=True)
    slug            = Column(String(100), unique=True, nullable=False)
    name            = Column(String(200), nullable=False)
    subject         = Column(String(300), nullable=False)
    body_html       = Column(Text, nullable=False)
    body_text       = Column(Text)
    variables       = Column(JSON)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, onupdate=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True)
    email           = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(300), nullable=False)
    full_name       = Column(String(200))
    role            = Column(Enum(UserRole), default=UserRole.staff)
    is_active       = Column(Boolean, default=True)
    client_id       = Column(ForeignKey("clients.id"), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # ── Email-based OTP (2FA) ──────────────────────────────────────────────
    # Both nullable — a user has no pending OTP most of the time. Set on
    # POST /auth/login (step 1), consumed and cleared on POST /auth/verify-otp
    # (step 2). See app/routers/auth.py for the full flow.
    otp_code        = Column(String(6), nullable=True)
    otp_expires_at  = Column(DateTime, nullable=True)

    client          = relationship("Client", back_populates="user", uselist=False)


class Client(Base):
    __tablename__ = "clients"

    id              = Column(Integer, primary_key=True)
    ref_code        = Column(String(30), unique=True, default=lambda: _short_uid("CLT"))
    company_name    = Column(String(200), nullable=False)
    contact_person  = Column(String(150))
    # unique=True: DB-level guard against duplicate client records.
    # The API-level check in create_client() gives a friendly 409 response
    # first, but this column constraint is what actually prevents a
    # duplicate if two requests race each other (API-level checks alone
    # aren't safe against concurrent requests).
    email           = Column(String(200), nullable=False, unique=True)
    phone           = Column(String(30))
    address         = Column(Text)
    industry        = Column(String(100))
    notes           = Column(Text)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, onupdate=datetime.utcnow)

    user            = relationship("User", back_populates="client", uselist=False)
    quotes          = relationship("Quote", back_populates="client", foreign_keys="Quote.client_id")
    rentals         = relationship("Rental", back_populates="client")
    email_logs      = relationship("EmailLog", back_populates="client")


class Lead(Base):
    __tablename__ = "leads"

    id              = Column(Integer, primary_key=True)
    ref_code        = Column(String(30), unique=True, default=lambda: _short_uid("L"))
    company_name    = Column(String(200), nullable=False)
    contact_person  = Column(String(150))
    email           = Column(String(200), nullable=False)
    phone           = Column(String(30))
    service_type    = Column(String(100))
    equipment_type  = Column(String(100))
    rental_duration = Column(String(80))
    description     = Column(Text)
    estimated_value = Column(Numeric(12, 2))
    status          = Column(Enum(LeadStatus), default=LeadStatus.new)
    source          = Column(String(80), default="website")
    notes           = Column(Text)
    converted_at    = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, onupdate=datetime.utcnow)

    quotes          = relationship("Quote", back_populates="lead", foreign_keys="Quote.lead_id")
    email_logs      = relationship("EmailLog", back_populates="lead")


class Equipment(Base):
    __tablename__ = "equipment"

    id              = Column(Integer, primary_key=True)
    ref_code        = Column(String(30), unique=True, default=lambda: _short_uid("EQ"))
    name            = Column(String(200), nullable=False)
    category        = Column(Enum(EquipmentCategory), nullable=False)
    make            = Column(String(100))
    model           = Column(String(100))
    capacity        = Column(String(80))
    year            = Column(Integer)
    serial_number   = Column(String(100))
    specs           = Column(JSON)
    daily_rate      = Column(Numeric(12, 2))
    monthly_rate    = Column(Numeric(12, 2))
    health_score    = Column(Integer, default=100)
    is_available    = Column(Boolean, default=True)
    image_url       = Column(String(500))
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, onupdate=datetime.utcnow)

    rentals         = relationship("Rental", back_populates="equipment")
    maintenance     = relationship("MaintenanceRecord", back_populates="equipment")


class Quote(Base):
    __tablename__ = "quotes"

    id              = Column(Integer, primary_key=True)
    quote_number    = Column(String(30), unique=True, default=lambda: _short_uid("QT"))
    lead_id         = Column(ForeignKey("leads.id"), nullable=True)
    client_id       = Column(ForeignKey("clients.id"), nullable=True)
    rental_id       = Column(ForeignKey("rentals.id"), nullable=True)
    service_desc    = Column(Text)
    equipment_type  = Column(String(100))
    duration        = Column(String(80))
    amount          = Column(Numeric(12, 2))
    vat_rate        = Column(Numeric(5, 2), default=7.5)
    status          = Column(Enum(QuoteStatus), default=QuoteStatus.draft)
    valid_until     = Column(Date)
    pdf_path        = Column(String(500))
    notes           = Column(Text)
    sent_at         = Column(DateTime)
    accepted_at     = Column(DateTime)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, onupdate=datetime.utcnow)

    lead            = relationship("Lead", back_populates="quotes", foreign_keys=[lead_id])
    client          = relationship("Client", back_populates="quotes", foreign_keys=[client_id])
    rental          = relationship("Rental", back_populates="quote", foreign_keys=[rental_id])


class Rental(Base):
    __tablename__ = "rentals"

    id              = Column(Integer, primary_key=True)
    rental_code     = Column(String(30), unique=True, default=lambda: _short_uid("RNT"))
    client_id       = Column(ForeignKey("clients.id"), nullable=False)
    equipment_id    = Column(ForeignKey("equipment.id"), nullable=False)
    start_date      = Column(Date, nullable=False)
    end_date        = Column(Date, nullable=False)
    monthly_rate    = Column(Numeric(12, 2))
    status          = Column(Enum(RentalStatus), default=RentalStatus.active)
    health_score    = Column(Integer, default=100)
    site_location   = Column(String(300))
    notes           = Column(Text)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, onupdate=datetime.utcnow)

    quote           = relationship("Quote", back_populates="rental", foreign_keys="Quote.rental_id", uselist=False)
    client          = relationship("Client", back_populates="rentals")
    equipment       = relationship("Equipment", back_populates="rentals")
    maintenance     = relationship("MaintenanceRecord", back_populates="rental")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id              = Column(Integer, primary_key=True)
    maint_code      = Column(String(30), unique=True, default=lambda: _short_uid("MNT"))
    rental_id       = Column(ForeignKey("rentals.id"), nullable=True)
    equipment_id    = Column(ForeignKey("equipment.id"), nullable=False)
    maint_type      = Column(Enum(MaintType), nullable=False)
    technician      = Column(String(150))
    scheduled_date  = Column(Date)
    completed_date  = Column(Date)
    status          = Column(Enum(MaintStatus), default=MaintStatus.scheduled)
    report          = Column(Text)
    parts_used      = Column(JSON)
    cost            = Column(Numeric(12, 2))
    health_before   = Column(Integer)
    health_after    = Column(Integer)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, onupdate=datetime.utcnow)

    rental          = relationship("Rental", back_populates="maintenance")
    equipment       = relationship("Equipment", back_populates="maintenance")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id              = Column(Integer, primary_key=True)
    lead_id         = Column(ForeignKey("leads.id"), nullable=True)
    client_id       = Column(ForeignKey("clients.id"), nullable=True)
    template_slug   = Column(String(100))
    recipient_email = Column(String(200), nullable=False)
    recipient_name  = Column(String(200))
    subject         = Column(String(300))
    status          = Column(Enum(EmailStatus), default=EmailStatus.queued)
    scheduled_at    = Column(DateTime)
    sent_at         = Column(DateTime)
    opened_at       = Column(DateTime)
    error_message   = Column(Text)
    celery_task_id  = Column(String(200))
    context_data    = Column(JSON)
    created_at      = Column(DateTime, default=datetime.utcnow)

    lead            = relationship("Lead", back_populates="email_logs")
    client          = relationship("Client", back_populates="email_logs")
