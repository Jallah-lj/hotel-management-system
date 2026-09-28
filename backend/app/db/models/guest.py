"""Guest profiles (CRM)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.db.enums import Gender, IdDocumentType

if TYPE_CHECKING:
    from app.db.models.reservation import Reservation


class Guest(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "guests"

    reference: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)

    first_name: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    last_name: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    alternate_phone: Mapped[str | None] = mapped_column(String(32))
    gender: Mapped[Gender] = enum_column(Gender, "gender", nullable=False, default=Gender.UNDISCLOSED)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(64))

    address_line1: Mapped[str | None] = mapped_column(String(180))
    address_line2: Mapped[str | None] = mapped_column(String(180))
    city: Mapped[str | None] = mapped_column(String(96))
    state: Mapped[str | None] = mapped_column(String(96))
    postal_code: Mapped[str | None] = mapped_column(String(24))
    country: Mapped[str | None] = mapped_column(String(64))

    id_document_type: Mapped[IdDocumentType | None] = enum_column(IdDocumentType, "id_document_type")
    id_document_number: Mapped[str | None] = mapped_column(String(64))
    id_document_expiry: Mapped[date | None] = mapped_column(Date)
    id_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    emergency_contact_name: Mapped[str | None] = mapped_column(String(120))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(32))
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(48))

    company_name: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    preferences: Mapped[str | None] = mapped_column(Text)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blacklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blacklist_reason: Mapped[str | None] = mapped_column(Text)

    # Denormalised loyalty metrics - maintained by the reservations service.
    total_stays: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_nights: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_spend: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    outstanding_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    last_stay_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_vip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="guest", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("total_stays >= 0 AND total_nights >= 0", name="guest_counters_non_negative"),
        Index("ix_guests_name", "last_name", "first_name"),
        Index("ix_guests_deleted", "deleted_at"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
