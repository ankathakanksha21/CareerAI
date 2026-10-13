"""One import of a user's background (a coach call, pasted text, a CV file): what the model is
asked, where each achievement it finds happened, and which CV facts to offer the user.

Achievements are saved straight away. Jobs, courses, skills and languages are only proposed:
nothing here is saved until the user confirms it. Pure functions; the routes do the reading
and writing."""
import re

import ai
from parallel import together
from sponsors import normalise

FACTS_FAILED = "We could not pick out your education and work history this time. Add them on your Profile page."
MIN_NAME_CHARS = 4  # a shorter name found inside a longer one proves nothing ("IT" in "Zzqx IT Services")
SMALL_WORDS = {"of", "the", "and", "in", "at", "for"}
FILLABLE = {"work_history": ("job_title", "location", "country", "start_month", "end_month", "employer_context"),
            # not the qualification or subject: a course is matched on those, so the saved entry already says them
            "education": ("start_month", "end_month", "grade", "country")}
NAMED_BY = {"work_history": "employer", "education": "institution"}


def read(text: str, profile: dict, source: str, achievements: list) -> dict:
    """Ask for achievements and for CV facts at the same time, which halves the wait. Returns
    {"items", "pitch", "facts"}. If only the facts call fails, facts is None and the achievements
    still count; if the achievements call fails, the whole import has failed."""
    def attempt(task):
        try:
            return task()
        except ai.AIError as e:
            return e
    found, facts = together(attempt, [lambda: ai.extract_achievements(text, profile, source, achievements),
                                      lambda: ai.extract_facts(text, profile, source)])
    if isinstance(found, Exception):
        raise found
    return {"items": found["items"], "pitch": found["pitch"], "facts": None if isinstance(facts, Exception) else facts}


def _words(text) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def same(a: str, b: str) -> bool:
    """Whether two wordings name the same employer, institution or course: the same once company
    suffixes are dropped ("Zzqx Holdings Ltd", "Zzqx Holdings Limited"), the same words in another
    order ("University of Zzqx", "Zzqx University"), or one found whole inside the other
    ("Systems Engineer, Zzqx Holdings Ltd, Pune")."""
    x, y = _words(a), _words(b)
    if not x or not y:
        return False
    if normalise(a) == normalise(b) or set(x) - SMALL_WORDS == set(y) - SMALL_WORDS:
        return True
    short, long = sorted((" ".join(x), " ".join(y)), key=len)
    return len(short) >= MIN_NAME_CHARS and f" {short} " in f" {long} "


def _match(entry: dict, table: str, saved: list) -> dict | None:
    """The saved job or course this found one repeats, if any. Another role at the same employer,
    or another course at the same university, is a different entry."""
    for row in saved:
        if not same(entry[NAMED_BY[table]], row[NAMED_BY[table]]):
            continue
        if table == "work_history":
            if not entry["job_title"] or not row["job_title"] or same(entry["job_title"], row["job_title"]):
                return row
        elif same(f"{entry['qualification']} {entry['subject']}", f"{row['qualification']} {row['subject']}"):
            return row
    return None


def place(items: list, facts: dict | None, work: list, education: list) -> list[dict]:
    """Each achievement with where it happened. One at a saved job or course gains
    work_history_id or education_id. One at a job or course only just found gains
    "proposal": (table, index into the facts), to be linked when the user confirms it."""
    saved = {"work_history": work, "education": education}
    found = {table: (facts or {}).get(table) or [] for table in saved}
    placed = []
    for item in items:
        where, out = item.get("where") or "", dict(item) | {"proposal": None}
        for table, column in (("work_history", "work_history_id"), ("education", "education_id")):
            row = next((r for r in saved[table] if same(where, r[NAMED_BY[table]])), None)
            if row:
                out[column] = row["id"]
                break
        else:
            out["proposal"] = next(((table, i) for table in found for i, entry in enumerate(found[table])
                                    if same(where, entry[NAMED_BY[table]])), None)
        placed.append(out)
    return placed


def _name(table: str, row: dict) -> str:
    first = row["job_title"] if table == "work_history" else f"{row['qualification']} {row['subject']}".strip()
    return ", ".join(x for x in (first, row[NAMED_BY[table]]) if x)


def proposals(facts: dict | None, items: list, saved_items: list, work: list, education: list, profile: dict) -> dict | None:
    """What to offer the user from the facts found. `items` are the placed achievements and
    `saved_items` the same ones as saved, in the same order.

    A job or course that is new is offered whole. One that repeats a saved entry is offered as
    {"id", "name", "adds"}: only the fields it would fill in, and left out when it adds nothing.
    Each carries the ids of the new achievements that happened there. Skills and languages
    already on the profile are not offered again."""
    if facts is None:
        return None
    happened_at = {}
    for item, row in zip(items, saved_items):
        if item.get("proposal"):
            happened_at.setdefault(item["proposal"], []).append(row["id"])
    offered = {}
    for table, saved in (("work_history", work), ("education", education)):
        offered[table] = []
        for i, entry in enumerate(facts[table]):
            ids, match = happened_at.get((table, i), []), _match(entry, table, saved)
            if not match:
                offered[table].append(entry | {"achievement_ids": ids})
                continue
            adds = {k: entry[k] for k in FILLABLE[table] if entry[k] and not match[k]}
            if match.get("is_current"):
                adds.pop("end_month", None)
            if adds or ids:
                offered[table].append({"id": match["id"], "name": _name(table, match), "adds": adds, "achievement_ids": ids})
    has = {s.lower() for s in profile.get("skills") or []}
    speaks = {x["language"].lower() for x in profile.get("languages") or []}
    offered["skills"] = [s for s in facts["skills"] if s.lower() not in has]
    offered["languages"] = [x for x in facts["languages"] if x["language"].lower() not in speaks]
    return offered
