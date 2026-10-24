"""Buddy groups in the database: peer_view, the one function that shows one user anything about
another; switching Peers on and off; matching, proposals, expiry and leaving; check-ins, nudges,
contact links, blocks and reports.

The names cannot be real. Real accounts may be waiting in the real database, so a pair a test
expects to be matched shares a city no real user has, and no test asserts that someone stays
waiting after matching runs unless it replaces peerdb._candidates."""
import json
import uuid
from datetime import timedelta

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


SHOWN = ("first_name", "university", "course", "target_roles")


def test_the_user_sees_themselves_exactly_as_buddies_do(conn):
    a, b = person(conn, name="Zzqxzhang Wei"), person(conn)
    group_of(conn, a, b)
    mine, seen = peerdb.appears_as(conn, a), peerdb.peer_view(conn, b, a)
    assert mine == {k: seen[k] for k in SHOWN}
    assert mine["first_name"] == "Zzqxzhang"  # a name typed surname-first shows the surname: the user is shown this
    assert peerdb.status(conn, a)["appears_as"] == mine


def test_how_the_user_appears_is_shown_before_they_join(conn):
    a = person(conn, name="Zzqxzhang Wei", on=False)
    assert peerdb.status(conn, a)["appears_as"] == {"first_name": "Zzqxzhang", "university": "Zzqx University",
                                                    "course": "MSc Zzqx Data Science", "target_roles": ["Zzqx Data Analyst"]}
    assert peerdb.status(conn, new_user(conn))["appears_as"] is None  # no profile yet


# ---------- switching on and off ----------

def test_switching_on(conn):
    a = person(conn, on=False)
    peerdb.switch_on(conn, a, field="accounting")
    row = peerdb.get_profile(conn, a)
    assert (row["enabled"], row["over_18"], row["field"]) == (True, True, "accounting")
    assert row["consented_at"] is not None
    with pytest.raises(peerdb.AlreadyOn):
        peerdb.switch_on(conn, a, field="data")


def test_switching_on_needs_a_listed_field(conn):
    a = person(conn, on=False)
    with pytest.raises(ValueError):
        peerdb.switch_on(conn, a, field="finance")
    assert peerdb.get_profile(conn, a) is None


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


def test_switching_off_leaves_the_group_found_after_waiting_for_the_lock(conn, monkeypatch, no_rematch):
    """The race: a's membership is read, then another request (holding the group) closes it and
    proposes a to x before switching off gets the lock. a must still end up in no group."""
    a, b, x = person(conn), person(conn), person(conn)
    old = group_of(conn, a, b)
    stale = peerdb._live(conn, a)
    conn.execute("update peer_groups set status = 'closed' where id = %s", (old,))
    conn.execute("update peer_group_members set status = 'left' where group_id = %s", (old,))
    new = group_of(conn, a, x, status="proposed", member_status="proposed")
    reads, real_live = [], peerdb._live

    def first_read_is_stale(conn, user_id):
        reads.append(user_id)
        return stale if len(reads) == 1 else real_live(conn, user_id)
    monkeypatch.setattr(peerdb, "_live", first_read_is_stale)
    peerdb.leave_all(conn, a)
    assert live_group(conn, a) is None and peerdb.get_profile(conn, a)["enabled"] is False
    assert group_status(conn, new) == "closed" and waiting(conn, x)


def test_a_proposal_holding_someone_switched_off_closes_on_the_next_visit(conn, no_rematch):
    a, x = person(conn), person(conn)
    group = group_of(conn, a, x, status="proposed", member_status="proposed")
    conn.execute("update peer_profiles set enabled = false where user_id = %s", (a,))  # as that race used to leave it
    assert peerdb.status(conn, x)["status"] == "waiting"
    assert group_status(conn, group) == "closed" and waiting(conn, x)


def test_a_proposal_with_nobody_to_show_reads_as_waiting(conn):
    a, x = person(conn), person(conn)
    group_of(conn, a, x, status="proposed", member_status="proposed")
    conn.execute("insert into peer_blocks (blocker, blocked) values (%s, %s)", (a, x))  # never through block(), which would also say no
    mine = peerdb.status(conn, x)
    assert (mine["status"], mine["proposal"]) == ("waiting", None)


