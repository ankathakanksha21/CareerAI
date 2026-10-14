"""Company research and prep packs through the API, with every outside service replaced."""
import uuid
from datetime import date

import pytest

import ai

REAL_PREP_PACK = ai.prep_pack  # kept before any test replaces it
import companies_house
import db
import fetcher
import repo
import websearch

pytestmark = pytest.mark.db

GONE = "That item no longer exists"
LIMIT = "You've reached today's limit. It resets at midnight."
AI_FAILED = "The AI did not respond properly. Try again."
OFF = "Interview prep is not set up on the server."
KEYS = {"COMPANIES_HOUSE_API_KEY": "ch-key-SECRET-1111", "SEARCH_PROVIDER": "tavily", "SEARCH_API_KEY": "tvly-SECRET-2222"}
NAME = "Zzqx Holdings Ltd"
NUMBER = "ZZ000001"
SITE = "zzqx-never-real.test"
REGISTRY = {"number": NUMBER, "name": "ZZQX HOLDINGS LIMITED", "status": "Active", "incorporated_on": date(2004, 3, 12), "town": "Town A",
            "type": "ltd", "sic": [], "url": f"https://find-and-update.company-information.service.gov.uk/company/{NUMBER}"}
PAGES = [{"url": f"https://{SITE}/", "title": "Zzqx", "text": "Zzqx builds payment software for councils."}]
NEWS = [{"title": "Zzqx opens office", "url": "https://news.test/a", "snippet": "Zzqx opened a Leeds office.", "published_on": date(2026, 9, 1)}]
STATEMENT = {"section": "what_they_do", "text": "Zzqx builds payment software for councils.", "source": 1, "quote": ""}
DESCRIPTION = "We need SQL and clear reporting. " * 3
ITEM = {"title": "Delays report", "raw": "r", "uk_version": "Built a weekly delays report for 15 managers"}


@pytest.fixture
def outside(monkeypatch, stub):
    """Companies House, the website, the search service and both AI tasks replaced, with the
    research settings set. Returns a dict counting the calls to each, and the brief and pack
    calls the stubs saw."""
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    count = {"search": 0, "registry": 0, "website": 0, "news": 0, "competitors": 0}

    def counted(name, value):
        def fake(*args):
            count[name] += 1
            if isinstance(value, Exception):
                raise value
            return value
        return fake

    def install(matches=None, registry=REGISTRY, site=(PAGES, []), news=NEWS, rivals=(), brief=(STATEMENT,), pack=None):
        monkeypatch.setattr(companies_house, "search", counted("search", matches if matches is not None else
                                                                [{"number": NUMBER, "name": "ZZQX HOLDINGS LIMITED", "status": "Active",
                                                                  "town": "Town A", "incorporated_on": date(2004, 3, 12)}]))
        monkeypatch.setattr(companies_house, "profile", counted("registry", registry))
        monkeypatch.setattr(fetcher, "site", counted("website", site))
        monkeypatch.setattr(websearch, "news", counted("news", news))
        monkeypatch.setattr(websearch, "competitors", counted("competitors", list(rivals)))
        count["briefs"] = stub("company_brief", brief if isinstance(brief, Exception) else list(brief))
        count["packs"] = stub("prep_pack", pack or written())
        return count
    return install


def written(**kw):
    return {"talking_points": [{"text": "You build payment software, and I built reports.", "fact_id": "f2", "achievement_id": None}],
            "pitch": "My pitch.", "likely_questions": [{"question": f"Q{i}?", "competency": "teamwork", "story_id": None, "why": ""} for i in range(8)],
            "questions_to_ask": [{"question": f"Ask {i}?", "fact_id": None} for i in range(5)]} | kw


def research(client, **kw):
    return client.post("/api/companies/research", json={"name": NAME, "company_number": NUMBER, "website": SITE} | kw)


def profile_ready(conn, user, **kw):
    repo.get_or_create_profile(conn, user, "Test Person")
    conn.execute("update profiles set visa_type = 'graduate', visa_end_date = '2027-01-30', course = 'MSc Course A' where user_id = %s", (user,))
    return repo.add_achievements(conn, user, [ITEM], "paste")[0]


def job(conn, user, **kw):
    fields = dict(title="Zzqx Analyst", company="Zzqx", location=None, url=None, description=DESCRIPTION, summary="s",
                  keywords=["SQL"], role_family_id=None) | kw
    return repo.add_job(conn, user, **fields)


