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
from datetime import date, datetime, time, timezone

import psycopg

import habits
import peers
import repo

LIVE = ("proposed", "accepted")


class Gone(LookupError):
    """A group, member or line the caller cannot see (left, closed, never theirs): a 404. Raised by
    name, so a KeyError or IndexError from a bug is never mistaken for it."""


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
    if field not in peers.FIELDS:
        raise ValueError(field)
    row = conn.execute("select enabled, barred_at from peer_profiles where user_id = %s for update", (user_id,)).fetchone()
    if row and row["barred_at"]:
        raise Barred()
    if row and row["enabled"]:
        raise AlreadyOn()
    conn.execute("insert into peer_profiles (user_id, enabled, consented_at, over_18, field, waiting_since) "
                 "values (%s, true, now(), true, %s, now()) on conflict (user_id) do update set enabled = true, "
                 "consented_at = now(), over_18 = true, field = excluded.field, waiting_since = now()", (user_id, field))
    propose(conn, user_id)


_MEMBER = ("m.id, m.group_id, m.user_id, m.slot, m.status, m.yes_from, m.proposed_at, m.joined_at, "
           f"((m.proposed_at + interval '{peers.PROPOSAL_DAYS} days') at time zone 'Europe/London')::date as expires_on, "
           f"m.proposed_at < now() - interval '{peers.PROPOSAL_DAYS} days' as stale, "
           "exists (select 1 from peer_profiles p where p.user_id = m.user_id and p.enabled and p.barred_at is null) as switched_on")


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
    nudges sent and received deleted. The field and the record of consent stay, as do blocks and passes.

    The membership is read again once its group is locked: while this waited for the lock, another
    request may have closed that group and proposed the user to someone else. It repeats until the
    user is live in no group."""
    others = []
    while seen := _live(conn, user_id):
        conn.execute("select id from peer_groups where id = %s for update", (seen["group_id"],))
        mine = _live(conn, user_id)
        if not mine or mine["group_id"] != seen["group_id"]:
            continue  # moved on while we waited: lock wherever they are now
        _depart(conn, mine["group_id"], mine, status="left")
        others += _settle(conn, mine["group_id"])
    conn.execute("update peer_profiles set enabled = false, waiting_since = null, contact_link = null where user_id = %s", (user_id,))
    conn.execute("delete from peer_checkins where user_id = %s", (user_id,))
    conn.execute("delete from peer_nudges where from_user = %s or to_user = %s", (user_id, user_id))
    _rematch(conn, others)


# ---------- what one member sees of another: the one exception ----------

LIMITED = ("member", "first_name", "university", "course", "target_roles")
FULL = LIMITED + ("progress", "streak", "contact_link", "checkin", "inactive")


def _clock(conn) -> dict:
    """Today and this week's Monday in London, read once for a whole state read."""
    return dict(conn.execute("select (now() at time zone 'Europe/London')::date as today, "
                             "date_trunc('week', now() at time zone 'Europe/London')::date as monday").fetchone())


def _shown(conn, user_id) -> dict | None:
    """First name, university, course and target roles: what anyone in a group sees of this user.
    Read by peer_view for a member, and by appears_as for the user themselves."""
    row = conn.execute("select p.full_name, p.university, p.course, "
                       "array(select r.name from role_families r where r.user_id = p.user_id and r.targeted order by r.name) as roles "
                       "from profiles p where p.user_id = %s", (user_id,)).fetchone()
    if not row:
        return None
    return {"first_name": peers.first_name(row["full_name"]), "university": row["university"], "course": row["course"],
            "target_roles": list(row["roles"])}


def appears_as(conn, user_id) -> dict | None:
    """The caller's own name, university, course and target roles exactly as their group sees them,
    so a name typed surname-first can be noticed and put right in Profile. Their own rows only."""
    return _shown(conn, user_id)


