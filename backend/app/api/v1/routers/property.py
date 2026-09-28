"""Room and room-type administration plus availability search."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.dependencies import require_permission
from app.core.errors import ConflictError, NotFoundError
from app.db.enums import RoomStatus
from app.db.models.property import Room, RoomType
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import Page, PaginationParams
from app.schemas.domain import AvailabilityRoom, RoomCreate, RoomOut, RoomTypeCreate, RoomTypeOut, RoomTypeUpdate, RoomUpdate
from app.services.common import audit
from app.services.reservations import ReservationService

router = APIRouter(tags=["Rooms"])


@router.get("/room-types", response_model=Page[RoomTypeOut])
def list_room_types(pagination: PaginationParams = Depends(), include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(require_permission("rooms:view"))):
    q = select(RoomType).where(RoomType.deleted_at.is_(None))
    if not include_inactive: q = q.where(RoomType.is_active.is_(True))
    if pagination.search:
        term = f"%{pagination.search.lower()}%"; q = q.where(or_(func.lower(RoomType.name).like(term), func.lower(RoomType.code).like(term)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.options(selectinload(RoomType.amenities)).order_by(RoomType.sort_order, RoomType.name).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).all(), total, pagination.page, pagination.page_size)


@router.post("/room-types", response_model=RoomTypeOut, status_code=status.HTTP_201_CREATED)
def create_room_type(payload: RoomTypeCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("room_types:manage"))):
    if db.scalar(select(RoomType.id).where(or_(func.lower(RoomType.code) == payload.code.lower(), func.lower(RoomType.name) == payload.name.lower()), RoomType.deleted_at.is_(None))): raise ConflictError("A room type with this code or name already exists.")
    row = RoomType(**payload.model_dump()); db.add(row); db.flush(); audit(db, user=user, action="create", resource="room_types", resource_id=row.id, request=request); db.commit(); db.refresh(row); return row


@router.patch("/room-types/{room_type_id}", response_model=RoomTypeOut)
def update_room_type(room_type_id: UUID, payload: RoomTypeUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("room_types:manage"))):
    row = db.scalar(select(RoomType).where(RoomType.id == room_type_id, RoomType.deleted_at.is_(None)).options(selectinload(RoomType.amenities)))
    if not row: raise NotFoundError("Room type not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None: setattr(row, key, value)
    audit(db, user=user, action="update", resource="room_types", resource_id=row.id, request=request); db.commit(); db.refresh(row); return row


@router.get("/rooms", response_model=Page[RoomOut])
def list_rooms(pagination: PaginationParams = Depends(), status_filter: RoomStatus | None = Query(None, alias="status"), room_type_id: UUID | None = None, floor: int | None = Query(None, ge=0), include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(require_permission("rooms:view"))):
    q = select(Room).where(Room.deleted_at.is_(None))
    if not include_inactive: q = q.where(Room.is_active.is_(True))
    if status_filter: q = q.where(Room.status == status_filter)
    if room_type_id: q = q.where(Room.room_type_id == room_type_id)
    if floor is not None: q = q.where(Room.floor == floor)
    if pagination.search:
        term = f"%{pagination.search.lower()}%"; q = q.where(or_(func.lower(Room.number).like(term), func.lower(Room.name).like(term)))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.options(joinedload(Room.room_type), selectinload(Room.amenities)).order_by(Room.floor, Room.number).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).unique().all(), total, pagination.page, pagination.page_size)


@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(payload: RoomCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("rooms:create"))):
    if not db.get(RoomType, payload.room_type_id): raise NotFoundError("Room type not found.")
    if db.scalar(select(Room.id).where(func.lower(Room.number) == payload.number.lower(), Room.deleted_at.is_(None))): raise ConflictError("A room with this number already exists.")
    row = Room(**payload.model_dump()); db.add(row); db.flush(); audit(db, user=user, action="create", resource="rooms", resource_id=row.id, request=request); db.commit(); db.refresh(row); return row


@router.get("/rooms/availability", response_model=list[AvailabilityRoom])
def availability(room_type_id: UUID, check_in: date, check_out: date, db: Session = Depends(get_db), _: User = Depends(require_permission("rooms:view_calendar"))):
    return [AvailabilityRoom(id=r.id, number=r.number, room_type_id=r.room_type_id, room_type_name=r.room_type.name, price_per_night=r.price_per_night, capacity=r.capacity, status=r.status) for r in ReservationService(db).available_rooms(room_type_id, check_in, check_out)]


@router.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_permission("rooms:view"))):
    row = db.scalar(select(Room).where(Room.id == room_id, Room.deleted_at.is_(None)).options(joinedload(Room.room_type), selectinload(Room.amenities)))
    if not row: raise NotFoundError("Room not found.")
    return row


@router.patch("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: UUID, payload: RoomUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("rooms:update"))):
    row = db.scalar(select(Room).where(Room.id == room_id, Room.deleted_at.is_(None)))
    if not row: raise NotFoundError("Room not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None: setattr(row, key, value)
    audit(db, user=user, action="update", resource="rooms", resource_id=row.id, request=request); db.commit(); db.refresh(row); return row


