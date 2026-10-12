"""Finding and judging jobs: which searches to run for a user, which adverts to score first,
and how an advert's fit is worked out. Pure functions and outside calls; the SQL is in repo.py."""
import re
import statistics
from concurrent.futures import ThreadPoolExecutor

import ai
import reed
import sponsors

CACHE_HOURS = 6            # a search anyone ran this recently is read from the database, not from Reed
FRESH_DAYS = 14            # adverts older than this are not shown
NEW_DAYS = 2               # "posted in the last 48 hours": Reed gives a date, not a time
TITLES_PER_FAMILY = 3
SEARCHES_PER_REFRESH = 20  # keeps one refresh well inside the 60-second request limit
SCORE_PER_REFRESH = 15
SCORE_BATCH = 5            # adverts per model call; the calls run side by side
WORKERS = 8

FIT_BANDS = ((80, "direct"), (60, "near"), (40, "stretch"))  # below the last: not a match
SHOWN_ON_CARD = 3
SENIOR = re.compile(r"\b(senior|lead|principal|head|director|manager)\b", re.I)
# Reed lists many training and recruitment companies as "direct employers". A name with one of
# these words in it is not the employer of the job advertised...
NOT_THE_EMPLOYER = re.compile(r"recruit|career|staffing|resourcing|\brpo\b|training|(?<!machine )(?<!deep )learning|\bcourses?\b|bootcamp", re.I)
# ...a name with one of these sells courses...
TRAINING_COMPANY = re.compile(r"training|(?<!machine )(?<!deep )learning|\bcourses?\b|bootcamp", re.I)
# ...and so does a recruiter whose advert reads like this.
PROGRAMME = re.compile(r"career programme|training programme|no experience (is )?(required|needed|necessary)|job guarantee|"
                       r"guaranteed job|launch your new career", re.I)


def _tidy(text: str) -> str:
    return " ".join(text.lower().split())


# ---------- which searches to run ----------

def plan(families: list[dict], locations: list[str]) -> list[dict]:
    """The searches for a user: each targeted family's first few UK job titles (its name if it has
    none) in each preferred location. A search two families share runs once, under the first."""
    seen, searches = set(), []
    for family in families:
        if not family.get("targeted"):
            continue
        titles = [t for t in map(_tidy, family.get("uk_titles") or []) if t][:TITLES_PER_FAMILY] or [_tidy(family["name"])]
        for title in titles:
            for place in map(_tidy, locations):
                if title and place and (title, place) not in seen:
                    seen.add((title, place))
                    searches.append({"family_id": family["id"], "query": title, "location": place})
    return searches


def is_senior(title: str) -> bool:
    return bool(SENIOR.search(title))


def poster(item: dict) -> str:
    """Who really placed an advert: "employer", "agency" (a recruiter or job board, so the employer
    is not named) or "training" (it sells a course, not a job). Reed's own flag is the starting
    point; the company's name, and for a recruiter the advert's wording, can only move an advert
    away from "employer". A real employer's trainee job is left alone."""
    name = item["employer"]
    if TRAINING_COMPANY.search(name):
        return "training"
    if NOT_THE_EMPLOYER.search(name):
        return "training" if PROGRAMME.search(f"{item['title']} {item['description']}") else "agency"
    return item["posted_by"]


def _same_job(item: dict) -> tuple | None:
    """What makes two adverts the same job. None when the employer is unknown: those are never merged."""
    return (_tidy(item["title"]), item["employer_key"], _tidy(item["location"])) if item["employer_key"] else None


def dedupe(listings: list[dict], keep: list[dict] = ()) -> list[dict]:
    """One advert per title, employer and town: employers repost the same job under a new id.
    The most recently posted is kept, except that an advert the user already has (`keep`) always
    wins, so a job they saved or dismissed does not come back when it is posted again."""
    taken = {_same_job(item): item["id"] for item in keep if _same_job(item)}
    kept = {}
    for n, item in enumerate(listings):
        key = _same_job(item) or n
        if taken.get(key, item["id"]) != item["id"]:
            continue
        if key not in kept or item["posted_on"] > kept[key]["posted_on"]:
            kept[key] = item
    return list(kept.values())


# ---------- which adverts to score first ----------

def skills_of(achievements: list[dict]) -> list[str]:
    """The distinct skills named across the user's achievements, lower-cased."""
    return list(dict.fromkeys(s for a in achievements for s in map(_tidy, a.get("skills") or []) if s))


