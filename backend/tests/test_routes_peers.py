"""Peers through the API: switching on with consent, proposals, the group, check-ins, nudges,
contact links, blocks and reports, the field suggestion, and Peers in the state read.

The model is replaced; the names cannot be real. Real accounts may be waiting in the real
database, so the first of a pair is put on the list directly (no matching runs for them) and the
second joins through the API sharing a city no real user has."""
import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient

import ai
import main
import peerdb

pytestmark = pytest.mark.db

GONE = "That item no longer exists"
LIMIT = "You've reached today's limit. It resets at midnight."
AI_FAILED = "The AI did not respond properly. Try again."
PROFILE_FIRST = "Add your university and course in Profile first: your buddies see them."
BARRED = "You can't join buddy groups."
ALREADY_ON = "Buddy groups are already on."
JOIN = {"over_18": True, "conduct": True, "field": "data"}
LIMITED = {"member", "first_name", "university", "course", "target_roles"}
FULL = LIMITED | {"progress", "streak", "contact_link", "checkin", "inactive"}


def city() -> str:
    return f"Zzqxtown-{uuid.uuid4().hex[:10]}"


def new_user(conn) -> str:
    user_id = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, email) values (%s, %s)", (user_id, f"test-{user_id}@example.test"))
    return user_id


def account(conn, user, *, name="Zzqxasha Patel", place=None) -> str:
    """Complete details, a targeted role family, an application with a CV at a named employer, an achievement."""
    conn.execute("insert into profiles (user_id, full_name, university, course, graduation_date, visa_type, visa_end_date, locations) "
                 "values (%s, %s, 'Zzqx University', 'MSc Zzqx Data Science', '2026-09-01', 'student', '2027-01-31', %s) "
                 "on conflict (user_id) do update set full_name = excluded.full_name, university = excluded.university, course = excluded.course, "
                 "graduation_date = excluded.graduation_date, visa_type = excluded.visa_type, visa_end_date = excluded.visa_end_date, "
                 "locations = excluded.locations", (user, name, [place or city()]))
    conn.execute("insert into role_families (user_id, name, fit, overlap, targeted) values (%s, 'Zzqx Data Analyst', 'direct', 80, true)", (user,))
    cv = conn.execute("insert into cv_versions (user_id, name, content) values (%s, 'Zzqx CV', '{}') returning id", (user,)).fetchone()["id"]
    conn.execute("insert into applications (user_id, company, role, source, cv_version_id) values (%s, 'Zzqx Holdings Ltd', 'Zzqx Analyst', 'Other', %s)",
                 (user, cv))
    conn.execute("insert into achievements (user_id, title, uk_version, source) values (%s, 'Zzqx churn model', 'Built a churn model', 'paste')", (user,))
    return user


def waiting(conn, user, field="data"):
    """On the list without matching running for them."""
    conn.execute("insert into peer_profiles (user_id, enabled, consented_at, over_18, field, waiting_since) values (%s, true, now(), true, %s, now())",
                 (user, field))


def group_of(conn, *users) -> str:
    group = str(conn.execute("insert into peer_groups (status, active_since) values ('active', current_date) returning id").fetchone()["id"])
    for slot, user in enumerate(users, start=1):
        conn.execute("insert into peer_profiles (user_id, enabled, consented_at, over_18, field) values (%s, true, now(), true, 'data') "
                     "on conflict (user_id) do update set enabled = true, waiting_since = null", (user,))
        conn.execute("insert into peer_group_members (group_id, user_id, slot, status, yes_from, joined_at) values (%s, %s, %s, 'accepted', %s, now())",
                     (group, user, slot, list(users)))
    return group


def peers_of(client) -> dict:
    r = client.get("/api/peers")
    assert r.status_code == 200, r.text
    return r.json()


def usage(conn, user) -> int:
    return conn.execute("select count(*) as n from usage_events where user_id = %s and kind = 'ai'", (user,)).fetchone()["n"]


def capture(monkeypatch, name: str, result) -> list:
    calls = []

    def fake(*args, **kwargs):
        calls.append(kwargs or {"args": args})
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(ai, name, fake)
    return calls


