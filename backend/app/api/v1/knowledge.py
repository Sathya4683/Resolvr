"""
Knowledge base articles (markdown). Admins and analysts can write them; support agents can only
read. Saving an article embeds its sections right away, so the next analysis can already use it.
"""

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import admin_only, analyst_or_admin, any_user
from app.models import KbArticle, KbChunk, User
from app.models.tickets import PRODUCTS
from app.schemas import CategoryBrief, KbArticleIn, KbArticleListItem, KbArticleOut
from app.services import audit
from app.services.files import read_upload
from app.services.ingest import find_category, parse_front_matter, save_kb_article

router = APIRouter(prefix="/kb", tags=["knowledge base"])


def excerpt(md: str, length: int = 180) -> str:
    text = re.sub(r"^#+.*$", "", md, flags=re.M)
    text = re.sub(r"[*_`>#-]", "", text)
    return " ".join(text.split())[:length]


def list_item(article: KbArticle) -> KbArticleListItem:
    return KbArticleListItem(
        ref=article.ref,
        title=article.title,
        product=article.product,
        category=CategoryBrief.model_validate(article.category) if article.category else None,
        tags=article.tags or [],
        status=article.status,
        version=article.version,
        updated_at=article.updated_at,
        author=article.created_by.full_name if article.created_by else "Resolvr team",
        excerpt=excerpt(article.content_md),
    )


def detail(db: Session, article: KbArticle) -> KbArticleOut:
    #sql: SELECT count(*) FROM kb_chunks WHERE article_id = :article_id
    chunks = db.scalar(select(func.count(KbChunk.id)).where(KbChunk.article_id == article.id))
    return KbArticleOut(**list_item(article).model_dump(), content_md=article.content_md, chunks=chunks)


def load(db: Session, ref: str) -> KbArticle:
    #sql: SELECT * FROM kb_articles WHERE ref = :ref
    article = db.scalar(select(KbArticle).where(KbArticle.ref == ref.upper()))
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    return article


def check_category(db: Session, slug: str | None) -> None:
    if slug and find_category(db, slug) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown category '{slug}'")


@router.get("", response_model=list[KbArticleListItem])
def list_articles(
    q: str | None = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(any_user),
):
    #sql: SELECT * FROM kb_articles
    #     WHERE status = 'published' AND (title ILIKE :q OR content_md ILIKE :q OR ref ILIKE :q)
    #     ORDER BY ref
    stmt = select(KbArticle)
    if not include_archived:
        stmt = stmt.where(KbArticle.status == "published")
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(KbArticle.title.ilike(like), KbArticle.content_md.ilike(like), KbArticle.ref.ilike(like)))
    return [list_item(a) for a in db.scalars(stmt.order_by(KbArticle.ref))]


@router.get("/{ref}", response_model=KbArticleOut)
def get_article(ref: str, db: Session = Depends(get_db), _: User = Depends(any_user)):
    return detail(db, load(db, ref))


@router.post("", response_model=KbArticleOut, status_code=201)
def create_article(body: KbArticleIn, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)):
    check_category(db, body.category_slug)
    article, _ = save_kb_article(
        db,
        title=body.title,
        content_md=body.content_md,
        product=body.product,
        category_slug=body.category_slug,
        tags=body.tags,
        user=user,
    )
    audit.record(db, user, "kb.create", "kb", article.ref, title=article.title)
    db.commit()
    return detail(db, article)


@router.put("/{ref}", response_model=KbArticleOut)
def update_article(
    ref: str, body: KbArticleIn, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)
):
    article = load(db, ref)
    check_category(db, body.category_slug)
    article, _ = save_kb_article(
        db,
        ref=article.ref,
        title=body.title,
        content_md=body.content_md,
        product=body.product,
        category_slug=body.category_slug,
        tags=body.tags,
        user=user,
    )
    audit.record(db, user, "kb.update", "kb", article.ref, version=article.version)
    db.commit()
    return detail(db, article)


@router.post("/upload", response_model=KbArticleOut, status_code=201)
def upload_markdown(
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)
):
    """upload a .md file, front matter (title, product, category, tags) is optional"""
    text = read_upload(file, (".md", ".markdown"))
    meta, body = parse_front_matter(text)
    title = meta.get("title")
    if not title:
        #fall back to the first "# heading", then the file name
        match = re.search(r"^#\s+(.+)$", body, re.M)
        title = match.group(1).strip() if match else (file.filename or "Untitled").rsplit(".", 1)[0]
        body = re.sub(r"^#\s+.+\n?", "", body, count=1, flags=re.M).strip()
    if len(body) < 20:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The article is empty")
    check_category(db, meta.get("category"))
    article, _ = save_kb_article(
        db,
        title=title,
        content_md=body,
        product=meta.get("product") if meta.get("product") in PRODUCTS else None,
        category_slug=meta.get("category"),
        tags=meta.get("tags", []),
        user=user,
    )
    audit.record(db, user, "kb.upload", "kb", article.ref, filename=file.filename)
    db.commit()
    return detail(db, article)


@router.post("/{ref}/archive", response_model=KbArticleOut)
def archive_article(ref: str, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """archived articles stay readable but are no longer used for answers"""
    article = load(db, ref)
    article.status = "archived"
    audit.record(db, admin, "kb.archive", "kb", article.ref)
    db.commit()
    return detail(db, article)


@router.post("/{ref}/restore", response_model=KbArticleOut)
def restore_article(ref: str, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    article = load(db, ref)
    article.status = "published"
    audit.record(db, admin, "kb.restore", "kb", article.ref)
    db.commit()
    return detail(db, article)
