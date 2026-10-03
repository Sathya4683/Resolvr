"""pdf reports and the daily digest email"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.models import DigestRun
from app.services import digest
from app.services.reports import build_digest_pdf, build_quality_pdf


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(digest, "send_email", lambda to, subject, text, **kw: sent.append((to, subject, kw)) or True)
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com,lead@example.com")
    return sent


def today():
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def test_pdfs_are_valid_even_when_empty(db):
    assert build_digest_pdf(db, today()).startswith(b"%PDF")
    assert build_quality_pdf(db, date(2026, 10, 1), today()).startswith(b"%PDF")


def test_digest_pdf_with_data(client, headers, knowledge):
    client.post("/v1/tickets", headers=headers["support_agent"], json={"complaint": "internet drops every evening"})
    res = client.get("/v1/reports/digest.pdf", headers=headers["admin"])
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF") and len(res.content) > 2000


def test_scheduled_digest_is_sent_once_per_day(db, outbox):
    first = digest.send_scheduled(db, today())
    assert first.status == "sent"
    #a second scheduler (or a restart) for the same day does nothing
    assert digest.send_scheduled(db, today()) is None
    assert len(outbox) == 1
    to, subject, kw = outbox[0]
    assert to == ["boss@example.com", "lead@example.com"]
    assert kw["attachments"][0][0].endswith(".pdf")
    assert db.query(DigestRun).filter_by(trigger="cron").count() == 1


def test_failed_email_is_recorded_and_alerted(db, monkeypatch):
    alerts = []
    monkeypatch.setattr(digest, "send_email", lambda *a, **k: False)
    monkeypatch.setattr(digest.notify, "dispatch", lambda a: alerts.extend(a))
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    run = digest.send_scheduled(db, today())
    assert run.status == "failed"
    assert alerts and "failed" in alerts[0].title


def test_send_now_and_runs_list(client, headers, outbox):
    res = client.post("/v1/reports/digest/send", headers=headers["admin"])
    assert res.status_code == 200 and res.json()["status"] == "sent"
    runs = client.get("/v1/reports/digests", headers=headers["admin"]).json()
    assert runs[0]["trigger"] == "manual"


def test_report_access(client, headers):
    assert client.get("/v1/reports/digest.pdf", headers=headers["support_agent"]).status_code == 403
    assert client.get("/v1/reports/digest.pdf", headers=headers["analyst"]).status_code == 403
    assert client.get("/v1/reports/quality.pdf", headers=headers["analyst"]).status_code == 200
    assert client.get("/v1/reports/quality.pdf", headers=headers["support_agent"]).status_code == 403
    assert client.post("/v1/reports/digest/send", headers=headers["analyst"]).status_code == 403
