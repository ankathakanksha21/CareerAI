from datetime import date

import psycopg
import pytest

import migrate

pytestmark = pytest.mark.db

TABLES = ("profiles", "achievements", "role_families", "saved_jobs", "cv_versions", "stories",
          "applications", "journal_entries", "usage_events", "schema_migrations",
          "job_listings", "job_searches", "job_search_results", "sponsors", "reference_meta", "job_matches")


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
