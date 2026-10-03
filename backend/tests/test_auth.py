from tests.conftest import PASSWORD


def test_login_returns_token_and_user(client, users):
    res = client.post("/v1/auth/login", json={"username": "agent", "password": PASSWORD, "role": "support_agent"})
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["user"]["role"] == "support_agent"


def test_wrong_password_is_rejected(client, users):
    res = client.post("/v1/auth/login", json={"username": "agent", "password": "nope"})
    assert res.status_code == 401


def test_login_tab_must_match_role(client, users):
    #an agent trying to sign in from the admin tab
    res = client.post("/v1/auth/login", json={"username": "agent", "password": PASSWORD, "role": "admin"})
    assert res.status_code == 403


def test_me_needs_a_token(client):
    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_disabled_user_cannot_login(client, users, db):
    users["support_agent"].is_active = False
    db.commit()
    res = client.post("/v1/auth/login", json={"username": "agent", "password": PASSWORD})
    assert res.status_code == 403
