"""
Human review for critical cases. A critical draft is hidden from the agent until an admin
approves it, approves it with edits, or declines it.
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import admin_only
from app.models import Analysis, ReviewDecision, User
from app.schemas import ApprovalItem, DecisionIn, TicketDetail
from app.services import audit, notify
from app.services import tickets as ticket_service

router = APIRouter(prefix="/approvals", tags=["approvals"])

NEW_STATUS = {"approve": "approved", "edit": "edited", "reject": "rejected"}


def to_item(analysis: Analysis, decision: ReviewDecision | None = None) -> ApprovalItem:
    ticket = analysis.ticket
    waited = datetime.now(timezone.utc) - analysis.created_at
    return ApprovalItem(
        analysis_id=analysis.id,
        ticket_ref=ticket.ref,
        subject=ticket.subject,
        snippet=ticket.complaint[:200],
        severity=ticket.severity,
        critical_reason=ticket.critical_reason,
        category=ticket.category.name if ticket.category else None,
        raised_by=ticket.created_by.full_name if ticket.created_by else None,
        created_at=analysis.created_at,
        waiting_minutes=int(waited.total_seconds() // 60),
        review_status=analysis.review_status,
        decided_by=decision.admin.full_name if decision else None,
        decided_at=decision.created_at if decision else None,
        comment=decision.comment if decision else None,
    )


@router.get("/count")
def pending_count(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    #sql: SELECT count(*) FROM analyses WHERE review_status = 'pending_review'
    n = db.scalar(select(func.count(Analysis.id)).where(Analysis.review_status == "pending_review"))
    return {"pending": n}


@router.get("", response_model=list[ApprovalItem])
def list_approvals(
    state: Literal["pending", "decided"] = "pending",
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    if state == "pending":
        #oldest first, those are the closest to breaching the review sla
        #sql: SELECT * FROM analyses WHERE review_status = 'pending_review' ORDER BY created_at ASC
        rows = db.scalars(
            select(Analysis).where(Analysis.review_status == "pending_review").order_by(Analysis.created_at)
        ).all()
        return [to_item(a) for a in rows]

    #sql: SELECT review_decisions.*, analyses.* FROM review_decisions
    #     JOIN analyses ON analyses.id = review_decisions.analysis_id
    #     ORDER BY review_decisions.created_at DESC LIMIT 50
    rows = db.execute(
        select(ReviewDecision, Analysis)
        .join(Analysis, Analysis.id == ReviewDecision.analysis_id)
        .order_by(ReviewDecision.created_at.desc())
        .limit(50)
    ).all()
    return [to_item(analysis, decision) for decision, analysis in rows]


@router.post("/{analysis_id}/decision", response_model=TicketDetail)
def decide(
    analysis_id: int,
    body: DecisionIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_only),
):
    #lock the row so two admins clicking at the same time can't both decide
    #sql: SELECT * FROM analyses WHERE id = :analysis_id FOR UPDATE OF analyses
    analysis = db.scalar(select(Analysis).where(Analysis.id == analysis_id).with_for_update(of=Analysis))
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    if analysis.review_status != "pending_review":
        raise HTTPException(status.HTTP_409_CONFLICT, "This case has already been decided")
    if body.action == "reject" and not (body.comment or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a short reason when declining")

    edited_steps = []
    if body.action == "edit":
        if not body.steps:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Edited steps are required")
        allowed = {s["ref"] for s in analysis.retrieved or []}
        for step in body.steps:
            unknown = [c for c in step.citations if c not in allowed]
            if unknown:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"Citation {unknown[0]} is not one of the retrieved sources"
                )
        edited_steps = [s.model_dump() for s in body.steps]

    analysis.review_status = NEW_STATUS[body.action]
    analysis.final_steps = edited_steps
    ticket = analysis.ticket
    #the agent can now resolve it (or handle it manually if the draft was declined)
    ticket.status = "open"
    db.add(
        ReviewDecision(
            analysis_id=analysis.id,
            admin_id=admin.id,
            action=body.action,
            comment=body.comment,
            edited_steps=edited_steps,
        )
    )
    audit.record(db, admin, f"approval.{body.action}", "ticket", ticket.ref, analysis_id=analysis.id)
    alerts = notify.after_decision(db, ticket, body.action, admin, body.comment)
    db.commit()

    background.add_task(notify.dispatch, alerts)
    return ticket_service.ticket_detail(db, ticket, admin)
