"""The Companies House public data API (https://developer.company-information.service.gov.uk):
search by name, and one company's profile.

Everything Companies House-specific stays in this file. The key travels only as the Basic-auth
username and never appears in an error or a log line. Companies House gives a company's nature of
business as SIC codes; their descriptions come from gov.uk's condensed SIC 2007 list, kept in
data/sic_codes.json (Open Government Licence v3.0)."""
import json
import logging
import re
from datetime import date
from functools import cache
from pathlib import Path

import httpx

from config import companies_house_key

log = logging.getLogger("companies_house")

API = "https://api.company-information.service.gov.uk"
PUBLIC_URL = "https://find-and-update.company-information.service.gov.uk/company/{number}"
NUMBER = re.compile(r"^[A-Z0-9]{8}$")
MAX_MATCHES = 5
TIMEOUT_S = 10
UNREACHABLE = "We could not reach Companies House. You can carry on without it."
NOT_FOUND = "Companies House has no company with that number."
SIC_FILE = Path(__file__).parent / "data" / "sic_codes.json"


class CompaniesHouseError(Exception):
    """Companies House could not be reached, refused the request or has no such company."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S)


def _get(path: str, params: dict | None = None) -> dict:
    key = companies_house_key()
    if not key:
        raise CompaniesHouseError(UNREACHABLE)
    try:
        with _client() as client:
            r = client.get(API + path, params=params, auth=(key, ""))  # the key is the username, with no password
        if r.status_code == 404:
            raise CompaniesHouseError(NOT_FOUND)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Companies House request failed: %s", type(e).__name__)
        raise CompaniesHouseError(UNREACHABLE) from None  # the original error can carry request details
    return data if isinstance(data, dict) else {}


# ---------- reading what Companies House sends ----------

def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _date(value) -> date | None:
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _status(value) -> str:
    """"voluntary-arrangement" as "Voluntary arrangement"."""
    words = _text(value).replace("-", " ")
    return words[:1].upper() + words[1:]


def _number(value) -> str:
    number = _text(value).upper()
    return number if NUMBER.match(number) else ""


@cache
def _sic_descriptions() -> dict:
    return json.loads(SIC_FILE.read_text(encoding="utf-8"))["codes"]


# ---------- the two calls ----------

def search(name: str) -> list[dict]:
    """Up to five companies whose name matches, as Companies House ranks them."""
    data = _get("/search/companies", {"q": name, "items_per_page": 10})
    found = []
    for item in data.get("items") or []:
        if not isinstance(item, dict) or not _number(item.get("company_number")) or not _text(item.get("title")):
            continue
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        found.append({"number": _number(item["company_number"]), "name": _text(item["title"]),
                      "status": _status(item.get("company_status")), "town": _text(address.get("locality")),
                      "incorporated_on": _date(item.get("date_of_creation"))})
    return found[:MAX_MATCHES]


def profile(number: str) -> dict:
    """One company's register entry. The number is checked before it is put in an address."""
    checked = _number(number)
    if not checked:
        raise ValueError("not a Companies House number")
    data = _get(f"/company/{checked}")
    office = data.get("registered_office_address") if isinstance(data.get("registered_office_address"), dict) else {}
    codes = [c for c in (data.get("sic_codes") or []) if isinstance(c, str) and c.strip()]
    return {"number": _number(data.get("company_number")) or checked, "name": _text(data.get("company_name")),
            "status": _status(data.get("company_status")), "incorporated_on": _date(data.get("date_of_creation")),
            "town": _text(office.get("locality")), "type": _text(data.get("type")),
            "sic": [{"code": c.strip(), "description": _sic_descriptions().get(c.strip(), "")} for c in codes],
            "url": PUBLIC_URL.format(number=checked)}
