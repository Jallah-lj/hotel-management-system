"""Reservations, accompanying guests, folio charges, check-in and check-out."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.db.enums import (
    BookingSource,
    ChargeType,
    FolioStatus,
    PaymentStatus,
    ReservationStatus,
)

if TYPE_CHECKING:
    from app.db.models.billing import Invoice, Payment
    from app.db.models.guest import Guest
    from app.db.models.operations import ServiceOrder
    from app.db.models.property import Room, RoomType
    from app.db.models.user import User


class Reservation(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "reservations"

    reference: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)

    guest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("room_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Room may be assigned at booking time or later (e.g. at check-in) for
    # reservations that only guarantee a room *type*.
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rooms.id", ondelete="RESTRICT"), index=True
    )

    check_in_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_out_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nights: Mapped[int] = mapped_column(Integer, nullable=False)
    adults: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    children: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    room_rate: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    extra_person_charge: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # Monetary summary mirrors the folio (reservation_charges) and is refreshed
    # by the pricing service after every change so that list/report queries stay
    # fast and consistent.
    room_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    services_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    charges_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    discount_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    paid_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    refunded_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=10)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_reason: Mapped[str | None] = mapped_column(String(180))

    status: Mapped[ReservationStatus] = enum_column(
        ReservationStatus, "reservation_status", nullable=False, default=ReservationStatus.PENDING, index=True
    )
    payment_status: Mapped[PaymentStatus] = enum_column(
        PaymentStatus, "reservation_payment_status", nullable=False, default=PaymentStatus.PENDING, index=True
    )
    folio_status: Mapped[FolioStatus] = enum_column(
        FolioStatus, "folio_status", nullable=False, default=FolioStatus.OPEN
    )
    booking_source: Mapped[BookingSource] = enum_column(
        BookingSource, "booking_source", nullable=False, default=BookingSource.WALK_IN
    )

    special_requests: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    no_show_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    folio_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    guest: Mapped["Guest"] = relationship(back_populates="reservations", lazy="joined")
    room: Mapped["Room | None"] = relationship(back_populates="reservations", lazy="joined")
    room_type: Mapped["RoomType"] = relationship(lazy="joined")
    guests: Mapped[list["ReservationGuest"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan"
    )
    charges: Mapped[list["ReservationCharge"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", order_by="ReservationCharge.posted_at"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="reservation")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="reservation")
    orders: Mapped[list["ServiceOrder"]] = relationship(back_populates="reservation")
    check_in: Mapped["CheckIn | None"] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", uselist=False
    )
    check_out: Mapped["CheckOut | None"] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint("check_out_date > check_in_date", name="reservation_stay_window_valid"),
        CheckConstraint("nights > 0", name="reservation_nights_positive"),
        CheckConstraint("adults >= 1", name="reservation_adults_min_one"),
        CheckConstraint("children >= 0", name="reservation_children_non_negative"),
        CheckConstraint("room_rate >= 0", name="reservation_rate_non_negative"),
        CheckConstraint("discount_amount >= 0", name="reservation_discount_non_negative"),
        Index("ix_reservations_room_window", "room_id", "check_in_date", "check_out_date"),
        Index("ix_reservations_status_window", "status", "check_in_date"),
    )

    @property
    def guest_name(self) -> str:
        return self.guest.full_name if self.guest else ""

    @property
    def is_active(self) -> bool:
        return self.status in (
            ReservationStatus.PENDING,
            ReservationStatus.CONFIRMED,
            ReservationStatus.CHECKED_IN,
        )


class ReservationGuest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Additional occupants sharing the reservation (children, colleagues...)."""

    __tablename__ = "reservation_guests"

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guest_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("guests.id", ondelete="SET NULL")
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    relationship_to_lead: Mapped[str | None] = mapped_column(String(48))
    is_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    age: Mapped[int | None] = mapped_column(Integer)
    id_document_number: Mapped[str | None] = mapped_column(String(64))

    reservation: Mapped[Reservation] = relationship(back_populates="guests")
    guest: Mapped["Guest | None"] = relationship()

    __table_args__ = (
        UniqueConstraint("reservation_id", "guest_id", name="reservation_guest_unique"),
        CheckConstraint("age IS NULL OR age >= 0", name="reservation_guest_age_non_negative"),
    )


class ReservationCharge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A folio line. Room, service and restaurant charges are posted here and
    the reservation totals are derived from this table."""

    __tablename__ = "reservation_charges"

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    charge_type: Mapped[ChargeType] = enum_column(
        ChargeType, "charge_type", nullable=False, default=ChargeType.ROOM, index=True
    )
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    service_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_orders.id", ondelete="SET NULL")
    )
    service_date: Mapped[date | None] = mapped_column(Date, index=True)
    is_voided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    void_reason: Mapped[str | None] = mapped_column(String(180))
    notes: Mapped[str | None] = mapped_column(Text)

    posted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    reservation: Mapped[Reservation] = relationship(back_populates="charges")
    posted_by: Mapped["User | None"] = relationship(foreign_keys=[posted_by_id])

    __table_args__ = (
        CheckConstraint("quantity > 0", name="charge_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="charge_unit_price_non_negative"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="charge_tax_rate_range"),
        CheckConstraint("discount_amount >= 0", name="charge_discount_non_negative"),
    )


class CheckIn(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "check_ins"
    __table_args__ = (UniqueConstraint("reservation_id", name="check_in_reservation_unique"),)

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_in_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    deposit_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    registration_card_signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    key_cards_issued: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text)
    confirmation_code: Mapped[str] = mapped_column(String(24), nullable=False)

    reservation: Mapped[Reservation] = relationship(back_populates="check_in")
    room: Mapped["Room | None"] = relationship()
    checked_in_by: Mapped["User | None"] = relationship()


class CheckOut(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "check_outs"
    __table_args__ = (UniqueConstraint("reservation_id", name="check_out_reservation_unique"),)

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    checked_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checked_out_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    final_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    balance_settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    override_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    override_reason: Mapped[str | None] = mapped_column(Text)
    keys_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    minibar_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    luggage_collected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    reservation: Mapped[Reservation] = relationship(back_populates="check_out")
    room: Mapped["Room | None"] = relationship()
    checked_out_by: Mapped["User | None"] = relationship(foreign_keys=[checked_out_by_id])
    override_by: Mapped["User | None"] = relationship(foreign_keys=[override_by_id])
