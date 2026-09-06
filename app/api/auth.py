import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract, func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database.connection import get_db
from app.models import Bill, Company, Customer, InvoiceSettings, User, UserInvite
from app.services.mailer import send_mail
from app.schemas import (
    AuthResponse,
    BootstrapPayload,
    CompanyAccessStatusPayload,
    CompanyAccessStatusResponse,
    CreateCompanyAccessPayload,
    ForgotPasswordPayload,
    ForgotPasswordResponse,
    InviteUserPayload,
    InviteUserResponse,
    LoginPayload,
    SetupPasswordPayload,
    SuperAdminOverviewSchema,
    UserSchema,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _require_admin(user: User) -> None:
    if user.role.upper() != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin users can perform this action")


def _require_super_admin(user: User) -> None:
    if user.role.upper() != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admin users can create companies")


def _setup_link(token: str) -> str:
    base_url = settings.cors_origin_list[0] if settings.cors_origin_list else "http://localhost:5173"
    return f"{base_url}/set-password?token={token}"


def _create_setup_token(db: Session, user: User) -> tuple[str, datetime]:
    now_utc = datetime.utcnow()
    db.query(UserInvite).filter(UserInvite.user_id == user.id, UserInvite.used_at.is_(None)).update(
        {UserInvite.used_at: now_utc}
    )

    expires_at = now_utc + timedelta(minutes=20)
    for _ in range(5):
        setup_token = "".join(secrets.choice("0123456789") for _ in range(6))
        exists = db.query(UserInvite.id).filter(UserInvite.token == setup_token).first()
        if not exists:
            db.add(UserInvite(user_id=user.id, token=setup_token, expires_at=expires_at))
            return setup_token, expires_at
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to generate verification code")


def _send_setup_email(email: str, token: str, expires_at: datetime) -> bool:
    setup_link = _setup_link(token)
    try:
        return send_mail(
            recipient=email,
            subject="Your MK-BILLERS verification code",
            body=(
                "Hello,\n\n"
                f"Use this verification code to set your password: {token}\n"
                f"Or open this link: {setup_link}\n\n"
                f"This code expires at {expires_at.isoformat()} UTC."
            ),
        )
    except Exception:
        return False


@router.post("/bootstrap", response_model=AuthResponse)
def bootstrap(payload: BootstrapPayload, db: Session = Depends(get_db)) -> AuthResponse:
    has_users = db.query(User.id).first()
    if has_users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap is disabled because users already exist. Use invite flow instead.",
        )

    company = Company(name=payload.company_name, email=payload.company_email)
    db.add(company)
    db.flush()

    user = User(
        company_id=company.id,
        email=payload.admin_email,
        password_hash=hash_password(payload.admin_password),
        role="SUPER_ADMIN",
    )
    db.add(user)

    db.add(
        InvoiceSettings(
            company_id=company.id,
            company_name=company.name,
            email=company.email,
            invoice_prefix="INV",
            footer_text="Thank you for your business.",
        )
    )
    db.commit()

    user = db.query(User).options(joinedload(User.company)).filter(User.id == user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create admin user")
    token = create_access_token(user.email, user.company_id)
    return AuthResponse(access_token=token, user=UserSchema.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginPayload, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.query(User).options(joinedload(User.company)).filter(User.email == payload.email).first()
    print("user=====>", user)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.email, user.company_id)
    return AuthResponse(access_token=token, user=UserSchema.model_validate(user))


@router.post("/invite", response_model=InviteUserResponse)
def invite_user(
    payload: InviteUserPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InviteUserResponse:
    _require_admin(current_user)

    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user and existing_user.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email already belongs to another company",
        )

    user = existing_user
    if not user:
        user = User(
            company_id=current_user.company_id,
            email=payload.email,
            role=payload.role,
            # Temporary random hash; user must set a real password via invite link.
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.flush()
    else:
        user.role = payload.role

    invite_token, expires_at = _create_setup_token(db, user)
    db.commit()

    setup_link = _setup_link(invite_token)
    email_sent = _send_setup_email(user.email, invite_token, expires_at)

    return InviteUserResponse(
        message=(
            "Access granted. Verification code has been sent to user email."
            if email_sent
            else "Access granted. Email is not configured, use the code below to set password."
        ),
        email=user.email,
        role=user.role,
        setup_link=None if email_sent else setup_link,
        verification_code=None if email_sent else invite_token,
        expires_at=expires_at.isoformat(),
    )


@router.post("/company-access", response_model=InviteUserResponse, status_code=status.HTTP_201_CREATED)
def create_company_access(
    payload: CreateCompanyAccessPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InviteUserResponse:
    _require_super_admin(current_user)

    existing_company = db.query(Company.id).filter(Company.email == payload.company_email).first()
    if existing_company:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company email already exists")

    existing_user = db.query(User.id).filter(User.email == payload.admin_email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin email already exists")

    company = Company(name=payload.company_name, email=payload.company_email)
    db.add(company)
    db.flush()

    admin_user = User(
        company_id=company.id,
        email=payload.admin_email,
        role="ADMIN",
        password_hash=hash_password(secrets.token_urlsafe(32)),
    )
    db.add(admin_user)
    db.flush()
    db.add(
        InvoiceSettings(
            company_id=company.id,
            company_name=company.name,
            email=company.email,
            invoice_prefix="INV",
            footer_text="Thank you for your business.",
        )
    )

    verify_code, expires_at = _create_setup_token(db, admin_user)
    db.commit()

    setup_link = _setup_link(verify_code)
    email_sent = _send_setup_email(company.email, verify_code, expires_at)

    return InviteUserResponse(
        message=(
            "Company created and verification code sent to company email."
            if email_sent
            else "Company created. Email is not configured, use the code below to set password."
        ),
        email=company.email,
        role=admin_user.role,
        setup_link=None if email_sent else setup_link,
        verification_code=None if email_sent else verify_code,
        expires_at=expires_at.isoformat(),
    )


@router.get("/companies/overview", response_model=SuperAdminOverviewSchema)
def companies_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SuperAdminOverviewSchema:
    _require_super_admin(current_user)
    companies = db.query(Company).order_by(Company.name.asc()).all()
    summaries = []
    for company in companies:
        admin = (
            db.query(User.email)
            .filter(User.company_id == company.id, User.role == "ADMIN")
            .order_by(User.id.asc())
            .first()
        )
        bills = db.query(Bill).filter(Bill.company_id == company.id).all()
        monthly_bills = []
        for month in range(1, 13):
            month_bills = [
                bill for bill in bills
                if bill.invoice_date and bill.invoice_date.month == month
            ]
            monthly_bills.append({
                "month": datetime(2000, month, 1).strftime("%B"),
                "bill_count": len(month_bills),
                "revenue": float(sum(
                    bill.grand_total for bill in month_bills
                    if bill.status != "Cancelled"
                )),
            })
        summaries.append({
            "id": company.id,
            "name": company.name,
            "email": company.email,
            "is_active": company.is_active,
            "admin_email": admin[0] if admin else None,
            "customer_count": db.query(Customer.id).filter(Customer.company_id == company.id).count(),
            "bill_count": len(bills),
            "total_revenue": float(sum(
                bill.grand_total for bill in bills if bill.status != "Cancelled"
            )),
            "monthly_bills": monthly_bills,
        })
    customers = [
        {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "company_id": customer.company_id,
            "company_name": customer.company.name,
        }
        for customer in db.query(Customer).join(Customer.company).order_by(Customer.name.asc()).all()
    ]
    return SuperAdminOverviewSchema(companies=summaries, customers=customers)


@router.patch("/company-access/{company_id}/status", response_model=CompanyAccessStatusResponse)
def update_company_access_status(
    company_id: int,
    payload: CompanyAccessStatusPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CompanyAccessStatusResponse:
    _require_super_admin(current_user)
    if company_id == current_user.company_id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate the current Super Admin company",
        )

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    company.is_active = payload.is_active
    db.commit()
    db.refresh(company)
    return CompanyAccessStatusResponse(
        company_id=company.id,
        is_active=company.is_active,
        message="Company access activated" if company.is_active else "Company access deactivated",
    )


@router.delete("/company-access/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company_access(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    _require_super_admin(current_user)
    if company_id == current_user.company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the current Super Admin company")
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    db.delete(company)
    db.commit()


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordPayload, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        return ForgotPasswordResponse(
            message="If this account exists, a password reset link has been generated.",
        )

    reset_token, _ = _create_setup_token(db, user)
    db.commit()
    return ForgotPasswordResponse(
        message="If this account exists, a password reset link has been generated.",
        # In production, email this link and avoid returning it in API responses.
        reset_link=_setup_link(reset_token),
    )


@router.post("/setup-password", response_model=AuthResponse)
def setup_password(payload: SetupPasswordPayload, db: Session = Depends(get_db)) -> AuthResponse:
    invite = (
        db.query(UserInvite)
        .options(joinedload(UserInvite.user).joinedload(User.company))
        .filter(UserInvite.token == payload.token)
        .first()
    )
    now_utc = datetime.utcnow()
    if not invite or invite.used_at is not None or invite.expires_at < now_utc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite link is invalid or expired")

    user = invite.user
    user.password_hash = hash_password(payload.password)
    invite.used_at = now_utc
    db.commit()

    token = create_access_token(user.email, user.company_id)
    return AuthResponse(access_token=token, user=UserSchema.model_validate(user))


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"message": "Logged out scuccessfully."}


@router.get("/me", response_model=UserSchema)
def me(user: User = Depends(get_current_user)) -> User:
    return user
