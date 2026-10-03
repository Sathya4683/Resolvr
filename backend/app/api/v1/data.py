"""
Ways for admins and analysts to grow the searchable knowledge (support agents can't write to it):
  - import resolved tickets / kb articles from csv (idempotent, per-row error report)
  - add a single resolved ticket
  - promote tickets that agents resolved in the app into the searchable history
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import analyst_or_admin
from app.models import Analysis, AnalystReview, Feedback, Ticket, User
from app.models.tickets import PRODUCTS
from app.schemas import ImportReport, PromotableTicket, PromoteIn, ResolvedTicketIn
from app.services import audit
from app.services.files import read_csv
from app.services.ingest import content_hash, find_category, import_resolved_tickets, promote_ticket, save_kb_article

router = APIRouter(prefix="/data", tags=["data import"])

MAX_IMPORT_ROWS = 500


@router.post("/tickets/import", response_model=ImportReport)
def import_tickets_csv(
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)
):
    rows = read_csv(file, {"complaint", "category", "severity", "resolution_steps"}, MAX_IMPORT_ROWS)
    report = import_resolved_tickets(db, rows, user=user, source="csv")
    audit.record(db, user, "data.import_tickets", "file", file.filename,
                 inserted=report["inserted"], duplicates=report["duplicates"], errors=len(report["errors"]))
    db.commit()
    return ImportReport(**report)


@router.post("/tickets", response_model=ImportReport, status_code=201)
def add_resolved_ticket(
    body: ResolvedTicketIn, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)
):
    row = body.model_dump()
    report = import_resolved_tickets(db, [row], user=user, source="manual")
    if report["errors"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, report["errors"][0]["error"])
    audit.record(db, user, "data.add_ticket", "ticket", None, duplicate=bool(report["duplicates"]))
    db.commit()
    return ImportReport(**report)


@router.post("/kb/import", response_model=ImportReport)
def import_kb_csv(
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)
):
    """csv columns: title, content_md and optionally ref, product, category, tags (comma separated)"""
    rows = read_csv(file, {"title", "content_md"}, MAX_IMPORT_ROWS)
    report = ImportReport()
    for i, row in enumerate(rows, start=1):
        if len(row["title"]) < 3 or len(row["content_md"]) < 20:
            report.errors.append({"row": i, "error": "title or content is too short"})
            continue
        if row.get("category") and find_category(db, row["category"]) is None:
            report.errors.append({"row": i, "error": f"unknown category '{row['category']}'"})
            continue
        _, created = save_kb_article(
            db,
            ref=row.get("ref") or None,
            title=row["title"],
            content_md=row["content_md"],
            product=row.get("product") if row.get("product") in PRODUCTS else None,
            category_slug=row.get("category") or None,
            tags=[t.strip() for t in (row.get("tags") or "").split(",") if t.strip()],
            user=user,
        )
        if created:
            report.inserted += 1
        else:
            report.updated += 1
    audit.record(db, user, "data.import_kb", "file", file.filename,
                 inserted=report.inserted, updated=report.updated, errors=len(report.errors))
    db.commit()
    return report


@router.get("/tickets/promotable", response_model=list[PromotableTicket])
def promotable_tickets(db: Session = Depends(get_db), _: User = Depends(analyst_or_admin)):
    """tickets resolved in the app that are not part of the searchable history yet"""
    #sql: SELECT * FROM tickets WHERE status = 'resolved' AND is_searchable = false
    #     ORDER BY resolved_at DESC LIMIT 200
    tickets = db.scalars(
        select(Ticket)
        .where(Ticket.status == "resolved", Ticket.is_searchable.is_(False))
        .order_by(Ticket.resolved_at.desc())
        .limit(200)
    ).all()
    out = []
    for t in tickets:
        #sql: SELECT id FROM analyses WHERE ticket_id = :ticket_id ORDER BY id DESC LIMIT 1
        analysis_id = db.scalar(
            select(Analysis.id).where(Analysis.ticket_id == t.id).order_by(Analysis.id.desc()).limit(1)
        )
        feedback = verdict = None
        if analysis_id:
            #sql: SELECT rating FROM feedback WHERE analysis_id = :analysis_id LIMIT 1
            feedback = db.scalar(select(Feedback.rating).where(Feedback.analysis_id == analysis_id).limit(1))
            #sql: SELECT verdict FROM analyst_reviews WHERE analysis_id = :analysis_id
            verdict = db.scalar(select(AnalystReview.verdict).where(AnalystReview.analysis_id == analysis_id))
        out.append(
            PromotableTicket(
                ref=t.ref,
                subject=t.subject,
                snippet=t.complaint[:160],
                category=t.category.name if t.category else None,
                severity=t.severity,
                resolved_at=t.resolved_at,
                resolved_by=t.resolved_by.full_name if t.resolved_by else None,
                steps=t.resolution_steps or [],
                feedback=feedback,
                analyst_verdict=verdict,
            )
        )
    return out


@router.post("/tickets/promote")
def promote(body: PromoteIn, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)):
    refs = [r.upper() for r in body.refs]
    #sql: SELECT * FROM tickets WHERE ref IN (:refs) AND status = 'resolved' AND is_searchable = false
    tickets = db.scalars(
        select(Ticket).where(Ticket.ref.in_(refs), Ticket.status == "resolved", Ticket.is_searchable.is_(False))
    ).all()
    promoted, skipped = [], []
    for ticket in tickets:
        digest = content_hash(ticket.complaint, ticket.resolution_steps or [])
        #sql: SELECT id FROM tickets WHERE content_hash = :digest
        if db.scalar(select(Ticket.id).where(Ticket.content_hash == digest)):
            skipped.append(ticket.ref)  #an identical ticket is already searchable
            continue
        promote_ticket(db, ticket)
        promoted.append(ticket.ref)
    audit.record(db, user, "data.promote", "ticket", None, promoted=promoted, skipped=skipped)
    db.commit()
    return {"promoted": promoted, "skipped": skipped}
