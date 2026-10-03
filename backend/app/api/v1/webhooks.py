"""
Helpdesk integration: a tool like Zendesk/Freshdesk can call this when a ticket is created.
Authenticated with a shared secret header, idempotent on the helpdesk's own ticket id.
"""

import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Ticket
from app.pipeline.analyze import run_analysis
from app.services import audit, notify

router = APIRouter(prefix="/webhooks", tags=["integrations"])
log = logging.getLogger(__name__)


class HelpdeskTicket(BaseModel):
    external_id: str = Field(min_length=1, max_length=60)
    subject: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=5, max_length=4000)
    customer_ref: str | None = Field(default=None, max_length=40)
    channel: str | None = Field(default=None, max_length=20)


def check_secret(x_webhook_secret: str | None = Header(default=None)) -> None:
    if not settings.webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhook is not configured")
    #constant time compare so the secret can't be guessed byte by byte from response times
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, settings.webhook_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")


@router.post("/helpdesk", status_code=201, dependencies=[Depends(check_secret)])
def helpdesk_ticket_created(body: HelpdeskTicket, background: BackgroundTasks, db: Session = Depends(get_db)):
    tag = f"ext:{body.external_id}"
    #sql: SELECT * FROM tickets WHERE source = 'webhook' AND tags @> ARRAY[:tag]
    existing = db.scalar(select(Ticket).where(Ticket.source == "webhook", Ticket.tags.contains([tag])))
    if existing:
        #helpdesks retry webhooks, the same ticket must not be analysed twice
        return {"ref": existing.ref, "duplicate": True, "severity": existing.severity, "status": existing.status}

    ticket = Ticket(
        complaint=body.description.strip(),
        subject=body.subject,
        customer_ref=body.customer_ref,
        channel="webhook",
        source="webhook",
        status="open",
        tags=[tag],
    )
    db.add(ticket)
    db.flush()
    analysis = run_analysis(db, ticket, None)
    audit.record(db, None, "webhook.ticket", "ticket", ticket.ref, external_id=body.external_id)
    alerts = notify.after_analysis(db, ticket, analysis)
    db.commit()
    background.add_task(notify.dispatch, alerts)
    return {
        "ref": ticket.ref,
        "duplicate": False,
        "severity": ticket.severity,
        "status": ticket.status,
        "review_status": analysis.review_status,
        "url": f"{settings.frontend_url.rstrip('/')}/tickets/{ticket.ref}",
    }
