"""
Sending the daily digest. Safe to call more than once: a partial unique index on
digest_runs(report_date) WHERE trigger = 'cron' means only the first caller for a day gets to send,
even if two schedulers were running by mistake.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import metrics
from app.config import settings
from app.models import DigestRun, User
from app.services import notify
from app.services.mailer import send_email
from app.services.reports import build_digest_pdf, digest_text

log = logging.getLogger(__name__)


def deliver(db: Session, run: DigestRun) -> DigestRun:
    recipients = settings.admin_email_list
    pdf = build_digest_pdf(db, run.report_date)
    run.recipients = recipients
    run.attempts += 1
    ok = send_email(
        recipients,
        f"Resolvr daily digest - {run.report_date:%d %b %Y}",
        digest_text(db, run.report_date),
        attachments=[(f"resolvr-digest-{run.report_date}.pdf", pdf, "application/pdf")],
    )
    if ok:
        run.status = "sent"
        run.sent_at = datetime.now(timezone.utc)
        run.error = None
    else:
        run.status = "failed"
        run.error = "smtp failed after retries" if recipients else "ADMIN_EMAILS is empty"
        notify.dispatch(
            [
                notify.Alert(
                    title="Daily digest email failed",
                    message=f"The digest for {run.report_date} could not be emailed. Download it from Reports.",
                    topic=settings.ntfy_admin_topic,
                    priority="high",
                    tags=["email", "warning"],
                    link="/reports",
                )
            ]
        )
    db.commit()
    metrics.DIGESTS.labels(run.status).inc()
    log.info("digest run finished", extra={"day": str(run.report_date), "status": run.status, "trigger": run.trigger})
    return run


def send_scheduled(db: Session, day: date) -> DigestRun | None:
    """cron path: returns None if this day was already handled"""
    #sql: INSERT INTO digest_runs (report_date, trigger, status, attempts, recipients)
    #     VALUES (:day, 'cron', 'sending', 0, '[]')
    #     ON CONFLICT (report_date) WHERE trigger = 'cron' DO NOTHING RETURNING id
    run_id = db.scalar(
        insert(DigestRun)
        .values(report_date=day, trigger="cron", status="sending", attempts=0, recipients=[])
        .on_conflict_do_nothing(index_elements=["report_date"], index_where=text("trigger = 'cron'"))
        .returning(DigestRun.id)
    )
    db.commit()
    if run_id is None:
        log.info("digest already handled for this day", extra={"day": str(day)})
        return None
    return deliver(db, db.get(DigestRun, run_id))


def send_manual(db: Session, day: date, user: User) -> DigestRun:
    run = DigestRun(
        report_date=day, trigger="manual", status="sending", attempts=0, recipients=[], triggered_by_id=user.id
    )
    db.add(run)
    db.commit()
    return deliver(db, run)


def catch_up(db: Session) -> None:
    """after a worker restart, send yesterday's digest (and today's if its time has passed) if they were missed"""
    tz = ZoneInfo(settings.app_timezone)
    now = datetime.now(tz)
    days = [now.date() - timedelta(days=1)]
    if (now.hour, now.minute) >= (settings.digest_hour, settings.digest_minute):
        days.append(now.date())
    for day in days:
        #sql: SELECT id FROM digest_runs WHERE report_date = :day AND trigger = 'cron'
        if not db.scalar(select(DigestRun.id).where(DigestRun.report_date == day, DigestRun.trigger == "cron")):
            log.info("catching up missed digest", extra={"day": str(day)})
            send_scheduled(db, day)


def send_today(db: Session) -> None:
    send_scheduled(db, datetime.now(ZoneInfo(settings.app_timezone)).date())
