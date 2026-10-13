import uuid
from datetime import date

import pytest

import repo

pytestmark = pytest.mark.db

ITEM = {"title": "Thing one", "raw": "did a thing", "uk_version": "Built X for 40 users"}
STORY = {"title": "Story", "competency": "Problem solving", "situation": "s", "task": "t", "action": "a",
         "result": "r", "strength": "strong", "tip": ""}
CONTENT = {"profile": "P", "bullets": [{"text": "Built X", "achievement_id": ""}], "keywords": ["SQL"],
           "cover_letter": {"why_them": "A", "why_you": "B", "what_you_deliver": "C"}, "gaps": []}


def family(conn, user):
    return repo.sync_families(conn, user, [{"name": "Data Analyst", "fit": "direct", "overlap": 80}])[0]


def job(conn, user, **kw):
    fields = dict(title="Role A", company="Company A", location=None, url=None, description="Analyse data. " * 5,
                  summary="A summary", keywords=["SQL"], role_family_id=None) | kw
    return repo.add_job(conn, user, **fields)


def cv(conn, user, **kw):
    fields = dict(saved_job_id=None, role_family_id=None, base_name="Role A, Company A", content=CONTENT) | kw
    return repo.add_cv_version(conn, user, **fields)


def application(conn, user, **kw):
    return repo.add_application(conn, user, {"company": "Company A", "role": "Role A", "source": "Company site"} | kw)


# ---------- saved jobs ----------

def test_job_round_trip_and_delete(conn, user_a):
    fam = family(conn, user_a)
    j = job(conn, user_a, role_family_id=fam["id"], url="https://example.test/job", location="London")
    assert j["role_family_id"] == fam["id"] and j["keywords"] == ["SQL"] and j["source"] == "pasted"
    assert repo.get_job(conn, user_a, j["id"])["summary"] == "A summary"
    assert [x["id"] for x in repo.list_jobs(conn, user_a)] == [j["id"]]
    assert repo.delete_job(conn, user_a, j["id"]) is True
    assert repo.delete_job(conn, user_a, j["id"]) is False


def test_get_job_none_for_other_user(conn, user_a, user_b):
    assert repo.get_job(conn, user_b, job(conn, user_a)["id"]) is None


def test_delete_job_false_for_other_user(conn, user_a, user_b):
    j = job(conn, user_a)
    assert repo.delete_job(conn, user_b, j["id"]) is False
    assert repo.get_job(conn, user_a, j["id"]) is not None


# ---------- CV versions ----------

def test_cv_version_names_increment_per_job(conn, user_a):
    j, other = job(conn, user_a), job(conn, user_a, title="Role B")
    assert cv(conn, user_a, saved_job_id=j["id"])["name"] == "Role A, Company A v1"
    assert cv(conn, user_a, saved_job_id=j["id"])["name"] == "Role A, Company A v2"
    assert cv(conn, user_a, saved_job_id=other["id"], base_name="Role B, Company A")["name"] == "Role B, Company A v1"


def test_cv_version_content_round_trips_as_dict(conn, user_a):
    saved = cv(conn, user_a)
    assert saved["content"] == CONTENT
    assert repo.list_cv_versions(conn, user_a)[0]["content"]["cover_letter"]["why_them"] == "A"
    assert repo.get_cv_version(conn, user_a, saved["id"])["name"] == saved["name"]


def test_get_cv_version_none_for_other_user(conn, user_a, user_b):
    assert repo.get_cv_version(conn, user_b, cv(conn, user_a)["id"]) is None


# ---------- stories ----------

def test_story_keeps_when_achievement_deleted(conn, user_a):
    a = repo.add_achievements(conn, user_a, [ITEM], "paste")[0]
    s = repo.add_story(conn, user_a, a["id"], STORY)
    assert s["achievement_id"] == a["id"] and s["strength"] == "strong"
    repo.delete_achievement(conn, user_a, a["id"])
    assert repo.list_stories(conn, user_a)[0]["achievement_id"] is None


# ---------- applications ----------

def test_application_defaults(conn, user_a):
    a = application(conn, user_a)
    today = conn.execute("select (now() at time zone 'Europe/London')::date as d").fetchone()["d"]
    assert a["stage"] == "applied" and a["applied_on"] == today
    assert a["posted_on"] is None and a["role_family_id"] is None and a["notes"] is None


