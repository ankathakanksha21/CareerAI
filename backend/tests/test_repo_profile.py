from datetime import date

import pytest

import repo

pytestmark = pytest.mark.db

DETAILS = dict(full_name="Test Person", university="University A", course="MSc Course A",
               graduation_date=date(2026, 9, 17), visa_type="student", visa_end_date=date(2027, 1, 31),
               locations=["London", "Remote"])
ITEM = {"title": "Thing one", "raw": "did a thing", "uk_version": "Built X for 40 users", "skills": ["SQL"],
        "outcome": "40 users", "scale": "one team", "context_note": "note"}


def fam(name="Data Analyst", **kw):
    return {"name": name, "fit": "direct", "overlap": 80, "uk_titles": ["Data Analyst"], "why": "w",
            "needs": [{"need": "SQL", "shown_by": "Thing one"}]} | kw


# ---------- profile ----------

def test_profile_created_once(conn, user_a):
    first = repo.get_or_create_profile(conn, user_a, "Test Person")
    second = repo.get_or_create_profile(conn, user_a, "Another Name")
    assert first["full_name"] == second["full_name"] == "Test Person"
    assert first["user_id"] == user_a and first["locations"] == []


def test_first_name_derived(conn, user_a):
    assert repo.get_or_create_profile(conn, user_a, "Test Person")["first_name"] == "Test"
    assert repo.get_or_create_profile(conn, repo_user(conn), "")["first_name"] == ""


def repo_user(conn):
    from conftest import _throwaway_user
    return _throwaway_user(conn)


def test_update_profile_normalises_graduation(conn, user_a):
    p = repo.update_profile(conn, user_a, **DETAILS)
    assert p["graduation_date"] == date(2026, 9, 1)
    assert p["visa_type"] == "student" and p["locations"] == ["London", "Remote"] and p["first_name"] == "Test"
    assert repo.get_or_create_profile(conn, user_a, "ignored")["university"] == "University A"


def test_update_profile_updates_existing_row(conn, user_a):
    repo.get_or_create_profile(conn, user_a, "Old Name")
    repo.set_pitch(conn, user_a, "I am a pitch.")
    p = repo.update_profile(conn, user_a, **DETAILS)
    assert p["full_name"] == "Test Person" and p["pitch"] == "I am a pitch."


def test_details_complete():
    full = DETAILS | {"graduation_date": date(2026, 9, 1)}
    assert repo.details_complete(full) is True
    for key in ("university", "course", "graduation_date", "visa_type", "visa_end_date"):
        assert repo.details_complete(full | {key: None}) is False
    assert repo.details_complete(full | {"locations": []}) is False
    assert repo.details_complete(full | {"course": "  "}) is False


# ---------- achievements ----------

def test_achievements_round_trip_newest_first(conn, user_a):
    saved = repo.add_achievements(conn, user_a, [ITEM, ITEM | {"title": "Thing two"}], "paste")
    assert [a["title"] for a in saved] == ["Thing one", "Thing two"]
    assert all(isinstance(a["id"], str) and a["source"] == "paste" and a["skills"] == ["SQL"] for a in saved)
    later = repo.add_achievements(conn, user_a, [ITEM | {"title": "Thing three"}], "voice")
    listed = repo.list_achievements(conn, user_a)
    assert len(listed) == 3 and {a["id"] for a in listed} == {a["id"] for a in saved + later}
    assert repo.get_achievement(conn, user_a, saved[0]["id"])["uk_version"] == "Built X for 40 users"


def test_delete_achievement(conn, user_a):
    a = repo.add_achievements(conn, user_a, [ITEM], "paste")[0]
    assert repo.delete_achievement(conn, user_a, a["id"]) is True
    assert repo.delete_achievement(conn, user_a, a["id"]) is False
    assert repo.list_achievements(conn, user_a) == []


def test_delete_achievement_returns_false_for_other_user(conn, user_a, user_b):
    a = repo.add_achievements(conn, user_a, [ITEM], "paste")[0]
    assert repo.delete_achievement(conn, user_b, a["id"]) is False
    assert len(repo.list_achievements(conn, user_a)) == 1


def test_get_achievement_none_for_other_user(conn, user_a, user_b):
    a = repo.add_achievements(conn, user_a, [ITEM], "paste")[0]
    assert repo.get_achievement(conn, user_b, a["id"]) is None


def test_list_achievements_empty_for_other_user(conn, user_a, user_b):
    repo.add_achievements(conn, user_a, [ITEM], "paste")
    assert repo.list_achievements(conn, user_b) == []



