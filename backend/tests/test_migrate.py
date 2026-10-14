from datetime import date, datetime, timezone

import psycopg
import pytest

import migrate

pytestmark = pytest.mark.db

TABLES = ("profiles", "achievements", "role_families", "saved_jobs", "cv_versions", "stories",
          "applications", "journal_entries", "usage_events", "schema_migrations",
          "job_listings", "job_searches", "job_search_results", "sponsors", "reference_meta", "job_matches",
          "work_history", "education", "application_events", "weekly_goals", "companies", "prep_packs",
          "contacts", "outreach_events", "networking_events")


def test_apply_all_is_idempotent(conn):
    migrate.apply_all(conn)
    assert migrate.pending(conn) == []
    assert migrate.apply_all(conn) == []


def test_all_tables_exist_with_rls(conn):
    rows = conn.execute(
        "select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind = 'r' and c.relname = any(%s)", (list(TABLES),)).fetchall()
    assert {r["relname"]: r["relrowsecurity"] for r in rows} == {t: True for t in TABLES}


def test_no_policies_exist(conn):
    assert conn.execute("select count(*) as n from pg_policies where schemaname = 'public'").fetchone()["n"] == 0


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_have_no_privileges(conn, role):
    for table in TABLES:
        for privilege in ("select", "insert", "update", "delete"):
            allowed = conn.execute("select has_table_privilege(%s, %s, %s) as ok",
                                   (role, f"public.{table}", privilege)).fetchone()["ok"]
            assert not allowed, f"{role} can {privilege} {table}"


def test_cascade_on_user_delete(conn, user_a):
    conn.execute("insert into profiles (user_id, full_name) values (%s, 'Test Person')", (user_a,))
    conn.execute("insert into achievements (user_id, title, uk_version, source) values (%s, 'T', 'Did X', 'paste')", (user_a,))
    conn.execute("delete from auth.users where id = %s", (user_a,))
    assert conn.execute("select count(*) as n from profiles where user_id = %s", (user_a,)).fetchone()["n"] == 0
    assert conn.execute("select count(*) as n from achievements where user_id = %s", (user_a,)).fetchone()["n"] == 0


def test_posted_after_applied_rejected(conn, user_a):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("insert into applications (user_id, company, role, source, applied_on, posted_on) "
                     "values (%s, 'Company A', 'Role A', 'Other', %s, %s)", (user_a, date(2026, 10, 1), date(2026, 10, 10)))


def test_applied_on_defaults_to_today_in_london(conn, user_a):
    row = conn.execute("insert into applications (user_id, company, role, source) values (%s, 'Company A', 'Role A', 'Other') "
                       "returning applied_on, (now() at time zone 'Europe/London')::date as london_today", (user_a,)).fetchone()
    assert row["applied_on"] == row["london_today"]


def test_family_names_unique_per_user_ignoring_case(conn, user_a, user_b):
    insert = "insert into role_families (user_id, name, fit, overlap) values (%s, %s, 'direct', 80)"
    conn.execute(insert, (user_a, "Data Analyst"))
    conn.execute(insert, (user_b, "Data Analyst"))  # another user may use the same name
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (user_a, "data analyst"))


# ---------- 003_jobs: shared listings, per-user matches ----------

def _listing(conn, source_id="t-1"):
    """A listing that cannot collide with a real one: its source is 'test'."""
    return conn.execute(
        "insert into job_listings (source, source_id, title, employer, posted_by, url, posted_on) "
        "values ('test', %s, 'Role A', 'Zzqx Holdings Ltd', 'employer', 'https://example.test/1', current_date) returning id",
        (source_id,)).fetchone()["id"]


def _count(conn, table, column, value):
    return conn.execute(f"select count(*) as n from {table} where {column} = %s", (value,)).fetchone()["n"]


def test_job_match_deleted_with_user_but_listing_stays(conn, user_a):
    listing = _listing(conn)
    conn.execute("insert into job_matches (user_id, listing_id) values (%s, %s)", (user_a, listing))
    conn.execute("delete from auth.users where id = %s", (user_a,))
    assert _count(conn, "job_matches", "listing_id", listing) == 0
    assert _count(conn, "job_listings", "id", listing) == 1