# ---------- the standing rules ----------

ID = uuid.uuid4()
ROUTES = [("get", "/api/peers"), ("post", "/api/peers/join"), ("post", "/api/peers/leave-all"),
          ("post", f"/api/peers/groups/{ID}/accept"), ("post", f"/api/peers/groups/{ID}/decline"), ("post", f"/api/peers/groups/{ID}/leave"),
          ("post", "/api/ai/peers/field")]


@pytest.mark.parametrize("method, path", ROUTES)
def test_every_peers_route_needs_a_login(method, path):
    assert getattr(TestClient(main.app), method)(path).status_code == 401


@pytest.mark.parametrize("action", ["accept", "decline", "leave"])
def test_malformed_group_id_is_422(client, action):
    assert client.post(f"/api/peers/groups/x/{action}").status_code == 422


@pytest.mark.parametrize("action", ["accept", "decline", "leave"])
def test_a_group_the_caller_is_not_in_is_404(client, conn, user_a, action):
    account(conn, user_a)
    waiting(conn, user_a)
    group = group_of(conn, account(conn, new_user(conn)), account(conn, new_user(conn)))
    r = client.post(f"/api/peers/groups/{group}/{action}")
    assert (r.status_code, r.json()["detail"]) == (404, GONE)


def test_a_coding_error_is_not_dressed_up_as_gone(client, conn, user_a, monkeypatch):
    account(conn, user_a)

    def broken(*args, **kwargs):
        raise KeyError("a bug")
    monkeypatch.setattr(peerdb, "answer", broken)
    with pytest.raises(KeyError):
        client.post(f"/api/peers/groups/{ID}/accept")


# ---------- switching on ----------

def test_off_by_default(client):
    mine = peers_of(client)
    assert (mine["status"], mine["proposal"], mine["group"], mine["nudges"]) == ("off", None, None, [])
    assert len(mine["options"]["fields"]) == 21 and len(mine["options"]["conduct"]) == 6
    assert client.get("/api/state").json()["peers"]["status"] == "off"


@pytest.mark.parametrize("body", [JOIN | {"over_18": False}, {k: v for k, v in JOIN.items() if k != "conduct"},
                                  JOIN | {"conduct": False}, JOIN | {"field": "astronaut"}, {}])
def test_joining_needs_both_ticks_and_a_listed_field(client, conn, user_a, body):
    account(conn, user_a)
    assert client.post("/api/peers/join", json=body).status_code == 422
    assert peerdb.get_profile(conn, user_a) is None


def test_joining_needs_the_details_buddies_see(client, user_a):
    r = client.post("/api/peers/join", json=JOIN)
    assert (r.status_code, r.json()["detail"]) == (409, PROFILE_FIRST)


def test_a_barred_user_cannot_join(client, conn, user_a):
    account(conn, user_a)
    conn.execute("insert into peer_profiles (user_id, barred_at) values (%s, now())", (user_a,))
    r = client.post("/api/peers/join", json=JOIN)
    assert (r.status_code, r.json()["detail"]) == (403, BARRED)


def test_joining_twice_is_409(client, conn, user_a, monkeypatch):
    account(conn, user_a)
    monkeypatch.setattr(peerdb, "_candidates", lambda conn, user_id, me: [])
    assert client.post("/api/peers/join", json=JOIN).json()["status"] == "waiting"
    r = client.post("/api/peers/join", json=JOIN)
    assert (r.status_code, r.json()["detail"]) == (409, ALREADY_ON)


