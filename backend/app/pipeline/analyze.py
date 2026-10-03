"""
The analysis pipeline, stage by stage:

  redact pii -> embed -> classify (llm) -> severity rules -> hybrid retrieve
  -> abstain check -> draft with citations (llm) -> validate citations -> route -> save

Each stage is a plain function in its own module so it can be tested on its own.
If the llm is unreachable we still save the retrieved sources, so the agent isn't left empty handed.
"""

import logging
import time
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import embeddings, metrics
from app.config import settings
from app.llm import LLMError, estimate_cost
from app.logging_setup import request_id_var
from app.models import Analysis, Category, Ticket, User
from app.pipeline.classify import classify
from app.pipeline.draft import draft_resolution
from app.pipeline.outage import detect_outage
from app.pipeline.pii import redact
from app.pipeline.retrieve import hybrid_search, reviewer_guidance
from app.pipeline.rules import apply_rules
from app.pipeline.validate import citation_problems, strip_invalid

log = logging.getLogger(__name__)


class Usage:
    """adds up tokens over the two or three llm calls of one analysis"""

    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.model = None

    def add(self, result) -> None:
        self.prompt_tokens += result.prompt_tokens
        self.completion_tokens += result.completion_tokens
        self.model = result.model


def needs_admin_review(severity: str) -> bool:
    return severity in settings.approval_severity_list


def run_analysis(db: Session, ticket: Ticket, user: User | None) -> Analysis:
    started = time.perf_counter()
    timings: dict[str, int] = {}
    usage = Usage()

    @contextmanager
    def timed(stage: str):
        t0 = time.perf_counter()
        yield
        elapsed = time.perf_counter() - t0
        timings[stage] = round(elapsed * 1000)
        metrics.STAGE_LATENCY.labels(stage).observe(elapsed)

    #1. never send phone numbers / emails / account numbers to the llm
    text, pii_found = redact(ticket.complaint)
    with timed("embed"):
        qvec = embeddings.embed_query(text)
    guidance = reviewer_guidance(db, qvec)

    #2. classify with the live category list, then let the rules escalate if needed
    llm_ok = True
    try:
        with timed("classify"):
            labels, result = classify(db, text, guidance, ticket.product_hint)
        usage.add(result)
    except LLMError as exc:
        llm_ok = False
        log.warning("classifier unavailable, continuing with rules only", extra={"error": str(exc)[:200]})
        labels = {
            "category": None, "product": ticket.product_hint, "severity": "medium", "critical_reason": None,
            "sentiment": "neutral", "language": "en", "in_scope": True, "summary": "", "confidence": 0.0,
        }
    llm_severity = labels["severity"]
    severity, critical_reason, fired = apply_rules(ticket.complaint, labels["severity"], labels["critical_reason"])
    labels.update(
        severity=severity,
        critical_reason=critical_reason,
        llm_severity=llm_severity,
        rules_fired=fired,
        pii_redacted=pii_found,
        guidance_used=guidance,
    )

    #3. hybrid search over searchable tickets + kb
    with timed("retrieve"):
        sources = hybrid_search(db, text, qvec)
    allowed = {s.ref for s in sources}
    best_similarity = max((s.similarity for s in sources), default=0.0)
    labels["best_similarity"] = round(best_similarity, 4)

    #4 + 5 + 6. abstain, draft, validate
    draft = {"steps": [], "customer_reply": "", "abstain": False, "abstain_reason": ""}
    outcome, abstain_reason, citation_check = "drafted", None, {}
    if not labels["in_scope"]:
        outcome, abstain_reason = "abstained", "This doesn't look like a telecom support issue."
    elif not sources or best_similarity < settings.abstain_threshold:
        outcome, abstain_reason = "abstained", "No similar past tickets or help articles were found."
    elif not llm_ok:
        outcome = "draft_unavailable"
    else:
        try:
            with timed("draft"):
                draft, result = draft_resolution(text, labels, sources)
                usage.add(result)
                problems = citation_problems(draft, allowed)
                citation_check = {"valid": not problems, "retried": False, "stripped": False, "problems": problems}
                if problems and not draft["abstain"]:
                    #one retry with a stricter prompt, then strip whatever is still wrong
                    metrics.CITATION_FAILURES.labels("retried").inc()
                    draft, result = draft_resolution(text, labels, sources, problems=problems)
                    usage.add(result)
                    citation_check["retried"] = True
                    problems = citation_problems(draft, allowed)
                    if problems:
                        draft = strip_invalid(draft, allowed)
                        citation_check["stripped"] = True
                        metrics.CITATION_FAILURES.labels("stripped").inc()
                    citation_check["valid"] = not problems
            if draft["abstain"] or not draft["steps"]:
                outcome = "abstained"
                abstain_reason = draft["abstain_reason"] or "The sources don't explain how to fix this problem."
        except LLMError as exc:
            log.warning("drafting failed, returning sources only", extra={"error": str(exc)[:200]})
            outcome = "draft_unavailable"

    if outcome == "abstained":
        metrics.ABSTENTIONS.labels("out_of_scope" if not labels["in_scope"] else "weak_evidence").inc()

    #7. route: critical cases wait for an admin before the agent sees the draft
    review_status = "pending_review" if needs_admin_review(severity) else "auto_approved"

    #8. save everything we need for audits, evals and the dashboard
    total_s = time.perf_counter() - started
    timings["total"] = round(total_s * 1000)
    analysis = Analysis(
        ticket_id=ticket.id,
        created_by_id=user.id if user else None,
        parsed=labels,
        retrieved=[s.to_dict() for s in sources],
        draft=draft,
        outcome=outcome,
        abstain_reason=abstain_reason,
        citation_check=citation_check,
        confidence=labels.get("confidence"),
        review_status=review_status,
        latency_ms=timings["total"],
        timings=timings,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cost_usd=estimate_cost(usage.prompt_tokens, usage.completion_tokens),
        model=usage.model,
        trace_id=request_id_var.get(),
    )
    db.add(analysis)

    #copy the labels onto the ticket so lists and reports can filter on them
    category = None
    if labels["category"]:
        #sql: SELECT * FROM categories WHERE slug = :slug
        category = db.scalar(select(Category).where(Category.slug == labels["category"]))
    ticket.category_id = category.id if category else None
    ticket.product = labels["product"] or (category.product if category else None)
    ticket.severity = severity
    ticket.critical_reason = critical_reason
    ticket.sentiment = labels["sentiment"]
    ticket.language = labels["language"]
    if ticket.status != "resolved":
        ticket.status = "pending_review" if review_status == "pending_review" else "open"
    #keep the complaint vector for the outage detector and the category relabel suggestions
    #(it is not searchable until an admin promotes the ticket)
    if not ticket.is_searchable:
        ticket.embedding = qvec
        ticket.embedding_model = settings.embedding_model
    db.flush()

    outage_refs = detect_outage(db, ticket, qvec)
    if outage_refs:
        labels["outage_refs"] = outage_refs
        analysis.parsed = dict(labels)

    metrics.ANALYSES.labels(severity, review_status).inc()
    log.info(
        "analysis done",
        extra={
            "ticket": ticket.ref,
            "severity": severity,
            "category": labels["category"],
            "outcome": outcome,
            "review_status": review_status,
            "sources": len(sources),
            "latency_ms": timings["total"],
            "rules_fired": fired,
        },
    )
    return analysis
