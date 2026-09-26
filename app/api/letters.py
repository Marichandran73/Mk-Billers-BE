from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, require_active_admin_company
from app.database.connection import get_db
from app.models import Customer, LetterPad, User
from app.schemas import LetterPadPayload, LetterPadSchema

router = APIRouter(prefix="/letters", tags=["letters"])


def get_letter_or_404(letter_id: int, db: Session, user: User) -> LetterPad:
    letter = (
        db.query(LetterPad)
        .options(joinedload(LetterPad.customer))
        .filter(LetterPad.id == letter_id, LetterPad.company_id == user.company_id)
        .first()
    )
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    return letter


def ensure_customer_in_company(customer_id: int | None, db: Session, user: User) -> None:
    if customer_id is None:
        return
    exists = (
        db.query(Customer.id)
        .filter(Customer.id == customer_id, Customer.company_id == user.company_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Customer not found")


@router.get("", response_model=list[LetterPadSchema])
def list_letters(
    search: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[LetterPad]:
    query = (
        db.query(LetterPad)
        .options(joinedload(LetterPad.customer))
        .filter(LetterPad.company_id == user.company_id)
    )
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                LetterPad.title.ilike(term),
                LetterPad.subject.ilike(term),
                LetterPad.content.ilike(term),
            )
        )
    return query.order_by(LetterPad.updated_at.desc()).all()


@router.post("", response_model=LetterPadSchema, status_code=status.HTTP_201_CREATED)
def create_letter(
    payload: LetterPadPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_active_admin_company),
) -> LetterPad:
    ensure_customer_in_company(payload.customer_id, db, user)
    letter = LetterPad(company_id=user.company_id, **payload.model_dump())
    db.add(letter)
    db.commit()
    return get_letter_or_404(letter.id, db, user)


@router.get("/{letter_id}", response_model=LetterPadSchema)
def get_letter(
    letter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LetterPad:
    return get_letter_or_404(letter_id, db, user)


@router.put("/{letter_id}", response_model=LetterPadSchema)
def update_letter(
    letter_id: int,
    payload: LetterPadPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_active_admin_company),
) -> LetterPad:
    ensure_customer_in_company(payload.customer_id, db, user)
    letter = get_letter_or_404(letter_id, db, user)
    for key, value in payload.model_dump().items():
        setattr(letter, key, value)
    db.commit()
    return get_letter_or_404(letter.id, db, user)


@router.delete("/{letter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_letter(
    letter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_active_admin_company),
) -> None:
    letter = get_letter_or_404(letter_id, db, user)
    db.delete(letter)
    db.commit()
