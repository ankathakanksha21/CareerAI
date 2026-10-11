"""Settings from the environment, then backend/.env. The file is read on every call, so
edits (for example agent IDs written by setup_agents.py) apply without restarting the server."""
import os
from pathlib import Path

from dotenv import dotenv_values

ENV_PATH = Path(__file__).parent / ".env"
DAILY_LIMIT_DEFAULTS = {"ai": 40, "voice": 3}


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


def supabase_url() -> str:
    return env("SUPABASE_URL").rstrip("/")


def daily_limit(kind: str) -> int:
    """How many "ai" actions or "voice" sessions one user may start per day."""
    raw = env(f"DAILY_{kind.upper()}_LIMIT")
    return int(raw) if raw.isdigit() else DAILY_LIMIT_DEFAULTS[kind]
