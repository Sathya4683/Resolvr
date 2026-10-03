"""
PDF reports (ReportLab):
  - daily digest: what happened on the desk on one day, emailed to admins every evening
  - quality report: analyst reviews over a date range, the "evaluation" report
"""

import io
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Analysis, AnalystReview, AuditLog, Feedback, ReviewDecision, Ticket
from app.pipeline.pii import redact

ACCENT = colors.HexColor("#4f46e5")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#e5e7eb")
HEADER_BG = colors.HexColor("#f3f4f6")

_styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_styles["Heading1"], fontSize=18, spaceAfter=2, textColor=colors.HexColor("#111827"))
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=12.5, spaceBefore=12, spaceAfter=6, textColor=ACCENT)
BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontSize=9, leading=12, alignment=TA_LEFT)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10, textColor=MUTED)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8, leading=10)


def day_window(day: date) -> tuple[datetime, datetime]:
    """start and end of a day in the app timezone, the end is capped at "now" for today"""
    tz = ZoneInfo(settings.app_timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = min(start + timedelta(days=1), datetime.now(timezone.utc).astimezone(tz))
    return start, end


def _table(rows: list[list], widths: list[float], header: bool = True) -> Table:
    data = [[Paragraph(str(c), CELL) if not isinstance(c, Paragraph) else c for c in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), HEADER_BG))
    t.setStyle(TableStyle(style))
    return t


def _kv_table(pairs: list[tuple[str, object]]) -> Table:
    #two key/value columns side by side, reads like a summary card
    half = (len(pairs) + 1) // 2
    left, right = pairs[:half], pairs[half:]
    rows = []
    for i in range(half):
        row = [left[i][0], f"<b>{left[i][1]}</b>"]
        row += [right[i][0], f"<b>{right[i][1]}</b>"] if i < len(right) else ["", ""]
        rows.append(row)
    return _table(rows, [50 * mm, 35 * mm, 50 * mm, 35 * mm], header=False)


def _render(story: list, title: str) -> bytes:
    buf = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, f"Resolvr · {title}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title,
        author="Resolvr",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def pct(n: int, d: int) -> str:
    return f"{n / d:.0%}" if d else "-"


#---------------- daily digest ----------------


def digest_numbers(db: Session, day: date) -> dict:
    start, end = day_window(day)
    in_day = lambda col: (col >= start) & (col < end)  # noqa: E731

    #sql: SELECT count(*) FROM tickets WHERE created_at >= :start AND created_at < :end
    created = db.scalar(select(func.count(Ticket.id)).where(in_day(Ticket.created_at)))
    #sql: SELECT * FROM tickets WHERE resolved_at >= :start AND resolved_at < :end ORDER BY resolved_at
    resolved = db.scalars(select(Ticket).where(in_day(Ticket.resolved_at)).order_by(Ticket.resolved_at)).all()
    #sql: SELECT * FROM analyses WHERE created_at >= :start AND created_at < :end
    analyses = db.scalars(select(Analysis).where(in_day(Analysis.created_at))).all()
    #sql: SELECT severity, category_id, sentiment FROM tickets WHERE created_at in the window
    day_tickets = db.execute(
        select(Ticket.severity, Ticket.sentiment, Ticket.category_id).where(in_day(Ticket.created_at))
    ).all()
    #sql: SELECT * FROM review_decisions WHERE created_at >= :start AND created_at < :end
    decisions = db.scalars(select(ReviewDecision).where(in_day(ReviewDecision.created_at))).all()
    #sql: SELECT rating, count(*) FROM feedback WHERE created_at in the window GROUP BY rating
    feedback = dict(
        db.execute(
            select(Feedback.rating, func.count(Feedback.id))
            .where(in_day(Feedback.created_at))
            .group_by(Feedback.rating)
        ).all()
    )
    #sql: SELECT * FROM audit_logs WHERE action = 'outage.detected' AND created_at in the window
    outages = db.scalars(
        select(AuditLog).where(AuditLog.action == "outage.detected", in_day(AuditLog.created_at))
    ).all()
    #sql: SELECT count(*) FROM analyses WHERE review_status = 'pending_review'
    pending = db.scalar(select(func.count(Analysis.id)).where(Analysis.review_status == "pending_review"))

    resolved_categories = Counter(t.category.name if t.category else "Uncategorised" for t in resolved)
    return {
        "day": day,
        "start": start,
        "end": end,
        "created": created,
        "resolved": resolved,
        "analyses": analyses,
        "severity": Counter(s or "unrated" for s, _, _ in day_tickets),
        "sentiment": Counter(s or "unknown" for _, s, _ in day_tickets),
        "resolved_categories": resolved_categories,
        "decisions": decisions,
        "feedback": feedback,
        "outages": outages,
        "pending": pending,
    }


