import uuid
from datetime import date

import pytest

import repo

pytestmark = pytest.mark.db

DETAILS = {"full_name": "Test Person", "university": "Zzqx City University", "course": "MSc Course A", "graduation_date": "2026-09-17",
           "visa_type": "student", "visa_end_date": "2027-01-31", "locations": ["London"]}
JOB = {"employer": "Zzqx Holdings Ltd", "job_title": "Systems Engineer", "location": "Pune", "country": "India",
       "start_month": "2023-07-14", "end_month": "2025-08-20", "is_current": False, "employer_context": "IT services"}
COURSE = {"institution": "University of Zzqx", "qualification": "BTech", "subject": "Computer Science",
          "start_month": "2019-07-01", "end_month": "2023-05-31", "grade": "8.4/10", "country": "India"}
ITEM = {"title": "Thing one", "raw": "did a thing", "uk_version": "Built X for 40 users", "skills": ["SQL"], "outcome": "40 users", "scale": "", "context_note": ""}
STORY = {"title": "Story", "competency": "Problem solving", "situation": "s", "task": "t", "action": "a", "result": "r", "strength": "strong", "tip": ""}
ENTRIES = [("/api/work-history", JOB, "employer", "work_history"), ("/api/education", COURSE, "institution", "education")]
END_BEFORE_START = "The end month cannot be before the start month."
FROM_DETAILS = "Your current course comes from Your details. Change it there."
GONE = "That item no longer exists"


def state(client):
    return client.get("/api/state").json()


def achievement(conn, user, **kw):
    return repo.add_achievements(conn, user, [ITEM | kw], "cv")[0]


# ---------- work history and education ----------

@pytest.mark.parametrize("path, body, name, key", ENTRIES)
def test_add_edit_and_delete_an_entry(client, path, body, name, key):
    made = client.post(path, json=body)
    assert made.status_code == 201
    row = made.json()
    assert row[name] == body[name] and row["start_month"].endswith("-01") and row["end_month"].endswith("-01") and row["source"] == "manual"
    assert state(client)[key] == [row]

    changed = client.patch(f"{path}/{row['id']}", json={"country": "Elsewhere"}).json()
    assert changed["country"] == "Elsewhere" and changed[name] == body[name] and changed["start_month"] == row["start_month"]

    assert client.delete(f"{path}/{row['id']}").status_code == 204
    assert state(client)[key] == [] and client.delete(f"{path}/{row['id']}").status_code == 404


@pytest.mark.parametrize("path, body, name, key", ENTRIES)
def test_an_entry_needs_only_its_name(client, path, body, name, key):
    row = client.post(path, json={name: body[name]}).json()
    assert row["start_month"] is None and row["end_month"] is None and row["country"] == ""


@pytest.mark.parametrize("path, body, name, key", ENTRIES)
@pytest.mark.parametrize("change", [{"NAME": "  "}, {"NAME": "x" * 161}, {"start_month": "last summer"}, {"start_month": "1066-10-01"},
                                    {"start_month": "2024-01-01", "end_month": "2023-12-01"}])
def test_entry_validation(client, path, body, name, key, change):
    change = {name if k == "NAME" else k: v for k, v in change.items()}
    r = client.post(path, json=body | change)
    assert r.status_code == 422 and state(client)[key] == []


@pytest.mark.parametrize("path, body, name, key", ENTRIES)
def test_end_before_start_is_refused_with_a_plain_message(client, path, body, name, key):
    assert client.post(path, json=body | {"start_month": "2024-03-01", "end_month": "2024-02-01"}).json()["detail"][0]["msg"].endswith(END_BEFORE_START)
    row = client.post(path, json=body).json()
    r = client.patch(f"{path}/{row['id']}", json={"end_month": "2010-01-01"})   # before the stored start
    assert r.status_code == 422 and r.json()["detail"] == END_BEFORE_START
    assert state(client)[key][0]["end_month"] == row["end_month"]


def test_a_job_in_the_same_month_it_started_is_fine(client):
    assert client.post("/api/work-history", json=JOB | {"start_month": "2024-03-28", "end_month": "2024-03-02"}).status_code == 201


def test_a_current_job_has_no_end_month(client):
    r = client.post("/api/work-history", json=JOB | {"is_current": True})
    assert r.status_code == 422 and r.json()["detail"][0]["msg"].endswith("A job you still do has no end month.")
    row = client.post("/api/work-history", json=JOB | {"is_current": True, "end_month": None}).json()
    assert row["is_current"] is True and row["end_month"] is None
    r = client.patch(f"/api/work-history/{row['id']}", json={"end_month": "2025-08-01"})
    assert r.status_code == 422 and r.json()["detail"] == "A job you still do has no end month."
    done = client.patch(f"/api/work-history/{row['id']}", json={"end_month": "2025-08-01", "is_current": False}).json()
    assert done["is_current"] is False and done["end_month"] == "2025-08-01"


