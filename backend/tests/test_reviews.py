"""analyst review queue: one analyst per item, corrections feed back into future analyses"""

from datetime import datetime, timedelta, timezone

import pytest

from app.llm.fake import FakeProvider
from app.models import Analysis, User
from app.security import hash_password
from tests.conftest import PASSWORD, classify_response, login

COMPLAINT = "internet drops every evening, router restarted twice"
REVIEW = {
    "verdict": "partially_correct",
    "citations_ok": True,
    "rubric": {"correct": True, "safe": True, "actionable": True, "complete": False},
    "corrections": {"severity": "medium"},
    "notes": "evening drops without an outage are medium, not high",
}


@pytest.fixture
def analysis_id(client, headers, knowledge):
    FakeProvider.queue("classify", classify_response(severity="high"))
    ticket = client.post("/v1/tickets", headers=headers["support_agent"], json={"complaint": COMPLAINT}).json()
    return ticket["analysis"]["id"]


@pytest.fixture
def second_analyst(client, db):
    db.add(User(username="analyst2", full_name="Second Analyst", role="analyst", password_hash=hash_password(PASSWORD)))
    db.commit()
    return login(client, "analyst2")


def test_queue_lists_unreviewed_analyses(client, headers, analysis_id):
    queue = client.get("/v1/reviews/queue", headers=headers["analyst"]).json()
    assert [q["analysis_id"] for q in queue] == [analysis_id]
    assert queue[0]["reasons"]


def test_only_one_analyst_can_hold_an_item(client, headers, analysis_id, second_analyst):
    assert client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers["analyst"]).status_code == 200
    res = client.post(f"/v1/reviews/{analysis_id}/claim", headers=second_analyst)
    assert res.status_code == 409
    assert "Analyst is reviewing" in res.json()["detail"]
    #the other analyst sees it as locked in the queue
    queue = client.get("/v1/reviews/queue", headers=second_analyst).json()
    assert queue[0]["locked"] is True and queue[0]["claimed_by"] == "Analyst"
    #re-claiming your own item just extends the lock
    assert client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers["analyst"]).status_code == 200


def test_expired_lock_can_be_taken_over(client, headers, analysis_id, second_analyst, db):
    client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers["analyst"])
    analysis = db.get(Analysis, analysis_id)
    analysis.claimed_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    db.commit()
    assert client.post(f"/v1/reviews/{analysis_id}/claim", headers=second_analyst).status_code == 200


def test_release_frees_the_item(client, headers, analysis_id, second_analyst):
    client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers["analyst"])
    assert client.post(f"/v1/reviews/{analysis_id}/release", headers=headers["analyst"]).status_code == 204
    assert client.post(f"/v1/reviews/{analysis_id}/claim", headers=second_analyst).status_code == 200


def test_submit_needs_the_claim(client, headers, analysis_id):
    assert client.post(f"/v1/reviews/{analysis_id}", headers=headers["analyst"], json=REVIEW).status_code == 409


def test_review_is_saved_and_only_once(client, headers, analysis_id, second_analyst):
    client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers["analyst"])
    res = client.post(f"/v1/reviews/{analysis_id}", headers=headers["analyst"], json=REVIEW)
    assert res.status_code == 201
    body = res.json()
    assert body["corrected_labels"] == {"severity": "medium"}
    assert body["original_labels"]["severity"] == "high"
    #reviewed items leave the queue and can't be claimed again
    assert client.get("/v1/reviews/queue", headers=second_analyst).json() == []
    assert client.post(f"/v1/reviews/{analysis_id}/claim", headers=second_analyst).status_code == 409


def test_analyst_note_becomes_guidance_for_similar_complaints(client, headers, analysis_id):
    client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers["analyst"])
    client.post(f"/v1/reviews/{analysis_id}", headers=headers["analyst"], json=REVIEW)

    FakeProvider.queue("classify", classify_response())
    ticket = client.post("/v1/tickets", headers=headers["support_agent"], json={"complaint": COMPLAINT}).json()
    guidance = ticket["analysis"]["parsed"]["guidance_used"]
    assert guidance and "medium, not high" in guidance[0]


def test_quality_summary_reflects_reviews(client, headers, analysis_id):
    client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers["analyst"])
    client.post(f"/v1/reviews/{analysis_id}", headers=headers["analyst"], json=REVIEW)
    summary = client.get("/v1/quality/summary", headers=headers["admin"]).json()
    assert summary["reviews"] == 1
    assert summary["agreement"]["severity"] == 0.0
    assert summary["agreement"]["category"] == 1.0


def test_roles(client, headers, analysis_id):
    for role in ("support_agent", "admin"):
        assert client.post(f"/v1/reviews/{analysis_id}/claim", headers=headers[role]).status_code == 403
    assert client.get("/v1/reviews/queue", headers=headers["support_agent"]).status_code == 403
    #analysts can't approve critical drafts
    assert client.post(f"/v1/approvals/{analysis_id}/decision", headers=headers["analyst"],
                       json={"action": "approve"}).status_code == 403


def test_only_the_latest_analysis_of_a_ticket_is_queued(client, headers, analysis_id):
    ticket = client.get("/v1/reviews/queue", headers=headers["analyst"]).json()[0]["ticket_ref"]
    FakeProvider.queue("classify", classify_response())
    client.post(f"/v1/tickets/{ticket}/reanalyze", headers=headers["support_agent"])
    queue = client.get("/v1/reviews/queue", headers=headers["analyst"]).json()
    assert [q["ticket_ref"] for q in queue] == [ticket]
    assert queue[0]["analysis_id"] != analysis_id
