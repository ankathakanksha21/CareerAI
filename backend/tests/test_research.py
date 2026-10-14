import time
from datetime import date

import pytest

import ai
import companies_house
import fetcher
import research
import websearch

TODAY = date(2026, 10, 14)
REGISTRY = {"number": "01234567", "name": "ZZQX HOLDINGS LIMITED", "status": "Active", "incorporated_on": date(2004, 3, 12),
            "town": "Town A", "type": "ltd", "sic": [{"code": "62012", "description": "Business and domestic software development"}],
            "url": "https://find-and-update.company-information.service.gov.uk/company/01234567"}
PAGES = [{"url": "https://zzqx.test/", "title": "Zzqx | Home",
          "text": "Zzqx builds payment software for councils.\nMenu\nWe value honesty and care."},
         {"url": "https://zzqx.test/careers", "title": "Careers", "text": "Join our graduate scheme in Leeds."}]
NEWS = [{"title": "Zzqx opens office", "url": "https://news.test/a", "snippet": "Zzqx opened a Leeds office.", "published_on": date(2026, 9, 1)},
        {"title": "Zzqx award", "url": "https://news.test/b", "snippet": "Zzqx won an award.", "published_on": None}]
RIVALS = [{"title": "Zzqx alternatives", "url": "https://compare.test/zzqx", "snippet": "Alternatives include Qqzx Pay.", "published_on": None}]


@pytest.fixture
def sources(monkeypatch):
    """The four outside sources replaced. Each value is a result, or an exception to raise. Returns the calls made."""
    def install(registry=REGISTRY, site=(PAGES, []), news=NEWS, rivals=RIVALS):
        calls = []

        def answer(name, value):
            def fake(*args):
                calls.append((name, args))
                if isinstance(value, Exception):
                    raise value
                return value
            return fake
        monkeypatch.setattr(companies_house, "profile", answer("registry", registry))
        monkeypatch.setattr(fetcher, "site", answer("website", site))
        monkeypatch.setattr(websearch, "news", answer("news", news))
        monkeypatch.setattr(websearch, "competitors", answer("competitors", rivals))
        return calls
    return install


def gather(**kw):
    return research.gather(**({"name": "Zzqx Holdings Ltd", "number": "01234567", "website": "https://zzqx.test/", "today": TODAY} | kw))


# ---------- the cache key ----------

def test_lookup_key_by_number_name_and_host():
    assert research.lookup_key(name="Zzqx Holdings Ltd", number="01234567", website="https://www.zzqx.test/") == "ch:01234567|zzqx|zzqx.test"
    assert research.lookup_key(name="ZZQX", number="01234567", website=None) == "ch:01234567|zzqx|"
    # the name is searched for, so a different name is a different record even with the same number
    assert research.lookup_key(name="Some Other Co", number="01234567", website=None) == "ch:01234567|some other|"


def test_lookup_key_by_name_when_not_on_the_register():
    assert research.lookup_key(name="The Zzqx Group Ltd", number=None, website="https://zzqx.test/") == "name:zzqx|zzqx.test"
    assert research.lookup_key(name="ZZQX", number=None, website=None) == "name:zzqx|"


# ---------- gathering ----------

def test_gather_runs_all_four(sources):
    calls = sources()
    got = gather()
    assert sorted(name for name, _ in calls) == ["competitors", "news", "registry", "website"]
    assert got == {"registry": REGISTRY, "pages": PAGES, "news": NEWS, "competitors": RIVALS, "missing": []}


@pytest.mark.parametrize("source, error, words, key", [
    ("registry", companies_house.CompaniesHouseError("down"), "Companies House", "registry"),
    ("news", websearch.SearchError("down"), "the news search", "news"),
    ("rivals", websearch.SearchError("down"), "the competitor search", "competitors")])
def test_gather_survives_each_failing(sources, source, error, words, key):
    sources(**{source: error})
    got = gather()
    assert got["missing"] == [words] and got[key] in (None, [])


@pytest.mark.parametrize("reason, words", [
    ("robots", "their website, which asks automated readers not to read it"),
    ("timeout", "their website, which did not answer in time"),
    ("address", "their website, which could not be reached"),
    ("not_html", "their website, which could not be read")])
