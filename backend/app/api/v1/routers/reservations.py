"""Reservation search and stay lifecycle endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_any_permission, require_permission
from app.core.errors import NotFoundError
from app.db.enums import ReservationStatus
from app.db.models.reservation import Reservation
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import Page, PaginationParams
from app.schemas.domain import CancellationRequest, CheckInOut, CheckInRequest, CheckOutRequest, ReservationCreate, ReservationOut, ReservationUpdate
from app.services.reservations import ReservationService

router = APIRouter(prefix="/reservations", tags=["Reservations"])


def query_base():
    return select(Reservation).options(joinedload(Reservation.guest), joinedload(Reservation.room), joinedload(Reservation.room_type))


def find(db: Session, reservation_id: UUID) -> Reservation:
    row = db.scalar(query_base().where(Reservation.id == reservation_id, Reservation.deleted_at.is_(None)))
    if not row: raise NotFoundError("Reservation not found.")
    return row


@router.get("", response_model=Page[ReservationOut])
def list_reservations(pagination: PaginationParams = Depends(), status_filter: ReservationStatus | None = Query(None, alias="status"), date_from: date | None = None, date_to: date | None = None, view: Literal["arrivals", "departures", "in_house"] | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("reservations:view"))):
    q = query_base().where(Reservation.deleted_at.is_(None))
    if status_filter: q = q.where(Reservation.status == status_filter)
    if date_from: q = q.where(Reservation.check_in_date >= date_from)
    if date_to: q = q.where(Reservation.check_in_date <= date_to)
    if view == "arrivals":
        # Same semantics as the dashboard "arrivals today" figure.
        q = q.where(Reservation.check_in_date == date.today(), Reservation.status.in_((ReservationStatus.PENDING, ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_IN)))
    elif view == "departures":
        q = q.where(Reservation.check_out_date == date.today(), Reservation.status == ReservationStatus.CHECKED_IN)
    elif view == "in_house":
        q = q.where(Reservation.status == ReservationStatus.CHECKED_IN)
    if pagination.search:
        from app.db.models.guest import Guest
        term = f"%{pagination.search.lower()}%"
        q = q.join(Reservation.guest).where(
            or_(func.lower(Reservation.reference).like(term), func.lower(Guest.first_name).like(term), func.lower(Guest.last_name).like(term))
        )
    total = db.scalar(select(func.count()).select_from(q.with_only_columns(Reservation.id).order_by(None).subquery())) or 0
    q = q.order_by(Reservation.check_in_date.desc(), Reservation.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).unique().all(), total, pagination.page, pagination.page_size)


@router.post("", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(payload: ReservationCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("reservations:create"))):
    service = ReservationService(db, user, request)
    row = service.create(payload)
    db.commit(); db.refresh(row)
    return row


@router.get("/{reservation_id}", response_model=ReservationOut)
def get_reservation(reservation_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_permission("reservations:view"))):
    return find(db, reservation_id)


@router.patch("/{reservation_id}", response_model=ReservationOut)
def update_reservation(reservation_id: UUID, payload: ReservationUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("reservations:update"))):
    row = ReservationService(db, user, request).update(find(db, reservation_id), payload)
    db.commit(); db.refresh(row); return row


@router.post("/{reservation_id}/cancel", response_model=ReservationOut)
def cancel_reservation(reservation_id: UUID, payload: CancellationRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("reservations:cancel"))):
    row = ReservationService(db, user, request).cancel(find(db, reservation_id), payload.reason)
    db.commit(); db.refresh(row); return row


@router.post("/{reservation_id}/check-in", response_model=CheckInOut)
def check_in(reservation_id: UUID, payload: CheckInRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("reservations:check_in"))):
    row = ReservationService(db, user, request).check_in(find(db, reservation_id), payload)
    db.commit(); db.refresh(row); return row


@router.post("/{reservation_id}/check-out", response_model=CheckInOut)
def check_out(reservation_id: UUID, payload: CheckOutRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("reservations:check_out"))):
    row = ReservationService(db, user, request).check_out(find(db, reservation_id), payload)
    db.commit(); db.refresh(row); return row


@router.post("/{reservation_id}/no-show", response_model=ReservationOut)
def no_show(reservation_id: UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("reservations:no_show"))):
    row = find(db, reservation_id)
    if row.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
        from app.core.errors import BusinessRuleError; raise BusinessRuleError("Only pending or confirmed reservations can be marked no-show.")
    row.status = ReservationStatus.NO_SHOW
    if row.room and row.room.status == "reserved": row.room.status = "available"
    db.commit(); db.refresh(row); return row
