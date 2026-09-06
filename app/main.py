from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.api import auth, bills, company, customers, dashboard, reports, settings as invoice_settings
from app.core.config import settings
from app.core.security import hash_password
from app.database.connection import Base, SessionLocal, engine
from app.models import Company, Customer, InvoiceSettings, User

app = FastAPI(title="Mk-BILLS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(company.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(bills.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(invoice_settings.router, prefix="/api")


def ensure_schema_updates() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        company_columns = {column["name"] for column in inspector.get_columns("companies")}
        if "is_active" not in company_columns:
            if engine.dialect.name == "sqlite":
                connection.execute(text("ALTER TABLE companies ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
            else:
                connection.execute(text("ALTER TABLE companies ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))


def seed_default_company(db: Session) -> None:
    if not settings.seed_admin_email or not settings.seed_admin_password:
        return

    existing = db.query(User).filter(User.email == settings.seed_admin_email).first()
    if existing:
        return

    company = db.query(Company).filter(Company.email == settings.seed_admin_email).first()
    if not company:
        company = Company(
            name=settings.seed_company_name,
            email=settings.seed_admin_email,
            phone=settings.seed_company_phone,
            address=settings.seed_company_address,
            gst_number=settings.seed_company_gst_number,
        )
        db.add(company)
        db.flush()

    db.add(
        User(
            company_id=company.id,
            email=settings.seed_admin_email,
            password_hash=hash_password(settings.seed_admin_password),
            role="SUPER_ADMIN",
        )
    )
    invoice_settings = db.query(InvoiceSettings).filter(InvoiceSettings.company_id == company.id).first()
    if not invoice_settings:
        db.add(
            InvoiceSettings(
                company_id=company.id,
                company_name=company.name,
                address=company.address,
                phone=company.phone,
                email=company.email,
                gst_number=company.gst_number,
                upi_id="febills@upi",
                bank_details="Bank: Example Bank\nAccount: 1234567890\nIFSC: EXAM0001234",
                invoice_prefix="INV",
                footer_text="Thank you for your business.",
            )
        )
    sample_customer = db.query(Customer).filter(
        Customer.company_id == company.id,
        Customer.phone == "9000000001",
    ).first()
    if not sample_customer:
        db.add(
            Customer(
                company_id=company.id,
                name="Aarav Traders",
                company_name="Aarav Traders Pvt Ltd",
                phone="9000000001",
                email="billing@aarav.example",
                address="MG Road, Bengaluru",
                gst_number="29AAACA1111A1Z1",
                city="Bengaluru",
                state="Karnataka",
                pincode="560001",
            )
        )
    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_updates()
    db = SessionLocal()
    try:
        seed_default_company(db)
    finally:
        db.close()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
