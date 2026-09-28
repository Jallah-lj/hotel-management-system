"""Payments, payment methods, invoices and invoice lines."""

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
    ChargeType,
    InvoiceStatus,
    PaymentEntryType,
    PaymentMethodType,
    PaymentStatus,
)

if TYPE_CHECKING:
    from app.db.models.guest import Guest
    from app.db.models.reservation import Reservation
    from app.db.models.user import User


class PaymentMethod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payment_methods"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[PaymentMethodType] = enum_column(
        PaymentMethodType, "payment_method_type", nullable=False, default=PaymentMethodType.OTHER
    )
    description: Mapped[str | None] = mapped_column(String(255))
    requires_reference: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    instructions: Mapped[str | None] = mapped_column(Text)


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A money movement against a reservation.

    ``amount`` is always stored positive; ``entry_type`` records whether it is a
    payment or a refund, which keeps the table auditable and the refund rules
    explicit.  No card numbers, CVVs or bank credentials are ever persisted -
    only a non-sensitive external reference (authorisation code, transfer id).
    """

    __tablename__ = "payments"

    number: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    guest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), index=True
    )
    parent_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL")
    )

    entry_type: Mapped[PaymentEntryType] = enum_column(
        PaymentEntryType, "payment_entry_type", nullable=False, default=PaymentEntryType.PAYMENT, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    method_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_methods.id", ondelete="RESTRICT")
    )
    method_code: Mapped[str] = mapped_column(String(32), nullable=False, default="cash")
    method_label: Mapped[str] = mapped_column(String(64), nullable=False, default="Cash")
    reference: Mapped[str | None] = mapped_column(String(96))
    status: Mapped[PaymentStatus] = enum_column(
        PaymentStatus, "payment_status", nullable=False, default=PaymentStatus.PAID, index=True
    )
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    void_reason: Mapped[str | None] = mapped_column(Text)

    reservation: Mapped["Reservation"] = relationship(back_populates="payments")
    guest: Mapped["Guest"] = relationship()
    invoice: Mapped["Invoice | None"] = relationship(back_populates="payments")
    method: Mapped[PaymentMethod | None] = relationship()
    received_by: Mapped["User | None"] = relationship(foreign_keys=[received_by_id])
    refunds: Mapped[list["Payment"]] = relationship(
        remote_side="Payment.parent_payment_id", viewonly=True, uselist=True
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="payment_amount_positive"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="payment_currency_format"),
        Index("ix_payments_paid_at", "paid_at"),
        Index("ix_payments_reservation_entry", "reservation_id", "entry_type"),
        Index("ix_payments_status_entry", "status", "entry_type"),
    )

    @property
    def signed_amount(self) -> float:
        return float(self.amount) * (-1 if self.entry_type == PaymentEntryType.REFUND else 1)

    @property
    def is_refund(self) -> bool:
        return self.entry_type == PaymentEntryType.REFUND

    @property
    def is_refundable(self) -> bool:
        return (
            self.entry_type == PaymentEntryType.PAYMENT
            and self.status == PaymentStatus.PAID
            and self.voided_at is None
        )


class Invoice(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Tax invoice / pro-forma.  Financial documents are never hard deleted -
    they are voided, preserving the audit trail."""

    __tablename__ = "invoices"

    number: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    guest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("guests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[InvoiceStatus] = enum_column(
        InvoiceStatus, "invoice_status", nullable=False, default=InvoiceStatus.DRAFT, index=True
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date | None] = mapped_column(Date)

    guest_name: Mapped[str] = mapped_column(String(180), nullable=False)
    guest_email: Mapped[str | None] = mapped_column(String(255))
    guest_address: Mapped[str | None] = mapped_column(Text)
    guest_tax_id: Mapped[str | None] = mapped_column(String(64))

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    paid_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    is_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    notes: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    void_reason: Mapped[str | None] = mapped_column(Text)

    reservation: Mapped["Reservation"] = relationship(back_populates="invoices")
    guest: Mapped["Guest"] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.sort_order"
    )
    payments: Mapped[list[Payment]] = relationship(back_populates="invoice")

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="invoice_total_non_negative"),
        Index("ix_invoices_issue_status", "issue_date", "status"),
    )

    @property
    def is_editable(self) -> bool:
        return self.status in (InvoiceStatus.DRAFT,)


class InvoiceItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    charge_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservation_charges.id", ondelete="SET NULL")
    )
    charge_type: Mapped[ChargeType] = enum_column(
        ChargeType, "invoice_item_charge_type", nullable=False, default=ChargeType.OTHER
    )
    description: Mapped[str] = mapped_column(String(180), nullable=False)
    service_date: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="items")
