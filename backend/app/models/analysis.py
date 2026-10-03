from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base

REVIEW_STATUSES = ("auto_approved", "pending_review", "approved", "edited", "rejected")


class Analysis(Base):
    """one run of the pipeline on a ticket: labels, sources, draft and all the numbers around it"""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    #what the classifier said + which rules changed it
    parsed: Mapped[dict] = mapped_column(JSONB, default=dict)
    #[{ref, kind, title, score, why}]
    retrieved: Mapped[list] = mapped_column(JSONB, default=list)
    #{steps: [{text, citations}], customer_reply}
    draft: Mapped[dict] = mapped_column(JSONB, default=dict)
    #drafted | abstained | draft_unavailable
    outcome: Mapped[str] = mapped_column(String(20), default="drafted")
    abstain_reason: Mapped[str | None] = mapped_column(Text)
    citation_check: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float | None] = mapped_column()

    review_status: Mapped[str] = mapped_column(String(20), default="auto_approved", index=True)
    #steps after an admin edited them, empty means the draft was used as is
    final_steps: Mapped[list] = mapped_column(JSONB, default=list)
    last_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    timings: Mapped[dict] = mapped_column(JSONB, default=dict)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    model: Mapped[str | None] = mapped_column(String(80))
    trace_id: Mapped[str | None] = mapped_column(String(40))

    #analyst lock, only one analyst can review an analysis at a time
    claimed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    ticket = relationship("Ticket", lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id])
    claimed_by = relationship("User", foreign_keys=[claimed_by_id], lazy="joined")


class ReviewDecision(Base):
    """admin decision on a critical draft"""

    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    #approve | edit | reject
    action: Mapped[str] = mapped_column(String(10))
    comment: Mapped[str | None] = mapped_column(Text)
    edited_steps: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    admin = relationship("User", lazy="joined")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    #up | down
    rating: Mapped[str] = mapped_column(String(4))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("analysis_id", "user_id", name="feedback_one_per_user"),)


class AnalystReview(Base):
    """
    post-hoc quality review by an analyst. it doesn't block anyone, it measures how good the
    assistant is. the notes are embedded too, so later analyses can use them as guidance.
    """

    __tablename__ = "analyst_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), unique=True)
    analyst_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    #correct | partially_correct | incorrect
    verdict: Mapped[str] = mapped_column(String(20))
    citations_ok: Mapped[bool] = mapped_column(Boolean)
    #{correct, safe, actionable, complete} -> bool
    rubric: Mapped[dict] = mapped_column(JSONB, default=dict)
    original_labels: Mapped[dict] = mapped_column(JSONB, default=dict)
    corrected_labels: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    #complaint summary + notes, used as "reviewer guidance" in future prompts
    guidance_text: Mapped[str | None] = mapped_column(Text)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    analyst = relationship("User", lazy="joined")
    analysis = relationship("Analysis")

    __table_args__ = (
        Index(
            "analyst_reviews_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
