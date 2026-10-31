from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.connection import get_db
from app.models import Founder, User
from app.schemas import FounderPayload, FounderSchema

router = APIRouter(prefix="/founders", tags=["founders"])


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role.upper() != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admin can manage founders")
    return user


def get_founder_or_404(founder_id: int, db: Session) -> Founder:
    founder = db.query(Founder).filter(Founder.id == founder_id).first()
    if not founder:
        raise HTTPException(status_code=404, detail="Founder not found")
    return founder


@router.get("", response_model=list[FounderSchema])
def list_founders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Founder]:
    return db.query(Founder).order_by(Founder.sort_order.asc(), Founder.id.asc()).all()


@router.post("", response_model=FounderSchema, status_code=status.HTTP_201_CREATED)
def create_founder(
    payload: FounderPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_admin),
) -> Founder:
    founder = Founder(**payload.model_dump())
    db.add(founder)
    db.commit()
    db.refresh(founder)
    return founder


@router.put("/{founder_id}", response_model=FounderSchema)
def update_founder(
    founder_id: int,
    payload: FounderPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_admin),
) -> Founder:
    founder = get_founder_or_404(founder_id, db)
    for key, value in payload.model_dump().items():
        setattr(founder, key, value)
    db.commit()
    db.refresh(founder)
    return founder


@router.delete("/{founder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_founder(
    founder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_admin),
) -> None:
    founder = get_founder_or_404(founder_id, db)
    db.delete(founder)
    db.commit()
