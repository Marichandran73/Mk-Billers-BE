import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_mail(
    recipient: str,
    subject: str,
    body: str,
    html: str | None = None,
    inline_images: dict[str, bytes] | None = None,
) -> bool:
    """Send an email. Returns False when SMTP is not configured; raises on SMTP errors.

    inline_images maps a Content-ID to PNG bytes; reference them in the HTML as src="cid:<id>".
    """
    if not settings.smtp_host:
        return False

    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
        html_part = message.get_payload()[-1]
        for content_id, data in (inline_images or {}).items():
            html_part.add_related(data, maintype="image", subtype="png", cid=f"<{content_id}>")

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        return True

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
    return True