def test_two_people_accept_and_see_only_the_permitted_details(client, conn, user_a, user_b, as_user):
    place = city()
    account(conn, user_a, name="Zzqxasha Patel", place=place)
    waiting(conn, user_a)
    account(conn, user_b, name="Zzqxben Okafor", place=place)
    as_user(user_b, "Zzqxben Okafor")
    mine = client.post("/api/peers/join", json=JOIN).json()
    assert mine["status"] == "proposed"
    [asha] = mine["proposal"]["members"]
    assert set(asha) == LIMITED and asha["first_name"] == "Zzqxasha" and mine["proposal"]["said_yes"] is False
    group = mine["proposal"]["group_id"]
    assert client.post(f"/api/peers/groups/{group}/accept").json()["proposal"]["said_yes"] is True
    as_user(user_a, "Zzqxasha Patel")
    assert client.post(f"/api/peers/groups/{group}/accept").json()["status"] == "group"
    as_user(user_b, "Zzqxben Okafor")
    mine = peers_of(client)
    [asha] = mine["group"]["members"]
    assert set(asha) == FULL | {"nudged_today"}
    assert asha["progress"]["of"] == 3 and isinstance(asha["streak"], int)
    assert set(mine["group"]["me"]) == {"progress", "streak", "checkin"}
    shown = json.dumps(mine)
    for hidden in ("Patel", user_a, "student", "2027-01-31", "Zzqx Holdings", "churn", "applied", "example.test"):
        assert hidden not in shown, hidden
    assert not re.search(r"\d{4}-\d{2}-\d{2}", json.dumps(mine["group"]["members"]))  # no date of anyone's activity


def test_switching_off_removes_the_user_in_the_same_request(client, conn, user_a, user_b, as_user):
    account(conn, user_a, name="Zzqxasha Patel")
    account(conn, user_b, name="Zzqxben Okafor")
    group_of(conn, user_a, user_b)
    assert client.post("/api/peers/leave-all").json()["status"] == "off"
    as_user(user_b)
    mine = peers_of(client)
    assert mine["group"] is None and "Zzqxasha" not in json.dumps(mine)


def test_account_deletion_switches_peers_off_first(client, conn, user_a, user_b, as_user, monkeypatch):
    removed = []
    monkeypatch.setattr(main, "_delete_auth_user", removed.append)
    account(conn, user_a)
    account(conn, user_b)
    group_of(conn, user_a, user_b)
    assert client.delete("/api/account").status_code == 204
    assert removed == [user_a] and peerdb.get_profile(conn, user_a)["enabled"] is False
    as_user(user_b)
    assert peers_of(client)["group"] is None


# ---------- the field suggestion ----------

def test_field_suggestion(client, conn, user_a, monkeypatch):
    account(conn, user_a)
    calls = capture(monkeypatch, "suggest_field", "data")
    r = client.post("/api/ai/peers/field")
    assert (r.status_code, r.json()) == (200, {"field": "data"})
    assert calls == [{"role_names": ["Zzqx Data Analyst"]}] and usage(conn, user_a) == 1


def test_no_target_roles_no_suggestion_and_no_ai_action(client, conn, user_a, monkeypatch):
    account(conn, user_a)
    conn.execute("update role_families set targeted = false where user_id = %s", (user_a,))
    calls = capture(monkeypatch, "suggest_field", "data")
    assert client.post("/api/ai/peers/field").json() == {"field": None}
    assert calls == [] and usage(conn, user_a) == 0


def test_field_suggestion_at_the_daily_limit(client, conn, user_a, monkeypatch):
    account(conn, user_a)
    capture(monkeypatch, "suggest_field", "data")
    monkeypatch.setenv("DAILY_AI_LIMIT", "1")
    assert client.post("/api/ai/peers/field").status_code == 200
    r = client.post("/api/ai/peers/field")
    assert (r.status_code, r.json()["detail"]) == (429, LIMIT)


def test_field_suggestion_when_the_model_fails(client, conn, user_a, monkeypatch):
    account(conn, user_a)
    capture(monkeypatch, "suggest_field", ai.AIError("peers_field"))
    r = client.post("/api/ai/peers/field")
    assert (r.status_code, r.json()["detail"]) == (502, AI_FAILED)
    assert peerdb.get_profile(conn, user_a) is None


# ---------- check-ins, nudges, contact links ----------

BAD_CONTACT_LINK = "Use your LinkedIn profile address"
PEERS_OFF = "Switch buddy groups on first."


def member_of(conn, group, user) -> str:
    return str(conn.execute("select id from peer_group_members where group_id = %s and user_id = %s", (group, user)).fetchone()["id"])


