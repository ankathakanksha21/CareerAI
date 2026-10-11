from datetime import date

import psycopg
import pytest

import migrate

pytestmark = pytest.mark.db

TABLES = ("profiles", "achievements", "role_families", "saved_jobs", "cv_versions", "stories",
          "applications", "journal_entries", "usage_events", "schema_migrations")


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