# ---------- editing an achievement, and where it happened ----------

def job_at(conn, user, employer="Zzqx Holdings Ltd"):
    return repo.add_entry(conn, user, "work_history", {"employer": employer})


def course_at(conn, user):
    return repo.add_entry(conn, user, "education", {"institution": "University of Zzqx"})


def test_update_achievement_changes_only_the_fields_given(conn, user_a):
    a = repo.add_achievements(conn, user_a, [ITEM], "cv")[0]
    changed = repo.update_achievement(conn, user_a, a["id"], {"uk_version": "Built X for 55 users", "skills": ["SQL", "Excel"]})
    assert changed["uk_version"] == "Built X for 55 users" and changed["skills"] == ["SQL", "Excel"]
    assert {k: changed[k] for k in ("title", "raw", "outcome", "scale", "context_note", "source")} == \
           {k: a[k] for k in ("title", "raw", "outcome", "scale", "context_note", "source")}


@pytest.mark.parametrize("field", ["raw", "source", "user_id", "source_url"])
def test_the_quote_and_the_source_cannot_be_edited(conn, user_a, field):
    a = repo.add_achievements(conn, user_a, [ITEM], "cv")[0]
    with pytest.raises(ValueError):
        repo.update_achievement(conn, user_a, a["id"], {field: "changed"})
    assert repo.get_achievement(conn, user_a, a["id"]) == a


def test_update_achievement_none_for_other_user(conn, user_a, user_b):
    a = repo.add_achievements(conn, user_a, [ITEM], "cv")[0]
    assert repo.update_achievement(conn, user_b, a["id"], {"title": "Taken over"}) is None
    assert repo.get_achievement(conn, user_a, a["id"])["title"] == "Thing one"


def test_an_achievement_is_linked_to_a_job_or_a_course_never_both(conn, user_a):
    a = repo.add_achievements(conn, user_a, [ITEM], "cv")[0]
    job, course = job_at(conn, user_a), course_at(conn, user_a)
    at_work = repo.update_achievement(conn, user_a, a["id"], {"work_history_id": job["id"]})
    assert at_work["work_history_id"] == job["id"] and at_work["education_id"] is None
    on_course = repo.update_achievement(conn, user_a, a["id"], {"education_id": course["id"]})
    assert on_course["education_id"] == course["id"] and on_course["work_history_id"] is None
    unlinked = repo.update_achievement(conn, user_a, a["id"], {"education_id": None})
    assert unlinked["education_id"] is None and unlinked["work_history_id"] is None


def test_an_achievement_cannot_be_linked_to_another_users_job_or_course(conn, user_a, user_b):
    a = repo.add_achievements(conn, user_a, [ITEM], "cv")[0]
    theirs, their_course = job_at(conn, user_b), course_at(conn, user_b)
    assert repo.update_achievement(conn, user_a, a["id"], {"work_history_id": theirs["id"]})["work_history_id"] is None
    assert repo.update_achievement(conn, user_a, a["id"], {"education_id": their_course["id"]})["education_id"] is None


def test_deleting_the_job_keeps_the_achievement_unlinked(conn, user_a):
    job = job_at(conn, user_a)
    a = repo.add_achievements(conn, user_a, [ITEM | {"work_history_id": job["id"]}], "cv")[0]
    assert a["work_history_id"] == job["id"]
    repo.delete_entry(conn, user_a, "work_history", job["id"])
    assert repo.get_achievement(conn, user_a, a["id"])["work_history_id"] is None


def test_new_achievements_carry_their_link_and_repository(conn, user_a, user_b):
    job, theirs = job_at(conn, user_a), job_at(conn, user_b)
    saved = repo.add_achievements(conn, user_a, [
        ITEM | {"work_history_id": job["id"], "source_url": "https://github.com/zzqx-sample/thing"},
        ITEM | {"title": "Thing two", "work_history_id": theirs["id"]},
        ITEM | {"title": "Thing three"}], "github")
    assert saved[0]["work_history_id"] == job["id"] and saved[0]["source_url"] == "https://github.com/zzqx-sample/thing"
    assert saved[1]["work_history_id"] is None and saved[2]["source_url"] is None


