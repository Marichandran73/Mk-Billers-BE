import base64
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Callable, Literal

EmailPurpose = Literal["invite", "company", "reset"]

DEFAULT_EMAIL_TEMPLATE = "classic"

LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "mk-logo.png"
LOGO_CID = "mk-billers-logo"


@lru_cache(maxsize=1)
def _logo_bytes() -> bytes | None:
    return LOGO_PATH.read_bytes() if LOGO_PATH.exists() else None


def _logo_data_uri() -> str:
    data = _logo_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode()}" if data else ""


def _logo_img(src: str, size: int, extra_style: str = "") -> str:
    if not src:
        return ""
    return (
        f'<img src="{src}" width="{size}" height="{size}" alt="MK-BILLERS" '
        f'style="display:block;width:{size}px;height:{size}px;border:0;border-radius:50%;{extra_style}">'
    )


@dataclass(frozen=True)
class EmailContext:
    purpose: EmailPurpose
    recipient: str
    otp: str
    setup_link: str
    expires_minutes: int
    company_name: str = "MK-BILLERS"
    role: str | None = None
    invited_by: str | None = None


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str
    # Content-ID -> PNG bytes, embedded in the email so the logo shows without remote images.
    inline_images: dict[str, bytes] = field(default_factory=dict)


def _copy(ctx: EmailContext) -> dict[str, str]:
    company = escape(ctx.company_name)
    role = escape((ctx.role or "STAFF").title())
    if ctx.purpose == "reset":
        return {
            "subject": "Your MK-BILLERS password reset OTP",
            "heading": "Reset your password",
            "intro": "We received a request to reset your MK-BILLERS password. Use the OTP below to set a new one.",
            "button": "Reset Password",
        }
    if ctx.purpose == "company":
        return {
            "subject": f"Welcome to MK-BILLERS - {ctx.company_name} workspace is ready",
            "heading": "Your company workspace is ready",
            "intro": f"A new MK-BILLERS workspace has been created for <b>{company}</b>. "
            "Use the OTP below to set your admin password and sign in.",
            "button": "Activate Account",
        }
    inviter = f" by {escape(ctx.invited_by)}" if ctx.invited_by else ""
    return {
        "subject": f"You're invited to {ctx.company_name} on MK-BILLERS",
        "heading": "You've been invited",
        "intro": f"You have been invited{inviter} to join <b>{company}</b> on MK-BILLERS as <b>{role}</b>. "
        "Use the OTP below to set your password.",
        "button": "Accept Invite",
    }


def _otp_cells(otp: str, cell_style: str) -> str:
    return "".join(f'<td style="{cell_style}">{escape(digit)}</td>' for digit in otp)


def _classic(ctx: EmailContext, copy: dict[str, str]) -> str:
    cells = _otp_cells(
        ctx.otp,
        "width:44px;height:52px;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;"
        "font:700 24px Arial,sans-serif;color:#0f172a;text-align:center;",
    )
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 12px;font-family:Arial,sans-serif;">
  <tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
      <tr><td style="background:#0f84c8;padding:16px 28px;">
        <table role="presentation" cellpadding="0" cellspacing="0"><tr>
          <td style="padding-right:12px;">{_logo_img(copy["logo_src"], 40, "border:2px solid #ffffff;")}</td>
          <td style="color:#ffffff;font:700 20px Arial,sans-serif;">MK-BILLERS</td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:28px;">
        <h1 style="margin:0 0 12px;font:700 22px Arial,sans-serif;color:#0f172a;">{copy["heading"]}</h1>
        <p style="margin:0 0 22px;font:15px/1.6 Arial,sans-serif;color:#475569;">{copy["intro"]}</p>
        <table role="presentation" cellpadding="0" cellspacing="6" style="margin:0 auto 22px;"><tr>{cells}</tr></table>
        <p style="margin:0 0 24px;text-align:center;">
          <a href="{escape(ctx.setup_link)}" style="display:inline-block;background:#0f84c8;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font:600 15px Arial,sans-serif;">{copy["button"]}</a>
        </p>
        <p style="margin:0;font:13px/1.6 Arial,sans-serif;color:#64748b;">This OTP expires in {ctx.expires_minutes} minutes. If you did not expect this email, you can ignore it.</p>
      </td></tr>
      <tr><td style="background:#f8fafc;padding:16px 28px;font:12px Arial,sans-serif;color:#94a3b8;">MK-BILLERS &middot; GST billing made simple</td></tr>
    </table>
  </td></tr>
