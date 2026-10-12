import base64
import logging
from datetime import date

import httpx
import pytest

import reed

KEY = "reed-test-key-0000"
# Synthetic values in the shape Reed returns
RAW = {"jobId": 1001, "employerId": 5, "employerName": "Company A", "employerProfileId": None, "employerProfileName": None,
       "jobTitle": "Role A", "locationName": "Town A", "minimumSalary": 28000.0, "maximumSalary": 32000.0, "currency": "GBP",
       "expirationDate": "20/11/2026", "date": "09/10/2026", "jobDescription": "Analyse data and <b>report</b> findings.",
       "applications": 12, "jobUrl": "https://www.reed.co.uk/jobs/role-a/1001"}
DETAILS = {"jobId": 1001, "employerName": "Company A", "jobTitle": "Role A", "locationName": "Town A",
           "minimumSalary": 28000.0, "maximumSalary": 32000.0, "yearlyMinimumSalary": 28000.0, "yearlyMaximumSalary": 32000.0,
           "currency": "GBP", "salaryType": "per annum", "datePosted": "09/10/2026",
           "jobDescription": "<p>We need an analyst.</p><ul><li>SQL</li><li>Python &amp; Excel</li></ul><script>alert(1)</script>",
           "jobUrl": "https://www.reed.co.uk/jobs/role-a/1001"}


@pytest.fixture
def api(monkeypatch):
    """Reed replaced by a handler: api(lambda request: httpx.Response(...)). Returns the requests made."""
    monkeypatch.setenv("REED_API_KEY", KEY)

    def install(handler):
        seen = []

        def record(request):
            seen.append(request)
            return handler(request)
        monkeypatch.setattr(reed, "_client", lambda: httpx.Client(transport=httpx.MockTransport(record)))
        return seen
    return install


def results(*raws):
    return lambda request: httpx.Response(200, json={"results": list(raws), "totalResults": len(raws)})


# ---------- search ----------

def test_search_sends_the_key_as_the_basic_auth_username_and_filters_by_poster(api):
    seen = api(results(RAW))
    reed.search("data analyst", "London", "employer")
    request = seen[0]
    assert request.url.path == "/api/1.0/search" and request.url.host == "www.reed.co.uk"
    assert request.headers["authorization"] == "Basic " + base64.b64encode(f"{KEY}:".encode()).decode()
    assert dict(request.url.params) == {"keywords": "data analyst", "locationName": "London", "postedByDirectEmployer": "true", "resultsToTake": "100"}
    reed.search("data analyst", "London", "agency")
    assert "postedByRecruitmentAgency" in seen[1].url.params and "postedByDirectEmployer" not in seen[1].url.params


def test_search_parses_a_listing(api):
    api(results(RAW))
    assert reed.search("role a", "Town A", "employer") == [{
        "source": "reed", "source_id": "1001", "title": "Role A", "employer": "Company A", "posted_by": "employer",
        "location": "Town A", "salary_min": 28000, "salary_max": 32000, "salary_annual": True,
        "description": "Analyse data and report findings.", "description_is_full": False,
        "url": "https://www.reed.co.uk/jobs/role-a/1001", "posted_on": date(2026, 10, 9)}]


@pytest.mark.parametrize("location", ["Remote", " remote ", "REMOTE"])
def test_remote_becomes_a_keyword(api, location):
    seen = api(results())
    reed.search("data analyst", location, "employer")
    assert seen[0].url.params["keywords"] == "data analyst remote" and "locationName" not in seen[0].url.params


def test_no_location_searches_everywhere(api):
    seen = api(results())
    reed.search("data analyst", None, "employer")
    assert "locationName" not in seen[0].url.params and seen[0].url.params["keywords"] == "data analyst"


@pytest.mark.parametrize("change", [{"employerName": ""}, {"employerName": None}, {"jobTitle": "  "}, {"jobId": None},
                                    {"date": None}, {"date": "soon"}])
def test_a_listing_missing_something_essential_is_skipped(api, change):
    api(results(RAW | change, RAW | {"jobId": 1002}))
    assert [x["source_id"] for x in reed.search("role a", None, "employer")] == ["1002"]


@pytest.mark.parametrize("low, high, expected", [
    (28000, 32000, (28000, 32000, True)),
    (None, 30000, (None, 30000, True)),
    (15, 18.5, (15, 18.5, False)),    # an hourly rate
    (450, 450, (450, 450, False)),    # a day rate
    (None, None, (None, None, False)),
    (0, 0, (None, None, False)),
    ("lots", None, (None, None, False)),
])
def test_salary_is_annual_only_from_ten_thousand_up(api, low, high, expected):
    api(results(RAW | {"minimumSalary": low, "maximumSalary": high}))
    got = reed.search("role a", None, "employer")[0]
    assert (got["salary_min"], got["salary_max"], got["salary_annual"]) == expected


@pytest.mark.parametrize("given", ["2026-10-09", "2026-10-09T00:00:00", "09/10/2026"])
def test_posting_date_formats(api, given):
    api(results(RAW | {"date": given}))
    assert reed.search("role a", None, "employer")[0]["posted_on"] == date(2026, 10, 9)


