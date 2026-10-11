import pytest

import limits
import repo

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def caps(monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "2")
    monkeypatch.setenv("DAILY_VOICE_LIMIT", "1")


def test_under_limit_records(conn, user_a):
    limits.check_and_record(conn, user_a, "ai", "tone")
    assert limits.usage(conn, user_a) == {"ai": {"used": 1, "limit": 2}, "voice": {"used": 0, "limit": 1}}


def test_at_limit_raises_and_does_not_record(conn, user_a):
    limits.check_and_record(conn, user_a, "ai", "tone")
    limits.check_and_record(conn, user_a, "ai", "tailor")
    with pytest.raises(limits.LimitReached) as e:
        limits.check_and_record(conn, user_a, "ai", "tone")
    assert e.value.kind == "ai"
    assert limits.usage(conn, user_a)["ai"]["used"] == 2


def test_kinds_are_separate(conn, user_a):
    limits.check_and_record(conn, user_a, "ai", "tone")
    limits.check_and_record(conn, user_a, "ai", "tone")
    limits.check_and_record(conn, user_a, "voice", "onboarding")
    assert limits.usage(conn, user_a)["voice"]["used"] == 1


def test_users_are_separate(conn, user_a, user_b):
    limits.check_and_record(conn, user_a, "voice", "onboarding")
    limits.check_and_record(conn, user_b, "voice", "onboarding")
    assert limits.usage(conn, user_b)["voice"]["used"] == 1


def test_zero_limit_blocks_everything(conn, user_a, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    assert limits.allowed(conn, user_a, "ai") is False
    with pytest.raises(limits.LimitReached):
        limits.check_and_record(conn, user_a, "ai", "tone")


def test_yesterdays_usage_does_not_count(conn, user_a):
    midnight = "(date_trunc('day', now() at time zone 'Europe/London') at time zone 'Europe/London')"
    conn.execute(f"insert into usage_events (user_id, kind, action, created_at) values (%s, 'ai', 'tone', {midnight} - interval '1 minute')", (user_a,))
    conn.execute(f"insert into usage_events (user_id, kind, action, created_at) values (%s, 'ai', 'tone', {midnight})", (user_a,))
    assert repo.count_usage_today(conn, user_a, "ai") == 1


def test_retry_window_is_free(conn, user_a):
    limits.check_and_record(conn, user_a, "voice", "onboarding")
    limits.check_and_record(conn, user_a, "voice", "onboarding", retry_window_s=120)  # at the cap, but a retry
    assert limits.usage(conn, user_a)["voice"]["used"] == 1


def test_retry_window_expires(conn, user_a):
    limits.check_and_record(conn, user_a, "voice", "onboarding")
    conn.execute("update usage_events set created_at = now() - interval '5 minutes' where user_id = %s", (user_a,))
    with pytest.raises(limits.LimitReached):
        limits.check_and_record(conn, user_a, "voice", "onboarding", retry_window_s=120)


def test_retry_window_only_for_same_action(conn, user_a, monkeypatch):
    monkeypatch.setenv("DAILY_VOICE_LIMIT", "5")
    limits.check_and_record(conn, user_a, "voice", "interviewer")
    limits.check_and_record(conn, user_a, "voice", "onboarding", retry_window_s=120)
    assert limits.usage(conn, user_a)["voice"]["used"] == 2


def test_allowed_does_not_record(conn, user_a):
    assert limits.allowed(conn, user_a, "ai") is True
    assert limits.usage(conn, user_a)["ai"]["used"] == 0
