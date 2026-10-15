"""The weekly habits the tracker builds: goals, the weekly streak, follow-ups due, milestones and
the weekly plan. Pure functions over the user's own rows, worked out afresh on every read, so
nothing about them can drift from what the user actually did. Since step 6 a week has three
targets: applications with a CV, mock interviews, and messages sent to contacts.

A week runs Monday to Sunday, UK time. Dates come in already as London dates."""
from collections import Counter
from datetime import date, timedelta

from analytics import INTERVIEWED, RESPONDED, plural, responded
from networking import REPLIED

DEFAULT_GOAL = {"applications": 5, "practice": 2}  # until the user sets goals; the outreach target then is the profile's own default
WEEK = timedelta(days=7)
CLOSED = {"offer", "rejected", "rejected_after_interview"}  # an application that has ended: nothing to follow up
STALE_DAYS = 21     # at Applied with no change for this long: suggest moving it to No reply
STORY_TARGET = 6
MAX_TASKS = 5
APPLICATION_COUNTS = (1, 10, 25, 50)
STREAK_WEEKS = (4, 8)
MILESTONES = {  # id: the banner, shown once
    "applications-1": "You logged your first application. From here the tracker can tell you what to fix.",
    "applications-10": "10 applications logged.",
    "applications-25": "25 applications logged.",
    "applications-50": "50 applications logged.",
    "first-reply": "Your first reply from an employer.",
    "first-interview": "Your first interview.",
    "first-offer": "Your first offer. Congratulations.",
    "first-mock-interview": "Your first mock interview is done.",
    "story-bank-6": "Six STAR stories in your bank, enough for most competency questions.",
    "streak-4": "Four weeks in a row at your goal.",
    "streak-8": "Eight weeks in a row at your goal.",
    "first-message-sent": "Your first message to a contact is sent. Most people who reply do so within two weeks.",
    "first-contact-reply": "Your first reply from a contact.",
    "first-chat": "Your first chat with someone in your field is done.",
    "first-referral": "Your first referral offered. Link it to your application.",
}


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def goal_for(week: date, goals: list[dict], default_outreach: int = 0) -> dict:
    """The goal that applied in the week starting `week`: the latest set from that Monday or
    before, else the defaults with the account's own outreach target. A goal saved before the
    outreach target existed asks for no messages, so no week before it changes."""
    started = [g for g in goals if g["effective_from"] <= week]
    if not started:
        return DEFAULT_GOAL | {"outreach": default_outreach}
    chosen = max(started, key=lambda g: g["effective_from"])
    return {"applications": chosen["applications"], "practice": chosen["practice"], "outreach": chosen.get("outreach") or 0}


def goal_starts(today: date, goals: list[dict]) -> date:
    """When a goal set today applies: this week for the first goal a user ever sets, so a new user
    is not judged by defaults they never chose; next Monday for any later change, so a week in
    progress can never be made easier."""
    return monday(today) + (WEEK if goals else timedelta(0))


def _counted(applications: list) -> tuple[Counter, Counter]:
    """Applications per week: those with a CV version recorded, which count toward the goal, and the rest."""
    with_cv, without = Counter(), Counter()
    for a in applications:
        (with_cv if a.get("cv_version_id") else without)[monday(a["applied_on"])] += 1
    return with_cv, without


def week_counts(week: date, applications: list, practice_days: list[date], outreach_days: list[date] = ()) -> dict:
    with_cv, without = _counted(applications)
    practice, outreach = Counter(monday(d) for d in practice_days), Counter(monday(d) for d in outreach_days)
    return {"applications": with_cv[week], "practice": practice[week], "without_cv": without[week], "outreach": outreach[week]}


def _met(counts: dict, goal: dict) -> bool:
    return all(counts[k] >= goal[k] for k in ("applications", "practice", "outreach"))


