from datetime import date

import pytest

import repo

pytestmark = pytest.mark.db

JOB = dict(employer="Zzqx Holdings Ltd", job_title="Systems Engineer", location="Pune", country="India",
           start_month=date(2023, 7, 14), end_month=date(2025, 8, 20), is_current=False, employer_context="IT services for retailers")
COURSE = dict(institution="University of Zzqx", qualification="BTech", subject="Computer Science",
              start_month=date(2019, 7, 1), end_month=date(2023, 5, 31), grade="8.4/10", country="India")
DETAILS = dict(full_name="Test Person", university="Zzqx City University", course="MSc Course A",
               graduation_date=date(2026, 9, 17), visa_type="student", visa_end_date=date(2027, 1, 31), locations=["London"])
TABLES = [("work_history", JOB, "employer"), ("education", COURSE, "institution")]


# ---------- adding and listing ----------

@pytest.mark.parametrize("table, fields, name", TABLES)
def test_add_entry_keeps_every_field_and_starts_months_on_the_first(conn, user_a, table, fields, name):
    row = repo.add_entry(conn, user_a, table, fields)
    assert isinstance(row["id"], str) and row["user_id"] == user_a and row["source"] == "manual"
    assert row["start_month"].day == 1 and row["end_month"].day == 1
    assert {k: row[k] for k in fields if not k.endswith("_month")} == {k: v for k, v in fields.items() if not k.endswith("_month")}
    assert repo.get_entry(conn, user_a, table, row["id"]) == row
    assert repo.list_entries(conn, user_a, table) == [row]


def test_add_entry_records_where_it_came_from(conn, user_a):
    assert repo.add_entry(conn, user_a, "work_history", JOB, "cv")["source"] == "cv"


def test_a_missing_text_field_is_stored_empty(conn, user_a):
    row = repo.add_entry(conn, user_a, "work_history", {"employer": "Zzqx Holdings Ltd", "job_title": None, "start_month": None})
    assert row["job_title"] == "" and row["location"] == "" and row["start_month"] is None and row["is_current"] is False


def test_work_history_lists_the_current_job_first_then_the_latest(conn, user_a):
    old = repo.add_entry(conn, user_a, "work_history", JOB | {"employer": "Zzqx Old Ltd", "start_month": date(2019, 1, 1), "end_month": date(2020, 1, 1)})
    recent = repo.add_entry(conn, user_a, "work_history", JOB)
    undated = repo.add_entry(conn, user_a, "work_history", {"employer": "Zzqx Undated Ltd"})
    current = repo.add_entry(conn, user_a, "work_history", {"employer": "Zzqx Now Ltd", "start_month": date(2018, 1, 1), "is_current": True})
    assert [r["id"] for r in repo.list_entries(conn, user_a, "work_history")] == [current["id"], recent["id"], old["id"], undated["id"]]


def test_education_lists_the_current_course_first(conn, user_a):
    later = repo.add_entry(conn, user_a, "education", COURSE | {"end_month": date(2030, 1, 1)})
    repo.update_profile(conn, user_a, **DETAILS)
    listed = repo.list_entries(conn, user_a, "education")
    assert listed[0]["from_details"] is True and listed[1]["id"] == later["id"]


# ---------- changing ----------

@pytest.mark.parametrize("table, fields, name", TABLES)
def test_update_entry_changes_only_the_fields_given(conn, user_a, table, fields, name):
    row = repo.add_entry(conn, user_a, table, fields)
    changed = repo.update_entry(conn, user_a, table, row["id"], {name: "Zzqx Renamed", "start_month": date(2020, 2, 9)})
    assert changed[name] == "Zzqx Renamed" and changed["start_month"] == date(2020, 2, 1)
    assert changed["end_month"] == row["end_month"] and changed["country"] == row["country"]


def test_update_entry_can_clear_a_month(conn, user_a):
    row = repo.add_entry(conn, user_a, "work_history", JOB)
    changed = repo.update_entry(conn, user_a, "work_history", row["id"], {"end_month": None, "is_current": True})
    assert changed["end_month"] is None and changed["is_current"] is True


