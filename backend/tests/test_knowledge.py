"""evolving data and classes: categories, kb articles, imports and promotion"""

import io

from app.llm.fake import FakeProvider
from app.models import Ticket
from tests.conftest import classify_response


def csv_file(text: str, name: str = "data.csv"):
    return {"file": (name, io.BytesIO(text.encode()), "text/csv")}


def test_admin_adds_category_and_it_is_listed(client, headers, categories):
    res = client.post(
        "/v1/categories",
        headers=headers["admin"],
        json={"name": "5G Home Router Issues", "description": "Problems with the 5G fixed wireless home router",
              "product": "broadband", "default_severity": "medium"},
    )
    assert res.status_code == 201
    assert res.json()["slug"] == "5g_home_router_issues"
    slugs = [c["slug"] for c in client.get("/v1/categories", headers=headers["support_agent"]).json()]
    assert "5g_home_router_issues" in slugs


def test_deactivated_category_disappears_from_the_list(client, headers, categories):
    cid = categories["billing_dispute"].id
    res = client.patch(f"/v1/categories/{cid}", headers=headers["admin"], json={"is_active": False})
    assert res.status_code == 200
    slugs = [c["slug"] for c in client.get("/v1/categories", headers=headers["admin"]).json()]
    assert "billing_dispute" not in slugs


def test_relabel_candidates_and_relabel(client, headers, categories):
    rows = (
        "complaint,category,severity,resolution_steps\n"
        "my 5g home router shows one bar,broadband_disconnection,medium,moved router near window\n"
        "bill has extra charges,billing_dispute,medium,explained the bill\n"
    )
    client.post("/v1/data/tickets/import", headers=headers["admin"], files=csv_file(rows))
    new = client.post("/v1/categories", headers=headers["admin"],
                      json={"name": "5G router", "description": "5g home router signal problems one bar"}).json()

    candidates = client.get(f"/v1/categories/{new['id']}/candidates", headers=headers["admin"]).json()
    assert candidates[0]["snippet"].startswith("my 5g home router")
    res = client.post(f"/v1/categories/{new['id']}/relabel", headers=headers["admin"],
                      json={"refs": [candidates[0]["ref"]]})
    assert res.json()["updated"] == 1


def test_ticket_csv_import_reports_rows_and_is_idempotent(client, headers, categories):
    rows = (
        "complaint,category,severity,resolution_steps\n"
        "internet drops every night,broadband_disconnection,high,restart router | change channel\n"
        "bad row,no_such_category,high,step\n"
        "missing steps,billing_dispute,medium,\n"
    )
    first = client.post("/v1/data/tickets/import", headers=headers["admin"], files=csv_file(rows)).json()
    assert first["inserted"] == 1
    assert {e["row"] for e in first["errors"]} == {2, 3}

    again = client.post("/v1/data/tickets/import", headers=headers["admin"], files=csv_file(rows)).json()
    assert again["inserted"] == 0 and again["duplicates"] == 1


def test_csv_with_missing_columns_is_rejected(client, headers, categories):
    res = client.post("/v1/data/tickets/import", headers=headers["admin"], files=csv_file("complaint\nhi\n"))
    assert res.status_code == 400


def test_kb_article_is_searchable_right_after_saving(client, headers, categories):
    md = "## Symptoms\nThe 5G home router keeps rebooting at night.\n## Steps\n1. Update firmware.\n2. Re-seat the SIM."
    res = client.post("/v1/kb", headers=headers["analyst"],
                      json={"title": "5G router reboot loop", "content_md": md,
                            "category_slug": "broadband_disconnection"})
    assert res.status_code == 201
    article = res.json()
    assert article["ref"].startswith("KB-") and article["chunks"] == 2

    #the very next analysis can already retrieve it
    FakeProvider.queue("classify", classify_response())
    ticket = client.post("/v1/tickets", headers=headers["support_agent"],
                         json={"complaint": "my 5g home router keeps rebooting every night"}).json()
    assert article["ref"] in {s["ref"] for s in ticket["analysis"]["retrieved"]}


def test_markdown_upload_reads_front_matter(client, headers, categories):
    md = (
        "---\ntitle: Router lights explained\ncategory: broadband_disconnection\ntags: router, lights\n---\n"
        "## Steps\n1. Check the PON light.\n2. Check the LOS light."
    )
    res = client.post("/v1/kb/upload", headers=headers["admin"],
                      files={"file": ("router.md", io.BytesIO(md.encode()), "text/markdown")})
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "Router lights explained"
    assert body["tags"] == ["router", "lights"]
    assert body["category"]["slug"] == "broadband_disconnection"


def test_kb_update_bumps_version(client, headers, categories):
    md = "## Steps\n1. Restart the set top box.\n2. Check the dish cable."
    ref = client.post("/v1/kb", headers=headers["admin"], json={"title": "STB basics", "content_md": md}).json()["ref"]
    res = client.put(f"/v1/kb/{ref}", headers=headers["admin"],
                     json={"title": "STB basics v2", "content_md": md + "\n3. Call support."})
    assert res.json()["version"] == 2 and res.json()["title"] == "STB basics v2"


def test_promote_agent_resolved_ticket(client, headers, categories, db):
    ticket = client.post("/v1/tickets", headers=headers["support_agent"],
                         json={"complaint": "wifi password reset needed"}).json()
    client.post(f"/v1/tickets/{ticket['ref']}/resolve", headers=headers["support_agent"],
                json={"steps": ["Guided the customer through the app"]})

    promotable = client.get("/v1/data/tickets/promotable", headers=headers["admin"]).json()
    assert ticket["ref"] in [p["ref"] for p in promotable]

    res = client.post("/v1/data/tickets/promote", headers=headers["admin"], json={"refs": [ticket["ref"]]})
    assert res.json()["promoted"] == [ticket["ref"]]
    db.expire_all()
    assert db.query(Ticket).filter_by(ref=ticket["ref"]).one().is_searchable is True


def test_analyst_can_add_a_category_and_use_it_in_an_article(client, headers, categories):
    res = client.post("/v1/categories", headers=headers["analyst"],
                      json={"name": "OTT App Subscriptions",
                            "description": "Streaming apps bundled with the plan are not activating"})
    assert res.status_code == 201
    md = "## Steps\n1. Check Plan > Bundled apps in CRM.\n2. Resend the activation link."
    res = client.post("/v1/kb", headers=headers["analyst"],
                      json={"title": "Bundled OTT app not active", "content_md": md,
                            "category_slug": "ott_app_subscriptions"})
    assert res.status_code == 201


def test_unknown_category_error_says_what_to_do(client, headers, categories):
    res = client.post("/v1/kb", headers=headers["analyst"],
                      json={"title": "Something new", "content_md": "## Steps\n1. Do the thing properly.",
                            "category_slug": "not_there_yet"})
    assert res.status_code == 422 and "Add it under Categories first" in res.json()["detail"]


def test_analyst_can_promote_a_resolved_ticket(client, headers, categories, db):
    ticket = client.post("/v1/tickets", headers=headers["support_agent"],
                         json={"complaint": "dth channels missing after recharge"}).json()
    client.post(f"/v1/tickets/{ticket['ref']}/resolve", headers=headers["support_agent"],
                json={"steps": ["Sent a refresh command from CRM"]})
    promotable = client.get("/v1/data/tickets/promotable", headers=headers["analyst"]).json()
    assert ticket["ref"] in [p["ref"] for p in promotable]
    res = client.post("/v1/data/tickets/promote", headers=headers["analyst"], json={"refs": [ticket["ref"]]})
    assert res.json()["promoted"] == [ticket["ref"]]
