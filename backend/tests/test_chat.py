"""assistant chat: retrieval-grounded streaming answers"""

import json

from app.llm import LLMError
from app.llm.fake import FakeProvider
from app.models import ChatMessage


def read_events(res) -> list[tuple[str, object]]:
    events = []
    for block in res.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_chat_streams_sources_tokens_and_saves_answer(client, headers, knowledge, db):
    session = client.post("/v1/chat/sessions", headers=headers["support_agent"], json={}).json()
    FakeProvider.queue("chat", {"text": "Restart the router first [KB-001]. Then check cables [KB-999]."})
    res = client.post(f"/v1/chat/sessions/{session['id']}/messages", headers=headers["support_agent"],
                      json={"content": "internet drops every evening, what should I do?"})
    assert res.status_code == 200
    events = read_events(res)
    kinds = [e for e, _ in events]
    assert kinds[0] == "sources" and kinds[-1] == "done" and "token" in kinds
    #only citations of retrieved sources count
    assert events[-1][1]["cited"] == ["KB-001"]

    messages = client.get(f"/v1/chat/sessions/{session['id']}/messages", headers=headers["support_agent"]).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["sources"]
    #first question becomes the chat title
    titles = [s["title"] for s in client.get("/v1/chat/sessions", headers=headers["support_agent"]).json()]
    assert titles[0].startswith("internet drops every evening")


def test_chat_falls_back_when_llm_is_down(client, headers, knowledge, db):
    session = client.post("/v1/chat/sessions", headers=headers["support_agent"], json={}).json()
    FakeProvider.queue("chat", LLMError("quota"))
    res = client.post(f"/v1/chat/sessions/{session['id']}/messages", headers=headers["support_agent"],
                      json={"content": "router keeps restarting"})
    events = read_events(res)
    assert events[-1][1]["error"]
    assert db.query(ChatMessage).filter_by(role="assistant").count() == 1


def test_chat_about_a_ticket(client, headers, knowledge):
    ticket = client.post("/v1/tickets", headers=headers["support_agent"],
                         json={"complaint": "internet drops every evening"}).json()
    session = client.post("/v1/chat/sessions", headers=headers["support_agent"],
                          json={"ticket_ref": ticket["ref"]}).json()
    assert session["ticket_ref"] == ticket["ref"]
    assert session["title"] == f"About {ticket['ref']}"


def test_chats_are_private(client, headers, knowledge):
    session = client.post("/v1/chat/sessions", headers=headers["support_agent"], json={}).json()
    res = client.get(f"/v1/chat/sessions/{session['id']}/messages", headers=headers["admin"])
    assert res.status_code == 404
