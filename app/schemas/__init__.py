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
    company: CompanySchema


class LoginPayload(BaseModel):
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


class SuperAdminOverviewSchema(BaseModel):
    companies: list[CompanySummarySchema]
    customers: list[dict[str, int | str | None]]


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
        if value not in {"Paid", "Pending", "Cancelled"}:
            raise ValueError("Invalid bill status")
        return value


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
