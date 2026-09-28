from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_active_admin_company, require_admin_or_super
from app.core.plans import get_plan
from app.database.connection import get_db
from app.models import Bill, BillPayment, Customer, User
from app.schemas import BillPaymentPayload, BillPaymentSchema, BillPaymentSummary, BillPayload, BillSchema, PaginatedBills
from app.services.billing import calculate_totals, generate_invoice_number, replace_bill_items

router = APIRouter(prefix="/bills", tags=["bills"])


def ensure_bill_write_access(db: Session, user: User) -> None:
    role = user.role.upper()
    if role == "SUPER_ADMIN":
        return

    if role == "ADMIN" and not user.company.is_active:
        raise HTTPException(
            status_code=403,
            detail="You don't have access to create user or report",
        )

    plan = get_plan(user.company.plan_code)
    bill_limit = plan["bill_limit"]
    if bill_limit is not None:
        bill_count = db.query(Bill.id).filter(Bill.company_id == user.company_id).count()
        if bill_count >= bill_limit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"{plan['name']} plan allows only {bill_limit} bills. "
                    "Upgrade plan to continue bill actions."
                ),
            )


def scoped_bill(db: Session, bill_id: int, company_id: int) -> Bill:
    bill = (
        db.query(Bill)
        .options(joinedload(Bill.customer), joinedload(Bill.items))
        .filter(Bill.id == bill_id, Bill.company_id == company_id)
        .first()
    )
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


def payment_summary_for_bill(db: Session, bill: Bill) -> BillPaymentSummary:
    payments = (
        db.query(BillPayment)
        .filter(BillPayment.bill_id == bill.id)
        .order_by(BillPayment.paid_on.desc(), BillPayment.id.desc())
        .all()
    )
    paid_total = float(sum(payment.amount for payment in payments))
    outstanding_total = float(max(bill.grand_total - paid_total, 0))
    return BillPaymentSummary(
        bill_id=bill.id,
        grand_total=float(bill.grand_total),
        paid_total=paid_total,
        outstanding_total=outstanding_total,
        fully_paid=outstanding_total <= 0,
        payments=[BillPaymentSchema.model_validate(payment) for payment in payments],
    )


@router.get("", response_model=PaginatedBills)
def list_bills(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = "",
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
    customer_id: int | None = None,
    sort_by: str = "invoice_date",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaginatedBills:
    query = db.query(Bill).options(joinedload(Bill.customer), joinedload(Bill.items)).join(Customer, isouter=True).filter(Bill.company_id == user.company_id)
    if search:
        term = f"%{search}%"
        query = query.filter(or_(Bill.invoice_number.ilike(term), Customer.name.ilike(term), Customer.phone.ilike(term)))
    if month:
        query = query.filter(extract("month", Bill.invoice_date) == month)
    if year:
        query = query.filter(extract("year", Bill.invoice_date) == year)
    if customer_id:
        query = query.filter(Bill.customer_id == customer_id)
    total = query.count()
    sort_column = getattr(Bill, sort_by, Bill.invoice_date)
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    items = query.offset((page - 1) * limit).limit(limit).all()
    return PaginatedBills(items=items, total=total, page=page, limit=limit)


@router.post("", response_model=BillSchema, status_code=201)
def create_bill(payload: BillPayload, db: Session = Depends(get_db), user: User = Depends(require_active_admin_company)) -> Bill:
    ensure_bill_write_access(db, user)
    customer = db.query(Customer).filter(Customer.id == payload.customer_id, Customer.company_id == user.company_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    try:
        totals = calculate_totals(payload.items, payload.transportation, payload.discount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    bill = Bill(
        company_id=user.company_id,
        invoice_number=payload.invoice_number or generate_invoice_number(db, user.company_id, payload.invoice_date),
        customer_id=payload.customer_id,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        transportation=payload.transportation,
        discount=payload.discount,
        status=payload.status,
        notes=payload.notes,
        **totals,
    )
    db.add(bill)

    replace_bill_items(db, bill, payload.items)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate invoice number") from exc
    return scoped_bill(db, bill.id, user.company_id)


@router.get("/{bill_id}", response_model=BillSchema)
def get_bill(bill_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Bill:
    return scoped_bill(db, bill_id, user.company_id)


@router.get("/{bill_id}/payments", response_model=BillPaymentSummary)
def get_bill_payments(
    bill_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BillPaymentSummary:
    bill = scoped_bill(db, bill_id, user.company_id)
    return payment_summary_for_bill(db, bill)


@router.post("/{bill_id}/payments", response_model=BillPaymentSummary, status_code=201)
def add_bill_payment(
    bill_id: int,
    payload: BillPaymentPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BillPaymentSummary:
    ensure_bill_write_access(db, user)
    bill = scoped_bill(db, bill_id, user.company_id)
    if bill.status == "Cancelled":
        raise HTTPException(status_code=400, detail="Cannot add payments for cancelled bills")

    summary_before = payment_summary_for_bill(db, bill)
    if summary_before.outstanding_total <= 0:
        raise HTTPException(status_code=400, detail="Bill is already fully paid")
    if payload.amount > summary_before.outstanding_total:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Payment exceeds outstanding amount ({summary_before.outstanding_total:.2f})."
            ),
        )

    payment = BillPayment(
        bill_id=bill.id,
        amount=payload.amount,
        paid_on=payload.paid_on,
        payment_method=payload.payment_method,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(payment)
    db.flush()

    updated_outstanding = max(summary_before.outstanding_total - payload.amount, 0)
    bill.status = "Paid" if updated_outstanding <= 0 else "Pending"

    db.commit()
    return payment_summary_for_bill(db, bill)


@router.put("/{bill_id}", response_model=BillSchema)
def update_bill(bill_id: int, payload: BillPayload, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Bill:
    ensure_bill_write_access(db, user)
    bill = scoped_bill(db, bill_id, user.company_id)
    customer = db.query(Customer).filter(Customer.id == payload.customer_id, Customer.company_id == user.company_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    totals = calculate_totals(payload.items, payload.transportation, payload.discount)
    for key, value in {
        "invoice_number": payload.invoice_number or bill.invoice_number,
        "customer_id": payload.customer_id,
        "invoice_date": payload.invoice_date,
        "due_date": payload.due_date,
        "transportation": payload.transportation,
        "discount": payload.discount,
        "status": payload.status,
        "notes": payload.notes,
        **totals,
    }.items():
        setattr(bill, key, value)
    replace_bill_items(db, bill, payload.items)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate invoice number") from exc
    return scoped_bill(db, bill.id, user.company_id)


@router.delete("/{bill_id}", status_code=204)
def delete_bill(bill_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    ensure_bill_write_access(db, user)
    bill = scoped_bill(db, bill_id, user.company_id)
    db.delete(bill)
    db.commit()
