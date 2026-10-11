"""One call path for every Bedrock model, through the Mantle endpoint.

anthropic.* model IDs go through AnthropicBedrockMantle (Messages API). Any other
provider prefix goes to the OpenAI-compatible surface on the same Mantle host,
because the Messages surface only serves Claude models. The model ID comes from
BEDROCK_MODEL_ID, so swapping models is a settings edit. If that model is refused
(403 or 404) and BEDROCK_FALLBACK_MODEL_ID is set, the request is tried once there.
"""
import json
import re

import anthropic
import httpx
from anthropic import AnthropicBedrockMantle

from config import bedrock_region, env

REFUSED = (403, 404)  # no access to the model, or no such model: worth trying the fallback


class LLMNotConfigured(Exception):
    pass


def _call(model: str, system: str, user: str, max_tokens: int) -> str:
    """One request to one model."""
    region, key = bedrock_region(), env("BEDROCK_API_KEY")
    if model.startswith("anthropic."):
        # api_key=None falls back to the standard AWS credential chain (SigV4)
        client = AnthropicBedrockMantle(aws_region=region, api_key=key or None, timeout=60)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")

    if not key:
        raise LLMNotConfigured("Non-Claude Mantle models need BEDROCK_API_KEY")
    r = httpx.post(
        f"https://bedrock-mantle.{region}.api.aws/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _status(error: Exception) -> int | None:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    if isinstance(error, anthropic.APIStatusError):
        return error.status_code
    return None


def complete(system: str, user: str, max_tokens: int = 1500) -> str:
    model = env("BEDROCK_MODEL_ID")
    if not (bedrock_region() and model):
        raise LLMNotConfigured("Set BEDROCK_REGION and BEDROCK_MODEL_ID in backend/.env")
    try:
        return _call(model, system, user, max_tokens)
    except (httpx.HTTPStatusError, anthropic.APIStatusError) as e:
        fallback = env("BEDROCK_FALLBACK_MODEL_ID")
        if _status(e) in REFUSED and fallback and fallback != model:
            return _call(fallback, system, user, max_tokens)
        raise


def strip_reasoning(text: str) -> str:
    """Drop a reasoning model's <think> block, which can contain braces that are not the answer."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"<think>.*", "", text, flags=re.S)  # block never closed: nothing after it is an answer
    if "</think>" in text:  # opening tag dropped by the server
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


def complete_json(system: str, user: str, max_tokens: int = 1500):
    """Ask for JSON only and parse the first JSON object or array in the reply."""
    text = complete(system + "\n\nReply with valid JSON only. No prose, no markdown fences.", user, max_tokens)
    text = re.sub(r"^```(?:json)?|```$", "", strip_reasoning(text), flags=re.M).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("No JSON in model reply")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start : end + 1])
