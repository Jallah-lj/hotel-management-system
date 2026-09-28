"""Housekeeping, maintenance, service order and notifications endpoints."""

from __future__ import annotations

from datetime import date, UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_permission
from app.core.errors import NotFoundError
from app.db.enums import HousekeepingTaskStatus, MaintenanceStatus, OrderStatus
from app.db.models.operations import HousekeepingTask, MaintenanceTicket, Notification, Service, ServiceOrder
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import Page, PaginationParams, Message
from app.schemas.domain import HousekeepingTaskCreate, HousekeepingTaskOut, HousekeepingTaskUpdate, MaintenanceTicketCreate, MaintenanceTicketOut, MaintenanceTicketUpdate, ServiceCreate, ServiceOrderCreate, ServiceOrderOut, ServiceOrderStatusUpdate, ServiceOut, ServiceUpdate
from app.services.operations import OperationsService

router = APIRouter(tags=["Operations"])


@router.get("/services", response_model=Page[ServiceOut])
def list_services(pagination: PaginationParams = Depends(), include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(require_permission("services:view"))):
    q = select(Service).where(Service.deleted_at.is_(None))
    if not include_inactive: q = q.where(Service.is_active.is_(True))
    if pagination.search: q = q.where(Service.name.ilike(f"%{pagination.search}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(Service.category, Service.name).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).all(), total, pagination.page, pagination.page_size)


@router.post("/services", response_model=ServiceOut)
def create_service(payload: ServiceCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("services:manage"))):
    row = Service(**payload.model_dump()); db.add(row); db.flush(); db.commit(); db.refresh(row); return row


@router.patch("/services/{service_id}", response_model=ServiceOut)
def update_service(service_id: UUID, payload: ServiceUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("services:manage"))):
    row = db.scalar(select(Service).where(Service.id == service_id, Service.deleted_at.is_(None)))
    if not row: raise NotFoundError("Service not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None: setattr(row, key, value)
    db.commit(); db.refresh(row); return row


@router.get("/orders", response_model=Page[ServiceOrderOut])
def list_orders(pagination: PaginationParams = Depends(), status_filter: OrderStatus | None = Query(None, alias="status"), db: Session = Depends(get_db), _: User = Depends(require_permission("orders:view"))):
    q = select(ServiceOrder).where(ServiceOrder.deleted_at.is_(None)).options(joinedload(ServiceOrder.items))
    if status_filter: q = q.where(ServiceOrder.status == status_filter)
    if pagination.search: q = q.where(ServiceOrder.order_number.ilike(f"%{pagination.search}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(ServiceOrder.placed_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).unique().all(), total, pagination.page, pagination.page_size)


@router.post("/orders", response_model=ServiceOrderOut)
def create_order(payload: ServiceOrderCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("orders:create"))):
    row = OperationsService(db, user, request).create_order(payload); db.commit(); db.refresh(row); return row


@router.patch("/orders/{order_id}", response_model=ServiceOrderOut)
def update_order(order_id: UUID, payload: ServiceOrderStatusUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("orders:update"))):
    row = db.scalar(select(ServiceOrder).where(ServiceOrder.id == order_id, ServiceOrder.deleted_at.is_(None)).options(joinedload(ServiceOrder.items)))
    if not row: raise NotFoundError("Order not found.")
    row = OperationsService(db, user, request).update_order(row, payload); db.commit(); db.refresh(row); return row


@router.get("/housekeeping", response_model=Page[HousekeepingTaskOut])
def list_housekeeping(pagination: PaginationParams = Depends(), task_date: date | None = None, status_filter: HousekeepingTaskStatus | None = Query(None, alias="status"), db: Session = Depends(get_db), _: User = Depends(require_permission("housekeeping:view"))):
    q = select(HousekeepingTask).options(joinedload(HousekeepingTask.room)).where(HousekeepingTask.scheduled_date == (task_date or date.today()))
    if status_filter: q = q.where(HousekeepingTask.status == status_filter)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(HousekeepingTask.priority.desc(), HousekeepingTask.created_at).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).unique().all(), total, pagination.page, pagination.page_size)


@router.post("/housekeeping", response_model=HousekeepingTaskOut)
def create_housekeeping(payload: HousekeepingTaskCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("housekeeping:assign"))):
    row = OperationsService(db, user, request).create_task(payload); db.commit(); db.refresh(row); return row


@router.patch("/housekeeping/{task_id}", response_model=HousekeepingTaskOut)
def update_housekeeping(task_id: UUID, payload: HousekeepingTaskUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("housekeeping:update_status"))):
    row = db.scalar(select(HousekeepingTask).where(HousekeepingTask.id == task_id).options(joinedload(HousekeepingTask.room)))
    if not row: raise NotFoundError("Housekeeping task not found.")
    row = OperationsService(db, user, request).update_task(row, payload); db.commit(); db.refresh(row); return row


@router.get("/maintenance", response_model=Page[MaintenanceTicketOut])
def list_maintenance(pagination: PaginationParams = Depends(), status_filter: MaintenanceStatus | None = Query(None, alias="status"), db: Session = Depends(get_db), _: User = Depends(require_permission("maintenance:view"))):
    q = select(MaintenanceTicket).where(MaintenanceTicket.status != MaintenanceStatus.CLOSED)
    if status_filter: q = q.where(MaintenanceTicket.status == status_filter)
    if pagination.search: q = q.where(MaintenanceTicket.title.ilike(f"%{pagination.search}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(MaintenanceTicket.priority.desc(), MaintenanceTicket.reported_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).all(), total, pagination.page, pagination.page_size)


@router.post("/maintenance", response_model=MaintenanceTicketOut)
def create_maintenance(payload: MaintenanceTicketCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("maintenance:create"))):
    row = OperationsService(db, user, request).create_ticket(payload); db.commit(); db.refresh(row); return row


@router.patch("/maintenance/{ticket_id}", response_model=MaintenanceTicketOut)
def update_maintenance(ticket_id: UUID, payload: MaintenanceTicketUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("maintenance:update"))):
    row = db.get(MaintenanceTicket, ticket_id)
    if not row: raise NotFoundError("Maintenance ticket not found.")
    row = OperationsService(db, user, request).update_ticket(row, payload); db.commit(); db.refresh(row); return row


@router.get("/notifications")
def list_notifications(unread_only: bool = False, pagination: PaginationParams = Depends(), db: Session = Depends(get_db), user: User = Depends(require_permission("notifications:view"))):
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only: q = q.where(Notification.is_read.is_(False))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(Notification.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).all(), total, pagination.page, pagination.page_size)


@router.post("/notifications/{notification_id}/read", response_model=Message)
def read_notification(notification_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("notifications:view"))):
    row = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if not row: raise NotFoundError("Notification not found.")
    row.is_read = True; row.read_at = datetime.now(UTC); db.commit(); return Message(message="Notification marked as read.")
