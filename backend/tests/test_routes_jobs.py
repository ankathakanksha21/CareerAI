"""The jobs routes, with Reed and the model replaced. The database is the real one, so every
name here is one that cannot occur in real data."""
import uuid
from datetime import date, timedelta

import pytest

import ai
import reed
import repo
import sponsors

pytestmark = pytest.mark.db

TODAY = date.today()
GONE = "That item no longer exists"


def advert(n, **changes):
    """A listing as reed.search_both returns it."""
    return {"source": "reed", "source_id": f"zzqx-{n}", "title": f"Zzqx Role {n}", "employer": "Zzqx Holdings Ltd", "posted_by": "employer",
            "location": "Zzqx Town", "salary_min": 28000, "salary_max": 32000, "salary_annual": True, "description": f"Short text {n}",
            "description_is_full": False, "url": f"https://www.reed.co.uk/jobs/{n}", "posted_on": TODAY} | changes


def ready(conn, user_id, locations=("Zzqx Town",), families=(("Zzqx Analyst", ["Zzqx Role"]),)):
    """A user who can search: details filled in, a targeted role family and one achievement."""
    repo.update_profile(conn, user_id, full_name="Test Person", university="University A", course="MSc Course A",
                        graduation_date=date(2026, 9, 1), visa_type="graduate", visa_end_date=date(2028, 1, 31), locations=list(locations))
    ids = []
    for name, titles in families:
        made = repo.sync_families(conn, user_id, [{"name": n, "fit": "direct", "overlap": 80, "uk_titles": t} for n, t in families])
        ids.append(repo.set_family_targeted(conn, user_id, next(f["id"] for f in made if f["name"] == name), True)["id"])
    repo.add_achievements(conn, user_id, [{"title": "Thing one", "uk_version": "Built X for 40 users", "skills": ["SQL"]}], "paste")
    return ids


def register(conn, *names):
    for r in sponsors.with_keys([{"name": n, "town": "", "county": "", "route": "Skilled Worker", "rating": ""} for n in names]):
        conn.execute("insert into sponsors (name, name_key, route) values (%s, %s, %s)", (r["name"], r["name_key"], r["route"]))
    # the tests must not rely on the real register having been loaded
    conn.execute("insert into reference_meta (key, published_on, row_count) values ('sponsors', current_date, 1) "
                 "on conflict (key) do update set published_on = excluded.published_on")


class Reed:
    def __init__(self):
        self.adverts, self.searches, self.asked, self.down, self.details_down = [], [], [], set(), False

    def search_both(self, query, location):
        self.searches.append((query, location))
        if self.down is True or query in self.down:
            raise reed.ReedError("down")
        return [dict(a) for a in self.adverts]

    def details(self, source_id):
        self.asked.append(source_id)
        if self.details_down:
            raise reed.ReedError("down")
        return {"description": f"The full advert {source_id}. SQL and Python.", "description_is_full": True,
                "salary_min": 30000, "salary_max": 35000, "salary_annual": True}


@pytest.fixture
def site(monkeypatch):
    """Reed, replaced. Set site.adverts; read site.searches."""
    fake = Reed()
    monkeypatch.setenv("REED_API_KEY", "reed-marker-key")
    monkeypatch.setattr(reed, "search_both", fake.search_both)
    monkeypatch.setattr(reed, "details", fake.details)
    return fake


@pytest.fixture
def model(monkeypatch):
    """The fit-scoring model, replaced: every advert asks for SQL (shown) and Python (a gap)."""
    state = {"calls": [], "fail": False}

    def score_jobs(batch, achievements):
        state["calls"].append(batch)
        if state["fail"]:
            raise ai.AIError("job fit")
        return {b["n"]: [{"need": "SQL", "shown_by": "Thing one"}, {"need": "Python", "shown_by": ""}] for b in batch}
    monkeypatch.setattr(ai, "score_jobs", score_jobs)
    return state