# ---------- matching, answering, expiry, leaving ----------

def join(conn, *, field="data", **kw) -> str:
    """A whole account switching Peers on, so matching runs for them."""
    user = person(conn, on=False, **kw)
    peerdb.switch_on(conn, user, field=field)
    return user


def live_group(conn, user) -> str | None:
    row = conn.execute("select group_id from peer_group_members where user_id = %s and status in ('proposed', 'accepted')", (user,)).fetchone()
    return str(row["group_id"]) if row else None


def waiting(conn, user) -> bool:
    return peerdb.get_profile(conn, user)["waiting_since"] is not None


def group_status(conn, group) -> str:
    return conn.execute("select status from peer_groups where id = %s", (group,)).fetchone()["status"]


def passed(conn, user, other) -> bool:
    return conn.execute("select 1 from peer_passes where user_id = %s and other_id = %s", (user, other)).fetchone() is not None


@pytest.fixture
def no_rematch(monkeypatch):
    """Nobody sent back to the list is matched again, so the test can see them waiting."""
    monkeypatch.setattr(peerdb, "propose", lambda conn, user_id: None)


def test_two_in_the_same_field_are_proposed_to_each_other(conn):
    place = city()
    a = person(conn, place=place, waiting=True)
    b = join(conn, place=place)
    group = live_group(conn, b)
    assert group and live_group(conn, a) == group and group_status(conn, group) == "proposed"
    rows = conn.execute("select user_id, status, slot from peer_group_members where group_id = %s order by slot", (group,)).fetchall()
    assert [(str(r["user_id"]), r["status"], r["slot"]) for r in rows] == [(b, "proposed", 1), (a, "proposed", 2)]
    others = {c["id"] for c in peerdb._candidates(conn, person(conn), {"field": "data", "places": {place}, "university": ""})}
    assert a not in others and b not in others  # proposed to each other, so nobody else's candidate


def test_same_field_preferred(conn):
    place = city()
    a = person(conn, place=city(), waiting=True)                     # data, another city, the same university
    person(conn, field="finance", place=place, waiting=True)         # finance, the same city
    b = join(conn, place=place)
    assert live_group(conn, b) == live_group(conn, a)


@pytest.mark.parametrize("relation", ["nothing", "b blocked a", "a blocked b", "b passed a", "a passed b", "a barred", "a switched off"])
def test_never_proposed(conn, relation):
    place = city()
    a = person(conn, place=place, waiting=True)
    b = person(conn, place=place, on=False)
    if relation == "b blocked a":
        conn.execute("insert into peer_blocks (blocker, blocked) values (%s, %s)", (b, a))
    elif relation == "a blocked b":
        conn.execute("insert into peer_blocks (blocker, blocked) values (%s, %s)", (a, b))
    elif relation == "b passed a":
        conn.execute("insert into peer_passes (user_id, other_id) values (%s, %s)", (b, a))
    elif relation == "a passed b":
        conn.execute("insert into peer_passes (user_id, other_id) values (%s, %s)", (a, b))
    elif relation == "a barred":
        conn.execute("update peer_profiles set barred_at = now() where user_id = %s", (a,))
    elif relation == "a switched off":
        conn.execute("update peer_profiles set enabled = false where user_id = %s", (a,))
    peerdb.switch_on(conn, b, field="data")
    if relation == "nothing":  # the control: with nothing between them, they are proposed to each other
        assert live_group(conn, a) is not None and live_group(conn, a) == live_group(conn, b)
    else:
        assert live_group(conn, a) is None  # b may have been matched with a real account; never with a


def test_candidates_never_include_the_caller(conn):
    b = person(conn, waiting=True)
    found = peerdb._candidates(conn, b, {"field": "data", "places": set(), "university": ""})
    assert b not in {c["id"] for c in found}


def test_nobody_suitable_leaves_the_user_waiting(conn, monkeypatch):
    monkeypatch.setattr(peerdb, "_candidates", lambda conn, user_id, me: [])
    b = join(conn)
    assert waiting(conn, b) and live_group(conn, b) is None


