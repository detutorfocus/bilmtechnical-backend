"""
Bilm Technical Services — Pydantic Schemas (request / response)
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─── Shared base ─────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = {"from_attributes": True}


# ─── Company Settings ─────────────────────────────────────────────────────────

class SettingItem(OrmBase):
    key: str
    value: Optional[str]
    description: Optional[str]

class SettingUpdate(BaseModel):
    value: str


# ─── Email Templates ──────────────────────────────────────────────────────────

class EmailTemplateBase(BaseModel):
    name:       str
    subject:    str
    body_html:  str
    body_text:  Optional[str] = None
    variables:  Optional[List[str]] = None
    is_active:  bool = True

class EmailTemplateCreate(EmailTemplateBase):
    slug: str

class EmailTemplateUpdate(BaseModel):
    name:       Optional[str] = None
    subject:    Optional[str] = None
    body_html:  Optional[str] = None
    body_text:  Optional[str] = None
    variables:  Optional[List[str]] = None
    is_active:  Optional[bool] = None

class EmailTemplateOut(EmailTemplateBase, OrmBase):
    id:         int
    slug:       str
    updated_at: Optional[datetime]

class EmailTemplatePreview(BaseModel):
    recipient_email: EmailStr
    context:         Dict[str, Any] = {}


# ─── Auth ────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[int] = None
    role:    Optional[str] = None

class UserLogin(BaseModel):
    email:    EmailStr
    password: str

class UserCreate(BaseModel):
    email:     EmailStr
    password:  str = Field(min_length=8)
    full_name: Optional[str] = None
    role:      str = "staff"
    client_id: Optional[int] = None

class UserOut(OrmBase):
    id:        int
    email:     str
    full_name: Optional[str]
    role:      str
    is_active: bool


# ─── Client ──────────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    company_name:   str
    contact_person: Optional[str] = None
    email:          EmailStr
    phone:          Optional[str] = None
    address:        Optional[str] = None
    industry:       Optional[str] = None
    notes:          Optional[str] = None

class ClientUpdate(BaseModel):
    company_name:   Optional[str] = None
    contact_person: Optional[str] = None
    email:          Optional[EmailStr] = None
    phone:          Optional[str] = None
    address:        Optional[str] = None
    industry:       Optional[str] = None
    notes:          Optional[str] = None
    is_active:      Optional[bool] = None

class ClientOut(OrmBase):
    id:             int
    ref_code:       str
    company_name:   str
    contact_person: Optional[str]
    email:          str
    phone:          Optional[str]
    address:        Optional[str]
    industry:       Optional[str]
    is_active:      bool
    created_at:     datetime


# ─── Lead ────────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    company_name:    str
    contact_person:  Optional[str] = None
    email:           EmailStr
    phone:           Optional[str] = None
    service_type:    Optional[str] = None
    equipment_type:  Optional[str] = None
    rental_duration: Optional[str] = None
    description:     Optional[str] = None
    source:          str = "website"

class LeadUpdate(BaseModel):
    status:          Optional[str] = None
    notes:           Optional[str] = None
    estimated_value: Optional[Decimal] = None
    service_type:    Optional[str] = None
    equipment_type:  Optional[str] = None

class LeadOut(OrmBase):
    id:              int
    ref_code:        str
    company_name:    str
    contact_person:  Optional[str]
    email:           str
    phone:           Optional[str]
    service_type:    Optional[str]
    equipment_type:  Optional[str]
    rental_duration: Optional[str]
    description:     Optional[str]
    estimated_value: Optional[Decimal]
    status:          str
    source:          str
    notes:           Optional[str]
    created_at:      datetime
    updated_at:      Optional[datetime]


# ─── Equipment ────────────────────────────────────────────────────────────────

class EquipmentCreate(BaseModel):
    name:          str
    category:      str
    make:          Optional[str] = None
    model:         Optional[str] = None
    capacity:      Optional[str] = None
    year:          Optional[int] = None
    serial_number: Optional[str] = None
    specs:         Optional[List[str]] = None
    daily_rate:    Optional[Decimal] = None
    monthly_rate:  Optional[Decimal] = None
    image_url:     Optional[str] = None
    notes:         Optional[str] = None

class EquipmentUpdate(BaseModel):
    name:          Optional[str] = None
    make:          Optional[str] = None
    model:         Optional[str] = None
    capacity:      Optional[str] = None
    specs:         Optional[List[str]] = None
    daily_rate:    Optional[Decimal] = None
    monthly_rate:  Optional[Decimal] = None
    health_score:  Optional[int] = None
    is_available:  Optional[bool] = None
    image_url:     Optional[str] = None
    notes:         Optional[str] = None

class EquipmentOut(OrmBase):
    id:            int
    ref_code:      str
    name:          str
    category:      str
    make:          Optional[str]
    model:         Optional[str]
    capacity:      Optional[str]
    year:          Optional[int]
    specs:         Optional[List[str]]
    daily_rate:    Optional[Decimal]
    monthly_rate:  Optional[Decimal]
    health_score:  int
    is_available:  bool
    image_url:     Optional[str]


# ─── Quote ───────────────────────────────────────────────────────────────────

class QuoteCreate(BaseModel):
    lead_id:       Optional[int] = None
    client_id:     Optional[int] = None
    rental_id:     Optional[int] = None
    service_desc:  Optional[str] = None
    equipment_type:Optional[str] = None
    duration:      Optional[str] = None
    amount:        Optional[Decimal] = None
    vat_rate:      Decimal = Decimal("7.5")
    valid_until:   Optional[date] = None
    notes:         Optional[str] = None

class QuoteUpdate(BaseModel):
    service_desc:  Optional[str] = None
    equipment_type:Optional[str] = None
    duration:      Optional[str] = None
    amount:        Optional[Decimal] = None
    vat_rate:      Optional[Decimal] = None
    valid_until:   Optional[date] = None
    status:        Optional[str] = None
    notes:         Optional[str] = None

class QuoteOut(OrmBase):
    id:            int
    quote_number:  str
    lead_id:       Optional[int]
    client_id:     Optional[int]
    rental_id:     Optional[int]
    service_desc:  Optional[str]
    equipment_type:Optional[str]
    duration:      Optional[str]
    amount:        Optional[Decimal]
    vat_rate:      Optional[Decimal]
    status:        str
    valid_until:   Optional[date]
    notes:         Optional[str]
    sent_at:       Optional[datetime]
    accepted_at:   Optional[datetime]
    created_at:    datetime


# ─── Rental ──────────────────────────────────────────────────────────────────

class RentalCreate(BaseModel):
    client_id:     int
    equipment_id:  int
    start_date:    date
    end_date:      date
    monthly_rate:  Optional[Decimal] = None
    site_location: Optional[str] = None
    notes:         Optional[str] = None

class RentalUpdate(BaseModel):
    end_date:      Optional[date] = None
    status:        Optional[str] = None
    health_score:  Optional[int] = None
    site_location: Optional[str] = None
    notes:         Optional[str] = None

class RentalOut(OrmBase):
    id:            int
    rental_code:   str
    client_id:     int
    equipment_id:  int
    start_date:    date
    end_date:      date
    monthly_rate:  Optional[Decimal]
    status:        str
    health_score:  int
    site_location: Optional[str]
    created_at:    datetime

class RentalWithRelations(RentalOut):
    client:        Optional[ClientOut]
    equipment:     Optional[EquipmentOut]


# ─── Maintenance ─────────────────────────────────────────────────────────────

class MaintenanceCreate(BaseModel):
    rental_id:      Optional[int] = None
    equipment_id:   int
    maint_type:     str
    technician:     Optional[str] = None
    scheduled_date: Optional[date] = None
    notes:          Optional[str] = None

class MaintenanceUpdate(BaseModel):
    status:         Optional[str] = None
    technician:     Optional[str] = None
    scheduled_date: Optional[date] = None
    completed_date: Optional[date] = None
    report:         Optional[str] = None
    parts_used:     Optional[List[Dict]] = None
    cost:           Optional[Decimal] = None
    health_after:   Optional[int] = None

class MaintenanceOut(OrmBase):
    id:             int
    maint_code:     str
    rental_id:      Optional[int]
    equipment_id:   int
    maint_type:     str
    technician:     Optional[str]
    scheduled_date: Optional[date]
    completed_date: Optional[date]
    status:         str
    report:         Optional[str]
    cost:           Optional[Decimal]
    health_before:  Optional[int]
    health_after:   Optional[int]
    created_at:     datetime


# ─── Email Log ────────────────────────────────────────────────────────────────

class EmailLogOut(OrmBase):
    id:              int
    lead_id:         Optional[int]
    client_id:       Optional[int]
    template_slug:   Optional[str]
    recipient_email: str
    recipient_name:  Optional[str]
    subject:         Optional[str]
    status:          str
    scheduled_at:    Optional[datetime]
    sent_at:         Optional[datetime]
    created_at:      datetime

class SendTestEmail(BaseModel):
    recipient_email: EmailStr
    template_slug:   str
    context:         Dict[str, Any] = {}


# ─── Reports ─────────────────────────────────────────────────────────────────

class KPIReport(BaseModel):
    total_leads:        int
    hot_leads:          int
    open_quotes:        int
    open_quotes_value:  Decimal
    active_rentals:     int
    overdue_rentals:    int
    queued_emails:      int
    fleet_total:        int
    fleet_available:    int

class RevenuePoint(BaseModel):
    period:  str
    revenue: Decimal
    count:   int

class ServiceBreakdown(BaseModel):
    service:  str
    count:    int
    revenue:  Decimal
    pct:      float


# ─── Pagination wrapper (GENERIC — fixes the serialization crash) ───────────
#
# ROOT CAUSE: the old `Page` schema declared `items: List[Any]`. "Any" tells
# Pydantic "I don't know the shape of this data", so when raw SQLAlchemy
# model instances (e.g. app.models.Lead) were placed inside it, Pydantic
# had no serializer and crashed with:
#   PydanticSerializationError: Unable to serialize unknown type: <class 'app.models.Lead'>
#
# FIX: Page is now Generic[T]. Each route declares response_model=Page[LeadOut],
# Page[QuoteOut], etc. so Pydantic knows exactly how to convert each item
# (via that schema's own OrmBase / from_attributes config) before serializing.

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items:   List[T]
    total:   int
    page:    int
    size:    int
    pages:   int
