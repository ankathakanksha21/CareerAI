"""The weekly habits the tracker builds: goals, the weekly streak, follow-ups due, milestones and
the weekly plan. Pure functions over the user's own rows, worked out afresh on every read, so
nothing about them can drift from what the user actually did.

A week runs Monday to Sunday, UK time. Dates come in already as London dates."""
from collections import Counter
from datetime import date, timedelta

DEFAULT_GOAL = {"applications": 5, "practice": 2}
WEEK = timedelta(days=7)


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def goal_for(week: date, goals: list[dict]) -> dict:
    """The goal that applied in the week starting `week`: the latest set from that Monday or
    before, else the defaults."""
    started = [g for g in goals if g["effective_from"] <= week]
    chosen = max(started, key=lambda g: g["effective_from"]) if started else DEFAULT_GOAL
    return {"applications": chosen["applications"], "practice": chosen["practice"]}


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


def week_counts(week: date, applications: list, practice_days: list[date]) -> dict:
    with_cv, without = _counted(applications)
    practice = Counter(monday(d) for d in practice_days)
    return {"applications": with_cv[week], "practice": practice[week], "without_cv": without[week]}


def _met(counts: dict, goal: dict) -> bool:
    return counts["applications"] >= goal["applications"] and counts["practice"] >= goal["practice"]


def streaks(*, applications: list, practice_days: list[date], goals: list[dict], started: date | None, today: date) -> dict:
    """The current streak, in weeks, and the best ever. The current streak is the run of met weeks
    ending last week, plus this week once it is met: a week still in progress never breaks it.
    Weeks before the account existed are not counted."""
    if started is None:
        return {"current": 0, "best": 0}
    with_cv, _ = _counted(applications)
    practice = Counter(monday(d) for d in practice_days)
    met, week = [], monday(started)
    while week <= monday(today):
        met.append(_met({"applications": with_cv[week], "practice": practice[week]}, goal_for(week, goals)))
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


def this_week(*, applications: list, practice_days: list[date], goals: list[dict], today: date) -> dict:
    """This week against its goal, and the goal from next Monday when the user has changed it."""
    week = monday(today)
    goal, following = goal_for(week, goals), goal_for(week + WEEK, goals)
    counts = week_counts(week, applications, practice_days)
    return {"week_of": week, **counts, "goal": goal, "met": _met(counts, goal),
            "next_goal": following if following != goal else None}
