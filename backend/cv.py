"""The CV document (format 2): which section comes first, how a CV is put together from the
user's stored records and what the model wrote, how an edit is applied, and which of a job's
keywords it covers.

Facts are never taken from the model or from an edit. An employer, job title, date, institution,
qualification, grade or contact detail on a CV is a copy of the stored record, made when the CV
was built, or again when the user asks for it to be brought up to date. Pure functions: nothing
here reads or writes the database."""
import re
from datetime import date

SECTIONS = ("education", "work", "projects", "skills", "additional")  # the profile paragraph always comes first
MAX_JOB_BULLETS, MAX_PROJECTS = 5, 4  # how many show on a new CV; any more the model picked are kept, hidden
RECENT_MONTHS = 24  # still studying, or graduated at most this long ago...
WORK_MONTHS = 24    # ...and worked for less than this: education comes before work experience
JOB_FACTS = ("employer", "job_title", "location", "country", "start_month", "end_month", "is_current", "employer_context")
COURSE_FACTS = ("institution", "qualification", "subject", "start_month", "end_month", "grade", "country")
SKILL_GROUPS = ("technical", "tools", "languages")
LETTER_PARTS = ("why_them", "why_you", "what_you_deliver")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
VISA_LINE = {"graduate": "Right to work in the UK: Graduate visa", "student": "Visa status: Student visa"}
# how much an edit may hold
MAX_ENTRIES, MAX_BULLETS, MAX_LISTED, MAX_LINES = 30, 12, 40, 12
PROFILE_CHARS, BULLET_CHARS, LINE_CHARS, TITLE_CHARS, SKILL_CHARS, LETTER_CHARS = 1500, 600, 300, 160, 60, 2500
AVAILABLE_FROM = 3  # how many achievements are named as showing a keyword


# ---------- dates ----------

def as_date(value) -> date | None:
    """A date from a record (a date) or from a stored CV (ISO text); None for anything else."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value[:10]) if isinstance(value, str) else None
    except ValueError:
        return None


def long_date(day: date) -> str:
    """A date as a UK letter writes it: 14 March 2028."""
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def _stored(value):
    """A fact as it is kept inside a CV: a date becomes ISO text, everything else stays as it is."""
    return value.isoformat() if isinstance(value, date) else value


def _month_number(day: date) -> int:
    return day.year * 12 + day.month


# ---------- which section comes first ----------

def months_worked(work_history: list, today: date) -> int:
    """Months covered by the user's jobs. Two jobs at once count once; a job still held runs to
    today; a job with no start month cannot be counted."""
    covered = set()
    for job in work_history:
        start = as_date(job.get("start_month"))
        if not start:
            continue
        end = today if job.get("is_current") else as_date(job.get("end_month")) or start
        last = min(_month_number(end), _month_number(today))
        covered.update(range(_month_number(start), max(_month_number(start), last) + 1))
    return len(covered)


def education_first(profile: dict, work_history: list, today: date) -> bool:
    """Education leads for someone still studying or recently graduated who has little work
    experience; otherwise work experience leads."""
    graduated = as_date(profile.get("graduation_date"))
    recent = graduated is None or _month_number(today) - _month_number(graduated) <= RECENT_MONTHS
    return recent and months_worked(work_history, today) < WORK_MONTHS


def section_order(profile: dict, work_history: list, today: date) -> list[str]:
    first = ("education", "work") if education_first(profile, work_history, today) else ("work", "education")
    return [*first, "projects", "skills", "additional"]


# ---------- facts copied from the profile ----------

def right_to_work(profile: dict) -> str:
    """The wording offered for the optional right-to-work line: the visa held and the day it ends,
    nothing about what comes after. A Student visa limits working hours, so its line does not
    say "right to work"."""
    lead, ends = VISA_LINE.get(profile.get("visa_type")), as_date(profile.get("visa_end_date"))
    return f"{lead}, valid until {long_date(ends)}." if lead and ends else ""


def contact(profile: dict, email: str) -> dict:
    """The name and contact line. The email is the login's; the GitHub address is the account projects were imported from."""
    github = f"github.com/{profile['github_username']}" if profile.get("github_username") else ""
    return {"name": profile.get("full_name") or "", "city": profile.get("city") or "", "phone": profile.get("phone") or "",
            "email": email or "", "linkedin": profile.get("linkedin_url") or "", "github": github}


