"""Guest CRM endpoints."""

from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_permission
from app.core.errors import ConflictError, NotFoundError
from app.db.models.guest import Guest
from app.db.models.reservation import Reservation
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import Page, PaginationParams
from app.schemas.domain import GuestCreate, GuestOut, GuestUpdate, ReservationOut
from app.services.common import audit

router = APIRouter(prefix="/guests", tags=["Guests"])


def _ref() -> str:
    return "GST-" + secrets.token_hex(4).upper()


@router.get("", response_model=Page[GuestOut])
def list_guests(
    pagination: PaginationParams = Depends(),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("guests:view")),
):
    q = select(Guest)
    if not include_archived:
        q = q.where(Guest.deleted_at.is_(None))
    if pagination.search:
        term = f"%{pagination.search.lower()}%"
        q = q.where(or_(func.lower(Guest.first_name).like(term), func.lower(Guest.last_name).like(term), func.lower(Guest.reference).like(term), func.lower(Guest.email).like(term), Guest.phone.like(term)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = pagination.apply_order(q, {"name": Guest.last_name, "created_at": Guest.created_at, "spend": Guest.total_spend}, Guest.created_at).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).all(), total, pagination.page, pagination.page_size)


@router.post("", response_model=GuestOut, status_code=status.HTTP_201_CREATED)
def create_guest(payload: GuestCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("guests:create"))):
    if payload.email:
        existing = db.scalar(select(Guest.id).where(func.lower(Guest.email) == payload.email.lower(), Guest.deleted_at.is_(None)))
        if existing:
            raise ConflictError("A guest with this email address already exists.")
    guest = Guest(reference=_ref(), **payload.model_dump())
    db.add(guest)
    db.flush()
    audit(db, user=user, action="create", resource="guests", resource_id=guest.id, after={"reference": guest.reference}, request=request)
    db.commit()
    db.refresh(guest)
    return guest


@router.get("/{guest_id}", response_model=GuestOut)
def get_guest(guest_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_permission("guests:view"))):
    guest = db.scalar(select(Guest).where(Guest.id == guest_id, Guest.deleted_at.is_(None)))
    if not guest: raise NotFoundError("Guest not found.")
    return guest


@router.patch("/{guest_id}", response_model=GuestOut)
def update_guest(guest_id: UUID, payload: GuestUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("guests:update"))):
    guest = db.scalar(select(Guest).where(Guest.id == guest_id, Guest.deleted_at.is_(None)))
    if not guest: raise NotFoundError("Guest not found.")
    before = {"email": guest.email, "phone": guest.phone, "first_name": guest.first_name, "last_name": guest.last_name}
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None: setattr(guest, key, value)
    audit(db, user=user, action="update", resource="guests", resource_id=guest.id, before=before, after={"email": guest.email, "phone": guest.phone, "first_name": guest.first_name, "last_name": guest.last_name}, request=request)
    db.commit(); db.refresh(guest)
    return guest


@router.delete("/{guest_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_guest(guest_id: UUID, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("guests:delete"))):
    guest = db.scalar(select(Guest).where(Guest.id == guest_id, Guest.deleted_at.is_(None)))
    if not guest: raise NotFoundError("Guest not found.")
    if db.scalar(select(Reservation.id).where(Reservation.guest_id == guest.id, Reservation.status.in_(("pending", "confirmed", "checked_in")), Reservation.deleted_at.is_(None)).limit(1)):
        raise ConflictError("A guest with an active stay cannot be archived.")
    from datetime import UTC, datetime
    guest.deleted_at = datetime.now(UTC); guest.deleted_reason = "Archived by staff"
    audit(db, user=user, action="delete", resource="guests", resource_id=guest.id, request=request)
    db.commit()
    return None


@router.get("/{guest_id}/reservations", response_model=Page[ReservationOut])
def guest_reservations(guest_id: UUID, pagination: PaginationParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_permission("guests:view"))):
    if not db.scalar(select(Guest.id).where(Guest.id == guest_id, Guest.deleted_at.is_(None))): raise NotFoundError("Guest not found.")
    q = select(Reservation).where(Reservation.guest_id == guest_id, Reservation.deleted_at.is_(None)).options(joinedload(Reservation.guest), joinedload(Reservation.room), joinedload(Reservation.room_type))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(Reservation.check_in_date.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).unique().all(), total, pagination.page, pagination.page_size)
