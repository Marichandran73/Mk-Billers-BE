from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Bill, BillItem, InvoiceSettings
from app.schemas import BillItemPayload


def calculate_totals(items: list[BillItemPayload], transportation: float, discount: float) -> dict[str, float]:
    subtotal = sum(item.quantity * item.rate for item in items)
    gst = sum((item.quantity * item.rate * item.gst_percent) / 100 for item in items)
    if discount > subtotal + gst + transportation:
        raise ValueError("Discount cannot exceed invoice value")
    return {
        "subtotal": subtotal,
        "cgst": gst / 2,
        "sgst": gst / 2,
        "grand_total": max(subtotal + gst + transportation - discount, 0),
    }


def generate_invoice_number(db: Session, company_id: int, invoice_date: date) -> str:
    settings = db.query(InvoiceSettings).filter(InvoiceSettings.company_id == company_id).first()
    prefix = settings.invoice_prefix if settings else "INV"
    year = invoice_date.year
    count = (
        db.query(func.count(Bill.id))
        .filter(Bill.company_id == company_id, Bill.invoice_number.like(f"{prefix}-{year}-%"))
        .scalar()
        or 0
    )
    return f"{prefix}-{year}-{count + 1:04d}"


def replace_bill_items(db: Session, bill: Bill, items: list[BillItemPayload]) -> None:
    bill.items.clear()
    db.flush()
    for item in items:
        bill.items.append(
            BillItem(
                description=item.description,
                quantity=item.quantity,
                unit=item.unit,
                rate=item.rate,
                gst_percent=item.gst_percent,
                amount=item.quantity * item.rate,
            )
        )
