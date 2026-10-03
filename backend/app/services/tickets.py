"""Ticket queries and the rules for what each role is allowed to see."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Analysis, Feedback, ReviewDecision, Ticket, User
from app.schemas import (
    AnalysisOut,
    CategoryBrief,
    ReviewDecisionOut,
    TicketDetail,
    TicketListItem,
    UserBrief,
)

#agents never see a draft an admin hasn't signed off yet, or one that was rejected
HIDDEN_FOR_AGENTS = ("pending_review", "rejected")


def get_by_ref(db: Session, ref: str) -> Ticket | None:
    #sql: SELECT * FROM tickets WHERE ref = :ref
    return db.scalar(select(Ticket).where(Ticket.ref == ref.upper()))


def latest_analysis(db: Session, ticket_id: int) -> Analysis | None:
    #sql: SELECT * FROM analyses WHERE ticket_id = :ticket_id ORDER BY id DESC LIMIT 1
    return db.scalar(
        select(Analysis).where(Analysis.ticket_id == ticket_id).order_by(Analysis.id.desc()).limit(1)
    )


def latest_decision(db: Session, analysis_id: int) -> ReviewDecision | None:
    #sql: SELECT * FROM review_decisions WHERE analysis_id = :analysis_id ORDER BY id DESC LIMIT 1
    return db.scalar(
        select(ReviewDecision)
        .where(ReviewDecision.analysis_id == analysis_id)
        .order_by(ReviewDecision.id.desc())
        .limit(1)
    )


def can_edit(ticket: Ticket, user: User) -> bool:
    return user.role == "admin" or ticket.created_by_id == user.id


def visible_steps(analysis: Analysis) -> list[dict]:
    if analysis.final_steps:
        return analysis.final_steps
    return analysis.draft.get("steps", []) if analysis.draft else []


def analysis_out(db: Session, analysis: Analysis, user: User) -> AnalysisOut:
    hidden = user.role == "support_agent" and analysis.review_status in HIDDEN_FOR_AGENTS
    draft = analysis.draft or {}
    decision = latest_decision(db, analysis.id)
    #sql: SELECT rating FROM feedback WHERE analysis_id = :analysis_id AND user_id = :user_id
    my_feedback = db.scalar(
        select(Feedback.rating).where(Feedback.analysis_id == analysis.id, Feedback.user_id == user.id)
    )
    return AnalysisOut(
        id=analysis.id,
        parsed=analysis.parsed or {},
        retrieved=analysis.retrieved or [],
        draft={} if hidden else draft,
        draft_hidden=hidden,
        steps=[] if hidden else visible_steps(analysis),
        outcome=analysis.outcome,
        abstain_reason=analysis.abstain_reason,
        citation_check=analysis.citation_check or {},
        review_status=analysis.review_status,
        decision=ReviewDecisionOut(
            action=decision.action,
            comment=decision.comment,
            admin=decision.admin.full_name,
            created_at=decision.created_at,
        )
        if decision
        else None,
        my_feedback=my_feedback,
        latency_ms=analysis.latency_ms,
        timings=analysis.timings or {},
        prompt_tokens=analysis.prompt_tokens,
        completion_tokens=analysis.completion_tokens,
        cost_usd=float(analysis.cost_usd or 0),
        model=analysis.model,
        trace_id=analysis.trace_id,
        created_at=analysis.created_at,
    )


def ticket_detail(db: Session, ticket: Ticket, user: User) -> TicketDetail:
    analysis = latest_analysis(db, ticket.id)
    return TicketDetail(
        id=ticket.id,
        ref=ticket.ref,
        subject=ticket.subject,
        complaint=ticket.complaint,
        customer_ref=ticket.customer_ref,
        channel=ticket.channel,
        city=ticket.city,
        product_hint=ticket.product_hint,
        status=ticket.status,
        source=ticket.source,
        severity=ticket.severity,
        critical_reason=ticket.critical_reason,
        sentiment=ticket.sentiment,
        product=ticket.product,
        language=ticket.language,
        category=CategoryBrief.model_validate(ticket.category) if ticket.category else None,
        tags=ticket.tags or [],
        resolution_steps=ticket.resolution_steps or [],
        resolution_summary=ticket.resolution_summary,
        is_searchable=ticket.is_searchable,
        created_by=UserBrief.model_validate(ticket.created_by) if ticket.created_by else None,
        created_at=ticket.created_at,
        resolved_at=ticket.resolved_at,
        analysis=analysis_out(db, analysis, user) if analysis else None,
        can_edit=can_edit(ticket, user),
    )


def list_item(ticket: Ticket, review_status: str | None) -> TicketListItem:
    return TicketListItem(
        id=ticket.id,
        ref=ticket.ref,
        subject=ticket.subject,
        snippet=ticket.complaint[:140],
        status=ticket.status,
        severity=ticket.severity,
        sentiment=ticket.sentiment,
        product=ticket.product,
        category=CategoryBrief.model_validate(ticket.category) if ticket.category else None,
        review_status=review_status,
        source=ticket.source,
        created_at=ticket.created_at,
        created_by=ticket.created_by.full_name if ticket.created_by else None,
    )