</table>"""


def _modern(ctx: EmailContext, copy: dict[str, str]) -> str:
    cells = _otp_cells(
        ctx.otp,
        "width:46px;height:56px;border-radius:10px;background:#1e293b;border:1px solid #2dd4bf;"
        "font:700 26px 'Courier New',monospace;color:#5eead4;text-align:center;",
    )
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#020617;padding:32px 12px;font-family:Arial,sans-serif;">
  <tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#0f172a;border-radius:16px;overflow:hidden;border:1px solid #1e293b;">
      <tr><td style="padding:28px 28px 8px;">
        <table role="presentation" cellpadding="0" cellspacing="0"><tr>
          <td style="padding-right:10px;">{_logo_img(copy["logo_src"], 36, "border:2px solid #2dd4bf;")}</td>
          <td style="font:700 12px Arial,sans-serif;letter-spacing:3px;color:#2dd4bf;">MK-BILLERS</td>
        </tr></table>
        <h1 style="margin:10px 0 12px;font:700 26px Arial,sans-serif;color:#f8fafc;">{copy["heading"]}</h1>
        <p style="margin:0;font:15px/1.6 Arial,sans-serif;color:#cbd5e1;">{copy["intro"]}</p>
      </td></tr>
      <tr><td style="padding:24px 28px;">
        <p style="margin:0 0 10px;font:600 12px Arial,sans-serif;letter-spacing:2px;color:#94a3b8;text-align:center;">YOUR ONE-TIME PASSWORD</p>
        <table role="presentation" cellpadding="0" cellspacing="6" style="margin:0 auto;"><tr>{cells}</tr></table>
      </td></tr>
      <tr><td style="padding:0 28px 28px;text-align:center;">
        <a href="{escape(ctx.setup_link)}" style="display:inline-block;background:#14b8a6;color:#042f2e;text-decoration:none;padding:13px 30px;border-radius:999px;font:700 15px Arial,sans-serif;">{copy["button"]} &rarr;</a>
        <p style="margin:20px 0 0;font:12px/1.6 Arial,sans-serif;color:#64748b;">Expires in {ctx.expires_minutes} minutes &middot; Never share this code with anyone.</p>
      </td></tr>
    </table>
  </td></tr>
</table>"""


def _minimal(ctx: EmailContext, copy: dict[str, str]) -> str:
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;padding:32px 16px;font-family:Georgia,serif;">
  <tr><td align="center">
    <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="max-width:520px;width:100%;">
      <tr><td style="border-bottom:1px solid #e5e7eb;padding-bottom:14px;">
        <table role="presentation" cellpadding="0" cellspacing="0"><tr>
          <td style="padding-right:10px;">{_logo_img(copy["logo_src"], 30)}</td>
          <td style="font:600 14px Georgia,serif;letter-spacing:4px;color:#111827;">MK-BILLERS</td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:26px 0;">
        <h1 style="margin:0 0 14px;font:400 24px Georgia,serif;color:#111827;">{copy["heading"]}</h1>
        <p style="margin:0 0 24px;font:15px/1.7 Georgia,serif;color:#374151;">{copy["intro"]}</p>
        <p style="margin:0 0 24px;font:700 34px 'Courier New',monospace;letter-spacing:10px;color:#111827;">{escape(ctx.otp)}</p>
        <p style="margin:0 0 24px;font:15px Georgia,serif;"><a href="{escape(ctx.setup_link)}" style="color:#111827;">{copy["button"]}</a></p>
        <p style="margin:0;font:13px/1.6 Georgia,serif;color:#6b7280;">Valid for {ctx.expires_minutes} minutes.</p>
      </td></tr>
      <tr><td style="border-top:1px solid #e5e7eb;padding-top:14px;font:12px Georgia,serif;color:#9ca3af;">Sent by MK-BILLERS</td></tr>
    </table>
  </td></tr>
