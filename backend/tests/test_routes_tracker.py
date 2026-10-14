"""The tracker through the API: a rejection and its lesson, follow-ups, weekly goals, milestones,
and what the state read carries. The model is replaced; the names cannot be real."""
import uuid
from datetime import date, timedelta

import pytest

import ai
import repo

pytestmark = pytest.mark.db

GONE = "That item no longer exists"
LIMIT = "You've reached today's limit. It resets at midnight."
AI_FAILED = "The AI did not respond properly. Try again."
NOTHING_TO_COMPARE = ("No CV or job description was recorded for this application, so there is nothing to compare. "
                      "Attach both next time.")
ENDED = "This application has ended, so there is nothing to follow up."
CHANGED = "This application changed while the lesson was being written, so it was not saved. Ask for it again from the application."
LESSON = {"likely_reason": "The CV may not have shown enough SQL.", "one_change": "Put SQL in the first bullet.", "page": "resume"}
DRAFT = {"subject": "Zzqx Analyst application", "message": "Dear Zzqx Person,\n\nIs there any news?\n\nKind regards,\nTest Person"}
APP = {"company": "Zzqx Holdings Ltd", "role": "Zzqx Analyst", "source": "Company site"}
CV_CONTENT = {"profile": "Graduate analyst.", "work": [{"employer": "Zzqx Works", "job_title": "Analyst", "hidden": False,
                                                       "bullets": [{"text": "Built a Python dashboard for 40 staff", "hidden": False}]}],
              "skills": {"technical": ["Python"], "tools": [], "languages": []}}
DEFAULT_GOAL = {"applications": 5, "practice": 2, "outreach": 2}  # a new account: two messages a week


def capture(monkeypatch, name: str, result) -> list:
    """Replace ai.<name>, recording the keyword arguments of each call."""
    calls = []

    def fake(*args, **kwargs):
        calls.append(kwargs)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(ai, name, fake)
    return calls


def add(client, **kw) -> dict:
    r = client.post("/api/applications", json=APP | kw)
    assert r.status_code == 201, r.text
    return r.json()


def saved_job(conn, user) -> dict:
    return repo.add_job(conn, user, title="Zzqx Analyst", company="Zzqx Holdings Ltd", location=None, url=None,
                        description="We need strong SQL and clear reporting. " * 4, summary="s", keywords=[], role_family_id=None)


def sent_cv(conn, user, job=None, content=CV_CONTENT, format_version=2) -> dict:
    return repo.add_cv_version(conn, user, saved_job_id=job["id"] if job else None, role_family_id=None,
                               base_name="Zzqx Analyst, Zzqx Holdings Ltd", content=content, format_version=format_version, pages=1)


def state(client) -> dict:
    return client.get("/api/state").json()


def ai_used(conn, user) -> int:
    return conn.execute("select count(*) as n from usage_events where user_id = %s and kind = 'ai'", (user,)).fetchone()["n"]


def stages(conn, user, app_id) -> list:
    return [e["to_stage"] for e in repo.list_application_events(conn, user) if e["application_id"] == app_id]


def reject(client, app, **body):
    return client.post(f"/api/applications/{app['id']}/reject", json={"ended_at": "cv"} | body)


# ---------- rejecting ----------

def test_reject_with_nothing_to_compare_makes_no_model_call(client, monkeypatch, conn, user_a):
    calls = capture(monkeypatch, "rejection_lesson", LESSON)
    r = reject(client, add(client))
    assert r.status_code == 200, r.text
    assert (r.json()["lesson"], r.json()["notice"]) == (None, NOTHING_TO_COMPARE)
    assert (r.json()["application"]["stage"], r.json()["application"]["rejected_at_stage"]) == ("rejected", "cv")
    assert calls == [] and ai_used(conn, user_a) == 0


