"""Service catalog and hotel operations workflows."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.db.enums import (
    ChargeType,
    HousekeepingTaskStatus,
    MaintenanceStatus,
    OrderStatus,
    PaymentMethodType,
    RoomStatus,
)
from app.db.models.billing import PaymentMethod
from app.db.models.operations import (
    Expense,
    HousekeepingTask,
    MaintenanceTicket,
    MenuItem,
    Service,
    ServiceOrder,
    ServiceOrderItem,
)
from app.db.models.property import Room
from app.db.models.reservation import Reservation
from app.db.models.user import User
from app.schemas.domain import (
    ExpenseCreate,
    HousekeepingTaskCreate,
    HousekeepingTaskUpdate,
    MaintenanceTicketCreate,
    MaintenanceTicketUpdate,
    ServiceOrderCreate,
    ServiceOrderStatusUpdate,
)
from app.services.common import audit, make_number, money, next_setting_number, notify
from app.services.reservations import ReservationService


class OperationsService:
    def __init__(self, db: Session, user: User | None = None, request=None):
        self.db, self.user, self.request = db, user, request

    def create_order(self, data: ServiceOrderCreate) -> ServiceOrder:
        reservation = self.db.get(Reservation, data.reservation_id) if data.reservation_id else None
        if data.reservation_id and not reservation:
            raise NotFoundError("Reservation not found.")
        order = ServiceOrder(
            order_number=next_setting_number(self.db, "sequence_order", "ORD"), order_type=data.order_type, reservation_id=data.reservation_id,
            guest_id=data.guest_id or (reservation.guest_id if reservation else None), room_id=data.room_id or (reservation.room_id if reservation else None),
            table_reference=data.table_reference, is_room_service=data.is_room_service, placed_by_id=self.user.id if self.user else None,
            placed_at=datetime.now(UTC), notes=data.notes,
        )
        self.db.add(order)
        self.db.flush()
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        for item in data.items:
            if item.service_id:
                source = self.db.get(Service, item.service_id)
                if not source or not source.is_active:
                    raise NotFoundError("Service not found or inactive.")
                name, price, tax_rate = source.name, money(source.price), money(source.tax_rate if source.is_taxable else 0)
            else:
                source = self.db.get(MenuItem, item.menu_item_id)
                if not source or not source.is_available:
                    raise NotFoundError("Menu item not found or unavailable.")
                name, price, tax_rate = source.name, money(source.price), money(source.tax_rate)
            line = money(item.quantity * price)
            tax = money(line * tax_rate / 100)
            subtotal += line
            tax_total += tax
            order.items.append(ServiceOrderItem(order_id=order.id, service_id=item.service_id, menu_item_id=item.menu_item_id, name_snapshot=name, quantity=item.quantity, unit_price=price, tax_rate=tax_rate, tax_amount=tax, total_amount=line + tax, notes=item.notes))
        order.subtotal = subtotal
        order.tax_amount = tax_total
        order.total_amount = subtotal + tax_total + money(order.service_charge) - money(order.discount_amount)
        self.db.flush()
        if reservation:
            for item in order.items:
                ReservationService(self.db, self.user, self.request).post_charge(reservation, description=f"{order.order_number} · {item.name_snapshot}", charge_type=ChargeType.RESTAURANT if order.order_type.value in ("restaurant", "room_service") else ChargeType.SERVICE, quantity=item.quantity, unit_price=money(item.unit_price), tax_rate=money(item.tax_rate), service_order_id=order.id)
            order.is_billed = True
        audit(self.db, user=self.user, action="create", resource="service_orders", resource_id=order.id, request=self.request)
        return order

    def update_order(self, order: ServiceOrder, data: ServiceOrderStatusUpdate) -> ServiceOrder:
        allowed = {
            OrderStatus.PENDING: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
            OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
            OrderStatus.READY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
            OrderStatus.DELIVERED: set(),
            OrderStatus.CANCELLED: set(),
        }
        if data.status != order.status and data.status not in allowed[order.status]:
            raise BusinessRuleError(f"An order in {order.status.value} cannot move to {data.status.value}.")
        now = datetime.now(UTC)
        order.status = data.status
        order.notes = data.notes or order.notes
        if data.status == OrderStatus.PREPARING: order.accepted_at = now
        if data.status == OrderStatus.READY: order.ready_at = now
        if data.status == OrderStatus.DELIVERED: order.delivered_at = now
        if data.status == OrderStatus.CANCELLED: order.cancelled_at = now
        self.db.flush()
        audit(self.db, user=self.user, action="update", resource="service_orders", resource_id=order.id, after={"status": order.status.value}, request=self.request)
        return order

    def create_task(self, data: HousekeepingTaskCreate) -> HousekeepingTask:
        room = self.db.get(Room, data.room_id)
        if not room or room.deleted_at:
            raise NotFoundError("Room not found.")
        task = HousekeepingTask(room_id=room.id, task_type=data.task_type, priority=data.priority, assigned_to_id=data.assigned_to_id, created_by_id=self.user.id if self.user else None, scheduled_date=data.scheduled_date or date.today(), scheduled_time=data.scheduled_time, notes=data.notes)
        self.db.add(task)
        self.db.flush()
        return task

    def update_task(self, task: HousekeepingTask, data: HousekeepingTaskUpdate) -> HousekeepingTask:
        old = task.status
        values = data.model_dump(exclude_unset=True)
        for key, value in values.items(): setattr(task, key, value)
        now = datetime.now(UTC)
        if data.status == HousekeepingTaskStatus.IN_PROGRESS and old == HousekeepingTaskStatus.PENDING:
            task.started_at = now
            task.room.status = RoomStatus.CLEANING
        elif data.status in (HousekeepingTaskStatus.COMPLETED, HousekeepingTaskStatus.INSPECTED):
            task.completed_at = task.completed_at or now
            if task.started_at: task.duration_minutes = max(1, int((now - task.started_at).total_seconds() / 60))
            if data.status == HousekeepingTaskStatus.COMPLETED:
                task.room.status = RoomStatus.AVAILABLE
                task.room.housekeeping_condition = "clean"
        self.db.flush()
        audit(self.db, user=self.user, action="update", resource="housekeeping_tasks", resource_id=task.id, after={"status": task.status.value}, request=self.request)
        return task

    def create_ticket(self, data: MaintenanceTicketCreate) -> MaintenanceTicket:
        if data.room_id:
            room = self.db.get(Room, data.room_id)
            if not room: raise NotFoundError("Room not found.")
        ticket = MaintenanceTicket(ticket_number=next_setting_number(self.db, "sequence_ticket", "MNT"), room_id=data.room_id, location=data.location, category=data.category, priority=data.priority, status=MaintenanceStatus.OPEN, title=data.title, description=data.description, reported_by_id=self.user.id if self.user else None, reported_at=datetime.now(UTC), blocks_room=data.blocks_room)
        self.db.add(ticket)
        self.db.flush()
        if ticket.room and data.blocks_room:
            ticket.room.status = RoomStatus.MAINTENANCE
        audit(self.db, user=self.user, action="create", resource="maintenance_tickets", resource_id=ticket.id, request=self.request)
        return ticket

    def update_ticket(self, ticket: MaintenanceTicket, data: MaintenanceTicketUpdate) -> MaintenanceTicket:
        for key, value in data.model_dump(exclude_unset=True).items(): setattr(ticket, key, value)
        now = datetime.now(UTC)
        if data.status == MaintenanceStatus.IN_PROGRESS: ticket.started_at = ticket.started_at or now
        if data.status == MaintenanceStatus.RESOLVED: ticket.resolved_at = now
        if data.status == MaintenanceStatus.CLOSED:
            ticket.closed_at = now
            if ticket.room and ticket.blocks_room: ticket.room.status = RoomStatus.CLEANING
        self.db.flush()
        return ticket

    def create_expense(self, data: ExpenseCreate) -> Expense:
        row = Expense(expense_number=next_setting_number(self.db, "sequence_expense", "EXP"), category=data.category, description=data.description, amount=data.amount, tax_amount=data.tax_amount, currency=data.currency, expense_date=data.expense_date, payment_method_label=data.payment_method.value, vendor=data.vendor, reference=data.reference, recorded_by_id=self.user.id if self.user else None, notes=data.notes)
        self.db.add(row)
        self.db.flush()
        audit(self.db, user=self.user, action="create", resource="expenses", resource_id=row.id, request=self.request)
        return row
