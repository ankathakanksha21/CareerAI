"""Weeks, goals and streaks: pure functions over the user's own rows."""
from datetime import date, timedelta

import habits

MON = date(2026, 10, 12)  # a Monday; "today" in these tests is the Wednesday of that week
TODAY = MON + timedelta(days=2)
SMALL = {"applications": 1, "practice": 0}


def week(n: int) -> date:
    """The Monday n weeks from MON: week(-1) is the week before."""
    return MON + timedelta(days=7 * n)


def app(day: date, cv: bool = True, **kw) -> dict:
    return {"applied_on": day, "cv_version_id": "cv-1" if cv else None, "stage": "applied"} | kw


def goal(monday: date, applications: int, practice: int) -> dict:
    return {"effective_from": monday, "applications": applications, "practice": practice}


def met(monday: date) -> tuple[list, list]:
    """Exactly the default goal in that week: five applications with a CV, two mock interviews."""
    return [app(monday + timedelta(days=d)) for d in range(5)], [monday + timedelta(days=1), monday + timedelta(days=3)]


def activity(*mondays: date) -> tuple[list, list]:
    apps, practice = [], []
    for m in mondays:
        a, p = met(m)
        apps, practice = apps + a, practice + p
    return apps, practice


def streaks(apps=(), practice=(), goals=(), started=week(-20), today=TODAY) -> dict:
    return habits.streaks(applications=list(apps), practice_days=list(practice), goals=list(goals), started=started, today=today)


# ---------- weeks and goals ----------

def test_monday_of_any_day():
    assert [habits.monday(MON + timedelta(days=d)) for d in range(7)] == [MON] * 7
    assert habits.monday(MON + timedelta(days=7)) == week(1)


def test_weeks_when_the_clocks_change_are_ordinary_weeks():
    assert habits.monday(date(2026, 3, 29)) == date(2026, 3, 23)    # the Sunday the clocks went forward
    assert habits.monday(date(2026, 3, 30)) == date(2026, 3, 30)
    assert habits.monday(date(2026, 10, 25)) == date(2026, 10, 19)  # the Sunday the clocks went back
    goals = [goal(date(2026, 1, 5), **SMALL)]
    spring = [app(date(2026, 3, 29)), app(date(2026, 3, 30))]
    assert streaks(spring, goals=goals, started=date(2026, 3, 1), today=date(2026, 4, 1)) == {"current": 2, "best": 2}
    autumn = [app(date(2026, 10, 25)), app(date(2026, 10, 26))]
    assert streaks(autumn, goals=goals, started=date(2026, 3, 1), today=date(2026, 10, 27)) == {"current": 2, "best": 2}


def test_sunday_counts_in_its_own_week_and_monday_in_the_next():
    sunday = week(-1) + timedelta(days=6)
    assert habits.week_counts(week(-1), [app(sunday)], [])["applications"] == 1
    assert habits.week_counts(MON, [app(sunday)], [sunday])["applications"] == 0
    assert habits.week_counts(MON, [app(MON)], [MON]) == {"applications": 1, "practice": 1, "without_cv": 0}


def test_application_without_cv_does_not_count():
    counts = habits.week_counts(MON, [app(MON, cv=False), app(MON)], [])
    assert (counts["applications"], counts["without_cv"]) == (1, 1)


def test_goal_for_a_week_is_the_latest_that_had_started():
    goals = [goal(week(-4), 3, 1), goal(week(-1), 4, 2)]
    assert habits.goal_for(week(-6), goals) == habits.DEFAULT_GOAL
    assert habits.goal_for(week(-2), goals) == {"applications": 3, "practice": 1}
    assert habits.goal_for(MON, goals) == {"applications": 4, "practice": 2}


def test_first_goal_applies_this_week():
    assert habits.goal_starts(TODAY, []) == MON


def test_goal_change_applies_from_next_monday_and_leaves_earlier_weeks():
    goals = [goal(MON, 3, 1)]
    assert habits.goal_starts(MON + timedelta(days=6), goals) == week(1)  # set on the Sunday: still next Monday
    changed = goals + [goal(week(1), **SMALL)]
    assert habits.goal_for(MON, changed) == {"applications": 3, "practice": 1}
    assert habits.goal_for(week(1), changed) == SMALL


# ---------- streaks ----------

def test_no_activity_is_zero():
    assert streaks() == {"current": 0, "best": 0}


def test_no_account_is_zero():
    assert streaks(*activity(week(-1)), started=None) == {"current": 0, "best": 0}


def test_three_met_weeks_then_a_missed_week_is_zero():
    assert streaks(*activity(week(-4), week(-3), week(-2))) == {"current": 0, "best": 3}


def test_met_current_week_extends():
    assert streaks(*activity(week(-2), week(-1), MON)) == {"current": 3, "best": 3}


def test_unmet_current_week_in_progress_does_not_break():
    apps, practice = activity(week(-2), week(-1))
    assert streaks(apps + [app(MON)], practice) == {"current": 2, "best": 2}