def build_digest_pdf(db: Session, day: date) -> bytes:
    n = digest_numbers(db, day)
    analyses = n["analyses"]
    abstained = [a for a in analyses if a.outcome == "abstained"]
    tokens = sum(a.prompt_tokens + a.completion_tokens for a in analyses)
    cost = sum(float(a.cost_usd or 0) for a in analyses)
    up, down = n["feedback"].get("up", 0), n["feedback"].get("down", 0)
    title = f"Daily digest - {day:%a %d %b %Y}"

    story = [
        Paragraph(f"Resolvr daily digest · {day:%A, %d %B %Y}", H1),
        Paragraph(
            f"Window {n['start']:%d %b %H:%M} to {n['end']:%d %b %H:%M} ({settings.app_timezone}). "
            f"Generated {datetime.now(ZoneInfo(settings.app_timezone)):%d %b %Y %H:%M}.",
            SMALL,
        ),
        Spacer(1, 8),
        Paragraph("Summary", H2),
        _kv_table(
            [
                ("Tickets received", n["created"]),
                ("Tickets resolved", len(n["resolved"])),
                ("AI analyses run", len(analyses)),
                ("Critical tickets", n["severity"].get("critical", 0)),
                ("Admin decisions", len(n["decisions"])),
                ("Waiting for approval (now)", n["pending"]),
                ("Abstained (no evidence)", f"{len(abstained)} ({pct(len(abstained), len(analyses))})"),
                ("Agent thumbs up / down", f"{up} / {down}"),
                ("Possible outages detected", len(n["outages"])),
                ("LLM tokens / est. cost", f"{tokens:,} / ${cost:.4f}"),
            ]
        ),
        Paragraph("Severity and sentiment of new tickets", H2),
        _table(
            [["Severity", "Count", "Sentiment", "Count"]]
            + [
                [s.title(), n["severity"].get(s, 0), m.title(), n["sentiment"].get(m, 0)]
                for s, m in zip(["low", "medium", "high", "critical"], ["positive", "neutral", "frustrated", "angry"])
            ],
            [45 * mm, 40 * mm, 45 * mm, 40 * mm],
        ),
    ]

    if n["resolved_categories"]:
        story += [
            Paragraph("Resolved tickets by category", H2),
            _table(
                [["Category", "Resolved"]] + [[c, k] for c, k in n["resolved_categories"].most_common(12)],
                [130 * mm, 40 * mm],
            ),
        ]

    if n["decisions"]:
        rows = [["Ticket", "Reason", "Decision", "Admin", "Note"]]
        for d in n["decisions"]:
            #sql: SELECT tickets.* FROM tickets JOIN analyses ON analyses.ticket_id = tickets.id
            #     WHERE analyses.id = :id
            ticket = db.scalar(
                select(Ticket).join(Analysis, Analysis.ticket_id == Ticket.id).where(Analysis.id == d.analysis_id)
            )
            rows.append(
                [ticket.ref, (ticket.critical_reason or "-").title(), d.action, d.admin.full_name, d.comment or "-"]
            )
        story += [Paragraph("Critical case decisions", H2), _table(rows, [25 * mm, 25 * mm, 20 * mm, 30 * mm, 70 * mm])]

    if n["outages"]:
        rows = [["Detected at", "Tickets in the cluster"]]
        rows += [
            [f"{o.created_at.astimezone(ZoneInfo(settings.app_timezone)):%H:%M}", ", ".join(o.details.get("refs", []))]
            for o in n["outages"]
        ]
        story += [Paragraph("Possible outages", H2), _table(rows, [30 * mm, 140 * mm])]

    #knowledge gaps: what the assistant couldn't answer or agents didn't like
    gap_ids = {a.id for a in abstained}
    #sql: SELECT analysis_id FROM feedback WHERE rating = 'down' AND created_at in the window
    gap_ids |= set(
        db.scalars(
            select(Feedback.analysis_id).where(
                Feedback.rating == "down", Feedback.created_at >= n["start"], Feedback.created_at < n["end"]
            )
        )
    )
    if gap_ids:
        rows = [["Ticket", "Why", "Complaint (masked)"]]
        for a in analyses:
            if a.id in gap_ids:
                why = "abstained" if a.outcome == "abstained" else "thumbs down"
                rows.append([a.ticket.ref, why, redact(a.ticket.complaint)[0][:160]])
        story += [
            Paragraph("Knowledge gaps (articles worth writing next)", H2),
            _table(rows, [25 * mm, 25 * mm, 120 * mm]),
        ]

    if n["resolved"]:
        rows = [["Ticket", "Category", "Severity", "Resolution summary (masked)"]]
        for t in n["resolved"][:80]:
            summary = t.resolution_summary or (t.resolution_steps[0] if t.resolution_steps else "-")
            rows.append(
                [t.ref, t.category.name if t.category else "-", (t.severity or "-").title(), redact(summary)[0][:180]]
            )
        story += [
            Paragraph(f"Resolved tickets ({len(n['resolved'])})", H2),
            _table(rows, [24 * mm, 42 * mm, 18 * mm, 86 * mm]),
        ]
        if len(n["resolved"]) > 80:
            story.append(Paragraph(f"... and {len(n['resolved']) - 80} more.", SMALL))

    return _render(story, title)


