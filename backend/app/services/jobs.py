"""Batch job processing, run by the worker container."""

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import metrics
from app.config import settings
from app.models import Analysis, BatchJob, Ticket
from app.pipeline.analyze import run_analysis
from app.services import notify
from app.services.tickets import HIDDEN_FOR_AGENTS, visible_steps

log = logging.getLogger(__name__)


def claim_next_job(db: Session) -> BatchJob | None:
    """
    picks the oldest queued job and marks it running. SKIP LOCKED means two workers never grab
    the same job, so we could run more than one worker later without changing anything.
    """
    #sql: SELECT * FROM batch_jobs WHERE status = 'queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED
    job = db.scalar(
        select(BatchJob)
        .where(BatchJob.status == "queued")
        .order_by(BatchJob.id)
        .limit(1)
        .with_for_update(skip_locked=True, of=BatchJob)
    )
    if job is None:
        return None
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    return job


def analyze_row(db: Session, job: BatchJob, row: dict) -> dict:
    ticket = Ticket(
        complaint=row["complaint"],
        subject=row.get("subject"),
        customer_ref=row.get("customer_ref"),
        channel=row.get("channel"),
        product_hint=row.get("product_hint"),
        source="csv",
        status="open",
        created_by_id=job.created_by_id,
    )
    db.add(ticket)
    db.flush()
    analysis = run_analysis(db, ticket, job.created_by)
    alerts = notify.after_analysis(db, ticket, analysis)
    db.commit()
    notify.dispatch(alerts)

    hidden = analysis.review_status in HIDDEN_FOR_AGENTS
    return {
        "row": row["row"],
        "ticket_ref": ticket.ref,
        "category": analysis.parsed.get("category"),
        "product": ticket.product,
        "severity": ticket.severity,
        "sentiment": ticket.sentiment,
        "review_status": analysis.review_status,
        "outcome": analysis.outcome,
        "top_source": analysis.retrieved[0]["ref"] if analysis.retrieved else None,
        "steps": [] if hidden else [s["text"] for s in visible_steps(analysis)],
    }


def process_job(db: Session, job: BatchJob) -> None:
    log.info("batch job started", extra={"job_id": job.id, "rows": job.total})
    results = []
    for i, row in enumerate(job.rows):
        if row.get("error"):
            results.append({"row": row["row"], "error": row["error"]})
            job.failed += 1
        else:
            try:
                results.append(analyze_row(db, job, row))
            except Exception as exc:
                db.rollback()
                log.exception("batch row failed", extra={"job_id": job.id, "row": row["row"]})
                results.append({"row": row["row"], "error": str(exc)[:200]})
                job.failed += 1
            #stay under the llm rate limit (free tier allows only a few requests a minute)
            if i < len(job.rows) - 1:
                time.sleep(settings.llm_min_interval_ms / 1000)
        job.processed = i + 1
        job.results = list(results)
        db.commit()

    job.status = "done"
    job.finished_at = datetime.now(timezone.utc)
    ok = job.total - job.failed
    notify.notify_users(
        db,
        [job.created_by],
        "batch_done",
        f"Batch #{job.id} finished",
        f"{ok} of {job.total} complaints analysed from {job.filename or 'your csv'}.",
        f"/batch?job={job.id}",
    )
    db.commit()
    metrics.JOBS.labels(job.kind, "done").inc()
    log.info("batch job finished", extra={"job_id": job.id, "ok": ok, "failed": job.failed})


def alert_overdue_reviews(db: Session) -> int:
    """re-alert admins about critical cases that have waited longer than the review sla"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.review_sla_minutes)
    #sql: SELECT * FROM analyses WHERE review_status = 'pending_review' AND created_at < :cutoff
    #       AND (last_alerted_at IS NULL OR last_alerted_at < :cutoff)
    overdue = db.scalars(
        select(Analysis).where(
            Analysis.review_status == "pending_review",
            Analysis.created_at < cutoff,
            (Analysis.last_alerted_at.is_(None)) | (Analysis.last_alerted_at < cutoff),
        )
    ).all()
    alerts = []
    for analysis in overdue:
        ticket = analysis.ticket
        waited = int((datetime.now(timezone.utc) - analysis.created_at).total_seconds() // 60)
        alerts.append(
            notify.Alert(
                title=f"Review overdue: {ticket.ref} waiting {waited} min",
                message=f"{(ticket.critical_reason or 'critical').title()} case still needs an admin decision.",
                topic=settings.ntfy_admin_topic,
                priority="high",
                tags=["hourglass"],
                link=f"/approvals?ref={ticket.ref}",
            )
        )
        analysis.last_alerted_at = datetime.now(timezone.utc)
    db.commit()
    notify.dispatch(alerts)
    if alerts:
        log.info("overdue review alerts sent", extra={"count": len(alerts)})
    return len(alerts)