def jobs_list(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200, r.text
    return r.json()


def refresh(client):
    r = client.post("/api/jobs/refresh")
    assert r.status_code == 200, r.text
    return r.json()


# ---------- who may call ----------

def test_internal_refresh_needs_the_secret(client, monkeypatch):
    called = []
    monkeypatch.setattr(sponsors, "refresh", lambda: called.append(1) or {"rows": 5, "published_on": TODAY})
    monkeypatch.delenv("CRON_SECRET", raising=False)
    import config
    monkeypatch.setattr(config, "ENV_PATH", config.ENV_PATH.parent / "no-such-file")
    assert client.get("/api/internal/refresh-sponsors", headers={"Authorization": "Bearer "}).status_code == 401  # no secret set: nobody may
    monkeypatch.setenv("CRON_SECRET", "cron-marker-secret")
    assert client.get("/api/internal/refresh-sponsors").status_code == 401
    assert client.get("/api/internal/refresh-sponsors", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/internal/refresh-sponsors", headers={"Authorization": "cron-marker-secret"}).status_code == 401
    assert called == []
    r = client.get("/api/internal/refresh-sponsors", headers={"Authorization": "Bearer cron-marker-secret"})
    assert r.status_code == 200 and r.json() == {"rows": 5, "published_on": TODAY.isoformat()} and called == [1]


def test_internal_refresh_failure_is_502(client, monkeypatch):
    def broken():
        raise sponsors.RegisterError("the register file's columns have changed")
    monkeypatch.setattr(sponsors, "refresh", broken)
    monkeypatch.setenv("CRON_SECRET", "cron-marker-secret")
    r = client.get("/api/internal/refresh-sponsors", headers={"Authorization": "Bearer cron-marker-secret"})
    assert r.status_code == 502 and r.json()["detail"] == "The sponsor register could not be reloaded. The stored copy is unchanged."


# ---------- refresh: what it needs ----------

def test_refresh_needs_target_roles(client, conn, user_a, site, model):
    r = client.post("/api/jobs/refresh")
    assert r.status_code == 400 and r.json()["detail"] == "Pick your target roles first."
    assert site.searches == []


def test_refresh_needs_achievements(client, conn, user_a, site, model):
    ready(conn, user_a)
    conn.execute("delete from achievements where user_id = %s", (user_a,))
    r = client.post("/api/jobs/refresh")
    assert r.status_code == 400 and r.json()["detail"] == "Build your profile first."
    assert site.searches == []


def test_refresh_without_a_reed_key_is_503(client, conn, user_a, site, model, monkeypatch, no_env_file):
    ready(conn, user_a)
    monkeypatch.delenv("REED_API_KEY")
    r = client.post("/api/jobs/refresh")
    assert r.status_code == 503 and r.json()["detail"] == "Job search is not set up on the server."
    assert jobs_list(client)["configured"] is False


# ---------- refresh: the whole path ----------

def test_refresh_fetches_scores_and_lists(client, conn, user_a, site, model):
    (family_id,) = ready(conn, user_a)
    register(conn, "Zzqx Holdings Ltd")
    site.adverts = [advert(1, posted_on=TODAY - timedelta(days=1)), advert(2)]
    before = jobs_list(client)
    assert before["matches"] == [] and before["due"] is True and before["searches"] == 1
    done = refresh(client)
    assert done == {"searched": 1, "remaining": 0, "new": 2, "scored": 2, "notice": None}
    assert site.searches == [("zzqx role", "zzqx town")]
    after = jobs_list(client)
    assert after["due"] is False
    assert [m["title"] for m in after["matches"]] == ["Zzqx Role 2", "Zzqx Role 1"]  # newest first
    m = after["matches"][0]
    assert (m["fit_percent"], m["fit_label"]) == (50, "stretch")
    assert m["shown"] == [{"need": "SQL", "achievement": "Thing one"}] and m["gaps"] == ["Python"]
    assert m["role_family_id"] == family_id and m["status"] == "new" and m["senior"] is False
    assert (m["sponsor_status"], m["sponsor_name"]) == ("listed", "Zzqx Holdings Ltd")
    # the full advert was fetched before scoring, and its salary replaces the search figure
    assert m["description_is_full"] is True and m["fit_from_summary"] is False and (m["salary_min"], m["salary_max"]) == (30000, 35000)
    assert sorted(site.asked) == ["zzqx-1", "zzqx-2"]
    assert after["register"] is not None and after["visa"]["checked_on"] and after["include_senior"] is False


def test_the_model_sees_the_full_advert_and_only_the_achievements(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1)]
    refresh(client)
    (batch,) = model["calls"]
    assert batch == [{"n": 1, "title": "Zzqx Role 1", "employer": "Zzqx Holdings Ltd", "description": "The full advert zzqx-1. SQL and Python."}]


def test_a_short_advert_is_scored_and_marked_when_the_full_one_cannot_be_fetched(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts, site.details_down = [advert(1)], True
    refresh(client)
    (m,) = jobs_list(client)["matches"]
    assert m["fit_percent"] == 50 and m["fit_from_summary"] is True and m["description_is_full"] is False
    assert model["calls"][0][0]["description"] == "Short text 1"


# ---------- the shared cache ----------

def test_a_second_refresh_inside_six_hours_does_not_call_reed(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1)]
    refresh(client)
    again = refresh(client)
    assert len(site.searches) == 1 and again == {"searched": 0, "remaining": 0, "new": 0, "scored": 0, "notice": None}


def test_after_six_hours_each_search_is_run_once(client, conn, user_a, site, model):
    ready(conn, user_a, locations=("Zzqx Town", "Zzqy City"))
    site.adverts = [advert(1)]
    refresh(client)
    assert len(site.searches) == 2
    conn.execute("update job_searches set fetched_at = now() - interval '7 hours' where query = 'zzqx role'")
    assert jobs_list(client)["due"] is True
    refresh(client)
    assert sorted(site.searches[2:]) == [("zzqx role", "zzqx town"), ("zzqx role", "zzqy city")]


def test_another_user_reads_the_cache_and_gets_their_own_matches(client, conn, user_a, user_b, as_user, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1)]
    refresh(client)
    (mine,) = jobs_list(client)["matches"]
    as_user(user_b)
    ready(conn, user_b)
    done = refresh(client)
    assert len(site.searches) == 1 and done["searched"] == 0 and done["new"] == 1 and done["scored"] == 1
    (theirs,) = jobs_list(client)["matches"]
    assert theirs["listing_id"] == mine["listing_id"] and theirs["id"] != mine["id"] and theirs["status"] == "new"


