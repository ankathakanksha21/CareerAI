import base64
import logging
from datetime import date

import httpx
import pytest

import companies_house as ch

KEY = "ch-test-key-0000"
# Synthetic values in the shape Companies House returns
ITEM = {"title": "ZZQX HOLDINGS LIMITED", "company_number": "01234567", "company_status": "active",
        "date_of_creation": "2004-03-12", "company_type": "ltd", "address": {"locality": "Town A", "postal_code": "AA1 1AA"},
        "address_snippet": "1 Road A, Town A, AA1 1AA"}
PROFILE = {"company_name": "ZZQX HOLDINGS LIMITED", "company_number": "01234567", "company_status": "voluntary-arrangement",
           "date_of_creation": "2004-03-12", "type": "ltd", "registered_office_address": {"locality": "Town A"},
           "sic_codes": ["62012", "00000"]}


@pytest.fixture
def api(monkeypatch):
    """Companies House replaced by a handler. Returns the requests made."""
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", KEY)

    def install(handler):
        seen = []

        def record(request):
            seen.append(request)
            return handler(request)
        monkeypatch.setattr(ch, "_client", lambda: httpx.Client(transport=httpx.MockTransport(record)))
        return seen
    return install


def test_search_shapes_five_matches(api):
    items = [ITEM | {"company_number": f"0123456{i}", "title": f"ZZQX {i} LIMITED"} for i in range(7)]
    api(lambda request: httpx.Response(200, json={"items": items}))
    found = ch.search("Zzqx")
    assert len(found) == 5
    assert found[0] == {"number": "01234560", "name": "ZZQX 0 LIMITED", "status": "Active", "town": "Town A",
                        "incorporated_on": date(2004, 3, 12)}


def test_search_sends_the_name_as_a_parameter_and_the_key_as_basic_auth(api):
    seen = api(lambda request: httpx.Response(200, json={"items": []}))
    ch.search("Zzqx & Sons")
    request = seen[0]
    assert request.url.path == "/search/companies" and request.url.params["q"] == "Zzqx & Sons"
    assert request.headers["Authorization"] == "Basic " + base64.b64encode(f"{KEY}:".encode()).decode()


def test_no_matches_is_an_empty_list(api):
    api(lambda request: httpx.Response(200, json={"items": []}))
    assert ch.search("Qqzx") == []


def test_odd_items_are_read_safely(api):
    api(lambda request: httpx.Response(200, json={"items": [{"title": "ZZQX LIMITED", "company_number": "SC123456"},
                                                             {"title": "", "company_number": "bad"}, "x"]}))
    assert ch.search("Zzqx") == [{"number": "SC123456", "name": "ZZQX LIMITED", "status": "", "town": "", "incorporated_on": None}]


def test_profile_reads_sic_descriptions(api):
    seen = api(lambda request: httpx.Response(200, json=PROFILE))
    p = ch.profile("01234567")
    assert seen[0].url.path == "/company/01234567"
    assert p == {"number": "01234567", "name": "ZZQX HOLDINGS LIMITED", "status": "Voluntary arrangement",
                 "incorporated_on": date(2004, 3, 12), "town": "Town A", "type": "ltd",
                 "sic": [{"code": "62012", "description": "Business and domestic software development"},
                         {"code": "00000", "description": ""}],
                 "url": "https://find-and-update.company-information.service.gov.uk/company/01234567"}


def test_profile_number_is_upper_cased(api):
    seen = api(lambda request: httpx.Response(200, json=PROFILE | {"company_number": "SC123456"}))
    ch.profile("sc123456")
    assert seen[0].url.path == "/company/SC123456"


@pytest.mark.parametrize("number", ["../x", "0123456", "012345678", "01234 67", ""])
def test_bad_number_never_reaches_the_api(api, number):
    seen = api(lambda request: httpx.Response(200, json=PROFILE))
    with pytest.raises(ValueError):
        ch.profile(number)
    assert seen == []


def test_not_found_profile_raises(api):
    api(lambda request: httpx.Response(404, json={"errors": [{"error": "company-profile-not-found"}]}))
    with pytest.raises(ch.CompaniesHouseError) as e:
        ch.profile("01234567")
    assert e.value.message == ch.NOT_FOUND


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.Response(500, text=f"error for key {KEY}"),
                                     httpx.Response(401, text=f"bad key {KEY}"), httpx.Response(200, text="not json")])
def test_failures_raise_without_the_key(api, caplog, failure):
    def handler(request):
        if isinstance(failure, Exception):
            raise failure
        return failure
    api(handler)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ch.CompaniesHouseError) as e:
        ch.search("Zzqx")
    assert e.value.message == ch.UNREACHABLE
    assert KEY not in str(e.value) and KEY not in caplog.text


def test_no_key_makes_no_request(monkeypatch, no_env_file):
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    monkeypatch.setattr(ch, "_client", lambda: pytest.fail("a request was made without a key"))
    with pytest.raises(ch.CompaniesHouseError):
        ch.search("Zzqx")