</table>"""


def _bold(ctx: EmailContext, copy: dict[str, str]) -> str:
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fff7ed;padding:32px 12px;font-family:Arial,sans-serif;">
  <tr><td align="center">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:2px solid #fdba74;">
      <tr><td style="background:#ea580c;background-image:linear-gradient(135deg,#f97316,#c2410c);padding:28px;text-align:center;" align="center">
        {_logo_img(copy["logo_src"], 64, "margin:0 auto 10px;border:3px solid #ffffff;")}
        <div style="font:800 26px Arial,sans-serif;color:#ffffff;letter-spacing:1px;">MK-BILLERS</div>
        <div style="margin-top:6px;font:14px Arial,sans-serif;color:#ffedd5;">{copy["heading"]}</div>
      </td></tr>
      <tr><td style="padding:28px;text-align:center;">
        <p style="margin:0 0 22px;font:15px/1.6 Arial,sans-serif;color:#431407;">{copy["intro"]}</p>
        <div style="display:inline-block;padding:16px 26px;border:2px dashed #f97316;border-radius:12px;background:#fff7ed;font:800 32px 'Courier New',monospace;letter-spacing:8px;color:#c2410c;">{escape(ctx.otp)}</div>
        <p style="margin:24px 0;">
          <a href="{escape(ctx.setup_link)}" style="display:inline-block;background:#c2410c;color:#ffffff;text-decoration:none;padding:13px 30px;border-radius:10px;font:700 15px Arial,sans-serif;">{copy["button"]}</a>
        </p>
        <p style="margin:0;font:13px/1.6 Arial,sans-serif;color:#9a3412;">This code expires in {ctx.expires_minutes} minutes.</p>
      </td></tr>
    </table>
  </td></tr>
</table>"""


EMAIL_TEMPLATES: dict[str, tuple[str, str, Callable[[EmailContext, dict[str, str]], str]]] = {
    "classic": ("Classic", "Clean white card with a blue MK-BILLERS header.", _classic),
    "modern": ("Modern Dark", "Dark theme with teal OTP boxes.", _modern),
    "minimal": ("Minimal", "Simple, text-first layout with a serif font.", _minimal),
    "bold": ("Bold Brand", "Bright orange banner with a highlighted OTP.", _bold),
}


def normalize_template_id(template_id: str | None) -> str:
    return template_id if template_id in EMAIL_TEMPLATES else DEFAULT_EMAIL_TEMPLATE


def render_email(template_id: str | None, ctx: EmailContext, preview: bool = False) -> RenderedEmail:
    """preview=True embeds the logo as a data URI (for in-app previews); otherwise it is a CID inline image."""
    _, _, renderer = EMAIL_TEMPLATES[normalize_template_id(template_id)]
    copy = _copy(ctx)
    logo = _logo_bytes()
    inline_images: dict[str, bytes] = {}
    if preview:
        copy["logo_src"] = _logo_data_uri()
    elif logo:
        copy["logo_src"] = f"cid:{LOGO_CID}"
        inline_images[LOGO_CID] = logo
    else:
        copy["logo_src"] = ""
    html = f'<!doctype html><html><body style="margin:0;padding:0;">{renderer(ctx, copy)}</body></html>'
    text = (
        f"{copy['heading']}\n\n"
        f"Your MK-BILLERS OTP: {ctx.otp}\n"
        f"Set your password: {ctx.setup_link}\n\n"
        f"This OTP expires in {ctx.expires_minutes} minutes.\n"
        "If you did not expect this email, you can ignore it.\n"
        "MK-BILLERS Team\n"
    )
    return RenderedEmail(subject=copy["subject"], html=html, text=text, inline_images=inline_images)


def list_templates_with_preview(purpose: EmailPurpose = "invite") -> list[dict[str, str]]:
    sample = EmailContext(
        purpose=purpose,
        recipient="user@example.com",
        otp="482913",
        setup_link="https://mkbillers.netlify.app/set-password",
        expires_minutes=60,
        company_name="Your Company",
        role="STAFF",
    )
    return [
        {
            "id": template_id,
            "name": name,
            "description": description,
            "preview_html": render_email(template_id, sample, preview=True).html,
        }
        for template_id, (name, description, _) in EMAIL_TEMPLATES.items()
    ]
