"""The peers rules, as pure functions: contact links, progress, the group streak, inactivity and
the ranking that chooses whom to propose."""
from datetime import date, datetime, timedelta

import pytest

import peers

TODAY = date(2026, 10, 15)  # a Thursday
MONDAY = date(2026, 10, 12)


# ---------- the owner's text ----------

def test_fields_and_conduct_follow_the_copy_rules():
    labels = list(peers.FIELDS.values())
    assert len(labels) == len({x.lower() for x in labels}) == 21
    assert len(peers.CONDUCT) == 6
    for text in (*labels, *peers.CONDUCT, *peers.REPORT_REASONS.values(), peers.NUDGE, peers.BAD_CONTACT_LINK):
        assert "—" not in text


# ---------- contact links ----------

@pytest.mark.parametrize("typed, stored", [
    ("https://www.linkedin.com/in/priya-shah-123/?trk=public_profile", "https://www.linkedin.com/in/priya-shah-123"),
    ("https://uk.linkedin.com/in/priya", "https://www.linkedin.com/in/priya"),
    ("linkedin.com/in/priya", "https://www.linkedin.com/in/priya"),
    ("HTTPS://WWW.LINKEDIN.COM/IN/Priya", "https://www.linkedin.com/in/Priya"),
    ("  https://www.linkedin.com/in/priya_shah#about  ", "https://www.linkedin.com/in/priya_shah"),
    ("https://www.linkedin.com/in/%E5%BC%A0%E4%BC%9F", "https://www.linkedin.com/in/%E5%BC%A0%E4%BC%9F"),
    ("https://wa.me/447700900123?text=hi", "https://wa.me/447700900123"),
    ("wa.me/447700900123", "https://wa.me/447700900123"),
])
def test_contact_link_accepted_and_tidied(typed, stored):
    assert peers.contact_link(typed) == stored


@pytest.mark.parametrize("typed", [
    "http://www.linkedin.com/in/priya",
    "ftp://wa.me/447700900123",
    "javascript:alert(1)",
    "https://www.linkedin.com.evil.test/in/x",
    "https://evil.test/www.linkedin.com/in/x",
    "https://wa.me/447700900123@evil.test",
    "https://user@www.linkedin.com/in/priya",
    "https://www.linkedin.com:8443/in/priya",
    "https://wa.me/+44 7700 900123",
    "https://wa.me/12",
    "https://wa.me/1234567890123456",
    "https://wa.me/07700900123",  # a number written the UK way: the link would open nobody's chat
    "https://www.linkedin.com/company/acme",
    "https://www.linkedin.com/in/ab",
    "https://www.linkedin.com/in/priya/details/experience",
    "https://notlinkedin.com/in/priya",
    "https://chat.whatsapp.com/AbCdEf",
    "",
    "   ",
])
def test_contact_link_refused(typed):
    with pytest.raises(ValueError, match="LinkedIn profile address"):
        peers.contact_link(typed)


# ---------- the name buddies see ----------

@pytest.mark.parametrize("full_name, shown", [("Priya Shah", "Priya"), ("Zhang Wei", "Zhang"), ("  Priya  ", "Priya"), ("", ""), (None, "")])
def test_first_name_is_the_first_word_as_typed(full_name, shown):
    assert peers.first_name(full_name) == shown


# ---------- this week and the streaks ----------

def test_progress_counts_targets_met():
    week = {"applications": 5, "practice": 1, "outreach": 0, "without_cv": 3,
            "goal": {"applications": 5, "practice": 2, "outreach": 0}}
    assert peers.progress(week) == {"met": 2, "of": 3}


def test_progress_all_met_and_none_met():
    goal = {"applications": 1, "practice": 1, "outreach": 1}
    assert peers.progress({"applications": 3, "practice": 1, "outreach": 4, "goal": goal}) == {"met": 3, "of": 3}
    assert peers.progress({"applications": 0, "practice": 0, "outreach": 0, "goal": goal}) == {"met": 0, "of": 3}


@pytest.mark.parametrize("members, active_since, want", [
    ([(1, True), (1, True)], MONDAY + timedelta(days=1), 1),   # active this week, everyone has met their targets
    ([(1, True), (0, False)], MONDAY, 0),                     # active this week, one has not
    ([(5, True), (2, False)], MONDAY - timedelta(weeks=10), 2),  # runs to last week of 4 and 2; this week not all met
    ([(5, True), (3, True)], MONDAY - timedelta(weeks=10), 3),   # runs of 4 and 2, plus this week
    ([(9, True), (9, True)], MONDAY - timedelta(weeks=2), 3),    # only the two weeks the group existed, plus this one
    ([(9, False), (9, False), (0, False)], MONDAY - timedelta(weeks=10), 0),
])
def test_group_streak(members, active_since, want):
    assert peers.group_streak(members, active_since, TODAY) == want


@pytest.mark.parametrize("last_active, joined, want", [
    (None, TODAY - timedelta(days=30), True),
    (None, TODAY - timedelta(days=10), False),               # too new to call inactive
    (TODAY - timedelta(days=20), TODAY - timedelta(days=30), False),
    (TODAY - timedelta(days=21), TODAY - timedelta(days=30), True),
    (TODAY, TODAY - timedelta(days=300), False),
])
def test_inactive_after_three_weeks(last_active, joined, want):
    assert peers.inactive(last_active, joined, TODAY) is want


# ---------- ranking ----------

ME = {"field": "data", "places": {"Leeds", "Remote"}, "university": "Zzqx University"}
LONG_AGO, RECENTLY = datetime(2026, 9, 1), datetime(2026, 10, 14)


def person(name, field="data", places=(), university="", since=RECENTLY):
    return {"kind": "person", "id": name, "fields": {field}, "places": set(places), "universities": {university}, "since": since}


def group(name, fields=("data",), places=(), universities=(), since=RECENTLY):
    return {"kind": "group", "id": name, "fields": set(fields), "places": set(places), "universities": set(universities), "since": since}


def chosen(*candidates):
    best = peers.rank(ME, list(candidates))
    return best and best["id"]


def test_nobody_to_rank():
    assert peers.rank(ME, []) is None


def test_same_field_beats_a_shared_city():
    assert chosen(person("far", places=["York"]), person("near", field="finance", places=["Leeds"])) == "far"


def test_within_a_field_city_then_university_then_waiting_longest():
    assert chosen(person("uni", university="Zzqx University", since=LONG_AGO), person("city", places=[" leeds "])) == "city"
    assert chosen(person("waited", since=LONG_AGO), person("uni", university="zzqx university")) == "uni"
    assert chosen(person("new"), person("waited", since=LONG_AGO)) == "waited"


def test_a_group_nearby_beats_a_person_far_away():
    assert chosen(person("far", since=LONG_AGO), group("pair", places=["Leeds", "York"])) == "pair"


def test_a_person_beats_a_group_when_neither_is_nearby():
    assert chosen(group("pair", since=LONG_AGO), person("someone")) == "someone"


def test_a_group_in_another_field_is_never_chosen():
    assert chosen(group("mixed", fields=("data", "finance"), places=["Leeds"])) is None
    assert chosen(group("theirs", fields=("finance",), places=["Leeds"])) is None


def test_a_different_field_is_the_last_resort():
    assert chosen(person("other", field="law")) == "other"
    assert chosen(person("other far", field="law", since=LONG_AGO), person("other near", field="law", places=["LEEDS"])) == "other near"


def test_remote_is_not_a_shared_city():
    assert chosen(person("remote", places=["Remote"]), person("waited", since=LONG_AGO)) == "waited"
