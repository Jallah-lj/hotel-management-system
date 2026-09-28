from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.errors import RoomNotAvailableError
from app.db.enums import BedType, Gender
from app.db.models import Guest, Reservation, Room, RoomType
from app.schemas.domain import ReservationCreate
from app.services.reservations import ReservationService


def setup_property(db):
    room_type = RoomType(code="TEST", name="Test Room", base_price=100, max_occupancy=2, max_adults=2, max_children=0, bed_type=BedType.QUEEN, tax_rate=10)
    room = Room(number="T-01", room_type=room_type, capacity=2, bed_type=BedType.QUEEN, price_per_night=100)
    guest_a = Guest(reference="GST-TEST-A", first_name="Alex", last_name="One", gender=Gender.UNDISCLOSED)
    guest_b = Guest(reference="GST-TEST-B", first_name="Blair", last_name="Two", gender=Gender.UNDISCLOSED)
    db.add_all([room_type, room, guest_a, guest_b]); db.flush()
    return room_type, room, guest_a, guest_b


def test_overlapping_reservations_are_rejected(db):
    room_type, room, guest_a, guest_b = setup_property(db)
    start = date.today() + timedelta(days=30)
    end = start + timedelta(days=2)
    service = ReservationService(db)
    service.create(ReservationCreate(guest_id=guest_a.id, room_type_id=room_type.id, room_id=room.id, check_in_date=start, check_out_date=end))
    db.commit()
    with pytest.raises(RoomNotAvailableError):
        service.create(ReservationCreate(guest_id=guest_b.id, room_type_id=room_type.id, room_id=room.id, check_in_date=start + timedelta(days=1), check_out_date=end + timedelta(days=1)))


def test_checkout_date_is_validated():
    with pytest.raises(ValueError):
        ReservationCreate(guest_id="00000000-0000-0000-0000-000000000001", room_type_id="00000000-0000-0000-0000-000000000002", check_in_date=date.today(), check_out_date=date.today())