@pytest.mark.parametrize("method, path", [("put", f"/api/peers/groups/{ID}/checkin"), ("post", f"/api/peers/groups/{ID}/nudge"),
                                          ("put", "/api/peers/contact-link")])
def test_the_group_routes_need_a_login(method, path):
    assert getattr(TestClient(main.app), method)(path).status_code == 401


@pytest.mark.parametrize("method, path, body", [("put", "/api/peers/groups/x/checkin", {"text": "Line"}),
                                                ("post", "/api/peers/groups/x/nudge", {"to": str(ID)}),
                                                ("post", f"/api/peers/groups/{ID}/nudge", {"to": "x"})])
def test_malformed_ids_in_group_routes_are_422(client, method, path, body):
    assert getattr(client, method)(path, json=body).status_code == 422


@pytest.mark.parametrize("text", ["x" * 141, "", "   "])
def test_a_checkin_must_be_1_to_140_characters(client, conn, user_a, user_b, text):
    group = group_of(conn, account(conn, user_a), account(conn, user_b))
    assert client.put(f"/api/peers/groups/{group}/checkin", json={"text": text}).status_code == 422


def test_a_checkin_is_seen_by_the_group_and_nobody_else(client, conn, user_a, user_b, as_user):
    group = group_of(conn, account(conn, user_a), account(conn, user_b))
    stranger = account(conn, new_user(conn))
    group_of(conn, stranger, account(conn, new_user(conn)))
    mine = client.put(f"/api/peers/groups/{group}/checkin", json={"text": "Zzqx two applications"}).json()
    assert mine["group"]["me"]["checkin"]["text"] == "Zzqx two applications"
    as_user(user_b)
    assert peers_of(client)["group"]["members"][0]["checkin"]["text"] == "Zzqx two applications"
    as_user(stranger)
    assert "Zzqx two applications" not in json.dumps(peers_of(client))
    assert client.put(f"/api/peers/groups/{group}/checkin", json={"text": "Mine"}).status_code == 404


def test_one_nudge_a_day_through_the_api(client, conn, user_a, user_b, as_user):
    account(conn, user_a)
    account(conn, user_b, name="Zzqxben Okafor")
    group = group_of(conn, user_a, user_b)
    to_b = {"to": member_of(conn, group, user_b)}
    first = client.post(f"/api/peers/groups/{group}/nudge", json=to_b)
    assert first.status_code == 200 and first.json()["group"]["members"][0]["nudged_today"] is True
    again = client.post(f"/api/peers/groups/{group}/nudge", json=to_b)
    assert (again.status_code, again.json()["detail"]) == (409, "You have already nudged Zzqxben today.")
    as_user(user_b, "Zzqxben Okafor")
    [received] = peers_of(client)["nudges"]
    assert (received["first_name"], received["text"]) == ("Zzqxasha", "Zzqxasha nudged you: one step today keeps your week on track.")


def test_a_nudge_to_someone_outside_the_group_is_404(client, conn, user_a, user_b):
    group = group_of(conn, account(conn, user_a), account(conn, user_b))
    other = group_of(conn, account(conn, new_user(conn)), account(conn, new_user(conn)))
    outsider = conn.execute("select id from peer_group_members where group_id = %s limit 1", (other,)).fetchone()["id"]
    for to in (outsider, member_of(conn, group, user_a), uuid.uuid4()):
        r = client.post(f"/api/peers/groups/{group}/nudge", json={"to": str(to)})
        assert (r.status_code, r.json()["detail"]) == (404, GONE)


def test_a_contact_link(client, conn, user_a, user_b, as_user):
    group_of(conn, account(conn, user_a), account(conn, user_b))
    bad = client.put("/api/peers/contact-link", json={"link": "https://evil.test/www.linkedin.com/in/x"})
    assert bad.status_code == 422 and BAD_CONTACT_LINK in bad.text and peerdb.get_profile(conn, user_a)["contact_link"] is None
    mine = client.put("/api/peers/contact-link", json={"link": "linkedin.com/in/zzqx-asha"}).json()
    assert mine["contact_link"] == "https://www.linkedin.com/in/zzqx-asha"
    as_user(user_b)
    assert peers_of(client)["group"]["members"][0]["contact_link"] == "https://www.linkedin.com/in/zzqx-asha"
    as_user(user_a)
    assert client.put("/api/peers/contact-link", json={"link": ""}).json()["contact_link"] is None