def digest_text(db: Session, day: date) -> str:
    n = digest_numbers(db, day)
    return (
        f"Resolvr daily digest for {day:%A %d %B %Y}\n\n"
        f"Tickets received: {n['created']}\n"
        f"Tickets resolved: {len(n['resolved'])}\n"
        f"AI analyses: {len(n['analyses'])}\n"
        f"Critical cases still waiting for approval: {n['pending']}\n"
        f"Possible outages detected: {len(n['outages'])}\n\n"
        "The full report is attached as a PDF."
    )


#---------------- quality / evaluation report ----------------


def build_quality_pdf(db: Session, start_day: date, end_day: date) -> bytes:
    start, _ = day_window(start_day)
    _, end = day_window(end_day)
    #sql: SELECT * FROM analyst_reviews WHERE created_at >= :start AND created_at < :end ORDER BY created_at
    reviews = db.scalars(
        select(AnalystReview)
        .where(AnalystReview.created_at >= start, AnalystReview.created_at < end)
        .order_by(AnalystReview.created_at)
    ).all()
    #sql: SELECT * FROM analyses WHERE created_at >= :start AND created_at < :end
    analyses = db.scalars(select(Analysis).where(Analysis.created_at >= start, Analysis.created_at < end)).all()
    #sql: SELECT rating, count(*) FROM feedback WHERE created_at in the range GROUP BY rating
    feedback = dict(
        db.execute(
            select(Feedback.rating, func.count(Feedback.id))
            .where(Feedback.created_at >= start, Feedback.created_at < end)
            .group_by(Feedback.rating)
        ).all()
    )

    total = len(reviews)
    verdicts = Counter(r.verdict for r in reviews)
    title = f"Quality report {start_day:%d %b} - {end_day:%d %b %Y}"
    story = [
        Paragraph("Resolvr quality and evaluation report", H1),
        Paragraph(
            f"{start_day:%d %b %Y} to {end_day:%d %b %Y} · from analyst reviews, agent feedback and admin decisions.",
            SMALL,
        ),
        Spacer(1, 8),
        Paragraph("Headline numbers", H2),
        _kv_table(
            [
                ("Analyst reviews", total),
                ("Marked correct", f"{verdicts['correct']} ({pct(verdicts['correct'], total)})"),
                ("Partly correct", f"{verdicts['partially_correct']} ({pct(verdicts['partially_correct'], total)})"),
                ("Incorrect", f"{verdicts['incorrect']} ({pct(verdicts['incorrect'], total)})"),
                ("Citations proper", pct(sum(r.citations_ok for r in reviews), total)),
                ("Analyses in range", len(analyses)),
                ("Abstention rate", pct(sum(a.outcome == "abstained" for a in analyses), len(analyses))),
                ("Citation retries needed", sum(bool(a.citation_check.get("retried")) for a in analyses)),
                ("Agent thumbs up / down", f"{feedback.get('up', 0)} / {feedback.get('down', 0)}"),
                (
                    "Avg analysis latency",
                    f"{sum(a.latency_ms or 0 for a in analyses) / len(analyses) / 1000:.1f}s" if analyses else "-",
                ),
            ]
        ),
    ]

    if total:
        rubric_rows = [["Rubric item", "Pass", "Pass rate"]]
        for key in ("correct", "safe", "actionable", "complete"):
            passed = sum(1 for r in reviews if r.rubric.get(key))
            rubric_rows.append([key.title(), f"{passed}/{total}", pct(passed, total)])
        agree_rows = [["Label", "Analyst agreed", "Agreement"]]
        for field in ("category", "product", "severity", "sentiment"):
            agreed = sum(1 for r in reviews if field not in (r.corrected_labels or {}))
            agree_rows.append([field.title(), f"{agreed}/{total}", pct(agreed, total)])
        story += [
            Paragraph("Rubric pass rates", H2),
            _table(rubric_rows, [70 * mm, 50 * mm, 50 * mm]),
            Paragraph("Label agreement (AI label kept by the analyst)", H2),
            _table(agree_rows, [70 * mm, 50 * mm, 50 * mm]),
        ]

        by_cat: dict[str, list[int]] = {}
        for r in reviews:
            ticket = r.analysis.ticket
            name = ticket.category.name if ticket.category else "Uncategorised"
            stats = by_cat.setdefault(name, [0, 0])
            stats[0] += 1
            stats[1] += r.verdict == "correct"
        story += [
            Paragraph("Accuracy by category", H2),
            _table(
                [["Category", "Reviews", "Correct", "Accuracy"]]
                + [[c, s[0], s[1], pct(s[1], s[0])] for c, s in sorted(by_cat.items(), key=lambda x: -x[1][0])],
                [80 * mm, 30 * mm, 30 * mm, 30 * mm],
            ),
        ]

        rows = [["Ticket", "Analyst", "Verdict", "Corrections", "Notes"]]
        for r in reviews:
            corrections = (
                ", ".join(f"{k}: {r.original_labels.get(k)} -> {v}" for k, v in r.corrected_labels.items()) or "-"
            )
            rows.append(
                [r.analysis.ticket.ref, r.analyst.full_name, r.verdict.replace("_", " "), corrections, r.notes or "-"]
            )
        story += [Paragraph("Individual reviews", H2), _table(rows, [22 * mm, 26 * mm, 22 * mm, 45 * mm, 55 * mm])]
    else:
        story.append(Paragraph("No analyst reviews in this period yet.", BODY))

    return _render(story, title)
