from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import admin_only, analyst_or_admin
from app.models import Analysis, AnalystReview, AuditLog, Category, Feedback, KbArticle, Ticket, User

router = APIRouter(tags=["admin"])


def local_midnight(days_ago: int = 0) -> datetime:
    tz = ZoneInfo(settings.app_timezone)
    day = datetime.now(tz).date() - timedelta(days=days_ago)
    return datetime.combine(day, time.min, tzinfo=tz)


@router.get("/admin/overview")
def overview(days: int = Query(default=7, ge=1, le=60), db: Session = Depends(get_db), _: User = Depends(admin_only)):
    today = local_midnight()
    since = local_midnight(days - 1)
    tz = settings.app_timezone

    # sql: SELECT count(*) FROM tickets WHERE created_at >= :today
    created_today = db.scalar(select(func.count(Ticket.id)).where(Ticket.created_at >= today))
    # sql: SELECT count(*) FROM tickets WHERE resolved_at >= :today
    resolved_today = db.scalar(select(func.count(Ticket.id)).where(Ticket.resolved_at >= today))
    # sql: SELECT count(*) FROM analyses WHERE review_status = 'pending_review'
    pending = db.scalar(select(func.count(Analysis.id)).where(Analysis.review_status == "pending_review"))
    # sql: SELECT count(*) FROM tickets WHERE is_searchable = true
    searchable = db.scalar(select(func.count(Ticket.id)).where(Ticket.is_searchable.is_(True)))
    # sql: SELECT count(*) FROM kb_articles WHERE status = 'published'
    kb_count = db.scalar(select(func.count(KbArticle.id)).where(KbArticle.status == "published"))

    # sql: SELECT count(*), count(*) FILTER (WHERE outcome = 'abstained'), avg(latency_ms),
    #            sum(prompt_tokens + completion_tokens), sum(cost_usd)
    #     FROM analyses WHERE created_at >= :since
    stats = db.execute(
        select(
            func.count(Analysis.id),
            func.count(Analysis.id).filter(Analysis.outcome == "abstained"),
            func.avg(Analysis.latency_ms),
            func.coalesce(func.sum(Analysis.prompt_tokens + Analysis.completion_tokens), 0),
            func.coalesce(func.sum(Analysis.cost_usd), 0),
        ).where(Analysis.created_at >= since)
    ).one()

    # sql: SELECT count(*) FILTER (WHERE rating = 'up'), count(*) FROM feedback WHERE created_at >= :since
    up, total_feedback = db.execute(
        select(func.count(Feedback.id).filter(Feedback.rating == "up"), func.count(Feedback.id)).where(
            Feedback.created_at >= since
        )
    ).one()

    # sql: SELECT count(*) FILTER (WHERE verdict = 'correct'), count(*) FROM analyst_reviews
    correct, reviewed = db.execute(
        select(func.count(AnalystReview.id).filter(AnalystReview.verdict == "correct"), func.count(AnalystReview.id))
    ).one()

    day = func.date(func.timezone(tz, Ticket.created_at))
    # sql: SELECT date(timezone(:tz, created_at)) AS day, severity, count(*) FROM tickets
    #     WHERE created_at >= :since GROUP BY day, severity ORDER BY day
    per_day: dict[str, dict] = {}
    for d, severity, n in db.execute(
        select(day, Ticket.severity, func.count(Ticket.id))
        .where(Ticket.created_at >= since)
        .group_by(day, Ticket.severity)
        .order_by(day)
    ):
        row = per_day.setdefault(d.isoformat(), {"day": d.isoformat(), "low": 0, "medium": 0, "high": 0, "critical": 0})
        if severity in row:
            row[severity] = n

    # sql: SELECT categories.name, count(tickets.id) FROM tickets JOIN categories ON ...
    #     WHERE tickets.created_at >= :since GROUP BY categories.name ORDER BY count DESC LIMIT 8
    categories = [
        {"name": name, "count": n}
        for name, n in db.execute(
            select(Category.name, func.count(Ticket.id))
            .join(Category, Category.id == Ticket.category_id)
            .where(Ticket.created_at >= since)
            .group_by(Category.name)
            .order_by(func.count(Ticket.id).desc())
            .limit(8)
        )
    ]

    # sql: SELECT sentiment, count(*) FROM tickets WHERE created_at >= :since GROUP BY sentiment
    sentiment = {
        s or "unknown": n
        for s, n in db.execute(
            select(Ticket.sentiment, func.count(Ticket.id)).where(Ticket.created_at >= since).group_by(Ticket.sentiment)
        )
    }

    # sql: SELECT outcome, count(*) FROM analyses WHERE created_at >= :since GROUP BY outcome
    outcomes = dict(
        db.execute(
            select(Analysis.outcome, func.count(Analysis.id))
            .where(Analysis.created_at >= since)
            .group_by(Analysis.outcome)
        ).all()
    )

    return {
        "kpis": {
            "created_today": created_today,
            "resolved_today": resolved_today,
            "pending_approvals": pending,
            "searchable_tickets": searchable,
            "kb_articles": kb_count,
            "analyses": stats[0],
            "abstention_rate": (stats[1] / stats[0]) if stats[0] else None,
            "avg_latency_ms": round(stats[2]) if stats[2] else None,
            "tokens": int(stats[3]),
            "cost_usd": float(stats[4]),
            "thumbs_up_rate": (up / total_feedback) if total_feedback else None,
            "feedback_count": total_feedback,
            "analyst_accuracy": (correct / reviewed) if reviewed else None,
            "analyst_reviews": reviewed,
        },
        "per_day": list(per_day.values()),
        "categories": categories,
        "sentiment": sentiment,
        "outcomes": outcomes,
    }


