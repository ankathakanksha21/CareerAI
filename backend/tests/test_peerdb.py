"""Buddy groups in the database: peer_view, the one function that shows one user anything about
another; switching Peers on and off; matching, proposals, expiry and leaving; check-ins, nudges,
contact links, blocks and reports.

The names cannot be real. Real accounts may be waiting in the real database, so a pair a test
expects to be matched shares a city no real user has, and no test asserts that someone stays
waiting after matching runs unless it replaces peerdb._candidates."""
import json
import uuid

import pytest

import peerdb

pytestmark = pytest.mark.db

LIMITED = {"member", "first_name", "university", "course", "target_roles"}
FULL = LIMITED | {"progress", "streak", "contact_link", "checkin", "inactive"}
THIS_MONDAY = "date_trunc('week', now() at time zone 'Europe/London')::date"


def new_user(conn) -> str:
    user_id = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, email) values (%s, %s)", (user_id, f"test-{user_id}@example.test"))
    return user_id


def city() -> str:
    return f"Zzqxtown-{uuid.uuid4().hex[:10]}"


def person(conn, *, name="Zzqx Priya Shah", field="data", place=None, university="Zzqx University", on=True, waiting=False) -> str:
    """A whole account: a surname, visa details, a targeted and an untargeted role family, an
    application with a CV at a named employer, an achievement; and Peers switched on."""
    user = new_user(conn)
    conn.execute("insert into profiles (user_id, full_name, university, course, graduation_date, visa_type, visa_end_date, locations) "
                 "values (%s, %s, %s, 'MSc Zzqx Data Science', '2026-09-01', 'student', '2027-01-31', %s)",
                 (user, name, university, [place or city()]))
    conn.execute("insert into role_families (user_id, name, fit, overlap, targeted) values (%s, 'Zzqx Data Analyst', 'direct', 80, true)", (user,))
    conn.execute("insert into role_families (user_id, name, fit, overlap, targeted) values (%s, 'Zzqx Astronaut', 'stretch', 10, false)", (user,))
    cv = conn.execute("insert into cv_versions (user_id, name, content) values (%s, 'Zzqx CV', '{}') returning id", (user,)).fetchone()["id"]
    conn.execute("insert into applications (user_id, company, role, source, cv_version_id) values (%s, 'Zzqx Holdings Ltd', 'Zzqx Analyst', 'Other', %s)",
                 (user, cv))
    conn.execute("insert into achievements (user_id, title, uk_version, source) values (%s, 'Zzqx churn model', 'Built a churn model', 'paste')", (user,))
    if on:
        conn.execute("insert into peer_profiles (user_id, enabled, consented_at, over_18, field, waiting_since) "
                     "values (%s, true, now(), true, %s, case when %s then now() end)", (user, field, waiting))
    return user


def group_of(conn, *users, status="active", member_status="accepted") -> str:
    """A group put in place directly, with everyone's yes."""
    group = conn.execute("insert into peer_groups (status, active_since) values (%s, case when %s = 'active' then current_date end) returning id",
                         (status, status)).fetchone()["id"]
    for slot, user in enumerate(users, start=1):
        conn.execute("insert into peer_group_members (group_id, user_id, slot, status, yes_from, joined_at) "
                     "values (%s, %s, %s, %s, %s, case when %s = 'accepted' then now() end)",
                     (group, user, slot, member_status, list(users), member_status))
    return str(group)


def membership(conn, group, user) -> dict:
    return conn.execute("select * from peer_group_members where group_id = %s and user_id = %s", (group, user)).fetchone()


def checkin(conn, group, user, text="Two applications and a mock interview") -> str:
    return str(conn.execute(f"insert into peer_checkins (group_id, user_id, week_start, text) values (%s, %s, {THIS_MONDAY}, %s) returning id",
                            (group, user, text)).fetchone()["id"])