def test_matches_and_search_links_deleted_with_listing_but_saved_job_stays(conn, user_a):
    listing = _listing(conn)
    conn.execute("insert into job_matches (user_id, listing_id) values (%s, %s)", (user_a, listing))
    search = conn.execute("insert into job_searches (source, query, location) values ('test', 'zzqx role', 'zzqx town') returning id").fetchone()["id"]
    conn.execute("insert into job_search_results (search_id, listing_id) values (%s, %s)", (search, listing))
    saved = conn.execute(
        "insert into saved_jobs (user_id, title, company, description, source, listing_id, posted_on) "
        "values (%s, 'Role A', 'Zzqx Holdings Ltd', 'd', 'reed', %s, current_date) returning id", (user_a, listing)).fetchone()["id"]
    conn.execute("delete from job_listings where id = %s", (listing,))
    assert _count(conn, "job_matches", "listing_id", listing) == 0
    assert _count(conn, "job_search_results", "search_id", search) == 0
    row = conn.execute("select listing_id, posted_on from saved_jobs where id = %s", (saved,)).fetchone()
    assert row["listing_id"] is None and row["posted_on"] is not None


def test_listing_unique_per_source(conn):
    _listing(conn, "t-dup")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _listing(conn, "t-dup")


def test_one_match_per_user_per_listing(conn, user_a, user_b):
    listing = _listing(conn)
    insert = "insert into job_matches (user_id, listing_id) values (%s, %s)"
    conn.execute(insert, (user_a, listing))
    conn.execute(insert, (user_b, listing))  # another user may match the same listing
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (user_a, listing))