def test_a_contact_link_needs_peers_on(client, conn, user_a):
    account(conn, user_a)
    r = client.put("/api/peers/contact-link", json={"link": "https://wa.me/447700900123"})
    assert (r.status_code, r.json()["detail"]) == (409, PEERS_OFF)


def test_after_leaving_the_link_and_the_person_are_gone(client, conn, user_a, user_b, as_user):
    account(conn, user_a, name="Zzqxasha Patel")
    group = group_of(conn, user_a, account(conn, user_b, name="Zzqxben Okafor"))  # b's own name is in b's state ("appears_as")
    client.put("/api/peers/contact-link", json={"link": "https://wa.me/447700900123"})
    client.post(f"/api/peers/groups/{group}/leave")
    as_user(user_b, "Zzqxben Okafor")
    shown = json.dumps(peers_of(client))
    assert "447700900123" not in shown and "Zzqxasha" not in shown


# ---------- block and report ----------

@pytest.mark.parametrize("path", ["/api/peers/block", "/api/peers/report"])
def test_block_and_report_need_a_login(path):
    assert TestClient(main.app).post(path).status_code == 401


@pytest.mark.parametrize("path, body", [("/api/peers/block", {"member": "x"}),
                                        ("/api/peers/report", {"member": "x", "reason": "unkind"}),
                                        ("/api/peers/report", {"member": str(ID), "reason": "unkind", "checkin_id": "x"})])
def test_malformed_ids_in_safety_routes_are_422(client, path, body):
    assert client.post(path, json=body).status_code == 422


def test_block_and_leave_through_the_api(client, conn, user_a, user_b, as_user, monkeypatch):
    monkeypatch.setattr(peerdb, "propose", lambda conn, user_id: None)
    account(conn, user_a)
    account(conn, user_b, name="Zzqxben Okafor")
    c = account(conn, new_user(conn), name="Zzqxcat Jones")
    group = group_of(conn, user_a, user_b, c)
    mine = client.post("/api/peers/block", json={"member": member_of(conn, group, c)}).json()
    assert mine["status"] == "waiting" and "Zzqxcat" not in json.dumps(mine)
    as_user(user_b)
    assert [m["first_name"] for m in peers_of(client)["group"]["members"]] == ["Zzqxcat"]
    as_user(user_a)
    r = client.post("/api/peers/block", json={"member": str(uuid.uuid4())})
    assert (r.status_code, r.json()["detail"]) == (404, GONE)


def test_a_report_through_the_api(client, conn, user_a, user_b, as_user):
    account(conn, user_a)
    account(conn, user_b)
    group = group_of(conn, user_a, user_b)
    as_user(user_b)
    client.put(f"/api/peers/groups/{group}/checkin", json={"text": "Zzqx line to report"})
    as_user(user_a)
    line = peers_of(client)["group"]["members"][0]["checkin"]["id"]
    body = {"member": member_of(conn, group, user_b), "reason": "personal", "details": "Asked for my BRP", "checkin_id": line}
    for wrong in ({"reason": "rude"}, {"details": "x" * 501}):
        assert client.post("/api/peers/report", json=body | wrong).status_code == 422
    mine = client.post("/api/peers/report", json=body).json()
    assert mine["group"]["members"][0]["checkin"] is None
    stored = conn.execute("select reason, details, checkin_text from peer_reports where reporter = %s", (user_a,)).fetchone()
    assert stored == {"reason": "personal", "details": "Asked for my BRP", "checkin_text": "Zzqx line to report"}
    r = client.post("/api/peers/report", json=body | {"member": str(uuid.uuid4())})
    assert (r.status_code, r.json()["detail"]) == (404, GONE)
