"""Search links for people and events, and professional bodies by field. Every address must point
at the expected site, with whatever the user typed kept inside its query value or path segment."""
import json
import re
from urllib.parse import parse_qs, urlsplit

import pytest

import links

ALLOWED = {"www.linkedin.com", "www.meetup.com", "www.eventbrite.co.uk"}


def build(**kw):
    args = {"university": "University of Leeds", "locations": ["Leeds"], "fields": ["Data Analyst"], "titles": [],
            "companies": [], "events_url": None} | kw
    return links.search_links(**args)


def every_url(result):
    for group in ("people", "meetup", "eventbrite"):
        for link in result[group]:
            yield link["url"]


# ---------- the patterns checked on 14 October 2026 ----------

def test_linkedin_people_search_for_alumni_at_a_company():
    [link] = build(companies=["Zzqx Holdings"])["people"]
    assert link == {"label": "Alumni of University of Leeds at Zzqx Holdings",
                    "url": "https://www.linkedin.com/search/results/people/?keywords=University%20of%20Leeds%20Zzqx%20Holdings",
                    "terms": "University of Leeds Zzqx Holdings"}


def test_linkedin_people_search_by_job_title():
    [link] = build(titles=["Data Analyst"])["people"]
    assert link["label"] == "Alumni of University of Leeds working as Data Analyst"
    assert link["terms"] == "University of Leeds Data Analyst"


def test_alumni_alone_when_there_is_nothing_to_narrow_by():
    [link] = build()["people"]
    assert link["label"] == "Alumni of University of Leeds"
    assert link["url"] == "https://www.linkedin.com/search/results/people/?keywords=University%20of%20Leeds"


def test_no_people_links_without_a_university():
    assert build(university="  ", companies=["Zzqx Holdings"])["people"] == []


def test_meetup_search_for_a_field_in_a_city():
    [link] = build(locations=["Milton Keynes"])["meetup"]
    assert link == {"label": "Data Analyst in Milton Keynes",
                    "url": "https://www.meetup.com/find/?keywords=Data%20Analyst&location=gb--Milton%20Keynes&source=EVENTS",
                    "terms": "Data Analyst, Milton Keynes"}


def test_eventbrite_search_for_a_field_in_a_city_and_online():
    result = build(locations=["Milton Keynes", "Remote"])
    assert [(l["label"], l["url"]) for l in result["eventbrite"]] == [
        ("Data Analyst in Milton Keynes", "https://www.eventbrite.co.uk/d/united-kingdom--milton-keynes/data-analyst/"),
        ("Data Analyst online", "https://www.eventbrite.co.uk/d/online/data-analyst/"),
    ]


def test_remote_is_not_a_meetup_city():
    assert build(locations=["Remote"])["meetup"] == []


def test_caps_and_duplicates():
    result = build(companies=["A1", "a1", "B2", "C3", "D4", "E5", "F6"], titles=["T1", "T2", "T3", "T4"],
                   fields=["F1", "F2", "F3", "F4"], locations=["Leeds", "leeds", "York", "Hull", "Bath"])
    assert len(result["people"]) == 5 + 3
    assert len(result["meetup"]) == 3 * 3 and len(result["eventbrite"]) == 3 * 3
    assert len({l["url"] for l in result["people"]}) == len(result["people"])


# ---------- odd characters stay where they belong ----------

ODD = ["AT&T", "C# / .NET", "Saint-Étienne", "../?x=1#y", "R&D \"Lab\"", "a%20b", "https://evil.example/x"]


@pytest.mark.parametrize("odd", ODD)
def test_odd_characters_cannot_change_the_site_or_path(odd):
    result = build(university=f"Uni {odd}", companies=[odd], titles=[odd], fields=[odd], locations=[odd, "Remote"])
    for url in every_url(result):
        parts = urlsplit(url)
        assert parts.scheme == "https" and parts.hostname in ALLOWED, url
        assert parts.fragment == "" and parts.username is None and parts.port is None, url
        if parts.hostname == "www.eventbrite.co.uk":
            assert re.fullmatch(r"/d/(online|united-kingdom--[a-z0-9-]+)/[a-z0-9-]+/", parts.path), url
        else:
            assert parts.path in ("/search/results/people/", "/find/"), url


