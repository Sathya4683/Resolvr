"""
Hybrid retrieval over resolved tickets and kb articles.

1. vector search (pgvector cosine) and keyword search (postgres full text) run separately
2. the ranked lists are merged with reciprocal rank fusion (rrf), which only looks at the rank
   in each list, so the very different score scales don't matter
3. the top candidates are re-scored by a cross-encoder (reads complaint + document together)
"""

import math
import re
from dataclasses import asdict, dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app import embeddings
from app.config import settings
from app.models import AnalystReview, KbArticle, KbChunk, Ticket

RRF_K = 60
WORD_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = set(
    """the and for are but not you all any can had her was one our out has have from they this that with
    what when your just been were will there their them then than into some very also please pls kindly
    since still even after before about again because would could should these those dont didnt its
    i'm im my me we us is it in on at to of a an or be do so if no as by up hi hello sir team thanks
    thank help want need get got going""".split()
)


@dataclass
class Source:
    ref: str
    kind: str  #ticket | kb
    title: str
    snippet: str
    content: str  #what the llm sees
    rerank_text: str
    category: str | None = None
    product: str | None = None
    similarity: float = 0.0
    vector_rank: int | None = None
    keyword_rank: int | None = None
    rrf: float = 0.0
    rerank_score: float | None = None
    matched_terms: list[str] = field(default_factory=list)
    _vector: list | None = None

    @property
    def why(self) -> str:
        parts = [f"{round(self.similarity * 100)}% semantic match"]
        if self.matched_terms:
            parts.append("shared words: " + ", ".join(self.matched_terms))
        if self.rerank_score is not None:
            parts.append(f"reranker relevance {self.rerank_score:.2f}")
        return " · ".join(parts)

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("rerank_text", "_vector"):
            data.pop(key, None)
        data["why"] = self.why
        data["similarity"] = round(self.similarity, 4)
        data["rrf"] = round(self.rrf, 5)
        return data


def keywords(text: str) -> list[str]:
    seen = []
    for word in WORD_RE.findall(text.lower()):
        if len(word) > 2 and word not in STOPWORDS and word not in seen:
            seen.append(word)
    return seen[:40]


def or_tsquery(words: list[str]) -> str | None:
    #plainto_tsquery would AND every word, a long complaint would then match nothing
    return " | ".join(words) if words else None


def cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


#---------------- building sources ----------------

def ticket_source(t: Ticket) -> Source:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(t.resolution_steps or [], start=1))
    category = t.category.name if t.category else "uncategorised"
    return Source(
        ref=t.ref,
        kind="ticket",
        title=t.subject or t.complaint[:80],
        snippet=t.complaint[:240],
        content=f"Past resolved ticket ({category})\nComplaint: {t.complaint}\nResolution steps:\n{steps}",
        rerank_text=f"{t.subject or ''}\n{t.complaint}\n{t.resolution_summary or ''}",
        category=t.category.slug if t.category else None,
        product=t.product,
        _vector=t.embedding,
    )


def kb_source(chunk: KbChunk) -> Source:
    article = chunk.article
    return Source(
        ref=article.ref,
        kind="kb",
        title=article.title,
        snippet=chunk.content[:240],
        content=f"Help article: {article.title}\n{article.content_md[:3500]}",
        rerank_text=chunk.content,
        category=article.category.slug if article.category else None,
        product=article.product,
        _vector=chunk.embedding,
    )


#---------------- the four searches ----------------

def ticket_vector_hits(db: Session, qvec: list[float], limit: int) -> list[Source]:
    distance = Ticket.embedding.cosine_distance(qvec)
    #sql: SELECT tickets.*, embedding <=> :qvec AS distance FROM tickets
    #     WHERE is_searchable = true ORDER BY distance LIMIT :limit
    stmt = (
        select(Ticket, distance.label("distance"))
        .where(Ticket.is_searchable.is_(True))
        .order_by(distance)
        .limit(limit)
    )
    out = []
    for ticket, dist in db.execute(stmt):
        src = ticket_source(ticket)
        src.similarity = 1 - float(dist)
        out.append(src)
    return out


def ticket_keyword_hits(db: Session, query: str, limit: int) -> list[Source]:
    tsq = func.to_tsquery("english", query)
    rank = func.ts_rank_cd(Ticket.tsv, tsq)
    #sql: SELECT tickets.*, ts_rank_cd(tsv, to_tsquery('english', :q)) AS rank FROM tickets
    #     WHERE is_searchable = true AND tsv @@ to_tsquery('english', :q)
    #     ORDER BY rank DESC LIMIT :limit
    stmt = (
        select(Ticket, rank.label("rank"))
        .where(Ticket.is_searchable.is_(True), Ticket.tsv.op("@@")(tsq))
        .order_by(rank.desc())
        .limit(limit)
    )
    return [ticket_source(t) for t, _ in db.execute(stmt)]


def _best_chunk_per_article(chunks: list[KbChunk], limit: int) -> list[KbChunk]:
    best, seen = [], set()
    for chunk in chunks:
        if chunk.article_id not in seen:
            seen.add(chunk.article_id)
            best.append(chunk)
    return best[:limit]