def test_both_yes_makes_an_active_group(conn):
    place = city()
    a = person(conn, place=place, waiting=True)
    b = join(conn, place=place)
    group = live_group(conn, a)
    peerdb.answer(conn, a, group, yes=True)
    assert group_status(conn, group) == "proposed" and set(peerdb.peer_view(conn, b, a)) == LIMITED
    peerdb.answer(conn, b, group, yes=True)
    row = conn.execute("select status, active_since = (now() at time zone 'Europe/London')::date as today from peer_groups where id = %s",
                       (group,)).fetchone()
    assert (row["status"], row["today"]) == ("active", True)
    assert membership(conn, group, a)["status"] == membership(conn, group, b)["status"] == "accepted"
    assert set(peerdb.peer_view(conn, b, a)) == FULL
    assert not waiting(conn, a) and not waiting(conn, b)  # in a group now, so off the list


def test_not_this_time(conn, monkeypatch):
    place = city()
    a = person(conn, place=place, waiting=True)
    b = join(conn, place=place)
    group = live_group(conn, a)
    real_propose = peerdb.propose
    monkeypatch.setattr(peerdb, "propose", lambda conn, user_id: None)
    peerdb.answer(conn, b, group, yes=False)
    assert group_status(conn, group) == "closed" and membership(conn, group, b)["status"] == "declined"
    assert waiting(conn, a) and waiting(conn, b) and passed(conn, b, a)
    real_propose(conn, b)
    assert live_group(conn, a) is None  # a is still waiting: never proposed with b again


def test_a_third_needs_everyones_yes(conn):
    place = city()
    a, b = person(conn, place=place), person(conn, place=place)
    group = group_of(conn, a, b)
    c = join(conn, place=place)
    assert live_group(conn, c) == group
    assert (membership(conn, group, c)["status"], membership(conn, group, c)["slot"]) == ("proposed", 3)
    peerdb.answer(conn, c, group, yes=True)
    peerdb.answer(conn, a, group, yes=True)
    assert membership(conn, group, c)["status"] == "proposed" and set(peerdb.peer_view(conn, a, c)) == LIMITED
    peerdb.answer(conn, b, group, yes=True)
    assert membership(conn, group, c)["status"] == "accepted" and set(peerdb.peer_view(conn, a, c)) == FULL


def test_a_member_can_turn_a_newcomer_away(conn, no_rematch):
    place = city()
    a, b = person(conn, place=place), person(conn, place=place)
    group = group_of(conn, a, b)
    c = person(conn, place=place, on=False)
    peerdb.switch_on(conn, c, field="data")  # no_rematch replaces propose, so place c by hand
    conn.execute("update peer_profiles set waiting_since = null where user_id = %s", (c,))
    conn.execute("insert into peer_group_members (group_id, user_id, slot, status) values (%s, %s, 3, 'proposed')", (group, c))
    peerdb.answer(conn, a, group, yes=False)
    assert membership(conn, group, c)["status"] == "declined" and passed(conn, a, c) and waiting(conn, c)
    assert group_status(conn, group) == "active" and set(peerdb.peer_view(conn, a, b)) == FULL


def test_a_full_group_takes_nobody(conn):
    place = city()
    group = group_of(conn, *(person(conn, place=place) for _ in range(3)))
    d = join(conn, place=place)
    assert live_group(conn, d) != group


def test_nothing_to_answer(conn):
    a, b, c = person(conn), person(conn), person(conn)
    closed = group_of(conn, a, b, status="closed", member_status="left")
    with pytest.raises(peerdb.Gone):
        peerdb.answer(conn, a, closed, yes=True)
    group = group_of(conn, b, c)
    with pytest.raises(peerdb.Gone):
        peerdb.answer(conn, b, group, yes=True)  # accepted, and no newcomer to answer for
    with pytest.raises(peerdb.Gone):
        peerdb.answer(conn, a, group, yes=True)  # not in it


def test_the_other_switched_off_before_my_yes(conn, no_rematch):
    place = city()
    a, b = person(conn, place=place), person(conn, place=place)
    group = group_of(conn, a, b, status="proposed", member_status="proposed")
    peerdb.leave_all(conn, a)
    assert group_status(conn, group) == "closed" and waiting(conn, b)
    assert peerdb.peer_view(conn, b, a) is None
    with pytest.raises(peerdb.Gone):
        peerdb.answer(conn, b, group, yes=True)


def test_a_proposal_expires_after_seven_days(conn, no_rematch):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b, status="proposed", member_status="proposed")
    conn.execute("update peer_group_members set yes_from = %s where group_id = %s", ([a], group))  # a said yes, b said nothing
    conn.execute("update peer_group_members set proposed_at = now() - interval '6 days' where group_id = %s", (group,))
    peerdb.tidy(conn, a)
    assert group_status(conn, group) == "proposed"
    conn.execute("update peer_group_members set proposed_at = now() - interval '8 days' where group_id = %s", (group,))
    peerdb.tidy(conn, a)
    assert group_status(conn, group) == "closed"
    assert passed(conn, b, a) and not passed(conn, a, b)
    assert waiting(conn, a) and waiting(conn, b)


def test_leaving_a_pair_closes_it(conn, no_rematch):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    peerdb.leave(conn, a, group)
    assert group_status(conn, group) == "closed" and waiting(conn, a) and waiting(conn, b) and passed(conn, a, b)
    with pytest.raises(peerdb.Gone):
        peerdb.leave(conn, a, group)


def test_leaving_a_three_keeps_the_other_two(conn, no_rematch):
    a, b, c = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b, c)
    peerdb.leave(conn, c, group)
    assert group_status(conn, group) == "active" and set(peerdb.peer_view(conn, a, b)) == FULL and waiting(conn, c)


def test_deleting_a_login_closes_a_group_left_with_one(conn, no_rematch):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    conn.execute("delete from auth.users where id = %s", (a,))
    peerdb.tidy(conn, b)
    assert group_status(conn, group) == "closed" and waiting(conn, b)


def test_someone_on_with_no_group_goes_back_on_the_list(conn, no_rematch):
    a = person(conn)  # on, not waiting, in no group
    peerdb.tidy(conn, a)
    assert waiting(conn, a)


# ---------- a fair queue ----------

def since(conn, user):
    return peerdb.get_profile(conn, user)["waiting_since"]


def waited(conn, user, days=5):
    conn.execute("update peer_profiles set waiting_since = now() - make_interval(days => %s) where user_id = %s", (days, user))
    return since(conn, user)


def test_someone_declined_keeps_their_place_on_the_list(conn, monkeypatch):
    place = city()
    a = person(conn, place=place, waiting=True)
    before = waited(conn, a)
    b = join(conn, place=place)
    group = live_group(conn, a)
    assert group and group == live_group(conn, b)
    b_before = waited(conn, b, days=10)  # b had waited even longer than a
    monkeypatch.setattr(peerdb, "propose", lambda conn, user_id: None)
    peerdb.answer(conn, b, group, yes=False)
    assert since(conn, a) == before  # a did nothing wrong
    assert since(conn, b) > before > b_before  # b said no, so b goes to the back


def test_a_newcomer_turned_away_keeps_their_place(conn, no_rematch):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    c = person(conn, waiting=True)
    before = waited(conn, c)
    conn.execute("insert into peer_group_members (group_id, user_id, slot, status) values (%s, %s, 3, 'proposed')", (group, c))
    peerdb.answer(conn, a, group, yes=False)
    assert since(conn, c) == before


def test_after_a_lapse_whoever_said_yes_is_matched_first_and_keeps_their_place(conn, monkeypatch):
    a, b = person(conn, waiting=True), person(conn, waiting=True)
    before = waited(conn, a)
    waited(conn, b)
    group = group_of(conn, b, a, status="proposed", member_status="proposed")  # the silent b holds place 1, so is read first
    conn.execute("update peer_group_members set yes_from = %s, proposed_at = now() - interval '8 days' where group_id = %s", ([a], group))
    order = []
    monkeypatch.setattr(peerdb, "propose", lambda conn, user_id: order.append(str(user_id)))
    peerdb.tidy(conn, b)  # b, who never answered, is the one who opens the page
    assert order[0] == a
    assert since(conn, a) == before and since(conn, b) > before


