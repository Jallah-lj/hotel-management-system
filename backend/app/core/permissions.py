"""The permission catalogue and the shipped role definitions.

Permissions are ``resource:action`` strings.  The catalogue below is the single
source of truth: the seed script upserts it into the ``permissions`` table and
the built-in roles receive a default set.  Super administrators can create
additional roles and pick any subset of these permissions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionSpec:
    code: str
    resource: str
    action: str
    group: str
    description: str


def _p(resource: str, action: str, group: str, description: str) -> PermissionSpec:
    return PermissionSpec(f"{resource}:{action}", resource, action, group, description)


PERMISSIONS: tuple[PermissionSpec, ...] = (
    # Dashboard -----------------------------------------------------------------
    _p("dashboard", "view", "Dashboard", "Access the operational dashboard"),
    # Users / roles -------------------------------------------------------------
    _p("users", "view", "Administration", "View staff accounts"),
    _p("users", "create", "Administration", "Create staff accounts"),
    _p("users", "update", "Administration", "Edit staff accounts and roles"),
    _p("users", "delete", "Administration", "Deactivate or delete staff accounts"),
    _p("users", "reset_password", "Administration", "Force a password reset for a staff account"),
    _p("roles", "view", "Administration", "View roles and their permissions"),
    _p("roles", "manage", "Administration", "Create roles and change permission assignments"),
    # Hotel configuration -------------------------------------------------------
    _p("settings", "view", "Administration", "View hotel configuration"),
    _p("settings", "manage", "Administration", "Change hotel configuration"),
    _p("payment_methods", "manage", "Administration", "Configure accepted payment methods"),
    # Rooms & room types --------------------------------------------------------
    _p("rooms", "view", "Rooms", "View rooms and room types"),
    _p("rooms", "create", "Rooms", "Create rooms"),
    _p("rooms", "update", "Rooms", "Edit rooms, status and maintenance flags"),
    _p("rooms", "delete", "Rooms", "Deactivate or delete rooms"),
    _p("room_types", "manage", "Rooms", "Create and edit room types"),
    _p("amenities", "manage", "Rooms", "Maintain the amenities catalogue"),
    _p("rooms", "view_calendar", "Rooms", "Use the availability calendar"),
    # Guests --------------------------------------------------------------------
    _p("guests", "view", "Guests", "View guest profiles and history"),
    _p("guests", "create", "Guests", "Register new guests"),
    _p("guests", "update", "Guests", "Edit guest profiles"),
    _p("guests", "delete", "Guests", "Archive guest profiles"),
    # Reservations --------------------------------------------------------------
    _p("reservations", "view", "Reservations", "View reservations"),
    _p("reservations", "create", "Reservations", "Create reservations"),
    _p("reservations", "update", "Reservations", "Modify reservations"),
    _p("reservations", "cancel", "Reservations", "Cancel reservations"),
    _p("reservations", "check_in", "Reservations", "Check guests in"),
    _p("reservations", "check_out", "Reservations", "Check guests out"),
    _p("reservations", "override_balance", "Reservations", "Check out with an outstanding balance"),
    _p("reservations", "no_show", "Reservations", "Mark a reservation as a no-show"),
    _p("reservations", "view_folio", "Reservations", "View the guest folio (charges)"),
    # Payments & billing --------------------------------------------------------
    _p("payments", "view", "Finance", "View payments"),
    _p("payments", "create", "Finance", "Record payments"),
    _p("payments", "refund", "Finance", "Issue refunds"),
    _p("invoices", "view", "Finance", "View invoices and receipts"),
    _p("invoices", "create", "Finance", "Issue invoices"),
    _p("invoices", "void", "Finance", "Void an invoice"),
    _p("expenses", "view", "Finance", "View expenses"),
    _p("expenses", "create", "Finance", "Record expenses"),
    _p("expenses", "update", "Finance", "Edit or void expenses"),
    _p("reports", "view", "Reports", "View operational and financial reports"),
    _p("reports", "financial", "Reports", "View revenue, payment and expense reports"),
    _p("reports", "export", "Reports", "Export reports to PDF/CSV"),
    # Services & F&B ------------------------------------------------------------
    _p("services", "view", "Services", "View the hotel service catalogue"),
    _p("services", "manage", "Services", "Create and edit hotel services"),
    _p("orders", "view", "Services", "View service and restaurant orders"),
    _p("orders", "create", "Services", "Post service / room-service orders"),
    _p("orders", "update", "Services", "Advance order status"),
    _p("orders", "cancel", "Services", "Cancel orders"),
    _p("menu", "manage", "Services", "Manage restaurant menu categories and items"),
    # Housekeeping & maintenance ------------------------------------------------
    _p("housekeeping", "view", "Operations", "View the housekeeping board and tasks"),
    _p("housekeeping", "update_status", "Operations", "Start/finish cleaning and update room condition"),
    _p("housekeeping", "assign", "Operations", "Assign housekeeping tasks to staff"),
    _p("maintenance", "view", "Operations", "View maintenance tickets"),
    _p("maintenance", "create", "Operations", "Report maintenance issues"),
    _p("maintenance", "update", "Operations", "Assign, progress and resolve maintenance tickets"),
    _p("inventory", "view", "Operations", "View inventory levels"),
    _p("inventory", "manage", "Operations", "Adjust inventory levels and reorder points"),
    # Notifications & audit -----------------------------------------------------
    _p("notifications", "view", "System", "Read in-app notifications"),
    _p("audit_logs", "view", "System", "View the audit trail"),
    _p("audit_logs", "export", "System", "Export the audit trail"),
)

PERMISSION_CODES: frozenset[str] = frozenset(p.code for p in PERMISSIONS)

# ---------------------------------------------------------------------------
# Built-in roles
# ---------------------------------------------------------------------------
ROLE_SUPER_ADMIN = "super_admin"
ROLE_HOTEL_MANAGER = "hotel_manager"
ROLE_RECEPTIONIST = "receptionist"
ROLE_HOUSEKEEPING = "housekeeping"
ROLE_ACCOUNTANT = "accountant"
ROLE_STAFF = "staff"


def _all() -> set[str]:
    return set(PERMISSION_CODES)


ROLE_DEFINITIONS: dict[str, dict[str, object]] = {
    ROLE_SUPER_ADMIN: {
        "name": "Super Administrator",
        "description": "Full, unrestricted access to every module and system setting.",
        "level": 100,
        "is_system": True,
        "permissions": _all(),
    },
    ROLE_HOTEL_MANAGER: {
        "name": "Hotel Manager",
        "description": "Runs day-to-day hotel operations: reservations, rooms, guests, staff tasks and reporting.",
        "level": 80,
        "is_system": True,
        "permissions": {
            "dashboard:view",
            "rooms:view", "rooms:create", "rooms:update", "rooms:view_calendar",
            "room_types:manage", "amenities:manage",
            "guests:view", "guests:create", "guests:update",
            "reservations:view", "reservations:create", "reservations:update",
            "reservations:cancel", "reservations:check_in", "reservations:check_out",
            "reservations:override_balance", "reservations:no_show", "reservations:view_folio",
            "payments:view", "payments:create", "invoices:view", "invoices:create",
            "expenses:view", "expenses:create",
            "reports:view", "reports:export",
            "services:view", "services:manage",
            "orders:view", "orders:create", "orders:update", "orders:cancel", "menu:manage",
            "housekeeping:view", "housekeeping:assign", "housekeeping:update_status",
            "maintenance:view", "maintenance:create", "maintenance:update",
            "inventory:view", "inventory:manage",
            "notifications:view",
        },
    },
    ROLE_RECEPTIONIST: {
        "name": "Receptionist",
        "description": "Front desk: arrivals, departures, reservations, guests and payments.",
        "level": 50,
        "is_system": True,
        "permissions": {
            "dashboard:view",
            "rooms:view", "rooms:view_calendar",
            "guests:view", "guests:create", "guests:update",
            "reservations:view", "reservations:create", "reservations:update",
            "reservations:cancel", "reservations:check_in", "reservations:check_out",
            "reservations:view_folio", "reservations:no_show",
            "payments:view", "payments:create",
            "invoices:view", "invoices:create",
            "services:view",
            "orders:view", "orders:create", "orders:update",
            "housekeeping:view", "housekeeping:update_status",
            "maintenance:view", "maintenance:create",
            "notifications:view",
        },
    },
    ROLE_HOUSEKEEPING: {
        "name": "Housekeeping",
        "description": "Room attendants and supervisors: cleaning tasks, room condition and issue reporting.",
        "level": 30,
        "is_system": True,
        "permissions": {
            "dashboard:view",
            "rooms:view",
            "housekeeping:view", "housekeeping:update_status", "housekeeping:assign",
            "maintenance:view", "maintenance:create",
            "inventory:view",
            "notifications:view",
        },
    },
    ROLE_ACCOUNTANT: {
        "name": "Accountant",
        "description": "Finance: payments, invoices, expenses and financial reporting.",
        "level": 60,
        "is_system": True,
        "permissions": {
            "dashboard:view",
            "payments:view", "payments:create", "payments:refund",
            "invoices:view", "invoices:create", "invoices:void",
            "expenses:view", "expenses:create", "expenses:update",
            "reservations:view", "reservations:view_folio",
            "guests:view",
            "reports:view", "reports:financial", "reports:export",
            "audit_logs:view",
            "notifications:view",
        },
    },
    ROLE_STAFF: {
        "name": "Staff",
        "description": "General staff account - permissions are granted explicitly by an administrator.",
        "level": 20,
        "is_system": True,
        "permissions": {"dashboard:view", "notifications:view"},
    },
}