# ---------- when Reed fails ----------

def test_reed_down_keeps_the_stored_jobs_and_says_so(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1)]
    refresh(client)
    conn.execute("update job_searches set fetched_at = now() - interval '7 hours' where query = 'zzqx role'")
    site.down = True
    done = refresh(client)
    assert done["notice"] == "We could not reach Reed. Try again shortly." and done["searched"] == 0
    listed = jobs_list(client)
    assert [m["title"] for m in listed["matches"]] == ["Zzqx Role 1"] and listed["due"] is True


def test_some_searches_failing_returns_the_rest_with_a_notice(client, conn, user_a, site, model):
    ready(conn, user_a, families=(("Zzqx Analyst", ["Zzqx Role", "Zzqx Other"]),))
    site.adverts, site.down = [advert(1)], {"zzqx other"}
    done = refresh(client)
    assert done["searched"] == 1 and done["new"] == 1 and done["notice"] == "Some searches could not be completed. Check again shortly."
    assert len(jobs_list(client)["matches"]) == 1


# ---------- the same advert twice, and senior titles ----------

def test_a_reposted_advert_appears_once(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1, title="Zzqx Role", posted_on=TODAY - timedelta(days=3)), advert(2, title="Zzqx Role"), advert(3, title="Zzqx Role", location="Elsewhere")]
    refresh(client)
    assert sorted((m["source_id"], m["location"]) for m in jobs_list(client)["matches"]) == [("zzqx-2", "Zzqx Town"), ("zzqx-3", "Elsewhere")]


