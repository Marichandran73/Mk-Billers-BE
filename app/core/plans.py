from typing import TypedDict


DEFAULT_PLAN_CODE = "FREE"


class PlanDefinition(TypedDict):
    code: str
    name: str
    monthly_price_inr: int
    bill_limit: int | None
    user_limit: int | None
    features: list[str]
    rules: list[str]


PLAN_DEFINITIONS: tuple[PlanDefinition, ...] = (
    {
        "code": "FREE",
        "name": "Free",
        "monthly_price_inr": 0,
        "bill_limit": 6,
        "user_limit": 1,
        "features": [
            "6 invoices total",
            "1 active user",
            "GST calculation",
            "Invoice sharing",
            "Customer management",
            "Basic reports",
            "Email support",
        ],
        "rules": [
            "All limits are company-level.",
            "When the bill cap is reached, create/edit/delete bill actions are blocked.",
            "Only ADMIN and SUPER_ADMIN can switch plans.",
        ],
    },
    {
        "code": "PRO",
        "name": "Pro",
        "monthly_price_inr": 699,
        "bill_limit": 200,
        "user_limit": 3,
        "features": [
            "200 invoices total",
            "Up to 3 active users",
            "E-Invoice",
            "E-Way Bill",
            "GST filing",
            "Standard reports",
            "Email and chat support",
        ],
        "rules": [
            "All limits are company-level.",
            "When the bill cap is reached, create/edit/delete bill actions are blocked.",
            "Only ADMIN and SUPER_ADMIN can switch plans.",
        ],
    },
    {
        "code": "PREMIUM",
        "name": "Premium",
        "monthly_price_inr": 999,
        "bill_limit": 500,
        "user_limit": 8,
        "features": [
            "500 invoices total",
            "Up to 8 active users",
            "All Pro features",
            "Bank reconciliation",
            "Accounting automation",
            "Advanced dashboard",
            "Priority support",
        ],
        "rules": [
            "All limits are company-level.",
            "When the bill cap is reached, create/edit/delete bill actions are blocked.",
            "Only ADMIN and SUPER_ADMIN can switch plans.",
        ],
    },
    {
        "code": "BUSINESS",
        "name": "Business",
        "monthly_price_inr": 1299,
        "bill_limit": None,
        "user_limit": 20,
        "features": [
            "Unlimited invoices",
            "Up to 20 active users",
            "Advanced reconciliation",
            "Advanced automation",
            "Full API access",
            "Custom reports",
            "Dedicated account manager",
        ],
        "rules": [
            "User limit remains enforced at company-level.",
            "No invoice count limit for this plan.",
            "Only ADMIN and SUPER_ADMIN can switch plans.",
        ],
    },
)

PLAN_BY_CODE: dict[str, PlanDefinition] = {plan["code"]: plan for plan in PLAN_DEFINITIONS}


def normalize_plan_code(plan_code: str | None) -> str:
    normalized = (plan_code or DEFAULT_PLAN_CODE).strip().upper()
    if normalized not in PLAN_BY_CODE:
        return DEFAULT_PLAN_CODE
    return normalized


def get_plan(plan_code: str | None) -> PlanDefinition:
    return PLAN_BY_CODE[normalize_plan_code(plan_code)]


def list_plans() -> list[PlanDefinition]:
    return [dict(plan) for plan in PLAN_DEFINITIONS]
