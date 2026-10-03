from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import metrics
from app.db import get_db
from app.deps import agent_or_admin, any_user
from app.models import Analysis, Feedback, Ticket, User
from app.pipeline.analyze import run_analysis
from app.ratelimit import rate_limit
from app.schemas import FeedbackIn, ResolveIn, TicketCreate, TicketDetail, TicketListItem
from app.services import audit, notify
from app.services import tickets as ticket_service

router = APIRouter(tags=["tickets"])


def load_ticket(db: Session, ref: str) -> Ticket:
    ticket = ticket_service.get_by_ref(db, ref)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


@router.post("/tickets", response_model=TicketDetail, status_code=201, dependencies=[Depends(rate_limit("analyze"))])
def create_ticket(
    body: TicketCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(agent_or_admin),
):
    """an agent pastes a complaint, we save it and run the full analysis straight away"""
    ticket = Ticket(
        complaint=body.complaint.strip(),
        subject=body.subject,
        customer_ref=body.customer_ref,
        channel=body.channel,
        product_hint=body.product_hint,
        source="agent",
        status="open",
        created_by_id=user.id,
    )
    db.add(ticket)
    db.flush()
    analysis = run_analysis(db, ticket, user)
    audit.record(db, user, "ticket.create", "ticket", ticket.ref, severity=ticket.severity)
    alerts = notify.after_analysis(db, ticket, analysis)
    db.commit()
    #push + email go out after the response so the agent isn't kept waiting
    background.add_task(notify.dispatch, alerts)
    db.refresh(ticket)
    return ticket_service.ticket_detail(db, ticket, user)


@router.get("/tickets", response_model=list[TicketListItem])
def list_tickets(
    scope: Literal["mine", "all"] = "mine",
    status_: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=60, le=300),
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(any_user),
):
    latest_status = (
        select(Analysis.review_status)
        .where(Analysis.ticket_id == Ticket.id)
        .order_by(Analysis.id.desc())
        .limit(1)
        .correlate(Ticket)
        .scalar_subquery()
    )
    #sql: SELECT tickets.*,
    #       (SELECT review_status FROM analyses WHERE analyses.ticket_id = tickets.id
    #        ORDER BY id DESC LIMIT 1) AS review_status
    #     FROM tickets
    #     WHERE created_by_id = :me            -- only for scope=mine
    #       AND status = :status AND severity = :severity
    #       AND (ref ILIKE :q OR subject ILIKE :q OR complaint ILIKE :q)
    #     ORDER BY created_at DESC LIMIT :limit OFFSET :offset
    stmt = select(Ticket, latest_status.label("review_status"))
    if scope == "mine":
        stmt = stmt.where(Ticket.created_by_id == user.id)
    if status_:
        stmt = stmt.where(Ticket.status == status_)
    if severity:
        stmt = stmt.where(Ticket.severity == severity)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Ticket.ref.ilike(like), Ticket.subject.ilike(like), Ticket.complaint.ilike(like)))
    stmt = stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    return [ticket_service.list_item(t, review_status) for t, review_status in db.execute(stmt)]


@router.get("/tickets/{ref}", response_model=TicketDetail)
def get_ticket(ref: str, db: Session = Depends(get_db), user: User = Depends(any_user)):
    return ticket_service.ticket_detail(db, load_ticket(db, ref), user)


@router.post("/tickets/{ref}/reanalyze", response_model=TicketDetail, dependencies=[Depends(rate_limit("analyze"))])
def reanalyze(
    ref: str, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)
):
    ticket = load_ticket(db, ref)
    if not ticket_service.can_edit(ticket, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the agent who raised this ticket can re-run it")
    if ticket.status == "resolved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is already resolved")
    analysis = run_analysis(db, ticket, user)
    audit.record(db, user, "ticket.reanalyze", "ticket", ticket.ref)
    alerts = notify.after_analysis(db, ticket, analysis)
    db.commit()
    background.add_task(notify.dispatch, alerts)
    return ticket_service.ticket_detail(db, ticket, user)


@router.post("/tickets/{ref}/resolve", response_model=TicketDetail)
def resolve(ref: str, body: ResolveIn, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    ticket = load_ticket(db, ref)
    if not ticket_service.can_edit(ticket, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the agent who raised this ticket can resolve it")
    if ticket.status == "resolved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is already resolved")
    if ticket.status == "pending_review":
        raise HTTPException(status.HTTP_409_CONFLICT, "This ticket is waiting for admin approval")

    analysis = ticket_service.latest_analysis(db, ticket.id)
    steps = [s.strip() for s in (body.steps or []) if s.strip()]
    if not steps and analysis and analysis.review_status not in ticket_service.HIDDEN_FOR_AGENTS:
        steps = [s["text"] for s in ticket_service.visible_steps(analysis)]
    if not steps:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Add the steps you took to resolve it")

    ticket.resolution_steps = steps
    ticket.resolution_summary = body.summary or (analysis.parsed.get("summary") if analysis else None)
    ticket.status = "resolved"
    ticket.resolved_at = datetime.now(timezone.utc)
    ticket.resolved_by_id = user.id
    audit.record(db, user, "ticket.resolve", "ticket", ticket.ref, steps=len(steps))
    db.commit()
    return ticket_service.ticket_detail(db, ticket, user)


@router.post("/analyses/{analysis_id}/feedback", status_code=204)
def give_feedback(
    analysis_id: int, body: FeedbackIn, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)
):
    #sql: SELECT * FROM analyses WHERE id = :analysis_id
    if db.get(Analysis, analysis_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    #sql: SELECT * FROM feedback WHERE analysis_id = :analysis_id AND user_id = :user_id
    feedback = db.scalar(
        select(Feedback).where(Feedback.analysis_id == analysis_id, Feedback.user_id == user.id)
    )
    if feedback is None:
        feedback = Feedback(analysis_id=analysis_id, user_id=user.id)
        db.add(feedback)
    feedback.rating = body.rating
    feedback.comment = body.comment
    db.commit()
    metrics.FEEDBACK.labels(body.rating).inc()