@pytest.mark.parametrize("path, body, name, key", ENTRIES)
def test_entry_bad_and_unknown_ids(client, path, body, name, key):
    assert client.patch(f"{path}/not-a-uuid", json={"country": "x"}).status_code == 422
    assert client.delete(f"{path}/not-a-uuid").status_code == 422
    r = client.patch(f"{path}/{uuid.uuid4()}", json={"country": "x"})
    assert r.status_code == 404 and r.json()["detail"] == GONE


@pytest.mark.parametrize("path, body, name, key", ENTRIES)
def test_another_user_cannot_see_change_or_delete_an_entry(client, user_b, as_user, path, body, name, key):
    row = client.post(path, json=body).json()
    as_user(user_b)
    assert state(client)[key] == []
    assert client.patch(f"{path}/{row['id']}", json={name: "Taken over"}).status_code == 404
    assert client.delete(f"{path}/{row['id']}").status_code == 404


# ---------- the current course ----------

def test_saving_details_gives_the_first_education_entry(client):
    client.put("/api/profile", json=DETAILS)
    course = state(client)["education"][0]
    assert course["from_details"] is True and course["institution"] == "Zzqx City University" and course["qualification"] == "MSc Course A"
    assert course["end_month"] == "2026-09-01" and course["country"] == "United Kingdom"


def test_the_current_course_takes_a_grade_and_start_month_but_is_renamed_only_in_details(client):
    client.put("/api/profile", json=DETAILS)
    course = state(client)["education"][0]
    path = f"/api/education/{course['id']}"
    added = client.patch(path, json={"grade": "Predicted Merit", "start_month": "2025-09-15", "subject": "Analytics",
                                     "institution": "Zzqx City University", "end_month": "2026-09-01"})   # unchanged values are allowed through
    assert added.status_code == 200 and added.json()["grade"] == "Predicted Merit" and added.json()["start_month"] == "2025-09-01"
    for change in ({"institution": "Another University"}, {"qualification": "MSc Something Else"}, {"end_month": "2027-01-01"}):
        r = client.patch(path, json=change)
        assert r.status_code == 422 and r.json()["detail"] == FROM_DETAILS
    r = client.delete(path)
    assert r.status_code == 422 and r.json()["detail"] == FROM_DETAILS
    assert state(client)["education"][0]["institution"] == "Zzqx City University"


# ---------- skills and languages ----------

def test_put_skills_replaces_both_lists(client):
    client.put("/api/profile/skills", json={"skills": ["SQL"], "languages": [{"language": "Hindi", "level": "Native"}]})
    p = client.put("/api/profile/skills", json={"skills": [" Python ", "python", "Power BI"], "languages": [{"language": "English", "level": ""}]}).json()
    assert p["skills"] == ["Python", "Power BI"] and p["languages"] == [{"language": "English", "level": ""}] and p["email"] == "a@example.test"
    assert state(client)["profile"]["skills"] == ["Python", "Power BI"]


@pytest.mark.parametrize("body", [
    {"skills": ["x" * 61], "languages": []}, {"skills": [f"s{n}" for n in range(61)], "languages": []}, {"skills": [""], "languages": []},
    {"skills": [], "languages": [{"language": "Hindi", "level": "Expert"}]}, {"skills": [], "languages": [{"language": "", "level": ""}]},
    {"skills": [], "languages": [{"language": f"l{n}", "level": ""} for n in range(11)]}, {"skills": "SQL", "languages": []}, {}])
def test_skills_validation(client, body):
    assert client.put("/api/profile/skills", json=body).status_code == 422


def test_the_levels_a_language_may_have_are_in_the_state(client):
    assert state(client)["options"]["language_levels"] == ["Native", "Fluent", "Professional", "Conversational", "Basic"]


def test_skills_are_private(client, user_b, as_user):
    client.put("/api/profile/skills", json={"skills": ["SQL"], "languages": []})
    as_user(user_b)
    assert state(client)["profile"]["skills"] == []


# ---------- confirming what an import found ----------