def nudge(conn, group, sender, to):
    conn.execute("insert into peer_nudges (group_id, from_user, to_user, on_day) values (%s, %s, %s, (now() at time zone 'Europe/London')::date)",
                 (group, sender, to))


# ---------- peer_view ----------

def test_view_holds_exactly_the_permitted_fields(conn):
    a, b = person(conn), person(conn, name="Zzqx Tom Brown")
    conn.execute(f"insert into weekly_goals (user_id, effective_from, applications, practice, outreach) values (%s, {THIS_MONDAY}, 1, 2, 3)", (a,))
    group = group_of(conn, a, b)
    view = peerdb.peer_view(conn, b, a)
    assert set(view) == FULL
    assert (view["first_name"], view["university"], view["course"]) == ("Zzqx", "Zzqx University", "MSc Zzqx Data Science")
    assert view["target_roles"] == ["Zzqx Data Analyst"]
    assert view["progress"] == {"met": 1, "of": 3}  # one application with a CV meets the first target only
    assert view["streak"] == 0
    assert (view["contact_link"], view["checkin"], view["inactive"]) == (None, None, False)
    assert view["member"] == str(membership(conn, group, a)["id"])
    shown = json.dumps(view, default=str)
    for hidden in ("Shah", "student", "2027-01-31","Zzqx Holdings", "churn", "Astronaut", "Zzqx Analyst", a, "example.test", "applied"):
        assert hidden not in shown, hidden


def test_proposed_members_see_only_who_they_are(conn):
    a, b = person(conn), person(conn)
    group_of(conn, a, b, status="proposed", member_status="proposed")
    assert set(peerdb.peer_view(conn, a, b)) == set(peerdb.peer_view(conn, b, a)) == LIMITED
    c, d, newcomer = person(conn), person(conn), person(conn)
    group = group_of(conn, c, d)
    conn.execute("insert into peer_group_members (group_id, user_id, slot, status) values (%s, %s, 3, 'proposed')", (group, newcomer))
    assert set(peerdb.peer_view(conn, c, newcomer)) == set(peerdb.peer_view(conn, newcomer, c)) == LIMITED
    assert set(peerdb.peer_view(conn, c, d)) == FULL


def _separate(conn, a, b, how):
    if how == "stranger":
        return
    if how == "different group":
        group_of(conn, a, person(conn))
        group_of(conn, b, person(conn))
        return
    group = group_of(conn, a, b, person(conn))
    if how in ("left", "declined"):
        conn.execute("update peer_group_members set status = %s where group_id = %s and user_id = %s", (how, group, a))
    elif how == "closed":
        conn.execute("update peer_groups set status = 'closed' where id = %s", (group,))
    elif how == "a blocked b":
        conn.execute("insert into peer_blocks (blocker, blocked) values (%s, %s)", (a, b))
    elif how == "b blocked a":
        conn.execute("insert into peer_blocks (blocker, blocked) values (%s, %s)", (b, a))
    elif how == "a switched off":
        conn.execute("update peer_profiles set enabled = false where user_id = %s", (a,))
    elif how == "a barred":
        conn.execute("update peer_profiles set barred_at = now() where user_id = %s", (a,))


@pytest.mark.parametrize("how", ["stranger", "different group", "left", "declined", "closed", "a blocked b", "b blocked a",
                                 "a switched off", "a barred"])
def test_view_is_empty_for(conn, how):
    a, b = person(conn), person(conn)
    _separate(conn, a, b, how)
    assert peerdb.peer_view(conn, b, a) is None


def test_nobody_views_themselves(conn):
    a, b = person(conn), person(conn)
    group_of(conn, a, b)
    assert peerdb.peer_view(conn, a, a) is None


def test_the_view_reads_the_profile_as_it_is_now(conn):
    a, b = person(conn), person(conn)
    group_of(conn, a, b)
    conn.execute("update profiles set course = 'MSc Zzqx Statistics' where user_id = %s", (a,))
    conn.execute("update role_families set targeted = false where user_id = %s", (a,))
    view = peerdb.peer_view(conn, b, a)
    assert (view["course"], view["target_roles"]) == ("MSc Zzqx Statistics", [])


