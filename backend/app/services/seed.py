"""Loads the demo data from /data into an empty database (categories, users, kb, resolved tickets)."""

import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Category, KbArticle, Ticket, User
from app.security import hash_password
from app.services.ingest import import_resolved_tickets, parse_front_matter, save_kb_article

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))

SEED_USERS = [
    ("ravi", "Ravi Kumar", "support_agent", "ravi@resolvr.local"),
    ("meera", "Meera Nair", "support_agent", "meera@resolvr.local"),
    ("arjun", "Arjun Mehta", "admin", "arjun@resolvr.local"),
    ("kavya", "Kavya Iyer", "analyst", "kavya@resolvr.local"),
    ("rahul", "Rahul Verma", "analyst", "rahul@resolvr.local"),
]


def is_empty(db: Session) -> bool:
    #tickets are loaded last, so if a previous seed got interrupted we simply run it again
    #(every step below is safe to repeat)
    #sql: SELECT count(*) FROM tickets
    return db.scalar(select(func.count(Ticket.id))) == 0


def seed_categories(db: Session) -> int:
    items = json.loads((DATA_DIR / "categories.json").read_text())
    for item in items:
        #sql: SELECT * FROM categories WHERE slug = :slug
        category = db.scalar(select(Category).where(Category.slug == item["slug"]))
        if category is None:
            category = Category(slug=item["slug"])
            db.add(category)
        category.name = item["name"]
        category.description = item["description"]
        category.product = item.get("product")
        category.default_severity = item.get("default_severity", "medium")
        category.is_active = True
    db.flush()
    return len(items)


def seed_users(db: Session) -> int:
    count = 0
    for username, full_name, role, email in SEED_USERS:
        #sql: SELECT id FROM users WHERE username = :username
        if db.scalar(select(User.id).where(User.username == username)):
            continue
        db.add(
            User(
                username=username,
                full_name=full_name,
                role=role,
                email=email,
                password_hash=hash_password(settings.seed_user_password),
            )
        )
        count += 1
    db.flush()
    return count


def seed_kb(db: Session) -> int:
    files = sorted((DATA_DIR / "kb").glob("*.md"))
    for path in files:
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        #sql: SELECT * FROM kb_articles WHERE ref = :ref
        existing = db.scalar(select(KbArticle).where(KbArticle.ref == meta.get("ref")))
        if existing and existing.content_md == body:
            continue  #already loaded and unchanged, no need to embed it again
        save_kb_article(
            db,
            ref=meta.get("ref"),
            title=meta.get("title", path.stem),
            content_md=body,
            product=meta.get("product"),
            category_slug=meta.get("category"),
            tags=meta.get("tags", []),
            user=None,
        )
    #new articles created from the ui continue after the highest seeded number
    #sql: SELECT setval('kb_ref_seq', (SELECT count(*) FROM kb_articles))
    db.execute(text("SELECT setval('kb_ref_seq', GREATEST((SELECT count(*) FROM kb_articles), 1))"))
    return len(files)


def seed_tickets(db: Session) -> dict:
    with (DATA_DIR / "tickets_resolved.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    #the demo data covers 1-3 oct, if we seed in the middle of one of those days we don't want
    #tickets "from the future" showing up in the sidebar or the daily report
    now = datetime.now(timezone.utc)
    current = [r for r in rows if datetime.fromisoformat(r["resolved_at"]) <= now]
    if len(current) < len(rows):
        log.info("skipping future dated demo tickets", extra={"skipped": len(rows) - len(current)})
    return import_resolved_tickets(db, current, user=None, source="seed")


def run_seed(db: Session, if_empty: bool = False) -> None:
    if if_empty and not is_empty(db):
        log.info("database already has data, skipping seed")
        return

    log.info("seeding database", extra={"data_dir": str(DATA_DIR)})
    categories = seed_categories(db)
    users = seed_users(db)
    db.commit()
    articles = seed_kb(db)
    db.commit()
    report = seed_tickets(db)
    db.commit()

    #sql: SELECT count(*) FROM tickets WHERE is_searchable = true
    searchable = db.scalar(select(func.count(Ticket.id)).where(Ticket.is_searchable.is_(True)))
    #sql: SELECT count(*) FROM kb_articles
    kb_total = db.scalar(select(func.count(KbArticle.id)))
    log.info(
        "seed finished",
        extra={
            "categories": categories,
            "users_created": users,
            "kb_files": articles,
            "kb_total": kb_total,
            "tickets_inserted": report["inserted"],
            "ticket_errors": len(report["errors"]),
            "searchable_tickets": searchable,
        },
    )
