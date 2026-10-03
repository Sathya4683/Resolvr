"""rate limits, helpdesk webhook, input limits"""

import pytest

from app import ratelimit
from app.config import settings


class FakeRedis:
    """just enough of redis for the fixed window counter"""

    def __init__(self):
        self.store = {}

    def pipeline(self):
        return self

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        self._last = self.store[key]

    def expire(self, key, seconds):
        pass

    def execute(self):
        return [self._last, True]


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "_client", fake)
    return fake


def test_analyze_is_rate_limited_per_user(client, headers, knowledge, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_analyze_per_min", 2)
    body = {"complaint": "internet drops every evening"}
    for _ in range(2):
        assert client.post("/v1/tickets", headers=headers["support_agent"], json=body).status_code == 201
    res = client.post("/v1/tickets", headers=headers["support_agent"], json=body)
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) > 0
    #admins have their own counter (and double the limit)
    assert client.post("/v1/tickets", headers=headers["admin"], json=body).status_code == 201


def test_rate_limiter_fails_open_without_redis(client, headers, knowledge):
    #conftest points REDIS_URL at a closed port
    assert client.post("/v1/tickets", headers=headers["support_agent"],
                       json={"complaint": "internet drops every evening"}).status_code == 201


def test_webhook_requires_the_secret(client):
    payload = {"external_id": "ZD-1", "description": "internet drops every evening"}
    assert client.post("/v1/webhooks/helpdesk", json=payload).status_code == 401
    assert client.post("/v1/webhooks/helpdesk", json=payload, headers={"X-Webhook-Secret": "nope"}).status_code == 401


def test_webhook_creates_and_dedupes(client, knowledge):
    payload = {"external_id": "ZD-42", "subject": "Net down", "description": "internet drops every evening"}
    headers = {"X-Webhook-Secret": "test-webhook-secret"}
    first = client.post("/v1/webhooks/helpdesk", json=payload, headers=headers)
    assert first.status_code == 201 and first.json()["duplicate"] is False
    again = client.post("/v1/webhooks/helpdesk", json=payload, headers=headers).json()
    assert again["duplicate"] is True and again["ref"] == first.json()["ref"]


def test_webhook_disabled_without_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", "")
    res = client.post("/v1/webhooks/helpdesk", json={"external_id": "x", "description": "hello there"},
                      headers={"X-Webhook-Secret": "anything"})
    assert res.status_code == 503


def test_complaint_length_is_capped(client, headers):
    res = client.post("/v1/tickets", headers=headers["support_agent"], json={"complaint": "x" * 4001})
    assert res.status_code == 422


def test_errors_never_leak_stack_traces(client, headers, monkeypatch):
    from app.api.v1 import tickets

    def boom(*a, **k):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(tickets.ticket_service, "get_by_ref", boom)
    res = client.get("/v1/tickets/TCK-1", headers=headers["support_agent"])
    assert res.status_code == 500
    assert "secret internals" not in res.text and "request_id" in res.json()
