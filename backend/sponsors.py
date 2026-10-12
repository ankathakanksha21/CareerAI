"""The gov.uk register of licensed sponsors: where the file is, how it is read, and how an
employer's name is compared with it.

Only employers licensed for the Skilled Worker route are kept. A match is "listed" when the
names are the same once company suffixes and punctuation are ignored, and "possible" when the
advert's name is the start of a longer registered name. The SQL lives in repo.py."""
import csv
import io
import logging
import re
from datetime import datetime

import httpx

import db
import repo

log = logging.getLogger("sponsors")

REGISTER_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
REGISTER_API = "https://www.gov.uk/api/content/government/publications/register-of-licensed-sponsors-workers"
FILE_HOST = "https://assets.publishing.service.gov.uk/"  # the file's address changes with every update
COLUMNS = ["Organisation Name", "Town/City", "County", "Type & Rating", "Route"]
ROUTE = "Skilled Worker"
MIN_ROWS = 50_000  # the real file has over 120,000; far fewer means it is broken or has changed shape

# Words that say what kind of company it is, not which one
SUFFIXES = {"ltd", "limited", "plc", "llp", "lp", "inc", "group", "holdings", "uk", "co", "company"}
TRADING_AS = re.compile(r"\s+(?:t/a|trading\s+as)\s+", re.I)


class RegisterError(Exception):
    """The register could not be found, downloaded or read. The stored copy is left as it was."""


# ---------- names ----------

def normalise(name: str) -> str:
    """A company name reduced to what identifies it: "The Acme Group (UK) Ltd." and "ACME" both give "acme"."""
    text = name.lower().replace("&", " and ").replace("'", "").replace("’", "")
    words = re.sub(r"[\W_]+", " ", text).split()
    core = words[1:] if words[:1] == ["the"] else list(words)
    while core and core[-1] in SUFFIXES:
        core.pop()
    return " ".join(core or words)  # a name made only of such words is kept whole


def keys(name: str) -> list[str]:
    """Every name an employer may be advertised under: its legal name and, for "X T/A Y", its trading name."""
    found = []
    for part in TRADING_AS.split(name):
        key = normalise(part)
        if key and key not in found:
            found.append(key)
    return found


def with_keys(rows: list[dict]) -> list[dict]:
    """One row per name the organisation is known by, ready to store."""
    return [row | {"name_key": key} for row in rows for key in keys(row["name"])]


def employer_key(name: str) -> str:
    """The key an advert's employer is looked up by. Empty for a name that identifies nobody,
    such as a blank or one that is nothing but "Ltd" or "Group"."""
    key = normalise(name)
    return "" if set(key.split()) <= SUFFIXES | {"the"} else key


def status(conn, employer: str, posted_by: str = "employer") -> dict:
    """What the register says about an advert's employer: {"status", "name"}. An advert placed by a
    recruitment agency names the agency, not the employer, so it is never looked up."""
    if posted_by == "agency":
        return {"status": "agency", "name": None}
    return repo.find_sponsor(conn, employer_key(employer))


# ---------- the file ----------

def latest() -> dict:
    """Where today's register file is and the date it was published: {"url", "published_on"}."""
    try:
        r = httpx.get(REGISTER_API, timeout=20)
        r.raise_for_status()
        page = r.json()
        files = [a["url"] for a in page["details"]["attachments"]
                 if a.get("content_type") == "text/csv" or str(a.get("url", "")).lower().endswith(".csv")]
        url, published_on = files[0], datetime.fromisoformat(page["public_updated_at"]).date()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
        raise RegisterError("could not find the register file on gov.uk") from e
    if not url.startswith(FILE_HOST):
        raise RegisterError("the register file is not where gov.uk normally publishes it")
    return {"url": url, "published_on": published_on}


def download(url: str) -> str:
    try:
        r = httpx.get(url, timeout=60, follow_redirects=True)
        r.raise_for_status()
        return r.content.decode("utf-8-sig")
    except (httpx.HTTPError, UnicodeDecodeError) as e:
        raise RegisterError("could not download the register file") from e


def parse(text: str) -> list[dict]:
    """The Skilled Worker rows of the register file. Raises RegisterError rather than return a
    file that is empty, cut short or laid out differently."""
    try:
        reader = csv.reader(io.StringIO(text))
        header = [h.strip() for h in next(reader, [])]
        if header != COLUMNS:
            raise RegisterError("the register file's columns have changed")
        rows = [{"name": r[0].strip(), "town": r[1].strip(), "county": r[2].strip(), "rating": r[3].strip(), "route": r[4].strip()}
                for r in reader if len(r) == len(COLUMNS) and r[4].strip() == ROUTE and r[0].strip()]
    except csv.Error as e:
        raise RegisterError("the register file could not be read") from e
    if len(rows) < MIN_ROWS:
        raise RegisterError(f"the register file has only {len(rows)} Skilled Worker rows")
    return rows


def refresh() -> dict:
    """Replace the stored register with today's file and re-check every stored listing against it.
    Nothing is changed unless the new file was found, downloaded and read in full."""
    found = latest()
    rows = parse(download(found["url"]))
    with db.transaction() as conn:
        repo.replace_sponsors(conn, with_keys(rows), published_on=found["published_on"], source_url=found["url"], row_count=len(rows))
        repo.recheck_listing_sponsors(conn)
    log.info("sponsor register loaded: %d organisations, published %s", len(rows), found["published_on"])
    return {"rows": len(rows), "published_on": found["published_on"]}