def own_skills(profile: dict, achievements: list) -> list[str]:
    """Every skill the user has: the profile's, then those on their achievements, one spelling each."""
    kept, seen = [], set()
    for skill in [*(profile.get("skills") or []), *(s for a in achievements for s in a.get("skills") or [])]:
        name = (skill or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            kept.append(name)
    return kept


def _facts(record: dict, fields: tuple) -> dict:
    return {k: _stored(record.get(k)) for k in fields}


def _by_id(rows: list) -> dict:
    return {str(r["id"]): r for r in rows}


def _link(url) -> str:
    """A repository address as a CV prints it: without the scheme."""
    return re.sub(r"^https?://(www\.)?", "", url or "").rstrip("/")


def _project_facts(achievement: dict, courses: dict) -> dict:
    """Where a project came from: its repository, and the institution if it was part of a course."""
    course = courses.get(str(achievement.get("education_id")))
    return {"link": _link(achievement.get("source_url")), "where": (course or {}).get("institution") or ""}


def _spoken(profile: dict) -> list[str]:
    return [f"{x['language']} ({x['level']})" if x.get("level") else x["language"]
            for x in profile.get("languages") or [] if x.get("language")]


# ---------- putting a CV together ----------

def assemble(*, profile: dict, email: str, education: list, work_history: list, achievements: list, written: dict,
             job: dict | None, today: date) -> dict:
    """A new CV. `written` is what the model wrote: the profile paragraph, bullets each naming one
    of the user's achievements, skills in two groups and, for a job, its keywords, gaps and cover
    letter. Everything else is copied from the records. A bullet goes under the job its achievement
    is linked to; one linked to no job becomes a project."""
    own, courses = _by_id(achievements), _by_id(education)
    work = [{"work_history_id": str(j["id"]), **_facts(j, JOB_FACTS), "hidden": False, "bullets": []} for j in work_history]
    jobs, projects, used = {e["work_history_id"]: e for e in work}, [], set()
    for item in written.get("bullets") or []:
        achievement = own.get(str(item.get("achievement_id")))
        wording = (item.get("text") or "").strip()
        if not achievement or not wording or str(achievement["id"]) in used:
            continue
        used.add(str(achievement["id"]))
        bullet = {"text": wording, "achievement_id": str(achievement["id"]), "hidden": False}
        entry = jobs.get(str(achievement.get("work_history_id")))
        if entry:
            entry["bullets"].append(bullet | {"hidden": len(entry["bullets"]) >= MAX_JOB_BULLETS})
        else:
            projects.append({"achievement_id": bullet["achievement_id"], "title": achievement.get("title") or "",
                             **_project_facts(achievement, courses), "hidden": len(projects) >= MAX_PROJECTS, "bullets": [bullet]})
    skills = own_skills(profile, achievements)
    grouped = written.get("skills") or {}
    technical, tools = list(grouped.get("technical") or []), list(grouped.get("tools") or [])
    if not technical and not tools:  # the model sorted none: the user's own skills still belong on their CV
        technical = skills[:MAX_LISTED]
    content = {
        "contact": contact(profile, email),
        "job": {"title": job["title"], "company": job["company"]} if job else None,
        "profile": (written.get("profile") or "").strip(),
        "section_order": section_order(profile, work_history, today),
        "education": [{"education_id": str(c["id"]), **_facts(c, COURSE_FACTS), "note": "", "hidden": False} for c in education],
        "work": work,
        "projects": projects,
        "skills": {"technical": technical, "tools": tools, "languages": _spoken(profile)},
        "additional": {"lines": [{"text": line, "hidden": False} for line in profile.get("additional") or []]},
        "right_to_work": {"shown": False, "text": right_to_work(profile)},
        "cover_letter": {k: ((written.get("cover_letter") or {}).get(k) or "").strip() for k in LETTER_PARTS} if job else None,
        "gaps": [g.strip() for g in written.get("gaps") or [] if g.strip()] if job else [],
    }
    return content | {"keywords": coverage(list(written.get("keywords") or []) if job else [], content, achievements, skills)}


# ---------- applying an edit ----------

def _list(value) -> list:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _strings(value, limit: int, most: int) -> list[str]:
    kept = [_text(x, limit) for x in value] if isinstance(value, list) else []
    return [x for x in kept if x][:most]


def _bullets(items, own: dict) -> list[dict]:
    """Bullets as the user left them. A bullet may name only one of the user's own achievements."""
    bullets = []
    for item in _list(items):
        wording = _text(item.get("text"), BULLET_CHARS)
        if wording:
            linked = str(item.get("achievement_id") or "")
            bullets.append({"text": wording, "achievement_id": linked if linked in own else "", "hidden": bool(item.get("hidden"))})
    return bullets[:MAX_BULLETS]


def _entries(edited, stored, records: dict, key: str, fields: tuple, refresh: bool, extra) -> list[dict]:
    """Jobs or courses in the order the edit gives them. Each entry's facts are its stored copy,
    or the user's record when the entry is new to this CV or the CV is being brought up to date.
    An entry naming a row that is neither stored here nor the user's is left out."""
    kept, entries, seen = {e.get(key): e for e in _list(stored)}, [], set()
    for item in _list(edited)[:MAX_ENTRIES]:
        row_id = str(item.get(key) or "")
        was, record = kept.get(row_id), records.get(row_id)
        if row_id in seen or not (was or record):
            continue
        seen.add(row_id)
        facts = _facts(record, fields) if record and (refresh or not was) else {k: was.get(k) for k in fields}
        entries.append({key: row_id, **facts, "hidden": bool(item.get("hidden")), **extra(item)})
    if refresh:  # a job or course added to the profile since this CV was built
        entries += [{key: row_id, **_facts(record, fields), "hidden": False, **extra({})} for row_id, record in records.items() if row_id not in seen]
    return entries


def merge(stored: dict, edited: dict, *, profile: dict, email: str, education: list, work_history: list, achievements: list,
          refresh: bool = False) -> dict:
    """The stored CV with a user's edit applied. Wording, order and what is hidden come from the
    edit; every fact comes from the stored copy or the user's own records, never from the edit.
    With `refresh` the facts and contact details are copied from the profile again."""
    own, courses = _by_id(achievements), _by_id(education)
    edited = edited if isinstance(edited, dict) else {}
    kept_projects, projects, seen = {p.get("achievement_id"): p for p in _list(stored.get("projects"))}, [], set()
    for item in _list(edited.get("projects"))[:MAX_ENTRIES]:
        row_id = str(item.get("achievement_id") or "")
        was, achievement = kept_projects.get(row_id), own.get(row_id)
        if row_id in seen or not (was or achievement):
            continue
        seen.add(row_id)
        facts = _project_facts(achievement, courses) if achievement and (refresh or not was) else {k: was.get(k) or "" for k in ("link", "where")}
        title = _text(item.get("title"), TITLE_CHARS) or (was or achievement).get("title") or ""
        projects.append({"achievement_id": row_id, "title": title, **facts, "hidden": bool(item.get("hidden")),
                         "bullets": _bullets(item.get("bullets"), own)})
    order = edited.get("section_order")
    skills, letter, visa = edited.get("skills"), edited.get("cover_letter"), edited.get("right_to_work")
    skills, letter, visa = (x if isinstance(x, dict) else {} for x in (skills, letter, visa))
    lines = _list((edited.get("additional") or {}).get("lines")) if isinstance(edited.get("additional"), dict) else []
    content = {
        "contact": contact(profile, email) if refresh else stored.get("contact") or contact(profile, email),
        "job": stored.get("job"),
        "profile": _text(edited.get("profile"), PROFILE_CHARS),
        "section_order": list(order) if isinstance(order, list) and sorted(map(str, order)) == sorted(SECTIONS) else stored.get("section_order") or list(SECTIONS),
        "education": _entries(edited.get("education"), stored.get("education"), courses, "education_id", COURSE_FACTS, refresh,
                              lambda item: {"note": _text(item.get("note"), LINE_CHARS)}),
        "work": _entries(edited.get("work"), stored.get("work"), _by_id(work_history), "work_history_id", JOB_FACTS, refresh,
                         lambda item: {"bullets": _bullets(item.get("bullets"), own)}),
        "projects": projects,
        "skills": {group: _strings(skills.get(group), SKILL_CHARS, MAX_LISTED) for group in SKILL_GROUPS},
        "additional": {"lines": [{"text": text, "hidden": bool(line.get("hidden"))}
                                 for line in lines if (text := _text(line.get("text"), LINE_CHARS))][:MAX_LINES]},
        "right_to_work": {"shown": bool(visa.get("shown")), "text": _text(visa.get("text"), LINE_CHARS)},
        "cover_letter": {k: _text(letter.get(k), LETTER_CHARS) for k in LETTER_PARTS} if stored.get("cover_letter") else None,
        "gaps": stored.get("gaps") or [],
    }
    terms = (stored.get("keywords") or {}).get("terms") or []
    return content | {"keywords": coverage(terms, content, achievements, own_skills(profile, achievements))}


# ---------- what a reader sees, and which keywords it covers ----------

def _shown(items) -> list[dict]:
    return [x for x in items or [] if not x.get("hidden")]


def text(content: dict) -> str:
    """Every word a reader of the CV sees, one piece to a line. Hidden entries, hidden bullets and
    the cover letter are not part of it."""
    parts = [content.get("profile")]
    for course in _shown(content.get("education")):
        parts += [course.get(k) for k in ("institution", "qualification", "subject", "grade", "note")]
    for job in _shown(content.get("work")):
        parts += [job.get(k) for k in ("employer", "job_title", "employer_context")] + [b["text"] for b in _shown(job.get("bullets"))]
    for project in _shown(content.get("projects")):
        parts += [project.get("title")] + [b["text"] for b in _shown(project.get("bullets"))]
    for group in SKILL_GROUPS:
        parts += (content.get("skills") or {}).get(group) or []
    parts += [line["text"] for line in _shown((content.get("additional") or {}).get("lines"))]
    visa = content.get("right_to_work") or {}
    if visa.get("shown"):
        parts.append(visa.get("text"))
    return "\n".join(p for p in parts if p)


def _tokens(text: str) -> list[str]:
    """Words as an applicant-tracking system compares them: lower case, punctuation dropped, but
    "c++", "c#" and "node.js" kept whole."""
    return re.findall(r"[^\W_](?:[\w+#.]*[\w+#])?", text.lower().replace("'", "").replace("’", ""))


def _same_word(a: str, b: str) -> bool:
    short, long = sorted((a, b), key=len)
    return a == b or long in (short + "s", short + "es")


def has_term(term: str, text: str) -> bool:
    """Whether the text says the term: the same words in the same order, give or take a plural."""
    wanted, words = _tokens(term), _tokens(text)
    return bool(wanted) and any(all(_same_word(w, words[at + n]) for n, w in enumerate(wanted))
                                for at in range(len(words) - len(wanted) + 1))


def coverage(terms: list[str], content: dict, achievements: list, skills: list[str]) -> dict:
    """Each of the job's main terms in one of three groups: covered (its words are in the CV as it
    will print), available (not in the CV, but in the user's profile, with the unused achievements
    that show it) or missing (nowhere in the profile: a gap, never added for them)."""
    seen, on_cv = text(content), set()
    for entry in [*_shown(content.get("work")), *_shown(content.get("projects"))]:
        on_cv.update(b.get("achievement_id") for b in _shown(entry.get("bullets")))
    described = {str(a["id"]): " \n ".join([a.get("title") or "", a.get("uk_version") or "", a.get("outcome") or "", a.get("scale") or "",
                                             *(a.get("skills") or [])]) for a in achievements}
    covered, available, missing = [], [], []
    for term in terms:
        if has_term(term, seen):
            covered.append(term)
            continue
        shows = [row_id for row_id, words in described.items() if has_term(term, words)]
        if shows or any(has_term(term, skill) for skill in skills):
            available.append({"term": term, "achievement_ids": [x for x in shows if x not in on_cv][:AVAILABLE_FROM]})
        else:
            missing.append(term)
    return {"terms": list(terms), "covered": covered, "available": available, "missing": missing}
