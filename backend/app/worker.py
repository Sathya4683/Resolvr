"""
Worker container: same code and image as the api, different entrypoint.
  - processes queued batch jobs (csv analysis)
  - runs scheduled tasks: overdue review alerts and the daily digest email
Only one worker should run the scheduler, the api replicas never do (no duplicate emails).
"""

import logging
import signal
import time

from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import start_http_server

from app import metrics
from app.config import settings
from app.db import SessionLocal
from app.logging_setup import setup_logging
from app.services import digest
from app.services.jobs import alert_overdue_reviews, claim_next_job, process_job

log = logging.getLogger("resolvr.worker")
running = True


def stop(*_):
    global running
    running = False


def run_scheduled(name: str, fn) -> None:
    try:
        with SessionLocal() as db:
            fn(db)
    except Exception:
        log.exception("scheduled task failed", extra={"task": name})


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.app_timezone)
    scheduler.add_job(
        run_scheduled, "interval", minutes=5, args=["overdue_reviews", alert_overdue_reviews], id="overdue_reviews"
    )
    #the daily digest email, at DIGEST_HOUR:DIGEST_MINUTE in the app timezone
    scheduler.add_job(
        run_scheduled,
        "cron",
        hour=settings.digest_hour,
        minute=settings.digest_minute,
        args=["daily_digest", digest.send_today],
        id="daily_digest",
    )
    scheduler.start()
    return scheduler


def main() -> None:
    setup_logging("worker", settings.log_level)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    #prometheus scrapes the worker separately from the api
    start_http_server(9101)
    scheduler = start_scheduler()
    log.info("worker started", extra={"jobs": [j.id for j in scheduler.get_jobs()]})
    run_scheduled("digest_catch_up", digest.catch_up)

    while running:
        try:
            with SessionLocal() as db:
                job = claim_next_job(db)
                if job:
                    try:
                        process_job(db, job)
                    except Exception as exc:
                        db.rollback()
                        job.status = "failed"
                        job.error = str(exc)[:500]
                        db.commit()
                        metrics.JOBS.labels(job.kind, "failed").inc()
                        log.exception("batch job failed", extra={"job_id": job.id})
                    continue
        except Exception:
            log.exception("worker loop error")
        time.sleep(2)

    scheduler.shutdown(wait=False)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