def streaks(*, applications: list, practice_days: list[date], goals: list[dict], started: date | None, today: date,
            outreach_days: list[date] = (), default_outreach: int = 0) -> dict:
    """The current streak, in weeks, and the best ever. The current streak is the run of met weeks
    ending last week, plus this week once it is met: a week still in progress never breaks it.
    Weeks before the account existed are not counted."""
    if started is None:
        return {"current": 0, "best": 0}
    with_cv, _ = _counted(applications)
    practice, outreach = Counter(monday(d) for d in practice_days), Counter(monday(d) for d in outreach_days)
    met, week = [], monday(started)
    while week <= monday(today):
        counts = {"applications": with_cv[week], "practice": practice[week], "outreach": outreach[week]}
        met.append(_met(counts, goal_for(week, goals, default_outreach)))
        week += WEEK
    if not met:
        return {"current": 0, "best": 0}
    run = best = current = 0
    for ok in met:
        run = run + 1 if ok else 0
        best = max(best, run)
    for ok in reversed(met[:-1]):  # the weeks already over, most recent first
        if not ok:
            break
        current += 1
    return {"current": current + met[-1], "best": best}


def this_week(*, applications: list, practice_days: list[date], goals: list[dict], today: date,
              outreach_days: list[date] = (), default_outreach: int = 0) -> dict:
    """This week against its goal, the goal from next Monday when the user has changed it, and
    whether they have ever chosen an outreach target (until then This week invites them to)."""
    week = monday(today)
    goal, following = goal_for(week, goals, default_outreach), goal_for(week + WEEK, goals, default_outreach)
    counts = week_counts(week, applications, practice_days, outreach_days)
    return {"week_of": week, **counts, "goal": goal, "met": _met(counts, goal),
            "next_goal": following if following != goal else None,
            "outreach_chosen": any(g.get("outreach") is not None for g in goals)}


def follow_ups_due(applications: list, events: list, today: date) -> list[dict]:
    """Open applications whose follow-up date has come, and those still at Applied with no change
    for three weeks, which the user may want to move to No reply. Quiet is counted from the last
    stage change, else from the day it was sent: logging an application late is not a change."""
    last_change = {}
    for e in events:
        if e["from_stage"] is not None:
            last_change[e["application_id"]] = max(e["day"], last_change.get(e["application_id"], e["day"]))
    listed = []
    for a in applications:
        if a["stage"] in CLOSED or a["stage"] == "no_response":  # at No reply the user has stopped waiting
            continue
        due = a["follow_up_on"] is not None and a["follow_up_on"] <= today
        changed = last_change.get(a["id"], a["applied_on"])
        quiet = (today - changed).days if a["stage"] == "applied" and (today - changed).days >= STALE_DAYS else None
        if due or quiet:
            since = a["follow_up_on"] if due else changed + timedelta(days=STALE_DAYS)
            listed.append((since, {"id": a["id"], "company": a["company"], "role": a["role"], "follow_up_on": a["follow_up_on"],
                                   "due": due, "quiet_days": quiet}))
    return [item for _, item in sorted(listed, key=lambda pair: pair[0])]


def milestones(*, applications: list, events: list, practice_count: int, story_count: int, best_streak: int,
               outreach: list = (), contacts: list = ()) -> list[str]:
    """Every milestone the user's data shows they have reached, in MILESTONES order. A reply,
    interview or offer counts if an application is at that stage now or ever passed through it;
    a networking step, if it was recorded or a contact's status shows it."""
    stages = {a["stage"] for a in applications} | {e["to_stage"] for e in events}
    reached = {f"applications-{n}" for n in APPLICATION_COUNTS if len(applications) >= n}
    reached |= {f"streak-{n}" for n in STREAK_WEEKS if best_streak >= n}
    if any(responded(a) for a in applications) or stages & RESPONDED:
        reached.add("first-reply")
    if stages & INTERVIEWED:
        reached.add("first-interview")
    if "offer" in stages:
        reached.add("first-offer")
    if practice_count:
        reached.add("first-mock-interview")
    if story_count >= STORY_TARGET:
        reached.add("story-bank-6")
    kinds, statuses = {row["kind"] for row in outreach}, {c["status"] for c in contacts}
    steps = kinds | statuses
    if "sent" in kinds or statuses - {"to_contact"}:  # a message recorded, or a contact the user has moved on
        reached.add("first-message-sent")
    if steps & REPLIED:
        reached.add("first-contact-reply")
    if "chat_done" in steps:
        reached.add("first-chat")
    if "referral_offered" in steps:
        reached.add("first-referral")
    return [m for m in MILESTONES if m in reached]


