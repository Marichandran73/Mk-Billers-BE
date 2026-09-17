from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.bills import list_bills
from app.api.deps import require_admin_or_super
from app.database.connection import get_db
from app.models import User
from app.schemas import PaginatedBills

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/bills", response_model=PaginatedBills)
def bill_report(
    month: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_super),
) -> PaginatedBills:
    return list_bills(page=1, limit=100, month=month, year=year, db=db, user=user)


@router.get("/bills/export", response_model=PaginatedBills)
def bill_export(
    month: int | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_super),
) -> PaginatedBills:
    return list_bills(page=1, limit=100, month=month, year=year, db=db, user=user)
