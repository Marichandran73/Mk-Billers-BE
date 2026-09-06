from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class BillStatus(str, Enum):
    paid = "Paid"
    pending = "Pending"
    cancelled = "Cancelled"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    gst_number: Mapped[str | None] = mapped_column(String(40))
    logo: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    customers: Mapped[list["Customer"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    bills: Mapped[list["Bill"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    invoice_settings: Mapped["InvoiceSettings"] = relationship(back_populates="company", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="ADMIN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    company: Mapped[Company] = relationship(back_populates="users")
    invites: Mapped[list["UserInvite"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserInvite(Base):
    __tablename__ = "user_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="invites")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("company_id", "phone", name="uq_customer_company_phone"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text)
    gst_number: Mapped[str | None] = mapped_column(String(40))
    city: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    pincode: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    company: Mapped[Company] = relationship(back_populates="customers")
    bills: Mapped[list["Bill"]] = relationship(back_populates="customer")


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (UniqueConstraint("company_id", "invoice_number", name="uq_bill_company_invoice"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    subtotal: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    cgst: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    sgst: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    transportation: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    grand_total: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=BillStatus.pending.value, index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    company: Mapped[Company] = relationship(back_populates="bills")
    customer: Mapped[Customer | None] = relationship(back_populates="bills")
    items: Mapped[list["BillItem"]] = relationship(back_populates="bill", cascade="all, delete-orphan")


class BillItem(Base):
    __tablename__ = "bill_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), default="Nos", nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    gst_percent: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    bill: Mapped[Bill] = relationship(back_populates="items")


class InvoiceSettings(Base):
    __tablename__ = "invoice_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True, index=True, nullable=False)
    logo: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    gst_number: Mapped[str | None] = mapped_column(String(40))
    upi_id: Mapped[str | None] = mapped_column(String(120))
    bank_details: Mapped[str | None] = mapped_column(Text)
    signature: Mapped[str | None] = mapped_column(Text)
    footer_text: Mapped[str | None] = mapped_column(Text)
    invoice_prefix: Mapped[str] = mapped_column(String(12), default="INV", nullable=False)

    company: Mapped[Company] = relationship(back_populates="invoice_settings")