def _weekly(conn, user_id, today: date) -> dict:
    """One user's week against their goals, their streak and the last day they did something that
    counts. From their own rows; called with the caller's id, or by peer_view after its checks."""
    applications = [dict(r) for r in conn.execute("select applied_on, cv_version_id from applications where user_id = %s", (user_id,))]
    practice = repo.practice_days(conn, user_id)
    outreach = [r["on_day"] for r in conn.execute("select on_day from outreach_events where user_id = %s and kind = 'sent'", (user_id,))]
    goals = repo.list_goals(conn, user_id)
    profile = conn.execute("select outreach_default, (created_at at time zone 'Europe/London')::date as started from profiles where user_id = %s",
                           (user_id,)).fetchone() or {"outreach_default": 0, "started": None}
    targets = {"outreach_days": outreach, "default_outreach": profile["outreach_default"]}
    week = habits.this_week(applications=applications, practice_days=practice, goals=goals, today=today, **targets)
    streak = habits.streaks(applications=applications, practice_days=practice, goals=goals,
                            started=profile["started"], today=today, **targets)["current"]
    done = [a["applied_on"] for a in applications if a["cv_version_id"]] + practice + outreach
    return {"progress": peers.progress(week), "streak": streak, "all_met": week["met"], "last_active": max(done, default=None)}


def peer_view(conn, viewer_id, member_id, *, clock: dict | None = None) -> dict | None:
    """What `viewer_id` may see of `member_id`, or None. See the module docstring: this is the one
    function that returns another user's information, and these are the only fields it returns.
    `clock` is _clock's answer, passed in by a caller that has already read it."""
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
    view = {"member": str(shared["member"])} | (_shown(conn, member_id) or {"first_name": "", "university": None, "course": None, "target_roles": []})
    if not (shared["group_status"] == "active" and shared["member_status"] == shared["viewer_status"] == "accepted"):
        return view
    clock = clock or _clock(conn)
    weekly = _weekly(conn, member_id, clock["today"])
    lines = conn.execute(  # this week's line, unless the viewer reported it, and the member's last check-in day
        "select c.id, c.text, (select max((x.updated_at at time zone 'Europe/London')::date) from peer_checkins x "
        "where x.user_id = %(member)s) as checked_in "
        "from (select 1) as one left join peer_checkins c on c.group_id = %(group)s and c.user_id = %(member)s and c.week_start = %(monday)s "
        "and not exists (select 1 from peer_reports r where r.checkin_id = c.id and r.reporter = %(viewer)s)",
        {"group": shared["group_id"], "member": member_id, "monday": clock["monday"], "viewer": viewer_id}).fetchone()
    last = max([d for d in (weekly["last_active"], lines["checked_in"]) if d], default=None)
    return view | {"progress": weekly["progress"], "streak": weekly["streak"], "contact_link": shared["contact_link"],
                   "checkin": {"id": str(lines["id"]), "text": lines["text"]} if lines["id"] else None,
                   "inactive": peers.inactive(last, shared["joined_on"] or clock["today"], clock["today"])}


# ---------- matching ----------

def _me(conn, user_id) -> dict | None:
    row = conn.execute("select p.field, pr.locations, pr.university from peer_profiles p join profiles pr on pr.user_id = p.user_id "
                       "where p.user_id = %s", (user_id,)).fetchone()
    return {"field": row["field"], "places": set(row["locations"] or []), "university": row["university"] or ""} if row else None


_NOT_KEPT_APART = (  # neither has blocked the other, and neither has passed on the other
    "not exists (select 1 from peer_blocks b where (b.blocker = %(me)s and b.blocked = {other}) or (b.blocker = {other} and b.blocked = %(me)s)) "
    "and not exists (select 1 from peer_passes s where (s.user_id = %(me)s and s.other_id = {other}) or (s.user_id = {other} and s.other_id = %(me)s))")

