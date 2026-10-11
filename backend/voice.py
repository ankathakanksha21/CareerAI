"""ElevenLabs Agents helpers. The API key stays here; the browser only gets a
short-lived conversation token for a WebRTC session."""
import re

import httpx

from config import env

API = "https://api.elevenlabs.io/v1/convai"
AGENT_ENV = {"onboarding": "ELEVENLABS_ONBOARDING_AGENT_ID", "interviewer": "ELEVENLABS_INTERVIEWER_AGENT_ID"}
CONVERSATION_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")  # it goes into a URL path, so nothing else is allowed


def _headers() -> dict:
    return {"xi-api-key": env("ELEVENLABS_API_KEY")}


def conversation_token(agent: str) -> str:
    agent_id = env(AGENT_ENV[agent])
    r = httpx.get(f"{API}/conversation/token", params={"agent_id": agent_id}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def signed_url(agent: str) -> str:
    """WebSocket fallback for browsers or networks that block the WebRTC (LiveKit) host."""
    agent_id = env(AGENT_ENV[agent])
    r = httpx.get(f"{API}/conversation/get-signed-url", params={"agent_id": agent_id}, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()["signed_url"]


def fetch_transcript(conversation_id: str, user_id: str) -> list[dict]:
    """Server-side transcript, used when the browser did not capture one. Only the user who
    started the session may read it: the browser tags every session with their id."""
    if not user_id or not CONVERSATION_ID.fullmatch(conversation_id):
        raise PermissionError("not this user's conversation")
    r = httpx.get(f"{API}/conversations/{conversation_id}", headers=_headers(), timeout=15)
    r.raise_for_status()
    data = r.json()
    start = data.get("conversation_initiation_client_data") or {}
    owners = {data.get("user_id"), start.get("user_id"), (start.get("dynamic_variables") or {}).get("user_id")}
    if user_id not in owners:
        raise PermissionError("not this user's conversation")
    turns = data.get("transcript") or []
    return [{"role": t.get("role"), "message": t.get("message")} for t in turns if t.get("message")]
