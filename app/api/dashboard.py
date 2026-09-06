from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.database.connection import get_db
from app.models import Bill, Customer, User
from app.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> DashboardStats:
    today = date.today()
    bill_query = db.query(Bill).filter(Bill.company_id == user.company_id)
    total_bills = bill_query.count()
    total_revenue = bill_query.filter(Bill.status != "Cancelled").with_entities(func.coalesce(func.sum(Bill.grand_total), 0)).scalar()
    pending_total = bill_query.filter(Bill.status == "Pending").with_entities(func.coalesce(func.sum(Bill.grand_total), 0)).scalar()
    this_month_revenue = (
        bill_query.filter(extract("month", Bill.invoice_date) == today.month, extract("year", Bill.invoice_date) == today.year, Bill.status != "Cancelled")
        .with_entities(func.coalesce(func.sum(Bill.grand_total), 0))
        .scalar()
    )
    total_customers = db.query(Customer).filter(Customer.company_id == user.company_id).count()
    month_names = ["January", "February", "March", "April", "May", "June", "July", "August"]
    monthly_revenue = []
    for index, name in enumerate(month_names, start=1):
        revenue = (
            bill_query.filter(extract("month", Bill.invoice_date) == index, extract("year", Bill.invoice_date) == today.year, Bill.status != "Cancelled")
            .with_entities(func.coalesce(func.sum(Bill.grand_total), 0))
            .scalar()
        )
        monthly_revenue.append({"month": name, "revenue": float(revenue or 0)})
    recent_bills = (
        bill_query.options(joinedload(Bill.customer), joinedload(Bill.items))
        .order_by(Bill.created_at.desc())
        .limit(5)
        .all()
    )
    recent_customers = db.query(Customer).filter(Customer.company_id == user.company_id).order_by(Customer.created_at.desc()).limit(5).all()
    return DashboardStats(
        total_bills=total_bills,
        total_revenue=float(total_revenue or 0),
        total_customers=total_customers,
        this_month_revenue=float(this_month_revenue or 0),
        monthly_revenue=monthly_revenue,
        recent_bills=recent_bills,
        recent_customers=recent_customers,
        pending_total=float(pending_total or 0),
    )