def test_a_later_repost_of_a_job_the_user_dismissed_does_not_come_back(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1, title="Zzqx Role", posted_on=TODAY - timedelta(days=3))]
    refresh(client)
    (m,) = jobs_list(client)["matches"]
    assert client.post(f"/api/jobs/{m['id']}/hide").status_code == 204
    conn.execute("update job_searches set fetched_at = now() - interval '7 hours' where query = 'zzqx role'")
    site.adverts = [advert(2, title="Zzqx Role")]
    assert refresh(client)["new"] == 0 and jobs_list(client)["matches"] == []


def test_senior_titles_are_flagged_and_not_scored_until_the_setting_is_on(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1, title="Senior Zzqx Role"), advert(2)]
    assert refresh(client)["scored"] == 1
    by_title = {m["title"]: m for m in jobs_list(client)["matches"]}
    assert by_title["Senior Zzqx Role"]["senior"] is True and by_title["Senior Zzqx Role"]["scored_at"] is None
    assert by_title["Zzqx Role 2"]["scored_at"] is not None
    assert client.put("/api/jobs/preferences", json={"include_senior": True}).json() == {"include_senior": True}
    assert refresh(client)["scored"] == 1
    listed = jobs_list(client)
    assert listed["include_senior"] is True and all(m["scored_at"] for m in listed["matches"])
    assert client.put("/api/jobs/preferences", json={"include_senior": "maybe"}).status_code == 422


# ---------- the AI allowance and AI failures ----------

def usage(client):
    return client.get("/api/state").json()["usage"]["ai"]["used"]


def test_a_refresh_that_scores_counts_one_ai_action_and_one_that_does_not_counts_none(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(n) for n in range(1, 8)]
    refresh(client)
    assert usage(client) == 1 and len(model["calls"]) == 2  # seven adverts, five per call, one action
    refresh(client)
    assert usage(client) == 1 and len(model["calls"]) == 2


def test_at_most_fifteen_adverts_are_scored_per_refresh(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(n) for n in range(1, 19)]
    assert refresh(client)["scored"] == 15
    assert sum(m["scored_at"] is None for m in jobs_list(client)["matches"]) == 3
    assert refresh(client)["scored"] == 3 and usage(client) == 2


def test_with_the_ai_allowance_used_up_jobs_are_still_listed_unscored(client, conn, user_a, site, model, monkeypatch):
    ready(conn, user_a)
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    site.adverts = [advert(1)]
    done = refresh(client)
    assert done["new"] == 1 and done["scored"] == 0
    assert done["notice"] == "You have reached today's AI limit, so new jobs were not scored. It resets at midnight."
    assert model["calls"] == [] and site.asked == []
    (m,) = jobs_list(client)["matches"]
    assert m["fit_percent"] is None and m["scored_at"] is None