def test_exactly_at_goal_is_met_and_one_short_is_not():
    apps, practice = met(week(-1))
    assert streaks(apps, practice)["current"] == 1
    assert streaks(apps[1:], practice)["current"] == 0
    assert streaks(apps, practice[1:])["current"] == 0


def test_lowering_the_goal_today_cannot_make_past_weeks_met():
    apps = [app(week(n)) for n in range(-4, 1)]  # one application with a CV in each of the last five weeks
    chosen = [goal(week(-8), 5, 2)]
    lowered = chosen + [goal(habits.goal_starts(TODAY, chosen), **SMALL)]
    assert streaks(apps, goals=lowered)["current"] == 0
    # a first goal applies this week, which can only count this week
    first = [goal(habits.goal_starts(TODAY, []), **SMALL)]
    assert streaks(apps, goals=first) == {"current": 1, "best": 1}


def test_weeks_before_the_account_do_not_count():
    apps, practice = activity(week(-3), week(-2), week(-1))
    assert streaks(apps, practice, started=week(-1) + timedelta(days=4)) == {"current": 1, "best": 1}


def test_best_streak_survives_a_break():
    assert streaks(*activity(week(-6), week(-5), week(-4), week(-2), week(-1))) == {"current": 2, "best": 3}


# ---------- this week ----------

def test_this_week_counts_against_its_goal():
    apps = [app(MON), app(MON, cv=False), app(week(-1))]
    week_now = habits.this_week(applications=apps, practice_days=[TODAY], goals=[], today=TODAY)
    assert week_now == {"week_of": MON, "applications": 1, "practice": 1, "without_cv": 1, "goal": habits.DEFAULT_GOAL,
                        "met": False, "next_goal": None}


def test_next_goal_shown_only_when_it_differs():
    set_before = [goal(week(-2), 3, 1)]
    assert habits.this_week(applications=[], practice_days=[], goals=set_before, today=TODAY)["next_goal"] is None
    pending = set_before + [goal(week(1), 4, 1)]
    assert habits.this_week(applications=[], practice_days=[], goals=pending, today=TODAY)["next_goal"] == {"applications": 4, "practice": 1}


# ---------- follow-ups due ----------

def tracked(stage="applied", applied_on=week(-1), follow_up_on=None, **kw) -> dict:
    return {"id": "app-1", "company": "Zzqx Holdings Ltd", "role": "Role A", "stage": stage, "applied_on": applied_on,
            "follow_up_on": follow_up_on, "cv_version_id": None, "rejected_at_stage": None} | kw


def event(to_stage: str, day: date, from_stage=None, application_id="app-1") -> dict:
    return {"application_id": application_id, "from_stage": from_stage, "to_stage": to_stage, "day": day}


def test_follow_up_due_on_the_day():
    due = habits.follow_ups_due([tracked(follow_up_on=TODAY)], [], TODAY)
    assert [(f["id"], f["due"], f["quiet_days"]) for f in due] == [("app-1", True, None)]
    assert habits.follow_ups_due([tracked(follow_up_on=TODAY + timedelta(days=1))], [], TODAY) == []


def test_offer_and_rejected_have_no_follow_up_due():
    for stage in ("offer", "rejected", "rejected_after_interview"):
        assert habits.follow_ups_due([tracked(stage=stage, applied_on=TODAY - timedelta(days=60), follow_up_on=TODAY)], [], TODAY) == []


def test_quiet_for_21_days_at_applied():
    assert habits.follow_ups_due([tracked(applied_on=TODAY - timedelta(days=20))], [], TODAY) == []
    quiet = habits.follow_ups_due([tracked(applied_on=TODAY - timedelta(days=21))], [], TODAY)
    assert [(f["due"], f["quiet_days"]) for f in quiet] == [(False, 21)]


def test_quiet_counts_from_the_last_stage_change():
    events = [event("applied", TODAY - timedelta(days=40)), event("screening", TODAY - timedelta(days=30), "applied"),
              event("applied", TODAY - timedelta(days=10), "screening")]
    assert habits.follow_ups_due([tracked(applied_on=TODAY - timedelta(days=40))], events, TODAY) == []


def test_only_an_application_at_applied_goes_quiet():
    assert habits.follow_ups_due([tracked(stage="screening", applied_on=TODAY - timedelta(days=40))], [], TODAY) == []


def test_old_application_without_history_counts_from_date_applied():
    old = habits.follow_ups_due([tracked(applied_on=TODAY - timedelta(days=30), follow_up_on=TODAY - timedelta(days=23))], [], TODAY)
    assert [(f["due"], f["quiet_days"]) for f in old] == [(True, 30)]


# ---------- milestones ----------

def reached(apps=(), events=(), practice_count=0, story_count=0, best_streak=0) -> list:
    return habits.milestones(applications=list(apps), events=list(events), practice_count=practice_count,
                             story_count=story_count, best_streak=best_streak)


