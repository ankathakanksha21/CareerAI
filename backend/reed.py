"""Reed's job search API (https://www.reed.co.uk/developers/jobseeker): search, and one advert in full.

Everything Reed-specific stays in this file. A listing leaves it in the shape of a job_listings
row. Search results do not say who posted an advert, so each search is made twice, once for
direct employers and once for recruitment agencies. Any failure is a ReedError; the key travels
only in the request's authorisation header and never appears in an error or a log line."""
import logging
import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from config import env

log = logging.getLogger("reed")

SEARCH_URL = "https://www.reed.co.uk/api/1.0/search"
JOB_URL = "https://www.reed.co.uk/api/1.0/jobs/{id}"
ADVERT_URL = "https://www.reed.co.uk/jobs/{id}"
HOSTS = {"www.reed.co.uk", "reed.co.uk"}
POSTED_BY = {"employer": "postedByDirectEmployer", "agency": "postedByRecruitmentAgency"}
PAGE_SIZE = 100       # the most Reed returns per call
TIMEOUT_S = 10
ANNUAL_FROM = 10_000  # search results give a figure with no period; below this it is a day or hourly rate
MAX_DESCRIPTION = 20_000


class ReedError(Exception):
    """Reed could not be reached, refused the request or sent something unreadable."""


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S)


def _get(url: str, params: dict | None = None):
    key = env("REED_API_KEY")
    if not key:
        raise ReedError("not configured")
    try:
        with _client() as client:
            r = client.get(url, params=params, auth=(key, ""))  # the key is the username, with no password
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Reed request failed: %s", type(e).__name__)
        raise ReedError(type(e).__name__) from None  # the original error can carry request details


# ---------- reading what Reed sends ----------

def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _money(value) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(value) if float(value).is_integer() else value


def _date(value) -> date | None:
    text = _text(value)
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return None


def _link(value, job_id) -> str:
    """The advert's address, only if it really is on Reed over https; otherwise the standard one."""
    url = urlparse(_text(value))
    return value.strip() if url.scheme == "https" and url.hostname in HOSTS else ADVERT_URL.format(id=job_id)


class _Text(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    HIDDEN = {"script", "style"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag):
        if tag in self.HIDDEN:
            self.hidden = max(0, self.hidden - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean(html) -> str:
    """An advert's HTML as plain text: one line per paragraph, list items marked with a dash."""
    parser = _Text()
    parser.feed(_text(html))
    parser.close()
    lines = (re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip() for line in "".join(parser.parts).split("\n"))
    return "\n".join(line for line in lines if line and line != "-")[:MAX_DESCRIPTION]


def parse(raw, posted_by: str) -> dict | None:
    """One search result as a listing, or None if it lacks its id, title, employer or posting date."""
    if not isinstance(raw, dict):
        return None
    job_id, title, employer = raw.get("jobId"), _text(raw.get("jobTitle")), _text(raw.get("employerName"))
    posted_on = _date(raw.get("date") or raw.get("datePosted"))
    if not (job_id and title and employer and posted_on):
        return None
    low, high = _money(raw.get("minimumSalary")), _money(raw.get("maximumSalary"))
    return {
        "source": "reed", "source_id": str(job_id), "title": title[:300], "employer": employer[:300], "posted_by": posted_by,
        "location": _text(raw.get("locationName"))[:200], "salary_min": low, "salary_max": high,
        "salary_annual": max(low or 0, high or 0) >= ANNUAL_FROM,
        "description": clean(raw.get("jobDescription")), "description_is_full": False,
        "url": _link(raw.get("jobUrl"), job_id), "posted_on": posted_on,
    }


# ---------- the two calls ----------

def search(keywords: str, location: str | None, posted_by: str) -> list[dict]:
    """Adverts for a job title, from direct employers or from agencies. "Remote" is not a place
    Reed knows, so it is searched as a word."""
    params = {"keywords": keywords, POSTED_BY[posted_by]: "true", "resultsToTake": PAGE_SIZE}
    place = (location or "").strip()
    if place.lower() == "remote":
        params["keywords"] = f"{keywords} remote"
    elif place:
        params["locationName"] = place
    data = _get(SEARCH_URL, params)
    found = data.get("results") if isinstance(data, dict) else None
    if not isinstance(found, list):
        log.warning("Reed search reply had no results list")
        raise ReedError("unexpected reply")
    return [listing for listing in (parse(raw, posted_by) for raw in found) if listing]


def search_both(keywords: str, location: str | None) -> list[dict]:
    """Every advert for a title in a place, each marked with who posted it."""
    return search(keywords, location, "employer") + search(keywords, location, "agency")


def details(source_id: str) -> dict:
    """The full text of one advert, with its salary as Reed states it."""
    raw = _get(JOB_URL.format(id=source_id))
    description = clean(raw.get("jobDescription")) if isinstance(raw, dict) else ""
    if not description or not raw.get("jobId"):  # Reed answers an unknown id with a blank advert
        raise ReedError("advert not found")
    low, high = _money(raw.get("minimumSalary")), _money(raw.get("maximumSalary"))
    period = _text(raw.get("salaryType")).lower()
    annual = ("annum" in period or "year" in period) if period else max(low or 0, high or 0) >= ANNUAL_FROM
    found = {"description": description, "description_is_full": True, "salary_min": low, "salary_max": high,
             "salary_annual": bool(annual and (low or high))}
    posted_on = _date(raw.get("datePosted") or raw.get("date"))
    return found | ({"posted_on": posted_on} if posted_on else {})
