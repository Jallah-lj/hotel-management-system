"""Payments, invoices and expense endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_permission
from app.core.errors import NotFoundError
from app.db.enums import PaymentEntryType, PaymentStatus
from app.db.models.billing import Invoice, Payment
from app.db.models.operations import Expense
from app.db.models.reservation import Reservation
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import Page, PaginationParams
from app.schemas.domain import ExpenseCreate, ExpenseOut, InvoiceOut, PaymentCreate, PaymentOut, RefundCreate
from app.services.operations import OperationsService
from app.services.payments import PaymentService
from app.services.common import notify
from app.services.reservations import ReservationService

router = APIRouter(tags=["Finance"])


@router.get("/payments", response_model=Page[PaymentOut])
def list_payments(pagination: PaginationParams = Depends(), date_from: date | None = None, date_to: date | None = None, entry_filter: PaymentEntryType | None = Query(None, alias="entry"), db: Session = Depends(get_db), _: User = Depends(require_permission("payments:view"))):
    q = select(Payment).where(Payment.deleted_at.is_(None))
    if entry_filter: q = q.where(Payment.entry_type == entry_filter)
    if date_from: q = q.where(func.date(Payment.paid_at) >= date_from)
    if date_to: q = q.where(func.date(Payment.paid_at) <= date_to)
    if pagination.search: q = q.where(Payment.number.ilike(f"%{pagination.search}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(Payment.paid_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).all(), total, pagination.page, pagination.page_size)


@router.post("/payments", response_model=PaymentOut)
def create_payment(payload: PaymentCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("payments:create"))):
    reservation = db.get(Reservation, payload.reservation_id)
    if not reservation: raise NotFoundError("Reservation not found.")
    row = PaymentService(db, user, request).create(reservation, payload.amount, payload.method, payload.reference, payload.notes)
    notify(db, user_id=user.id, title=f"Payment {row.number} recorded", message=f"{row.amount} {row.currency} via {row.method_label}", category="payment", link="/finance", entity_type="payment", entity_id=row.id, dedupe_key=f"pay-created-{row.id}")
    db.commit(); db.refresh(row); return row


@router.post("/payments/{payment_id}/refund", response_model=PaymentOut)
def refund_payment(payment_id: UUID, payload: RefundCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("payments:refund"))):
    row = db.get(Payment, payment_id)
    if not row: raise NotFoundError("Payment not found.")
    result = PaymentService(db, user, request).refund(row, payload.amount, payload.reason)
    notify(db, user_id=user.id, title=f"Refund {result.number} issued", message=f"{result.amount} {result.currency} returned via {result.method_label}", category="payment", severity="warning", link="/finance", entity_type="payment", entity_id=result.id, dedupe_key=f"refund-created-{result.id}")
    db.commit(); db.refresh(result); return result


@router.get("/invoices", response_model=Page[InvoiceOut])
def list_invoices(pagination: PaginationParams = Depends(), db: Session = Depends(get_db), _: User = Depends(require_permission("invoices:view"))):
    q = select(Invoice).where(Invoice.deleted_at.is_(None)).options(joinedload(Invoice.items))
    if pagination.search: q = q.where(Invoice.number.ilike(f"%{pagination.search}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(Invoice.issue_date.desc(), Invoice.created_at.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).unique().all(), total, pagination.page, pagination.page_size)


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_permission("invoices:view"))):
    row = db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None)).options(joinedload(Invoice.items)))
    if not row: raise NotFoundError("Invoice not found.")
    return row


@router.post("/reservations/{reservation_id}/invoice", response_model=InvoiceOut)
def issue_invoice(reservation_id: UUID, request: Request, receipt: bool = False, db: Session = Depends(get_db), user: User = Depends(require_permission("invoices:create"))):
    reservation = db.get(Reservation, reservation_id)
    if not reservation: raise NotFoundError("Reservation not found.")
    invoice = PaymentService(db, user, request).issue_invoice(reservation, receipt=receipt)
    db.commit(); db.refresh(invoice); return invoice


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_permission("invoices:view"))):
    row = db.scalar(select(Invoice).where(Invoice.id == invoice_id).options(joinedload(Invoice.items)))
    if not row: raise NotFoundError("Invoice not found.")
    from app.services.pdf import invoice_pdf_bytes
    content = invoice_pdf_bytes(row)
    return StreamingResponse(iter([content]), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{row.number}.pdf"'})


@router.get("/expenses", response_model=Page[ExpenseOut])
def list_expenses(pagination: PaginationParams = Depends(), date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("expenses:view"))):
    q = select(Expense).where(Expense.deleted_at.is_(None))
    if date_from: q = q.where(Expense.expense_date >= date_from)
    if date_to: q = q.where(Expense.expense_date <= date_to)
    if pagination.search: q = q.where(Expense.description.ilike(f"%{pagination.search}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(Expense.expense_date.desc()).offset(pagination.offset).limit(pagination.page_size)
    return Page.build(db.scalars(q).all(), total, pagination.page, pagination.page_size)


@router.post("/expenses", response_model=ExpenseOut)
def create_expense(payload: ExpenseCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_permission("expenses:create"))):
    row = OperationsService(db, user, request).create_expense(payload)
    db.commit(); db.refresh(row); return row