def test_fill_entry_fills_blanks_and_never_overwrites(conn, user_a):
    row = repo.add_entry(conn, user_a, "education", {"institution": "University of Zzqx", "qualification": "MSc Course A", "end_month": date(2026, 9, 1)})
    filled = repo.fill_entry(conn, user_a, "education", row["id"],
                             {"qualification": "Something else", "grade": "Merit", "start_month": date(2025, 9, 20), "end_month": date(2027, 1, 1)})
    assert filled["qualification"] == "MSc Course A" and filled["end_month"] == date(2026, 9, 1)
    assert filled["grade"] == "Merit" and filled["start_month"] == date(2025, 9, 1)


def test_fill_entry_leaves_out_a_month_that_would_put_the_end_before_the_start(conn, user_a):
    row = repo.add_entry(conn, user_a, "education", {"institution": "University of Zzqx", "end_month": date(2026, 9, 1)})
    filled = repo.fill_entry(conn, user_a, "education", row["id"], {"start_month": date(2027, 1, 1), "grade": "Merit"})
    assert filled["start_month"] is None and filled["grade"] == "Merit"


def test_fill_entry_does_not_end_a_current_job(conn, user_a):
    row = repo.add_entry(conn, user_a, "work_history", {"employer": "Zzqx Holdings Ltd", "is_current": True})
    filled = repo.fill_entry(conn, user_a, "work_history", row["id"], {"end_month": date(2025, 8, 1), "location": "Pune"})
    assert filled["is_current"] is True and filled["end_month"] is None and filled["location"] == "Pune"


def test_fill_entry_does_not_reopen_a_job_that_has_ended(conn, user_a):
    row = repo.add_entry(conn, user_a, "work_history", JOB | {"location": ""})   # ended in August 2025
    filled = repo.fill_entry(conn, user_a, "work_history", row["id"], {"is_current": True, "location": "Pune"})
    assert filled["is_current"] is False and filled["end_month"] == date(2025, 8, 1) and filled["location"] == "Pune"


@pytest.mark.parametrize("table, fields, name", TABLES)
def test_delete_entry(conn, user_a, table, fields, name):
    row = repo.add_entry(conn, user_a, table, fields)
    assert repo.delete_entry(conn, user_a, table, row["id"]) is True
    assert repo.delete_entry(conn, user_a, table, row["id"]) is False
    assert repo.list_entries(conn, user_a, table) == []


# ---------- one user's entries are invisible to another ----------

@pytest.mark.parametrize("table, fields, name", TABLES)
def test_another_user_sees_and_changes_nothing(conn, user_a, user_b, table, fields, name):
    row = repo.add_entry(conn, user_a, table, fields)
    assert repo.list_entries(conn, user_b, table) == []
    assert repo.get_entry(conn, user_b, table, row["id"]) is None
    assert repo.update_entry(conn, user_b, table, row["id"], {name: "Taken over"}) is None
    assert repo.fill_entry(conn, user_b, table, row["id"], {"country": "Elsewhere"}) is None
    assert repo.delete_entry(conn, user_b, table, row["id"]) is False
    assert repo.get_entry(conn, user_a, table, row["id"]) == row


# ---------- only the two tables, only their fields ----------

def test_unknown_table_is_refused(conn, user_a):
    for call in (lambda: repo.list_entries(conn, user_a, "profiles"),
                 lambda: repo.add_entry(conn, user_a, "profiles", {"employer": "x"}),
                 lambda: repo.delete_entry(conn, user_a, "achievements", "00000000-0000-0000-0000-000000000000")):
        with pytest.raises(ValueError):
            call()


@pytest.mark.parametrize("table, fields, name", TABLES)
def test_unknown_field_is_refused(conn, user_a, table, fields, name):
    with pytest.raises(ValueError):
        repo.add_entry(conn, user_a, table, fields | {"user_id": "someone"})
    row = repo.add_entry(conn, user_a, table, fields)
    with pytest.raises(ValueError):
        repo.update_entry(conn, user_a, table, row["id"], {"from_details": True})


# ---------- the current course follows "Your details" ----------

