import json
import logging
from datetime import date

import httpx
import pytest

import websearch

KEY = "tvly-test-key-0000"
TODAY = date(2026, 10, 14)


@pytest.fixture
def api(monkeypatch):
    """Tavily replaced by a handler. Returns the requests made."""
    monkeypatch.setenv("SEARCH_API_KEY", KEY)

    def install(handler):
        seen = []

        def record(request):
            seen.append(request)
            return handler(request)
        monkeypatch.setattr(websearch, "_client", lambda: httpx.Client(transport=httpx.MockTransport(record)))
        return seen
    return install


def results(*items):
    return lambda request: httpx.Response(200, json={"query": "q", "results": list(items), "response_time": 1.2})


def item(**kw):
    return {"title": "Zzqx opens office", "url": "https://news.test/zzqx", "content": "Zzqx Holdings opened an office.",
            "score": 0.8} | kw


def test_news_request_shape(api):
    seen = api(results())
    websearch.news("Zzqx Holdings Ltd", TODAY)
    request = seen[0]
    body = json.loads(request.content)
    assert request.method == "POST" and str(request.url) == websearch.API
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert body["query"] == '"Zzqx Holdings"' and body["topic"] == "news"
    assert body["start_date"] == "2025-10-14" and body["max_results"] == websearch.MAX_NEWS
    assert body["search_depth"] == "basic"


@pytest.mark.parametrize("raw, expected", [("Mon, 13 Oct 2026 10:00:00 GMT", date(2026, 10, 13)), ("2026-10-13", date(2026, 10, 13)),
                                            ("2026-10-13T08:30:00Z", date(2026, 10, 13)), ("yesterday", None), (None, None)])
def test_news_parses_dates(api, raw, expected):
    api(results(item(published_date=raw)))
    found = websearch.news("Zzqx", TODAY)
    assert found == [{"title": "Zzqx opens office", "url": "https://news.test/zzqx", "snippet": "Zzqx Holdings opened an office.",
                      "published_on": expected}]


def test_old_news_is_dropped_and_undated_kept(api):
    api(results(item(url="https://news.test/old", published_date="2025-10-13"), item(url="https://news.test/edge", published_date="2025-10-14"),
                item(url="https://news.test/undated")))
    assert [r["url"] for r in websearch.news("Zzqx", TODAY)] == ["https://news.test/edge", "https://news.test/undated"]


def test_competitors_request_shape(api):
    seen = api(results(item()))
    found = websearch.competitors("Zzqx Holdings Limited")
    body = json.loads(seen[0].content)
    assert body["query"] == "Zzqx Holdings competitors" and body["topic"] == "general"
    assert body["country"] == "united kingdom" and body["max_results"] == websearch.MAX_COMPETITORS
    assert found[0]["url"] == "https://news.test/zzqx"


def test_non_http_results_and_odd_items_dropped(api):
    api(results(item(url="javascript:alert(1)"), item(url="ftp://x.test/a"), item(url=""), "x", item(title="", url="https://news.test/notitle"),
                item(url="https://news.test/ok")))
    assert [r["url"] for r in websearch.competitors("Zzqx")] == ["https://news.test/notitle", "https://news.test/ok"]


def test_snippet_is_cut(api):
    api(results(item(content="word " * 400)))
    assert len(websearch.competitors("Zzqx")[0]["snippet"]) <= websearch.SNIPPET_CHARS


def test_quotes_in_a_name_do_not_break_the_query(api):
    seen = api(results())
    websearch.news('The "Zzqx" Company plc', TODAY)
    assert json.loads(seen[0].content)["query"] == '"The Zzqx Company"'


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.Response(401, json={"detail": {"error": f"Invalid key {KEY}"}}),
                                     httpx.Response(432, text="plan limit"), httpx.Response(500), httpx.Response(200, text="not json")])
def test_failures_raise_search_error_without_the_key(api, caplog, failure):
    def handler(request):
        if isinstance(failure, Exception):
            raise failure
        return failure
    api(handler)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(websearch.SearchError) as e:
        websearch.news("Zzqx", TODAY)
    assert KEY not in str(e.value) and KEY not in caplog.text


def test_no_key_makes_no_request(monkeypatch, no_env_file):
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    monkeypatch.setattr(websearch, "_client", lambda: pytest.fail("a request was made without a key"))
    with pytest.raises(websearch.SearchError):
        websearch.competitors("Zzqx")