def test_a_reported_checkin_is_hidden_from_the_reporter_only(conn):
    a, b, c = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b, c)
    line = checkin(conn, group, a)
    assert peerdb.peer_view(conn, b, a)["checkin"] == {"id": line, "text": "Two applications and a mock interview"}
    conn.execute("insert into peer_reports (reporter, about_user, group_id, checkin_id, reason) values (%s, %s, %s, %s, 'unkind')", (b, a, group, line))
    assert peerdb.peer_view(conn, b, a)["checkin"] is None
    assert peerdb.peer_view(conn, c, a)["checkin"]["id"] == line


def test_last_weeks_checkin_is_not_this_weeks(conn):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    conn.execute(f"insert into peer_checkins (group_id, user_id, week_start, text) values (%s, %s, {THIS_MONDAY} - 7, 'Old')", (group, a))
    assert peerdb.peer_view(conn, b, a)["checkin"] is None


def test_inactive_after_three_weeks(conn):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    conn.execute("update peer_group_members set joined_at = now() - interval '30 days' where group_id = %s", (group,))
    conn.execute("update applications set applied_on = applied_on - 30 where user_id = %s", (a,))
    assert peerdb.peer_view(conn, b, a)["inactive"] is True
    checkin(conn, group, a)
    assert peerdb.peer_view(conn, b, a)["inactive"] is False


# ---------- switching on and off ----------

def test_switching_on(conn):
    a = person(conn, on=False)
    peerdb.switch_on(conn, a, field="finance")
    row = peerdb.get_profile(conn, a)
    assert (row["enabled"], row["over_18"], row["field"]) == (True, True, "finance")
    assert row["consented_at"] is not None
    with pytest.raises(peerdb.AlreadyOn):
        peerdb.switch_on(conn, a, field="data")


def test_a_barred_user_cannot_switch_on(conn):
    a = person(conn, on=False)
    conn.execute("insert into peer_profiles (user_id, barred_at) values (%s, now())", (a,))
    with pytest.raises(peerdb.Barred):
        peerdb.switch_on(conn, a, field="data")
    assert peerdb.get_profile(conn, a)["enabled"] is False


def test_switching_off_removes_the_user_from_every_view_at_once(conn):
    a, b, c = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b, c)
    conn.execute("update peer_profiles set contact_link = 'https://wa.me/447700900123' where user_id = %s", (a,))
    checkin(conn, group, a)
    nudge(conn, group, a, b)
    nudge(conn, group, c, a)
    peerdb.leave_all(conn, a)
    assert peerdb.peer_view(conn, b, a) is None and peerdb.peer_view(conn, c, a) is None
    assert peerdb.peer_view(conn, a, b) is None
    assert conn.execute("select count(*) as n from peer_checkins where user_id = %s", (a,)).fetchone()["n"] == 0
    assert conn.execute("select count(*) as n from peer_nudges where from_user = %s or to_user = %s", (a, a)).fetchone()["n"] == 0
    row = peerdb.get_profile(conn, a)
    assert (row["enabled"], row["contact_link"], row["waiting_since"], row["field"]) == (False, None, None, "data")
    assert membership(conn, group, a)["status"] == "left"
    assert set(peerdb.peer_view(conn, b, c)) == FULL  # the other two stay together


def test_switching_off_touches_nobody_elses_rows(conn):
    a, b, c = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b, c)
    line = checkin(conn, group, b)
    nudge(conn, group, b, c)
    peerdb.leave_all(conn, a)
    assert peerdb.peer_view(conn, c, b)["checkin"]["id"] == line
    assert conn.execute("select count(*) as n from peer_nudges where from_user = %s and to_user = %s", (b, c)).fetchone()["n"] == 1
