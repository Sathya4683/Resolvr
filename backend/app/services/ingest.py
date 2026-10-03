"""
Getting knowledge into the retrieval pool: kb articles, resolved tickets (single or csv) and
promoting a ticket that an agent resolved. Everything here is idempotent so re-running an
import never creates duplicates.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import metrics
from app.config import settings
from app.embeddings import embed_documents
from app.models import Category, KbArticle, KbChunk, Ticket, User
from app.models.tickets import PRODUCTS, SENTIMENTS, SEVERITIES

log = logging.getLogger(__name__)


#---------------- kb articles ----------------

def parse_front_matter(text: str) -> tuple[dict, str]:
    """reads the small `key: value` block between --- lines at the top of a markdown file"""
    meta: dict = {}
    body = text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip()
        body = match.group(2)
    if "tags" in meta:
        meta["tags"] = [t.strip() for t in meta["tags"].split(",") if t.strip()]
    return meta, body.strip()


def split_sections(title: str, content_md: str) -> list[tuple[str, str]]:
    """one chunk per `## heading`, the title is repeated in every chunk so it gives context"""
    parts = re.split(r"^##\s+", content_md, flags=re.M)
    chunks = []
    intro = parts[0].strip()
    if intro:
        chunks.append(("Overview", f"{title}\n{intro}"))
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        body = body.strip()
        if body:
            chunks.append((heading.strip(), f"{title} - {heading.strip()}\n{body}"))
    if not chunks:
        chunks.append(("Article", f"{title}\n{content_md}"))
    return chunks


def find_category(db: Session, slug: str | None) -> Category | None:
    if not slug:
        return None
    #sql: SELECT * FROM categories WHERE slug = :slug
    return db.scalar(select(Category).where(Category.slug == slug))


def save_kb_article(
    db: Session,
    *,
    title: str,
    content_md: str,
    user: User | None,
    product: str | None = None,
    category_slug: str | None = None,
    tags: list[str] | None = None,
    ref: str | None = None,
) -> tuple[KbArticle, bool]:
    """create or update (by ref) an article and re-embed its sections. returns (article, created)"""
    category = find_category(db, category_slug)
    article = None
    if ref:
        #sql: SELECT * FROM kb_articles WHERE ref = :ref
        article = db.scalar(select(KbArticle).where(KbArticle.ref == ref))

    created = article is None
    if created:
        article = KbArticle(ref=ref) if ref else KbArticle()
        article.created_by_id = user.id if user else None
        db.add(article)
    else:
        article.version += 1
        #sql: DELETE FROM kb_chunks WHERE article_id = :article_id
        db.execute(delete(KbChunk).where(KbChunk.article_id == article.id))

    article.title = title.strip()
    article.content_md = content_md.strip()
    article.product = product or (category.product if category else None)
    article.category_id = category.id if category else None
    article.tags = tags or []
    article.status = "published"
    article.updated_by_id = user.id if user else None
    db.flush()  #gets us the id (and the generated ref) before adding chunks

    sections = split_sections(article.title, article.content_md)
    vectors = embed_documents([text for _, text in sections])
    for i, ((heading, text), vector) in enumerate(zip(sections, vectors)):
        db.add(
            KbChunk(
                article_id=article.id,
                chunk_index=i,
                heading=heading,
                content=text,
                embedding=vector,
                embedding_model=settings.embedding_model,
            )
        )
    db.flush()
    metrics.INGESTED.labels("kb", "created" if created else "updated").inc()
    return article, created


#---------------- resolved tickets ----------------

def parse_steps(value) -> list[str]:
    """accepts a list, a json list, or steps separated by ' | ' / new lines"""
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    text = (value or "").strip()
    if text.startswith("["):
        try:
            return [str(s).strip() for s in json.loads(text) if str(s).strip()]
        except json.JSONDecodeError:
            pass
    sep = "|" if "|" in text else "\n"
    return [re.sub(r"^\d+[.)]\s*", "", s).strip() for s in text.split(sep) if s.strip()]


def content_hash(complaint: str, steps: list[str]) -> str:
    normalized = " ".join(complaint.lower().split()) + "||" + "|".join(s.lower() for s in steps)
    return hashlib.sha256(normalized.encode()).hexdigest()


def ticket_embedding_text(subject: str | None, complaint: str, summary: str | None) -> str:
    parts = [subject or "", complaint]
    if summary:
        parts.append(f"Resolution: {summary}")
    return "\n".join(p for p in parts if p)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def validate_ticket_row(row: dict, categories: dict[str, Category]) -> str | None:
    complaint = (row.get("complaint") or "").strip()
    if not complaint:
        return "complaint is required"
    if len(complaint) > settings.max_complaint_chars:
        return f"complaint longer than {settings.max_complaint_chars} characters"
    if not parse_steps(row.get("resolution_steps")):
        return "resolution_steps is required"
    if row.get("category") not in categories:
        return f"unknown category '{row.get('category')}'"
    if row.get("product") and row["product"] not in PRODUCTS:
        return f"product must be one of {', '.join(PRODUCTS)}"
    if row.get("severity") not in SEVERITIES:
        return f"severity must be one of {', '.join(SEVERITIES)}"
    if row.get("sentiment") and row["sentiment"] not in SENTIMENTS:
        return f"sentiment must be one of {', '.join(SENTIMENTS)}"
    return None


def import_resolved_tickets(db: Session, rows: list[dict], user: User | None, source: str = "csv") -> dict:
    """
    validates every row on its own, skips duplicates (same complaint + steps) and embeds the rest
    in one go. returns a per-row report instead of failing the whole file.
    """
    #sql: SELECT * FROM categories
    categories = {c.slug: c for c in db.scalars(select(Category))}
    #sql: SELECT * FROM users
    users = {u.username: u for u in db.scalars(select(User))}

    report = {"inserted": 0, "duplicates": 0, "errors": []}
    pending: list[tuple[Ticket, str]] = []
    seen_hashes: set[str] = set()

    for i, row in enumerate(rows, start=1):
        error = validate_ticket_row(row, categories)
        if error:
            report["errors"].append({"row": i, "error": error})
            continue

        steps = parse_steps(row["resolution_steps"])
        digest = content_hash(row["complaint"], steps)
        #sql: SELECT id FROM tickets WHERE content_hash = :digest
        exists = db.scalar(select(Ticket.id).where(Ticket.content_hash == digest))
        if exists or digest in seen_hashes:
            report["duplicates"] += 1
            continue
        seen_hashes.add(digest)

        category = categories[row["category"]]
        resolver = users.get(row.get("resolved_by") or "") or user
        ticket = Ticket(
            customer_ref=row.get("customer_ref") or None,
            channel=row.get("channel") or None,
            city=row.get("city") or None,
            subject=(row.get("subject") or "")[:200] or None,
            complaint=row["complaint"].strip(),
            product=row.get("product") or category.product,
            category_id=category.id,
            severity=row["severity"],
            critical_reason=row.get("critical_reason") or None,
            sentiment=row.get("sentiment") or None,
            ticket_type=row.get("ticket_type") or None,
            tags=[t for t in (row.get("tags") or "").split("|") if t],
            status="resolved",
            source=source,
            resolution_steps=steps,
            resolution_summary=row.get("resolution_summary") or None,
            is_searchable=True,
            content_hash=digest,
            created_by_id=resolver.id if resolver else None,
            resolved_by_id=resolver.id if resolver else None,
        )
        #only the seed keeps its own refs and dates, everything else is "now"
        if source == "seed":
            ticket.ref = row["ticket_id"]
            ticket.created_at = parse_datetime(row.get("created_at"))
            ticket.resolved_at = parse_datetime(row.get("resolved_at"))
        else:
            ticket.resolved_at = datetime.now(timezone.utc)
        text = ticket_embedding_text(ticket.subject, ticket.complaint, ticket.resolution_summary)
        pending.append((ticket, text))

    if pending:
        vectors = embed_documents([text for _, text in pending])
        for (ticket, _), vector in zip(pending, vectors):
            ticket.embedding = vector
            ticket.embedding_model = settings.embedding_model
            db.add(ticket)
        db.flush()

    report["inserted"] = len(pending)
    metrics.INGESTED.labels("ticket", "inserted").inc(report["inserted"])
    metrics.INGESTED.labels("ticket", "duplicate").inc(report["duplicates"])
    metrics.INGESTED.labels("ticket", "error").inc(len(report["errors"]))
    return report


def promote_ticket(db: Session, ticket: Ticket) -> Ticket:
    """an admin approved an agent-resolved ticket, so it becomes part of the searchable history"""
    steps = ticket.resolution_steps or []
    ticket.content_hash = content_hash(ticket.complaint, steps)
    ticket.embedding = embed_documents(
        [ticket_embedding_text(ticket.subject, ticket.complaint, ticket.resolution_summary)]
    )[0]
    ticket.embedding_model = settings.embedding_model
    ticket.is_searchable = True
    metrics.INGESTED.labels("ticket", "promoted").inc()
    return ticket
