"""Buddy groups in the database (step 7). Every peers query lives here, apart from repo.py, because
this is the one place the app reads one user's rows on someone else's behalf.

THE EXCEPTION TO "EVERY USER'S DATA IS PRIVATE": peer_view is the only function that returns
information about another user. It builds its answer from an explicit list of columns, and returns
nothing unless the two are live members of the same open group, neither has blocked the other,
and the member has Peers switched on. Reviewers: no other function here may return another user's
fields, and no code outside this module may call _weekly with anyone's id but the caller's.

Matching (_candidates, propose) also reads other users' field, places, university and time waited,
to choose whom to propose; it returns only the group it made. The owner's report tools at the end
are for scripts/peer_reports.py and are never called from a route.

Pages never see a user id: a member is named by the id of their peer_group_members row."""
from datetime import date

import habits
import peers
import repo

LIVE = ("proposed", "accepted")


class Barred(Exception):
    """The owner has barred this user from buddy groups."""


class AlreadyOn(Exception):
    """Peers is already switched on."""


def _str(row: dict | None) -> dict | None:
    return repo._row(row)


def week_start(conn, at=None) -> date:
    """The London Monday of `at` (default now). Postgres does the clock change."""
    return conn.execute("select date_trunc('week', coalesce(%s::timestamptz, now()) at time zone 'Europe/London')::date as monday",
                        (at,)).fetchone()["monday"]


# ---------- the caller's own switch ----------

def get_profile(conn, user_id) -> dict | None:
    return _str(conn.execute("select enabled, consented_at, over_18, field, contact_link, waiting_since, barred_at "
                             "from peer_profiles where user_id = %s", (user_id,)).fetchone())


def switch_on(conn, user_id, *, field: str) -> None:
    """Consent given (18 or over, the code of conduct) and a field chosen: on the list from now."""
    row = conn.execute("select enabled, barred_at from peer_profiles where user_id = %s for update", (user_id,)).fetchone()
    if row and row["barred_at"]:
        raise Barred()
    if row and row["enabled"]:
        raise AlreadyOn()
    conn.execute("insert into peer_profiles (user_id, enabled, consented_at, over_18, field, waiting_since) "
                 "values (%s, true, now(), true, %s, now()) on conflict (user_id) do update set enabled = true, "
                 "consented_at = now(), over_18 = true, field = excluded.field, waiting_since = now()", (user_id, field))


_MEMBER = ("m.id, m.group_id, m.user_id, m.slot, m.status, m.yes_from, m.proposed_at, m.joined_at, "
           f"((m.proposed_at + interval '{peers.PROPOSAL_DAYS} days') at time zone 'Europe/London')::date as expires_on")


def _membership(row: dict | None) -> dict | None:
    return _str(row) | {"yes_from": [str(u) for u in row["yes_from"]]} if row else None


def _live(conn, user_id) -> dict | None:
    """The caller's live membership (proposed or accepted), with its group's state."""
    return _membership(conn.execute(
        f"select {_MEMBER}, g.status as group_status, g.active_since from peer_group_members m join peer_groups g on g.id = m.group_id "
        "where m.user_id = %s and m.status in ('proposed', 'accepted') and g.status <> 'closed'", (user_id,)).fetchone())


def _members(conn, group_id) -> list[dict]:
    """The live rows of a group, in place order."""
    rows = conn.execute(f"select {_MEMBER} from peer_group_members m where m.group_id = %s and m.status in ('proposed', 'accepted') "
                        "order by m.slot", (group_id,)).fetchall()
    return [_membership(r) for r in rows]


def _pass(conn, user_id, others) -> None:
    """Never propose these pairings again."""
    for other in others:
        if str(other) != str(user_id):
            conn.execute("insert into peer_passes (user_id, other_id) values (%s, %s) on conflict do nothing", (user_id, other))


def _depart(conn, group_id, row: dict, *, status: str) -> None:
    """A member leaves a group (left) or turns down a proposal (declined): never proposed with the others again."""
    conn.execute("update peer_group_members set status = %s where id = %s", (status, row["id"]))
    _pass(conn, row["user_id"], [m["user_id"] for m in _members(conn, group_id)])


def leave_all(conn, user_id) -> None:
    """Switch Peers off: out of any group at once, the contact link cleared, and the check-ins and
    nudges sent and received deleted. The field and the record of consent stay, as do blocks and passes."""
    mine = _live(conn, user_id)
    if mine:
        conn.execute("select id from peer_groups where id = %s for update", (mine["group_id"],))
        _depart(conn, mine["group_id"], mine, status="left")
    conn.execute("update peer_profiles set enabled = false, waiting_since = null, contact_link = null where user_id = %s", (user_id,))
    conn.execute("delete from peer_checkins where user_id = %s", (user_id,))
    conn.execute("delete from peer_nudges where from_user = %s or to_user = %s", (user_id, user_id))