def test_reject_with_a_cv_and_advert_returns_and_stores_a_lesson(client, monkeypatch, conn, user_a):
    job = saved_job(conn, user_a)
    app = add(client, cv_version_id=sent_cv(conn, user_a, job)["id"], saved_job_id=job["id"])
    calls = capture(monkeypatch, "rejection_lesson", LESSON)
    r = reject(client, app, ended_at="interview", feedback="  More SQL please.  ")
    assert r.status_code == 200, r.text
    lesson = r.json()["lesson"]
    assert lesson == LESSON | {"made_on": str(repo.today(conn))} and r.json()["notice"] is None
    assert r.json()["application"]["stage"] == "rejected_after_interview" and r.json()["application"]["lesson"] == lesson
    sent = calls[0]
    assert (sent["ended_at"], sent["feedback"]) == ("interview", "More SQL please.")
    assert sent["job"]["description"].startswith("We need strong SQL") and "Built a Python dashboard for 40 staff" in sent["cv_text"]
    assert ai_used(conn, user_a) == 1


def test_lesson_reads_the_job_the_cv_was_built_for(client, monkeypatch, conn, user_a):
    app = add(client, cv_version_id=sent_cv(conn, user_a, saved_job(conn, user_a))["id"])  # no saved job on the application itself
    calls = capture(monkeypatch, "rejection_lesson", LESSON)
    assert reject(client, app).status_code == 200
    assert calls[0]["job"]["title"] == "Zzqx Analyst"


def test_lesson_with_an_advert_but_no_cv(client, monkeypatch, conn, user_a):
    app = add(client, saved_job_id=saved_job(conn, user_a)["id"])
    calls = capture(monkeypatch, "rejection_lesson", LESSON)
    assert reject(client, app).json()["lesson"]["page"] == "resume"
    assert calls[0]["cv_text"] == ""


def test_lesson_reads_an_older_cv(client, monkeypatch, conn, user_a):
    old = sent_cv(conn, user_a, content={"profile": "Old paragraph.", "bullets": [{"text": "Built X", "achievement_id": ""}]}, format_version=1)
    app = add(client, cv_version_id=old["id"])
    calls = capture(monkeypatch, "rejection_lesson", LESSON)
    assert reject(client, app).status_code == 200
    assert calls[0]["cv_text"] == "Old paragraph.\nBuilt X" and calls[0]["job"] is None


def test_failed_lesson_keeps_the_rejection_and_a_retry_adds_no_event(client, monkeypatch, conn, user_a):
    app = add(client, cv_version_id=sent_cv(conn, user_a)["id"])
    capture(monkeypatch, "rejection_lesson", ai.AIError("lesson"))
    r = reject(client, app, feedback="No SQL")
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED
    row = repo.get_application(conn, user_a, app["id"])
    assert (row["stage"], row["rejected_at_stage"], row["feedback_received"], row["lesson"]) == ("rejected", "cv", "No SQL", None)
    capture(monkeypatch, "rejection_lesson", LESSON)
    assert reject(client, app, feedback="No SQL").json()["lesson"]["one_change"] == LESSON["one_change"]
    assert stages(conn, user_a, app["id"]) == ["applied", "rejected"]


def test_lesson_for_an_application_moved_meanwhile_is_not_saved(client, monkeypatch, conn, user_a):
    app = add(client, cv_version_id=sent_cv(conn, user_a)["id"])

    def moved_meanwhile(**kwargs):
        repo.update_application(conn, user_a, app["id"], {"stage": "applied"})  # the card is dragged out while the model writes
        return dict(LESSON)
    monkeypatch.setattr(ai, "rejection_lesson", moved_meanwhile)
    r = reject(client, app)
    assert r.status_code == 200 and (r.json()["lesson"], r.json()["notice"]) == (None, CHANGED)
    row = repo.get_application(conn, user_a, app["id"])
    assert (row["stage"], row["lesson"]) == ("applied", None)


def test_limit_reached_keeps_the_rejection(client, monkeypatch, conn, user_a):
    monkeypatch.setenv("DAILY_AI_LIMIT", "1")
    repo.record_usage(conn, user_a, "ai", "cv")
    app = add(client, cv_version_id=sent_cv(conn, user_a)["id"])
    calls = capture(monkeypatch, "rejection_lesson", LESSON)
    r = reject(client, app, ended_at="screening")
    assert r.status_code == 429 and r.json()["detail"] == LIMIT and calls == []
    assert repo.get_application(conn, user_a, app["id"])["rejected_at_stage"] == "screening"