def application(conn, user, **kw):
    return repo.add_application(conn, user, {"company": "Zzqx", "role": "Zzqx Analyst", "source": "Company site"} | kw)


def build(client, company_id, **target):
    return client.post("/api/ai/prep", json={"company_id": company_id} | target)


def usage(conn, user, kind) -> int:
    return conn.execute("select count(*) as n from usage_events where user_id = %s and kind = %s", (user, kind)).fetchone()["n"]


# ---------- the standing rules ----------

@pytest.mark.parametrize("method, path", [("post", "/api/companies/search"), ("post", "/api/companies/research"), ("post", "/api/ai/prep"),
                                          ("get", f"/api/prep/{uuid.uuid4()}"), ("patch", f"/api/prep/{uuid.uuid4()}"),
                                          ("delete", f"/api/prep/{uuid.uuid4()}"), ("post", f"/api/prep/{uuid.uuid4()}/refresh")])
def test_every_route_needs_a_login(method, path):
    from fastapi.testclient import TestClient

    import main
    assert getattr(TestClient(main.app), method)(path).status_code == 401


@pytest.mark.parametrize("method, path", [("get", "/api/prep/not-a-uuid"), ("patch", "/api/prep/not-a-uuid"),
                                          ("delete", "/api/prep/not-a-uuid"), ("post", "/api/prep/not-a-uuid/refresh")])
def test_malformed_ids_are_422(client, outside, method, path):
    outside()
    kwargs = {"json": {}} if method in ("patch", "post") else {}
    assert getattr(client, method)(path, **kwargs).status_code == 422


@pytest.mark.parametrize("method, path, body", [("post", "/api/companies/search", {"name": NAME}),
                                                ("post", "/api/companies/research", {"name": NAME}),
                                                ("post", "/api/ai/prep", {"job_id": str(uuid.uuid4()), "company_id": str(uuid.uuid4())}),
                                                ("post", f"/api/prep/{uuid.uuid4()}/refresh", None)])
def test_routes_that_reach_outside_are_hidden_without_settings(client, no_env_file, monkeypatch, method, path, body):
    for name in KEYS:
        monkeypatch.delenv(name, raising=False)
    r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert r.status_code == 503 and r.json()["detail"] == OFF


# ---------- confirming the company ----------

def test_search_returns_matches_and_the_name_travels_in_the_body(client, outside):
    outside()
    r = client.post("/api/companies/search", json={"name": NAME})
    assert r.status_code == 200 and r.json()["matches"][0]["number"] == NUMBER
    assert client.get("/api/companies/search", params={"name": NAME}).status_code == 405


def test_companies_house_down_is_502_with_message(client, outside, monkeypatch):
    outside()
    monkeypatch.setattr(companies_house, "search", lambda name: (_ for _ in ()).throw(companies_house.CompaniesHouseError(companies_house.UNREACHABLE)))
    r = client.post("/api/companies/search", json={"name": NAME})
    assert r.status_code == 502 and r.json()["detail"] == companies_house.UNREACHABLE


def test_no_match_is_an_empty_list(client, outside):
    outside(matches=[])
    assert client.post("/api/companies/search", json={"name": NAME}).json() == {"matches": []}


# ---------- research ----------

def test_research_returns_the_brief(client, outside, conn, user_a):
    count = outside()
    r = research(client)
    assert r.status_code == 200
    body = r.json()
    assert body["cached"] is False and body["name"] == NAME and body["missing"] == [] and body["notice"] is None
    assert [f["kind"] for f in body["facts"]] == ["website", "registry", "registry", "registry"]
    assert (count["registry"], count["website"], count["news"], count["competitors"], len(count["briefs"])) == (1, 1, 1, 1, 1)
    assert usage(conn, user_a, "research") == 1 and usage(conn, user_a, "ai") == 0


def test_research_counts_once_and_is_shared(client, outside, conn, user_a, user_b, as_user):
    count = outside()
    first = research(client).json()
    as_user(user_b)
    second = research(client, website=f"https://www.{SITE}/about").json()  # the same site, written differently
    assert second["cached"] is True and second["company_id"] == first["company_id"] and second["facts"] == first["facts"]
    assert (count["registry"], count["website"], count["news"], count["competitors"], len(count["briefs"])) == (1, 1, 1, 1, 1)
    assert usage(conn, user_a, "research") == 1 and usage(conn, user_b, "research") == 0