def test_gather_says_why_the_website_is_missing(sources, reason, words):
    sources(site=([], [reason]))
    got = gather()
    assert got["pages"] == [] and got["missing"] == [words]


def test_a_page_that_failed_beside_others_is_not_missing(sources):
    sources(site=(PAGES, ["robots"]))
    assert gather()["missing"] == []


def test_not_uk_skips_companies_house(sources):
    calls = sources()
    got = gather(number=None)
    assert "registry" not in [name for name, _ in calls] and got["registry"] is None and got["missing"] == []


def test_no_website_skips_fetching(sources):
    calls = sources()
    got = gather(website=None)
    assert "website" not in [name for name, _ in calls] and got["pages"] == [] and got["missing"] == []


# ---------- what code writes, and the numbered passages ----------

def test_registry_facts_for_an_active_company():
    facts = research.registry_facts(REGISTRY)
    assert [f["text"] for f in facts] == [
        "Registered at Companies House as ZZQX HOLDINGS LIMITED, company number 01234567, incorporated on 12 March 2004.",
        "Companies House lists the company as active.",
        "Registered office in Town A.",
        "Nature of business: business and domestic software development (SIC 62012)."]
    assert {f["section"] for f in facts} == {"size", "what_they_do"}
    assert all(f["kind"] == "registry" and f["url"] == REGISTRY["url"] and f["source_title"] == "Companies House" for f in facts)


def test_registry_facts_for_a_dissolved_company_with_little_on_record():
    facts = research.registry_facts(REGISTRY | {"status": "Dissolved", "incorporated_on": None, "town": "", "sic": []})
    assert [f["text"] for f in facts] == ["Registered at Companies House as ZZQX HOLDINGS LIMITED, company number 01234567.",
                                          "Companies House lists this company as dissolved."]


def test_passages_numbered_and_split(monkeypatch):
    monkeypatch.setattr(research, "PASSAGE_CHARS", 50)
    got = research.passages({"registry": REGISTRY, "pages": PAGES, "news": NEWS, "competitors": RIVALS, "missing": []}, "Zzqx")
    assert [p["n"] for p in got] == list(range(1, len(got) + 1))
    assert [p["kind"] for p in got] == ["website", "website", "website", "news", "news", "competitors"]
    assert got[0]["text"] == "Zzqx builds payment software for councils."  # one-word lines (menus) are left out
    assert got[1]["text"] == "Join our graduate scheme in Leeds."      # every page gets a turn before any gets a second
    assert got[2]["text"] == "We value honesty and care."
    assert got[3] == {"n": 4, "kind": "news", "url": "https://news.test/a", "title": "Zzqx opens office",
                      "text": "Zzqx opened a Leeds office.", "published_on": date(2026, 9, 1)}


def test_website_passages_are_limited(monkeypatch):
    monkeypatch.setattr(research, "PASSAGE_CHARS", 30)
    page = {"url": "https://zzqx.test/", "title": "Zzqx", "text": "\n".join(f"Line number {i} of the page" for i in range(60))}
    got = research.passages({"registry": None, "pages": [page], "news": [], "competitors": [], "missing": []}, "Zzqx")
    assert len(got) == research.MAX_WEBSITE_PASSAGES


def test_search_results_that_do_not_name_the_company_are_left_out():
    news = NEWS + [{"title": "Qqzx Bank raises funds", "url": "https://news.test/other", "snippet": "Qqzx Bank raised money.", "published_on": None}]
    rivals = RIVALS + [{"title": "Best banks", "url": "https://compare.test/banks", "snippet": "A list of banks.", "published_on": None}]
    got = research.passages({"registry": None, "pages": [], "news": news, "competitors": rivals, "missing": []}, "Zzqx Holdings Ltd")
    assert [p["url"] for p in got] == ["https://news.test/a", "https://news.test/b", "https://compare.test/zzqx"]


@pytest.mark.parametrize("name, text, kept", [("The Zzqx Group Ltd", "ZZQX opens a shop", True), ("BT Group plc", "BT launches a plan", True),
                                              ("Zzqx", "Zzqxs opens a shop", False), ("Zzqx & Co", "news about Zzqx", True)])