@pytest.mark.parametrize("odd", ODD)
def test_what_was_typed_comes_back_whole_from_the_query(odd):
    result = build(companies=[odd], fields=[odd], locations=["Leeds"])
    people = [l for l in result["people"] if odd in l["label"]][0]
    assert parse_qs(urlsplit(people["url"]).query)["keywords"] == [f"University of Leeds {odd}"]
    [meetup] = result["meetup"]
    assert parse_qs(urlsplit(meetup["url"]).query) == {"keywords": [odd], "location": ["gb--Leeds"], "source": ["EVENTS"]}


def test_a_field_with_nothing_left_after_slugging_gives_no_eventbrite_link():
    result = build(fields=["#?!", "Data Analyst"])
    assert [l["url"] for l in result["eventbrite"]] == ["https://www.eventbrite.co.uk/d/united-kingdom--leeds/data-analyst/"]
    assert not any("//" in urlsplit(u).path for u in every_url(result))


def test_accents_are_kept_simple_in_a_slug():
    [link] = build(fields=["Café Management"], locations=["Saint-Étienne"])["eventbrite"]
    assert link["url"] == "https://www.eventbrite.co.uk/d/united-kingdom--saint-etienne/cafe-management/"


# ---------- the university's own events page ----------

def test_the_university_events_page_is_shown_when_saved():
    assert build(events_url="https://careers.leeds.ac.uk/events")["university"] == {
        "label": "Your university's careers events", "url": "https://careers.leeds.ac.uk/events"}
    assert build()["university"] is None


def test_an_unsafe_saved_page_is_not_shown():
    assert build(events_url="javascript:alert(1)")["university"] is None


@pytest.mark.parametrize("value, expected", [
    ("https://careers.leeds.ac.uk/events", "https://careers.leeds.ac.uk/events"),
    ("careers.leeds.ac.uk/events", "https://careers.leeds.ac.uk/events"),
    ("  http://www.example.ac.uk/careers?x=1  ", "http://www.example.ac.uk/careers?x=1"),
    ("www.linkedin.com/in/zzqx-person", "https://www.linkedin.com/in/zzqx-person"),
    ("javascript:alert(1)", None),
    ("ftp://files.example.com", None),
    ("http://localhost/x", None),
    ("https://127.0.0.1/x", None),
    ("https://a b.com", None),
    ("https://user:pass@example.com", None),
    ("https://example.com:8080/x", None),
    ("https://intranet/x", None),
    ("", None),
    ("https://example.com/" + "x" * 500, None),
])
def test_safe_url(value, expected):
    assert links.safe_url(value) == expected


# ---------- professional bodies ----------

@pytest.mark.parametrize("texts, names", [
    (["Data Analyst"], ["BCS, The Chartered Institute for IT", "Royal Statistical Society"]),
    (["HR Advisor", "People Adviser"], ["CIPD"]),
    (["Marketing Executive"], ["Chartered Institute of Marketing"]),
    (["Graduate Accountant"], ["ICAEW"]),
    (["Project Coordinator"], ["Association for Project Management"]),
    (["Supply Chain Analyst"], ["Chartered Institute of Procurement and Supply"]),
    (["Civil Engineer"], ["Institution of Civil Engineers"]),
    (["Barista"], []),
])
def test_bodies_for_a_field(texts, names):
    assert [b["name"] for b in links.bodies_for(texts)] == names


def test_search_links_include_bodies_for_the_fields_and_titles():
    names = [b["name"] for b in build(fields=["Marketing"], titles=["HR Assistant"])["bodies"]]
    assert names == ["CIPD", "Chartered Institute of Marketing"]


def test_every_body_was_checked_and_links_to_its_events_page():
    bodies = json.loads(links.BODIES.read_text(encoding="utf-8"))
    assert len(bodies) == 10
    for body in bodies:
        assert body["checked_on"] == "2026-10-14"
        assert urlsplit(body["url"]).scheme == "https" and body["keywords"] and body["about"]
        assert "—" not in body["about"]
