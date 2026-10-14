"""Search links for finding people and events, and professional bodies by field. Built from the
user's profile, saved jobs and target roles on the server. Every link goes to a fixed site, with
what the user typed kept inside the query value or one path segment; the app itself fetches
nothing from these sites. The address patterns were checked on 14 October 2026."""
import ipaddress
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

BODIES = Path(__file__).parent / "data" / "professional_bodies.json"
LINKEDIN_PEOPLE = "https://www.linkedin.com/search/results/people/"
MEETUP_FIND = "https://www.meetup.com/find/"
EVENTBRITE = "https://www.eventbrite.co.uk/d/"
MAX_COMPANIES, MAX_TITLES, MAX_FIELDS, MAX_CITIES = 5, 3, 3, 3
REMOTE = {"remote", "online", "anywhere", "work from home", "hybrid"}
MAX_URL = 500


def _query(params: dict) -> str:
    return urlencode(params, quote_via=quote)  # a space as %20, every other special character escaped


def _slug(text: str) -> str:
    """'Milton Keynes' -> 'milton-keynes', 'Saint-Étienne' -> 'saint-etienne', 'C# / .NET' -> 'c-net'."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def _unique(items, cap: int) -> list[str]:
    """Trimmed, without blanks or anything with no letter or digit, without a second spelling of the
    same thing, at most `cap`."""
    kept, seen = [], set()
    for item in items:
        text = " ".join((item or "").split())
        if text and re.search(r"\w", text) and text.lower() not in seen:
            seen.add(text.lower())
            kept.append(text)
    return kept[:cap]


def _link(label: str, url: str, terms: str) -> dict:
    return {"label": label, "url": url, "terms": terms}


def _people(university: str, companies: list[str], titles: list[str]) -> list[dict]:
    """LinkedIn people searches for alumni of the user's university at a company or in a job title.
    LinkedIn asks a signed-out visitor to sign in first, then returns them to the search."""
    if not university:
        return []
    wanted = ([(f"Alumni of {university} at {c}", f"{university} {c}") for c in companies]
              + [(f"Alumni of {university} working as {t}", f"{university} {t}") for t in titles]
              or [(f"Alumni of {university}", university)])
    return [_link(label, f"{LINKEDIN_PEOPLE}?{_query({'keywords': terms})}", terms) for label, terms in wanted]


def _meetup(fields: list[str], cities: list[str]) -> list[dict]:
    return [_link(f"{field} in {city}", f"{MEETUP_FIND}?{_query({'keywords': field, 'location': f'gb--{city}', 'source': 'EVENTS'})}",
                  f"{field}, {city}")
            for field in fields for city in cities if city.lower() not in REMOTE]


def _eventbrite(fields: list[str], cities: list[str]) -> list[dict]:
    found = []
    for field in fields:
        topic = _slug(field)
        for city in cities:
            online = city.lower() in REMOTE
            place = "online" if online else _slug(city) and f"united-kingdom--{_slug(city)}"
            if topic and place:
                found.append(_link(f"{field} online" if online else f"{field} in {city}", f"{EVENTBRITE}{place}/{topic}/",
                                   f"{field}, {'online' if online else city}"))
    return found


def _words(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9&+-]+", text.lower())) + " "


def bodies_for(texts: list[str]) -> list[dict]:
    """The professional bodies whose keywords appear, as whole words, in the user's target roles."""
    said = "".join(_words(t) for t in texts)
    bodies = json.loads(BODIES.read_text(encoding="utf-8"))
    return [{"name": b["name"], "url": b["url"], "about": b["about"]} for b in bodies
            if any(f" {k} " in said for k in b["keywords"])]


def safe_url(value: str) -> str | None:
    """An address the user typed, if it is safe to show as a link: http or https, a named public
    host with a dot in it, no user name, password or port, no spaces. 'example.ac.uk/x' gains https://."""
    text = (value or "").strip()
    if not text or len(text) > MAX_URL or re.search(r"\s", text):
        return None
    if "://" not in text:
        if re.match(r"^[a-z][a-z0-9+.-]*:", text, re.I) and not re.match(r"^[^:/]+\.[^:/]+[:/]?", text):
            return None  # another scheme, such as javascript:
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname or ""
    if parts.scheme not in ("http", "https") or port is not None or parts.username or parts.password or "." not in host:
        return None
    try:
        ipaddress.ip_address(host)
        return None  # an address, not a name
    except ValueError:
        pass
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, parts.query, parts.fragment))


def search_links(*, university: str, locations: list[str], fields: list[str], titles: list[str], companies: list[str],
                 events_url: str | None) -> dict:
    """Where to look for people and events: LinkedIn alumni searches, Meetup and Eventbrite searches
    for each field and city, the university's own events page, and professional bodies."""
    fields, cities = _unique(fields, MAX_FIELDS), _unique(locations, MAX_CITIES)
    page = safe_url(events_url) if events_url else None
    return {
        "people": _people(" ".join((university or "").split()), _unique(companies, MAX_COMPANIES), _unique(titles, MAX_TITLES)),
        "meetup": _meetup(fields, cities),
        "eventbrite": _eventbrite(fields, cities),
        "university": {"label": "Your university's careers events", "url": page} if page else None,
        "bodies": bodies_for([*fields, *titles]),
    }
