"""batch csv jobs, outage detection and overdue review alerts"""

import io
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.llm.fake import FakeProvider
from app.models import Analysis, AuditLog, BatchJob, Notification
from app.services import jobs, notify
from tests.conftest import classify_response


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    pushed = []
    monkeypatch.setattr(notify, "push", lambda alert: pushed.append(alert))
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: True)
    monkeypatch.setattr(settings, "llm_min_interval_ms", 0)
    return pushed


def upload(client, headers, text):
    files = {"file": ("complaints.csv", io.BytesIO(text.encode()), "text/csv")}
    return client.post("/v1/batch", headers=headers["support_agent"], files=files)


def test_batch_csv_is_queued_then_processed(client, headers, knowledge, db):
    res = upload(client, headers, "complaint,channel\ninternet drops every evening,phone\nhi,chat\n")
    assert res.status_code == 202
    job = res.json()
    assert job["status"] == "queued" and job["total"] == 2

    claimed = jobs.claim_next_job(db)
    assert claimed.id == job["id"]
    jobs.process_job(db, claimed)

    done = client.get(f"/v1/batch/{job['id']}", headers=headers["support_agent"]).json()
    assert done["status"] == "done" and done["processed"] == 2 and done["failed"] == 1
    assert done["results"][0]["ticket_ref"].startswith("TCK-")
    assert "too short" in done["results"][1]["error"]

    csv_text = client.get(f"/v1/batch/{job['id']}/results.csv", headers=headers["support_agent"]).text
    assert csv_text.startswith("row,ticket_ref")
    assert db.query(Notification).filter_by(kind="batch_done").count() == 1


def test_batch_rejects_csv_without_complaint_column(client, headers):
    assert upload(client, headers, "text\nhello\n").status_code == 400


def test_batch_never_touches_the_knowledge_base(client, headers, knowledge, db):
    from app.models import Ticket

    before = db.query(Ticket).filter_by(is_searchable=True).count()
    upload(client, headers, "complaint\ninternet drops every evening\n")
    jobs.process_job(db, jobs.claim_next_job(db))
    assert db.query(Ticket).filter_by(is_searchable=True).count() == before


def test_other_agents_cannot_see_my_job(client, headers, db):
    job = upload(client, headers, "complaint\ninternet drops every evening\n").json()
    assert client.get(f"/v1/batch/{job['id']}", headers=headers["analyst"]).status_code == 403
    assert client.get(f"/v1/batch/{job['id']}", headers=headers["admin"]).status_code == 200


def test_outage_alert_fires_once_for_a_cluster(client, headers, knowledge, db, quiet, monkeypatch):
    monkeypatch.setattr(settings, "outage_min_count", 3)
    monkeypatch.setattr(settings, "outage_similarity", 0.8)
    complaint = "whole area in indiranagar has no internet since evening"
    refs = []
    for _ in range(4):
        t = client.post("/v1/tickets", headers=headers["support_agent"], json={"complaint": complaint}).json()
        refs.append(t)
    assert "outage_refs" not in refs[1]["analysis"]["parsed"]
    assert len(refs[2]["analysis"]["parsed"]["outage_refs"]) == 3
    #the 4th complaint belongs to the same cluster, no second alert
    assert "outage_refs" not in refs[3]["analysis"]["parsed"]
    assert db.query(AuditLog).filter_by(action="outage.detected").count() == 1
    assert any("Possible outage" in a.title for a in quiet)


def test_overdue_reviews_are_re_alerted_once_per_window(client, headers, knowledge, db, quiet):
    FakeProvider.queue("classify", classify_response(severity="critical", critical_reason="legal"))
    client.post("/v1/tickets", headers=headers["support_agent"], json={"complaint": "my lawyer will send a notice"})
    analysis = db.query(Analysis).one()
    analysis.created_at = datetime.now(timezone.utc) - timedelta(minutes=settings.review_sla_minutes + 5)
    db.commit()

    assert jobs.alert_overdue_reviews(db) == 1
    assert jobs.alert_overdue_reviews(db) == 0
    assert any("Review overdue" in a.title for a in quiet)


def test_worker_job_status_metric_free_path(db, users):
    #a job with only invalid rows still finishes cleanly
    db.add(BatchJob(kind="analyze_csv", rows=[{"row": 1, "complaint": "", "error": "empty"}], total=1,
                    created_by_id=users["support_agent"].id))
    db.commit()
    job = jobs.claim_next_job(db)
    jobs.process_job(db, job)
    assert job.status == "done" and job.failed == 1
