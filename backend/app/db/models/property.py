"""Rooms, room types, amenities and availability related structures."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.db.enums import BedType, HousekeepingCondition, MaintenanceFlag, RoomStatus

if TYPE_CHECKING:
    from app.db.models.reservation import Reservation

JSONType = JSON().with_variant(JSONB, "postgresql")

room_type_amenities = Table(
    "room_type_amenities",
    Base.metadata,
    Column("room_type_id", Uuid(as_uuid=True), ForeignKey("room_types.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", Uuid(as_uuid=True), ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)

room_amenities = Table(
    "room_amenity_links",
    Base.metadata,
    Column("room_id", Uuid(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
    Column("amenity_id", Uuid(as_uuid=True), ForeignKey("amenities.id", ondelete="CASCADE"), primary_key=True),
)


class Amenity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "amenities"

    code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(48))
    category: Mapped[str] = mapped_column(String(48), nullable=False, default="general")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    room_types: Mapped[list["RoomType"]] = relationship(
        secondary=room_type_amenities, back_populates="amenities"
    )
    rooms: Mapped[list["Room"]] = relationship(secondary=room_amenities, back_populates="amenities")


class RoomType(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "room_types"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    base_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    weekend_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    extra_person_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    max_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_adults: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_children: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bed_type: Mapped[BedType] = enum_column(BedType, "bed_type", nullable=False, default=BedType.QUEEN)
    bed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    size_sqm: Mapped[int | None] = mapped_column(Integer)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    hero_image_url: Mapped[str | None] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    amenities: Mapped[list[Amenity]] = relationship(
        secondary=room_type_amenities, lazy="selectin", back_populates="room_types"
    )
    rooms: Mapped[list["Room"]] = relationship(back_populates="room_type")

    __table_args__ = (
        CheckConstraint("base_price >= 0", name="room_type_base_price_non_negative"),
        CheckConstraint("max_occupancy > 0", name="room_type_occupancy_positive"),
        CheckConstraint("max_adults > 0 AND max_children >= 0", name="room_type_guest_limits"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="room_type_tax_rate_range"),
    )


class Room(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "rooms"

    number: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(96))
    room_type_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("room_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    floor: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    building: Mapped[str | None] = mapped_column(String(48))
    wing: Mapped[str | None] = mapped_column(String(48))
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    bed_type: Mapped[BedType] = enum_column(BedType, "room_bed_type", nullable=False, default=BedType.QUEEN)
    bed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    price_per_night: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[RoomStatus] = enum_column(RoomStatus, "room_status", nullable=False, default=RoomStatus.AVAILABLE, index=True)
    housekeeping_condition: Mapped[HousekeepingCondition] = enum_column(
        HousekeepingCondition, "housekeeping_condition", nullable=False, default=HousekeepingCondition.CLEAN
    )
    maintenance_flag: Mapped[MaintenanceFlag] = enum_column(
        MaintenanceFlag, "maintenance_flag", nullable=False, default=MaintenanceFlag.OPERATIONAL
    )
    description: Mapped[str | None] = mapped_column(Text)
    images: Mapped[list | None] = mapped_column(JSONType)
    view: Mapped[str | None] = mapped_column(String(48))
    is_smoking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_accessible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    room_type: Mapped[RoomType] = relationship(back_populates="rooms", lazy="joined")
    amenities: Mapped[list[Amenity]] = relationship(
        secondary=room_amenities, lazy="selectin", back_populates="rooms"
    )
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="room")

    __table_args__ = (
        CheckConstraint("capacity > 0", name="room_capacity_positive"),
        CheckConstraint("price_per_night >= 0", name="room_price_non_negative"),
        CheckConstraint("floor >= 0", name="room_floor_non_negative"),
        Index("ix_rooms_status_floor", "status", "floor"),
        Index("ix_rooms_type_active", "room_type_id", "is_active"),
    )

    @property
    def is_bookable(self) -> bool:
        return (
            self.is_active
            and self.deleted_at is None
            and self.maintenance_flag in (MaintenanceFlag.OPERATIONAL, MaintenanceFlag.NEEDS_ATTENTION)
            and self.status not in (RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE)
        )