def test_when_the_model_fails_the_jobs_stay_and_nothing_is_scored(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts, model["fail"] = [advert(1), advert(2)], True
    r = client.post("/api/jobs/refresh")
    assert r.status_code == 502 and r.json()["detail"] == "The AI did not respond properly. Try again."
    listed = jobs_list(client)["matches"]
    assert len(listed) == 2 and all(m["fit_percent"] is None and m["scored_at"] is None for m in listed)


def test_one_failed_model_call_keeps_the_others_results(client, conn, user_a, site, monkeypatch):
    ready(conn, user_a)
    site.adverts = [advert(n) for n in range(1, 8)]

    def score_jobs(batch, achievements):
        if len(batch) == 2:  # the second, smaller call fails
            raise ai.AIError("job fit")
        return {b["n"]: [{"need": "SQL", "shown_by": "Thing one"}] for b in batch}
    monkeypatch.setattr(ai, "score_jobs", score_jobs)
    done = refresh(client)
    assert done["scored"] == 5 and done["notice"] == "Some jobs could not be scored. Check again to score them."


# ---------- many searches ----------

def test_at_most_twenty_searches_per_refresh_and_the_rest_reported(client, conn, user_a, site, model):
    ready(conn, user_a, locations=("Zzqx A", "Zzqx B", "Zzqx C", "Zzqx D"),
          families=(("Zzqx One", ["Zzqx Ra", "Zzqx Rb", "Zzqx Rc"]), ("Zzqx Two", ["Zzqx Rd", "Zzqx Re", "Zzqx Rf"])))
    assert jobs_list(client)["searches"] == 24
    assert refresh(client)["remaining"] == 4 and len(site.searches) == 20
    assert refresh(client)["remaining"] == 0 and len(site.searches) == 24


# ---------- seen, hidden ----------

def test_reading_the_list_changes_nothing_and_seen_clears_new(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1)]
    refresh(client)
    assert jobs_list(client)["matches"][0]["status"] == "new" and jobs_list(client)["matches"][0]["status"] == "new"
    assert client.get("/api/state").json()["jobs"] == {"new": 1, "fresh": 1}
    assert client.post("/api/jobs/seen").status_code == 204
    assert jobs_list(client)["matches"][0]["status"] == "seen"
    assert client.get("/api/state").json()["jobs"] == {"new": 0, "fresh": 0}


def test_a_hidden_job_stays_hidden_after_the_next_refresh(client, conn, user_a, site, model):
    ready(conn, user_a)
    site.adverts = [advert(1), advert(2)]
    refresh(client)
    hidden = next(m for m in jobs_list(client)["matches"] if m["source_id"] == "zzqx-1")
    assert client.post(f"/api/jobs/{hidden['id']}/hide").status_code == 204
    conn.execute("update job_searches set fetched_at = now() - interval '7 hours' where query = 'zzqx role'")
    refresh(client)
    assert [m["source_id"] for m in jobs_list(client)["matches"]] == ["zzqx-2"]


# ---------- save and track ----------

def one_match(client, conn, user_id, site, **changes):
    ready(conn, user_id)
    site.adverts = [advert(1, **changes)]
    refresh(client)
    return jobs_list(client)["matches"][0]


def test_saving_copies_the_full_advert_into_the_users_jobs(client, conn, user_a, site, model):
    m = one_match(client, conn, user_a, site)
    r = client.post(f"/api/jobs/{m['id']}/save")
    assert r.status_code == 200
    job = r.json()
    assert (job["title"], job["company"], job["source"]) == ("Zzqx Role 1", "Zzqx Holdings Ltd", "reed")
    assert job["description"] == "The full advert zzqx-1. SQL and Python." and job["posted_on"] == TODAY.isoformat()
    assert job["url"] == "https://www.reed.co.uk/jobs/1" and job["role_family_id"] == m["role_family_id"]
    assert client.post(f"/api/jobs/{m['id']}/save").json()["id"] == job["id"]
    state = client.get("/api/state").json()
    assert [j["id"] for j in state["saved_jobs"]] == [job["id"]] and state["next_steps"][2]["done"] is True
    assert jobs_list(client)["matches"][0]["status"] == "saved"