def test_a_different_name_with_the_same_number_never_changes_anothers_research(client, outside, user_b, as_user):
    count = outside()
    planted = research(client, name="Qqzx Planted Name", website="").json()
    as_user(user_b)
    real = research(client, website="").json()
    assert real["company_id"] != planted["company_id"] and real["cached"] is False and real["name"] == NAME
    assert count["news"] == 2


def test_different_website_is_a_different_record(client, outside):
    count = outside()
    first = research(client).json()
    second = research(client, website="other-never-real.test").json()
    assert second["company_id"] != first["company_id"] and count["website"] == 2


def test_research_older_than_14_days_is_done_again(client, outside, conn):
    count = outside()
    first = research(client).json()
    conn.execute("update companies set researched_at = now() - interval '15 days' where id = %s", (first["company_id"],))
    again = research(client).json()
    assert again["cached"] is False and again["company_id"] == first["company_id"] and count["news"] == 2


def test_every_research_attempt_counts_and_a_failure_keeps_nothing(client, outside, conn, user_a):
    outside(brief=ai.AIError("brief"))
    r = research(client)
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED
    assert conn.execute("select count(*) as n from companies where company_number = %s", (NUMBER,)).fetchone()["n"] == 0
    outside()
    assert research(client).status_code == 200
    assert usage(conn, user_a, "research") == 2  # every search costs money, so a retry is a use too


def test_parallel_or_repeated_research_cannot_run_past_the_limit(client, outside, monkeypatch):
    count = outside(brief=ai.AIError("brief"))
    monkeypatch.setenv("DAILY_RESEARCH_LIMIT", "3")
    codes = [research(client).status_code for _ in range(5)]
    assert codes == [502, 502, 502, 429, 429] and count["news"] == 3


def test_research_limit_reached_is_429(client, outside, monkeypatch):
    count = outside()
    monkeypatch.setenv("DAILY_RESEARCH_LIMIT", "1")
    research(client)
    r = research(client, company_number="ZZ000002")
    assert r.status_code == 429 and r.json()["detail"] == LIMIT and count["news"] == 1


def test_a_cached_company_is_free_at_the_limit(client, outside, monkeypatch):
    outside()
    monkeypatch.setenv("DAILY_RESEARCH_LIMIT", "1")
    research(client)
    assert research(client).json()["cached"] is True


def test_search_failure_still_gives_a_brief_with_missing(client, outside):
    outside(news=websearch.SearchError("down"))
    body = research(client).json()
    assert body["missing"] == ["the news search"] and body["facts"]


def test_no_sources_gives_nothing_found_without_model(client, outside):
    count = outside(site=([], ["robots"]), news=[], rivals=[])
    body = research(client, not_uk=True).json()
    assert body["facts"] == [] and body["notice"] == f"We could not find anything about {NAME} in the sources we checked."
    assert body["missing"] == ["their website, which asks automated readers not to read it"] and count["briefs"] == []


def test_not_uk_company_flow(client, outside):
    count = outside()
    body = research(client, not_uk=True).json()
    assert count["registry"] == 0 and all(f["kind"] != "registry" for f in body["facts"])


def test_dissolved_company_flow(client, outside):
    outside(registry=REGISTRY | {"status": "Dissolved"})
    texts = [f["text"] for f in research(client).json()["facts"]]
    assert "Companies House lists this company as dissolved." in texts


def test_companies_house_failing_during_research_is_missing_not_fatal(client, outside):
    outside(registry=companies_house.CompaniesHouseError(companies_house.UNREACHABLE))
    assert research(client).json()["missing"] == ["Companies House"]


@pytest.mark.parametrize("website", ["localhost", "10.0.0.1", "https://x@zzqx.test", "zzqx.test:8080"])
def test_bad_website_is_422(client, outside, website):
    count = outside()
    r = research(client, website=website)
    assert r.status_code == 422 and r.json()["detail"] == "Enter the company's website, for example acme.co.uk."
    assert count["news"] == 0


@pytest.mark.parametrize("number", ["../etc", "123", "ZZ0000011"])
def test_bad_company_number_is_422(client, outside, number):
    outside()
    assert research(client, company_number=number).status_code == 422


def test_no_website_is_fine(client, outside):
    count = outside()
    assert research(client, website="").status_code == 200 and count["website"] == 0


