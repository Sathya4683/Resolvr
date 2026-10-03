import hashlib
import math
import os
import re

#point everything at the test database before the app is imported
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://resolvr:resolvr@localhost:5434/resolvr_test"
)
os.environ["LLM_PROVIDER"] = "fake"
os.environ["NTFY_ADMIN_TOPIC"] = ""
os.environ["NTFY_AGENT_TOPIC"] = ""
os.environ["RERANKER_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app import embeddings  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.llm.fake import FakeProvider  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.ingest import import_resolved_tickets, save_kb_article  # noqa: E402

PASSWORD = "test-password"


def fake_vector(text_: str) -> list[float]:
    """bag of words hashed into a vector, texts sharing words end up close together"""
    vec = [0.0] * settings.embedding_dim
    for word in re.findall(r"[a-z]+", text_.lower()):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % settings.embedding_dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def fake_models(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_documents", lambda texts, **kw: [fake_vector(t) for t in texts])
    monkeypatch.setattr(embeddings, "embed_query", fake_vector)


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def users(db):
    created = {}
    for username, role in [("agent", "support_agent"), ("admin", "admin"), ("analyst", "analyst")]:
        user = User(username=username, full_name=username.title(), role=role, password_hash=hash_password(PASSWORD))
        db.add(user)
        created[role] = user
    db.commit()
    return created


@pytest.fixture
def categories(db):
    rows = [
        ("broadband_disconnection", "Broadband disconnections", "broadband", "high",
         "Home broadband internet drops repeatedly or disconnects in the evening"),
        ("billing_dispute", "Billing and payments", "billing", "medium",
         "Wrong charges on the bill, payment deducted but not credited"),
        ("legal_regulatory", "Legal and regulatory", None, "critical",
         "Customer threatens legal notice, consumer court or TRAI complaint"),
    ]
    out = {}
    for slug, name, product, sev, desc in rows:
        c = Category(slug=slug, name=name, product=product, default_severity=sev, description=desc)
        db.add(c)
        out[slug] = c
    db.commit()
    return out


def login(client, username: str) -> dict:
    res = client.post("/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def headers(client, users):
    return {
        "support_agent": login(client, "agent"),
        "admin": login(client, "admin"),
        "analyst": login(client, "analyst"),
    }


def classify_response(**overrides):
    data = {
        "category": "broadband_disconnection", "product": "broadband", "severity": "high",
        "critical_reason": "none", "sentiment": "frustrated", "language": "en", "in_scope": True,
        "summary": "evening drops", "confidence": 0.9,
    }
    data.update(overrides)
    return data


@pytest.fixture(autouse=True)
def reset_fake(monkeypatch):
    FakeProvider.reset()
    #bag-of-words test vectors give lower scores than the real model
    monkeypatch.setattr(settings, "abstain_threshold", 0.05)
    yield
    FakeProvider.reset()


@pytest.fixture
def knowledge(db, users, categories):
    import_resolved_tickets(
        db,
        [
            {"complaint": "internet drops every evening, router restarted", "category": "broadband_disconnection",
             "product": "broadband", "severity": "high", "sentiment": "frustrated",
             "resolution_steps": "Changed wifi channel | Updated router firmware",
             "resolution_summary": "wifi congestion"},
            {"complaint": "bill has extra charges i did not ask for", "category": "billing_dispute",
             "product": "billing", "severity": "medium", "sentiment": "angry",
             "resolution_steps": "Explained pro-rata charge", "resolution_summary": "pro-rata"},
        ],
        user=users["admin"],
    )
    save_kb_article(
        db, ref="KB-001", title="Broadband keeps disconnecting", user=users["admin"],
        content_md="## Symptoms\nInternet drops in the evening.\n## Steps\n1. Restart the router.\n2. Check cables.",
        category_slug="broadband_disconnection",
    )
    db.commit()
