"""Date-filtered operational and financial reports."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta, datetime, UTC
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import require_any_permission
from app.db.enums import PaymentEntryType, PaymentStatus, ReservationStatus
from app.db.models.billing import Payment
from app.db.models.operations import Expense, HousekeepingTask
from app.db.models.reservation import Reservation
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.domain import ChartPoint, ReportOut

router = APIRouter(prefix="/reports", tags=["Reports"])


def dates(date_from: date | None, date_to: date | None):
    end = date_to or date.today(); start = date_from or (end - timedelta(days=29))
    if start > end: from app.core.errors import ValidationError; raise ValidationError("Start date must be on or before end date.")
    return start, end


@router.get("/revenue", response_model=ReportOut)
def revenue_report(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_any_permission("reports:view", "reports:financial"))):
    start, end = dates(date_from, date_to)
    rows = db.execute(select(func.date(Payment.paid_at), func.sum(Payment.amount)).where(Payment.entry_type == PaymentEntryType.PAYMENT, Payment.status == PaymentStatus.PAID, func.date(Payment.paid_at) >= start, func.date(Payment.paid_at) <= end).group_by(func.date(Payment.paid_at)).order_by(func.date(Payment.paid_at))).all()
    total = sum((Decimal(str(r[1] or 0)) for r in rows), Decimal("0"))
    return ReportOut(name="Revenue report", generated_at=datetime.now(UTC), date_from=start, date_to=end, summary={"total_revenue": total, "payment_count": len(rows)}, series=[ChartPoint(label=str(r[0]), value=r[1] or 0) for r in rows])


@router.get("/occupancy", response_model=ReportOut)
def occupancy_report(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_any_permission("reports:view", "reports:financial"))):
    start, end = dates(date_from, date_to)
    rows=[]
    total_rooms = db.scalar(select(func.count()).select_from(__import__('app.db.models.property', fromlist=['Room']).Room).where(__import__('app.db.models.property', fromlist=['Room']).Room.is_active.is_(True))) or 0
    current = start
    while current <= end:
        occupied = db.scalar(select(func.count(Reservation.id)).where(Reservation.status.in_((ReservationStatus.CHECKED_IN, ReservationStatus.CHECKED_OUT)), Reservation.check_in_date <= current, Reservation.check_out_date > current)) or 0
        rows.append(ChartPoint(label=str(current), value=round(float(occupied) / total_rooms * 100, 1) if total_rooms else 0, secondary=occupied))
        current += timedelta(days=1)
    avg = sum(float(x.value) for x in rows) / len(rows) if rows else 0
    return ReportOut(name="Occupancy report", generated_at=datetime.now(UTC), date_from=start, date_to=end, summary={"average_occupancy": round(avg, 1), "rooms": total_rooms}, series=rows)


@router.get("/expenses", response_model=ReportOut)
def expense_report(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_any_permission("reports:view", "reports:financial"))):
    start, end = dates(date_from, date_to)
    rows = db.execute(select(Expense.category, func.sum(Expense.amount)).where(Expense.expense_date >= start, Expense.expense_date <= end, Expense.deleted_at.is_(None)).group_by(Expense.category).order_by(func.sum(Expense.amount).desc())).all()
    total = sum((Decimal(str(r[1] or 0)) for r in rows), Decimal("0"))
    return ReportOut(name="Expense report", generated_at=datetime.now(UTC), date_from=start, date_to=end, summary={"total_expenses": total, "categories": len(rows)}, series=[ChartPoint(label=str(r[0].value if hasattr(r[0], 'value') else r[0]).replace('_',' ').title(), value=r[1] or 0) for r in rows])


@router.get("/reservations", response_model=ReportOut)
def reservations_report(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_any_permission("reports:view", "reports:financial"))):
    start, end = dates(date_from, date_to)
    day = func.date(Reservation.created_at)
    base = select(func.count(Reservation.id)).where(Reservation.deleted_at.is_(None), day >= start, day <= end)
    rows = db.execute(select(day, func.count(Reservation.id)).where(Reservation.deleted_at.is_(None), day >= start, day <= end).group_by(day).order_by(day)).all()
    total = db.scalar(base) or 0
    nights = db.scalar(select(func.sum(Reservation.nights)).where(Reservation.deleted_at.is_(None), day >= start, day <= end)) or 0
    value = db.scalar(select(func.sum(Reservation.total_amount)).where(Reservation.deleted_at.is_(None), day >= start, day <= end)) or 0
    mix = db.execute(select(Reservation.status, func.count(Reservation.id)).where(Reservation.deleted_at.is_(None), day >= start, day <= end).group_by(Reservation.status)).all()
    status_mix = [{"label": (s.value if hasattr(s, "value") else str(s)).replace("_", " ").title(), "value": int(c)} for s, c in mix]
    return ReportOut(name="Reservations report", generated_at=datetime.now(UTC), date_from=start, date_to=end, summary={"total_reservations": int(total), "room_nights": int(nights), "booking_value": Decimal(str(value)).quantize(Decimal("0.01")), "status_mix": status_mix}, series=[ChartPoint(label=str(r[0]), value=int(r[1])) for r in rows])


@router.get("/housekeeping", response_model=ReportOut)
def housekeeping_report(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_any_permission("reports:view", "reports:financial"))):
    start, end = dates(date_from, date_to)
    day = func.date(HousekeepingTask.completed_at)
    rows = db.execute(select(day, func.count(HousekeepingTask.id)).where(HousekeepingTask.completed_at.is_not(None), day >= start, day <= end).group_by(day).order_by(day)).all()
    completed = int(sum(r[1] for r in rows))
    inspected = db.scalar(select(func.count(HousekeepingTask.id)).where(HousekeepingTask.completed_at.is_not(None), HousekeepingTask.status == "inspected", day >= start, day <= end)) or 0
    backlog = db.scalar(select(func.count(HousekeepingTask.id)).where(HousekeepingTask.status.in_(("pending", "in_progress")))) or 0
    return ReportOut(name="Housekeeping report", generated_at=datetime.now(UTC), date_from=start, date_to=end, summary={"completed_in_range": completed, "inspected_in_range": int(inspected), "open_backlog": int(backlog)}, series=[ChartPoint(label=str(r[0]), value=int(r[1])) for r in rows])


@router.get("/revenue.csv")
def revenue_csv(date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_any_permission("reports:export", "reports:financial"))):
    start, end = dates(date_from, date_to)
    rows = db.execute(select(func.date(Payment.paid_at), Payment.method_label, Payment.number, Payment.amount).where(Payment.entry_type == PaymentEntryType.PAYMENT, Payment.status == PaymentStatus.PAID, func.date(Payment.paid_at) >= start, func.date(Payment.paid_at) <= end).order_by(Payment.paid_at)).all()
    out = io.StringIO(); writer = csv.writer(out); writer.writerow(["Date", "Payment", "Method", "Amount"]); writer.writerows(rows)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="revenue-{start}-{end}.csv"'})