# ---------- what one member sees of another: the one exception ----------

LIMITED = ("member", "first_name", "university", "course", "target_roles")
FULL = LIMITED + ("progress", "streak", "contact_link", "checkin", "inactive")


def _weekly(conn, user_id) -> dict:
    """One user's week against their goals, their streak and the last day they did something that
    counts. From their own rows; called with the caller's id, or by peer_view after its checks."""
    applications = [dict(r) for r in conn.execute("select applied_on, cv_version_id from applications where user_id = %s", (user_id,))]
    practice = repo.practice_days(conn, user_id)
    outreach = [r["on_day"] for r in conn.execute("select on_day from outreach_events where user_id = %s and kind = 'sent'", (user_id,))]
    goals, today = repo.list_goals(conn, user_id), repo.today(conn)
    default = (conn.execute("select outreach_default from profiles where user_id = %s", (user_id,)).fetchone() or {"outreach_default": 0})["outreach_default"]
    targets = {"outreach_days": outreach, "default_outreach": default}
    week = habits.this_week(applications=applications, practice_days=practice, goals=goals, today=today, **targets)
    streak = habits.streaks(applications=applications, practice_days=practice, goals=goals,
                            started=repo.account_started(conn, user_id), today=today, **targets)["current"]
    done = [a["applied_on"] for a in applications if a["cv_version_id"]] + practice + outreach
    return {"progress": peers.progress(week), "streak": streak, "all_met": week["met"], "last_active": max(done, default=None)}


def peer_view(conn, viewer_id, member_id) -> dict | None:
    """What `viewer_id` may see of `member_id`, or None. See the module docstring: this is the one
    function that returns another user's information, and these are the only fields it returns."""
    if str(viewer_id) == str(member_id):
        return None
    shared = conn.execute(
        "select m.id as member, m.status as member_status, v.status as viewer_status, g.id as group_id, g.status as group_status, "
        "(m.joined_at at time zone 'Europe/London')::date as joined_on, p.contact_link "
        "from peer_group_members v "
        "join peer_groups g on g.id = v.group_id and g.status <> 'closed' "
        "join peer_group_members m on m.group_id = v.group_id and m.user_id = %(member)s and m.status in ('proposed', 'accepted') "
        "join peer_profiles p on p.user_id = m.user_id and p.enabled and p.barred_at is null "
        "join peer_profiles vp on vp.user_id = v.user_id and vp.enabled and vp.barred_at is null "
        "where v.user_id = %(viewer)s and v.status in ('proposed', 'accepted') "
        "and not exists (select 1 from peer_blocks b where (b.blocker = %(viewer)s and b.blocked = %(member)s) "
        "or (b.blocker = %(member)s and b.blocked = %(viewer)s))",
        {"viewer": viewer_id, "member": member_id}).fetchone()
    if not shared:
        return None
    who = conn.execute("select full_name, university, course from profiles where user_id = %s", (member_id,)).fetchone()
    roles = [r["name"] for r in conn.execute("select name from role_families where user_id = %s and targeted order by name", (member_id,))]
    view = {"member": str(shared["member"]), "first_name": ((who["full_name"] if who else "").split() or [""])[0],
            "university": who["university"] if who else None, "course": who["course"] if who else None, "target_roles": roles}
    if not (shared["group_status"] == "active" and shared["member_status"] == shared["viewer_status"] == "accepted"):
        return view
    weekly, monday = _weekly(conn, member_id), week_start(conn)
    line = conn.execute(
        "select c.id, c.text from peer_checkins c where c.group_id = %s and c.user_id = %s and c.week_start = %s "
        "and not exists (select 1 from peer_reports r where r.checkin_id = c.id and r.reporter = %s)",
        (shared["group_id"], member_id, monday, viewer_id)).fetchone()
    checked_in = conn.execute("select max((updated_at at time zone 'Europe/London')::date) as day from peer_checkins where user_id = %s",
                              (member_id,)).fetchone()["day"]
    last = max([d for d in (weekly["last_active"], checked_in) if d], default=None)
    return view | {"progress": weekly["progress"], "streak": weekly["streak"], "contact_link": shared["contact_link"],
                   "checkin": {"id": str(line["id"]), "text": line["text"]} if line else None,
                   "inactive": peers.inactive(last, shared["joined_on"] or repo.today(conn), repo.today(conn))}
