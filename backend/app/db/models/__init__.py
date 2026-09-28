"""Import every model so ``Base.metadata`` is complete for Alembic and
``create_all`` in the test-suite."""

from app.db.base import Base
from app.db.models.billing import Invoice, InvoiceItem, Payment, PaymentMethod
from app.db.models.guest import Guest
from app.db.models.operations import (
    AuditLog,
    Expense,
    HotelSetting,
    HousekeepingTask,
    InventoryItem,
    InventoryMovement,
    MaintenanceTicket,
    MenuCategory,
    MenuItem,
    Notification,
    Service,
    ServiceOrder,
    ServiceOrderItem,
)
from app.db.models.property import Amenity, Room, RoomType, room_amenities, room_type_amenities
from app.db.models.reservation import CheckIn, CheckOut, Reservation, ReservationCharge, ReservationGuest
from app.db.models.user import (
    LoginAttempt,
    PasswordResetToken,
    Permission,
    RefreshToken,
    Role,
    User,
    role_permissions,
    user_roles,
)

__all__ = [
    "Base",
    # users & access
    "User",
    "Role",
    "Permission",
    "RefreshToken",
    "PasswordResetToken",
    "LoginAttempt",
    "user_roles",
    "role_permissions",
    # property
    "RoomType",
    "Room",
    "Amenity",
    "room_amenities",
    "room_type_amenities",
    # guests & reservations
    "Guest",
    "Reservation",
    "ReservationGuest",
    "ReservationCharge",
    "CheckIn",
    "CheckOut",
    # billing
    "Payment",
    "PaymentMethod",
    "Invoice",
    "InvoiceItem",
    # operations
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
]
