from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_active_admin_company
from app.database.connection import get_db
from app.models import Company, InvoiceSettings, User
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
def update_invoice_settings(payload: InvoiceSettingsSchema, db: Session = Depends(get_db), user: User = Depends(require_active_admin_company)) -> InvoiceSettings:
    settings = get_or_create_settings(db, user)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)

    company_updates: dict[str, str | None] = {
        "name": payload.company_name,
        "phone": payload.phone,
        "address": payload.address,
        "gst_number": payload.gst_number,
        "logo": payload.logo,
    }
    if payload.email:
        company_updates["email"] = payload.email

    db.query(Company).filter(Company.id == user.company_id).update(company_updates)

    db.commit()
    db.refresh(settings)
    return settings
