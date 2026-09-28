"""Small, deterministic invoice PDF renderer.

This intentionally renders from a fully materialised invoice object and never
accepts HTML from the client, avoiding the usual PDF/HTML injection footgun.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.db.models.billing import Invoice


def invoice_pdf_bytes(invoice: Invoice) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("AURORA GRAND HOTEL", styles["Title"]))
    story.append(Paragraph("Hospitality, thoughtfully delivered · 18 Meridian Avenue · +1 555 014 2040", styles["Normal"]))
    story.append(Spacer(1, 8 * mm))
    title = "RECEIPT" if invoice.is_receipt else "INVOICE"
    story.append(Paragraph(f"{title} <b>{invoice.number}</b>", styles["Heading2"]))
    story.append(Paragraph(f"Issue date: {invoice.issue_date.isoformat()}<br/>Guest: {invoice.guest_name}<br/>Email: {invoice.guest_email or '—'}", styles["Normal"]))
    story.append(Spacer(1, 8 * mm))
    data = [["Description", "Qty", "Unit", "Tax", "Total"]]
    for item in invoice.items:
        data.append([item.description, f"{item.quantity:g}", f"{invoice.currency} {item.unit_price:,.2f}", f"{item.tax_rate:g}%", f"{invoice.currency} {item.line_total:,.2f}"])
    data.extend([["", "", "", "Subtotal", f"{invoice.currency} {invoice.subtotal:,.2f}"], ["", "", "", "Tax", f"{invoice.currency} {invoice.tax_amount:,.2f}"], ["", "", "", "Total", f"{invoice.currency} {invoice.total_amount:,.2f}"], ["", "", "", "Paid", f"{invoice.currency} {invoice.paid_amount:,.2f}"], ["", "", "", "Balance", f"{invoice.currency} {invoice.balance:,.2f}"]])
    table = Table(data, colWidths=[88 * mm, 17 * mm, 28 * mm, 20 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#102a43")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#d9e2ec")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("FONTNAME", (3, -5), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (3, -1), (-1, -1), colors.HexColor("#e9f5f1")), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Thank you for staying with Aurora Grand. This document is generated from the hotel folio and is valid without a signature.", styles["Normal"]))
    doc.build(story)
    return output.getvalue()