# ---------- building a pack ----------

def test_pack_for_job_then_prepare_again_rebuilds_same_pack(client, outside, conn, user_a):
    profile_ready(conn, user_a)
    count = outside()
    company = research(client).json()
    j = job(conn, user_a)
    first = build(client, company["company_id"], job_id=j["id"])
    assert first.status_code == 200
    pack = first.json()
    assert (pack["saved_job_id"], pack["role"], pack["company"]) == (j["id"], "Zzqx Analyst", "Zzqx")
    c = pack["content"]
    assert c["right_to_work"] == "I have the right to work in the UK on a Graduate visa until 30 January 2027."
    assert c["brief"]["facts"] == company["facts"] and c["interview_type"] == "video" and c["ticked"] == []
    client.patch(f"/api/prep/{pack['id']}", json={"pitch": "My own pitch."})
    again = build(client, company["company_id"], job_id=j["id"]).json()
    assert again["id"] == pack["id"] and again["content"]["pitch"] == "My own pitch."
    assert len(state(client)["prep_packs"]) == 1


def test_pack_sends_the_job_brief_and_the_users_own_records(client, outside, conn, user_a, monkeypatch):
    profile_ready(conn, user_a)
    outside()
    seen = []
    monkeypatch.setattr(ai, "prep_pack", lambda **kw: seen.append(kw) or written())
    company = research(client).json()
    j = job(conn, user_a)
    build(client, company["company_id"], job_id=j["id"])
    kw = seen[0]
    assert kw["job"] == {"title": "Zzqx Analyst", "company": "Zzqx", "description": DESCRIPTION}
    assert kw["brief"] == company["facts"] and [a["title"] for a in kw["achievements"]] == ["Delays report"]


def test_pack_for_application_uses_its_saved_job(client, outside, conn, user_a, monkeypatch):
    profile_ready(conn, user_a)
    outside()
    seen = []
    monkeypatch.setattr(ai, "prep_pack", lambda **kw: seen.append(kw) or written())
    company = research(client).json()
    j = job(conn, user_a)
    app = application(conn, user_a, saved_job_id=j["id"], stage="screening")
    pack = build(client, company["company_id"], application_id=app["id"]).json()
    assert pack["saved_job_id"] == j["id"] and pack["application_id"] == app["id"]
    assert seen[0]["job"]["description"] == DESCRIPTION and pack["content"]["interview_type"] == "phone"
    assert build(client, company["company_id"], job_id=j["id"]).json()["id"] == pack["id"]  # the job's pack is the same one


def test_pack_for_application_without_job_has_no_advert(client, outside, conn, user_a, monkeypatch):
    profile_ready(conn, user_a)
    outside()
    seen = []
    monkeypatch.setattr(ai, "prep_pack", lambda **kw: seen.append(kw) or written())
    company = research(client).json()
    app = application(conn, user_a)
    pack = build(client, company["company_id"], application_id=app["id"]).json()
    assert pack["saved_job_id"] is None and pack["application_id"] == app["id"]
    assert seen[0]["job"] == {"title": "Zzqx Analyst", "company": "Zzqx", "description": ""}
    assert build(client, company["company_id"], application_id=app["id"]).json()["id"] == pack["id"]


def test_pack_needs_exactly_one_target(client, outside, conn, user_a):
    profile_ready(conn, user_a)
    outside()
    company = research(client).json()
    j, app = job(conn, user_a), application(conn, user_a)
    assert build(client, company["company_id"]).status_code == 422
    assert build(client, company["company_id"], job_id=j["id"], application_id=app["id"]).status_code == 422


def test_pack_for_unknown_company_job_or_application_is_404(client, outside, conn, user_a):
    profile_ready(conn, user_a)
    count = outside()
    company = research(client).json()
    j = job(conn, user_a)
    assert build(client, str(uuid.uuid4()), job_id=j["id"]).status_code == 404
    assert build(client, company["company_id"], job_id=str(uuid.uuid4())).status_code == 404
    assert build(client, company["company_id"], application_id=str(uuid.uuid4())).status_code == 404
    assert count["packs"] == []


def test_pack_refused_without_achievements(client, outside, conn, user_a):
    count = outside()
    company = research(client).json()
    r = build(client, company["company_id"], job_id=job(conn, user_a)["id"])
    assert r.status_code == 400 and r.json()["detail"] == "Build your profile first." and count["packs"] == []