def test_confirming_facts_saves_them_and_links_the_achievements(client, conn, user_a):
    a1, a2 = achievement(conn, user_a), achievement(conn, user_a, title="Thing two")
    r = client.post("/api/profile/facts", json={
        "source": "cv", "work_history": [JOB | {"achievement_ids": [a1["id"]]}], "education": [COURSE | {"achievement_ids": [a2["id"]]}],
        "skills": ["Python"], "languages": [{"language": "Hindi", "level": "Native"}]})
    assert r.status_code == 200
    body = r.json()
    job, course = body["work_history"][0], body["education"][0]
    assert job["employer"] == "Zzqx Holdings Ltd" and job["source"] == "cv" and course["source"] == "cv"
    assert body["profile"]["skills"] == ["Python"] and body["profile"]["languages"] == [{"language": "Hindi", "level": "Native"}]
    by_id = {a["id"]: a for a in state(client)["achievements"]}
    assert by_id[a1["id"]]["work_history_id"] == job["id"] and by_id[a2["id"]]["education_id"] == course["id"]


def test_confirming_a_fact_that_matches_a_saved_entry_fills_only_its_blanks(client):
    client.put("/api/profile", json=DETAILS)
    course = state(client)["education"][0]
    body = client.post("/api/profile/facts", json={"source": "cv", "education": [
        {"id": course["id"], "start_month": "2025-09-01", "grade": "Predicted Merit", "institution": "Something Else", "end_month": "2030-01-01"}]}).json()
    assert len(body["education"]) == 1
    after = body["education"][0]
    assert after["start_month"] == "2025-09-01" and after["grade"] == "Predicted Merit"
    assert after["institution"] == "Zzqx City University" and after["end_month"] == "2026-09-01"


def test_confirming_the_same_facts_twice_does_not_duplicate_them(client):
    body = {"source": "cv", "work_history": [JOB], "education": [COURSE], "skills": ["Python"], "languages": []}
    client.post("/api/profile/facts", json=body)
    again = client.post("/api/profile/facts", json=body).json()
    assert len(again["work_history"]) == 1 and len(again["education"]) == 1 and again["profile"]["skills"] == ["Python"]


def test_confirming_facts_adds_skills_to_those_already_there(client):
    client.put("/api/profile/skills", json={"skills": ["SQL"], "languages": [{"language": "Hindi", "level": "Native"}]})
    p = client.post("/api/profile/facts", json={"source": "paste", "skills": ["sql", "Excel"], "languages": [{"language": "English", "level": "Fluent"}]}).json()["profile"]
    assert p["skills"] == ["SQL", "Excel"] and [x["language"] for x in p["languages"]] == ["Hindi", "English"]


def test_confirming_facts_never_touches_another_users_rows(client, conn, user_a, user_b):
    theirs = achievement(conn, user_b)
    their_job = repo.add_entry(conn, user_b, "work_history", {"employer": "Zzqx Other Ltd"})
    r = client.post("/api/profile/facts", json={"source": "cv", "work_history": [
        JOB | {"achievement_ids": [theirs["id"]]}, {"id": their_job["id"], "location": "Taken over", "achievement_ids": []}]})
    assert r.status_code == 200 and len(r.json()["work_history"]) == 1
    assert repo.get_achievement(conn, user_b, theirs["id"])["work_history_id"] is None
    assert repo.get_entry(conn, user_b, "work_history", their_job["id"])["location"] == ""


@pytest.mark.parametrize("body", [
    {"work_history": [JOB]},                                                         # no source
    {"source": "github", "work_history": [JOB]},                                     # facts never come from GitHub
    {"source": "cv", "work_history": [{"job_title": "No employer"}]},
    {"source": "cv", "education": [{"grade": "No institution"}]},
    {"source": "cv", "work_history": [JOB | {"start_month": "2024-01-01", "end_month": "2023-01-01"}]},
    {"source": "cv", "work_history": [JOB] * 21},
    {"source": "cv", "work_history": [JOB | {"achievement_ids": ["not-a-uuid"]}]},
])
def test_facts_validation(client, body):
    assert client.post("/api/profile/facts", json=body).status_code == 422


def test_nothing_is_saved_when_one_fact_is_invalid(client):
    r = client.post("/api/profile/facts", json={"source": "cv", "work_history": [JOB], "skills": ["Python"],
                                                "education": [COURSE | {"start_month": "2024-01-01", "end_month": "2023-01-01"}]})
    assert r.status_code == 422
    s = state(client)
    assert s["work_history"] == [] and s["education"] == [] and s["profile"]["skills"] == []


# ---------- editing an achievement ----------

def test_patch_achievement_changes_only_what_is_sent(client, conn, user_a):
    a = achievement(conn, user_a)
    r = client.patch(f"/api/achievements/{a['id']}", json={"uk_version": "Built X for 55 users", "skills": ["SQL", "Excel"]})
    assert r.status_code == 200
    changed = r.json()
    assert changed["uk_version"] == "Built X for 55 users" and changed["skills"] == ["SQL", "Excel"]
    assert changed["title"] == "Thing one" and changed["raw"] == "did a thing" and changed["source"] == "cv" and changed["needs_number"] is False