_TODAY = "({at} at time zone 'Europe/London')::date = (now() at time zone 'Europe/London')::date"
_PROPOSED_TODAY = (  # new people put before {who} this London day: each proposal of theirs, and each newcomer proposed into a group they were already in
    f"((select count(*) from peer_group_members t where t.user_id = {{who}} and {_TODAY.format(at='t.proposed_at')}) "
    "+ (select count(*) from peer_group_members n join peer_group_members t on t.group_id = n.group_id and t.user_id = {who} "
    f"where n.user_id <> {{who}} and n.proposed_at > t.proposed_at and {_TODAY.format(at='n.proposed_at')}))")


def proposed_today(conn, user_id) -> int:
    """How many proposals the user has had this London day: groups they were proposed into, and
    newcomers proposed into a group they were already in. From the rows of their own groups."""
    return conn.execute(f"select {_PROPOSED_TODAY.format(who='%(who)s')} as n", {"who": user_id}).fetchone()["n"]


def again_tomorrow(conn, user_id) -> bool:
    """Proposed peers.PROPOSALS_A_DAY times today: nobody new is shown to them until tomorrow."""
    return proposed_today(conn, user_id) >= peers.PROPOSALS_A_DAY


def _candidates(conn, user_id, me: dict) -> list[dict]:
    """Whom the caller could be proposed to: people waiting, and active pairs with room in the
    caller's field. Reads other users' field, places, university and time waited, to choose; none
    of it leaves this module."""
    people = conn.execute(
        "select p.user_id, p.field, p.waiting_since, pr.locations, pr.university "
        "from peer_profiles p join profiles pr on pr.user_id = p.user_id "
        "where p.enabled and p.barred_at is null and p.waiting_since is not null and p.user_id <> %(me)s "
        "and not exists (select 1 from peer_group_members m where m.user_id = p.user_id and m.status in ('proposed', 'accepted')) "
        f"and {_PROPOSED_TODAY.format(who='p.user_id')} < %(cap)s "
        "and " + _NOT_KEPT_APART.format(other="p.user_id"), {"me": user_id, "cap": peers.PROPOSALS_A_DAY}).fetchall()
    found = [{"kind": "person", "id": str(r["user_id"]), "fields": {r["field"]}, "places": set(r["locations"] or []),
              "universities": {r["university"] or ""}, "since": r["waiting_since"]} for r in people]
    rows = conn.execute(
        "select g.id, g.active_since, m.user_id, p.field, pr.locations, pr.university "
        "from peer_groups g join peer_group_members m on m.group_id = g.id and m.status = 'accepted' "
        "join peer_profiles p on p.user_id = m.user_id join profiles pr on pr.user_id = m.user_id "
        "where g.status = 'active' "
        "and (select count(*) from peer_group_members x where x.group_id = g.id and x.status in ('proposed', 'accepted')) = 2 "
        "and not exists (select 1 from peer_group_members x where x.group_id = g.id and x.status = 'proposed') "
        "and not exists (select 1 from peer_group_members x where x.group_id = g.id and x.status in ('proposed', 'accepted') "
        f"and {_PROPOSED_TODAY.format(who='x.user_id')} >= %(cap)s) "  # nobody in it has had today's proposals already
        "and not exists (select 1 from peer_group_members x where x.group_id = g.id and x.status in ('proposed', 'accepted') and not ("
        + _NOT_KEPT_APART.format(other="x.user_id") + "))", {"me": user_id, "cap": peers.PROPOSALS_A_DAY}).fetchall()
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(str(r["id"]), {"kind": "group", "id": str(r["id"]), "fields": set(), "places": set(), "universities": set(),
                                             "since": datetime.combine(r["active_since"] or date.today(), time.min, tzinfo=timezone.utc)})
        g["fields"].add(r["field"])
        g["places"] |= set(r["locations"] or [])
        g["universities"].add(r["university"] or "")
    return found + list(groups.values())


