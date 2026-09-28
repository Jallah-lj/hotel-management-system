"""Payment and invoice rules.  Refunds are separate immutable ledger rows."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BusinessRuleError, NotFoundError
from app.db.enums import AuditAction, ChargeType, InvoiceStatus, PaymentEntryType, PaymentMethodType, PaymentStatus
from app.db.models.billing import Invoice, InvoiceItem, Payment, PaymentMethod
from app.db.models.guest import Guest
from app.db.models.reservation import Reservation
from app.db.models.user import User
from app.services.common import audit, money, next_setting_number
from app.services.reservations import ReservationService


METHOD_LABELS = {
    PaymentMethodType.CASH: "Cash",
    PaymentMethodType.CARD: "Card",
    PaymentMethodType.BANK_TRANSFER: "Bank transfer",
    PaymentMethodType.MOBILE_MONEY: "Mobile money",
    PaymentMethodType.OTHER: "Other",
}


class PaymentService:
    def __init__(self, db: Session, user: User | None = None, request=None):
        self.db, self.user, self.request = db, user, request

    def create(self, reservation: Reservation, amount: Decimal, method: PaymentMethodType, reference: str | None = None, notes: str | None = None) -> Payment:
        if reservation.status.value in ("cancelled", "no_show"):
            raise BusinessRuleError("Payments cannot be posted to a cancelled or no-show reservation.")
        amount = money(amount)
        ReservationService(self.db, self.user, self.request)._recalculate(reservation)
        if amount > money(reservation.balance):
            raise BusinessRuleError(f"Payment exceeds the outstanding balance of {money(reservation.balance):.2f} {reservation.currency}.", code="overpayment")
        row = Payment(
            number=next_setting_number(self.db, "sequence_payment", "PAY"), reservation_id=reservation.id, guest_id=reservation.guest_id,
            entry_type=PaymentEntryType.PAYMENT, amount=amount, currency=reservation.currency, method_code=method.value,
            method_label=METHOD_LABELS[method], reference=reference, status=PaymentStatus.PAID, paid_at=datetime.now(UTC),
            received_by_id=self.user.id if self.user else None, notes=notes,
        )
        self.db.add(row)
        self.db.flush()
        ReservationService(self.db, self.user, self.request)._recalculate(reservation)
        audit(self.db, user=self.user, action=AuditAction.PAYMENT.value, resource="payments", resource_id=row.id, after={"amount": str(amount), "method": method.value}, request=self.request)
        return row

    def refund(self, payment: Payment, amount: Decimal, reason: str) -> Payment:
        if not payment.is_refundable:
            raise BusinessRuleError("Only settled payment entries can be refunded.")
        amount = money(amount)
        already = sum((money(p.amount) for p in self.db.scalars(select(Payment).where(Payment.parent_payment_id == payment.id, Payment.status == PaymentStatus.PAID)).all()), Decimal("0"))
        if amount > money(payment.amount) - already:
            raise BusinessRuleError("Refund cannot exceed the remaining amount originally paid.", code="refund_exceeds_payment")
        refund = Payment(number=next_setting_number(self.db, "sequence_payment", "REF"), reservation_id=payment.reservation_id, guest_id=payment.guest_id, invoice_id=payment.invoice_id, parent_payment_id=payment.id, entry_type=PaymentEntryType.REFUND, amount=amount, currency=payment.currency, method_id=payment.method_id, method_code=payment.method_code, method_label=payment.method_label, reference=payment.reference, status=PaymentStatus.PAID, paid_at=datetime.now(UTC), received_by_id=self.user.id if self.user else None, notes=reason)
        self.db.add(refund)
        self.db.flush()
        reservation = self.db.get(Reservation, payment.reservation_id)
        if reservation:
            ReservationService(self.db, self.user, self.request)._recalculate(reservation)
        audit(self.db, user=self.user, action=AuditAction.REFUND.value, resource="payments", resource_id=refund.id, description=reason, after={"amount": str(amount)}, request=self.request)
        return refund

    def issue_invoice(self, reservation: Reservation, *, receipt: bool = False) -> Invoice:
        ReservationService(self.db, self.user, self.request)._recalculate(reservation)
        for existing in reservation.invoices:
            if existing.status != InvoiceStatus.VOID and existing.is_receipt == receipt:
                return existing
        invoice = Invoice(number=next_setting_number(self.db, "sequence_invoice", "RCT" if receipt else "INV"), reservation_id=reservation.id, guest_id=reservation.guest_id, status=InvoiceStatus.ISSUED, issue_date=date.today(), guest_name=reservation.guest.full_name, guest_email=reservation.guest.email, guest_address=", ".join(filter(None, [reservation.guest.address_line1, reservation.guest.city, reservation.guest.country])), currency=reservation.currency, subtotal=money(reservation.charges_total), discount_amount=money(reservation.discount_total), tax_amount=money(reservation.tax_total), total_amount=money(reservation.total_amount), paid_amount=money(reservation.paid_amount), balance=money(reservation.balance), is_receipt=receipt, issued_by_id=self.user.id if self.user else None)
        self.db.add(invoice)
        self.db.flush()
        for idx, charge in enumerate(reservation.charges):
            if charge.is_voided: continue
            invoice.items.append(InvoiceItem(invoice_id=invoice.id, charge_id=charge.id, charge_type=charge.charge_type, description=charge.description, service_date=charge.service_date, quantity=charge.quantity, unit_price=charge.unit_price, discount_amount=charge.discount_amount, tax_rate=charge.tax_rate, tax_amount=charge.tax_amount, line_total=charge.total_amount, sort_order=idx))
        self.db.flush()
        return invoice