def test_pack_counts_one_ai_action(client, outside, conn, user_a, monkeypatch):
    profile_ready(conn, user_a)
    outside()
    company = research(client).json()
    j = job(conn, user_a)
    build(client, company["company_id"], job_id=j["id"])
    assert usage(conn, user_a, "ai") == 1
    monkeypatch.setenv("DAILY_AI_LIMIT", "1")
    assert build(client, company["company_id"], job_id=j["id"]).status_code == 429


def test_a_failed_pack_saves_nothing(client, outside, conn, user_a):
    profile_ready(conn, user_a)
    outside(pack=ai.AIError("prep"))
    company = research(client).json()
    r = build(client, company["company_id"], job_id=job(conn, user_a)["id"])
    assert r.status_code == 502 and state(client)["prep_packs"] == []


def test_pack_survives_its_job_being_deleted(client, outside, conn, user_a):
    profile_ready(conn, user_a)
    outside()
    company = research(client).json()
    j = job(conn, user_a)
    pack = build(client, company["company_id"], job_id=j["id"]).json()
    client.delete(f"/api/jobs/{j['id']}")
    got = client.get(f"/api/prep/{pack['id']}").json()
    assert got["saved_job_id"] is None and got["role"] == "Zzqx Analyst"


def test_another_users_job_or_application_is_404(client, outside, conn, user_a, user_b, as_user):
    profile_ready(conn, user_b)
    outside()
    company = research(client).json()
    j, app = job(conn, user_a), application(conn, user_a)
    as_user(user_b)
    assert build(client, company["company_id"], job_id=j["id"]).status_code == 404
    assert build(client, company["company_id"], application_id=app["id"]).status_code == 404


# ---------- reading, editing, refreshing, deleting ----------

def built(client, outside, conn, user):
    profile_ready(conn, user)
    count = outside()
    company = research(client).json()
    return build(client, company["company_id"], job_id=job(conn, user)["id"]).json(), count


def test_patch_pack(client, outside, conn, user_a):
    pack, _ = built(client, outside, conn, user_a)
    r = client.patch(f"/api/prep/{pack['id']}", json={"pitch": "Mine.", "right_to_work": "My line.", "ticked": [0, 2], "interview_type": "in_person"})
    c = r.json()["content"]
    assert (c["pitch"], c["pitch_edited"], c["right_to_work"], c["ticked"], c["interview_type"]) == ("Mine.", True, "My line.", [0, 2], "in_person")
    assert client.get(f"/api/prep/{pack['id']}").json()["content"] == c


@pytest.mark.parametrize("body", [{"ticked": [0, 1, 2, 3]}, {"ticked": [9]}, {"interview_type": "pigeon"}, {"pitch": "x" * 2501},
                                  {"right_to_work": "x" * 301}, {"brief": {}}])
def test_patch_refuses_what_cannot_be(client, outside, conn, user_a, body):
    pack, _ = built(client, outside, conn, user_a)
    assert client.patch(f"/api/prep/{pack['id']}", json=body).status_code == 422


def test_refresh_researches_again_and_counts(client, outside, conn, user_a):
    pack, count = built(client, outside, conn, user_a)
    r = client.post(f"/api/prep/{pack['id']}/refresh")
    assert r.status_code == 200 and r.json()["cached"] is False and r.json()["company_id"] == pack["company_id"]
    assert count["news"] == 2 and count["website"] == 2 and usage(conn, user_a, "research") == 2
    client.post(f"/api/prep/{pack['id']}/refresh")
    assert usage(conn, user_a, "research") == 3  # straight away, again: still a use


def test_refresh_stops_at_the_limit(client, outside, conn, user_a, monkeypatch):
    pack, count = built(client, outside, conn, user_a)
    monkeypatch.setenv("DAILY_RESEARCH_LIMIT", "2")
    assert client.post(f"/api/prep/{pack['id']}/refresh").status_code == 200
    r = client.post(f"/api/prep/{pack['id']}/refresh")
    assert r.status_code == 429 and count["news"] == 2


def test_stored_packs_work_without_the_settings(client, outside, conn, user_a, no_env_file, monkeypatch):
    pack, _ = built(client, outside, conn, user_a)
    for name in KEYS:
        monkeypatch.delenv(name)
    assert client.get(f"/api/prep/{pack['id']}").status_code == 200
    assert client.patch(f"/api/prep/{pack['id']}", json={"ticked": [1]}).status_code == 200
    assert client.delete(f"/api/prep/{pack['id']}").status_code == 204