def propose(conn, user_id) -> str | None:
    """If the caller is waiting, propose them to the best person or pair, and return the group.
    Whoever is chosen is locked first; if someone else got there first, the next best is tried.
    Nobody is proposed more than peers.PROPOSALS_A_DAY times in a London day."""
    mine = conn.execute("select enabled, barred_at, waiting_since from peer_profiles where user_id = %s for update", (user_id,)).fetchone()
    if not mine or not mine["enabled"] or mine["barred_at"] or not mine["waiting_since"] or _live(conn, user_id) or again_tomorrow(conn, user_id):
        return None
    me = _me(conn, user_id)
    if not me:  # no profile to match on
        return None
    candidates = _candidates(conn, user_id, me)
    while (best := peers.rank(me, candidates)) is not None:
        candidates.remove(best)
        try:
            with conn.transaction():
                group = _pair(conn, user_id, best["id"]) if best["kind"] == "person" else _join(conn, user_id, best["id"])
        except psycopg.errors.UniqueViolation:
            group = None
        if group:
            return group
    return None


def _pair(conn, user_id, other) -> str | None:
    """A proposal of two. Both keep their place on the list (waiting_since) until they are in an
    active group, so whoever is turned down or left behind does not lose it."""
    if not conn.execute("select 1 from peer_profiles p where p.user_id = %s and p.enabled and p.waiting_since is not null "
                        "and not exists (select 1 from peer_group_members m where m.user_id = p.user_id and m.status in ('proposed', 'accepted')) "
                        "for update skip locked", (other,)).fetchone():
        return None
    group = str(conn.execute("insert into peer_groups (status) values ('proposed') returning id").fetchone()["id"])
    conn.execute("insert into peer_group_members (group_id, user_id, slot) values (%s, %s, 1), (%s, %s, 2)", (group, user_id, group, other))
    return group


def _join(conn, user_id, group) -> str | None:
    if not conn.execute("select 1 from peer_groups where id = %s and status = 'active' for update skip locked", (group,)).fetchone():
        return None
    taken = {m["slot"] for m in _members(conn, group)}
    if len(taken) >= peers.MAX_MEMBERS:
        return None
    slot = min(set(range(1, peers.MAX_MEMBERS + 1)) - taken)
    conn.execute("insert into peer_group_members (group_id, user_id, slot) values (%s, %s, %s)", (group, user_id, slot))
    return str(group)


# ---------- answering, leaving, closing ----------

def _back_on_list(conn, users, *, keep: bool = False) -> list[str]:
    """Those still switched on go back on the list. With `keep`, someone who did nothing wrong (turned
    down by another, or left behind in a proposal) keeps the place they had; otherwise the place is
    at the back. Returns them, for matching."""
    rows = conn.execute("update peer_profiles set waiting_since = case when %s then coalesce(waiting_since, now()) else now() end "
                        "where user_id = any(%s::uuid[]) and enabled and barred_at is null returning user_id",
                        (keep, [str(u) for u in users])).fetchall()
    return [str(r["user_id"]) for r in rows]


def _settle(conn, group_id) -> list[str]:
    """Close a group left without two members (two accepted once active, two live while proposed),
    and send whoever was left in it back to the list, keeping their place. Returns them. Anyone
    still live in it with Peers off or barred is taken out first and not counted."""
    group = conn.execute("select status from peer_groups where id = %s", (group_id,)).fetchone()
    if not group or group["status"] == "closed":
        return []
    live = _members(conn, group_id)
    gone = [m["id"] for m in live if not m["switched_on"]]
    if gone:
        conn.execute("update peer_group_members set status = 'left' where id = any(%s::uuid[])", (gone,))
    live = [m for m in live if m["switched_on"]]
    accepted = [m for m in live if m["status"] == "accepted"]
    if (group["status"] == "active" and len(accepted) >= 2) or (group["status"] == "proposed" and len(live) >= 2):
        return []
    conn.execute("update peer_groups set status = 'closed', closed_at = now() where id = %s", (group_id,))
    conn.execute("update peer_group_members set status = 'left' where group_id = %s and status in ('proposed', 'accepted')", (group_id,))
    return _back_on_list(conn, [m["user_id"] for m in live], keep=True)


