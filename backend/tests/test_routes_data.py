import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

import repo

pytestmark = pytest.mark.db

DETAILS = {"full_name": "Test Person", "university": "University A", "course": "MSc Course A", "graduation_date": "2026-09-17",
           "visa_type": "student", "visa_end_date": "2027-01-31", "locations": ["London"]}
APP = {"company": "Company A", "role": "Role A", "source": "Company site"}
GONE = "That item no longer exists"


def test_every_route_but_config_needs_a_token():
    import main
    anonymous = TestClient(main.app)
    checked = 0
    for route in main.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api") or path == "/api/config":
            continue
        url = path.replace("{conversation_id}", "conv_1")
        for name in ("id", "app_id", "job_id", "family_id", "achievement_id", "entry_id"):
            url = url.replace("{" + name + "}", str(uuid.uuid4()))
        assert "{" not in url, f"unfilled path parameter in {path}"
        for method in route.methods - {"HEAD", "OPTIONS"}:
            r = anonymous.request(method, url, json={})
            assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a token"
            checked += 1
    assert checked >= 9


def test_config_is_public_and_has_no_secret(monkeypatch):
    import main
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co/")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_never_show")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@example.test")
    r = TestClient(main.app).get("/api/config")
    assert r.json() == {"supabase_url": "https://proj.supabase.co", "supabase_publishable_key": "sb_publishable_test",
                        "contact_email": "hello@example.test"}
    assert "sb_secret_never_show" not in r.text


def test_state_for_new_user(client):
    s = client.get("/api/state").json()
    assert s["details_complete"] is False
    assert s["profile"]["full_name"] == "Test Person" and s["profile"]["first_name"] == "Test" and s["profile"]["email"] == "a@example.test"
    for key in ("achievements", "role_families", "saved_jobs", "cv_versions", "stories", "applications", "journal"):
        assert s[key] == []
    assert len(s["next_steps"]) == 6 and not any(x["done"] for x in s["next_steps"])
    assert s["usage"] == {"ai": {"used": 0, "limit": 40}, "voice": {"used": 0, "limit": 3}}
    assert s["stats"]["findings"] == [] and s["stats"]["funnel"]["applied"] == 0
    assert "Company site" in s["options"]["sources"] and "applied" in s["options"]["stages"]
    assert set(s["config"]) == {"llm", "voice"}


def test_content_in_state(client):
    c = client.get("/api/state").json()["content"]
    assert len(c["uk_market"]) == 5 and len(c["tone_phrases"]) == 8


def test_put_profile_completes_details(client):
    p = client.put("/api/profile", json=DETAILS).json()
    assert p["graduation_date"] == "2026-09-01" and p["first_name"] == "Test"
    assert client.get("/api/state").json()["details_complete"] is True


@pytest.mark.parametrize("change", [{"visa_type": "tourist"}, {"locations": []}, {"locations": ["a", "b", "c", "d", "e", "f"]},
                                    {"university": "  "}, {"full_name": ""}, {"visa_end_date": "soon"}, {"locations": ["  "]}])
def test_put_profile_validation(client, change):
    assert client.put("/api/profile", json=DETAILS | change).status_code == 422


def test_application_crud(client):
    r = client.post("/api/applications", json=APP | {"posted_on": "2026-10-01", "applied_on": "2026-10-02", "notes": "n"})
    assert r.status_code == 201
    a = r.json()
    assert a["stage"] == "applied" and a["posted_on"] == "2026-10-01"
    patched = client.patch(f"/api/applications/{a['id']}", json={"stage": "interview"}).json()
    assert patched["stage"] == "interview" and patched["notes"] == "n"
    s = client.get("/api/state").json()
    assert s["stats"]["funnel"]["interviews"] == 1 and s["next_steps"][5]["done"] is True
    assert client.delete(f"/api/applications/{a['id']}").status_code == 204
    again = client.delete(f"/api/applications/{a['id']}")
    assert again.status_code == 404 and again.json()["detail"] == GONE


@pytest.mark.parametrize("change", [{"source": "Carrier pigeon"}, {"stage": "hired"}, {"company": ""}, {"role": " "}])
def test_application_bad_input_422(client, change):
    assert client.post("/api/applications", json=APP | change).status_code == 422


