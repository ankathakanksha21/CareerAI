"""Settings from the environment, then backend/.env. The file is read on every call, so
edits (for example agent IDs written by setup_agents.py) apply without restarting the server."""
import os
from pathlib import Path

from dotenv import dotenv_values

ENV_PATH = Path(__file__).parent / ".env"
DAILY_LIMIT_DEFAULTS = {"ai": 40, "voice": 3, "research": 5}


def env(name: str, default: str = "") -> str:
    values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    value = (os.environ.get(name) or values.get(name) or default).strip()
    return "" if value.startswith("your-") else value  # unfilled .env.example placeholder


def bedrock_region() -> str:
    # AWS_REGION is reserved on Vercel (set to the function region), so BEDROCK_REGION wins there
    return env("BEDROCK_REGION") or env("AWS_REGION")


def llm_configured() -> bool:
    return bool(bedrock_region() and env("BEDROCK_MODEL_ID"))


def voice_configured(agent: str) -> bool:
    key = {"onboarding": "ELEVENLABS_ONBOARDING_AGENT_ID", "interviewer": "ELEVENLABS_INTERVIEWER_AGENT_ID"}[agent]
    return bool(env("ELEVENLABS_API_KEY") and env(key))


def jobs_configured() -> bool:
    """Job search needs a Reed API key."""
    return bool(env("REED_API_KEY"))


def cron_secret() -> str:
    """Shared with the scheduler that reloads the sponsor register. Empty means nobody may call it."""
    return env("CRON_SECRET")


def github_token() -> str:
    """Optional. Lifts GitHub's allowance from 60 requests an hour for each server address to 5,000."""
    return env("GITHUB_TOKEN")


def companies_house_key() -> str:
    return env("COMPANIES_HOUSE_API_KEY")


def search_key() -> str:
    return env("SEARCH_API_KEY")


def research_configured() -> bool:
    """Interview prep needs Companies House and a web search service. Only Tavily is built."""
    return bool(companies_house_key() and env("SEARCH_PROVIDER").lower() == "tavily" and search_key())


def supabase_url() -> str:
    return env("SUPABASE_URL").rstrip("/")


def daily_limit(kind: str) -> int:
    """How many "ai" actions, "voice" sessions or "research" uses (a newly researched company) one user may start per day."""
    raw = env(f"DAILY_{kind.upper()}_LIMIT")
    return int(raw) if raw.isdigit() else DAILY_LIMIT_DEFAULTS[kind]
