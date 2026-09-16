from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin_or_super
from app.database.connection import get_db
from app.models import Customer, User
from app.schemas import CustomerPayload, CustomerSchema

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerSchema])
def list_customers(search: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[Customer]:
    query = db.query(Customer).filter(Customer.company_id == user.company_id)
    if search:
        term = f"%{search}%"
        query = query.filter(or_(Customer.name.ilike(term), Customer.phone.ilike(term), Customer.company_name.ilike(term)))
    return query.order_by(Customer.name.asc()).all()


@router.post("", response_model=CustomerSchema, status_code=201)
def create_customer(
    payload: CustomerPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_super),
) -> Customer:
    customer = Customer(company_id=user.company_id, **payload.model_dump())
    db.add(customer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate customer") from exc
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerSchema)
def get_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.company_id == user.company_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.put("/{customer_id}", response_model=CustomerSchema)
def update_customer(customer_id: int, payload: CustomerPayload, db: Session = Depends(get_db), user: User = Depends(require_admin_or_super)) -> Customer:
    customer = get_customer(customer_id, db, user)
    for key, value in payload.model_dump().items():
        setattr(customer, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate customer") from exc
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin_or_super)) -> None:
    customer = get_customer(customer_id, db, user)
    db.delete(customer)
    db.commit()