def _promote(conn, group_id) -> None:
    """A proposed member everyone live has said yes to (themselves included) is in. A group with two
    in is active, and whoever is in an active group is off the list."""
    live = _members(conn, group_id)
    everyone = {m["user_id"] for m in live}
    for m in live:
        if m["status"] == "proposed" and everyone <= set(m["yes_from"]):
            conn.execute("update peer_group_members set status = 'accepted', joined_at = now() where id = %s", (m["id"],))
    conn.execute("update peer_groups set status = 'active', active_since = (now() at time zone 'Europe/London')::date "
                 "where id = %s and status = 'proposed' and (select count(*) from peer_group_members m where m.group_id = %s "
                 "and m.status = 'accepted') >= 2", (group_id, group_id))
    conn.execute("update peer_profiles p set waiting_since = null from peer_group_members m join peer_groups g on g.id = m.group_id "
                 "where m.group_id = %s and g.status = 'active' and m.status = 'accepted' and p.user_id = m.user_id "
                 "and p.waiting_since is not null", (group_id,))


def _rematch(conn, users) -> None:
    for user in dict.fromkeys(users):
        propose(conn, user)


def _locked_membership(conn, user_id, group_id) -> dict:
    """The caller's live row in a group that is still open, with the group locked; else Gone."""
    group = conn.execute("select status from peer_groups where id = %s for update", (group_id,)).fetchone()
    mine = next((m for m in _members(conn, group_id) if m["user_id"] == str(user_id)), None) if group and group["status"] != "closed" else None
    if not mine:
        raise Gone(group_id)
    return mine


def answer(conn, user_id, group_id, *, yes: bool) -> None:
    """Yes or "Not this time" to a proposal: the caller's own, or, for a member already in, a newcomer's."""
    mine = _locked_membership(conn, user_id, group_id)
    newcomer = next((m for m in _members(conn, group_id) if m["status"] == "proposed" and m["user_id"] != str(user_id)), None)
    if mine["status"] == "proposed":
        asked = mine
    elif newcomer:
        asked = newcomer
    else:
        raise Gone(group_id)
    if yes:
        targets = [m["id"] for m in _members(conn, group_id)] if asked is mine else [asked["id"]]
        conn.execute("update peer_group_members set yes_from = array_append(yes_from, %s::uuid) where id = any(%s::uuid[]) "
                     "and not (%s::uuid = any(yes_from))", (user_id, targets, user_id))
        _promote(conn, group_id)
        return
    if asked is mine:
        _depart(conn, group_id, mine, status="declined")
    else:
        conn.execute("update peer_group_members set status = 'declined' where id = %s", (asked["id"],))
        _pass(conn, user_id, [asked["user_id"]])
    others = _settle(conn, group_id)  # those left behind are matched first and keep their place: they did nothing
    _rematch(conn, others + _back_on_list(conn, [asked["user_id"]], keep=asked is not mine))  # a newcomer turned away keeps theirs too


def leave(conn, user_id, group_id) -> None:
    """Leave a group, or turn down a proposal. The caller goes back on the list for a new group."""
    mine = _locked_membership(conn, user_id, group_id)
    if mine["status"] == "proposed":
        return answer(conn, user_id, group_id, yes=False)
    _depart(conn, group_id, mine, status="left")
    others = _settle(conn, group_id)
    _rematch(conn, others + _back_on_list(conn, [user_id]))


def _untidy(mine: dict, live: list[dict]) -> bool:
    """Whether the caller's group may need tidying: a proposal past its 7 days, someone in it with
    Peers off or barred, or too few left in it."""
    counted = [m for m in live if m["switched_on"]]
    if mine["group_status"] == "active":
        enough = len([m for m in counted if m["status"] == "accepted"]) >= 2
    else:
        enough = len(counted) >= 2
    return not enough or len(counted) < len(live) or any(m["status"] == "proposed" and m["stale"] for m in live)