def test_saving_details_creates_the_current_course_once(conn, user_a):
    repo.update_profile(conn, user_a, **DETAILS)
    repo.update_profile(conn, user_a, **DETAILS | {"course": "MSc Course B", "graduation_date": date(2027, 1, 20)})
    courses = repo.list_entries(conn, user_a, "education")
    assert len(courses) == 1
    assert courses[0] | {"id": 0, "created_at": 0, "updated_at": 0} == {
        "id": 0, "user_id": user_a, "institution": "Zzqx City University", "qualification": "MSc Course B", "subject": "",
        "start_month": None, "end_month": date(2027, 1, 1), "grade": "", "country": "United Kingdom",
        "from_details": True, "source": "manual", "created_at": 0, "updated_at": 0}


def test_saving_details_keeps_what_was_added_to_the_current_course(conn, user_a):
    repo.update_profile(conn, user_a, **DETAILS)
    course = repo.list_entries(conn, user_a, "education")[0]
    repo.update_entry(conn, user_a, "education", course["id"], {"grade": "Merit", "start_month": date(2025, 9, 1)})
    repo.update_profile(conn, user_a, **DETAILS | {"university": "Zzqx Renamed University"})
    after = repo.list_entries(conn, user_a, "education")[0]
    assert after["institution"] == "Zzqx Renamed University" and after["grade"] == "Merit" and after["start_month"] == date(2025, 9, 1)


def test_a_graduation_moved_before_the_start_month_clears_the_start(conn, user_a):
    repo.update_profile(conn, user_a, **DETAILS)
    course = repo.list_entries(conn, user_a, "education")[0]
    repo.update_entry(conn, user_a, "education", course["id"], {"start_month": date(2025, 9, 1)})
    repo.update_profile(conn, user_a, **DETAILS | {"graduation_date": date(2024, 6, 1)})
    after = repo.list_entries(conn, user_a, "education")[0]
    assert after["end_month"] == date(2024, 6, 1) and after["start_month"] is None


# ---------- skills, languages, GitHub ----------

def test_set_skills_replaces_and_tidies(conn, user_a):
    repo.get_or_create_profile(conn, user_a, "Test Person")
    repo.set_skills(conn, user_a, ["SQL"], [{"language": "Hindi", "level": "Native"}])
    p = repo.set_skills(conn, user_a, [" Python ", "python", "", "Power BI"],
                        [{"language": " English ", "level": "Fluent"}, {"language": "english", "level": "Basic"}, {"language": "", "level": "Fluent"}])
    assert p["skills"] == ["Python", "Power BI"]
    assert p["languages"] == [{"language": "English", "level": "Fluent"}]
    assert p["first_name"] == "Test"


def test_set_skills_works_before_the_profile_exists(conn, user_a):
    assert repo.set_skills(conn, user_a, ["SQL"], [])["skills"] == ["SQL"]


def test_add_skills_keeps_what_is_there_and_skips_repeats(conn, user_a):
    repo.set_skills(conn, user_a, ["SQL", "Excel"], [{"language": "Hindi", "level": "Native"}])
    p = repo.add_skills(conn, user_a, ["sql", "Python"], [{"language": "hindi", "level": "Basic"}, {"language": "Telugu", "level": ""}])
    assert p["skills"] == ["SQL", "Excel", "Python"]
    assert p["languages"] == [{"language": "Hindi", "level": "Native"}, {"language": "Telugu", "level": ""}]


def test_skills_are_private(conn, user_a, user_b):
    repo.set_skills(conn, user_a, ["SQL"], [])
    assert repo.get_or_create_profile(conn, user_b, "Other Person")["skills"] == []


def test_github_username_saved(conn, user_a, user_b):
    repo.get_or_create_profile(conn, user_a, "Test Person")
    repo.get_or_create_profile(conn, user_b, "Other Person")
    repo.set_github_username(conn, user_a, "zzqx-sample")
    assert repo.get_or_create_profile(conn, user_a, "x")["github_username"] == "zzqx-sample"
    assert repo.get_or_create_profile(conn, user_b, "x")["github_username"] is None


def test_state_carries_work_history_and_education(conn, user_a, user_b):
    job = repo.add_entry(conn, user_a, "work_history", JOB)
    course = repo.add_entry(conn, user_a, "education", COURSE)
    state = repo.load_state(conn, user_a)
    assert state["work_history"] == [job] and state["education"] == [course]
    other = repo.load_state(conn, user_b)
    assert other["work_history"] == [] and other["education"] == []