def test_milestones_from_data():
    assert reached() == []
    many = lambda n: [tracked(id=f"app-{i}") for i in range(n)]  # noqa: E731
    assert reached(many(1)) == ["applications-1"]
    assert reached(many(9)) == ["applications-1"]
    assert reached(many(10)) == ["applications-1", "applications-10"]
    assert reached(many(49))[-1] == "applications-25"
    assert reached(many(50))[-1] == "applications-50"
    assert reached(practice_count=1) == ["first-mock-interview"]
    assert reached(story_count=5) == [] and reached(story_count=6) == ["story-bank-6"]
    assert reached(best_streak=3) == [] and reached(best_streak=4) == ["streak-4"]
    assert reached(best_streak=8) == ["streak-4", "streak-8"]
    assert reached([tracked(stage="offer")]) == ["applications-1", "first-reply", "first-interview", "first-offer"]
    assert list(habits.MILESTONES) == ["applications-1", "applications-10", "applications-25", "applications-50", "first-reply",
                                       "first-interview", "first-offer", "first-mock-interview", "story-bank-6", "streak-4", "streak-8"]


def test_reply_reached_through_history_counts():
    now_rejected = tracked(stage="rejected", rejected_at_stage="cv")  # wrongly answered, but the history shows an interview
    history = [event("applied", week(-3)), event("interview", week(-2), "applied"), event("rejected", week(-1), "interview")]
    assert reached([now_rejected], history) == ["applications-1", "first-reply", "first-interview"]


def test_rejection_after_a_phone_screen_is_a_reply():
    assert reached([tracked(stage="rejected", rejected_at_stage="screening")]) == ["applications-1", "first-reply"]


# ---------- the weekly plan ----------

PAGES = {"applications", "interview", "profile", "resume", "jobs"}
FINDING = {"id": "cv-none", "title": "T", "action": "Tailor a CV to each job.", "evidence": "0 responses from 4 applications.",
           "link": {"page": "resume", "label": "Tailor a CV"}}
DUE = {"id": "app-1", "company": "Zzqx Holdings Ltd", "role": "Role A", "follow_up_on": TODAY, "due": True, "quiet_days": None}


def plan(**kw) -> list:
    args = dict(follow_ups=[], findings=[], fresh_jobs=0, story_count=6, missing_numbers=0, pages=PAGES,
                week=habits.this_week(applications=[], practice_days=[], goals=[], today=TODAY)) | kw
    return habits.weekly_plan(**args)


def ids(tasks) -> list:
    return [t["id"] for t in tasks]


def test_plan_order():
    assert ids(plan(follow_ups=[DUE], findings=[FINDING], fresh_jobs=3)) == [
        "follow-ups", "finding-cv-none", "new-jobs", "applications", "practice"]
    assert ids(plan(story_count=2, missing_numbers=1)) == ["applications", "practice", "stories", "numbers"]


def test_plan_at_most_five():
    findings = [FINDING | {"id": f"f{i}"} for i in range(4)]
    tasks = plan(follow_ups=[DUE], findings=findings, fresh_jobs=3, story_count=0, missing_numbers=4)
    assert len(tasks) == 5 and ids(tasks)[0] == "follow-ups"


def test_plan_copy():
    tasks = {t["id"]: t for t in plan(follow_ups=[DUE], story_count=4, missing_numbers=1)}
    assert tasks["follow-ups"]["text"] == "Follow up with Zzqx Holdings Ltd"
    assert (tasks["applications"]["text"], tasks["applications"]["why"]) == (
        "Send 5 more applications with a tailored CV", "Your goal is 5 this week and 0 have a CV recorded.")
    assert tasks["practice"]["text"] == "Do 2 more mock interviews"
    assert (tasks["stories"]["text"], tasks["stories"]["page"], tasks["stories"]["tab"]) == ("Write 2 more STAR stories", "interview", "stories")
    assert tasks["numbers"]["text"] == "Add a number to 1 achievement"
    assert all(t["why"] and t["label"] and t["page"] in PAGES for t in tasks.values())
    two = plan(follow_ups=[DUE, DUE | {"id": "app-2", "company": "Zzqx Two"}])
    assert two[0]["text"] == "Follow up on 2 applications"


def test_quiet_applications_alone_are_not_a_follow_up_task():
    assert "follow-ups" not in ids(plan(follow_ups=[DUE | {"due": False, "quiet_days": 25}]))


def test_no_jobs_task_without_the_jobs_page():
    tasks = plan(fresh_jobs=3, pages=PAGES - {"jobs"})
    assert "new-jobs" not in ids(tasks)
    assert next(t for t in tasks if t["id"] == "applications")["page"] == "resume"
    assert next(t for t in plan() if t["id"] == "applications")["page"] == "jobs"


def test_finding_without_a_page_is_not_a_task():
    referral = FINDING | {"id": "network", "link": None}
    timing = FINDING | {"id": "timing", "link": {"page": "jobs", "label": "See new jobs"}}
    assert ids(plan(findings=[referral, timing], pages=PAGES - {"jobs"})) == ["applications", "practice"]


def test_met_goal_gives_no_goal_task():
    apps, practice = met(MON)
    done = habits.this_week(applications=apps, practice_days=practice, goals=[], today=TODAY)
    assert ids(plan(week=done)) == []


def test_six_stories_and_no_missing_numbers_give_no_task():
    tasks = ids(plan(story_count=6, missing_numbers=0))
    assert "stories" not in tasks and "numbers" not in tasks