def test_posted_after_applied_422(client):
    r = client.post("/api/applications", json=APP | {"posted_on": "2026-10-10", "applied_on": "2026-10-01"})
    assert r.status_code == 422
    a = client.post("/api/applications", json=APP | {"applied_on": "2026-10-01"}).json()
    r = client.patch(f"/api/applications/{a['id']}", json={"posted_on": "2026-10-10"})
    assert r.status_code == 422 and r.json()["detail"] == "The posting date cannot be after the application date."
    assert client.get("/api/state").json()["applications"][0]["posted_on"] is None


def test_patch_cannot_blank_required_fields(client):
    a = client.post("/api/applications", json=APP).json()
    assert client.patch(f"/api/applications/{a['id']}", json={"stage": None}).status_code == 422
    assert client.patch(f"/api/applications/{a['id']}", json={"company": None}).status_code == 422
    assert client.patch(f"/api/applications/{a['id']}", json={"notes": None}).json()["notes"] is None


def test_malformed_id_422(client):
    assert client.patch("/api/applications/not-a-uuid", json={"stage": "offer"}).status_code == 422
    assert client.delete("/api/achievements/123").status_code == 422
    assert client.post("/api/applications", json=APP | {"role_family_id": "nope"}).status_code == 422


def test_unknown_id_404(client):
    r = client.patch(f"/api/applications/{uuid.uuid4()}", json={"stage": "offer"})
    assert r.status_code == 404 and r.json()["detail"] == GONE
    assert client.post(f"/api/families/{uuid.uuid4()}/target", json={"targeted": True}).status_code == 404


def test_user_b_cannot_see_or_change_user_a(client, user_a, user_b, as_user):
    a = client.post("/api/applications", json=APP).json()
    as_user(user_b)
    assert client.get("/api/state").json()["applications"] == []
    assert client.patch(f"/api/applications/{a['id']}", json={"stage": "offer"}).status_code == 404
    assert client.delete(f"/api/applications/{a['id']}").status_code == 404
    as_user(user_a, "Test Person")
    mine = client.get("/api/state").json()["applications"]
    assert len(mine) == 1 and mine[0]["stage"] == "applied"


def test_target_family(client, conn, user_a):
    fam = repo.sync_families(conn, user_a, [{"name": "Data Analyst", "fit": "direct", "overlap": 80}])[0]
    assert client.post(f"/api/families/{fam['id']}/target", json={"targeted": True}).json()["targeted"] is True
    s = client.get("/api/state").json()
    assert s["role_families"][0]["targeted"] is True and s["next_steps"][1]["done"] is True


def test_delete_achievement_and_job(client, conn, user_a):
    a = repo.add_achievements(conn, user_a, [{"title": "T", "uk_version": "Did X"}], "paste")[0]
    j = repo.add_job(conn, user_a, title="Role A", company="Company A", location=None, url=None, description="d" * 40,
                     summary="s", keywords=[], role_family_id=None)
    assert client.delete(f"/api/achievements/{a['id']}").status_code == 204
    assert client.delete(f"/api/jobs/{j['id']}").status_code == 204
    assert client.delete(f"/api/jobs/{j['id']}").status_code == 404
    s = client.get("/api/state").json()
    assert s["achievements"] == [] and s["saved_jobs"] == []


def test_account_delete_calls_supabase(client, monkeypatch, user_a):
    import main
    deleted = []
    monkeypatch.setattr(main, "_delete_auth_user", deleted.append)
    assert client.delete("/api/account").status_code == 204
    assert deleted == [user_a]


def test_account_delete_failure_is_502(client, monkeypatch):
    import main

    def fail(user_id):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(main, "_delete_auth_user", fail)
    r = client.delete("/api/account")
    assert r.status_code == 502 and r.json()["detail"] == "Could not delete the account. Try again."


def test_delete_auth_user_request(monkeypatch):
    import main
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    seen = {}

    def fake_delete(url, headers, timeout):
        seen.update(url=url, headers=headers)
        return httpx.Response(200, json={}, request=httpx.Request("DELETE", url))
    monkeypatch.setattr(main.httpx, "delete", fake_delete)
    main._delete_auth_user("11111111-1111-1111-1111-111111111111")
    assert seen["url"] == "https://proj.supabase.co/auth/v1/admin/users/11111111-1111-1111-1111-111111111111"
    assert seen["headers"] == {"apikey": "sb_secret_test", "Authorization": "Bearer sb_secret_test"}
    monkeypatch.setattr(main.httpx, "delete", lambda url, headers, timeout: httpx.Response(403, request=httpx.Request("DELETE", url)))
    with pytest.raises(httpx.HTTPStatusError):
        main._delete_auth_user("11111111-1111-1111-1111-111111111111")