# ---------- at most three new proposals a London day ----------

def proposed_today(conn, user, times):
    """`times` proposals already made to the user today, in groups since closed."""
    for _ in range(times):
        group_of(conn, user, person(conn), status="closed", member_status="declined")


def test_after_three_proposals_today_the_user_waits_until_tomorrow(conn):
    place = city()
    a = person(conn, place=place, waiting=True)
    b = person(conn, place=place, on=False)
    proposed_today(conn, b, 3)
    peerdb.switch_on(conn, b, field="data")
    assert live_group(conn, b) is None and live_group(conn, a) is None
    mine = peerdb.status(conn, b)
    assert (mine["status"], mine["again_tomorrow"]) == ("waiting", True)
    conn.execute("update peer_group_members set proposed_at = proposed_at - interval '1 day' "  # tomorrow: those proposals were yesterday's
                 "where group_id in (select group_id from peer_group_members where user_id = %s)", (b,))
    assert peerdb.status(conn, b)["status"] == "proposed" and live_group(conn, a) == live_group(conn, b)


def test_two_proposals_today_still_leave_room_for_a_third(conn):
    place = city()
    a = person(conn, place=place, waiting=True)
    b = person(conn, place=place, on=False)
    proposed_today(conn, b, 2)
    peerdb.switch_on(conn, b, field="data")
    assert live_group(conn, b) is not None and live_group(conn, b) == live_group(conn, a)
    assert peerdb.status(conn, b)["again_tomorrow"] is False


def test_someone_at_the_cap_is_nobodys_candidate(conn):
    a = person(conn, waiting=True)
    proposed_today(conn, a, 3)
    found = peerdb._candidates(conn, person(conn), {"field": "data", "places": set(), "university": ""})
    assert a not in {c["id"] for c in found}


def pair_formed_yesterday(conn) -> tuple[str, str, str]:
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    conn.execute("update peer_group_members set proposed_at = now() - interval '1 day' where group_id = %s", (group,))
    return a, b, group


def newcomers_turned_away_today(conn, group, times):
    for _ in range(times):
        conn.execute("insert into peer_group_members (group_id, user_id, slot, status) values (%s, %s, 3, 'declined')", (group, person(conn)))


def test_a_newcomer_counts_as_a_new_person_for_those_already_in_the_group(conn):
    a, b, group = pair_formed_yesterday(conn)
    newcomers_turned_away_today(conn, group, 2)
    assert peerdb.proposed_today(conn, a) == peerdb.proposed_today(conn, b) == 2


def test_a_pair_that_turned_away_three_newcomers_today_takes_no_fourth(conn):
    a, b, group = pair_formed_yesterday(conn)
    newcomers_turned_away_today(conn, group, 2)
    me = {"field": "data", "places": set(), "university": ""}
    assert group in {c["id"] for c in peerdb._candidates(conn, person(conn), me)}  # the control: room for one more today
    newcomers_turned_away_today(conn, group, 1)
    assert group not in {c["id"] for c in peerdb._candidates(conn, person(conn), me)}


# ---------- check-ins, nudges, contact links ----------

def member_id(conn, group, user) -> str:
    return str(membership(conn, group, user)["id"])


def test_a_second_checkin_in_the_week_replaces_the_first(conn):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    peerdb.set_checkin(conn, a, group, "First line")
    peerdb.set_checkin(conn, a, group, "Second line")
    assert [r["text"] for r in conn.execute("select text from peer_checkins where user_id = %s", (a,))] == ["Second line"]
    assert peerdb.peer_view(conn, b, a)["checkin"]["text"] == "Second line"


