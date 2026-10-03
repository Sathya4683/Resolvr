"""
The ticket taxonomy lives in the database, so admins and analysts can add / rename / switch off
categories without a redeploy. The classifier reads the active list on every request.
Analysts are included because they are the ones who spot new kinds of issues while reviewing.
Every change is audit logged.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import embeddings
from app.db import get_db
from app.deps import analyst_or_admin, any_user
from app.models import Category, Ticket, User
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate, RelabelCandidate, RelabelIn
from app.services import audit

router = APIRouter(prefix="/categories", tags=["categories"])


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]


def load(db: Session, category_id: int) -> Category:
    #sql: SELECT * FROM categories WHERE id = :category_id
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(
    include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(any_user)
):
    counts = (
        select(Ticket.category_id, func.count(Ticket.id).label("n")).group_by(Ticket.category_id).subquery()
    )
    #sql: SELECT categories.*, coalesce(c.n, 0) AS ticket_count FROM categories
    #     LEFT JOIN (SELECT category_id, count(id) AS n FROM tickets GROUP BY category_id) c
    #       ON c.category_id = categories.id
    #     WHERE is_active = true            -- unless include_inactive
    #     ORDER BY name
    stmt = select(Category, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.category_id == Category.id)
    if not include_inactive:
        stmt = stmt.where(Category.is_active.is_(True))
    out = []
    for category, n in db.execute(stmt.order_by(Category.name)):
        item = CategoryOut.model_validate(category)
        item.ticket_count = n
        out.append(item)
    return out


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryCreate, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)):
    slug = body.slug or slugify(body.name)
    #sql: SELECT id FROM categories WHERE slug = :slug
    if db.scalar(select(Category.id).where(Category.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A category with slug '{slug}' already exists")
    category = Category(
        slug=slug,
        name=body.name,
        description=body.description,
        product=body.product,
        default_severity=body.default_severity,
    )
    db.add(category)
    db.flush()
    audit.record(db, user, "category.create", "category", category.slug, name=category.name)
    db.commit()
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int, body: CategoryUpdate, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)
):
    category = load(db, category_id)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(category, field, value)
    audit.record(db, user, "category.update", "category", category.slug, changes=changes)
    db.commit()
    return category


@router.get("/{category_id}/candidates", response_model=list[RelabelCandidate])
def relabel_candidates(
    category_id: int, limit: int = 20, db: Session = Depends(get_db), _: User = Depends(analyst_or_admin)
):
    """
    for a new class (say "5G home router issues"), old tickets were filed under other categories.
    we embed the new category's description and show the closest tickets so an admin can move them.
    """
    category = load(db, category_id)
    qvec = embeddings.embed_query(f"{category.name}. {category.description}")
    distance = Ticket.embedding.cosine_distance(qvec)
    #sql: SELECT tickets.*, embedding <=> :qvec AS distance FROM tickets
    #     WHERE embedding IS NOT NULL AND (category_id IS NULL OR category_id <> :category_id)
    #     ORDER BY distance LIMIT :limit
    stmt = (
        select(Ticket, distance.label("distance"))
        .where(
            Ticket.embedding.is_not(None),
            (Ticket.category_id.is_(None)) | (Ticket.category_id != category.id),
        )
        .order_by(distance)
        .limit(min(limit, 50))
    )
    return [
        RelabelCandidate(
            ref=t.ref,
            subject=t.subject,
            snippet=t.complaint[:160],
            current_category=t.category.name if t.category else None,
            similarity=round(1 - float(d), 3),
        )
        for t, d in db.execute(stmt)
    ]


@router.post("/{category_id}/relabel")
def relabel(category_id: int, body: RelabelIn, db: Session = Depends(get_db), user: User = Depends(analyst_or_admin)):
    category = load(db, category_id)
    refs = [r.upper() for r in body.refs]
    #sql: UPDATE tickets SET category_id = :category_id WHERE ref IN (:refs)
    result = db.execute(update(Ticket).where(Ticket.ref.in_(refs)).values(category_id=category.id))
    audit.record(db, user, "category.relabel", "category", category.slug, tickets=refs)
    db.commit()
    return {"updated": result.rowcount}