def test_user_b_cannot_read_change_refresh_or_delete_a_pack(client, outside, conn, user_a, user_b, as_user):
    pack, count = built(client, outside, conn, user_a)
    as_user(user_b)
    path = f"/api/prep/{pack['id']}"
    assert client.get(path).status_code == 404
    assert client.patch(path, json={"pitch": "Taken over."}).status_code == 404
    assert client.post(path + "/refresh").status_code == 404
    assert client.delete(path).status_code == 404
    assert state(client)["prep_packs"] == [] and count["news"] == 1
    as_user(user_a)
    assert client.get(path).json()["content"]["pitch"] == "My pitch."


def test_delete_pack(client, outside, conn, user_a):
    pack, _ = built(client, outside, conn, user_a)
    assert client.delete(f"/api/prep/{pack['id']}").status_code == 204
    assert client.get(f"/api/prep/{pack['id']}").status_code == 404 and state(client)["prep_packs"] == []


def test_state_lists_packs_without_content(client, outside, conn, user_a):
    pack, _ = built(client, outside, conn, user_a)
    listed = state(client)["prep_packs"]
    assert [p["id"] for p in listed] == [pack["id"]] and "content" not in listed[0]
    assert listed[0]["company"] == "Zzqx" and listed[0]["role"] == "Zzqx Analyst"


def test_state_options_and_config(client, outside):
    outside()
    s = state(client)
    assert s["options"]["competencies"][0] == ["teamwork", "Teamwork"] and len(s["options"]["competencies"]) == 8
    assert s["options"]["interview_types"] == ["phone", "video", "in_person"]
    assert s["config"]["prep"] is True


def test_pack_carries_interviewer_values(client, outside, conn, user_a):
    pack, _ = built(client, outside, conn, user_a)
    assert pack["interviewer"]["company_brief"] == "Zzqx builds payment software for councils."
    got = client.get(f"/api/prep/{pack['id']}").json()["interviewer"]
    assert got == pack["interviewer"] and got["likely_questions"].startswith("Q0? Q1?")
    assert client.patch(f"/api/prep/{pack['id']}", json={"ticked": [1]}).json()["interviewer"] == got


# ---------- keys and connections ----------

def test_no_key_in_any_response(client, outside, conn, user_a):
    pack, _ = built(client, outside, conn, user_a)
    bodies = [client.post("/api/companies/search", json={"name": NAME}).text, research(client).text,
              client.get(f"/api/prep/{pack['id']}").text, client.post(f"/api/prep/{pack['id']}/refresh").text,
              client.get("/api/state").text]
    for text in bodies:
        assert KEYS["COMPANIES_HOUSE_API_KEY"] not in text and KEYS["SEARCH_API_KEY"] not in text


def test_no_connection_held_during_research_or_pack(client, outside, conn, user_a, monkeypatch):
    profile_ready(conn, user_a)
    outside()
    inner = db.transaction
    open_now = []

    from contextlib import contextmanager

    @contextmanager
    def tracking():
        with inner() as c:
            open_now.append(1)
            try:
                yield c
            finally:
                open_now.pop()
    monkeypatch.setattr(db, "transaction", tracking)

    def closed(result):
        def fake(*args, **kwargs):
            assert open_now == [], "a database transaction was open during an outside call"
            return result
        return fake
    monkeypatch.setattr(websearch, "news", closed(NEWS))
    monkeypatch.setattr(fetcher, "site", closed((PAGES, [])))
    monkeypatch.setattr(ai, "company_brief", closed([STATEMENT]))
    monkeypatch.setattr(ai, "prep_pack", closed(written()))
    company = research(client).json()
    assert build(client, company["company_id"], job_id=job(conn, user_a)["id"]).status_code == 200


def state(client) -> dict:
    return client.get("/api/state").json()



# ---------- what the final review found ----------