@pytest.mark.parametrize("where", ["proposed", "closed", "another group"])
def test_only_someone_in_the_group_checks_in(conn, where):
    a, b = person(conn), person(conn)
    if where == "proposed":
        group = group_of(conn, a, b, status="proposed", member_status="proposed")
    elif where == "closed":
        group = group_of(conn, a, b, status="closed", member_status="left")
    else:
        group_of(conn, a, b)
        group = group_of(conn, person(conn), person(conn))
    with pytest.raises(peerdb.Gone):
        peerdb.set_checkin(conn, a, group, "Line")


@pytest.mark.parametrize("before, after, monday_before, monday_after", [
    ("2026-10-18 23:30 Europe/London", "2026-10-19 00:30 Europe/London", "2026-10-12", "2026-10-19"),
    ("2026-10-25 23:30 Europe/London", "2026-10-26 00:30 Europe/London", "2026-10-19", "2026-10-26"),  # the clocks went back that morning
])
def test_the_week_turns_at_midnight_on_sunday_in_london(conn, before, after, monday_before, monday_after):
    assert str(peerdb.week_start(conn, before)) == monday_before
    assert str(peerdb.week_start(conn, after)) == monday_after


def test_one_nudge_a_day(conn):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    assert peerdb.nudge(conn, a, group, member_id(conn, group, b)) == "Zzqx"
    with pytest.raises(peerdb.AlreadyNudged):
        peerdb.nudge(conn, a, group, member_id(conn, group, b))
    conn.execute("update peer_nudges set on_day = on_day - 1 where from_user = %s", (a,))  # as if sent yesterday
    peerdb.nudge(conn, a, group, member_id(conn, group, b))
    assert peerdb.nudge(conn, b, group, member_id(conn, group, a)) == "Zzqx"  # the other way is another nudge


def test_a_nudge_goes_only_to_someone_in_the_group(conn):
    a, b, newcomer = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b)
    conn.execute("insert into peer_group_members (group_id, user_id, slot, status) values (%s, %s, 3, 'proposed')", (group, newcomer))
    other = group_of(conn, person(conn), person(conn))
    stranger = conn.execute("select id from peer_group_members where group_id = %s limit 1", (other,)).fetchone()["id"]
    for target in (member_id(conn, group, newcomer), member_id(conn, group, a), stranger, uuid.uuid4()):
        with pytest.raises(peerdb.Gone):
            peerdb.nudge(conn, a, group, target)


def test_nudges_received_this_week_one_per_sender(conn):
    a, b, c = person(conn), person(conn, name="Zzqxcat Jones"), person(conn)
    group = group_of(conn, a, b, c)
    peerdb.nudge(conn, b, group, member_id(conn, group, a))
    peerdb.nudge(conn, c, group, member_id(conn, group, a))
    conn.execute("update peer_nudges set on_day = on_day - 1 where from_user = %s", (c,))
    peerdb.nudge(conn, c, group, member_id(conn, group, a))
    conn.execute("insert into peer_nudges (group_id, from_user, to_user, on_day) values (%s, %s, %s, %s)",
                 (group, b, a, peerdb.week_start(conn) - timedelta(days=1)))  # last week's
    received = peerdb.status(conn, a)["nudges"]
    assert sorted(n["first_name"] for n in received) == ["Zzqx", "Zzqxcat"]
    assert {n["text"] for n in received} >= {"Zzqxcat sent you a nudge: one step today keeps your week on track."}
    assert all(set(n) == {"member", "first_name", "text"} for n in received)  # no date of the sender's activity
    assert {n["member"] for n in received} == {member_id(conn, group, b), member_id(conn, group, c)}


def test_a_nudge_from_someone_no_longer_in_the_group_is_not_shown(conn):
    a, b, c = person(conn), person(conn, name="Zzqxben Okafor"), person(conn)
    group = group_of(conn, a, b, c)
    peerdb.nudge(conn, b, group, member_id(conn, group, a))
    conn.execute("update peer_group_members set status = 'left' where group_id = %s and user_id = %s", (group, b))
    assert peerdb.status(conn, a)["nudges"] == []


