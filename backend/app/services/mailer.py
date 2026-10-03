import logging
import smtplib
from email.message import EmailMessage

from tenacity import retry, stop_after_attempt, wait_exponential

from app import metrics
from app.config import settings

log = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=20), reraise=True)
def _send(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def send_email(
    to: list[str],
    subject: str,
    text: str,
    html: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """sends one email, retried a few times. returns False instead of raising so callers can carry on"""
    if not to:
        log.info("no recipients, email skipped", extra={"subject": subject})
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for filename, data, mime in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    try:
        _send(msg)
    except Exception as exc:
        metrics.NOTIFICATIONS.labels("email", "failed").inc()
        log.error("email failed", extra={"subject": subject, "error": str(exc)[:300]})
        return False
    metrics.NOTIFICATIONS.labels("email", "sent").inc()
    log.info("email sent", extra={"subject": subject, "recipients": len(to)})
    return True