def test_a_result_names_the_company_by_its_first_word(name, text, kept):
    result = {"title": "", "url": "https://news.test/x", "snippet": text, "published_on": None}
    got = research.passages({"registry": None, "pages": [], "news": [result], "competitors": [], "missing": []}, name)
    assert bool(got) is kept


def test_the_companys_own_pages_are_never_left_out():
    page = {"url": "https://zzqx.test/", "title": "Home", "text": "We build bridges for councils."}
    got = research.passages({"registry": None, "pages": [page], "news": [], "competitors": [], "missing": []}, "Zzqx")
    assert len(got) == 1


# ---------- the brief ----------

def test_brief_with_no_passages_makes_no_model_call(stub):
    calls = stub("company_brief", [])
    got = research.brief("Zzqx", {"registry": None, "pages": [], "news": [], "competitors": [], "missing": ["the news search"]}, TODAY)
    assert calls == []
    assert got == {"facts": [], "missing": ["the news search"], "notice": research.NOTHING_FOUND.format(name="Zzqx")}


def test_brief_with_only_the_register_has_its_lines_and_no_model_call(stub):
    calls = stub("company_brief", [])
    got = research.brief("Zzqx", {"registry": REGISTRY, "pages": [], "news": [], "competitors": [], "missing": []}, TODAY)
    assert calls == [] and got["notice"] is None and len(got["facts"]) == 4


def test_brief_attaches_source_details_by_code(stub):
    gathered = {"registry": REGISTRY, "pages": PAGES, "news": NEWS, "competitors": RIVALS, "missing": []}
    numbered = research.passages(gathered, "Zzqx")
    news_n = next(p["n"] for p in numbered if p["url"] == "https://news.test/a")
    stub("company_brief", [{"section": "news", "text": "Zzqx opened a Leeds office.", "source": news_n, "quote": ""},
                           {"section": "what_they_do", "text": "Zzqx builds payment software for councils.", "source": 1, "quote": ""}])
    got = research.brief("Zzqx", gathered, TODAY)
    assert [f["id"] for f in got["facts"]] == [f"f{i}" for i in range(1, 7)]
    assert [f["section"] for f in got["facts"]] == ["what_they_do", "what_they_do", "size", "size", "size", "news"]
    news = got["facts"][-1]
    assert news == {"id": "f6", "section": "news", "text": "Zzqx opened a Leeds office.", "quote": "", "url": "https://news.test/a",
                    "source_title": "Zzqx opens office", "kind": "news", "published_on": "2026-09-01"}
    assert got["facts"][1]["url"] == "https://zzqx.test/" and got["facts"][1]["source_title"] == "Zzqx | Home"


def test_untitled_source_is_named_by_its_site(stub):
    gathered = {"registry": None, "pages": [], "news": [], "missing": [],
                "competitors": [{"title": "", "url": "https://www.compare.test/x", "snippet": "Qqzx Pay is an alternative to Zzqx.", "published_on": None}]}
    stub("company_brief", [{"section": "competitors", "text": "Qqzx Pay is named as an alternative.", "source": 1, "quote": ""}])
    assert research.brief("Zzqx", gathered, TODAY)["facts"][0]["source_title"] == "compare.test"


def test_a_failed_brief_raises(stub):
    stub("company_brief", ai.AIError("brief"))
    with pytest.raises(ai.AIError):
        research.brief("Zzqx", {"registry": None, "pages": PAGES, "news": [], "competitors": [], "missing": []}, TODAY)


def test_gather_gives_up_on_a_source_that_takes_too_long(sources, monkeypatch):
    sources()
    monkeypatch.setattr(research, "GATHER_TIMEOUT_S", 0.3)

    def slow(home):
        time.sleep(2)
        return PAGES, []
    monkeypatch.setattr(fetcher, "site", slow)
    started = time.monotonic()
    got = gather()
    assert time.monotonic() - started < 1.5
    assert got["pages"] == [] and got["missing"] == ["their website, which did not answer in time"] and got["news"] == NEWS


def test_which_missing_sources_are_only_for_a_moment():
    assert set(research.TRANSIENT) == {"Companies House", "the news search", "the competitor search",
                                       "their website, which did not answer in time", "their website, which could not be reached"}