def test_link_achievements_links_only_the_callers(conn, user_a, user_b):
    mine = repo.add_achievements(conn, user_a, [ITEM, ITEM | {"title": "Thing two"}], "cv")
    theirs = repo.add_achievements(conn, user_b, [ITEM], "cv")[0]
    course = course_at(conn, user_a)
    assert repo.link_achievements(conn, user_a, [mine[0]["id"], theirs["id"]], education_id=course["id"]) == 1
    assert repo.get_achievement(conn, user_a, mine[0]["id"])["education_id"] == course["id"]
    assert repo.get_achievement(conn, user_a, mine[1]["id"])["education_id"] is None
    assert repo.get_achievement(conn, user_b, theirs["id"])["education_id"] is None


def test_link_achievements_to_another_users_job_does_nothing(conn, user_a, user_b):
    a = repo.add_achievements(conn, user_a, [ITEM], "cv")[0]
    assert repo.link_achievements(conn, user_a, [a["id"]], work_history_id=job_at(conn, user_b)["id"]) == 0
    assert repo.link_achievements(conn, user_a, [], work_history_id=job_at(conn, user_a)["id"]) == 0
    assert repo.get_achievement(conn, user_a, a["id"])["work_history_id"] is None


def test_imported_urls(conn, user_a, user_b):
    repo.add_achievements(conn, user_a, [ITEM | {"source_url": "https://github.com/zzqx-sample/thing"}, ITEM], "github")
    assert repo.imported_urls(conn, user_a) == {"https://github.com/zzqx-sample/thing"}
    assert repo.imported_urls(conn, user_b) == set()


# ---------- role families ----------

def test_sync_inserts_new_families(conn, user_a):
    out = repo.sync_families(conn, user_a, [fam("Stretchy", fit="stretch", overlap=40), fam("Near", fit="near", overlap=70),
                                            fam("Direct low", overlap=75), fam("Direct high", overlap=90)])
    assert [f["name"] for f in out] == ["Direct high", "Direct low", "Near", "Stretchy"]
    assert out[0]["needs"] == [{"need": "SQL", "shown_by": "Thing one"}] and out[0]["targeted"] is False
    assert out == repo.list_families(conn, user_a)


def test_sync_updates_in_place_keeping_id_and_targeted(conn, user_a):
    original = repo.sync_families(conn, user_a, [fam("Data Analyst")])[0]
    assert repo.set_family_targeted(conn, user_a, original["id"], True)["targeted"] is True
    updated = repo.sync_families(conn, user_a, [fam(" data analyst ", overlap=60)])
    assert len(updated) == 1
    assert updated[0]["id"] == original["id"] and updated[0]["targeted"] is True and updated[0]["overlap"] == 60


def test_sync_removes_untargeted_unreferenced(conn, user_a):
    repo.sync_families(conn, user_a, [fam("Keep"), fam("Drop")])
    assert [f["name"] for f in repo.sync_families(conn, user_a, [fam("Keep")])] == ["Keep"]


def test_sync_keeps_targeted_even_if_omitted(conn, user_a):
    old = repo.sync_families(conn, user_a, [fam("Targeted")])[0]
    repo.set_family_targeted(conn, user_a, old["id"], True)
    assert {f["name"] for f in repo.sync_families(conn, user_a, [fam("New")])} == {"Targeted", "New"}


def test_sync_keeps_referenced_even_if_omitted(conn, user_a):
    old = repo.sync_families(conn, user_a, [fam("Referenced")])[0]
    conn.execute("insert into applications (user_id, company, role, source, role_family_id) values (%s, 'Company A', 'Role A', 'Other', %s)",
                 (user_a, old["id"]))
    assert {f["name"] for f in repo.sync_families(conn, user_a, [fam("New")])} == {"Referenced", "New"}


def test_sync_tolerates_duplicate_names_in_input(conn, user_a):
    out = repo.sync_families(conn, user_a, [fam("Data Analyst", why="first"), fam("DATA ANALYST", why="second")])
    assert len(out) == 1


def test_sync_does_not_touch_other_users_families(conn, user_a, user_b):
    repo.sync_families(conn, user_a, [fam("Data Analyst")])
    theirs = repo.sync_families(conn, user_b, [fam("Data Analyst"), fam("Other")])
    assert len(theirs) == 2
    repo.sync_families(conn, user_b, [fam("Other")])
    assert [f["name"] for f in repo.list_families(conn, user_a)] == ["Data Analyst"]


def test_set_family_targeted_none_for_other_user(conn, user_a, user_b):
    f = repo.sync_families(conn, user_a, [fam()])[0]
    assert repo.set_family_targeted(conn, user_b, f["id"], True) is None
    assert repo.list_families(conn, user_a)[0]["targeted"] is False