def _task(id: str, text: str, why: str, page: str, label: str, tab: str | None = None) -> dict:
    return {"id": id, "text": text, "why": why, "page": page, "tab": tab, "label": label}


def weekly_plan(*, follow_ups: list, findings: list, fresh_jobs: int, week: dict, story_count: int, missing_numbers: int,
                pages: set[str], contact_follow_ups: list = (), to_message: dict | None = None) -> list[dict]:
    """Up to five tasks for this week, built by rules from the user's real state, most pressing
    first. A task that is done is simply not built, so it disappears on the next load. A task is
    never offered for a page this build does not have."""
    tasks = []
    due = [f for f in follow_ups if f["due"]]
    if due:
        text = f"Follow up with {due[0]['company']}" if len(due) == 1 else f"Follow up on {len(due)} applications"
        tasks.append(_task("follow-ups", text, "A short, polite message a week after applying keeps you in mind.", "applications", "See follow-ups"))
    if contact_follow_ups:
        people = contact_follow_ups
        text = f"Follow up with {people[0]['name']}" if len(people) == 1 else f"Follow up with {len(people)} people"
        tasks.append(_task("contact-follow-ups", text, "Two weeks without a reply: one short, friendly follow-up often gets one.",
                           "networking", "Open People", tab="people"))
    for f in findings:
        if f.get("link"):
            tasks.append(_task(f"finding-{f['id']}", f["action"], f["evidence"], f["link"]["page"], f["link"]["label"], tab=f["link"].get("tab")))
    if fresh_jobs:
        tasks.append(_task("new-jobs", f"Look at {plural(fresh_jobs, 'new matching job')} posted in the last 48 hours",
                           "Roles get most of their applications in the first few days.", "jobs", "See jobs"))
    goal, have = week["goal"]["applications"], week["applications"]
    if have < goal:
        jobs = "jobs" in pages
        tasks.append(_task("applications", f"Send {plural(goal - have, 'more application')} with a tailored CV",
                           f"Your goal is {goal} this week and {have} {'has' if have == 1 else 'have'} a CV recorded.",
                           "jobs" if jobs else "resume", "See jobs" if jobs else "Tailor a CV"))
    goal, done = week["goal"]["practice"], week["practice"]
    if done < goal:
        tasks.append(_task("practice", f"Do {plural(goal - done, 'more mock interview')}",
                           f"Your goal is {plural(goal, 'practice session')} this week and you have done {done}.", "interview", "Practise"))
    goal, sent = week["goal"]["outreach"], week["outreach"]
    if sent < goal:
        why = f"Your target is {plural(goal, 'message')} this week and you have sent {sent}."
        if to_message:
            tasks.append(_task("outreach", f"Message {to_message['name']}", why, "networking", "Open People", tab="people"))
        else:
            tasks.append(_task("outreach", "Find someone to message", why, "networking", "Find people", tab="people"))
    if story_count < STORY_TARGET:
        missing = STORY_TARGET - story_count
        tasks.append(_task("stories", f"Write {missing} more STAR {'story' if missing == 1 else 'stories'}",
                           "Six stories cover most of the competency questions UK employers ask.", "interview", "Open stories", tab="stories"))
    if missing_numbers:
        tasks.append(_task("numbers", f"Add a number to {plural(missing_numbers, 'achievement')}",
                           "A result with a figure is what UK employers look for on a CV.", "profile", "Open profile"))
    return [t for t in tasks if t["page"] in pages][:MAX_TASKS]