def test_saving_an_unscored_advert_fetches_the_full_text_first(client, conn, user_a, site, model, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")  # so the refresh stores only the short text
    m = one_match(client, conn, user_a, site)
    assert site.asked == []
    job = client.post(f"/api/jobs/{m['id']}/save").json()
    assert site.asked == ["zzqx-1"] and job["description"] == "The full advert zzqx-1. SQL and Python."


def test_saving_fails_cleanly_when_the_full_advert_cannot_be_fetched(client, conn, user_a, site, model, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    m = one_match(client, conn, user_a, site)
    site.details_down = True
    r = client.post(f"/api/jobs/{m['id']}/save")
    assert r.status_code == 502 and r.json()["detail"] == "We could not fetch the full advert from Reed. Try again."
    assert client.get("/api/state").json()["saved_jobs"] == [] and jobs_list(client)["matches"][0]["status"] == "new"


@pytest.mark.parametrize("on_register, posted_by, expected", [(True, "employer", True), (False, "employer", False), (True, "agency", None)])
def test_tracking_creates_an_application_with_link_posted_date_and_sponsor_status(client, conn, user_a, site, model, on_register, posted_by, expected):
    if on_register:
        register(conn, "Zzqx Holdings Ltd")
    m = one_match(client, conn, user_a, site, posted_by=posted_by, posted_on=TODAY - timedelta(days=1))
    r = client.post(f"/api/jobs/{m['id']}/track")
    assert r.status_code == 201
    a = r.json()
    assert (a["company"], a["role"], a["source"], a["stage"]) == ("Zzqx Holdings Ltd", "Zzqx Role 1", "Reed", "applied")
    assert a["job_url"] == "https://www.reed.co.uk/jobs/1" and a["posted_on"] == (TODAY - timedelta(days=1)).isoformat()
    assert a["sponsor_licence"] is expected and a["role_family_id"] == m["role_family_id"]
    state = client.get("/api/state").json()
    assert a["saved_job_id"] == state["saved_jobs"][0]["id"] and len(state["applications"]) == 1


def test_tracking_the_same_job_twice_gives_the_same_application(client, conn, user_a, site, model):
    m = one_match(client, conn, user_a, site)
    first = client.post(f"/api/jobs/{m['id']}/track")
    again = client.post(f"/api/jobs/{m['id']}/track")
    assert first.status_code == 201 and again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert len(client.get("/api/state").json()["applications"]) == 1


def test_an_application_can_carry_and_change_its_sponsor_status(client):
    a = client.post("/api/applications", json={"company": "Company A", "role": "Role A", "source": "Reed", "sponsor_licence": True}).json()
    assert a["sponsor_licence"] is True
    assert client.patch(f"/api/applications/{a['id']}", json={"sponsor_licence": None}).json()["sponsor_licence"] is None


# ---------- ids, and other people's matches ----------

@pytest.mark.parametrize("action", ["save", "hide", "track"])
def test_malformed_and_unknown_match_ids(client, action):
    assert client.post(f"/api/jobs/not-a-uuid/{action}").status_code == 422
    r = client.post(f"/api/jobs/{uuid.uuid4()}/{action}")
    assert r.status_code == 404 and r.json()["detail"] == GONE


def test_user_b_cannot_see_save_hide_or_track_user_a_match(client, conn, user_a, user_b, as_user, site, model):
    m = one_match(client, conn, user_a, site)
    client.post(f"/api/jobs/{m['id']}/save")
    as_user(user_b)
    assert jobs_list(client)["matches"] == []
    for action in ("save", "hide", "track"):
        assert client.post(f"/api/jobs/{m['id']}/{action}").status_code == 404
    assert client.post("/api/jobs/seen").status_code == 204
    state = client.get("/api/state").json()
    assert state["saved_jobs"] == [] and state["applications"] == [] and state["jobs"] == {"new": 0, "fresh": 0} and state["market"] == {}
    as_user(user_a, "Test Person")
    mine = jobs_list(client)["matches"]
    assert len(mine) == 1 and mine[0]["status"] == "saved"


# ---------- visa facts ----------

def test_visa_facts_always_have_the_source_and_the_date_checked(client):
    for offer in ({}, {"salary": 38000}, {"employer": "Zzqx Holdings"}):
        facts = client.post("/api/visa-facts", json=offer).json()
        assert facts["checked_on"] and facts["sources"] and all(s["url"].startswith("https://www.gov.uk/") for s in facts["sources"])
        assert facts["standard_salary"] > facts["lower_salary"] > 0
        assert "register" in facts and not {"eligible", "meets", "verdict"} & set(facts)


def test_visa_facts_report_the_salary_and_look_the_employer_up(client, conn):
    register(conn, "Zzqx Holdings Ltd")
    facts = client.post("/api/visa-facts", json={"salary": 38000, "employer": " Zzqx Holdings "}).json()
    assert facts["advertised"] == {"min": 38000, "max": 38000}
    assert facts["sponsor"] == {"status": "listed", "name": "Zzqx Holdings Ltd"} and facts["register"]["published_on"]
    nothing = client.post("/api/visa-facts", json={"salary": None, "employer": ""}).json()
    assert nothing["advertised"] is None and nothing["sponsor"] is None


@pytest.mark.parametrize("offer", [{"salary": -1}, {"salary": "lots"}, {"salary": 10_000_001}, {"employer": "x" * 161}])
def test_visa_facts_validation(client, offer):
    assert client.post("/api/visa-facts", json=offer).status_code == 422


def test_an_offer_is_sent_in_the_body_not_the_address(client):
    """A salary and employer in the address would end up in server logs."""
    assert client.get("/api/visa-facts", params={"salary": 38000}).status_code == 405


# ---------- state, and no secrets ----------

def test_state_has_job_counts_market_figures_and_reed_as_a_source(client, conn, user_a, site, model):
    register(conn, "Zzqx Holdings Ltd")
    (family_id,) = ready(conn, user_a)
    site.adverts = [advert(1), advert(2, employer="Zzqy Nobody"), advert(3, posted_by="agency")]
    empty = client.get("/api/state").json()
    assert empty["jobs"] == {"new": 0, "fresh": 0} and empty["market"] == {} and empty["config"]["jobs"] is True
    assert "Reed" in empty["options"]["sources"]
    refresh(client)
    state = client.get("/api/state").json()
    assert state["jobs"] == {"new": 3, "fresh": 3}
    assert state["market"] == {family_id: {"jobs": 3, "named": 2, "listed": 1, "salary_median": 32500, "salary_n": 3}}


def test_no_key_appears_in_any_jobs_response(client, conn, user_a, site, model, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "cron-marker-secret")
    m = one_match(client, conn, user_a, site)
    replies = [client.get("/api/jobs"), client.post("/api/jobs/refresh"), client.get("/api/state"), client.post("/api/visa-facts", json={}),
               client.post(f"/api/jobs/{m['id']}/save"), client.get("/api/internal/refresh-sponsors"), client.get("/api/config")]
    for r in replies:
        assert "reed-marker-key" not in r.text and "cron-marker-secret" not in r.text


# ---------- training programmes advertised as jobs ----------

def test_a_training_programme_is_listed_apart_never_scored_and_never_called_a_sponsor(client, conn, user_a, site, model):
    (family_id,) = ready(conn, user_a)
    register(conn, "Zzqx Training Ltd")  # a training company can hold a licence for its own staff
    site.adverts = [advert(1), advert(2, employer="Zzqx Training", description="Launch your new career. No experience required."),
                    advert(3, employer="Zzqx Recruit", description="Our career programme gets you job ready.")]
    assert refresh(client)["scored"] == 1
    by_id = {m["source_id"]: m for m in jobs_list(client)["matches"]}
    assert by_id["zzqx-1"]["posted_by"] == "employer" and by_id["zzqx-1"]["scored_at"] is not None
    for source_id in ("zzqx-2", "zzqx-3"):
        m = by_id[source_id]
        assert m["posted_by"] == "training" and m["scored_at"] is None and m["fit_percent"] is None
        assert (m["sponsor_status"], m["sponsor_name"]) == ("agency", None)
    assert refresh(client)["scored"] == 0 and len(model["calls"]) == 1  # they are never sent to the model later either
    state = client.get("/api/state").json()
    assert state["jobs"] == {"new": 1, "fresh": 1}
    assert state["market"][family_id]["jobs"] == 1 and state["market"][family_id]["named"] == 1