@pytest.mark.parametrize("link", ["http://www.reed.co.uk/jobs/role-a/1001", "https://evil.example.test/jobs/1001",
                                  "javascript:alert(1)", "https://www.reed.co.uk.evil.example.test/x", "", None])
def test_a_link_that_is_not_on_reed_is_replaced(api, link):
    api(results(RAW | {"jobUrl": link}))
    assert reed.search("role a", None, "employer")[0]["url"] == "https://www.reed.co.uk/jobs/1001"


def test_search_both_asks_for_employers_and_agencies(api):
    seen = api(lambda request: httpx.Response(200, json={"results": [RAW | {"jobId": 2 if "postedByRecruitmentAgency" in request.url.params else 1}]}))
    got = reed.search_both("role a", "Town A")
    assert len(seen) == 2
    assert {(x["source_id"], x["posted_by"]) for x in got} == {("1", "employer"), ("2", "agency")}


# ---------- one advert in full ----------

def test_details_gives_the_full_text_and_annual_salary(api):
    seen = api(lambda request: httpx.Response(200, json=DETAILS))
    got = reed.details("1001")
    assert seen[0].url.path == "/api/1.0/jobs/1001"
    assert got == {"description": "We need an analyst.\n- SQL\n- Python & Excel", "description_is_full": True,
                   "salary_min": 28000, "salary_max": 32000, "salary_annual": True, "posted_on": date(2026, 10, 9)}


def test_details_for_a_day_rate_is_not_annual(api):
    api(lambda request: httpx.Response(200, json=DETAILS | {"minimumSalary": 12000, "maximumSalary": 12500, "salaryType": "per month",
                                                            "yearlyMinimumSalary": 144000, "yearlyMaximumSalary": 150000}))
    got = reed.details("1001")
    assert (got["salary_min"], got["salary_max"], got["salary_annual"]) == (12000, 12500, False)


@pytest.mark.parametrize("reply", [{}, {"jobId": None, "jobDescription": None}, {"jobId": 1001, "jobDescription": "  "}])
def test_details_of_a_missing_advert_is_an_error(api, reply):
    api(lambda request: httpx.Response(200, json=reply))
    with pytest.raises(reed.ReedError):
        reed.details("1001")


# ---------- HTML to text ----------

def test_clean_turns_html_into_plain_text():
    html = "<p>First&nbsp;paragraph.</p><p>Second <strong>bold</strong> one.<br/>Next line.</p><ul><li>One</li><li>Two &amp; three</li></ul>"
    assert reed.clean(html) == "First paragraph.\nSecond bold one.\nNext line.\n- One\n- Two & three"


def test_clean_drops_scripts_and_styles():
    assert reed.clean("<style>p{color:red}</style>Hello<script>alert('x')</script> there") == "Hello there"


def test_clean_leaves_plain_text_alone_and_handles_nothing():
    assert reed.clean("Just  some\n\n\n text") == "Just some\ntext"
    assert reed.clean("") == "" and reed.clean(None) == ""


# ---------- failures ----------

@pytest.mark.parametrize("failure", [
    lambda request: httpx.Response(500, text="oops"),
    lambda request: httpx.Response(429, text="slow down"),
    lambda request: httpx.Response(401, text="bad key"),
    lambda request: httpx.Response(200, text="<html>maintenance</html>"),
    lambda request: httpx.Response(200, json={"unexpected": True}),
    lambda request: httpx.Response(200, json=["not", "an", "object"]),
])
def test_every_failure_is_a_reed_error(api, failure):
    api(failure)
    with pytest.raises(reed.ReedError):
        reed.search("role a", None, "employer")


def test_a_timeout_is_a_reed_error(api):
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)
    api(slow)
    with pytest.raises(reed.ReedError):
        reed.search("role a", None, "employer")
    with pytest.raises(reed.ReedError):
        reed.details("1001")


def test_one_failed_half_fails_the_whole_search(api):
    api(lambda request: httpx.Response(500) if "postedByRecruitmentAgency" in request.url.params else httpx.Response(200, json={"results": [RAW]}))
    with pytest.raises(reed.ReedError):
        reed.search_both("role a", None)


def test_without_a_key_nothing_is_sent(monkeypatch, no_env_file):
    monkeypatch.delenv("REED_API_KEY", raising=False)
    monkeypatch.setattr(reed, "_client", lambda: pytest.fail("a request was made without a key"))
    with pytest.raises(reed.ReedError):
        reed.search("role a", None, "employer")


def test_the_key_never_reaches_an_error_or_a_log(api, caplog):
    api(lambda request: httpx.Response(500, text="oops"))
    with caplog.at_level(logging.DEBUG), pytest.raises(reed.ReedError) as error:
        reed.search("role a", None, "employer")
    encoded = base64.b64encode(f"{KEY}:".encode()).decode()
    everything = caplog.text + repr(error.value) + str(error.value.__cause__) + str(error.value.__context__)
    assert KEY not in everything and encoded not in everything