@pytest.mark.parametrize("body", [{"ended_at": "offer"}, {}, {"ended_at": "cv", "feedback": "x" * 2001}])
def test_reject_validation(client, body):
    app = add(client)
    assert client.post(f"/api/applications/{app['id']}/reject", json=body).status_code == 422


# ---------- follow-ups ----------

def test_follow_up_draft_sends_only_the_role_company_date_and_name(client, monkeypatch, conn, user_a):
    app = add(client, contact_name="Zzqx Person", contact="zzqx@example.test", applied_on="2026-10-07")
    calls = capture(monkeypatch, "follow_up", DRAFT)
    r = client.post(f"/api/ai/applications/{app['id']}/follow-up")
    assert r.status_code == 200 and r.json() == DRAFT
    assert calls == [{"role": "Zzqx Analyst", "company": "Zzqx Holdings Ltd", "applied_on": date(2026, 10, 7),
                      "contact_name": "Zzqx Person", "sender": "Test Person"}]
    assert ai_used(conn, user_a) == 1


def test_follow_up_refused_once_an_application_has_ended(client, monkeypatch):
    calls = capture(monkeypatch, "follow_up", DRAFT)
    for stage in ("offer", "rejected", "rejected_after_interview"):
        r = client.post(f"/api/ai/applications/{add(client, stage=stage)['id']}/follow-up")
        assert r.status_code == 400 and r.json()["detail"] == ENDED
    assert calls == []


def test_follow_up_draft_failure_shows_retry(client, monkeypatch):
    capture(monkeypatch, "follow_up", ai.AIError("follow up"))
    r = client.post(f"/api/ai/applications/{add(client)['id']}/follow-up")
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED


def test_followed_up_moves_the_date_a_week_from_today(client, conn):
    r = client.post(f"/api/applications/{add(client)['id']}/followed-up")
    today = repo.today(conn)
    assert r.status_code == 200
    assert (r.json()["last_followed_up_on"], r.json()["follow_up_on"]) == (str(today), str(today + timedelta(days=7)))


def test_follow_ups_due_in_the_state(client, conn):
    app = add(client, applied_on=str(repo.today(conn) - timedelta(days=7)))
    s = state(client)
    assert [f["id"] for f in s["follow_ups_due"]] == [app["id"]] and s["plan"][0]["id"] == "follow-ups"


# ---------- goals ----------

def test_first_goal_applies_this_week_and_the_next_from_monday(client, conn):
    today = repo.today(conn)
    monday = today - timedelta(days=today.weekday())
    r = client.put("/api/profile/goals", json={"applications": 1, "practice": 0})
    assert r.status_code == 200 and r.json() == {"goal": {"applications": 1, "practice": 0, "outreach": 2}, "starts_on": str(monday)}
    assert state(client)["habits"]["this_week"]["goal"] == {"applications": 1, "practice": 0, "outreach": 2}  # left out: kept
    r = client.put("/api/profile/goals", json={"applications": 4, "practice": 1})
    assert r.json()["starts_on"] == str(monday + timedelta(days=7))
    week = state(client)["habits"]["this_week"]
    assert (week["goal"], week["next_goal"]) == ({"applications": 1, "practice": 0, "outreach": 2}, {"applications": 4, "practice": 1, "outreach": 2})


@pytest.mark.parametrize("goal", [{"applications": 0, "practice": 1}, {"applications": 31, "practice": 1}, {"applications": 5, "practice": 15},
                                  {"applications": 5, "practice": -1}, {"applications": 5}, {}])
def test_goal_bounds(client, goal):
    assert client.put("/api/profile/goals", json=goal).status_code == 422


def test_one_application_with_a_cv_meets_a_goal_of_one(client, conn, user_a):
    client.put("/api/profile/goals", json={"applications": 1, "practice": 0, "outreach": 0})
    add(client)  # no CV recorded: logged, but it does not count
    assert state(client)["habits"]["this_week"]["met"] is False
    add(client, cv_version_id=sent_cv(conn, user_a)["id"])
    habits = state(client)["habits"]
    assert (habits["this_week"]["met"], habits["this_week"]["without_cv"], habits["streak"], habits["best_streak"]) == (True, 1, 1, 1)


