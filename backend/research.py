"""Researching one company for a prep pack: what Companies House, the company's own website and a
web search say about it, as a brief in which every line names its source.

The four sources are read side by side, and any of them may fail without stopping the others.
Companies House lines are written here, by code. Everything else comes from the model, which is
given only numbered passages of what was fetched and must cite one for each statement
(ai.company_brief checks each against its passage). A brief is shared by every user for
FRESH_DAYS, found by its lookup key."""
import logging
from datetime import date
from urllib.parse import urlsplit

import ai
import companies_house
import fetcher
import sponsors
import websearch
from parallel import together

log = logging.getLogger("research")

FRESH_DAYS = 14
PASSAGE_CHARS = 700
MAX_WEBSITE_PASSAGES = 18
MAX_SIC = 3
NOTHING_FOUND = "We could not find anything about {name} in the sources we checked."
REGISTRY_TITLE = "Companies House"
MISSING = {"registry": "Companies House", "news": "the news search", "competitors": "the competitor search"}
WEBSITE_MISSING = {"robots": "their website, which asks automated readers not to read it",
                   "timeout": "their website, which did not answer in time",
                   "address": "their website, which could not be reached",
                   "unreachable": "their website, which could not be reached"}
WEBSITE_UNREAD = "their website, which could not be read"
FAILURES = (companies_house.CompaniesHouseError, websearch.SearchError, ValueError)


def _host(url: str | None) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.") if url else ""


def lookup_key(*, name: str, number: str | None, website: str | None) -> str:
    """Where a company's research is kept: its Companies House number, or its normalised name when
    it has none, with the website's host, so a different website is a different record."""
    who = f"ch:{number}" if number else f"name:{sponsors.normalise(name)}"
    return f"{who}|{_host(website)}"


# ---------- reading the sources ----------

def gather(*, name: str, number: str | None, website: str | None, today: date) -> dict:
    """Everything the four sources say, read at the same time. A source that fails is named in
    `missing` (and the website says why); nothing here raises."""
    work = {
        "registry": (lambda: companies_house.profile(number)) if number else None,
        "website": (lambda: fetcher.site(website)) if website else None,
        "news": lambda: websearch.news(name, today),
        "competitors": lambda: websearch.competitors(name),
    }

    def run(item):
        source, read = item
        if read is None:
            return source, None, False
        try:
            return source, read(), False
        except FAILURES as e:
            log.warning("research source %s failed: %s", source, type(e).__name__)
            return source, None, True
    results = {source: (value, failed) for source, value, failed in together(run, list(work.items()))}

    missing = [MISSING[s] for s in ("registry",) if results["registry"][1]]
    pages, problems = results["website"][0] or ([], [])
    if website and not pages:
        missing.append(WEBSITE_MISSING.get(problems[0] if problems else "", WEBSITE_UNREAD))
    missing += [MISSING[s] for s in ("news", "competitors") if results[s][1]]
    return {"registry": results["registry"][0], "pages": pages, "news": results["news"][0] or [],
            "competitors": results["competitors"][0] or [], "missing": missing}


# ---------- what code writes from the register ----------

def _long_date(value) -> str:
    value = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{value.day} {value:%B %Y}"


def registry_facts(registry: dict) -> list[dict]:
    """The register's own facts, worded by code: name, number and age; status; office; nature of business."""
    lines = []
    made = f", incorporated on {_long_date(registry['incorporated_on'])}" if registry.get("incorporated_on") else ""
    lines.append(("size", f"Registered at Companies House as {registry['name']}, company number {registry['number']}{made}."))
    status = registry.get("status", "").lower()
    if status == "dissolved":
        lines.append(("size", "Companies House lists this company as dissolved."))
    elif status:
        lines.append(("size", f"Companies House lists the company as {status}."))
    if registry.get("town"):
        lines.append(("size", f"Registered office in {registry['town']}."))
    for sic in registry.get("sic", [])[:MAX_SIC]:
        if sic.get("description"):
            words = sic["description"][:1].lower() + sic["description"][1:]
            lines.append(("what_they_do", f"Nature of business: {words} (SIC {sic['code']})."))
    return [{"section": section, "text": text, "quote": "", "url": registry["url"], "source_title": REGISTRY_TITLE,
             "kind": "registry", "published_on": None} for section, text in lines]


# ---------- the numbered passages the model is given ----------

def _chunks(text: str) -> list[str]:
    """A page's text in passages of at most PASSAGE_CHARS, split between lines. A line of one word
    (a menu item, a button) is left out."""
    chunks, current = [], ""
    for line in text.split("\n"):
        line = line.strip()
        if len(line.split()) < 2:
            continue
        line = line[:PASSAGE_CHARS]
        if current and len(current) + 1 + len(line) > PASSAGE_CHARS:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    return chunks + ([current] if current else [])


def passages(gathered: dict) -> list[dict]:
    """Every passage, numbered from 1: the website's (each page in turn, so every page is heard
    before any is heard twice, at most MAX_WEBSITE_PASSAGES), then news, then competitors."""
    found, seen = [], set()
    per_page = [[(page, chunk) for chunk in _chunks(page["text"])] for page in gathered["pages"]]
    turn = 0
    while len(found) < MAX_WEBSITE_PASSAGES and any(turn < len(chunks) for chunks in per_page):
        for chunks in per_page:
            if turn < len(chunks) and len(found) < MAX_WEBSITE_PASSAGES and chunks[turn][1] not in seen:
                page, chunk = chunks[turn]
                seen.add(chunk)
                found.append({"kind": "website", "url": page["url"], "title": page["title"], "text": chunk, "published_on": None})
        turn += 1
    for kind in ("news", "competitors"):
        found += [{"kind": kind, "url": r["url"], "title": r["title"], "text": r["snippet"], "published_on": r["published_on"]}
                  for r in gathered[kind]]
    return [{"n": n} | p for n, p in enumerate(found, start=1)]


# ---------- the brief ----------

def brief(name: str, gathered: dict, today: date) -> dict:
    """{facts, missing, notice}: the register's lines and the model's checked statements, each with
    its source's address, title, kind and date, ordered by section. With nothing fetched at all, no
    model call is made and the notice says nothing was found. A failed model call raises AIError."""
    facts = registry_facts(gathered["registry"]) if gathered["registry"] else []
    numbered = passages(gathered)
    by_n = {p["n"]: p for p in numbered}
    for s in ai.company_brief(name, numbered, today) if numbered else []:
        p = by_n[s["source"]]
        facts.append({"section": s["section"], "text": s["text"], "quote": s["quote"], "url": p["url"],
                      "source_title": p["title"] or _host(p["url"]), "kind": p["kind"],
                      "published_on": p["published_on"].isoformat() if p["published_on"] else None})
    facts.sort(key=lambda f: ai.BRIEF_SECTIONS.index(f["section"]))
    return {"facts": [{"id": f"f{i}"} | f for i, f in enumerate(facts, start=1)], "missing": gathered["missing"],
            "notice": None if facts else NOTHING_FOUND.format(name=name)}
