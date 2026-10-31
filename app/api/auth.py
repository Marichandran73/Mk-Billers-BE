import logging
import secrets
import smtplib
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database.connection import get_db
from app.models import Bill, Company, Customer, InvoiceSettings, User, UserInvite
from app.core.plans import get_plan
from app.services.email_templates import EmailContext, EmailPurpose, list_templates_with_preview, render_email
from app.services.mailer import send_mail
from app.schemas import (
    AuthResponse,
    BootstrapPayload,
    CompanyAccessStatusPayload,
    CompanyAccessStatusResponse,
    CreateCompanyAccessPayload,
    EmailTemplateSchema,
    ForgotPasswordPayload,
    ForgotPasswordResponse,
    InviteUserPayload,
    InviteUserResponse,
    LoginPayload,
    RegisterPayload,
    RoleUpdatePayload,
    RoleUpdateResponse,
    SetupPasswordPayload,
    SuperAdminOverviewSchema,
    UserAccessStatusPayload,
    UserAccessStatusResponse,
    UserSchema,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _require_admin(user: User) -> None:
    if user.role.upper() not in {"ADMIN", "SUPER_ADMIN"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin users can perform this action")


def _require_super_admin(user: User) -> None:
    if user.role.upper() != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admin users can create companies")


def _setup_link(email: str, token: str) -> str:
    query = urlencode({"email": email, "token": token})
    return f"{settings.frontend_url.rstrip('/')}/set-password?{query}"


def _create_setup_token(db: Session, user: User) -> tuple[str, datetime]:
    now_utc = datetime.utcnow()
    db.query(UserInvite).filter(UserInvite.user_id == user.id, UserInvite.used_at.is_(None)).update(
        {UserInvite.used_at: now_utc}
    )

    expires_at = now_utc + timedelta(minutes=settings.invite_code_expire_minutes)
    for _ in range(5):
        setup_token = "".join(secrets.choice("0123456789") for _ in range(6))
        exists = db.query(UserInvite.id).filter(UserInvite.token == setup_token).first()
        if not exists:
            db.add(UserInvite(user_id=user.id, token=setup_token, expires_at=expires_at))
            return setup_token, expires_at
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to generate verification code")


def _send_otp_email(
    email: str,
    token: str,
    purpose: EmailPurpose,
    template_id: str | None,
    company_name: str = "MK-BILLERS",
    role: str | None = None,
    invited_by: str | None = None,
) -> tuple[bool, str | None]:
    """Returns (sent, error_message). error_message is None when sent or SMTP is not configured."""
    rendered = render_email(
        template_id,
        EmailContext(
            purpose=purpose,
            recipient=email,
            otp=token,
            setup_link=_setup_link(email, token),
            expires_minutes=settings.invite_code_expire_minutes,
            company_name=company_name,
            role=role,
            invited_by=invited_by,
        ),
    )
    try:
        sent = send_mail(
            recipient=email,
            subject=rendered.subject,
            body=rendered.text,
            html=rendered.html,
            inline_images=rendered.inline_images,
        )
        return sent, None if sent else "SMTP is not configured on the server."
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPServerDisconnected):
        # Gmail usually drops the connection (instead of returning 535) when the login itself is invalid.
        logger.exception("SMTP login failed while sending OTP to %s", email)
        return False, (
            "SMTP login failed. For Gmail, SMTP_USER must be the full Gmail address "
            "and SMTP_PASSWORD must be a 16-character App Password (not your normal Gmail password)."
        )
    except Exception as exc:
        logger.exception("Failed to send OTP email to %s", email)
        return False, f"Email could not be sent: {exc.__class__.__name__}: {exc}"


@router.get("/email-templates", response_model=list[EmailTemplateSchema])
def email_templates(
    purpose: EmailPurpose = "invite",
    current_user: User = Depends(get_current_user),
) -> list[dict[str, str]]:
    _require_admin(current_user)
    return list_templates_with_preview(purpose)


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


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterPayload, db: Session = Depends(get_db)) -> AuthResponse:
    existing_company = db.query(Company.id).filter(Company.email == payload.email).first()
    if existing_company:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company account already exists for this email")

    existing_user = db.query(User.id).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User account already exists for this email")

    company = Company(name=payload.company_name, email=payload.email)
    db.add(company)
    db.flush()

    user = User(
        company_id=company.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="STAFF",
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

    fresh_user = db.query(User).options(joinedload(User.company)).filter(User.id == user.id).first()
    if not fresh_user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user account")

    token = create_access_token(fresh_user.email, fresh_user.company_id)
    return AuthResponse(access_token=token, user=UserSchema.model_validate(fresh_user))


@router.post("/invite", response_model=InviteUserResponse)
def invite_user(
    payload: InviteUserPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InviteUserResponse:
    # Team invites are managed only by the MK-BILLERS super admin.
    if current_user.role.upper() != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admin can invite team members")

    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user and existing_user.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email already belongs to another company",
        )

    user = existing_user
    if not user:
        user_limit = get_plan(current_user.company.plan_code)["user_limit"]
        if current_user.role.upper() != "SUPER_ADMIN" and user_limit is not None:
            active_users = (
                db.query(User.id)
                .filter(User.company_id == current_user.company_id, User.is_active.is_(True))
                .count()
            )
            if active_users >= user_limit:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your plan allows only {user_limit} active user(s). Upgrade plan to invite more users.",
                )
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

    email_sent, email_error = _send_otp_email(
        user.email,
        invite_token,
        purpose="invite",
        template_id=payload.email_template,
        company_name=current_user.company.name,
        role=user.role,
        invited_by=current_user.email,
    )

    return InviteUserResponse(
        message=(
            "Invite sent. OTP has been emailed to the user."
            if email_sent
            else "User created, but the OTP email was not sent. Share the OTP below with the user."
        ),
        email=user.email,
        role=user.role,
        email_sent=email_sent,
        email_error=email_error,
        setup_link=None if email_sent else _setup_link(user.email, invite_token),
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

    # The OTP belongs to the admin login, so it goes to the admin email.
    email_sent, email_error = _send_otp_email(
        admin_user.email,
        verify_code,
        purpose="company",
        template_id=payload.email_template,
        company_name=company.name,
        role=admin_user.role,
    )

    return InviteUserResponse(
        message=(
            "Company created and OTP sent to the admin email."
            if email_sent
            else "Company created, but the OTP email was not sent. Share the OTP below with the admin."
        ),
        email=admin_user.email,
        role=admin_user.role,
        email_sent=email_sent,
        email_error=email_error,
        setup_link=None if email_sent else _setup_link(admin_user.email, verify_code),
        verification_code=None if email_sent else verify_code,
        expires_at=expires_at.isoformat(),
    )


@router.get("/companies/overview", response_model=SuperAdminOverviewSchema)
def companies_overview(
    user_search: str = "",
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
                "revenue": float(sum(bill.grand_total for bill in month_bills)),
            })
        summaries.append({
            "id": company.id,
            "name": company.name,
            "email": company.email,
            "is_active": company.is_active,
            "admin_email": admin[0] if admin else None,
            "customer_count": db.query(Customer.id).filter(Customer.company_id == company.id).count(),
            "bill_count": len(bills),
            "total_revenue": float(sum(bill.grand_total for bill in bills)),
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
    users_query = db.query(User).join(User.company)
    if user_search.strip():
        term = f"%{user_search.strip()}%"
        users_query = users_query.filter(
            or_(
                User.email.ilike(term),
                Company.name.ilike(term),
            )
        )
    users = [
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "company_id": user.company_id,
            "company_name": user.company.name,
            "is_active": user.is_active,
        }
        for user in users_query.order_by(User.email.asc()).all()
    ]
    return SuperAdminOverviewSchema(companies=summaries, customers=customers, users=users)


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


@router.patch("/users/{user_id}/role", response_model=RoleUpdateResponse)
def update_user_role(
    user_id: int,
    payload: RoleUpdatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoleUpdateResponse:
    _require_super_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Super admin cannot change own role")

    if user.role.upper() == "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change SUPER_ADMIN role")

    previous_role = user.role.upper()
    user.role = payload.role
    db.commit()
    db.refresh(user)

    return RoleUpdateResponse(
        user_id=user.id,
        email=user.email,
        previous_role=previous_role,
        current_role=user.role,
        message=f"Role updated from {previous_role} to {user.role}",
    )


@router.patch("/users/{user_id}/access", response_model=UserAccessStatusResponse)
def update_user_access_status(
    user_id: int,
    payload: UserAccessStatusPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserAccessStatusResponse:
    _require_super_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Super admin cannot deactivate own access")

    if user.role.upper() == "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change SUPER_ADMIN access")

    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)

    return UserAccessStatusResponse(
        user_id=user.id,
        email=user.email,
        is_active=user.is_active,
        message="User access activated" if user.is_active else "User access deactivated",
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="If this account does not exist, a password reset link has not been generated.",
        )

    reset_token, _ = _create_setup_token(db, user)
    db.commit()
    email_sent, _ = _send_otp_email(user.email, reset_token, purpose="reset", template_id=payload.email_template)
    if email_sent:
        return ForgotPasswordResponse(message="An OTP has been sent to your email.", email_sent=True)
    return ForgotPasswordResponse(
        message="Email could not be sent. Use the reset link below.",
        reset_link=_setup_link(user.email, reset_token),
    )


@router.post("/setup-password", response_model=AuthResponse)
def setup_password(payload: SetupPasswordPayload, db: Session = Depends(get_db)) -> AuthResponse:
    # The OTP must match the email it was issued for, so a guessed 6-digit code alone is not enough.
    invite = (
        db.query(UserInvite)
        .join(UserInvite.user)
        .options(joinedload(UserInvite.user).joinedload(User.company))
        .filter(
            UserInvite.token == payload.token.strip(),
            func.lower(User.email) == payload.email.lower(),
        )
        .first()
    )
    now_utc = datetime.utcnow()
    if not invite or invite.used_at is not None or invite.expires_at < now_utc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP is invalid or expired")

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
