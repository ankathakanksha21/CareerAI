"""Web search through Tavily (https://docs.tavily.com): a company's news from the last year, and
pages about its competitors.

Everything Tavily-specific stays in this file. Only the company's name is sent, never anything
about the user. Any failure is a SearchError; the key travels only in the authorisation header and
never appears in an error or a log line."""
import logging
import re
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from config import search_key

log = logging.getLogger("websearch")

API = "https://api.tavily.com/search"
TIMEOUT_S = 15
NEWS_DAYS = 365
MAX_NEWS = 8
MAX_COMPETITORS = 5
SNIPPET_CHARS = 600
LEGAL_FORM = re.compile(r"[\s,]+(ltd\.?|limited|plc|llp|lp|inc\.?)$", re.I)


class SearchError(Exception):
    """The search service could not be reached, refused the request or sent something unreadable."""


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S)


def _search(body: dict) -> list[dict]:
    key = search_key()
    if not key:
        raise SearchError("not configured")
    try:
        with _client() as client:
            r = client.post(API, json=body, headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Search request failed: %s", type(e).__name__)
        raise SearchError(type(e).__name__) from None  # the original error can carry request details
    found = data.get("results") if isinstance(data, dict) else None
    return [x for x in found if isinstance(x, dict)] if isinstance(found, list) else []


def _text(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _date(value) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError):
        return None


def _result(raw: dict) -> dict | None:
    url = _text(raw.get("url"))
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        return None
    return {"title": _text(raw.get("title")), "url": url, "snippet": _text(raw.get("content"))[:SNIPPET_CHARS],
            "published_on": _date(raw.get("published_date"))}


def _plain(company: str) -> str:
    """The name as people write it: no quotes, no "Ltd" or "plc" at the end."""
    return LEGAL_FORM.sub("", " ".join(company.replace('"', " ").split()))


def news(company: str, today: date) -> list[dict]:
    """News naming the company from the last NEWS_DAYS days, as {title, url, snippet, published_on}.
    A result dated before that is left out; one with no date is kept, with published_on None."""
    since = today - timedelta(days=NEWS_DAYS)
    raw = _search({"query": f'"{_plain(company)}"', "topic": "news", "start_date": since.isoformat(),
                   "max_results": MAX_NEWS, "search_depth": "basic", "include_published_date": True})
    found = [r for r in map(_result, raw) if r]
    return [r for r in found if r["published_on"] is None or r["published_on"] >= since]


def competitors(company: str) -> list[dict]:
    """Pages about the company's competitors, in the same shape as news."""
    raw = _search({"query": f"{_plain(company)} competitors", "topic": "general", "country": "united kingdom",
                   "max_results": MAX_COMPETITORS, "search_depth": "basic", "include_published_date": True})
    return [r for r in map(_result, raw) if r]