# ---------- milestones ----------

def new_milestones(client) -> list:
    return [m["id"] for m in state(client)["habits"]["new_milestones"]]


def test_milestone_shown_once(client):
    add(client)
    assert new_milestones(client) == ["applications-1"]
    assert state(client)["habits"]["new_milestones"][0]["text"]
    assert client.post("/api/milestones/seen", json={"ids": ["applications-1"]}).status_code == 204
    assert new_milestones(client) == [] and state(client)["habits"]["milestones"] == ["applications-1"]


@pytest.mark.parametrize("body", [{"ids": ["applications-1000"]}, {"ids": "applications-1"}, {}])
def test_unknown_milestone_refused(client, body):
    assert client.post("/api/milestones/seen", json=body).status_code == 422


def test_deleting_an_application_never_re_announces_and_takes_an_unseen_milestone_with_it(client):
    first = add(client)
    client.post("/api/milestones/seen", json={"ids": ["applications-1"]})
    client.delete(f"/api/applications/{first['id']}")
    second = add(client)
    assert new_milestones(client) == []
    client.patch(f"/api/applications/{second['id']}", json={"stage": "screening"})
    assert new_milestones(client) == ["first-reply"]
    client.delete(f"/api/applications/{second['id']}")
    assert new_milestones(client) == []


# ---------- the state read ----------

def test_state_for_a_new_user_starts_at_zero(client):
    s = state(client)
    habits = s["habits"]
    assert (habits["streak"], habits["best_streak"], habits["milestones"], habits["new_milestones"]) == (0, 0, [], [])
    assert habits["this_week"]["goal"] == DEFAULT_GOAL and s["follow_ups_due"] == []
    assert [t["id"] for t in s["plan"]] == ["applications", "practice", "outreach", "stories"]


def test_application_history_in_the_state(client):
    app = add(client)
    client.patch(f"/api/applications/{app['id']}", json={"stage": "screening"})
    history = next(a for a in state(client)["applications"] if a["id"] == app["id"])["history"]
    assert [(h["from_stage"], h["to_stage"]) for h in history] == [(None, "applied"), ("applied", "screening")]
    assert set(history[0]) == {"from_stage", "to_stage", "at"}


# ---------- ids and other users ----------

def test_malformed_and_unknown_ids(client):
    for path in ("/api/applications/{}/reject", "/api/ai/applications/{}/follow-up", "/api/applications/{}/followed-up"):
        assert client.post(path.format("not-an-id"), json={"ended_at": "cv"}).status_code == 422, path
        r = client.post(path.format(uuid.uuid4()), json={"ended_at": "cv"})
        assert r.status_code == 404 and r.json()["detail"] == GONE, path


def test_user_b_reaches_none_of_user_as_tracker(client, as_user, monkeypatch, conn, user_a, user_b):
    app = add(client, cv_version_id=sent_cv(conn, user_a)["id"])
    capture(monkeypatch, "rejection_lesson", LESSON)
    assert reject(client, app).status_code == 200
    client.put("/api/profile/goals", json={"applications": 2, "practice": 1})
    client.post("/api/milestones/seen", json={"ids": ["applications-1"]})
    as_user(user_b)
    drafts, lessons = capture(monkeypatch, "follow_up", DRAFT), capture(monkeypatch, "rejection_lesson", LESSON)
    for path in (f"/api/applications/{app['id']}/reject", f"/api/ai/applications/{app['id']}/follow-up", f"/api/applications/{app['id']}/followed-up"):
        r = client.post(path, json={"ended_at": "screening"})
        assert r.status_code == 404 and r.json()["detail"] == GONE, path
    s = state(client)
    assert s["applications"] == [] and s["habits"]["this_week"]["goal"] == DEFAULT_GOAL and s["habits"]["milestones"] == []
    assert drafts == [] and lessons == [] and ai_used(conn, user_b) == 0
    mine = repo.get_application(conn, user_a, app["id"])
    assert (mine["rejected_at_stage"], mine["last_followed_up_on"]) == ("cv", None) and mine["lesson"]["page"] == "resume"