def kb_vector_hits(db: Session, qvec: list[float], limit: int) -> list[Source]:
    distance = KbChunk.embedding.cosine_distance(qvec)
    #sql: SELECT kb_chunks.*, kb_chunks.embedding <=> :qvec AS distance FROM kb_chunks
    #     JOIN kb_articles ON kb_articles.id = kb_chunks.article_id
    #     WHERE kb_articles.status = 'published' ORDER BY distance LIMIT :limit * 4
    stmt = (
        select(KbChunk, distance.label("distance"))
        .join(KbArticle)
        .options(joinedload(KbChunk.article))
        .where(KbArticle.status == "published")
        .order_by(distance)
        .limit(limit * 4)
    )
    rows = db.execute(stmt).all()
    dist_by_chunk = {chunk.id: float(dist) for chunk, dist in rows}
    out = []
    for chunk in _best_chunk_per_article([c for c, _ in rows], limit):
        src = kb_source(chunk)
        src.similarity = 1 - dist_by_chunk[chunk.id]
        out.append(src)
    return out


def kb_keyword_hits(db: Session, query: str, limit: int) -> list[Source]:
    tsq = func.to_tsquery("english", query)
    rank = func.ts_rank_cd(KbChunk.tsv, tsq)
    #sql: SELECT kb_chunks.*, ts_rank_cd(kb_chunks.tsv, to_tsquery('english', :q)) AS rank FROM kb_chunks
    #     JOIN kb_articles ON kb_articles.id = kb_chunks.article_id
    #     WHERE kb_articles.status = 'published' AND kb_chunks.tsv @@ to_tsquery('english', :q)
    #     ORDER BY rank DESC LIMIT :limit * 4
    stmt = (
        select(KbChunk, rank.label("rank"))
        .join(KbArticle)
        .options(joinedload(KbChunk.article))
        .where(KbArticle.status == "published", KbChunk.tsv.op("@@")(tsq))
        .order_by(rank.desc())
        .limit(limit * 4)
    )
    chunks = [c for c, _ in db.execute(stmt)]
    return [kb_source(c) for c in _best_chunk_per_article(chunks, limit)]


#---------------- putting it together ----------------

def hybrid_search(
    db: Session,
    text: str,
    qvec: list[float],
    mode: str = "hybrid",
    top_k: int | None = None,
    rerank: bool | None = None,
) -> list[Source]:
    """mode is hybrid | vector | keyword (the last two exist for the evals)"""
    top_k = top_k or settings.retrieval_top_k
    rerank = settings.reranker_enabled if rerank is None else rerank
    n = settings.retrieval_candidates
    words = keywords(text)
    query = or_tsquery(words)

    ranked_lists: list[list[Source]] = []
    if mode in ("hybrid", "vector"):
        ranked_lists += [ticket_vector_hits(db, qvec, n), kb_vector_hits(db, qvec, n)]
    if mode in ("hybrid", "keyword") and query:
        ranked_lists += [ticket_keyword_hits(db, query, n), kb_keyword_hits(db, query, n)]

    merged: dict[str, Source] = {}
    for hits in ranked_lists:
        for rank, src in enumerate(hits, start=1):
            current = merged.setdefault(src.ref, src)
            current.rrf += 1 / (RRF_K + rank)
            if src.similarity:
                current.similarity = max(current.similarity, src.similarity)
                current.vector_rank = current.vector_rank or rank
            else:
                current.keyword_rank = current.keyword_rank or rank

    candidates = sorted(merged.values(), key=lambda s: s.rrf, reverse=True)[:n]

    for src in candidates:
        #keyword-only hits never got a similarity from the db, work it out here
        if not src.similarity:
            src.similarity = cosine(qvec, src._vector)
        doc_words = set(WORD_RE.findall(src.rerank_text.lower()))
        src.matched_terms = [w for w in words if w in doc_words][:5]

    if rerank and len(candidates) > 1:
        scores = embeddings.rerank_scores(text, [c.rerank_text for c in candidates])
        for src, score in zip(candidates, scores):
            src.rerank_score = score
        candidates.sort(key=lambda s: s.rerank_score, reverse=True)

    return pick_mix(candidates, top_k)


def pick_mix(ranked: list[Source], top_k: int, kb_slots: int = 2) -> list[Source]:
    """
    past tickets tend to win the ranking because they are short and worded like the complaint,
    but the kb article has the official steps. keep the best `kb_slots` articles in the final list.
    """
    kb = [s for s in ranked if s.kind == "kb"][:kb_slots]
    rest = [s for s in ranked if s not in kb][: top_k - len(kb)]
    chosen = set(id(s) for s in kb + rest)
    return [s for s in ranked if id(s) in chosen]


def reviewer_guidance(db: Session, qvec: list[float], limit: int = 3, min_similarity: float = 0.75) -> list[str]:
    """notes analysts left on similar past cases, fed back into the prompts as guidance"""
    distance = AnalystReview.embedding.cosine_distance(qvec)
    #sql: SELECT guidance_text, embedding <=> :qvec AS distance FROM analyst_reviews
    #     WHERE guidance_text IS NOT NULL ORDER BY distance LIMIT :limit
    stmt = (
        select(AnalystReview.guidance_text, distance.label("distance"))
        .where(AnalystReview.guidance_text.is_not(None), AnalystReview.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return [text for text, dist in db.execute(stmt) if 1 - float(dist) >= min_similarity]
