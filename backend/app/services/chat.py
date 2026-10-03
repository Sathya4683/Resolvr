"""
Assistant chat: every question goes through the same hybrid retrieval as the analysis pipeline,
and the model answers only from those sources, citing them inline like [KB-004].
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import embeddings
from app.models import ChatMessage, ChatSession, Ticket, User
from app.pipeline import prompts
from app.pipeline.pii import redact
from app.pipeline.retrieve import hybrid_search
from app.services.tickets import HIDDEN_FOR_AGENTS, latest_analysis, visible_steps

#matches [KB-004] and also grouped ones like [KB-004, TCK-10023]
CITATION_RE = re.compile(r"\[((?:KB|TCK)-\d+(?:\s*,\s*(?:KB|TCK)-\d+)*)\]")
HISTORY_TURNS = 8
MAX_SOURCES = 8


def history(db: Session, session: ChatSession) -> list[ChatMessage]:
    #sql: SELECT * FROM chat_messages WHERE session_id = :id ORDER BY id DESC LIMIT :n
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_TURNS)
    ).all()
    return list(reversed(rows))


def retrieval_query(question: str, past: list[ChatMessage]) -> str:
    #follow-ups like "and what if that doesn't work?" need the previous question for context
    previous = [m.content for m in past if m.role == "user"][-1:]
    return " ".join(previous + [question])


def ticket_context(db: Session, ticket: Ticket, user: User) -> tuple[str, list[dict]]:
    """the ticket's complaint, what the analysis concluded, and the sources its steps came from"""
    complaint, _ = redact(ticket.complaint)
    analysis = latest_analysis(db, ticket.id)
    labels = (
        f"category {ticket.category.name if ticket.category else 'unclear'}, "
        f"product {ticket.product or 'unknown'}, severity {ticket.severity or 'unknown'}"
    )
    if analysis is None:
        return prompts.CHAT_TICKET_CONTEXT.format(
            ref=ticket.ref, complaint=complaint, labels=labels, detail="No analysis has been run yet."
        ), []

    steps = visible_steps(analysis)
    if user.role == "support_agent" and analysis.review_status in HIDDEN_FOR_AGENTS:
        #a critical draft is hidden from agents until an admin signs off, the chat must not leak it
        detail = (
            "The drafted steps are waiting for admin approval (or were declined). Do not guess or reveal them, "
            "tell the agent to wait for the admin's decision."
        )
    elif steps:
        lines = [f"{i}. {st['text']} [{', '.join(st['citations'])}]" for i, st in enumerate(steps, start=1)]
        detail = "Suggested steps, with the sources each one came from:\n" + "\n".join(lines)
    else:
        detail = f"No steps were drafted ({analysis.outcome.replace('_', ' ')})."
    return prompts.CHAT_TICKET_CONTEXT.format(
        ref=ticket.ref, complaint=complaint, labels=labels, detail=detail
    ), list(analysis.retrieved or [])


def build_context(
    db: Session, session: ChatSession, question: str, user: User
) -> tuple[str, list[dict], list[dict]]:
    """returns (system prompt, messages for the model, sources)"""
    past = history(db, session)
    #sql: SELECT * FROM tickets WHERE id = :ticket_id
    ticket = db.get(Ticket, session.ticket_id) if session.ticket_id else None

    #search on the complaint as well as the question, "why was this the fix?" alone finds nothing useful
    query = retrieval_query(question, past)
    if ticket:
        query = f"{ticket.complaint}\n{query}"
    query, _ = redact(query)
    found = [s.to_dict() for s in hybrid_search(db, query, embeddings.embed_query(query), top_k=6)]

    ticket_block, ticket_sources = ticket_context(db, ticket, user) if ticket else ("", [])
    #the sources the ticket's steps cited come first, then anything new the chat search found
    sources, seen = [], set()
    for src in ticket_sources + found:
        if src["ref"] not in seen:
            seen.add(src["ref"])
            sources.append(src)
    sources = sources[:MAX_SOURCES]

    source_text = "\n\n".join(f"[{s['ref']}] {s['content']}" for s in sources) or "(no sources found)"
    system = prompts.CHAT_SYSTEM.format(sources=source_text) + ticket_block

    messages = [{"role": m.role, "content": redact(m.content)[0]} for m in past]
    messages.append({"role": "user", "content": redact(question)[0]})
    return system, messages, sources


def source_summary(sources: list[dict]) -> list[dict]:
    return [
        {
            "ref": s["ref"],
            "kind": s["kind"],
            "title": s["title"],
            "similarity": round(s.get("similarity") or 0, 3),
            "snippet": s.get("snippet", ""),
        }
        for s in sources
    ]


def cited_refs(text: str, sources: list[dict]) -> list[str]:
    allowed = {s["ref"] for s in sources}
    found = [ref.strip() for group in CITATION_RE.findall(text) for ref in group.split(",")]
    return [r for r in dict.fromkeys(found) if r in allowed]