def test_an_edit_made_while_the_pack_is_rewritten_is_kept(client, outside, conn, user_a, monkeypatch):
    pack, _ = built(client, outside, conn, user_a)

    def meanwhile(**kw):  # the user saves their pitch while the model is writing
        repo.merge_pack_content(conn, user_a, pack["id"], {"pitch": "Typed during the refresh.", "pitch_edited": True})
        return written(pitch="The model's new pitch.")
    monkeypatch.setattr(ai, "prep_pack", meanwhile)
    again = build(client, pack["company_id"], job_id=pack["saved_job_id"]).json()
    assert again["content"]["pitch"] == "Typed during the refresh." and again["content"]["pitch_edited"] is True


def test_a_save_made_from_an_old_copy_keeps_the_others(client, outside, conn, user_a, monkeypatch):
    pack, _ = built(client, outside, conn, user_a)
    stale = repo.get_pack(conn, user_a, pack["id"])
    client.patch(f"/api/prep/{pack['id']}", json={"pitch": "Mine."})
    with monkeypatch.context() as m:
        m.setattr(repo, "get_pack", lambda *a, **k: stale)  # a second save read the pack before the first was written
        client.patch(f"/api/prep/{pack['id']}", json={"ticked": [1]})
    got = client.get(f"/api/prep/{pack['id']}").json()["content"]
    assert (got["pitch"], got["ticked"]) == ("Mine.", [1])


def test_the_right_to_work_line_appears_once_visa_details_are_added(client, outside, conn, user_a):
    pack, _ = built(client, outside, conn, user_a)
    conn.execute("update prep_packs set content = jsonb_set(content, '{right_to_work}', '\"\"') where id = %s", (pack["id"],))
    conn.execute("update profiles set visa_type = 'student', visa_end_date = '2027-01-30' where user_id = %s", (user_a,))
    assert client.get(f"/api/prep/{pack['id']}").json()["content"]["right_to_work"] == "I am in the UK on a Student visa until 30 January 2027."


def test_research_missing_a_source_is_done_again_after_an_hour(client, outside, conn):
    count = outside(news=websearch.SearchError("down"))
    first = research(client).json()
    assert first["missing"] == ["the news search"]
    assert research(client).json()["cached"] is True  # within the hour
    conn.execute("update companies set researched_at = now() - interval '2 hours' where id = %s", (first["company_id"],))
    outside()
    again = research(client).json()
    assert again["cached"] is False and again["missing"] == [] and count["news"] >= 1


def test_pack_story_matching_only_own_stories(client, outside, conn, user_a, user_b, monkeypatch):
    a = profile_ready(conn, user_a)
    mine = repo.add_story(conn, user_a, a["id"], {"title": "My story", "situation": "s", "action": "a", "competencies": ["teamwork"]})
    theirs = repo.add_story(conn, user_b, profile_ready(conn, user_b)["id"], {"title": "Their story", "situation": "s", "action": "a"})
    outside()
    monkeypatch.setattr(ai, "prep_pack", REAL_PREP_PACK)
    pitch = ("I am finishing an MSc and I like turning data into decisions people can act on every single day. " * 7).strip()
    questions = [{"question": f"Q{i}?", "competency": "Teamwork", "story_id": sid, "why": "w"}
                 for i, sid in enumerate(["s1", "s2", theirs["id"], mine["id"], "", "s1", "s1", "s1"])]
    monkeypatch.setattr(ai, "complete_json", lambda *a, **k: {
        "talking_points": [{"text": "You build payment software and I built reports.", "fact_id": "f1", "achievement_id": "a1"}],
        "pitch": pitch, "likely_questions": questions, "questions_to_ask": [{"question": f"Ask {i}?", "fact_id": ""} for i in range(5)]})
    company = research(client).json()
    got = build(client, company["company_id"], job_id=job(conn, user_a)["id"]).json()["content"]["likely_questions"]
    assert [q["story_id"] for q in got] == [mine["id"], None, None, None, None, mine["id"], mine["id"], mine["id"]]


def test_an_applications_pack_is_kept_when_its_job_is_linked_later(client, outside, conn, user_a):
    profile_ready(conn, user_a)
    outside()
    company = research(client).json()
    app = application(conn, user_a)
    first = build(client, company["company_id"], application_id=app["id"]).json()
    j = job(conn, user_a)
    client.patch(f"/api/applications/{app['id']}", json={"saved_job_id": j["id"]})
    again = build(client, company["company_id"], application_id=app["id"]).json()
    assert again["id"] == first["id"] and again["saved_job_id"] == j["id"]
    assert client.delete(f"/api/jobs/{j['id']}").status_code == 204
    assert len(state(client)["prep_packs"]) == 1