def test_application_with_all_fields(conn, user_a):
    fam, j = family(conn, user_a), job(conn, user_a)
    c = cv(conn, user_a, saved_job_id=j["id"])
    a = application(conn, user_a, role_family_id=fam["id"], cv_version_id=c["id"], saved_job_id=j["id"], stage="screening",
                    applied_on=date(2026, 10, 5), posted_on=date(2026, 10, 3), job_url="https://example.test/j",
                    contact="A Person", notes="note", sponsor_licence=True, follow_up_on=date(2026, 10, 19))
    assert (a["role_family_id"], a["cv_version_id"], a["saved_job_id"]) == (fam["id"], c["id"], j["id"])
    assert a["posted_on"] == date(2026, 10, 3) and a["sponsor_licence"] is True and a["follow_up_on"] == date(2026, 10, 19)


def test_application_update_only_named_fields(conn, user_a):
    a = application(conn, user_a, notes="keep me")
    conn.execute("update applications set updated_at = now() - interval '1 hour' where id = %s", (a["id"],))
    before = conn.execute("select updated_at from applications where id = %s", (a["id"],)).fetchone()["updated_at"]
    updated = repo.update_application(conn, user_a, a["id"], {"stage": "interview"})
    assert updated["stage"] == "interview" and updated["notes"] == "keep me" and updated["updated_at"] > before


def test_application_update_with_no_fields_returns_row(conn, user_a):
    a = application(conn, user_a)
    assert repo.update_application(conn, user_a, a["id"], {})["id"] == a["id"]


def test_application_unknown_field_raises(conn, user_a, user_b):
    with pytest.raises(ValueError):
        application(conn, user_a, user_id=user_b)
    a = application(conn, user_a)
    with pytest.raises(ValueError):
        repo.update_application(conn, user_a, a["id"], {"user_id": user_b})
    with pytest.raises(ValueError):
        repo.update_application(conn, user_a, a["id"], {"id": str(uuid.uuid4())})


def test_update_application_none_for_other_user(conn, user_a, user_b):
    a = application(conn, user_a)
    assert repo.update_application(conn, user_b, a["id"], {"stage": "offer"}) is None
    assert repo.list_applications(conn, user_a)[0]["stage"] == "applied"


def test_delete_application_false_for_other_user(conn, user_a, user_b):
    a = application(conn, user_a)
    assert repo.delete_application(conn, user_b, a["id"]) is False
    assert repo.delete_application(conn, user_a, a["id"]) is True


def test_foreign_reference_stored_as_null(conn, user_a, user_b):
    fam, j = family(conn, user_a), job(conn, user_a)
    c = cv(conn, user_a)
    theirs = application(conn, user_b, role_family_id=fam["id"], cv_version_id=c["id"], saved_job_id=j["id"])
    assert (theirs["role_family_id"], theirs["cv_version_id"], theirs["saved_job_id"]) == (None, None, None)
    mine = application(conn, user_b)
    updated = repo.update_application(conn, user_b, mine["id"], {"role_family_id": fam["id"]})
    assert updated["role_family_id"] is None
    assert job(conn, user_b, role_family_id=fam["id"])["role_family_id"] is None
    assert cv(conn, user_b, saved_job_id=j["id"], role_family_id=fam["id"])["saved_job_id"] is None
    a = repo.add_achievements(conn, user_a, [ITEM], "paste")[0]
    assert repo.add_story(conn, user_b, a["id"], STORY)["achievement_id"] is None


def test_deleted_reference_stored_as_null(conn, user_a):
    assert application(conn, user_a, role_family_id=str(uuid.uuid4()))["role_family_id"] is None


def test_applications_newest_first(conn, user_a):
    application(conn, user_a, company="Old", applied_on=date(2026, 9, 1))
    application(conn, user_a, company="New", applied_on=date(2026, 10, 1))
    assert [a["company"] for a in repo.list_applications(conn, user_a)] == ["New", "Old"]


# ---------- journal ----------

def test_journal_round_trip(conn, user_a):
    e = repo.add_journal_entry(conn, user_a, type="interview", title="HR screening call: general practice", with_whom="Mock interviewer",
                               summary="s", points=["a"], actions=["b"], scores={"structure": 3})
    assert e["points"] == ["a"] and e["scores"] == {"structure": 3}
    plain = repo.add_journal_entry(conn, user_a, type="coach", title="t", with_whom="Careers coach", summary="s", points=[], actions=[])
    assert plain["scores"] is None
    assert {x["id"] for x in repo.list_journal(conn, user_a)} == {e["id"], plain["id"]}


