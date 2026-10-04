"""Seed a realistic development property.

Run with::

    DATABASE_URL=postgresql+psycopg://... python -m scripts.seed

The command is idempotent for the built-in catalogue and administrator.  The
sample operational records are only inserted when the database has no rooms.
Development credentials are documented in README.md and must be replaced
before any deployment.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta, UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.permissions import PERMISSIONS, ROLE_DEFINITIONS
from app.core.security import hash_password
from app.db.base import Base
from app.db.enums import BedType, BookingSource, Gender, HousekeepingTaskStatus, HousekeepingTaskType, MaintenanceCategory, MaintenanceStatus, PaymentMethodType, Priority, RoomStatus, ServiceAvailability
from app.db.models import *
from app.db.session import engine, session_scope
from app.schemas.domain import ReservationCreate
from app.services.reservations import ReservationService


HOTEL_SETTINGS = [
    ("hotel_name", "Aurora Grand Hotel", "string", "hotel", "Hotel name", True),
    ("hotel_tagline", "Thoughtful stays, beautifully handled.", "string", "hotel", "Tagline", True),
    ("hotel_phone", "+1 555 014 2040", "string", "hotel", "Primary telephone", True),
    ("hotel_email", "stay@auroragrand.example", "string", "hotel", "Reservations email", True),
    ("hotel_address", "18 Meridian Avenue, Harbor District", "string", "hotel", "Address", True),
    ("check_in_time", "15:00", "string", "operations", "Check-in time", True),
    ("check_out_time", "11:00", "string", "operations", "Check-out time", True),
    ("default_tax_rate", "10", "float", "finance", "Default tax rate", False),
    ("currency", "USD", "string", "finance", "Default currency", True),
]


def main() -> None:
    Base.metadata.create_all(engine)
    with session_scope() as db:
        # Permissions and roles are upserted by stable code.
        permission_by_code = {}
        for spec in PERMISSIONS:
            row = db.scalar(select(Permission).where(Permission.code == spec.code))
            if not row:
                row = Permission(code=spec.code, resource=spec.resource, action=spec.action, group_name=spec.group, description=spec.description, is_system=True)
                db.add(row)
            permission_by_code[spec.code] = row
        db.flush()
        role_by_code = {}
        for code, definition in ROLE_DEFINITIONS.items():
            row = db.scalar(select(Role).where(Role.code == code))
            if not row:
                row = Role(code=code, name=definition["name"], description=definition["description"], level=definition["level"], is_system=definition["is_system"])
                db.add(row)
            row.permissions = [permission_by_code[p] for p in sorted(definition["permissions"])]
            role_by_code[code] = row
        db.flush()

        for key, value, value_type, group, label, is_public in HOTEL_SETTINGS:
            if not db.scalar(select(HotelSetting).where(HotelSetting.key == key)):
                db.add(HotelSetting(key=key, value=value, value_type=value_type, group_name=group, label=label, is_public=is_public))
        for code, label, kind, reference in [("cash", "Cash", PaymentMethodType.CASH, False), ("card", "Card", PaymentMethodType.CARD, True), ("bank_transfer", "Bank transfer", PaymentMethodType.BANK_TRANSFER, True), ("mobile_money", "Mobile money", PaymentMethodType.MOBILE_MONEY, True), ("other", "Other", PaymentMethodType.OTHER, False)]:
            if not db.scalar(select(PaymentMethod).where(PaymentMethod.code == code)):
                db.add(PaymentMethod(code=code, name=label, type=kind, requires_reference=reference, is_active=True))
        db.flush()

        admin = db.scalar(select(User).where(User.email == "admin@auroragrand.example"))
        if not admin:
            admin = User(email="admin@auroragrand.example", username="admin", first_name="Avery", last_name="Morgan", password_hash=hash_password("AuroraAdmin!2026"), job_title="General Manager", department="Executive", is_superuser=True, must_change_password=False, roles=[role_by_code["super_admin"]])
            db.add(admin)
        manager = db.scalar(select(User).where(User.email == "manager@auroragrand.example"))
        if not manager:
            manager = User(email="manager@auroragrand.example", username="manager", first_name="Maya", last_name="Chen", password_hash=hash_password("AuroraManager!2026"), job_title="Hotel Manager", department="Operations", roles=[role_by_code["hotel_manager"]])
            db.add(manager)
        receptionist = db.scalar(select(User).where(User.email == "frontdesk@auroragrand.example"))
        if not receptionist:
            receptionist = User(email="frontdesk@auroragrand.example", username="frontdesk", first_name="Jordan", last_name="Lee", password_hash=hash_password("AuroraFrontdesk!2026"), job_title="Front Desk Lead", department="Front Office", roles=[role_by_code["receptionist"]])
            db.add(receptionist)
        accountant = db.scalar(select(User).where(User.email == "finance@auroragrand.example"))
        if not accountant:
            accountant = User(email="finance@auroragrand.example", username="finance", first_name="Noah", last_name="Williams", password_hash=hash_password("AuroraFinance!2026"), job_title="Financial Controller", department="Finance", roles=[role_by_code["accountant"]])
            db.add(accountant)
        housekeeper = db.scalar(select(User).where(User.email == "housekeeping@auroragrand.example"))
        if not housekeeper:
            housekeeper = User(email="housekeeping@auroragrand.example", username="housekeeping", first_name="Sofia", last_name="Patel", password_hash=hash_password("AuroraHousekeeping!2026"), job_title="Housekeeping Supervisor", department="Rooms", roles=[role_by_code["housekeeping"]])
            db.add(housekeeper)
        db.flush()

        from app.services.common import notify
        notify(db, user_id=admin.id, title="Arrivals today", message="An arrival is due today; review the front desk queue.", category="reservation", link="/reservations", dedupe_key="seed-arrivals")
        notify(db, user_id=admin.id, title="Maintenance ticket open", message="A priority ticket is open in engineering and may block a room.", category="maintenance", severity="warning", link="/maintenance", dedupe_key="seed-maintenance")
        notify(db, user_id=admin.id, title="Housekeeping queue", message="Rooms are waiting on housekeeping attention before the next arrival.", category="housekeeping", link="/housekeeping", dedupe_key="seed-housekeeping")
        db.flush()

        if db.scalar(select(Room.id).limit(1)):
            print("Aurora Grand catalogue and accounts already exist; no sample property records added.")
            return

        amenity_specs = [("wifi", "High-speed Wi-Fi", "connectivity"), ("breakfast", "Breakfast included", "dining"), ("workspace", "Dedicated workspace", "comfort"), ("city_view", "City view", "view"), ("rain_shower", "Rain shower", "bathroom"), ("bathtub", "Deep soaking tub", "bathroom"), ("balcony", "Private balcony", "comfort"), ("minibar", "Curated minibar", "dining")]
        amenities = []
        for code, name, category in amenity_specs:
            row = Amenity(code=code, name=name, category=category, is_active=True); db.add(row); amenities.append(row)
        db.flush()
        types = []
        for code, name, price, max_occ, bed, size, amenity_codes in [
            ("STD", "Classic King", 185, 2, BedType.KING, 28, ["wifi", "workspace", "rain_shower"]),
            ("DLX", "Deluxe City View", 245, 2, BedType.KING, 34, ["wifi", "workspace", "city_view", "minibar"]),
            ("EXE", "Executive Corner", 310, 3, BedType.KING, 46, ["wifi", "workspace", "city_view", "breakfast", "rain_shower"]),
            ("STE", "Meridian Suite", 495, 4, BedType.KING, 72, ["wifi", "workspace", "city_view", "breakfast", "bathtub", "minibar"]),
            ("FAM", "Family Residence", 385, 5, BedType.TWIN, 60, ["wifi", "breakfast", "workspace", "minibar"]),
        ]:
            row = RoomType(code=code, name=name, description=f"A considered {name.lower()} designed for unhurried stays.", base_price=price, weekend_price=price * 1.12, max_occupancy=max_occ, max_adults=min(max_occ, 3), max_children=max(0, max_occ - 2), bed_type=bed, bed_count=1, size_sqm=size, tax_rate=10, is_active=True, sort_order=len(types)); row.amenities = [a for a in amenities if a.code in amenity_codes]; db.add(row); types.append(row)
        db.flush()
        rooms = []
        room_num = 101
        for type_index, room_type in enumerate(types):
            count = 6 if type_index == 0 else 4
            for _ in range(count):
                floor = int(str(room_num)[0])
                rooms.append(Room(number=str(room_num), name=room_type.name, room_type_id=room_type.id, floor=floor, capacity=room_type.max_occupancy, bed_type=room_type.bed_type, bed_count=room_type.bed_count, price_per_night=room_type.base_price, status=RoomStatus.AVAILABLE, description=room_type.description, images=[], view="Harbor" if floor >= 3 else "Courtyard", is_accessible=(room_num % 10 == 1), is_active=True)); room_num += 1
        db.add_all(rooms); db.flush()
        services = [Service(code="laundry", name="Express laundry", category="wellness", price=28, tax_rate=10, unit="per bag", availability=ServiceAvailability.ALWAYS), Service(code="airport_transfer", name="Airport transfer", category="transport", price=65, tax_rate=10, unit="per transfer", availability=ServiceAvailability.ALWAYS), Service(code="spa_massage", name="Signature massage", category="wellness", price=120, tax_rate=10, unit="60 minutes", availability=ServiceAvailability.SCHEDULED, requires_scheduling=True, duration_minutes=60), Service(code="breakfast", name="Breakfast", category="dining", price=24, tax_rate=10, unit="per guest", availability=ServiceAvailability.ALWAYS)]
        db.add_all(services); db.flush()
        menu_category = MenuCategory(name="All-day dining", description="Seasonal plates from the Meridian kitchen", kitchen_station="main kitchen"); db.add(menu_category); db.flush()
        db.add_all([MenuItem(category_id=menu_category.id, name="Herb-roasted chicken", description="Pan jus, charred lemon, garden greens", price=32, tax_rate=10, prep_minutes=25, is_available=True), MenuItem(category_id=menu_category.id, name="Seasonal grain bowl", description="Roasted vegetables, tahini, herbs", price=24, tax_rate=10, prep_minutes=15, is_available=True)])
        db.flush()
        guest_specs = [("Elena", "Rossi", "elena.rossi@example.com", "+1 555 100 2001", "Italy", True), ("Marcus", "Reed", "marcus.reed@example.com", "+1 555 100 2002", "United States", False), ("Priya", "Nair", "priya.nair@example.com", "+1 555 100 2003", "India", False), ("Daniel", "Okafor", "daniel.okafor@example.com", "+1 555 100 2004", "Nigeria", False), ("Hana", "Sato", "hana.sato@example.com", "+1 555 100 2005", "Japan", True)]
        guests = []
        for idx, (first, last, email, phone, nation, vip) in enumerate(guest_specs):
            guest = Guest(reference=f"GST-DEMO{idx+1:02d}", first_name=first, last_name=last, email=email, phone=phone, nationality=nation, gender=Gender.UNDISCLOSED, is_vip=vip); db.add(guest); guests.append(guest)
        db.flush()
        # Create a mix of future arrivals, in-house stay and completed stay.
        today = date.today()
        for idx, guest in enumerate(guests):
            start = today + timedelta(days=idx - 1)
            end = start + timedelta(days=2 + idx % 3)
            if end <= start: end = start + timedelta(days=2)
            service = ReservationService(db, manager)
            try:
                reservation = service.create(ReservationCreate(guest_id=guest.id, room_type_id=types[idx % len(types)].id, room_id=next(r.id for r in rooms if r.room_type_id == types[idx % len(types)].id), check_in_date=start, check_out_date=end, adults=1 + idx % 2, children=0, booking_source=BookingSource.WEBSITE if idx % 2 else BookingSource.WALK_IN, special_requests="Late arrival" if idx == 1 else None))
                if idx == 0:
                    # Pre-seed one in-house stay for the dashboard.
                    reservation.status = "checked_in"; rooms[idx].status = RoomStatus.OCCUPIED
                db.flush()
            except Exception as exc:
                print(f"Skipped demo reservation {idx}: {exc}")
        db.flush()
        for idx, room in enumerate(rooms[:8]):
            db.add(HousekeepingTask(room_id=room.id, task_type=HousekeepingTaskType.CHECKOUT_CLEAN, status=HousekeepingTaskStatus.PENDING if idx % 2 else HousekeepingTaskStatus.IN_PROGRESS, priority=Priority.HIGH if idx < 2 else Priority.MEDIUM, assigned_to_id=housekeeper.id, created_by_id=manager.id, scheduled_date=today, notes="Guest departure turnaround"))
        db.add(MaintenanceTicket(ticket_number="MNT-DEMO01", room_id=rooms[8].id, category=MaintenanceCategory.AIR_CONDITIONING, priority=Priority.MEDIUM, status=MaintenanceStatus.OPEN, title="Air conditioning is noisy", description="Guest reported intermittent vibration from the wall unit.", reported_by_id=manager.id, reported_at=datetime.now(UTC), blocks_room=False))
        print("Seeded Aurora Grand Hotel: 20 rooms, 5 guests, 5 staff accounts, services, reservations and operations.")


if __name__ == "__main__":
    main()