def tidy(conn, user_id) -> dict:
    """Run before showing the caller where they stand: a proposal unanswered for 7 days lapses (the
    silent pass on each other), a group left short (a login deleted elsewhere) closes, and a caller
    with Peers on but in no group and not waiting goes back on the list. Then match: first whoever
    was sent back having said yes (they keep their place), then whoever stayed silent, then the
    caller if waiting. The group is locked only when something in it may change.

    Returns where the caller stands afterwards: their profile ("me"), their live membership ("mine")
    and that group's live rows ("live")."""
    mine = _live(conn, user_id)
    live = _members(conn, mine["group_id"]) if mine else []
    sent_back, silent, changed = [], set(), False
    if mine and _untidy(mine, live):
        changed, group_id = True, mine["group_id"]
        conn.execute("select id from peer_groups where id = %s for update", (group_id,))
        live = _members(conn, group_id)
        for row in live:
            if row["status"] != "proposed" or not row["stale"]:
                continue
            for m in live:
                if m["user_id"] not in row["yes_from"]:  # this one never answered
                    silent.add(m["user_id"])
                    _pass(conn, m["user_id"], [row["user_id"]] if m["user_id"] != row["user_id"] else [x["user_id"] for x in live])
            said_yes = row["user_id"] in row["yes_from"]
            conn.execute("update peer_group_members set status = %s where id = %s", ("left" if said_yes else "declined", row["id"]))
            sent_back += _back_on_list(conn, [row["user_id"]], keep=said_yes)
        sent_back += _settle(conn, group_id)
        mine = _live(conn, user_id)
    me = get_profile(conn, user_id)
    if me and me["enabled"] and not me["barred_at"] and not me["waiting_since"] and not mine:
        sent_back += _back_on_list(conn, [user_id])
    queue = [u for u in sent_back if u not in silent] + [u for u in sent_back if u in silent]
    if queue or (me and me["enabled"] and not me["barred_at"] and not mine):
        _rematch(conn, queue + [str(user_id)])
        changed = True
    if changed:
        me, mine = get_profile(conn, user_id), _live(conn, user_id)
        live = _members(conn, mine["group_id"]) if mine else []
    return {"me": me, "mine": mine, "live": live}


# ---------- where the caller stands: GET /api/peers and the state read ----------

OPTIONS = {"fields": list(peers.FIELDS.items()), "conduct": list(peers.CONDUCT), "report_reasons": list(peers.REPORT_REASONS.items()),
           "proposals_a_day": peers.PROPOSALS_A_DAY}


def _own_checkin(conn, user_id, group_id, monday: date) -> dict | None:
    row = conn.execute("select id, text from peer_checkins where group_id = %s and user_id = %s and week_start = %s",
                       (group_id, user_id, monday)).fetchone()
    return {"id": str(row["id"]), "text": row["text"]} if row else None