def test_the_page_knows_whom_the_caller_nudged_today(conn):
    a, b, c = person(conn), person(conn, name="Zzqxben Okafor"), person(conn, name="Zzqxcat Jones")
    group = group_of(conn, a, b, c)
    peerdb.nudge(conn, a, group, member_id(conn, group, b))
    members = {m["first_name"]: m["nudged_today"] for m in peerdb.status(conn, a)["group"]["members"]}
    assert members == {"Zzqxben": True, "Zzqxcat": False}


def test_a_contact_link_is_shown_to_the_group_only(conn):
    a, b = person(conn), person(conn)
    group_of(conn, a, b)
    c = person(conn)
    group_of(conn, c, person(conn))
    peerdb.set_contact_link(conn, a, "https://www.linkedin.com/in/zzqx-priya")
    assert peerdb.peer_view(conn, b, a)["contact_link"] == "https://www.linkedin.com/in/zzqx-priya"
    assert "zzqx-priya" not in json.dumps(peerdb.status(conn, c), default=str)
    peerdb.set_contact_link(conn, a, None)
    assert peerdb.peer_view(conn, b, a)["contact_link"] is None


def test_a_contact_link_needs_peers_on(conn):
    a = person(conn, on=False)
    with pytest.raises(peerdb.Gone):
        peerdb.set_contact_link(conn, a, "https://wa.me/447700900123")


@pytest.mark.parametrize("link", ["javascript:alert(1)", "https://evil.test/in/zzqx-priya", "http://wa.me/447700900123", "https://wa.me/07700900123"])
def test_a_contact_link_is_checked_here_too(conn, link):
    a = person(conn)
    with pytest.raises(ValueError):
        peerdb.set_contact_link(conn, a, link)
    assert peerdb.get_profile(conn, a)["contact_link"] is None


# ---------- what is out of sight, and what a page load costs ----------

def test_out_of_sight_is_gone(conn):
    a = person(conn)
    for attempt in (lambda: peerdb.answer(conn, a, str(uuid.uuid4()), yes=True), lambda: peerdb.leave(conn, a, str(uuid.uuid4())),
                    lambda: peerdb.set_checkin(conn, a, str(uuid.uuid4()), "Line"), lambda: peerdb.block(conn, a, uuid.uuid4()),
                    lambda: peerdb.report(conn, a, member=uuid.uuid4(), reason="unkind")):
        with pytest.raises(peerdb.Gone):
            attempt()


def statements(conn, monkeypatch) -> list[str]:
    """Every statement the connection runs from now on."""
    seen, real = [], conn.execute

    def counted(query, *args, **kwargs):
        seen.append(str(query))
        return real(query, *args, **kwargs)
    monkeypatch.setattr(conn, "execute", counted)
    return seen


def test_a_state_read_for_a_group_of_three_stays_small(conn, monkeypatch):
    a, b, c = person(conn), person(conn), person(conn)
    group_of(conn, a, b, c)
    seen = statements(conn, monkeypatch)
    peerdb.status(conn, a)
    assert len(seen) <= 30, len(seen)


def test_a_state_read_locks_no_group_when_nothing_changes(conn, monkeypatch):
    a, b = person(conn), person(conn)
    group_of(conn, a, b)
    seen = statements(conn, monkeypatch)
    peerdb.status(conn, a)
    assert not [q for q in seen if "peer_groups" in q and "for update" in q]




# ---------- block and report ----------

def test_block_and_leave_a_group_of_three(conn, no_rematch):
    a, b, c = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b, c)
    peerdb.block(conn, b, member_id(conn, group, c))
    assert membership(conn, group, b)["status"] == "left" and waiting(conn, b)
    assert group_status(conn, group) == "active" and set(peerdb.peer_view(conn, a, c)) == FULL
    assert peerdb.peer_view(conn, b, c) is None and peerdb.peer_view(conn, c, b) is None
    found = peerdb._candidates(conn, c, {"field": "data", "places": set(), "university": ""})
    assert b not in {x["id"] for x in found}


def test_blocking_on_a_proposal_turns_it_down(conn, no_rematch):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b, status="proposed", member_status="proposed")
    peerdb.block(conn, a, member_id(conn, group, b))
    assert membership(conn, group, a)["status"] == "declined" and group_status(conn, group) == "closed"


