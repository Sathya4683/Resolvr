"""
Possible outage detection: if several near-identical complaints arrive within a short window,
it's probably an area problem (fibre cut, tower down), not one customer's router.
We look at the embeddings of recent incoming tickets, so differently worded complaints still match.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import metrics
from app.config import settings
from app.models import AuditLog, Ticket


def detect_outage(db: Session, ticket: Ticket, qvec: list[float]) -> list[str] | None:
    """returns the refs of the similar recent tickets when they cross the threshold, else None"""
    since = datetime.now(timezone.utc) - timedelta(minutes=settings.outage_window_minutes)
    distance = Ticket.embedding.cosine_distance(qvec)
    #sql: SELECT ref FROM tickets
    #     WHERE created_at >= :since AND source <> 'seed' AND id <> :id
    #       AND embedding IS NOT NULL AND (embedding <=> :qvec) <= 1 - :min_similarity
    stmt = select(Ticket.ref).where(
        Ticket.created_at >= since,
        Ticket.source != "seed",
        Ticket.id != ticket.id,
        Ticket.embedding.is_not(None),
        distance <= 1 - settings.outage_similarity,
    )
    similar = list(db.scalars(stmt))
    if len(similar) + 1 < settings.outage_min_count:
        return None

    #only alert once per cluster: skip if a recent outage alert already covered one of these tickets
    #sql: SELECT details FROM audit_logs WHERE action = 'outage.detected' AND created_at >= :since
    recent = db.scalars(
        select(AuditLog.details).where(AuditLog.action == "outage.detected", AuditLog.created_at >= since)
    )
    for details in recent:
        if set(details.get("refs", [])) & set(similar):
            return None

    refs = similar + [ticket.ref]
    db.add(AuditLog(action="outage.detected", entity_type="ticket", entity_id=ticket.ref, details={"refs": refs}))
    metrics.OUTAGE_ALERTS.inc()
    return refs