def status(conn, user_id) -> dict:
    """Off, waiting, proposed or in a group, with what the caller may see of the others. Every
    detail about another user in it comes from peer_view. `appears_as` is the caller's own."""
    now = tidy(conn, user_id)
    me, mine, live = now["me"], now["mine"], now["live"]
    out = {"status": "off", "field": None, "contact_link": None, "barred": False, "waiting_since": None, "again_tomorrow": False,
           "appears_as": appears_as(conn, user_id), "proposal": None, "group": None, "nudges": [], "options": OPTIONS}
    if me:
        out |= {"field": me["field"], "contact_link": me["contact_link"], "barred": bool(me["barred_at"]), "waiting_since": me["waiting_since"]}
    if not me or not me["enabled"]:
        return out

    def waiting():
        return out | {"status": "waiting", "again_tomorrow": again_tomorrow(conn, user_id)}
    if not mine:
        return waiting()
    clock = _clock(conn)
    others = [m for m in live if m["user_id"] != str(user_id)]
    if mine["status"] == "proposed":
        views = [v for m in others if (v := peer_view(conn, user_id, m["user_id"], clock=clock))]
        if not views:  # nobody in it can be seen any more; it lapses or closes on a later visit
            return waiting()
        return out | {"status": "proposed", "proposal": {"group_id": mine["group_id"], "members": views,
                                                         "said_yes": str(user_id) in mine["yes_from"], "expires_on": mine["expires_on"]}}
    nudged = _nudged_today(conn, user_id)
    members = [v | {"nudged_today": m["user_id"] in nudged} for m in others
               if m["status"] == "accepted" and (v := peer_view(conn, user_id, m["user_id"], clock=clock))]
    newcomer = None
    if (row := next((m for m in others if m["status"] == "proposed"), None)) and (v := peer_view(conn, user_id, row["user_id"], clock=clock)):
        newcomer = v | {"said_yes": str(user_id) in row["yes_from"], "expires_on": row["expires_on"]}
    weekly = _weekly(conn, user_id, clock["today"])
    together = [(weekly["streak"], weekly["all_met"])] + [(v["streak"], v["progress"]["met"] == v["progress"]["of"]) for v in members]
    return out | {"status": "group", "nudges": _nudges_received(conn, user_id, clock), "group": {
        "id": mine["group_id"], "members": members, "newcomer": newcomer,
        "me": {"progress": weekly["progress"], "streak": weekly["streak"], "checkin": _own_checkin(conn, user_id, mine["group_id"], clock["monday"])},
        "streak": peers.group_streak(together, mine["active_since"] or clock["today"], clock["today"])}}


# ---------- check-ins, nudges and the contact link ----------

class AlreadyNudged(Exception):
    """One nudge from one person to another per London day."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


def _in_group(conn, user_id, group_id) -> dict:
    """The caller's membership, when they are in that active group; else Gone."""
    mine = _live(conn, user_id)
    if not mine or mine["group_id"] != str(group_id) or mine["status"] != "accepted" or mine["group_status"] != "active":
        raise Gone(group_id)
    return mine


def set_checkin(conn, user_id, group_id, text: str) -> None:
    """This week's line ("What is your focus this week?"). A second one in the same week replaces the first."""
    _in_group(conn, user_id, group_id)
    conn.execute("insert into peer_checkins (group_id, user_id, week_start, text) values (%s, %s, %s, %s) "
                 "on conflict (group_id, user_id, week_start) do update set text = excluded.text, updated_at = now()",
                 (group_id, user_id, week_start(conn), text))


def nudge(conn, user_id, group_id, member) -> str:
    """A nudge with fixed wording to a member who is in the caller's group. Returns their first name."""
    _in_group(conn, user_id, group_id)
    row = conn.execute("select user_id from peer_group_members where id = %s and group_id = %s and status = 'accepted'",
                       (member, group_id)).fetchone()
    view = peer_view(conn, user_id, row["user_id"]) if row else None
    if not view or "progress" not in view:
        raise Gone(member)
    sent = conn.execute("insert into peer_nudges (group_id, from_user, to_user, on_day) "
                        "values (%s, %s, %s, (now() at time zone 'Europe/London')::date) on conflict do nothing returning id",
                        (group_id, user_id, row["user_id"])).fetchone()
    if not sent:
        raise AlreadyNudged(view["first_name"])
    return view["first_name"]


def _nudged_today(conn, user_id) -> set[str]:
    """Whom the caller has nudged today: their own rows."""
    return {str(r["to_user"]) for r in conn.execute(
        "select to_user from peer_nudges where from_user = %s and on_day = (now() at time zone 'Europe/London')::date", (user_id,))}


def _nudges_received(conn, user_id, clock: dict) -> list[dict]:
    """This London week's nudges to the caller, one line per sender, from members still in their
    group (each shown only through peer_view). No date: when a member acted is never shown."""
    rows = conn.execute("select from_user from peer_nudges where to_user = %s and on_day >= %s "
                        "group by from_user order by max(at) desc", (user_id, clock["monday"])).fetchall()
    received = []
    for r in rows:
        view = peer_view(conn, user_id, r["from_user"], clock=clock)
        if view and "progress" in view:
            received.append({"member": view["member"], "first_name": view["first_name"], "text": peers.NUDGE.format(name=view["first_name"])})
    return received