def test_blocking_a_newcomer_turns_them_away(conn, no_rematch):
    a, b, newcomer = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b)
    conn.execute("insert into peer_group_members (group_id, user_id, slot, status) values (%s, %s, 3, 'proposed')", (group, newcomer))
    peerdb.block(conn, a, member_id(conn, group, newcomer))
    assert membership(conn, group, newcomer)["status"] == "declined" and membership(conn, group, a)["status"] == "accepted"


def test_blocking_someone_out_of_sight_is_refused(conn):
    a, b = person(conn), person(conn)
    group_of(conn, a, b)
    other = group_of(conn, person(conn), person(conn))
    stranger = conn.execute("select id from peer_group_members where group_id = %s limit 1", (other,)).fetchone()["id"]
    for target in (stranger, uuid.uuid4()):
        with pytest.raises(peerdb.Gone):
            peerdb.block(conn, a, target)


def test_a_report_hides_the_line_from_the_reporter_and_keeps_a_copy(conn):
    a, b, c = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b, c)
    line = checkin(conn, group, a, "Buy my course at zzqx.test")
    peerdb.report(conn, b, member=member_id(conn, group, a), reason="spam", details="Selling", checkin_id=line)
    assert peerdb.peer_view(conn, b, a)["checkin"] is None and peerdb.peer_view(conn, c, a)["checkin"]["id"] == line
    peerdb.set_checkin(conn, a, group, "Edited")
    assert peerdb.peer_view(conn, b, a)["checkin"] is None
    row = conn.execute("select about_user, group_id, reason, details, checkin_text, handled from peer_reports where reporter = %s", (b,)).fetchone()
    assert (str(row["about_user"]), str(row["group_id"]), row["reason"], row["details"], row["checkin_text"], row["handled"]) == \
        (a, group, "spam", "Selling", "Buy my course at zzqx.test", False)


def test_reporting_a_member_without_a_line(conn):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    peerdb.report(conn, b, member=member_id(conn, group, a), reason="unkind")
    assert conn.execute("select checkin_text from peer_reports where reporter = %s", (b,)).fetchone()["checkin_text"] is None


def test_a_report_needs_someone_in_sight_and_their_own_line(conn):
    a, b, c = person(conn), person(conn), person(conn)
    group = group_of(conn, a, b, c)
    cs_line = checkin(conn, group, c)
    with pytest.raises(peerdb.Gone):
        peerdb.report(conn, b, member=member_id(conn, group, a), reason="unkind", checkin_id=cs_line)
    with pytest.raises(peerdb.Gone):
        peerdb.report(conn, b, member=uuid.uuid4(), reason="unkind")


def test_the_owner_sees_open_reports_and_marks_them_handled(conn):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    line = checkin(conn, group, a, "Zzqx rude line")
    peerdb.report(conn, b, member=member_id(conn, group, a), reason="unkind", checkin_id=line)
    report = conn.execute("select id from peer_reports where reporter = %s", (b,)).fetchone()["id"]
    found = {r["id"]: r for r in peerdb.open_reports(conn)}
    assert found[str(report)]["reason"] == "Unkind, harassing or threatening" and found[str(report)]["checkin_text"] == "Zzqx rude line"
    assert peerdb.mark_handled(conn, report) is True
    assert str(report) not in {r["id"] for r in peerdb.open_reports(conn)}
    assert peerdb.mark_handled(conn, report) is False


def test_a_barred_user_is_out_and_stays_out(conn, no_rematch):
    a, b = person(conn), person(conn)
    group = group_of(conn, a, b)
    peerdb.bar(conn, a)
    me = peerdb.get_profile(conn, a)
    assert me["enabled"] is False and me["barred_at"] is not None
    assert group_status(conn, group) == "closed" and peerdb.peer_view(conn, b, a) is None
    with pytest.raises(peerdb.Barred):
        peerdb.switch_on(conn, a, field="data")


def test_barring_nobody_says_so(conn):
    assert peerdb.bar(conn, str(uuid.uuid4())) is False
