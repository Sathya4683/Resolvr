"""
Analyst quality reviews. This doesn't block anyone (unlike admin approval), it measures how good
the assistant is and feeds corrections back as guidance for similar complaints.

Locking: an analyst "claims" an analysis before reviewing it. The claim is one conditional UPDATE,
so if two analysts open the same item at the same moment only one of them gets it.
Claims expire after LOCK_MINUTES so an abandoned tab doesn't block the item forever.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import embeddings
from app.config import settings
from app.db import get_db
from app.deps import analyst_or_admin, require_roles
from app.models import Analysis, AnalystReview, Category, Feedback, Ticket, User
from app.pipeline.pii import redact
from app.schemas import AnalystReviewIn, AnalystReviewOut, QueueItem, TicketDetail
from app.services import audit
from app.services import tickets as ticket_service

router = APIRouter(prefix="/reviews", tags=["analyst reviews"])
analyst_only = require_roles("analyst")

LOCK_MINUTES = 15
LABEL_FIELDS = ("category", "product", "severity", "sentiment")


def lock_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=LOCK_MINUTES)


def is_locked_by_other(analysis: Analysis, user: User) -> bool:
    return (
        analysis.claimed_by_id is not None
        and analysis.claimed_by_id != user.id
        and analysis.claimed_at is not None
        and analysis.claimed_at > lock_cutoff()
    )


@router.get("/queue", response_model=list[QueueItem])
def review_queue(db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)):
    """
    a sample instead of everything: items most likely to show problems come first
    (thumbs down, abstained, critical, low confidence), then the most recent ones
    """
    reviewed = exists().where(AnalystReview.analysis_id == Analysis.id)
    thumbs_down = exists().where(Feedback.analysis_id == Analysis.id, Feedback.rating == "down")
    #sql: SELECT analyses.*, EXISTS (SELECT 1 FROM feedback WHERE analysis_id = analyses.id AND rating = 'down')
    #     FROM analyses
    #     WHERE NOT EXISTS (SELECT 1 FROM analyst_reviews WHERE analysis_id = analyses.id)
    #       AND review_status <> 'pending_review'
    #     ORDER BY created_at DESC LIMIT 200
    rows = db.execute(
        select(Analysis, thumbs_down.label("thumbs_down"))
        .where(~reviewed, Analysis.review_status != "pending_review")
        .order_by(Analysis.created_at.desc())
        .limit(200)
    ).all()

    items = []
    for analysis, down in rows:
        ticket = analysis.ticket
        reasons = []
        if down:
            reasons.append("thumbs down")
        if analysis.outcome == "abstained":
            reasons.append("abstained")
        if ticket.severity == "critical":
            reasons.append("critical")
        if (analysis.confidence or 0) < 0.6 and analysis.outcome == "drafted":
            reasons.append("low confidence")
        if analysis.citation_check.get("retried"):
            reasons.append("citation retry")
        if not reasons:
            reasons.append("random sample")
        items.append(
            QueueItem(
                analysis_id=analysis.id,
                ticket_ref=ticket.ref,
                subject=ticket.subject,
                snippet=ticket.complaint[:180],
                severity=ticket.severity,
                category=ticket.category.name if ticket.category else None,
                outcome=analysis.outcome,
                review_status=analysis.review_status,
                reasons=reasons,
                confidence=analysis.confidence,
                created_at=analysis.created_at,
                claimed_by=analysis.claimed_by.full_name if is_locked_by_other(analysis, user) else None,
                locked=is_locked_by_other(analysis, user),
            )
        )
    priority = {"thumbs down": 0, "abstained": 1, "critical": 2, "low confidence": 3, "citation retry": 4}
    items.sort(key=lambda i: min(priority.get(r, 9) for r in i.reasons))
    return items[:50]


@router.post("/{analysis_id}/claim", response_model=TicketDetail)
def claim(analysis_id: int, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    #one atomic statement, so two analysts can never both win the same item
    #sql: UPDATE analyses SET claimed_by_id = :me, claimed_at = now()
    #     WHERE id = :analysis_id
    #       AND (claimed_by_id IS NULL OR claimed_by_id = :me OR claimed_at < now() - interval '15 minutes')
    #       AND NOT EXISTS (SELECT 1 FROM analyst_reviews WHERE analysis_id = :analysis_id)
    #     RETURNING id
    result = db.execute(
        update(Analysis)
        .where(
            Analysis.id == analysis_id,
            or_(
                Analysis.claimed_by_id.is_(None),
                Analysis.claimed_by_id == user.id,
                Analysis.claimed_at < lock_cutoff(),
            ),
            ~exists().where(AnalystReview.analysis_id == analysis_id),
        )
        .values(claimed_by_id=user.id, claimed_at=func.now())
        .returning(Analysis.id)
    )
    if result.scalar() is None:
        db.rollback()
        #sql: SELECT * FROM analyses WHERE id = :analysis_id
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        #sql: SELECT id FROM analyst_reviews WHERE analysis_id = :analysis_id
        if db.scalar(select(AnalystReview.id).where(AnalystReview.analysis_id == analysis_id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "This one has already been reviewed")
        who = analysis.claimed_by.full_name if analysis.claimed_by else "another analyst"
        raise HTTPException(status.HTTP_409_CONFLICT, f"{who} is reviewing this right now")
    db.commit()

    analysis = db.get(Analysis, analysis_id)
    #analysts see the full draft, so render the ticket as an admin would
    return ticket_service.ticket_detail(db, analysis.ticket, user)


@router.post("/{analysis_id}/release", status_code=204)
def release(analysis_id: int, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    #sql: UPDATE analyses SET claimed_by_id = NULL, claimed_at = NULL WHERE id = :id AND claimed_by_id = :me
    db.execute(
        update(Analysis)
        .where(Analysis.id == analysis_id, Analysis.claimed_by_id == user.id)
        .values(claimed_by_id=None, claimed_at=None)
    )
    db.commit()


def guidance_text(ticket: Ticket, analysis: Analysis, corrected: dict, notes: str | None) -> str | None:
    """short note that later shows up in prompts for similar complaints"""
    parts = []
    for field, value in corrected.items():
        parts.append(f"{field} should be '{value}' (the assistant said '{analysis.parsed.get(field)}')")
    if notes:
        parts.append(notes.strip())
    if not parts:
        return None
    summary = analysis.parsed.get("summary") or ticket.complaint[:200]
    return f"For complaints like \"{summary}\": " + "; ".join(parts)


@router.post("/{analysis_id}", response_model=AnalystReviewOut, status_code=201)
def submit_review(
    analysis_id: int, body: AnalystReviewIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)
):
    #sql: SELECT * FROM analyses WHERE id = :analysis_id FOR UPDATE OF analyses
    analysis = db.scalar(select(Analysis).where(Analysis.id == analysis_id).with_for_update(of=Analysis))
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    if analysis.claimed_by_id != user.id or (analysis.claimed_at and analysis.claimed_at < lock_cutoff()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Open the item again to claim it before submitting")

    ticket = analysis.ticket
    original = {
        "category": analysis.parsed.get("category"),
        "product": ticket.product,
        "severity": ticket.severity,
        "sentiment": ticket.sentiment,
    }
    corrections = body.corrections.model_dump(exclude_none=True)
    if "category" in corrections:
        #sql: SELECT id FROM categories WHERE slug = :slug
        if not db.scalar(select(Category.id).where(Category.slug == corrections["category"])):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown category")
    #only keep the fields the analyst actually changed
    corrected = {k: v for k, v in corrections.items() if k in LABEL_FIELDS and v != original.get(k)}

    text = guidance_text(ticket, analysis, corrected, body.notes)
    review = AnalystReview(
        analysis_id=analysis.id,
        analyst_id=user.id,
        verdict=body.verdict,
        citations_ok=body.citations_ok,
        rubric=body.rubric.model_dump(),
        original_labels=original,
        corrected_labels=corrected,
        notes=body.notes,
        guidance_text=text,
    )
    if text:
        #we embed the complaint the note is about (not the note), so a similar new complaint finds it
        review.embedding = embeddings.embed_query(redact(ticket.complaint)[0])
        review.embedding_model = settings.embedding_model
    db.add(review)
    analysis.claimed_by_id = None
    analysis.claimed_at = None
    audit.record(db, user, "review.submit", "ticket", ticket.ref, verdict=body.verdict, corrected=list(corrected))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This one has already been reviewed") from None
    return review_out(review)


def review_out(r: AnalystReview) -> AnalystReviewOut:
    return AnalystReviewOut(
        id=r.id,
        analysis_id=r.analysis_id,
        ticket_ref=r.analysis.ticket.ref,
        analyst=r.analyst.full_name,
        verdict=r.verdict,
        citations_ok=r.citations_ok,
        rubric=r.rubric,
        original_labels=r.original_labels,
        corrected_labels=r.corrected_labels,
        notes=r.notes,
        created_at=r.created_at,
    )


@router.get("", response_model=list[AnalystReviewOut])
def list_reviews(
    mine: bool = False, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)
):
    #sql: SELECT * FROM analyst_reviews WHERE analyst_id = :me ORDER BY created_at DESC LIMIT :limit
    stmt = select(AnalystReview).order_by(AnalystReview.created_at.desc()).limit(min(limit, 500))
    if mine:
        stmt = stmt.where(AnalystReview.analyst_id == user.id)
    return [review_out(r) for r in db.scalars(stmt)]

