from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import admin_only, analyst_or_admin
from app.models import DigestRun, Ticket, User
from app.services import audit, digest
from app.services.reports import build_digest_pdf, build_quality_pdf

router = APIRouter(prefix="/reports", tags=["reports"])


def today() -> date:
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def pdf_response(data: bytes, filename: str) -> Response:
    return Response(
        data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/days")
def available_days(db: Session = Depends(get_db), _: User = Depends(analyst_or_admin)):
    """days that have tickets, for the date picker"""
    day = func.date(func.timezone(settings.app_timezone, Ticket.created_at))
    #sql: SELECT date(timezone(:tz, created_at)) AS day, count(*) FROM tickets GROUP BY day ORDER BY day DESC LIMIT 30
    rows = db.execute(select(day, func.count(Ticket.id)).group_by(day).order_by(day.desc()).limit(30)).all()
    return [{"day": d.isoformat(), "tickets": n} for d, n in rows]


@router.get("/digest.pdf")
def digest_pdf(
    day: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    day = day or today()
    if day > today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That day hasn't happened yet")
    audit.record(db, user, "report.download_digest", "report", str(day))
    db.commit()
    return pdf_response(build_digest_pdf(db, day), f"resolvr-digest-{day}.pdf")


@router.get("/quality.pdf")
def quality_pdf(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(analyst_or_admin),
):
    end = end or today()
    start = start or end - timedelta(days=6)
    if start > end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "start must be before end")
    audit.record(db, user, "report.download_quality", "report", f"{start}..{end}")
    db.commit()
    return pdf_response(build_quality_pdf(db, start, end), f"resolvr-quality-{start}-to-{end}.pdf")


@router.get("/digests")
def digest_runs(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    #sql: SELECT * FROM digest_runs ORDER BY created_at DESC LIMIT 30
    runs = db.scalars(select(DigestRun).order_by(DigestRun.created_at.desc()).limit(30)).all()
    return [
        {
            "id": r.id,
            "report_date": r.report_date,
            "trigger": r.trigger,
            "status": r.status,
            "attempts": r.attempts,
            "recipients": r.recipients,
            "error": r.error,
            "created_at": r.created_at,
            "sent_at": r.sent_at,
        }
        for r in runs
    ]


@router.post("/digest/send")
def send_digest_now(
    day: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    """manual send for demos, it doesn't block the scheduled one"""
    day = day or today()
    run = digest.send_manual(db, day, admin)
    audit.record(db, admin, "report.send_digest", "report", str(day), status=run.status)
    db.commit()
    if run.status != "sent":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Email failed: {run.error}")
    return {"status": run.status, "recipients": run.recipients}
