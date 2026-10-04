"""Request/response schemas for the property, guest, stay, finance and
operations modules.  Schemas deliberately do not mirror every persistence
column: internal flags, hashes and soft-delete metadata never cross the API
boundary."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import EmailStr, Field, field_validator, model_validator

from app.db.enums import (
    BedType,
    BookingSource,
    ChargeType,
    ExpenseCategory,
    Gender,
    HousekeepingTaskStatus,
    HousekeepingTaskType,
    IdDocumentType,
    InvoiceStatus,
    MaintenanceCategory,
    MaintenanceStatus,
    NotificationCategory,
    NotificationSeverity,
    OrderStatus,
    OrderType,
    PaymentMethodType,
    PaymentStatus,
    Priority,
    ReservationStatus,
    RoomStatus,
    ServiceAvailability,
)
from app.schemas.common import ORMModel

Money = Decimal


def _date_order(values: Any):
    check_in, check_out = values.get("check_in_date"), values.get("check_out_date")
    if check_in and check_out and check_out <= check_in:
        raise ValueError("Check-out date must be after check-in date.")
    return values


# ---------------------------------------------------------------------------
# Guests
# ---------------------------------------------------------------------------
class GuestCreate(ORMModel):
    first_name: str = Field(min_length=1, max_length=96)
    last_name: str = Field(min_length=1, max_length=96)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    alternate_phone: str | None = Field(default=None, max_length=32)
    gender: Gender = Gender.UNDISCLOSED
    date_of_birth: date | None = None
    nationality: str | None = Field(default=None, max_length=64)
    address_line1: str | None = Field(default=None, max_length=180)
    address_line2: str | None = Field(default=None, max_length=180)
    city: str | None = Field(default=None, max_length=96)
    state: str | None = Field(default=None, max_length=96)
    postal_code: str | None = Field(default=None, max_length=24)
    country: str | None = Field(default=None, max_length=64)
    id_document_type: IdDocumentType | None = None
    id_document_number: str | None = Field(default=None, max_length=64)
    id_document_expiry: date | None = None
    id_verified: bool = False
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_phone: str | None = Field(default=None, max_length=32)
    emergency_contact_relation: str | None = Field(default=None, max_length=48)
    company_name: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    preferences: str | None = None
    marketing_opt_in: bool = False
    is_vip: bool = False

    @field_validator("first_name", "last_name")
    @classmethod
    def _person_name(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def _sensible_dates(self):
        if self.date_of_birth and self.date_of_birth >= date.today():
            raise ValueError("Date of birth must be in the past.")
        if self.id_document_expiry and self.id_document_expiry < date.today() and self.id_verified:
            raise ValueError("An expired document cannot be marked as verified.")
        return self


class GuestUpdate(GuestCreate):
    first_name: str | None = Field(default=None, min_length=1, max_length=96)
    last_name: str | None = Field(default=None, min_length=1, max_length=96)


class GuestOut(ORMModel):
    id: UUID
    reference: str
    first_name: str
    last_name: str
    full_name: str
    email: EmailStr | None = None
    phone: str | None = None
    alternate_phone: str | None = None
    gender: Gender
    date_of_birth: date | None = None
    nationality: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    id_document_type: IdDocumentType | None = None
    id_document_number: str | None = None
    id_document_expiry: date | None = None
    id_verified: bool
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None
    company_name: str | None = None
    notes: str | None = None
    preferences: str | None = None
    marketing_opt_in: bool
    blacklisted: bool
    total_stays: int
    total_nights: int
    total_spend: Decimal
    outstanding_balance: Decimal
    last_stay_at: datetime | None = None
    is_vip: bool
    created_at: datetime
    updated_at: datetime


class GuestSummary(ORMModel):
    id: UUID
    reference: str
    full_name: str
    email: EmailStr | None = None
    phone: str | None = None
    is_vip: bool


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------
class AmenityOut(ORMModel):
    id: UUID
    code: str
    name: str
    category: str
    icon: str | None = None
    is_active: bool


class RoomTypeCreate(ORMModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=96)
    description: str | None = None
    base_price: Money = Field(ge=0)
    weekend_price: Money | None = Field(default=None, ge=0)
    extra_person_price: Money = Field(default=0, ge=0)
    max_occupancy: int = Field(default=2, ge=1, le=50)
    max_adults: int = Field(default=2, ge=1, le=50)
    max_children: int = Field(default=0, ge=0, le=50)
    bed_type: BedType = BedType.QUEEN
    bed_count: int = Field(default=1, ge=1, le=20)
    size_sqm: int | None = Field(default=None, ge=1, le=1000)
    tax_rate: Money = Field(default=10, ge=0, le=100)
    is_active: bool = True
    hero_image_url: str | None = Field(default=None, max_length=512)
    sort_order: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _occupancy(self):
        if self.max_adults is not None and self.max_children is not None and self.max_occupancy is not None and self.max_adults + self.max_children > self.max_occupancy:
            raise ValueError("Adult and child limits cannot exceed maximum occupancy.")
        return self


class RoomTypeUpdate(ORMModel):
    code: str | None = Field(default=None, min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str | None = Field(default=None, min_length=2, max_length=96)
    description: str | None = None
    base_price: Money | None = Field(default=None, ge=0)
    weekend_price: Money | None = Field(default=None, ge=0)
    extra_person_price: Money | None = Field(default=None, ge=0)
    max_occupancy: int | None = Field(default=None, ge=1, le=50)
    max_adults: int | None = Field(default=None, ge=1, le=50)
    max_children: int | None = Field(default=None, ge=0, le=50)
    bed_type: BedType | None = None
    bed_count: int | None = Field(default=None, ge=1, le=20)
    size_sqm: int | None = Field(default=None, ge=1, le=1000)
    tax_rate: Money | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None
    hero_image_url: str | None = Field(default=None, max_length=512)
    sort_order: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _occupancy(self):
        if self.max_adults is not None and self.max_children is not None and self.max_occupancy is not None and self.max_adults + self.max_children > self.max_occupancy:
            raise ValueError("Adult and child limits cannot exceed maximum occupancy.")
        return self


class RoomTypeOut(ORMModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    base_price: Decimal
    weekend_price: Decimal | None = None
    extra_person_price: Decimal
    max_occupancy: int
    max_adults: int
    max_children: int
    bed_type: BedType
    bed_count: int
    size_sqm: int | None = None
    tax_rate: Decimal
    is_active: bool
    hero_image_url: str | None = None
    amenities: list[AmenityOut] = []


class RoomCreate(ORMModel):
    number: str = Field(min_length=1, max_length=16)
    name: str | None = Field(default=None, max_length=96)
    room_type_id: UUID
    floor: int = Field(default=1, ge=0, le=200)
    building: str | None = Field(default=None, max_length=48)
    wing: str | None = Field(default=None, max_length=48)
    capacity: int = Field(default=2, ge=1, le=50)
    bed_type: BedType = BedType.QUEEN
    bed_count: int = Field(default=1, ge=1, le=20)
    price_per_night: Money = Field(ge=0)
    status: RoomStatus = RoomStatus.AVAILABLE
    description: str | None = None
    images: list[str] = []
    view: str | None = Field(default=None, max_length=48)
    is_smoking: bool = False
    is_accessible: bool = False
    is_active: bool = True
    notes: str | None = None


class RoomUpdate(RoomCreate):
    number: str | None = Field(default=None, min_length=1, max_length=16)
    room_type_id: UUID | None = None


class RoomOut(ORMModel):
    id: UUID
    number: str
    name: str | None = None
    room_type_id: UUID
    room_type: RoomTypeOut
    floor: int
    building: str | None = None
    wing: str | None = None
    capacity: int
    bed_type: BedType
    bed_count: int
    price_per_night: Decimal
    status: RoomStatus
    housekeeping_condition: str
    maintenance_flag: str
    description: str | None = None
    images: list[str] | None = None
    view: str | None = None
    is_smoking: bool
    is_accessible: bool
    is_active: bool
    is_bookable: bool
    notes: str | None = None


class AvailabilityRoom(ORMModel):
    id: UUID
    number: str
    room_type_id: UUID
    room_type_name: str
    price_per_night: Decimal
    capacity: int
    status: RoomStatus


# ---------------------------------------------------------------------------
# Reservations / check-in/out
# ---------------------------------------------------------------------------
class ReservationCreate(ORMModel):
    guest_id: UUID
    room_type_id: UUID
    room_id: UUID | None = None
    check_in_date: date
    check_out_date: date
    adults: int = Field(default=1, ge=1, le=50)
    children: int = Field(default=0, ge=0, le=50)
    room_rate: Money | None = Field(default=None, ge=0)
    tax_rate: Money | None = Field(default=None, ge=0, le=100)
    discount_amount: Money = Field(default=0, ge=0)
    discount_reason: str | None = Field(default=None, max_length=180)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    booking_source: BookingSource = BookingSource.WALK_IN
    special_requests: str | None = None
    internal_notes: str | None = None

    @model_validator(mode="after")
    def _dates_and_currency(self):
        _date_order(self.__dict__)
        if self.currency != self.currency.upper():
            raise ValueError("Currency must use a 3-letter uppercase ISO code.")
        return self


class ReservationUpdate(ORMModel):
    room_id: UUID | None = None
    check_in_date: date | None = None
    check_out_date: date | None = None
    adults: int | None = Field(default=None, ge=1, le=50)
    children: int | None = Field(default=None, ge=0, le=50)
    room_rate: Money | None = Field(default=None, ge=0)
    discount_amount: Money | None = Field(default=None, ge=0)
    discount_reason: str | None = Field(default=None, max_length=180)
    booking_source: BookingSource | None = None
    special_requests: str | None = None
    internal_notes: str | None = None
    status: ReservationStatus | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.check_in_date and self.check_out_date and self.check_out_date <= self.check_in_date:
            raise ValueError("Check-out date must be after check-in date.")
        return self


class ReservationOut(ORMModel):
    id: UUID
    reference: str
    guest_id: UUID
    guest: GuestSummary
    room_type_id: UUID
    room_type: RoomTypeOut
    room_id: UUID | None = None
    room: RoomOut | None = None
    check_in_date: date
    check_out_date: date
    nights: int
    adults: int
    children: int
    room_rate: Decimal
    room_total: Decimal
    services_total: Decimal
    charges_total: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    refunded_amount: Decimal
    balance: Decimal
    currency: str
    status: ReservationStatus
    payment_status: PaymentStatus
    folio_status: str
    booking_source: BookingSource
    special_requests: str | None = None
    internal_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CancellationRequest(ORMModel):
    reason: str = Field(min_length=2, max_length=500)


class CheckInRequest(ORMModel):
    room_id: UUID | None = None
    deposit_amount: Money = Field(default=0, ge=0)
    identity_verified: bool = False
    registration_card_signed: bool = False
    key_cards_issued: int = Field(default=1, ge=1, le=20)
    notes: str | None = None


class CheckOutRequest(ORMModel):
    payment_amount: Money = Field(default=0, ge=0)
    payment_method: PaymentMethodType = PaymentMethodType.CASH
    payment_reference: str | None = Field(default=None, max_length=96)
    allow_balance_override: bool = False
    override_reason: str | None = Field(default=None, max_length=500)
    keys_returned: bool = True
    minibar_checked: bool = False
    luggage_collected: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _override(self):
        if self.allow_balance_override and not self.override_reason:
            raise ValueError("An override reason is required when leaving a balance outstanding.")
        return self


class CheckInOut(ORMModel):
    id: UUID
    reservation_id: UUID
    room_id: UUID | None = None
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    confirmation_code: str | None = None
    final_balance: Decimal | None = None
    balance_settled: bool | None = None


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------
class PaymentCreate(ORMModel):
    reservation_id: UUID
    amount: Money = Field(gt=0)
    method: PaymentMethodType = PaymentMethodType.CASH
    reference: str | None = Field(default=None, max_length=96)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    notes: str | None = None


class PaymentOut(ORMModel):
    id: UUID
    number: str
    reservation_id: UUID
    guest_id: UUID
    entry_type: str
    amount: Decimal
    currency: str
    method_code: str
    method_label: str
    reference: str | None = None
    status: PaymentStatus
    paid_at: datetime
    received_by_id: UUID | None = None
    notes: str | None = None


class RefundCreate(ORMModel):
    amount: Money = Field(gt=0)
    reason: str = Field(min_length=2, max_length=500)


class InvoiceItemOut(ORMModel):
    id: UUID
    charge_type: ChargeType
    description: str
    service_date: date | None = None
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal


class InvoiceOut(ORMModel):
    id: UUID
    number: str
    reservation_id: UUID
    guest_id: UUID
    status: InvoiceStatus
    issue_date: date
    due_date: date | None = None
    guest_name: str
    guest_email: EmailStr | None = None
    currency: str
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    balance: Decimal
    is_receipt: bool
    items: list[InvoiceItemOut] = []
    created_at: datetime


# ---------------------------------------------------------------------------
# Services and F&B
# ---------------------------------------------------------------------------
class ServiceCreate(ORMModel):
    code: str = Field(min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=96)
    description: str | None = None
    category: str = Field(default="general", max_length=48)
    price: Money = Field(ge=0)
    tax_rate: Money = Field(default=0, ge=0, le=100)
    unit: str = Field(default="per service", max_length=24)
    availability: ServiceAvailability = ServiceAvailability.ALWAYS
    requires_scheduling: bool = False
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_active: bool = True
    is_taxable: bool = True


class ServiceUpdate(ORMModel):
    code: str | None = Field(default=None, min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str | None = Field(default=None, min_length=2, max_length=96)
    description: str | None = None
    category: str | None = Field(default=None, max_length=48)
    price: Money | None = Field(default=None, ge=0)
    tax_rate: Money | None = Field(default=None, ge=0, le=100)
    unit: str | None = Field(default=None, max_length=24)
    availability: ServiceAvailability | None = None
    requires_scheduling: bool | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    is_active: bool | None = None
    is_taxable: bool | None = None


class ServiceOut(ORMModel):
    id: UUID
    code: str
    name: str
    description: str | None = None
    category: str
    price: Decimal
    tax_rate: Decimal
    unit: str
    availability: ServiceAvailability
    requires_scheduling: bool
    duration_minutes: int | None = None
    is_active: bool
    is_taxable: bool


class OrderItemCreate(ORMModel):
    service_id: UUID | None = None
    menu_item_id: UUID | None = None
    quantity: Decimal = Field(gt=0)
    notes: str | None = None

    @model_validator(mode="after")
    def _one_source(self):
        if bool(self.service_id) == bool(self.menu_item_id):
            raise ValueError("Choose exactly one service or menu item.")
        return self


class ServiceOrderCreate(ORMModel):
    reservation_id: UUID | None = None
    guest_id: UUID | None = None
    room_id: UUID | None = None
    order_type: OrderType = OrderType.ROOM_SERVICE
    table_reference: str | None = Field(default=None, max_length=24)
    is_room_service: bool = True
    items: list[OrderItemCreate] = Field(min_length=1)
    notes: str | None = None


class ServiceOrderStatusUpdate(ORMModel):
    status: OrderStatus
    notes: str | None = None


class ServiceOrderItemOut(ORMModel):
    id: UUID
    name_snapshot: str
    quantity: Decimal
    unit_price: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class ServiceOrderOut(ORMModel):
    id: UUID
    order_number: str
    order_type: OrderType
    status: OrderStatus
    reservation_id: UUID | None = None
    guest_id: UUID | None = None
    room_id: UUID | None = None
    table_reference: str | None = None
    is_room_service: bool
    is_billed: bool
    subtotal: Decimal
    tax_amount: Decimal
    service_charge: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    currency: str
    placed_at: datetime
    items: list[ServiceOrderItemOut] = []


# ---------------------------------------------------------------------------
# Housekeeping / maintenance / expenses
# ---------------------------------------------------------------------------
class HousekeepingTaskCreate(ORMModel):
    room_id: UUID
    task_type: HousekeepingTaskType = HousekeepingTaskType.STAYOVER_CLEAN
    priority: Priority = Priority.MEDIUM
    assigned_to_id: UUID | None = None
    scheduled_date: date | None = None
    scheduled_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    notes: str | None = None


class HousekeepingTaskUpdate(ORMModel):
    status: HousekeepingTaskStatus | None = None
    assigned_to_id: UUID | None = None
    priority: Priority | None = None
    completion_notes: str | None = None
    maintenance_reported: bool | None = None
    damage_reported: bool | None = None


class HousekeepingTaskOut(ORMModel):
    id: UUID
    room_id: UUID
    task_type: HousekeepingTaskType
    status: HousekeepingTaskStatus
    priority: Priority
    assigned_to_id: UUID | None = None
    scheduled_date: date
    scheduled_time: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    notes: str | None = None
    completion_notes: str | None = None
    maintenance_reported: bool
    damage_reported: bool
    room: RoomOut | None = None


class MaintenanceTicketCreate(ORMModel):
    room_id: UUID | None = None
    location: str | None = Field(default=None, max_length=96)
    category: MaintenanceCategory = MaintenanceCategory.OTHER
    priority: Priority = Priority.MEDIUM
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3)
    blocks_room: bool = False


class MaintenanceTicketUpdate(ORMModel):
    status: MaintenanceStatus | None = None
    priority: Priority | None = None
    assigned_to_id: UUID | None = None
    resolution_notes: str | None = None
    cost: Money | None = Field(default=None, ge=0)
    blocks_room: bool | None = None


class MaintenanceTicketOut(ORMModel):
    id: UUID
    ticket_number: str
    room_id: UUID | None = None
    location: str | None = None
    category: MaintenanceCategory
    priority: Priority
    status: MaintenanceStatus
    title: str
    description: str
    reported_by_id: UUID | None = None
    assigned_to_id: UUID | None = None
    reported_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    resolution_notes: str | None = None
    cost: Decimal
    blocks_room: bool


class NotificationOut(ORMModel):
    id: UUID
    category: NotificationCategory
    severity: NotificationSeverity
    title: str
    message: str
    link: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class ExpenseCreate(ORMModel):
    category: ExpenseCategory
    description: str = Field(min_length=2, max_length=200)
    amount: Money = Field(gt=0)
    tax_amount: Money = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    expense_date: date
    payment_method: PaymentMethodType = PaymentMethodType.CASH
    vendor: str | None = Field(default=None, max_length=120)
    reference: str | None = Field(default=None, max_length=96)
    notes: str | None = None


class ExpenseOut(ORMModel):
    id: UUID
    expense_number: str
    category: ExpenseCategory
    description: str
    amount: Decimal
    tax_amount: Decimal
    currency: str
    expense_date: date
    payment_method_label: str | None = None
    vendor: str | None = None
    reference: str | None = None
    recorded_by_id: UUID | None = None
    created_at: datetime
    notes: str | None = None


# ---------------------------------------------------------------------------
# Dashboard / reporting payloads
# ---------------------------------------------------------------------------
class DashboardStats(ORMModel):
    total_rooms: int
    available_rooms: int
    occupied_rooms: int
    reserved_rooms: int
    cleaning_rooms: int
    maintenance_rooms: int
    occupancy_rate: float
    today_check_ins: int
    today_check_outs: int
    current_guests: int
    today_revenue: Decimal
    month_revenue: Decimal
    outstanding_payments: Decimal
    pending_housekeeping: int


class ChartPoint(ORMModel):
    label: str
    value: Decimal | float
    secondary: Decimal | float | None = None


class DashboardOut(ORMModel):
    stats: DashboardStats
    revenue_trend: list[ChartPoint]
    occupancy_trend: list[ChartPoint]
    reservation_mix: list[ChartPoint]
    payment_methods: list[ChartPoint]
    upcoming_arrivals: list[ReservationOut]
    upcoming_departures: list[ReservationOut]


class ReportOut(ORMModel):
    name: str
    generated_at: datetime
    date_from: date
    date_to: date
    summary: dict[str, Any]
    series: list[ChartPoint] = []
    rows: list[dict[str, Any]] = []
