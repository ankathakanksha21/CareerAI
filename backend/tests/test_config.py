import pytest

import config


@pytest.fixture(autouse=True)
def no_env_file(monkeypatch, tmp_path):
    """Point config at a missing .env so only monkeypatched variables are visible."""
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "none")
    for name in ("SUPABASE_URL", "DAILY_AI_LIMIT", "DAILY_VOICE_LIMIT", "DAILY_RESEARCH_LIMIT", "REED_API_KEY", "CRON_SECRET",
                 "COMPANIES_HOUSE_API_KEY", "SEARCH_PROVIDER", "SEARCH_API_KEY"):
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


RESEARCH = {"COMPANIES_HOUSE_API_KEY": "ch-key", "SEARCH_PROVIDER": "tavily", "SEARCH_API_KEY": "tvly-key"}


def test_research_needs_all_three_settings(monkeypatch):
    for name, value in RESEARCH.items():
        monkeypatch.setenv(name, value)
    assert config.research_configured() is True
    assert (config.companies_house_key(), config.search_key()) == ("ch-key", "tvly-key")
    for name in RESEARCH:
        monkeypatch.delenv(name)
        assert config.research_configured() is False
        monkeypatch.setenv(name, RESEARCH[name])
    monkeypatch.setenv("SEARCH_PROVIDER", "brave")  # only Tavily is built
    assert config.research_configured() is False


def test_research_limit_defaults_to_5(monkeypatch):
    assert config.daily_limit("research") == 5
    monkeypatch.setenv("DAILY_RESEARCH_LIMIT", "2")
    assert config.daily_limit("research") == 2
