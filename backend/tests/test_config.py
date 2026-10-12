import pytest

import config


@pytest.fixture(autouse=True)
def no_env_file(monkeypatch, tmp_path):
    """Point config at a missing .env so only monkeypatched variables are visible."""
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "none")
    for name in ("SUPABASE_URL", "DAILY_AI_LIMIT", "DAILY_VOICE_LIMIT", "REED_API_KEY", "CRON_SECRET"):
        monkeypatch.delenv(name, raising=False)


def test_supabase_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/")
    assert config.supabase_url() == "https://x.supabase.co"


def test_daily_limit_defaults():
    assert config.daily_limit("ai") == 40
    assert config.daily_limit("voice") == 3


def test_daily_limit_reads_env(monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "5")
    assert config.daily_limit("ai") == 5


def test_daily_limit_bad_value_uses_default(monkeypatch):
    monkeypatch.setenv("DAILY_VOICE_LIMIT", "abc")
    assert config.daily_limit("voice") == 3


def test_environment_wins_over_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DAILY_AI_LIMIT=7\nSUPABASE_URL=https://file.supabase.co\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", env_file)
    assert config.daily_limit("ai") == 7  # the file is used when the environment is silent
    monkeypatch.setenv("DAILY_AI_LIMIT", "9")
    assert config.daily_limit("ai") == 9
    assert config.supabase_url() == "https://file.supabase.co"


def test_jobs_configured_needs_the_reed_key(monkeypatch):
    assert config.jobs_configured() is False
    monkeypatch.setenv("REED_API_KEY", "your-reed-api-key")  # the placeholder from .env.example
    assert config.jobs_configured() is False
    monkeypatch.setenv("REED_API_KEY", "abc123")
    assert config.jobs_configured() is True


def test_cron_secret(monkeypatch):
    assert config.cron_secret() == ""
    monkeypatch.setenv("CRON_SECRET", " s3cret ")
    assert config.cron_secret() == "s3cret"
