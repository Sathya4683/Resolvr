from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base

SEVERITIES = ("low", "medium", "high", "critical")
SENTIMENTS = ("angry", "frustrated", "neutral", "positive")
PRODUCTS = ("broadband", "mobile", "dth", "billing")
CRITICAL_REASONS = ("legal", "regulatory", "privacy", "fraud", "compensation")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    product: Mapped[str | None] = mapped_column(String(20))
    default_severity: Mapped[str] = mapped_column(String(10), default="medium")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text("'TCK-' || nextval('ticket_ref_seq')")
    )
    customer_ref: Mapped[str | None] = mapped_column(String(40))
    channel: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(60))
    subject: Mapped[str | None] = mapped_column(String(200))
    complaint: Mapped[str] = mapped_column(Text)
    product_hint: Mapped[str | None] = mapped_column(String(20))

    #labels, filled in by the analysis (or by the csv for imported history)
    language: Mapped[str] = mapped_column(String(10), default="en")
    product: Mapped[str | None] = mapped_column(String(20), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    severity: Mapped[str | None] = mapped_column(String(10), index=True)
    critical_reason: Mapped[str | None] = mapped_column(String(20))
    sentiment: Mapped[str | None] = mapped_column(String(12))
    ticket_type: Mapped[str | None] = mapped_column(String(20))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    #open -> pending_review (critical only) -> resolved
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    source: Mapped[str] = mapped_column(String(20), default="agent")

    resolution_steps: Mapped[list[str]] = mapped_column(JSONB, default=list)
    resolution_summary: Mapped[str | None] = mapped_column(Text)

    #only resolved tickets an admin has approved are used for retrieval
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    tsv = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(subject, '') || ' ' || complaint || ' ' || "
            "coalesce(resolution_summary, ''))",
            persisted=True,
        ),
    )

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    category = relationship("Category", lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])

    __table_args__ = (
        Index(
            "tickets_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("tickets_tsv_idx", "tsv", postgresql_using="gin"),
    )
