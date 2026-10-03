"""
Support agents upload a csv of new complaints. The api only validates it and queues a job,
the worker container does the slow part (one llm analysis per row) in the background.
"""

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import agent_or_admin
from app.models import BatchJob, User
from app.ratelimit import rate_limit
from app.schemas import BatchJobOut
from app.services import audit
from app.services.files import read_csv

router = APIRouter(prefix="/batch", tags=["batch analysis"])

OPTIONAL_COLUMNS = ("subject", "customer_ref", "channel", "product_hint")
CHANNELS = {"phone", "email", "chat", "app", "store"}
PRODUCTS = {"broadband", "mobile", "dth", "billing"}


def load_job(db: Session, job_id: int, user: User) -> BatchJob:
    #sql: SELECT * FROM batch_jobs WHERE id = :job_id
    job = db.get(BatchJob, job_id)
    if job is None or (user.role != "admin" and job.created_by_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.post("", response_model=BatchJobOut, status_code=202, dependencies=[Depends(rate_limit("batch"))])
def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    rows = read_csv(file, {"complaint"}, settings.max_csv_rows)
    clean = []
    for i, row in enumerate(rows, start=1):
        complaint = row.get("complaint", "").strip()
        item = {"row": i, "complaint": complaint}
        for col in OPTIONAL_COLUMNS:
            item[col] = (row.get(col) or "").strip() or None
        #bad optional values are dropped rather than failing the row
        if item["channel"] not in CHANNELS:
            item["channel"] = None
        if item["product_hint"] not in PRODUCTS:
            item["product_hint"] = None
        if len(complaint) < 5:
            item["error"] = "complaint is empty or too short"
        elif len(complaint) > settings.max_complaint_chars:
            item["error"] = f"complaint longer than {settings.max_complaint_chars} characters"
        clean.append(item)

    job = BatchJob(
        kind="analyze_csv",
        filename=file.filename,
        rows=clean,
        total=len(clean),
        created_by_id=user.id,
    )
    db.add(job)
    db.flush()
    audit.record(db, user, "batch.upload", "batch_job", job.id, rows=len(clean))
    db.commit()
    return job


@router.get("", response_model=list[BatchJobOut])
def my_jobs(db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    #sql: SELECT * FROM batch_jobs WHERE created_by_id = :user_id ORDER BY id DESC LIMIT 20
    stmt = select(BatchJob).order_by(BatchJob.id.desc()).limit(20)
    if user.role != "admin":
        stmt = stmt.where(BatchJob.created_by_id == user.id)
    return db.scalars(stmt).all()


@router.get("/{job_id}", response_model=BatchJobOut)
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    return load_job(db, job_id, user)


@router.get("/{job_id}/results.csv")
def download_results(job_id: int, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    job = load_job(db, job_id, user)
    out = io.StringIO()
    columns = ["row", "ticket_ref", "category", "product", "severity", "sentiment", "review_status",
               "outcome", "top_source", "steps", "error"]
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for result in job.results:
        writer.writerow({**result, "steps": " | ".join(result.get("steps", []))})
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="batch-{job.id}-results.csv"'},
    )
