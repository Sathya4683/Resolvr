from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base


class KbArticle(Base):
    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text("'KB-' || lpad(nextval('kb_ref_seq')::text, 3, '0')")
    )
    title: Mapped[str] = mapped_column(String(200))
    product: Mapped[str | None] = mapped_column(String(20))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    content_md: Mapped[str] = mapped_column(Text)
    #published articles are searchable, archived ones are kept for history only
    status: Mapped[str] = mapped_column(String(20), default="published")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category = relationship("Category", lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")
    chunks = relationship("KbChunk", back_populates="article", cascade="all, delete-orphan")


class KbChunk(Base):
    """one section ("## Steps" etc.) of an article, this is what we actually embed and search"""

    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("kb_articles.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(settings.embedding_dim), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))

    article = relationship("KbArticle", back_populates="chunks")

    __table_args__ = (
        Index(
            "kb_chunks_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("kb_chunks_tsv_idx", "tsv", postgresql_using="gin"),
    )
