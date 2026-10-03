"""
Every admin-only endpoint must return 403 for support agents and analysts.
The list grows as endpoints are added.
"""

import pytest

ADMIN_ONLY = [
    ("get", "/v1/users"),
    ("post", "/v1/users"),
    ("patch", "/v1/users/1"),
    ("post", "/v1/categories"),
    ("patch", "/v1/categories/1"),
    ("get", "/v1/categories/1/candidates"),
    ("post", "/v1/categories/1/relabel"),
    ("post", "/v1/data/tickets/import"),
    ("post", "/v1/data/tickets"),
    ("post", "/v1/data/kb/import"),
    ("get", "/v1/data/tickets/promotable"),
    ("post", "/v1/data/tickets/promote"),
    ("post", "/v1/kb/KB-001/archive"),
    ("get", "/v1/approvals"),
    ("get", "/v1/approvals/count"),
    ("post", "/v1/approvals/1/decision"),
]

#support agents can read the kb but must never write to it
KB_WRITES = [
    ("post", "/v1/kb"),
    ("put", "/v1/kb/KB-001"),
    ("post", "/v1/kb/upload"),
]


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
@pytest.mark.parametrize("role", ["support_agent", "analyst"])
def test_non_admins_get_403(client, headers, role, method, path):
    res = client.request(method, path, headers=headers[role], json={})
    assert res.status_code == 403, f"{role} {method.upper()} {path} -> {res.status_code}"


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_anonymous_gets_401(client, method, path):
    res = client.request(method, path, json={})
    assert res.status_code == 401


def test_admin_can_manage_users(client, headers):
    res = client.post(
        "/v1/users",
        headers=headers["admin"],
        json={"username": "new.agent", "full_name": "New Agent", "role": "support_agent", "password": "longpassword1"},
    )
    assert res.status_code == 201
    user_id = res.json()["id"]

    res = client.patch(f"/v1/users/{user_id}", headers=headers["admin"], json={"is_active": False})
    assert res.status_code == 200
    assert res.json()["is_active"] is False


def test_admin_cannot_disable_self(client, headers, users):
    res = client.patch(f"/v1/users/{users['admin'].id}", headers=headers["admin"], json={"is_active": False})
    assert res.status_code == 400


@pytest.mark.parametrize("method,path", KB_WRITES)
def test_support_agent_cannot_write_kb(client, headers, method, path):
    res = client.request(method, path, headers=headers["support_agent"], json={})
    assert res.status_code == 403
