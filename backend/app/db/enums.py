"""Domain enumerations shared by models, schemas and services."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


# ---------------------------------------------------------------------------
# People & access
# ---------------------------------------------------------------------------
class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------
class RoomStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    OCCUPIED = "occupied"
    CLEANING = "cleaning"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"


class HousekeepingCondition(StrEnum):
    CLEAN = "clean"
    DIRTY = "dirty"
    CLEANING = "cleaning"
    INSPECTED = "inspected"


class BedType(StrEnum):
    SINGLE = "single"
    DOUBLE = "double"
    QUEEN = "queen"
    KING = "king"
    TWIN = "twin"
    SOFA_BED = "sofa_bed"
    BUNK = "bunk"


class MaintenanceFlag(StrEnum):
    OPERATIONAL = "operational"
    NEEDS_ATTENTION = "needs_attention"
    UNDER_MAINTENANCE = "under_maintenance"
    OUT_OF_ORDER = "out_of_order"


# ---------------------------------------------------------------------------
# Guests
# ---------------------------------------------------------------------------
class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNDISCLOSED = "undisclosed"


class IdDocumentType(StrEnum):
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    DRIVERS_LICENSE = "drivers_license"
    RESIDENCE_PERMIT = "residence_permit"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------
class ReservationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


ACTIVE_RESERVATION_STATUSES = (
    ReservationStatus.PENDING,
    ReservationStatus.CONFIRMED,
    ReservationStatus.CHECKED_IN,
)

IN_HOUSE_STATUSES = (ReservationStatus.CHECKED_IN,)


class BookingSource(StrEnum):
    WALK_IN = "walk_in"
    PHONE = "phone"
    EMAIL = "email"
    WEBSITE = "website"
    OTA = "ota"
    CORPORATE = "corporate"
    TRAVEL_AGENT = "travel_agent"
    REFERRAL = "referral"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    REFUNDED = "refunded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentMethodType(StrEnum):
    CASH = "cash"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    MOBILE_MONEY = "mobile_money"
    OTHER = "other"


class PaymentEntryType(StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"


class ChargeType(StrEnum):
    ROOM = "room"
    SERVICE = "service"
    RESTAURANT = "restaurant"
    LAUNDRY = "laundry"
    MINIBAR = "minibar"
    DAMAGE = "damage"
    DISCOUNT = "discount"
    ADJUSTMENT = "adjustment"
    OTHER = "other"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    VOID = "void"
    OVERDUE = "overdue"


class FolioStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    SETTLED = "settled"


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
class HousekeepingTaskType(StrEnum):
    CHECKOUT_CLEAN = "checkout_clean"
    STAYOVER_CLEAN = "stayover_clean"
    DEEP_CLEAN = "deep_clean"
    INSPECTION = "inspection"
    TURNDOWN = "turndown"
    PUBLIC_AREA = "public_area"


class HousekeepingTaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INSPECTED = "inspected"
    CANCELLED = "cancelled"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MaintenanceCategory(StrEnum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    FURNITURE = "furniture"
    AIR_CONDITIONING = "air_conditioning"
    INTERNET = "internet"
    APPLIANCE = "appliance"
    SAFETY = "safety"
    OTHER = "other"


class MaintenanceStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class OrderType(StrEnum):
    ROOM_SERVICE = "room_service"
    RESTAURANT = "restaurant"
    SERVICE = "service"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ServiceAvailability(StrEnum):
    ALWAYS = "always"
    SCHEDULED = "scheduled"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    ON_REQUEST = "on_request"


class ExpenseCategory(StrEnum):
    UTILITIES = "utilities"
    SALARIES = "salaries"
    MAINTENANCE = "maintenance"
    SUPPLIES = "supplies"
    FOOD_BEVERAGE = "food_beverage"
    TRANSPORTATION = "transportation"
    MARKETING = "marketing"
    TAXES = "taxes"
    OTHER = "other"


class NotificationCategory(StrEnum):
    RESERVATION = "reservation"
    PAYMENT = "payment"
    HOUSEKEEPING = "housekeeping"
    MAINTENANCE = "maintenance"
    INVENTORY = "inventory"
    SYSTEM = "system"


class NotificationSeverity(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditAction(StrEnum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    CANCEL = "cancel"
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    PAYMENT = "payment"
    REFUND = "refund"
    PERMISSION_CHANGE = "permission_change"
    SETTINGS_CHANGE = "settings_change"
    PASSWORD_RESET = "password_reset"
    EXPORT = "export"
    VIEW = "view"
