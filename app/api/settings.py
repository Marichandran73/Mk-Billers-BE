import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_active_admin_company, require_admin_or_super
from app.core.plans import get_plan, list_plans, normalize_plan_code
from app.database.connection import get_db
from app.models import Bill, Company, InvoiceSettings, User, UserInvoiceTemplate
from app.schemas import (
    CurrentPlanSchema,
    InvoiceSettingsSchema,
    PlanSchema,
    PlanSelectionPayload,
    PlanSelectionResponse,
    PlanUsageSchema,
    UserInvoiceTemplateSchema,
)

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
        invoice_template="template-1",
        footer_text="Thank you for your business.",
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def default_custom_template() -> UserInvoiceTemplateSchema:
    return UserInvoiceTemplateSchema(
        page_width=794,
        page_height=1123,
        background_image=None,
        background_fit="cover",
        background_x=50,
        background_y=50,
        background_zoom=100,
        background_opacity=1,
        fields=[
            {"key": "company_name", "label": "Company Name", "x": 40, "y": 40, "font_size": 24, "width": 320, "align": "left"},
            {"key": "company_address", "label": "Company Address", "x": 40, "y": 76, "font_size": 12, "width": 360, "align": "left"},
            {"key": "invoice_title", "label": "INVOICE", "x": 600, "y": 40, "font_size": 22, "width": 160, "align": "right"},
            {"key": "invoice_number", "label": "Invoice Number", "x": 560, "y": 76, "font_size": 12, "width": 200, "align": "right"},
            {"key": "invoice_date", "label": "Invoice Date", "x": 560, "y": 96, "font_size": 12, "width": 200, "align": "right"},
            {"key": "bill_to", "label": "Bill To", "x": 40, "y": 156, "font_size": 16, "width": 220, "align": "left"},
            {"key": "customer_name", "label": "Customer Name", "x": 40, "y": 182, "font_size": 14, "width": 320, "align": "left"},
            {"key": "customer_address", "label": "Customer Address", "x": 40, "y": 204, "font_size": 12, "width": 360, "align": "left"},
            {"key": "items_table", "label": "Items Table", "x": 40, "y": 280, "font_size": 11, "width": 714, "align": "left"},
            {"key": "total_label", "label": "Grand Total", "x": 560, "y": 760, "font_size": 13, "width": 120, "align": "left"},
            {"key": "grand_total", "label": "Amount", "x": 680, "y": 760, "font_size": 16, "width": 80, "align": "right"},
            {"key": "footer_text", "label": "Footer", "x": 40, "y": 1060, "font_size": 12, "width": 520, "align": "left"},
            {"key": "signature", "label": "Authorized Signature", "x": 580, "y": 1032, "font_size": 12, "width": 180, "align": "right"},
        ],
        images=[],
    )


def get_or_create_user_template(db: Session, user: User) -> UserInvoiceTemplate:
    template = (
        db.query(UserInvoiceTemplate)
        .filter(UserInvoiceTemplate.user_id == user.id)
        .first()
    )
    if template:
        return template
    defaults = default_custom_template()
    template = UserInvoiceTemplate(user_id=user.id, layout_json=json.dumps(defaults.model_dump()))
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def build_current_plan_response(db: Session, user: User) -> CurrentPlanSchema:
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    plan = get_plan(company.plan_code)
    bill_limit = plan["bill_limit"]
    user_limit = plan["user_limit"]

    bills_used = db.query(Bill.id).filter(Bill.company_id == user.company_id).count()
    users_used = db.query(User.id).filter(User.company_id == user.company_id, User.is_active.is_(True)).count()

    bill_usage_percent: float | None = None
    user_usage_percent: float | None = None
    if bill_limit and bill_limit > 0:
        bill_usage_percent = round(min(100.0, (bills_used / bill_limit) * 100), 2)
    if user_limit and user_limit > 0:
        user_usage_percent = round(min(100.0, (users_used / user_limit) * 100), 2)

    return CurrentPlanSchema(
        code=plan["code"],
        name=plan["name"],
        monthly_price_inr=plan["monthly_price_inr"],
        bill_limit=bill_limit,
        user_limit=user_limit,
        features=plan["features"],
        rules=plan["rules"],
        usage=PlanUsageSchema(
            bills_used=bills_used,
            users_used=users_used,
            bill_limit=bill_limit,
            user_limit=user_limit,
            bill_usage_percent=bill_usage_percent,
            user_usage_percent=user_usage_percent,
        ),
    )


@router.get("/plans", response_model=list[PlanSchema])
def get_plans(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[PlanSchema]:
    current_code = normalize_plan_code(user.company.plan_code)
    return [
        PlanSchema(
            code=plan["code"],
            name=plan["name"],
            monthly_price_inr=plan["monthly_price_inr"],
            bill_limit=plan["bill_limit"],
            user_limit=plan["user_limit"],
            features=plan["features"],
            rules=plan["rules"],
            current=plan["code"] == current_code,
        )
        for plan in list_plans()
    ]


@router.get("/plans/current", response_model=CurrentPlanSchema)
def get_current_plan(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> CurrentPlanSchema:
    return build_current_plan_response(db, user)


@router.put("/plans/current", response_model=PlanSelectionResponse)
def update_current_plan(
    payload: PlanSelectionPayload,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_super),
) -> PlanSelectionResponse:
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    company.plan_code = payload.code
    db.commit()
    db.refresh(company)

    return PlanSelectionResponse(
        message=f"Current plan updated to {get_plan(company.plan_code)['name']}",
        current_plan=build_current_plan_response(db, user),
    )


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


@router.get("/custom-template", response_model=UserInvoiceTemplateSchema)
def get_custom_template(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> UserInvoiceTemplateSchema:
    template = get_or_create_user_template(db, user)
    try:
        raw_payload = json.loads(template.layout_json)
    except json.JSONDecodeError:
        raw_payload = default_custom_template().model_dump()
    return UserInvoiceTemplateSchema(**raw_payload)


@router.put("/custom-template", response_model=UserInvoiceTemplateSchema)
def update_custom_template(
    payload: UserInvoiceTemplateSchema,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserInvoiceTemplateSchema:
    template = get_or_create_user_template(db, user)
    template.layout_json = json.dumps(payload.model_dump())
    db.commit()
    db.refresh(template)
    return payload
