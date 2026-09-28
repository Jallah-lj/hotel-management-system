"""Database-backed dashboard aggregates and reports."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session, joinedload

from app.db.enums import (
    ACTIVE_RESERVATION_STATUSES,
    HousekeepingTaskStatus,
    PaymentEntryType,
    PaymentStatus,
    ReservationStatus,
    RoomStatus,
)
from app.db.models.billing import Payment
from app.db.models.operations import HousekeepingTask
from app.db.models.property import Room
from app.db.models.reservation import Reservation
from app.services.common import money


def _scalar(db: Session, stmt, default=0):
    return db.scalar(stmt) or default


def dashboard(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    month_start = today.replace(day=1)
    total_rooms = int(_scalar(db, select(func.count(Room.id)).where(Room.is_active.is_(True), Room.deleted_at.is_(None))))
    counts = {
        status.value: int(_scalar(db, select(func.count(Room.id)).where(
            Room.status == status, Room.is_active.is_(True), Room.deleted_at.is_(None)
        )))
        for status in RoomStatus
    }
    occupied = counts.get(RoomStatus.OCCUPIED.value, 0)
    revenue_today = _scalar(db, select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.entry_type == PaymentEntryType.PAYMENT,
        Payment.status == PaymentStatus.PAID,
        cast(Payment.paid_at, Date) == today,
        Payment.deleted_at.is_(None),
    ))
    revenue_month = _scalar(db, select(func.coalesce(func.sum(Payment.amount), 0)).where(
        Payment.entry_type == PaymentEntryType.PAYMENT,
        Payment.status == PaymentStatus.PAID,
        cast(Payment.paid_at, Date) >= month_start,
        cast(Payment.paid_at, Date) <= today,
        Payment.deleted_at.is_(None),
    ))
    outstanding = _scalar(db, select(func.coalesce(func.sum(Reservation.balance), 0)).where(
        Reservation.status.in_(ACTIVE_RESERVATION_STATUSES),
        Reservation.balance > 0,
        Reservation.deleted_at.is_(None),
    ))
    pending_hk = int(_scalar(db, select(func.count(HousekeepingTask.id)).where(
        HousekeepingTask.status.in_((HousekeepingTaskStatus.PENDING, HousekeepingTaskStatus.IN_PROGRESS)),
        HousekeepingTask.scheduled_date <= today,
    )))

    trend = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        value = _scalar(db, select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.entry_type == PaymentEntryType.PAYMENT,
            Payment.status == PaymentStatus.PAID,
            cast(Payment.paid_at, Date) == day,
        ))
        trend.append({"label": day.strftime("%b %d"), "value": money(value)})

    reservation_mix = []
    for status in ReservationStatus:
        value = _scalar(db, select(func.count(Reservation.id)).where(
            Reservation.status == status, Reservation.deleted_at.is_(None)
        ))
        reservation_mix.append({"label": status.value.replace("_", " ").title(), "value": value})

    methods = db.execute(select(Payment.method_label, func.sum(Payment.amount)).where(
        Payment.entry_type == PaymentEntryType.PAYMENT,
        Payment.status == PaymentStatus.PAID,
    ).group_by(Payment.method_label)).all()
    arrival_query = select(Reservation).where(
        Reservation.check_in_date >= today,
        Reservation.check_in_date <= today + timedelta(days=7),
        Reservation.status.in_((ReservationStatus.CONFIRMED, ReservationStatus.PENDING)),
        Reservation.deleted_at.is_(None),
    ).options(joinedload(Reservation.guest), joinedload(Reservation.room), joinedload(Reservation.room_type)).order_by(Reservation.check_in_date).limit(10)
    departure_query = select(Reservation).where(
        Reservation.check_out_date >= today,
        Reservation.check_out_date <= today + timedelta(days=7),
        Reservation.status == ReservationStatus.CHECKED_IN,
        Reservation.deleted_at.is_(None),
    ).options(joinedload(Reservation.guest), joinedload(Reservation.room), joinedload(Reservation.room_type)).order_by(Reservation.check_out_date).limit(10)
    arrivals = list(db.scalars(arrival_query).unique().all())
    departures = list(db.scalars(departure_query).unique().all())

    return {
        "stats": {
            "total_rooms": total_rooms,
            "available_rooms": counts.get("available", 0),
            "occupied_rooms": occupied,
            "reserved_rooms": counts.get("reserved", 0),
            "cleaning_rooms": counts.get("cleaning", 0),
            "maintenance_rooms": counts.get("maintenance", 0) + counts.get("out_of_service", 0),
            "occupancy_rate": round(occupied / total_rooms * 100, 1) if total_rooms else 0,
            "today_check_ins": int(_scalar(db, select(func.count(Reservation.id)).where(
                Reservation.check_in_date == today,
                Reservation.status.in_((ReservationStatus.CONFIRMED, ReservationStatus.PENDING, ReservationStatus.CHECKED_IN)),
            ))),
            "today_check_outs": int(_scalar(db, select(func.count(Reservation.id)).where(
                Reservation.check_out_date == today, Reservation.status == ReservationStatus.CHECKED_IN,
            ))),
            "current_guests": int(_scalar(db, select(func.count(Reservation.id)).where(
                Reservation.status == ReservationStatus.CHECKED_IN,
            ))),
            "today_revenue": money(revenue_today),
            "month_revenue": money(revenue_month),
            "outstanding_payments": money(outstanding),
            "pending_housekeeping": pending_hk,
        },
        "revenue_trend": trend,
        "occupancy_trend": [],
        "reservation_mix": reservation_mix,
        "payment_methods": [{"label": label or "Other", "value": money(value)} for label, value in methods],
        "upcoming_arrivals": arrivals,
        "upcoming_departures": departures,
    }
