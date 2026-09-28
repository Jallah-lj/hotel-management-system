"""Reservation, folio and stay lifecycle business rules."""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, lazyload

from app.core.errors import BusinessRuleError, ConflictError, NotFoundError, RoomNotAvailableError, ValidationError
from app.db.enums import (
    ACTIVE_RESERVATION_STATUSES,
    AuditAction,
    ChargeType,
    FolioStatus,
    PaymentMethodType,
    PaymentStatus,
    ReservationStatus,
    RoomStatus,
)
from app.db.models.billing import Payment
from app.db.models.guest import Guest
from app.db.models.property import Room, RoomType
from app.db.models.reservation import CheckIn, CheckOut, Reservation, ReservationCharge
from app.db.models.user import User
from app.schemas.domain import CheckInRequest, CheckOutRequest, ReservationCreate, ReservationUpdate
from app.services.common import audit, make_number, money, next_setting_number, notify


class ReservationService:
    def __init__(self, db: Session, user: User | None = None, request=None):
        self.db = db
        self.user = user
        self.request = request

    def _reservation_query(self):
        return select(Reservation).options(
            joinedload(Reservation.guest), joinedload(Reservation.room), joinedload(Reservation.room_type)
        )

    def _check_window(self, room_id: UUID | None, check_in: date, check_out: date, exclude_id: UUID | None = None) -> None:
        if check_out <= check_in:
            raise ValidationError("Check-out date must be after check-in date.")
        if not room_id:
            return
        room = self.db.scalar(select(Room).options(lazyload(Room.room_type)).where(Room.id == room_id, Room.deleted_at.is_(None)).with_for_update())
        if not room:
            raise NotFoundError("Room not found.")
        if not room.is_bookable and room.status not in (RoomStatus.RESERVED, RoomStatus.AVAILABLE):
            raise RoomNotAvailableError("That room is out of service or under maintenance.")
        overlap = select(Reservation.id).where(
            Reservation.room_id == room_id,
            Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            Reservation.check_in_date < check_out,
            Reservation.check_out_date > check_in,
            Reservation.deleted_at.is_(None),
        )
        if exclude_id:
            overlap = overlap.where(Reservation.id != exclude_id)
        if self.db.scalar(overlap.limit(1)):
            raise RoomNotAvailableError("That room is already reserved for part of the requested stay.")

    def available_rooms(self, room_type_id: UUID, check_in: date, check_out: date) -> list[Room]:
        if check_out <= check_in:
            raise ValidationError("Check-out date must be after check-in date.")
        overlap = select(Reservation.room_id).where(
            Reservation.room_id.is_not(None), Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
            Reservation.check_in_date < check_out, Reservation.check_out_date > check_in,
            Reservation.deleted_at.is_(None),
        )
        return list(self.db.scalars(select(Room).where(
            Room.room_type_id == room_type_id, Room.is_active.is_(True), Room.deleted_at.is_(None),
            Room.status.not_in((RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE)), ~Room.id.in_(overlap)
        ).order_by(Room.number)).all())

    def _price(self, room_type: RoomType, check_in: date, check_out: date, adults: int, room_rate: Decimal | None) -> tuple[Decimal, Decimal, Decimal]:
        rate = money(room_rate if room_rate is not None else room_type.base_price)
        nights = (check_out - check_in).days
        # Weekend overrides are applied per night; this prevents a silent
        # undercharge when a stay crosses a weekend.
        room_total = Decimal("0")
        current = check_in
        while current < check_out:
            day_rate = money(room_type.weekend_price) if room_type.weekend_price and current.weekday() >= 5 and room_rate is None else rate
            room_total += day_rate
            current += timedelta(days=1)
        extra = max(0, adults - room_type.max_adults) * money(room_type.extra_person_price) * nights
        return rate, room_total, extra

    def _recalculate(self, reservation: Reservation) -> None:
        active_charges = [c for c in reservation.charges if not c.is_voided]
        room_charges = [c for c in active_charges if c.charge_type == ChargeType.ROOM]
        room_total = sum((money(c.total_amount) for c in room_charges), Decimal("0"))
        charges_total = sum((money(c.total_amount) for c in active_charges), Decimal("0"))
        discount_total = sum((money(c.discount_amount) for c in active_charges), Decimal("0")) + money(reservation.discount_amount)
        tax_total = sum((money(c.tax_amount) for c in active_charges), Decimal("0"))
        services_total = sum((money(c.total_amount) for c in active_charges if c.charge_type not in (ChargeType.ROOM, ChargeType.DISCOUNT)), Decimal("0"))
        # Reservation-level discount is applied before tax to preserve a clear
        # folio audit trail.
        subtotal_after_discount = max(Decimal("0"), charges_total - money(reservation.discount_amount))
        total = (subtotal_after_discount + tax_total).quantize(Decimal("0.01"))
        paid = sum((money(p.amount) for p in reservation.payments if p.entry_type.value == "payment" and p.status == PaymentStatus.PAID), Decimal("0"))
        refunded = sum((money(p.amount) for p in reservation.payments if p.entry_type.value == "refund" and p.status == PaymentStatus.PAID), Decimal("0"))
        paid_net = max(Decimal("0"), paid - refunded)
        reservation.room_total = room_total
        reservation.services_total = services_total
        reservation.charges_total = charges_total
        reservation.discount_total = discount_total
        reservation.tax_total = tax_total
        reservation.total_amount = total
        reservation.paid_amount = paid_net
        reservation.refunded_amount = refunded
        reservation.balance = max(Decimal("0"), total - paid_net)
        reservation.payment_status = PaymentStatus.PAID if reservation.balance == 0 and total > 0 else (PaymentStatus.PARTIAL if paid_net > 0 else PaymentStatus.PENDING)

    def create(self, data: ReservationCreate) -> Reservation:
        guest = self.db.get(Guest, data.guest_id)
        room_type = self.db.get(RoomType, data.room_type_id)
        if not guest or guest.deleted_at:
            raise NotFoundError("Guest not found.")
        if guest.blacklisted:
            raise BusinessRuleError("This guest profile is restricted from new bookings.")
        if not room_type or room_type.deleted_at or not room_type.is_active:
            raise NotFoundError("Room type not found or inactive.")
        if data.adults + data.children > room_type.max_occupancy:
            raise ValidationError("Guest count exceeds the selected room type capacity.")
        room_id = data.room_id
        if room_id:
            room = self.db.get(Room, room_id)
            if not room or room.room_type_id != room_type.id:
                raise ValidationError("The assigned room does not belong to the selected room type.")
        else:
            available = self.available_rooms(room_type.id, data.check_in_date, data.check_out_date)
            if len(available) == 1:
                room_id = available[0].id
            elif not available:
                raise RoomNotAvailableError()
        self._check_window(room_id, data.check_in_date, data.check_out_date)
        rate, room_total, extra = self._price(room_type, data.check_in_date, data.check_out_date, data.adults, data.room_rate)
        reservation = Reservation(
            reference=next_setting_number(self.db, "sequence_reservation", "RES"), guest_id=guest.id,
            room_type_id=room_type.id, room_id=room_id, check_in_date=data.check_in_date, check_out_date=data.check_out_date,
            nights=(data.check_out_date - data.check_in_date).days, adults=data.adults, children=data.children,
            room_rate=rate, extra_person_charge=extra, room_total=room_total, currency=data.currency,
            tax_rate=money(data.tax_rate if data.tax_rate is not None else room_type.tax_rate), discount_amount=data.discount_amount,
            discount_reason=data.discount_reason, booking_source=data.booking_source, special_requests=data.special_requests,
            internal_notes=data.internal_notes, status=ReservationStatus.CONFIRMED,
            created_by_id=self.user.id if self.user else None, updated_by_id=self.user.id if self.user else None,
        )
        self.db.add(reservation)
        self.db.flush()
        # Room charge is an immutable snapshot of the rate at booking time.
        tax = (room_total + extra) * reservation.tax_rate / 100
        self.db.add(ReservationCharge(
            reservation_id=reservation.id, charge_type=ChargeType.ROOM, description=f"Accommodation · {reservation.nights} night(s)",
            quantity=reservation.nights, unit_price=(room_total + extra) / reservation.nights, tax_rate=reservation.tax_rate,
            tax_amount=tax, total_amount=room_total + extra, posted_at=datetime.now(UTC), posted_by_id=self.user.id if self.user else None,
        ))
        self.db.flush()
        self.db.refresh(reservation)
        self._recalculate(reservation)
        if room_id:
            room = self.db.get(Room, room_id)
            if room and room.status == RoomStatus.AVAILABLE:
                room.status = RoomStatus.RESERVED
        audit(self.db, user=self.user, action=AuditAction.CREATE.value, resource="reservations", resource_id=reservation.id, description="Reservation created", after={"reference": reservation.reference, "status": reservation.status.value}, request=self.request)
        self.db.flush()
        return reservation

    def update(self, reservation: Reservation, data: ReservationUpdate) -> Reservation:
        if reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.CHECKED_OUT, ReservationStatus.NO_SHOW):
            raise BusinessRuleError("This reservation is closed and cannot be modified.")
        before = {"status": reservation.status.value, "room_id": reservation.room_id, "check_in_date": reservation.check_in_date, "check_out_date": reservation.check_out_date}
        values = data.model_dump(exclude_unset=True)
        new_in = values.get("check_in_date", reservation.check_in_date)
        new_out = values.get("check_out_date", reservation.check_out_date)
        new_room = values.get("room_id", reservation.room_id)
        if new_room:
            room = self.db.get(Room, new_room)
            if not room or room.room_type_id != reservation.room_type_id:
                raise ValidationError("The assigned room does not belong to this reservation's room type.")
        self._check_window(new_room, new_in, new_out, reservation.id)
        for key, value in values.items():
            if key not in {"status"}:
                setattr(reservation, key, value)
        reservation.nights = (new_out - new_in).days
        reservation.updated_by_id = self.user.id if self.user else None
        self.db.flush()
        audit(self.db, user=self.user, action=AuditAction.UPDATE.value, resource="reservations", resource_id=reservation.id, before=before, after={"status": reservation.status.value, "room_id": reservation.room_id, "check_in_date": reservation.check_in_date, "check_out_date": reservation.check_out_date}, request=self.request)
        return reservation

    def cancel(self, reservation: Reservation, reason: str) -> Reservation:
        if reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.CHECKED_OUT):
            raise BusinessRuleError("This reservation is already closed.")
        reservation.status = ReservationStatus.CANCELLED
        reservation.cancellation_reason = reason
        reservation.cancelled_at = datetime.now(UTC)
        reservation.cancelled_by_id = self.user.id if self.user else None
        if reservation.room and reservation.room.status == RoomStatus.RESERVED:
            reservation.room.status = RoomStatus.AVAILABLE
        audit(self.db, user=self.user, action=AuditAction.CANCEL.value, resource="reservations", resource_id=reservation.id, description=reason, request=self.request)
        return reservation

    def check_in(self, reservation: Reservation, data: CheckInRequest) -> CheckIn:
        if reservation.status not in (ReservationStatus.CONFIRMED, ReservationStatus.PENDING):
            raise BusinessRuleError("Only confirmed or pending reservations can be checked in.")
        room = self.db.get(Room, data.room_id or reservation.room_id) if (data.room_id or reservation.room_id) else None
        if not room:
            raise ValidationError("Assign a room before checking the guest in.")
        self._check_window(room.id, reservation.check_in_date, reservation.check_out_date, reservation.id)
        if room.status in (RoomStatus.OCCUPIED, RoomStatus.CLEANING, RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE):
            raise RoomNotAvailableError("The selected room is not ready for check-in.")
        checkin = CheckIn(
            reservation_id=reservation.id, room_id=room.id, checked_in_at=datetime.now(UTC), checked_in_by_id=self.user.id if self.user else None,
            deposit_amount=data.deposit_amount, identity_verified=data.identity_verified, registration_card_signed=data.registration_card_signed,
            key_cards_issued=data.key_cards_issued, notes=data.notes, confirmation_code=secrets.token_hex(5).upper(),
        )
        self.db.add(checkin)
        reservation.room_id = room.id
        reservation.status = ReservationStatus.CHECKED_IN
        room.status = RoomStatus.OCCUPIED
        self.db.flush()
        audit(self.db, user=self.user, action=AuditAction.CHECK_IN.value, resource="reservations", resource_id=reservation.id, request=self.request)
        return checkin

    def check_out(self, reservation: Reservation, data: CheckOutRequest) -> CheckOut:
        if reservation.status != ReservationStatus.CHECKED_IN:
            raise BusinessRuleError("Only checked-in guests can check out.")
        if not reservation.check_in:
            raise BusinessRuleError("Check-in record is missing.")
        self._recalculate(reservation)
        balance = money(reservation.balance)
        if data.payment_amount:
            from app.services.payments import PaymentService
            PaymentService(self.db, self.user, self.request).create(reservation, data.payment_amount, data.payment_method, data.payment_reference, "Final payment at check-out")
            self.db.flush()
            self.db.refresh(reservation)
            self._recalculate(reservation)
            balance = money(reservation.balance)
        if balance > 0 and not data.allow_balance_override:
            raise BusinessRuleError(f"Outstanding balance of {balance:.2f} {reservation.currency} must be settled before check-out.", code="insufficient_balance", details={"balance": str(balance)})
        now = datetime.now(UTC)
        checkout = CheckOut(
            reservation_id=reservation.id, room_id=reservation.room_id, checked_out_at=now, checked_out_by_id=self.user.id if self.user else None,
            final_balance=balance, balance_settled=balance <= 0, override_by_id=self.user.id if balance > 0 else None,
            override_reason=data.override_reason, keys_returned=data.keys_returned, minibar_checked=data.minibar_checked,
            luggage_collected=data.luggage_collected, notes=data.notes,
        )
        self.db.add(checkout)
        reservation.status = ReservationStatus.CHECKED_OUT
        reservation.folio_status = FolioStatus.SETTLED if balance <= 0 else FolioStatus.CLOSED
        reservation.folio_closed_at = now
        if reservation.room:
            reservation.room.status = RoomStatus.CLEANING
        self.db.flush()
        audit(self.db, user=self.user, action=AuditAction.CHECK_OUT.value, resource="reservations", resource_id=reservation.id, after={"balance": str(balance)}, request=self.request)
        return checkout

    def post_charge(self, reservation: Reservation, *, description: str, charge_type: ChargeType, quantity: Decimal, unit_price: Decimal, tax_rate: Decimal, service_order_id: UUID | None = None) -> ReservationCharge:
        if reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.CHECKED_OUT):
            raise BusinessRuleError("Charges cannot be added to a closed reservation.")
        subtotal = money(quantity * unit_price)
        tax = money(subtotal * tax_rate / 100)
        charge = ReservationCharge(reservation_id=reservation.id, charge_type=charge_type, description=description, quantity=quantity, unit_price=unit_price, tax_rate=tax_rate, tax_amount=tax, total_amount=subtotal, service_order_id=service_order_id, service_date=date.today(), posted_at=datetime.now(UTC), posted_by_id=self.user.id if self.user else None)
        self.db.add(charge)
        self.db.flush()
        self.db.refresh(reservation)
        self._recalculate(reservation)
        return charge
