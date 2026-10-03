import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text

from app import metrics
from app.db import SessionLocal
from app.models import Analysis, AnalystReview, KbChunk, Ticket
from app.schemas import ClientLogIn

router = APIRouter(tags=["ops"])
log = logging.getLogger(__name__)


@router.get("/health")
def health():
    #liveness only, if the process answers it's alive
    return {"status": "ok"}


@router.get("/ready")
def ready():
    #readiness checks the things we can't work without
    checks = {}
    try:
        with SessionLocal() as db:
            #sql: SELECT 1
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.warning("db not ready", extra={"error": str(exc)})
        checks["database"] = "down"

    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)


def refresh_db_gauges() -> None:
    """workflow numbers live in the db, so they are read fresh every time prometheus scrapes"""
    with SessionLocal() as db:
        #sql: SELECT count(*), min(created_at) FROM analyses WHERE review_status = 'pending_review'
        pending, oldest = db.execute(
            select(func.count(Analysis.id), func.min(Analysis.created_at)).where(
                Analysis.review_status == "pending_review"
            )
        ).one()
        metrics.PENDING_APPROVALS.set(pending)
        metrics.OLDEST_PENDING.set((datetime.now(timezone.utc) - oldest).total_seconds() if oldest else 0)

        #sql: SELECT verdict, count(*) FROM analyst_reviews GROUP BY verdict
        verdicts = dict(db.execute(select(AnalystReview.verdict, func.count()).group_by(AnalystReview.verdict)).all())
        for verdict in ("correct", "partially_correct", "incorrect"):
            metrics.ANALYST_VERDICTS.labels(verdict).set(verdicts.get(verdict, 0))

        #sql: SELECT corrected_labels FROM analyst_reviews
        corrections = db.scalars(select(AnalystReview.corrected_labels)).all()
        for field in ("category", "product", "severity", "sentiment"):
            if corrections:
                kept = sum(1 for c in corrections if field not in (c or {}))
                metrics.ANALYST_AGREEMENT.labels(field).set(kept / len(corrections))

        #sql: SELECT count(*) FROM tickets WHERE is_searchable = true
        metrics.SEARCHABLE_DOCS.labels("ticket").set(
            db.scalar(select(func.count(Ticket.id)).where(Ticket.is_searchable.is_(True)))
        )
        #sql: SELECT count(*) FROM kb_chunks
        metrics.SEARCHABLE_DOCS.labels("kb_section").set(db.scalar(select(func.count(KbChunk.id))))


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    try:
        refresh_db_gauges()
    except Exception as exc:
        #never let a db hiccup break the scrape, the http metrics are still useful
        log.warning("could not refresh db gauges", extra={"error": str(exc)[:200]})
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post("/v1/client-logs", status_code=204, tags=["ops"])
def client_log(body: ClientLogIn):
    """the browser reports js errors here so they land in the same log pipeline (loki) as the api"""
    metrics.CLIENT_ERRORS.inc()
    log.warning(
        "frontend error",
        extra={"source": "frontend", "client_level": body.level, "error": body.message, "page": body.path,
               "file": body.source, "line": body.line},
    )