@pytest.mark.parametrize("column, value", [("fit_label", "perfect"), ("status", "gone"), ("fit_percent", 101)])
def test_match_values_are_checked(conn, user_a, column, value):
    listing = _listing(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(f"insert into job_matches (user_id, listing_id, {column}) values (%s, %s, %s)", (user_a, listing, value))


def test_match_defaults(conn, user_a):
    listing = _listing(conn)
    row = conn.execute("insert into job_matches (user_id, listing_id) values (%s, %s) returning *", (user_a, listing)).fetchone()
    assert row["status"] == "new" and row["fit_percent"] is None and row["scored_at"] is None
    assert row["shown"] == [] and row["gaps"] == []


def test_profile_hides_senior_roles_by_default(conn, user_a):
    row = conn.execute("insert into profiles (user_id, full_name) values (%s, 'Test Person') returning include_senior", (user_a,)).fetchone()
    assert row["include_senior"] is False


def test_a_listing_can_be_a_training_programme_and_nothing_else_new(conn):
    insert = ("insert into job_listings (source, source_id, title, employer, posted_by, url, posted_on) "
              "values ('test', %s, 'Role A', 'Zzqx Training', %s, 'https://example.test/1', current_date)")
    conn.execute(insert, ("t-training", "training"))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(insert, ("t-other", "charity"))


# ---------- 005_profile_depth: work history, education, skills, achievement links ----------

def _job(conn, user, **kw):
    fields = {"employer": "Zzqx Holdings Ltd"} | kw
    return conn.execute(f"insert into work_history (user_id, {', '.join(fields)}) values (%s, {', '.join(['%s'] * len(fields))}) returning id",
                        (user, *fields.values())).fetchone()["id"]


def _course(conn, user, **kw):
    fields = {"institution": "University of Zzqx"} | kw
    return conn.execute(f"insert into education (user_id, {', '.join(fields)}) values (%s, {', '.join(['%s'] * len(fields))}) returning id",
                        (user, *fields.values())).fetchone()["id"]


def test_history_and_education_deleted_with_user(conn, user_a):
    job, course = _job(conn, user_a), _course(conn, user_a)
    conn.execute("delete from auth.users where id = %s", (user_a,))
    assert _count(conn, "work_history", "id", job) == 0
    assert _count(conn, "education", "id", course) == 0


def test_deleting_a_job_or_course_keeps_the_achievement_and_clears_the_link(conn, user_a):
    job, course = _job(conn, user_a), _course(conn, user_a)
    insert = "insert into achievements (user_id, title, uk_version, source, {}) values (%s, 'T', 'Did X', 'cv', %s) returning id"
    at_work = conn.execute(insert.format("work_history_id"), (user_a, job)).fetchone()["id"]
    on_course = conn.execute(insert.format("education_id"), (user_a, course)).fetchone()["id"]
    conn.execute("delete from work_history where id = %s", (job,))
    conn.execute("delete from education where id = %s", (course,))
    rows = conn.execute("select work_history_id, education_id from achievements where id = any(%s)", ([at_work, on_course],)).fetchall()
    assert len(rows) == 2 and all(r["work_history_id"] is None and r["education_id"] is None for r in rows)


@pytest.mark.parametrize("make", [_job, _course])
def test_end_before_start_rejected(conn, user_a, make):
    make(conn, user_a, start_month=date(2023, 7, 1), end_month=date(2023, 7, 1))  # the same month is fine
    with pytest.raises(psycopg.errors.CheckViolation):
        make(conn, user_a, start_month=date(2023, 7, 1), end_month=date(2023, 6, 1))


def test_current_job_cannot_have_an_end_month(conn, user_a):
    _job(conn, user_a, is_current=True)
    with pytest.raises(psycopg.errors.CheckViolation):
        _job(conn, user_a, is_current=True, end_month=date(2025, 8, 1))


def test_one_current_course_per_user(conn, user_a, user_b):
    _course(conn, user_a, from_details=True)
    _course(conn, user_a)                      # any number of other courses
    _course(conn, user_b, from_details=True)   # another user has their own
    with pytest.raises(psycopg.errors.UniqueViolation):
        _course(conn, user_a, from_details=True)


@pytest.mark.parametrize("source, accepted", [("cv", True), ("github", True), ("voice", True), ("paste", True), ("linkedin", False)])
def test_achievement_sources(conn, user_a, source, accepted):
    insert = "insert into achievements (user_id, title, uk_version, source) values (%s, 'T', 'Did X', %s)"
    if accepted:
        conn.execute(insert, (user_a, source))
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(insert, (user_a, source))


def test_entry_source_is_checked(conn, user_a):
    _job(conn, user_a, source="cv")
    with pytest.raises(psycopg.errors.CheckViolation):
        _job(conn, user_a, source="linkedin")


def test_journal_import_type(conn, user_a):
    insert = "insert into journal_entries (user_id, type, title) values (%s, %s, 'T')"
    conn.execute(insert, (user_a, "import"))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(insert, (user_a, "other"))


def test_profile_starts_with_no_skills_languages_or_github(conn, user_a):
    row = conn.execute("insert into profiles (user_id, full_name) values (%s, 'Test Person') returning skills, languages, github_username",
                       (user_a,)).fetchone()
    assert row["skills"] == [] and row["languages"] == [] and row["github_username"] is None


def test_entry_defaults(conn, user_a):
    job = conn.execute("select * from work_history where id = %s", (_job(conn, user_a),)).fetchone()
    assert job["is_current"] is False and job["source"] == "manual" and job["start_month"] is None and job["employer_context"] == ""
    course = conn.execute("select * from education where id = %s", (_course(conn, user_a),)).fetchone()
    assert course["from_details"] is False and course["source"] == "manual" and course["grade"] == ""


# ---------- 006_full_cv: contact details, and what kind of CV a version is ----------

def test_profile_cv_defaults(conn, user_a):
    row = conn.execute("insert into profiles (user_id, full_name) values (%s, 'Test Person') returning phone, city, linkedin_url, additional",
                       (user_a,)).fetchone()
    assert (row["phone"], row["city"], row["linkedin_url"], row["additional"]) == ("", "", "", [])


def _version(conn, user, **kw):
    fields = {"name": "Role A, Zzqx Holdings Ltd v1", "content": "{}"} | kw
    return conn.execute(f"insert into cv_versions (user_id, {', '.join(fields)}) values (%s, {', '.join(['%s'] * len(fields))}) returning *",
                        (user, *fields.values())).fetchone()


def test_cv_version_defaults(conn, user_a):
    row = _version(conn, user_a)  # as a version made before this step was stored
    assert (row["kind"], row["format_version"], row["pages"], row["edited_at"], row["contact_name"]) == ("tailored", 1, None, None, "")


@pytest.mark.parametrize("column, value", [("kind", "other"), ("format_version", 3)])
def test_cv_kind_and_format_checked(conn, user_a, column, value):
    _version(conn, user_a, kind="base", format_version=2)
    with pytest.raises(psycopg.errors.CheckViolation):
        _version(conn, user_a, **{column: value})


# ---------- 007_tracker_habits: stage history, weekly goals, rejection answers ----------

def _application(conn, user, **kw):
    fields = {"company": "Zzqx Holdings Ltd", "role": "Role A", "source": "Other"} | kw
    return conn.execute(f"insert into applications (user_id, {', '.join(fields)}) values (%s, {', '.join(['%s'] * len(fields))}) returning *",
                        (user, *fields.values())).fetchone()


def _event(conn, user, application_id, to_stage="applied"):
    conn.execute("insert into application_events (user_id, application_id, to_stage) values (%s, %s, %s)", (user, application_id, to_stage))


def _goal(conn, user, effective_from=date(2026, 10, 12), applications=5, practice=2):
    conn.execute("insert into weekly_goals (user_id, effective_from, applications, practice) values (%s, %s, %s, %s)",
                 (user, effective_from, applications, practice))


def test_new_tables_cascade_on_user_delete(conn, user_a):
    application = _application(conn, user_a)["id"]
    _event(conn, user_a, application)
    _goal(conn, user_a)
    conn.execute("delete from auth.users where id = %s", (user_a,))
    assert _count(conn, "application_events", "user_id", user_a) == 0
    assert _count(conn, "weekly_goals", "user_id", user_a) == 0


def test_events_deleted_with_their_application(conn, user_a):
    application = _application(conn, user_a)["id"]
    _event(conn, user_a, application)
    _event(conn, user_a, application, "screening")
    conn.execute("delete from applications where id = %s", (application,))
    assert _count(conn, "application_events", "application_id", application) == 0


def test_goal_must_start_on_a_monday(conn, user_a):
    _goal(conn, user_a, effective_from=date(2026, 10, 12))  # a Monday
    with pytest.raises(psycopg.errors.CheckViolation):
        _goal(conn, user_a, effective_from=date(2026, 10, 13))


@pytest.mark.parametrize("applications, practice", [(0, 2), (31, 2), (5, -1), (5, 15)])
def test_goal_bounds(conn, user_a, applications, practice):
    _goal(conn, user_a, applications=1, practice=0)  # the smallest goal allowed
    with pytest.raises(psycopg.errors.CheckViolation):
        _goal(conn, user_a, effective_from=date(2026, 10, 19), applications=applications, practice=practice)


def test_rejected_at_stage_checked(conn, user_a):
    for stage in ("cv", "screening", "interview", "final"):
        _application(conn, user_a, stage="rejected", rejected_at_stage=stage)
    with pytest.raises(psycopg.errors.CheckViolation):
        _application(conn, user_a, stage="rejected", rejected_at_stage="offer")


def test_new_application_columns_start_empty(conn, user_a):
    row = _application(conn, user_a)
    assert (row["contact_name"], row["rejected_at_stage"], row["feedback_received"], row["lesson"], row["last_followed_up_on"]) == (None,) * 5


def test_milestones_seen_defaults_to_empty(conn, user_a):
    row = conn.execute("insert into profiles (user_id, full_name) values (%s, 'Test Person') returning milestones_seen", (user_a,)).fetchone()
    assert row["milestones_seen"] == []


# ---------- step 5: interview prep ----------

def _saved_job(conn, user):
    return conn.execute("insert into saved_jobs (user_id, title, company, description) values (%s, 'Role A', 'Zzqx Holdings Ltd', 'd') "
                        "returning id", (user,)).fetchone()["id"]


def _pack(conn, user, **kw):
    fields = {"role": "Role A", "company": "Zzqx Holdings Ltd", "content": "{}"} | kw
    return conn.execute(f"insert into prep_packs (user_id, {', '.join(fields)}) values (%s, {', '.join(['%s'] * len(fields))}) returning *",
                        (user, *fields.values())).fetchone()


def _story(conn, user, **kw):
    fields = {"title": "Story A"} | kw
    return conn.execute(f"insert into stories (user_id, {', '.join(fields)}) values (%s, {', '.join(['%s'] * len(fields))}) returning *",
                        (user, *fields.values())).fetchone()


def test_packs_cascade_on_user_delete(conn, user_a):
    _pack(conn, user_a, saved_job_id=_saved_job(conn, user_a))
    conn.execute("delete from auth.users where id = %s", (user_a,))
    assert conn.execute("select count(*) as n from prep_packs where user_id = %s", (user_a,)).fetchone()["n"] == 0


def test_pack_survives_its_job_being_deleted(conn, user_a):
    job = _saved_job(conn, user_a)
    pack = _pack(conn, user_a, saved_job_id=job)["id"]
    conn.execute("delete from saved_jobs where id = %s", (job,))
    assert conn.execute("select saved_job_id from prep_packs where id = %s", (pack,)).fetchone()["saved_job_id"] is None


def test_one_pack_per_saved_job(conn, user_a):
    job = _saved_job(conn, user_a)
    _pack(conn, user_a, saved_job_id=job)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _pack(conn, user_a, saved_job_id=job)


def test_one_pack_per_application_without_a_saved_job(conn, user_a):
    application = _application(conn, user_a)["id"]
    _pack(conn, user_a, application_id=application)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _pack(conn, user_a, application_id=application)


def test_story_competencies_checked(conn, user_a):
    assert _story(conn, user_a)["competencies"] == []
    assert _story(conn, user_a, competencies=["teamwork", "setback"])["competencies"] == ["teamwork", "setback"]
    with pytest.raises(psycopg.errors.CheckViolation):
        _story(conn, user_a, competencies=["cooking"])


def test_research_is_a_usage_kind(conn, user_a):
    conn.execute("insert into usage_events (user_id, kind, action) values (%s, 'research', 'research x')", (user_a,))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("insert into usage_events (user_id, kind, action) values (%s, 'other', 'x')", (user_a,))


def _backfill_statement() -> str:
    sql = (migrate.MIGRATIONS / "008_interview_prep.sql").read_text(encoding="utf-8")
    start = sql.index("update stories")
    return sql[start:sql.index(";", start)]


def test_backfill_maps_exact_labels(conn, user_a):
    tagged = _story(conn, user_a, competency="Teamwork")["id"]
    spaced = _story(conn, user_a, competency=" handling a setback ")["id"]
    hyphen = _story(conn, user_a, competency="Problem-solving")["id"]
    conn.execute(_backfill_statement())
    got = {r["id"]: r["competencies"] for r in conn.execute("select id, competencies from stories where user_id = %s", (user_a,))}
    assert got == {tagged: ["teamwork"], spaced: ["setback"], hyphen: []}


# ---------- 009_networking: contacts, their pipeline, saved events, the outreach target ----------

def _insert(conn, table, user, fields):
    return conn.execute(f"insert into {table} (user_id, {', '.join(fields)}) values (%s, {', '.join(['%s'] * len(fields))}) returning *",
                        (user, *fields.values())).fetchone()


def _contact(conn, user, **kw):
    return _insert(conn, "contacts", user, {"name": "Zzqx Person", "relationship": "none"} | kw)


def _sent(conn, user, contact_id, **kw):
    return _insert(conn, "outreach_events", user, {"contact_id": contact_id, "kind": "sent", "message_type": "chat_request"} | kw)


def _networking_event(conn, user, **kw):
    fields = {"name": "Zzqx Data Meetup", "starts_at": datetime(2026, 10, 20, 17, 30, tzinfo=timezone.utc), "type": "meetup"} | kw
    return _insert(conn, "networking_events", user, fields)


def test_networking_tables_cascade_on_user_delete(conn, user_a):
    event = _networking_event(conn, user_a)["id"]
    contact = _contact(conn, user_a, event_id=event)["id"]
    _sent(conn, user_a, contact)
    conn.execute("delete from auth.users where id = %s", (user_a,))
    for table in ("contacts", "outreach_events", "networking_events"):
        assert _count(conn, table, "user_id", user_a) == 0


def test_deleting_a_contact_keeps_the_application_and_the_messages_sent(conn, user_a):
    contact = _contact(conn, user_a)["id"]
    application = _application(conn, user_a, contact_id=contact)["id"]
    message = _sent(conn, user_a, contact)["id"]
    conn.execute("delete from contacts where id = %s", (contact,))
    assert conn.execute("select contact_id from applications where id = %s", (application,)).fetchone()["contact_id"] is None
    kept = conn.execute("select contact_id, kind from outreach_events where id = %s", (message,)).fetchone()
    assert kept == {"contact_id": None, "kind": "sent"}


def test_deleting_an_event_keeps_its_contacts(conn, user_a):
    event = _networking_event(conn, user_a)["id"]
    contact = _contact(conn, user_a, relationship="event", event_id=event)["id"]
    conn.execute("delete from networking_events where id = %s", (event,))
    assert conn.execute("select event_id from contacts where id = %s", (contact,)).fetchone()["event_id"] is None


@pytest.mark.parametrize("make, value", [
    (lambda c, u, v: _contact(c, u, relationship=v), "friend"),
    (lambda c, u, v: _contact(c, u, status=v), "ghosted"),
    (lambda c, u, v: _sent(c, u, _contact(c, u)["id"], kind=v), "liked"),
    (lambda c, u, v: _sent(c, u, _contact(c, u)["id"], message_type=v), "poem"),
    (lambda c, u, v: _networking_event(c, u, type=v), "party"),
    (lambda c, u, v: _networking_event(c, u, status=v), "maybe"),
])
def test_networking_values_are_checked(conn, user_a, make, value):
    with pytest.raises(psycopg.errors.CheckViolation):
        make(conn, user_a, value)


def test_a_message_type_only_with_a_message_sent(conn, user_a):
    contact = _contact(conn, user_a)["id"]
    with pytest.raises(psycopg.errors.CheckViolation):
        _sent(conn, user_a, contact, message_type=None)


def test_a_reply_has_no_message_type(conn, user_a):
    contact = _contact(conn, user_a)["id"]
    with pytest.raises(psycopg.errors.CheckViolation):
        _sent(conn, user_a, contact, kind="replied", message_type="chat_request")


def test_the_same_message_marked_sent_twice_on_one_day_is_one_row(conn, user_a):
    contact = _contact(conn, user_a)["id"]
    _sent(conn, user_a, contact)
    _sent(conn, user_a, contact, message_type="follow_up")  # another type the same day is another message
    with pytest.raises(psycopg.errors.UniqueViolation):
        _sent(conn, user_a, contact)


def test_networking_defaults(conn, user_a):
    contact = _contact(conn, user_a)
    assert (contact["status"], contact["role"], contact["company"], contact["notes"], contact["event_id"]) == ("to_contact", "", "", "", None)
    event = _networking_event(conn, user_a)
    assert (event["status"], event["online"], event["prep"]) == ("interested", False, None)
    assert _application(conn, user_a)["contact_id"] is None


@pytest.mark.parametrize("outreach, ok", [(None, True), (0, True), (20, True), (21, False), (-1, False)])
def test_outreach_target_bounds(conn, user_a, outreach, ok):
    insert = lambda: conn.execute("insert into weekly_goals (user_id, effective_from, applications, practice, outreach) "
                                  "values (%s, '2026-10-12', 5, 2, %s)", (user_a, outreach))
    if ok:
        insert()
    else:
        with pytest.raises(psycopg.errors.CheckViolation):
            insert()


def test_a_new_profile_has_an_outreach_target_of_two_and_no_events_page(conn, user_a):
    row = conn.execute("insert into profiles (user_id, full_name) values (%s, 'Test Person') returning *", (user_a,)).fetchone()
    assert (row["outreach_default"], row["university_events_url"]) == (2, None)


def _outreach_default_statements() -> list[str]:
    sql = (migrate.MIGRATIONS / "009_networking.sql").read_text(encoding="utf-8")
    return [s for s in sql.split(";") if "outreach_default" in s]


def test_accounts_that_exist_at_the_migration_get_no_outreach_target_and_later_ones_two(conn):
    statements = _outreach_default_statements()
    assert len(statements) == 2
    conn.execute("create temp table zzqx_profiles (user_id int)")
    conn.execute("insert into zzqx_profiles values (1)")
    for statement in statements:
        conn.execute(statement.replace("alter table profiles", "alter table zzqx_profiles"))
    conn.execute("insert into zzqx_profiles values (2)")
    rows = conn.execute("select outreach_default from zzqx_profiles order by user_id").fetchall()
    assert [r["outreach_default"] for r in rows] == [0, 2]
