"""Weekly goals, the days the user practised, when their account began, and milestones already shown."""
from datetime import date, datetime, timezone

import pytest

import repo

pytestmark = pytest.mark.db


def interview_at(conn, user, when: datetime):
    entry = repo.add_journal_entry(conn, user, type="interview", title="Practice", with_whom="Mock interviewer",
                                   summary="", points=[], actions=[])
    conn.execute("update journal_entries set created_at = %s where id = %s", (when, entry["id"]))


def test_set_goal_twice_for_the_same_monday_keeps_one_row(conn, user_a):
    repo.set_goal(conn, user_a, effective_from=date(2026, 10, 19), applications=5, practice=2)
    saved = repo.set_goal(conn, user_a, effective_from=date(2026, 10, 19), applications=3, practice=1)
    assert (saved["effective_from"], saved["applications"], saved["practice"]) == (date(2026, 10, 19), 3, 1)
    assert [(g["effective_from"], g["applications"]) for g in repo.list_goals(conn, user_a)] == [(date(2026, 10, 19), 3)]


def test_goals_oldest_first(conn, user_a):
    repo.set_goal(conn, user_a, effective_from=date(2026, 10, 19), applications=4, practice=1)
    repo.set_goal(conn, user_a, effective_from=date(2026, 10, 12), applications=5, practice=2)
    assert [g["effective_from"] for g in repo.list_goals(conn, user_a)] == [date(2026, 10, 12), date(2026, 10, 19)]


def test_practice_day_is_the_london_date(conn, user_a):
    interview_at(conn, user_a, datetime(2026, 3, 29, 23, 30, tzinfo=timezone.utc))   # the clocks went forward that day: 00:30 on Monday in London
    interview_at(conn, user_a, datetime(2026, 10, 25, 23, 30, tzinfo=timezone.utc))  # the clocks went back that day: still Sunday in London
    assert sorted(repo.practice_days(conn, user_a)) == [date(2026, 3, 30), date(2026, 10, 25)]


def test_coach_calls_and_imports_are_not_practice(conn, user_a):
    for kind in ("coach", "import"):
        repo.add_journal_entry(conn, user_a, type=kind, title="T", with_whom="", summary="", points=[], actions=[])
    assert repo.practice_days(conn, user_a) == []


def test_account_started_is_the_profiles_london_date(conn, user_a):
    assert repo.account_started(conn, user_a) is None
    repo.get_or_create_profile(conn, user_a, "Test Person")
    conn.execute("update profiles set created_at = %s where user_id = %s", (datetime(2026, 3, 29, 23, 30, tzinfo=timezone.utc), user_a))
    assert repo.account_started(conn, user_a) == date(2026, 3, 30)


def test_milestones_seen_is_a_union(conn, user_a):
    repo.get_or_create_profile(conn, user_a, "Test Person")
    assert repo.mark_milestones_seen(conn, user_a, ["applications-1", "first-reply"]) == ["applications-1", "first-reply"]
    both = ["applications-1", "first-reply", "applications-10"]
    assert repo.mark_milestones_seen(conn, user_a, ["first-reply", "applications-10"]) == both
    assert repo.get_or_create_profile(conn, user_a, "Test Person")["milestones_seen"] == both


def test_user_b_sees_and_changes_none_of_a(conn, user_a, user_b):
    repo.get_or_create_profile(conn, user_a, "Test Person")
    repo.get_or_create_profile(conn, user_b, "Other Person")
    repo.set_goal(conn, user_a, effective_from=date(2026, 10, 19), applications=4, practice=1)
    interview_at(conn, user_a, datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc))
    repo.mark_milestones_seen(conn, user_a, ["applications-1"])
    assert repo.list_goals(conn, user_b) == [] and repo.practice_days(conn, user_b) == []
    assert repo.get_or_create_profile(conn, user_b, "Other Person")["milestones_seen"] == []
    repo.set_goal(conn, user_b, effective_from=date(2026, 10, 19), applications=9, practice=3)
    repo.mark_milestones_seen(conn, user_b, ["first-offer"])
    assert repo.list_goals(conn, user_a)[0]["applications"] == 4
    assert repo.get_or_create_profile(conn, user_a, "Test Person")["milestones_seen"] == ["applications-1"]
