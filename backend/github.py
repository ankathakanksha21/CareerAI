"""GitHub's public API with no login: a user's own public repositories, and one README.

Everything GitHub-specific stays in this file. Any failure is a GitHubError carrying the
message to show and the status to answer with. Without GITHUB_TOKEN, GitHub allows 60 requests
an hour for each server address; with one, 5,000. The token travels only in the request's
authorisation header and never appears in an error or a log line."""
import logging
import re
from datetime import date, datetime

import httpx

from config import github_token
from cvfile import clean

log = logging.getLogger("github")

API = "https://api.github.com"
SITE = "https://github.com/"
USERNAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"  # GitHub's own rule. Also keeps anything odd out of the address
REPO = r"[A-Za-z0-9._-]{1,100}"
LISTED = 100          # the most GitHub returns per call; nobody picks from more
README_CHARS = 6_000
TIMEOUT_S = 10

NO_USER = "No GitHub user with that name"
BUSY = "GitHub is busy. Try again in a few minutes."
DOWN = "We could not reach GitHub. Try again shortly."


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S)


def _get(path: str, accept: str, params: dict | None = None) -> httpx.Response:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "uk-career-navigator"}
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = failed = None
    try:
        with _client() as client:
            r = client.get(API + path, params=params, headers=headers)
    except httpx.HTTPError as e:
        failed = type(e).__name__
    if failed:  # raised out here so the original error, which holds the request and its token, is not attached
        log.warning("GitHub request failed: %s", failed)
        raise GitHubError(502, DOWN)
    out_of_requests = r.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in r.headers
    if r.status_code == 429 or (r.status_code == 403 and out_of_requests):
        raise GitHubError(429, BUSY)
    return r


def _pushed(value) -> date | None:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def repos(username: str) -> list[dict]:
    """The user's public repositories that are their own work (no forks), most recently pushed first."""
    if not re.fullmatch(USERNAME, username or ""):
        raise GitHubError(404, NO_USER)
    r = _get(f"/users/{username}/repos", "application/vnd.github+json", {"type": "owner", "sort": "pushed", "per_page": LISTED})
    if r.status_code == 404:
        raise GitHubError(404, NO_USER)
    try:
        listed = r.json() if r.status_code == 200 else None
    except ValueError:
        listed = None
    if not isinstance(listed, list):
        log.warning("GitHub answered %s to a repository list", r.status_code)
        raise GitHubError(502, DOWN)
    found = []
    for item in listed:
        if not isinstance(item, dict) or item.get("fork") or item.get("private"):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not re.fullmatch(REPO, name):
            continue
        link = item.get("html_url")
        stars = item.get("stargazers_count")
        found.append({
            "name": name,
            "description": clean(item["description"]) if isinstance(item.get("description"), str) else "",
            "language": item["language"] if isinstance(item.get("language"), str) else "",
            "stars": stars if isinstance(stars, int) and not isinstance(stars, bool) else 0,
            "pushed_on": _pushed(item.get("pushed_at")),
            "url": link if isinstance(link, str) and link.startswith(SITE) else f"{SITE}{username}/{name}",
        })
    return sorted(found, key=lambda x: x["pushed_on"] or date.min, reverse=True)


def readme(username: str, repo: str) -> str:
    """The start of a repository's README as plain text; empty when it has none."""
    if not re.fullmatch(USERNAME, username or "") or not re.fullmatch(REPO, repo or ""):
        return ""
    r = _get(f"/repos/{username}/{repo}/readme", "application/vnd.github.raw+json")
    if r.status_code == 404:
        return ""
    if r.status_code != 200:
        log.warning("GitHub answered %s to a README request", r.status_code)
        raise GitHubError(502, DOWN)
    return clean(r.text)[:README_CHARS]