@pytest.mark.parametrize("body", [{"raw": "I never said this"}, {"source": "voice"}, {"title": ""}, {"uk_version": "  "}, {"uk_version": None},
                                  {"skills": "SQL"}, {"skills": ["x"] * 21}, {"work_history_id": "not-a-uuid"}])
def test_patch_achievement_validation_and_the_quote_is_read_only(client, conn, user_a, body):
    a = achievement(conn, user_a)
    assert client.patch(f"/api/achievements/{a['id']}", json=body).status_code == 422
    assert repo.get_achievement(conn, user_a, a["id"]) == a


def test_an_achievement_is_linked_to_where_it_happened(client, conn, user_a):
    a = achievement(conn, user_a)
    job, course = client.post("/api/work-history", json=JOB).json(), client.post("/api/education", json=COURSE).json()
    path = f"/api/achievements/{a['id']}"
    assert client.patch(path, json={"work_history_id": job["id"]}).json()["work_history_id"] == job["id"]
    on_course = client.patch(path, json={"education_id": course["id"]}).json()
    assert on_course["education_id"] == course["id"] and on_course["work_history_id"] is None
    assert client.patch(path, json={"education_id": None}).json()["education_id"] is None
    client.patch(path, json={"work_history_id": job["id"]})
    client.delete(f"/api/work-history/{job['id']}")
    assert state(client)["achievements"][0]["work_history_id"] is None   # the job went, the achievement stayed


def test_an_achievement_cannot_be_linked_to_another_users_job(client, conn, user_a, user_b):
    a = achievement(conn, user_a)
    theirs = repo.add_entry(conn, user_b, "work_history", {"employer": "Zzqx Other Ltd"})
    r = client.patch(f"/api/achievements/{a['id']}", json={"work_history_id": theirs["id"]})
    assert r.status_code == 200 and r.json()["work_history_id"] is None


def test_patch_achievement_bad_unknown_and_foreign_ids(client, conn, user_a, user_b, as_user):
    a = achievement(conn, user_a)
    assert client.patch("/api/achievements/not-a-uuid", json={"title": "x"}).status_code == 422
    assert client.patch(f"/api/achievements/{uuid.uuid4()}", json={"title": "x"}).status_code == 404
    as_user(user_b)
    assert client.patch(f"/api/achievements/{a['id']}", json={"title": "Taken over"}).status_code == 404
    assert repo.get_achievement(conn, user_a, a["id"])["title"] == "Thing one"


def test_state_marks_an_achievement_that_needs_a_number(client, conn, user_a):
    achievement(conn, user_a, title="No figure", uk_version="Built a report", outcome="Add a number: how many used it")
    achievement(conn, user_a, title="Has one")
    marks = {a["title"]: a["needs_number"] for a in state(client)["achievements"]}
    assert marks == {"No figure": True, "Has one": False}


# ---------- editing and deleting a story ----------

def story(conn, user):
    return repo.add_story(conn, user, achievement(conn, user)["id"], STORY)


def test_patch_and_delete_story(client, conn, user_a):
    s = story(conn, user_a)
    changed = client.patch(f"/api/stories/{s['id']}", json={"result": "Late deliveries fell by 8%"}).json()
    assert changed["result"] == "Late deliveries fell by 8%" and changed["situation"] == "s" and changed["strength"] == "strong"
    assert client.delete(f"/api/stories/{s['id']}").status_code == 204
    assert state(client)["stories"] == [] and len(state(client)["achievements"]) == 1


@pytest.mark.parametrize("body", [{"title": ""}, {"strength": "strong"}, {"achievement_id": str(uuid.uuid4())}, {"action": "x" * 2001}, {"result": None}])
def test_patch_story_validation(client, conn, user_a, body):
    s = story(conn, user_a)
    assert client.patch(f"/api/stories/{s['id']}", json=body).status_code == 422
    assert repo.get_story(conn, user_a, s["id"]) == s


def test_story_bad_unknown_and_foreign_ids(client, conn, user_a, user_b, as_user):
    s = story(conn, user_a)
    assert client.patch("/api/stories/not-a-uuid", json={"title": "x"}).status_code == 422
    assert client.delete("/api/stories/not-a-uuid").status_code == 422
    assert client.patch(f"/api/stories/{uuid.uuid4()}", json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/stories/{uuid.uuid4()}").status_code == 404
    as_user(user_b)
    assert client.patch(f"/api/stories/{s['id']}", json={"title": "Taken over"}).status_code == 404
    assert client.delete(f"/api/stories/{s['id']}").status_code == 404
    assert repo.get_story(conn, user_a, s["id"]) == s