@router.get("/audit")
def audit_log(
    action: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    # sql: SELECT * FROM audit_logs WHERE action LIKE :action || '%' ORDER BY id DESC LIMIT :limit
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    return [
        {
            "id": a.id,
            "action": a.action,
            "user": a.user.full_name if a.user else "system",
            "role": a.user.role if a.user else None,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "details": a.details,
            "created_at": a.created_at,
        }
        for a in db.scalars(stmt)
    ]


@router.get("/quality/summary")
def quality_summary(db: Session = Depends(get_db), _: User = Depends(analyst_or_admin)):
    """numbers for the quality page, analysts and admins both see it"""
    # sql: SELECT verdict, count(*) FROM analyst_reviews GROUP BY verdict
    verdicts = dict(
        db.execute(select(AnalystReview.verdict, func.count(AnalystReview.id)).group_by(AnalystReview.verdict)).all()
    )
    # sql: SELECT count(*) FILTER (WHERE citations_ok), count(*) FROM analyst_reviews
    cites_ok, total = db.execute(
        select(func.count(AnalystReview.id).filter(AnalystReview.citations_ok.is_(True)), func.count(AnalystReview.id))
    ).one()
    # sql: SELECT rating, count(*) FROM feedback GROUP BY rating
    feedback = dict(db.execute(select(Feedback.rating, func.count(Feedback.id)).group_by(Feedback.rating)).all())
    # sql: SELECT review_status, count(*) FROM analyses GROUP BY review_status
    review = dict(
        db.execute(select(Analysis.review_status, func.count(Analysis.id)).group_by(Analysis.review_status)).all()
    )

    # per field agreement: a label counts as agreed when the analyst didn't correct it
    fields = ("category", "product", "severity", "sentiment")
    agreement = {}
    rows = db.scalars(select(AnalystReview.corrected_labels)).all()
    for f in fields:
        agreement[f] = (sum(1 for r in rows if f not in (r or {})) / len(rows)) if rows else None

    # sql: SELECT categories.name, count(*), count(*) FILTER (WHERE verdict = 'correct')
    #     FROM analyst_reviews JOIN analyses ... JOIN tickets ... JOIN categories ... GROUP BY categories.name
    by_category = [
        {"category": name, "reviews": n, "correct": c}
        for name, n, c in db.execute(
            select(
                Category.name,
                func.count(AnalystReview.id),
                func.sum(case((AnalystReview.verdict == "correct", 1), else_=0)),
            )
            .join(Analysis, Analysis.id == AnalystReview.analysis_id)
            .join(Ticket, Ticket.id == Analysis.ticket_id)
            .join(Category, Category.id == Ticket.category_id)
            .group_by(Category.name)
            .order_by(func.count(AnalystReview.id).desc())
        )
    ]
    return {
        "verdicts": verdicts,
        "reviews": total,
        "citations_ok_rate": (cites_ok / total) if total else None,
        "agreement": agreement,
        "feedback": feedback,
        "review_status": review,
        "by_category": by_category,
    }
