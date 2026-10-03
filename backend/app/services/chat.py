"""
Assistant chat: every question goes through the same hybrid retrieval as the analysis pipeline,
and the model answers only from those sources, citing them inline like [KB-004].
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import embeddings
from app.models import ChatMessage, ChatSession, Ticket
from app.pipeline import prompts
from app.pipeline.pii import redact
from app.pipeline.retrieve import Source, hybrid_search

CITATION_RE = re.compile(r"\[((?:KB|TCK)-\d+)\]")
HISTORY_TURNS = 8


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


def build_context(db: Session, session: ChatSession, question: str) -> tuple[str, list[dict], list[Source]]:
    """returns (system prompt, messages for the model, sources)"""
    past = history(db, session)
    query, _ = redact(retrieval_query(question, past))
    sources = hybrid_search(db, query, embeddings.embed_query(query), top_k=6)

    source_text = "\n\n".join(f"[{s.ref}] {s.content}" for s in sources) or "(no sources found)"
    system = prompts.CHAT_SYSTEM.format(sources=source_text)
    if session.ticket_id:
        #sql: SELECT * FROM tickets WHERE id = :ticket_id
        ticket = db.get(Ticket, session.ticket_id)
        if ticket:
            complaint, _ = redact(ticket.complaint)
            system += prompts.CHAT_TICKET_CONTEXT.format(ref=ticket.ref, complaint=complaint)

    messages = [{"role": m.role, "content": redact(m.content)[0]} for m in past]
    messages.append({"role": "user", "content": redact(question)[0]})
    return system, messages, sources


def source_summary(sources: list[Source]) -> list[dict]:
    return [
        {"ref": s.ref, "kind": s.kind, "title": s.title, "similarity": round(s.similarity, 3), "snippet": s.snippet}
        for s in sources
    ]


def cited_refs(text: str, sources: list[dict]) -> list[str]:
    allowed = {s["ref"] for s in sources}
    return [r for r in dict.fromkeys(CITATION_RE.findall(text)) if r in allowed]
