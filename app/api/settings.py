from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.connection import get_db
from app.models import InvoiceSettings, User
from app.schemas import InvoiceSettingsSchema

router = APIRouter(prefix="/settings", tags=["settings"])


def get_or_create_settings(db: Session, user: User) -> InvoiceSettings:
    settings = db.query(InvoiceSettings).filter(InvoiceSettings.company_id == user.company_id).first()
    if settings:
        return settings
    settings = InvoiceSettings(
        company_id=user.company_id,
        company_name=user.company.name,
        address=user.company.address,
        phone=user.company.phone,
        email=user.company.email,
        gst_number=user.company.gst_number,
        invoice_prefix="INV",
        footer_text="Thank you for your business.",
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


@router.get("/invoice", response_model=InvoiceSettingsSchema)
def get_invoice_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InvoiceSettings:
    return get_or_create_settings(db, user)


@router.put("/invoice", response_model=InvoiceSettingsSchema)
def update_invoice_settings(payload: InvoiceSettingsSchema, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> InvoiceSettings:
    settings = get_or_create_settings(db, user)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings
