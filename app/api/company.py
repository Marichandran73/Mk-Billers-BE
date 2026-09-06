from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.connection import get_db
from app.models import Company, User
from app.schemas import CompanySchema, CompanyUpdate

router = APIRouter(prefix="/company", tags=["company"])


@router.get("", response_model=CompanySchema)
def get_company(user: User = Depends(get_current_user)) -> Company:
    return user.company


@router.put("", response_model=CompanySchema)
def update_company(payload: CompanyUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Company:
    company = user.company
    for key, value in payload.model_dump().items():
        setattr(company, key, value)
    db.commit()
    db.refresh(company)
    return company
