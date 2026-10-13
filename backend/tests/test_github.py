import logging
from datetime import date

import httpx
import pytest

import github

TOKEN = "github-test-token-0000"
# Synthetic values in the shape GitHub returns
REPO = {"name": "delay-report", "description": "Weekly delivery delays report", "language": "Python", "stargazers_count": 3,
        "fork": False, "private": False, "pushed_at": "2026-08-21T15:25:42Z", "html_url": "https://github.com/zzqx-sample/delay-report"}
BUSY = "GitHub is busy. Try again in a few minutes."
DOWN = "We could not reach GitHub. Try again shortly."


@pytest.fixture
def api(monkeypatch, no_env_file):
    """GitHub replaced by a handler: api(lambda request: httpx.Response(...)). Returns the requests made."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def install(handler):
        seen = []

        def record(request):
            seen.append(request)
            return handler(request)
        monkeypatch.setattr(github, "_client", lambda: httpx.Client(transport=httpx.MockTransport(record)))
        return seen
    return install


def listing(*repos):
    return lambda request: httpx.Response(200, json=list(repos))


def failure(call) -> github.GitHubError:
    with pytest.raises(github.GitHubError) as e:
        call()
    return e.value


# ---------- a user's repositories ----------

def test_repos_asks_for_the_users_own_repositories_newest_first(api):
    seen = api(listing(REPO))
    github.repos("zzqx-sample")
    request = seen[0]
    assert request.url.host == "api.github.com" and request.url.path == "/users/zzqx-sample/repos"
    assert dict(request.url.params) == {"type": "owner", "sort": "pushed", "per_page": "100"}
    assert request.headers["accept"] == "application/vnd.github+json" and request.headers["x-github-api-version"] == "2022-11-28"
    assert "authorization" not in request.headers


def test_a_token_is_sent_when_one_is_set(api, monkeypatch):
    seen = api(listing(REPO))
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    github.repos("zzqx-sample")
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"


def test_repos_parses_a_repository(api):
    api(listing(REPO))
    assert github.repos("zzqx-sample") == [{
        "name": "delay-report", "description": "Weekly delivery delays report", "language": "Python", "stars": 3,
        "pushed_on": date(2026, 8, 21), "url": "https://github.com/zzqx-sample/delay-report"}]


def test_forks_and_private_repositories_are_left_out(api):
    api(listing(REPO | {"name": "a-fork", "fork": True}, REPO | {"name": "hidden", "private": True}, REPO))
    assert [r["name"] for r in github.repos("zzqx-sample")] == ["delay-report"]


def test_missing_details_become_empty_not_errors(api):
    api(listing({"name": "bare", "fork": False}))
    assert github.repos("zzqx-sample") == [{"name": "bare", "description": "", "language": "", "stars": 0, "pushed_on": None,
                                            "url": "https://github.com/zzqx-sample/bare"}]


def test_most_recently_pushed_first(api):
    api(listing(REPO | {"name": "older", "pushed_at": "2025-01-01T00:00:00Z"}, REPO | {"name": "never", "pushed_at": None}, REPO))
    assert [r["name"] for r in github.repos("zzqx-sample")] == ["delay-report", "older", "never"]


@pytest.mark.parametrize("link", ["https://evil.example/zzqx-sample/delay-report", "javascript:alert(1)", "http://github.com/zzqx-sample/delay-report", None])
def test_a_link_that_is_not_on_github_is_rebuilt(api, link):
    api(listing(REPO | {"html_url": link}))
    assert github.repos("zzqx-sample")[0]["url"] == "https://github.com/zzqx-sample/delay-report"


@pytest.mark.parametrize("name", ["bad name", "bad/name", "", None, "x" * 101])
def test_a_repository_with_an_impossible_name_is_skipped(api, name):
    api(listing(REPO | {"name": name}, REPO))
    assert [r["name"] for r in github.repos("zzqx-sample")] == ["delay-report"]


def test_an_unknown_user(api):
    api(lambda request: httpx.Response(404, json={"message": "Not Found"}))
    error = failure(lambda: github.repos("zzqx-nobody"))
    assert error.status == 404 and error.message == "No GitHub user with that name" and str(error) == error.message


@pytest.mark.parametrize("username", ["../orgs/zzqx", "two words", "-leading", "x" * 40, "", "a?b=c"])
def test_a_name_github_would_never_allow_is_not_sent(api, username):
    seen = api(listing(REPO))
    assert failure(lambda: github.repos(username)).status == 404
    assert seen == []


@pytest.mark.parametrize("reply", [
    httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "API rate limit exceeded"}),
    httpx.Response(429, json={"message": "Too many requests"}),
    httpx.Response(403, headers={"retry-after": "60"}, json={"message": "secondary rate limit"}),
])
def test_out_of_requests_is_busy(api, reply):
    api(lambda request: reply)
    error = failure(lambda: github.repos("zzqx-sample"))
    assert error.status == 429 and error.message == BUSY
    error = failure(lambda: github.readme("zzqx-sample", "delay-report"))
    assert error.status == 429 and error.message == BUSY


@pytest.mark.parametrize("reply", [
    httpx.Response(500, text="oops"), httpx.Response(403, json={"message": "blocked"}), httpx.Response(200, text="<html>not json</html>"),
    httpx.Response(200, json={"message": "an object, not a list"}),
])
def test_anything_else_unexpected_is_could_not_reach(api, reply):
    api(lambda request: reply)
    error = failure(lambda: github.repos("zzqx-sample"))
    assert error.status == 502 and error.message == DOWN


def test_a_timeout_is_could_not_reach(api):
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)
    api(slow)
    assert failure(lambda: github.repos("zzqx-sample")).message == DOWN
    assert failure(lambda: github.readme("zzqx-sample", "delay-report")).message == DOWN


# ---------- one README ----------

def test_readme_asks_for_the_raw_text(api):
    seen = api(lambda request: httpx.Response(200, text="# Delay report\nA weekly report in SQL."))
    assert github.readme("zzqx-sample", "delay-report") == "# Delay report\nA weekly report in SQL."
    assert seen[0].url.path == "/repos/zzqx-sample/delay-report/readme"
    assert seen[0].headers["accept"] == "application/vnd.github.raw+json"


def test_a_repository_with_no_readme_gives_nothing(api):
    api(lambda request: httpx.Response(404, json={"message": "Not Found"}))
    assert github.readme("zzqx-sample", "delay-report") == ""


def test_a_long_readme_is_cut(api):
    api(lambda request: httpx.Response(200, text="word " * 5000))
    assert len(github.readme("zzqx-sample", "delay-report")) <= github.README_CHARS


def test_a_readme_is_cleaned_of_characters_the_database_refuses(api):
    api(lambda request: httpx.Response(200, text="Delay\x00 report\r\n\r\n\r\n\r\nin SQL"))
    assert github.readme("zzqx-sample", "delay-report") == "Delay report\n\nin SQL"


@pytest.mark.parametrize("repo", ["../../users/zzqx", "bad name", ""])
def test_a_readme_for_an_impossible_name_is_not_requested(api, repo):
    seen = api(lambda request: httpx.Response(200, text="text"))
    assert github.readme("zzqx-sample", repo) == "" and seen == []


# ---------- the token stays private ----------

def test_the_token_never_reaches_an_error_or_a_log(api, monkeypatch, caplog):
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)

    def broken(request):
        raise httpx.ConnectError(f"could not connect with {request.headers['authorization']}", request=request)
    api(broken)
    with caplog.at_level(logging.DEBUG):
        error = failure(lambda: github.repos("zzqx-sample"))
    everything = caplog.text + repr(error) + str(error) + str(error.__cause__) + str(error.__context__)
    assert TOKEN not in everything
