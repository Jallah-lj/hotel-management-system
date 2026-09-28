"""Operational models: services, F&B, housekeeping, maintenance, expenses,
inventory, notifications, audit trail and hotel settings."""

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
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.db.enums import (
    ExpenseCategory,
    HousekeepingCondition,
    HousekeepingTaskStatus,
    HousekeepingTaskType,
    MaintenanceCategory,
    MaintenanceStatus,
    NotificationCategory,
    NotificationSeverity,
    OrderStatus,
    OrderType,
    Priority,
    ServiceAvailability,
)

if TYPE_CHECKING:
    from app.db.models.guest import Guest
    from app.db.models.property import Room
    from app.db.models.reservation import Reservation
    from app.db.models.user import User

JSONType = JSON().with_variant(JSONB, "postgresql")


# ---------------------------------------------------------------------------
# Hotel services
# ---------------------------------------------------------------------------
class Service(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "services"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(48), nullable=False, default="general", index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    unit: Mapped[str] = mapped_column(String(24), nullable=False, default="per service")
    availability: Mapped[ServiceAvailability] = enum_column(
        ServiceAvailability, "service_availability", nullable=False, default=ServiceAvailability.ALWAYS
    )
    available_from: Mapped[str | None] = mapped_column(String(5))
    available_to: Mapped[str | None] = mapped_column(String(5))
    requires_scheduling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_taxable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    image_url: Mapped[str | None] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("price >= 0", name="service_price_non_negative"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="service_tax_rate_range"),
    )

    @property
    def price_with_tax(self) -> float:
        return round(float(self.price) * (1 + float(self.tax_rate) / 100), 2)


# ---------------------------------------------------------------------------
# Restaurant / room service
# ---------------------------------------------------------------------------
class MenuCategory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "menu_categories"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    kitchen_station: Mapped[str | None] = mapped_column(String(48))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    items: Mapped[list["MenuItem"]] = relationship(back_populates="category", cascade="all, delete-orphan")


class MenuItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "menu_items"

    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(String(32), unique=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=10)
    prep_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_vegan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_gluten_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spice_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allergens: Mapped[list | None] = mapped_column(JSONType)
    image_url: Mapped[str | None] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped[MenuCategory] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("price >= 0", name="menu_item_price_non_negative"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="menu_item_tax_rate_range"),
        CheckConstraint("spice_level >= 0 AND spice_level <= 3", name="menu_item_spice_level_range"),
    )


class ServiceOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A posted service or restaurant order, optionally billed to a folio."""

    __tablename__ = "service_orders"

    order_number: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    order_type: Mapped[OrderType] = enum_column(
        OrderType, "order_type", nullable=False, default=OrderType.ROOM_SERVICE, index=True
    )
    status: Mapped[OrderStatus] = enum_column(
        OrderStatus, "order_status", nullable=False, default=OrderStatus.PENDING, index=True
    )

    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="SET NULL"), index=True
    )
    guest_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("guests.id", ondelete="SET NULL"))
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))

    table_reference: Mapped[str | None] = mapped_column(String(24))
    is_room_service: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_billed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    service_charge: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    placed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    reservation: Mapped["Reservation | None"] = relationship(back_populates="orders")
    guest: Mapped["Guest | None"] = relationship()
    room: Mapped["Room | None"] = relationship()
    placed_by: Mapped["User | None"] = relationship()
    items: Mapped[list["ServiceOrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="ServiceOrderItem.created_at"
    )

    __table_args__ = (
        CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total_amount >= 0", name="order_totals_non_negative"),
        Index("ix_service_orders_status_placed", "status", "placed_at"),
    )


class ServiceOrderItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("service_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"))
    menu_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("menu_items.id", ondelete="SET NULL")
    )
    name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    order: Mapped[ServiceOrder] = relationship(back_populates="items")
    service: Mapped[Service | None] = relationship()
    menu_item: Mapped[MenuItem | None] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="order_item_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="order_item_price_non_negative"),
        CheckConstraint(
            "service_id IS NOT NULL OR menu_item_id IS NOT NULL", name="order_item_has_source"
        ),
    )


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------
class HousekeepingTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "housekeeping_tasks"

    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id", ondelete="SET NULL")
    )
    task_type: Mapped[HousekeepingTaskType] = enum_column(
        HousekeepingTaskType, "housekeeping_task_type", nullable=False, default=HousekeepingTaskType.STAYOVER_CLEAN
    )
    status: Mapped[HousekeepingTaskStatus] = enum_column(
        HousekeepingTaskStatus, "housekeeping_task_status", nullable=False, default=HousekeepingTaskStatus.PENDING, index=True
    )
    priority: Mapped[Priority] = enum_column(Priority, "housekeeping_priority", nullable=False, default=Priority.MEDIUM)

    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    inspected_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scheduled_time: Mapped[str | None] = mapped_column(String(5))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)
    completion_notes: Mapped[str | None] = mapped_column(Text)
    maintenance_reported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    damage_reported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    room: Mapped["Room"] = relationship(lazy="joined")
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id], lazy="joined")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    reservation: Mapped["Reservation | None"] = relationship()

    __table_args__ = (
        Index("ix_housekeeping_status_date", "status", "scheduled_date"),
        Index("ix_housekeeping_assignee_status", "assigned_to_id", "status"),
    )


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
class MaintenanceTicket(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "maintenance_tickets"

    ticket_number: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"), index=True
    )
    location: Mapped[str | None] = mapped_column(String(96))

    category: Mapped[MaintenanceCategory] = enum_column(
        MaintenanceCategory, "maintenance_category", nullable=False, default=MaintenanceCategory.OTHER, index=True
    )
    priority: Mapped[Priority] = enum_column(Priority, "maintenance_priority", nullable=False, default=Priority.MEDIUM, index=True)
    status: Mapped[MaintenanceStatus] = enum_column(
        MaintenanceStatus, "maintenance_status", nullable=False, default=MaintenanceStatus.OPEN, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    reported_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("housekeeping_tasks.id", ondelete="SET NULL")
    )

    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    blocks_room: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    photo_urls: Mapped[list | None] = mapped_column(JSONType)

    room: Mapped["Room | None"] = relationship(lazy="joined")
    reported_by: Mapped["User | None"] = relationship(foreign_keys=[reported_by_id], lazy="joined")
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("cost >= 0", name="maintenance_cost_non_negative"),
        Index("ix_maintenance_status_priority", "status", "priority"),
    )


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------
class Expense(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "expenses"

    expense_number: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    category: Mapped[ExpenseCategory] = enum_column(
        ExpenseCategory, "expense_category", nullable=False, default=ExpenseCategory.OTHER, index=True
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_methods.id", ondelete="SET NULL")
    )
    payment_method_label: Mapped[str | None] = mapped_column(String(64))
    vendor: Mapped[str | None] = mapped_column(String(120))
    reference: Mapped[str | None] = mapped_column(String(96))
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attachment_name: Mapped[str | None] = mapped_column(String(180))
    attachment_path: Mapped[str | None] = mapped_column(String(400))
    attachment_mime: Mapped[str | None] = mapped_column(String(96))
    notes: Mapped[str | None] = mapped_column(Text)

    recorded_by: Mapped["User | None"] = relationship(foreign_keys=[recorded_by_id], lazy="joined")
    payment_method: Mapped["PaymentMethod | None"] = relationship()

    __table_args__ = (
        CheckConstraint("amount > 0", name="expense_amount_positive"),
        CheckConstraint("tax_amount >= 0", name="expense_tax_non_negative"),
        Index("ix_expenses_date_category", "expense_date", "category"),
    )


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
class InventoryItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "inventory_items"

    sku: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False, default="housekeeping")
    unit: Mapped[str] = mapped_column(String(24), nullable=False, default="unit")
    quantity_on_hand: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    reorder_level: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    supplier: Mapped[str | None] = mapped_column(String(120))
    storage_location: Mapped[str | None] = mapped_column(String(96))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    movements: Mapped[list["InventoryMovement"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("quantity_on_hand >= 0", name="inventory_quantity_non_negative"),
        CheckConstraint("reorder_level >= 0", name="inventory_reorder_non_negative"),
        CheckConstraint("unit_cost >= 0", name="inventory_cost_non_negative"),
    )

    @property
    def is_below_reorder_level(self) -> bool:
        return float(self.quantity_on_hand) <= float(self.reorder_level)


class InventoryMovement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "inventory_movements"

    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delta: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    resulting_quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(48), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(96))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    item: Mapped[InventoryItem] = relationship(back_populates="movements")
    created_by: Mapped["User | None"] = relationship()

    __table_args__ = (CheckConstraint("resulting_quantity >= 0", name="inventory_result_non_negative"),)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[NotificationCategory] = enum_column(
        NotificationCategory, "notification_category", nullable=False, default=NotificationCategory.SYSTEM
    )
    severity: Mapped[NotificationSeverity] = enum_column(
        NotificationSeverity, "notification_severity", nullable=False, default=NotificationSeverity.INFO
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(255))
    entity_type: Mapped[str | None] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(48))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str | None] = mapped_column(String(120), index=True)

    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),)


# ---------------------------------------------------------------------------
# Audit log (append only)
# ---------------------------------------------------------------------------
class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable record of security-relevant and data-changing actions.

    The API exposes read-only access; no update/delete endpoints exist and the
    service layer never mutates rows once written.
    """

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(96))
    user_role: Mapped[str | None] = mapped_column(String(96))
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    method: Mapped[str | None] = mapped_column(String(10))
    path: Mapped[str | None] = mapped_column(String(255))
    status_code: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ip_address: Mapped[str | None] = mapped_column(String(64), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)

    before_data: Mapped[dict | None] = mapped_column(JSONType)
    after_data: Mapped[dict | None] = mapped_column(JSONType)
    extra_data: Mapped[dict | None] = mapped_column(JSONType)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    user: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_audit_resource_created", "resource", "created_at"),
        Index("ix_audit_user_created", "user_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Hotel settings (key/value configuration)
# ---------------------------------------------------------------------------
class HotelSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "hotel_settings"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False, default="string")
    group_name: Mapped[str] = mapped_column(String(48), nullable=False, default="general")
    label: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    updated_by: Mapped["User | None"] = relationship()

    @property
    def typed_value(self):
        if self.value is None:
            return None
        if self.value_type == "int":
            return int(self.value)
        if self.value_type == "float":
            return float(self.value)
        if self.value_type == "bool":
            return str(self.value).lower() in {"1", "true", "yes", "on"}
        if self.value_type == "json":
            import json

            return json.loads(self.value)
        return self.value


# Re-exported for convenience in services that need condition enums.
__all__ = [
    "Service",
    "MenuCategory",
    "MenuItem",
    "ServiceOrder",
    "ServiceOrderItem",
    "HousekeepingTask",
    "MaintenanceTicket",
    "Expense",
    "InventoryItem",
    "InventoryMovement",
    "Notification",
    "AuditLog",
    "HotelSetting",
    "HousekeepingCondition",
]