def test_journal_transcript_saved_but_not_listed(conn, user_a, user_b):
    with_text = repo.add_journal_entry(conn, user_a, type="coach", title="t", with_whom="Careers coach", summary="s",
                                       points=[], actions=[], transcript="Coach: hi\nCandidate: hello")
    without = repo.add_journal_entry(conn, user_a, type="coach", title="t2", with_whom="Careers coach", summary="s", points=[], actions=[])
    listed = {e["id"]: e for e in repo.list_journal(conn, user_a)}
    assert "transcript" not in with_text and all("transcript" not in e for e in listed.values())  # kept out of every page load
    assert listed[with_text["id"]]["has_transcript"] is True and listed[without["id"]]["has_transcript"] is False
    assert repo.get_journal_transcript(conn, user_a, with_text["id"]) == "Coach: hi\nCandidate: hello"
    assert repo.get_journal_transcript(conn, user_a, without["id"]) is None
    assert repo.get_journal_transcript(conn, user_b, with_text["id"]) is None


# ---------- everything at once ----------

def test_load_state_only_own_rows(conn, user_a, user_b):
    fam, j = family(conn, user_a), job(conn, user_a)
    a = repo.add_achievements(conn, user_a, [ITEM], "paste")[0]
    cv(conn, user_a, saved_job_id=j["id"])
    repo.add_story(conn, user_a, a["id"], STORY)
    application(conn, user_a, role_family_id=fam["id"])
    repo.add_journal_entry(conn, user_a, type="coach", title="t", with_whom="w", summary="s", points=[], actions=[])
    repo.add_entry(conn, user_a, "work_history", {"employer": "Zzqx Holdings Ltd"})
    repo.add_entry(conn, user_a, "education", {"institution": "University of Zzqx"})
    keys = {"achievements", "work_history", "education", "role_families", "saved_jobs", "cv_versions", "stories", "applications", "journal"}
    mine, theirs = repo.load_state(conn, user_a), repo.load_state(conn, user_b)
    assert set(mine) == set(theirs) == keys
    assert all(len(mine[k]) == 1 for k in keys)
    assert all(theirs[k] == [] for k in keys)


# ---------- editing and deleting stories ----------

def story(conn, user):
    a = repo.add_achievements(conn, user, [ITEM], "paste")[0]
    return a, repo.add_story(conn, user, a["id"], STORY)


def test_update_story_changes_only_the_fields_given(conn, user_a):
    _, s = story(conn, user_a)
    changed = repo.update_story(conn, user_a, s["id"], {"result": "Late deliveries fell by 8%", "competency": "Delivering results"})
    assert changed["result"] == "Late deliveries fell by 8%" and changed["competency"] == "Delivering results"
    assert changed["situation"] == "s" and changed["strength"] == "strong" and changed["achievement_id"] == s["achievement_id"]
    assert repo.get_story(conn, user_a, s["id"]) == changed


@pytest.mark.parametrize("field", ["achievement_id", "user_id", "strength"])
def test_update_story_refuses_other_fields(conn, user_a, field):
    _, s = story(conn, user_a)
    with pytest.raises(ValueError):
        repo.update_story(conn, user_a, s["id"], {field: "changed"})


def test_delete_story_keeps_the_achievement(conn, user_a):
    a, s = story(conn, user_a)
    assert repo.delete_story(conn, user_a, s["id"]) is True
    assert repo.delete_story(conn, user_a, s["id"]) is False
    assert repo.list_stories(conn, user_a) == [] and repo.get_achievement(conn, user_a, a["id"]) is not None


def test_another_user_cannot_read_change_or_delete_a_story(conn, user_a, user_b):
    _, s = story(conn, user_a)
    assert repo.get_story(conn, user_b, s["id"]) is None
    assert repo.update_story(conn, user_b, s["id"], {"title": "Taken over"}) is None
    assert repo.delete_story(conn, user_b, s["id"]) is False
    assert repo.get_story(conn, user_a, s["id"]) == s


def test_achievements_without_story(conn, user_a, user_b):
    a, _ = story(conn, user_a)
    bare = repo.add_achievements(conn, user_a, [ITEM | {"title": "Thing two"}], "paste")[0]
    repo.add_achievements(conn, user_b, [ITEM], "paste")
    assert [x["id"] for x in repo.achievements_without_story(conn, user_a)] == [bare["id"]]
    assert len(repo.achievements_without_story(conn, user_b)) == 1
