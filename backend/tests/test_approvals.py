"""critical drafts wait for an admin, decisions notify the agent, agents can't decide"""

import pytest

from app.llm.fake import FakeProvider
from app.models import AuditLog, Notification
from app.services import notify
from tests.conftest import classify_response


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "push", lambda alert: sent.append(("push", alert)))
    monkeypatch.setattr(notify, "send_email", lambda *a, **k: sent.append(("email", a)) or True)
    FakeProvider.reset()
    return sent


@pytest.fixture
def critical_ticket(client, headers, knowledge):
    FakeProvider.queue("classify", classify_response(severity="critical", critical_reason="legal"))
    res = client.post("/v1/tickets", headers=headers["support_agent"],
                      json={"complaint": "internet drops every evening, my lawyer will send a legal notice"})
    return res.json()


def test_critical_case_notifies_admins(critical_ticket, db, users, no_network, monkeypatch):
    assert critical_ticket["status"] == "pending_review"
    admin_notes = db.query(Notification).filter_by(user_id=users["admin"].id).all()
    assert any(n.kind == "approval_needed" for n in admin_notes)
    assert any(kind == "push" for kind, _ in no_network)


def test_queue_lists_pending_cases(client, headers, critical_ticket):
    assert client.get("/v1/approvals/count", headers=headers["admin"]).json()["pending"] == 1
    items = client.get("/v1/approvals", headers=headers["admin"]).json()
    assert items[0]["ticket_ref"] == critical_ticket["ref"]


def test_approve_shows_draft_to_agent_and_notifies(client, headers, critical_ticket, db, users):
    aid = critical_ticket["analysis"]["id"]
    res = client.post(f"/v1/approvals/{aid}/decision", headers=headers["admin"], json={"action": "approve"})
    assert res.status_code == 200

    agent_view = client.get(f"/v1/tickets/{critical_ticket['ref']}", headers=headers["support_agent"]).json()
    assert agent_view["status"] == "open"
    assert agent_view["analysis"]["draft_hidden"] is False and agent_view["analysis"]["steps"]
    assert db.query(Notification).filter_by(user_id=users["support_agent"].id, kind="decision").count() == 1
    assert db.query(AuditLog).filter_by(action="approval.approve").count() == 1


def test_edit_replaces_steps(client, headers, critical_ticket):
    aid = critical_ticket["analysis"]["id"]
    ref = critical_ticket["analysis"]["retrieved"][0]["ref"]
    steps = [{"text": "Escalate to the legal desk with the full history", "citations": [ref]}]
    res = client.post(f"/v1/approvals/{aid}/decision", headers=headers["admin"],
                      json={"action": "edit", "steps": steps, "comment": "use the legal desk"})
    assert res.status_code == 200
    agent_view = client.get(f"/v1/tickets/{critical_ticket['ref']}", headers=headers["support_agent"]).json()
    assert agent_view["analysis"]["steps"] == steps
    assert agent_view["analysis"]["review_status"] == "edited"


def test_edit_rejects_unknown_citation(client, headers, critical_ticket):
    aid = critical_ticket["analysis"]["id"]
    res = client.post(f"/v1/approvals/{aid}/decision", headers=headers["admin"],
                      json={"action": "edit", "steps": [{"text": "x", "citations": ["KB-999"]}]})
    assert res.status_code == 422


def test_rejected_draft_is_never_shown(client, headers, critical_ticket):
    aid = critical_ticket["analysis"]["id"]
    assert client.post(f"/v1/approvals/{aid}/decision", headers=headers["admin"],
                       json={"action": "reject"}).status_code == 422  #needs a reason
    res = client.post(f"/v1/approvals/{aid}/decision", headers=headers["admin"],
                      json={"action": "reject", "comment": "handle via the legal desk"})
    assert res.status_code == 200
    agent_view = client.get(f"/v1/tickets/{critical_ticket['ref']}", headers=headers["support_agent"]).json()
    assert agent_view["analysis"]["draft_hidden"] is True and agent_view["analysis"]["steps"] == []


def test_cannot_decide_twice(client, headers, critical_ticket):
    aid = critical_ticket["analysis"]["id"]
    client.post(f"/v1/approvals/{aid}/decision", headers=headers["admin"], json={"action": "approve"})
    res = client.post(f"/v1/approvals/{aid}/decision", headers=headers["admin"], json={"action": "approve"})
    assert res.status_code == 409


def test_non_critical_skips_the_queue(client, headers, knowledge):
    FakeProvider.queue("classify", classify_response(severity="medium"))
    ticket = client.post("/v1/tickets", headers=headers["support_agent"],
                         json={"complaint": "internet drops every evening"}).json()
    assert ticket["analysis"]["review_status"] == "auto_approved"
    assert client.get("/v1/approvals/count", headers=headers["admin"]).json()["pending"] == 0


def test_agent_and_analyst_cannot_decide(client, headers, critical_ticket):
    aid = critical_ticket["analysis"]["id"]
    for role in ("support_agent", "analyst"):
        res = client.post(f"/v1/approvals/{aid}/decision", headers=headers[role], json={"action": "approve"})
        assert res.status_code == 403


def test_notifications_read_flow(client, headers, critical_ticket):
    notes = client.get("/v1/notifications", headers=headers["admin"]).json()
    assert notes and notes[0]["is_read"] is False
    assert client.post(f"/v1/notifications/{notes[0]['id']}/read", headers=headers["admin"]).status_code == 204
    assert client.get("/v1/notifications", headers=headers["admin"]).json()[0]["is_read"] is True
