import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import metrics
from app.db import SessionLocal, get_db
from app.deps import agent_or_admin
from app.llm import LLMError, get_llm, record_usage
from app.models import ChatMessage, ChatSession, Ticket, User
from app.schemas import ChatMessageIn, ChatMessageOut, ChatSessionIn, ChatSessionOut
from app.services import chat as chat_service
from app.services.tickets import get_by_ref

router = APIRouter(prefix="/chat", tags=["assistant chat"])
log = logging.getLogger(__name__)


def session_out(db: Session, s: ChatSession) -> ChatSessionOut:
    ref = None
    if s.ticket_id:
        #sql: SELECT ref FROM tickets WHERE id = :ticket_id
        ref = db.scalar(select(Ticket.ref).where(Ticket.id == s.ticket_id))
    return ChatSessionOut(id=s.id, title=s.title, ticket_ref=ref, created_at=s.created_at, updated_at=s.updated_at)


def load_session(db: Session, session_id: int, user: User) -> ChatSession:
    #sql: SELECT * FROM chat_sessions WHERE id = :session_id
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return session


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    #sql: SELECT * FROM chat_sessions WHERE user_id = :user_id ORDER BY updated_at DESC LIMIT 50
    rows = db.scalars(
        select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc()).limit(50)
    ).all()
    return [session_out(db, s) for s in rows]


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
def create_session(body: ChatSessionIn, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    session = ChatSession(user_id=user.id, title=body.title or "New chat")
    if body.ticket_ref:
        ticket = get_by_ref(db, body.ticket_ref)
        if ticket is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
        session.ticket_id = ticket.id
        session.title = body.title or f"About {ticket.ref}"
    db.add(session)
    db.commit()
    return session_out(db, session)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(session_id: int, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    session = load_session(db, session_id, user)
    #sql: SELECT * FROM chat_messages WHERE session_id = :session_id ORDER BY id
    return db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.id)).all()


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)):
    db.delete(load_session(db, session_id, user))
    db.commit()


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: int, body: ChatMessageIn, db: Session = Depends(get_db), user: User = Depends(agent_or_admin)
):
    """
    streams the answer back as server-sent events:
      sources -> the retrieved documents, token -> text as it is generated, done -> final message id
    """
    session = load_session(db, session_id, user)
    question = body.content.strip()
    system, messages, sources = chat_service.build_context(db, session, question)
    summary = chat_service.source_summary(sources)

    db.add(ChatMessage(session_id=session.id, role="user", content=question))
    if session.title in ("New chat", "") and not session.ticket_id:
        session.title = question[:60] + ("..." if len(question) > 60 else "")
    db.commit()

    def stream():
        yield sse("sources", summary)
        parts, usage, error = [], None, None
        try:
            for chunk in get_llm().stream_text(system, messages):
                if chunk.done:
                    usage = chunk.usage
                elif chunk.text:
                    parts.append(chunk.text)
                    yield sse("token", chunk.text)
        except LLMError as exc:
            error = str(exc)[:200]
            log.warning("chat answer failed", extra={"error": error})
            fallback = "The assistant can't reach the language model right now. The closest sources are listed below."
            parts = [fallback]
            yield sse("token", fallback)

        text = "".join(parts).strip()
        if usage:
            record_usage("chat", usage)
        metrics.CHAT_MESSAGES.labels("error" if error else "ok").inc()
        #the request's db session is closed by now, so the answer is saved with a fresh one
        with SessionLocal() as s:
            msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=text,
                sources=summary,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
            )
            s.add(msg)
            #sql: UPDATE chat_sessions SET updated_at = now() WHERE id = :session_id
            s.get(ChatSession, session_id).updated_at = datetime.now(timezone.utc)
            s.commit()
            yield sse("done", {"id": msg.id, "cited": chat_service.cited_refs(text, summary), "error": error})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
