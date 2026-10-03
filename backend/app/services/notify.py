"""
Notifications go out on three channels:
  - in-app (the bell icon): rows in the notifications table, written in the same transaction
  - ntfy push to phones: one topic for admins, one shared topic for support agents
  - email to the admin list (ADMIN_EMAILS) for critical cases

ntfy and email are network calls, so the api runs them as background tasks after the response.
A failure is logged and counted, it never breaks the request that triggered it.
"""

import logging
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from app import metrics
from app.config import settings
from app.models import Analysis, Notification, Ticket, User
from app.services.mailer import send_email

log = logging.getLogger(__name__)

PRIORITY = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}


@dataclass
class Alert:
    title: str
    message: str
    topic: str = ""  #ntfy topic, empty means no push
    priority: str = "default"
    tags: list[str] = field(default_factory=list)
    link: str | None = None  #path inside the frontend, e.g. /tickets/TCK-20001
    email_to: list[str] = field(default_factory=list)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8), reraise=True)
def _post_ntfy(payload: dict) -> None:
    headers = {"Authorization": f"Bearer {settings.ntfy_token}"} if settings.ntfy_token else {}
    #publishing as json (instead of headers) keeps unicode titles working
    res = httpx.post(settings.ntfy_base_url.rstrip("/"), json=payload, headers=headers, timeout=10)
    res.raise_for_status()


def push(alert: Alert) -> None:
    if not alert.topic:
        return
    payload = {
        "topic": alert.topic,
        "title": alert.title,
        "message": alert.message,
        "priority": PRIORITY.get(alert.priority, 3),
        "tags": alert.tags,
    }
    if alert.link:
        payload["click"] = settings.frontend_url.rstrip("/") + alert.link
    try:
        _post_ntfy(payload)
        metrics.NOTIFICATIONS.labels("ntfy", "sent").inc()
    except Exception as exc:
        metrics.NOTIFICATIONS.labels("ntfy", "failed").inc()
        log.error("ntfy push failed", extra={"topic": alert.topic, "error": str(exc)[:300]})


def dispatch(alerts: list[Alert]) -> None:
    """send push + email for each alert (runs as a background task)"""
    for alert in alerts:
        push(alert)
        if alert.email_to:
            url = settings.frontend_url.rstrip("/") + (alert.link or "")
            send_email(
                alert.email_to,
                f"[Resolvr] {alert.title}",
                f"{alert.message}\n\nOpen in Resolvr: {url}\n",
                html=(
                    f"<div style='font-family:sans-serif'><h3 style='margin:0 0 8px'>{alert.title}</h3>"
                    f"<p style='white-space:pre-wrap'>{alert.message}</p>"
                    f"<p><a href='{url}'>Open in Resolvr</a></p></div>"
                ),
            )


#---------------- in-app ----------------

def notify_users(db: Session, users: list[User], kind: str, title: str, body: str | None, link: str | None) -> None:
    for user in users:
        db.add(Notification(user_id=user.id, kind=kind, title=title, body=body, link=link))


def users_with_role(db: Session, role: str) -> list[User]:
    #sql: SELECT * FROM users WHERE role = :role AND is_active = true
    return list(db.scalars(select(User).where(User.role == role, User.is_active.is_(True))))


#---------------- events ----------------

def after_analysis(db: Session, ticket: Ticket, analysis: Analysis) -> list[Alert]:
    """writes in-app notifications now and returns the push/email alerts to send afterwards"""
    alerts = []
    labels = analysis.parsed or {}
    link = f"/approvals?ref={ticket.ref}"
    snippet = ticket.complaint[:180]

    if analysis.review_status == "pending_review":
        reason = ticket.critical_reason or "critical"
        title = f"Critical case needs approval: {ticket.ref}"
        raised_by = ticket.created_by.full_name if ticket.created_by else "an agent"
        body = f"{reason.title()} case raised by {raised_by}: {snippet}"
        notify_users(db, users_with_role(db, "admin"), "approval_needed", title, body, link)
        alerts.append(
            Alert(
                title=title,
                message=body,
                topic=settings.ntfy_admin_topic,
                priority="high",
                tags=["rotating_light", reason],
                link=link,
                email_to=settings.admin_email_list,
            )
        )
    elif labels.get("sentiment") == "angry" and ticket.severity == "high":
        alerts.append(
            Alert(
                title=f"Angry customer, high severity: {ticket.ref}",
                message=snippet,
                topic=settings.ntfy_admin_topic,
                tags=["warning"],
                link=f"/tickets/{ticket.ref}",
            )
        )
    return alerts


DECISION_TEXT = {
    "approve": ("approved", "white_check_mark"),
    "edit": ("approved with changes", "pencil2"),
    "reject": ("declined", "x"),
}


def after_decision(db: Session, ticket: Ticket, action: str, admin: User, comment: str | None) -> list[Alert]:
    verb, tag = DECISION_TEXT[action]
    title = f"{ticket.ref}: admin {verb} the resolution"
    body = comment or f"{admin.full_name} {verb} the draft for '{ticket.subject or ticket.complaint[:60]}'."
    link = f"/tickets/{ticket.ref}"
    if ticket.created_by:
        notify_users(db, [ticket.created_by], "decision", title, body, link)
    return [Alert(title=title, message=body, topic=settings.ntfy_agent_topic, tags=[tag], link=link)]