def _mentions(text: str, skills: list[str]) -> int:
    """How many of the skills appear as whole words ("R" is not found in "Recruiter")."""
    text = text.lower()
    return sum(bool(re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", text)) for s in {_tidy(s) for s in skills} if s)


def shortlist(candidates: list[dict], skills: list[str], include_senior: bool, limit: int) -> list[dict]:
    """The unscored adverts most worth the model's time: those mentioning most of the user's
    skills, newest first among equals. Senior titles are left out unless the user asked for them,
    and a training programme is never scored: it is not a job."""
    wanted = [c for c in candidates if c["posted_by"] != "training" and (include_senior or not is_senior(c["title"]))]
    by_newest = sorted(wanted, key=lambda c: c["posted_on"], reverse=True)
    return sorted(by_newest, key=lambda c: -_mentions(f"{c['title']} {c['description']}", skills))[:limit]


# ---------- outside calls, several at once ----------

def _together(work, items) -> list:
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(items))) as pool:
        return list(pool.map(work, items))


def fetch(searches: list[dict]) -> tuple[dict, int]:
    """Run the searches on Reed side by side. Returns {(query, location): listings} for those that
    worked, each listing with who really placed it and the key its employer is looked up by, and
    how many searches failed."""
    def one(search):
        try:
            return reed.search_both(search["query"], search["location"])
        except reed.ReedError:
            return None

    found = dict(zip(((s["query"], s["location"]) for s in searches), _together(one, searches)))
    done = {key: [item | {"employer_key": sponsors.employer_key(item["employer"]), "posted_by": poster(item)} for item in listings]
            for key, listings in found.items() if listings is not None}
    # a company seen selling a programme sells one in its other adverts too, whatever their short text says
    sellers = {item["employer"] for listings in done.values() for item in listings if item["posted_by"] == "training"}
    for listings in done.values():
        for item in listings:
            if item["employer"] in sellers:
                item["posted_by"] = "training"
    return done, len(found) - len(done)


def fetch_details(candidates: list[dict]) -> dict[str, dict]:
    """The full advert for each candidate that only has the short search text, by listing id.
    One that cannot be fetched is simply absent and is scored on what there is."""
    def one(candidate):
        try:
            return reed.details(candidate["source_id"])
        except reed.ReedError:
            return None

    short = [c for c in candidates if not c["description_is_full"]]
    return {c["listing_id"]: d for c, d in zip(short, _together(one, short)) if d}


# ---------- fit ----------

def fit_label(percent: int) -> str:
    return next((label for floor, label in FIT_BANDS if percent >= floor), "none")


def fit(requirements: list[dict], achievement_titles: list[str]) -> dict | None:
    """How much of what an advert asks for the user already shows: requirements evidenced, out of
    requirements listed. A requirement counts only if the model named an achievement the user
    really has. None when the advert listed nothing to judge."""
    mine = {t.strip().lower(): t for t in achievement_titles}
    shown, gaps = [], []
    for r in requirements:
        text = r["need"].strip()
        if not text:
            continue
        title = mine.get(r.get("shown_by", "").strip().lower())
        if title:
            shown.append({"need": text, "achievement": title})
        else:
            gaps.append(text)
    total = len(shown) + len(gaps)
    if not total:
        return None
    percent = round(100 * len(shown) / total)
    return {"percent": percent, "label": fit_label(percent), "shown": shown[:SHOWN_ON_CARD], "gaps": gaps[:SHOWN_ON_CARD]}


def score(candidates: list[dict], achievements: list[dict]) -> tuple[list[dict], int]:
    """Judge the candidates against the user's achievements, a few adverts per model call, the calls
    side by side. Returns rows for repo.save_scores and how many adverts came back unjudged.
    A failed call loses only its own adverts; AIError is raised only if every call failed."""
    titles = [a["title"] for a in achievements]
    batches = [candidates[i:i + SCORE_BATCH] for i in range(0, len(candidates), SCORE_BATCH)]

    def one(batch):
        adverts = [{"n": n, "title": c["title"], "employer": c["employer"], "description": c["description"]} for n, c in enumerate(batch, 1)]
        try:
            judged = ai.score_jobs(adverts, achievements)
        except ai.AIError:
            return None
        return [{"match_id": c["match_id"], "fit": fit(judged[n], titles), "from_summary": not c["description_is_full"]}
                for n, c in enumerate(batch, 1) if n in judged]

    results = _together(one, batches)
    if batches and all(r is None for r in results):
        raise ai.AIError("job fit")
    rows = [row for r in results if r for row in r]
    return rows, len(candidates) - len(rows)


# ---------- figures for the role family cards ----------

def median(values: list) -> int | None:
    return round(statistics.median(values)) if values else None


def market(raw: dict[str, dict]) -> dict[str, dict]:
    """repo.family_market with each family's salaries reduced to their median and how many there were."""
    return {family_id: {"jobs": m["jobs"], "named": m["named"], "listed": m["listed"],
                        "salary_median": median(m["salaries"]), "salary_n": len(m["salaries"])}
            for family_id, m in raw.items()}
