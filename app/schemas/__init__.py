import re
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CompanySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    phone: str | None = None
    address: str | None = None
    gst_number: str | None = None
    logo: str | None = None
    is_active: bool = True


class CompanyUpdate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    address: str | None = None
    gst_number: str | None = None
    logo: str | None = None


class UserSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    email: EmailStr
    role: str
    is_active: bool = True
    company: CompanySchema


class LoginPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterPayload(BaseModel):
    company_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=8)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSchema


class BootstrapPayload(BaseModel):
    company_name: str = Field(min_length=2, max_length=160)
    company_email: EmailStr
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)


class InviteUserPayload(BaseModel):
    email: EmailStr
    role: str = "STAFF"

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        role = value.strip().upper()
        if role not in {"ADMIN", "STAFF"}:
            raise ValueError("Role must be ADMIN or STAFF")
        return role


class CreateCompanyAccessPayload(BaseModel):
    company_name: str = Field(min_length=2, max_length=160)
    company_email: EmailStr
    admin_email: EmailStr


class InviteUserResponse(BaseModel):
    message: str
    email: EmailStr
    role: str
    setup_link: str | None = None
    verification_code: str | None = None
    expires_at: str


class CompanySummarySchema(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_active: bool
    admin_email: EmailStr | None = None
    customer_count: int
    bill_count: int
    total_revenue: float
    monthly_bills: list[dict[str, int | str | float]]


class CompanyAccessStatusPayload(BaseModel):
    is_active: bool


class CompanyAccessStatusResponse(BaseModel):
    company_id: int
    is_active: bool
    message: str


class RoleUpdatePayload(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        role = value.strip().upper()
        if role not in {"ADMIN", "STAFF"}:
            raise ValueError("Role must be ADMIN or STAFF")
        return role


class RoleUpdateResponse(BaseModel):
    user_id: int
    email: EmailStr
    previous_role: str
    current_role: str
    message: str


class UserAccessStatusPayload(BaseModel):
    is_active: bool


class UserAccessStatusResponse(BaseModel):
    user_id: int
    email: EmailStr
    is_active: bool
    message: str


class SuperAdminOverviewSchema(BaseModel):
    companies: list[CompanySummarySchema]
    customers: list[dict[str, int | str | None]]
    users: list[dict[str, int | str | bool | None]]


class SetupPasswordPayload(BaseModel):
    token: str = Field(min_length=6)
    password: str = Field(min_length=8)


class ForgotPasswordPayload(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_link: str | None = None


class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    company_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    gst_number: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None


class CustomerPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    company_name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    phone: str = Field(min_length=1, max_length=40)
    address: str = Field(min_length=1, max_length=500)
    gst_number: str = Field(min_length=1, max_length=40)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    pincode: str = Field(min_length=1, max_length=20)

    @field_validator(
        "name",
        "company_name",
        "phone",
        "address",
        "gst_number",
        "city",
        "state",
        "pincode",
        mode="before",
    )
    @classmethod
    def required_non_blank_fields(cls, value: str) -> str:
        if value is None:
            raise ValueError("Field is required")
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("Field is required")
        return cleaned

    @field_validator("name", "company_name", "city", "state")
    @classmethod
    def alpha_fields(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", value):
            raise ValueError("Only letters, spaces, dot, apostrophe and hyphen are allowed")
        return value

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{10}", value):
            raise ValueError("Phone number must be exactly 10 digits")
        return value

    @field_validator("gst_number")
    @classmethod
    def valid_gst(cls, value: str) -> str:
        gst = value.upper()
        if not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]", gst):
            raise ValueError("GST number format is invalid")
        return gst

    @field_validator("pincode")
    @classmethod
    def valid_pincode(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{6}", value):
            raise ValueError("Pincode must be exactly 6 digits")
        return value


class CustomerSchema(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BillItemPayload(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    quantity: float = Field(gt=0)
    unit: str = "Nos"
    rate: float = Field(ge=0)
    gst_percent: float = Field(ge=0, le=100)


class BillItemSchema(BillItemPayload):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: float


class BillPayload(BaseModel):
    invoice_number: str | None = None
    customer_id: int
    invoice_date: date
    due_date: date | None = None
    transportation: float = Field(ge=0, default=0)
    discount: float = Field(ge=0, default=0)
    status: str = "Pending"
    notes: str | None = None
    items: list[BillItemPayload] = Field(min_length=1)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        status = value.strip().upper()
        if status == "DONE":
            return "Paid"
        if status == "PAID":
            return "Paid"
        if status == "PENDING":
            return "Pending"
        if status == "CANCELLED":
            return "Cancelled"
        raise ValueError("Status must be Pending, Done, or Cancelled")


class BillSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_number: str
    customer_id: int | None
    customer: CustomerSchema | None = None
    invoice_date: date
    due_date: date | None = None
    subtotal: float
    cgst: float
    sgst: float
    transportation: float
    discount: float
    grand_total: float
    status: str
    notes: str | None = None
    items: list[BillItemSchema]


class PaginatedBills(BaseModel):
    items: list[BillSchema]
    total: int
    page: int
    limit: int


class InvoiceSettingsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    logo: str | None = None
    company_name: str
    address: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    gst_number: str | None = None
    upi_id: str | None = None
    bank_details: str | None = None
    signature: str | None = None
    footer_text: str | None = None
    invoice_prefix: str = "INV"


class DashboardStats(BaseModel):
    total_bills: int
    total_revenue: float
    total_customers: int
    this_month_revenue: float
    monthly_revenue: list[dict[str, str | float]]
    recent_bills: list[BillSchema]
    recent_customers: list[CustomerSchema]
    pending_total: float