def set_contact_link(conn, user_id, link: str | None) -> None:
    """The caller's LinkedIn or WhatsApp link, or None to clear it. Checked here as well as at the
    route (ValueError), since it becomes a link other users click."""
    me = get_profile(conn, user_id)
    if not me or not me["enabled"]:
        raise Gone(user_id)
    conn.execute("update peer_profiles set contact_link = %s where user_id = %s", (peers.contact_link(link) if link else None, user_id))


# ---------- block and report ----------

def _visible(conn, user_id, member) -> tuple[str, str]:
    """(their user id, the group) for a member the caller can currently see; else Gone."""
    row = conn.execute("select user_id, group_id from peer_group_members where id = %s and status in ('proposed', 'accepted')",
                       (member,)).fetchone()
    if not row or not peer_view(conn, user_id, row["user_id"]):
        raise Gone(member)
    return str(row["user_id"]), str(row["group_id"])


def block(conn, user_id, member) -> None:
    """Block and leave: the two are never shown to or matched with each other again. On a
    proposal it is a "no"; in a group the caller leaves and the others stay together."""
    other, group_id = _visible(conn, user_id, member)
    conn.execute("insert into peer_blocks (blocker, blocked) values (%s, %s) on conflict do nothing", (user_id, other))
    mine = _locked_membership(conn, user_id, group_id)
    if mine["status"] == "proposed":
        answer(conn, user_id, group_id, yes=False)
    elif other in {m["user_id"] for m in _members(conn, group_id) if m["status"] == "proposed"}:
        answer(conn, user_id, group_id, yes=False)  # a newcomer the caller blocks is turned away; the caller stays
    else:
        leave(conn, user_id, group_id)


def report(conn, user_id, *, member, reason: str, details: str = "", checkin_id=None) -> None:
    """Stored for the owner to review. A reported check-in is hidden from the reporter at once, and
    its text is copied so editing or deleting it later does not remove the evidence."""
    other, group_id = _visible(conn, user_id, member)
    line = None
    if checkin_id:
        line = conn.execute("select text from peer_checkins where id = %s and user_id = %s and group_id = %s",
                            (checkin_id, other, group_id)).fetchone()
        if not line:
            raise Gone(checkin_id)
    conn.execute("insert into peer_reports (reporter, about_user, group_id, checkin_id, checkin_text, reason, details) "
                 "values (%s, %s, %s, %s, %s, %s, %s)", (user_id, other, group_id, checkin_id, line["text"] if line else None, reason, details))


# ---------- the owner's tools: scripts/peer_reports.py only, never a route ----------

def open_reports(conn) -> list[dict]:
    """Every report not yet handled, oldest first, with how many open reports there are about the same person."""
    rows = conn.execute("select r.id, r.at, r.reporter, r.about_user, r.reason, r.details, r.checkin_text, "
                        "(select count(*) from peer_reports x where x.about_user = r.about_user and not x.handled) as about_them "
                        "from peer_reports r where not r.handled order by r.at, r.id").fetchall()
    return [_str(r) | {"reason": peers.REPORT_REASONS.get(r["reason"], r["reason"])} for r in rows]


def mark_handled(conn, report_id) -> bool:
    return conn.execute("update peer_reports set handled = true where id = %s and not handled returning id", (report_id,)).fetchone() is not None


def bar(conn, user_id) -> bool:
    """Switch the user's Peers off now and stop them switching it on again. False when no account
    has that id."""
    if not conn.execute("select 1 from auth.users where id = %s", (user_id,)).fetchone():
        return False
    leave_all(conn, user_id)
    conn.execute("insert into peer_profiles (user_id, barred_at) values (%s, now()) "
                 "on conflict (user_id) do update set barred_at = now(), enabled = false, waiting_since = null", (user_id,))
    return True
