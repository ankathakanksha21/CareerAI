"""Every AI step: one prompt in, JSON out, shaped to what the UI expects.

A step returns the model's own result or raises AIError. Nothing is ever substituted for a
failed call, so a user never sees content that did not come from their own data."""
import json
import logging
import re
from datetime import date, timedelta

import anthropic
import httpx

import cv
import networking
import peers
from llm import complete_json

log = logging.getLogger("ai")

BASE = (
    "You are the AI inside a UK career navigator for international students and recent graduates. "
    "Write in British English, plainly and specifically. Never invent employers, numbers "
    "or achievements that are not in the input. No em dashes."
)
ATTEMPTS = 2  # the first call plus one retry
FITS = ("direct", "near", "stretch")
STRENGTHS = ("strong", "needs a number", "needs detail")
NOT_SHOWN = {"", "none", "gap", "n/a", "na", "-", "null", "nothing"}
MAX_ITEMS = {"voice": 6, "paste": 8, "cv": 8}  # achievements taken from one import
TEXT_NAME = {"voice": "Background transcript", "paste": "Pasted text", "cv": "CV text"}
LANGUAGE_LEVELS = ("Native", "Fluent", "Professional", "Conversational", "Basic")
_LEVEL_WORDS = (("Native", ("native", "mother tongue", "first language", "bilingual")), ("Fluent", ("fluent",)),
                ("Professional", ("professional", "advanced", "proficient", "business")),
                ("Conversational", ("conversational", "intermediate")), ("Basic", ("basic", "beginner", "elementary")))
STILL_THERE = {"present", "current", "now", "ongoing", "to date", "till date", "today"}
MAX_SKILLS, MAX_SKILL_CHARS = 40, 60
MIN_NAME_SHARE = 0.5  # how much of an employer's or institution's name must be in the text for it to be kept


class AIError(Exception):
    """The model could not produce a usable result for this task."""


def _empty(template):
    if isinstance(template, dict):
        return {k: _empty(v) for k, v in template.items()}
    return [] if isinstance(template, list) else 0 if isinstance(template, int) else ""


def _int(value) -> int:
    """The first whole number in a reply such as 4, "4/5" or "85%"; 0 when there is none."""
    m = re.search(r"-?\d+", str(value))
    return int(m.group()) if m else 0


def _conform(data, template):
    """Coerce model JSON to the template's keys and types, so the UI never meets a
    missing field or a string where it expects a list. Extra keys are kept."""
    if not isinstance(data, dict):
        return _empty(template)
    out = dict(data)
    for k, t in template.items():
        v = data.get(k)
        if isinstance(t, dict):
            out[k] = _conform(v, t)
        elif isinstance(t, list):
            v = v if isinstance(v, list) else [] if v in (None, "") else [v]
            if t and isinstance(t[0], dict):  # list of objects: conform each, wrap bare strings
                first = next(iter(t[0]))
                v = [_conform(x if isinstance(x, dict) else {first: str(x)}, t[0]) for x in v]
            else:
                v = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in v]
            out[k] = v
        elif isinstance(t, int) and not isinstance(t, bool):
            out[k] = _int(v)
        else:
            out[k] = v if isinstance(v, str) else "" if v is None else str(v)
    return out


def _blank(value) -> bool:
    if isinstance(value, dict):
        return all(_blank(v) for v in value.values())
    if isinstance(value, list):
        return all(_blank(v) for v in value)  # an empty list, or a list of empty things
    if isinstance(value, str):
        return not value.strip()
    return value is None


def _run(task: str, system: str, user: str, template: dict, max_tokens: int = 1500, required: tuple = (), check=None) -> dict:
    """One AI task: the model's reply in the template's shape. A reply that is malformed, lacks a
    required field or fails `check` counts as a failed attempt and is asked for once more."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            data = _conform(complete_json(BASE + "\n\n" + system, user, max_tokens), template)
        except (ValueError, httpx.HTTPError, anthropic.APIError) as e:
            # the exception type only: prompts and replies hold personal data and stay out of the logs
            log.warning("AI task %s, attempt %d: %s", task, attempt, type(e).__name__)
            continue
        missing = [k for k in required if _blank(data.get(k))]
        if missing:
            log.warning("AI task %s, attempt %d: reply had no %s", task, attempt, ", ".join(missing))
        elif check and not check(data):
            log.warning("AI task %s, attempt %d: reply failed its check", task, attempt)
        else:
            return data
    raise AIError(task)


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


SPEAKER = re.compile(r"^\s*(coach|interviewer|candidate)\s*:\s?(.*)$", re.I)


def _said_by_candidate(transcript: str) -> str:
    """Only what the candidate said in a call transcript. A line with no speaker label continues
    the previous speaker's turn. Text with no labels at all (a pasted CV) is all the candidate's;
    a call in which the candidate never spoke yields nothing, never the other speaker's words."""
    labelled, speaker, mine = False, None, []
    for line in transcript.splitlines():
        m = SPEAKER.match(line)
        if m:
            labelled, speaker, line = True, m.group(1).lower(), m.group(2)
        if speaker == "candidate":
            mine.append(line)
    return "\n".join(mine) if labelled else transcript


MIN_SHARED_SHARE = 0.5  # how much of a paraphrase must appear in one sentence to count as its source...
MIN_SHARED_WORDS = 3    # ...and at least this many words, so one common word never makes a match


WRAPPED_LINES = 5       # a sentence in a document can be wrapped across this many lines


def _closest_passage(lines: list[str], wanted: set) -> tuple[str, int]:
    """The run of consecutive lines sharing most words with `wanted`, and how many it shares. A
    PDF wraps sentences wherever the page was narrow, so one line is often half a sentence. Between
    runs that share as much, one that ends a sentence wins, then the shorter."""
    best, best_rank = "", (0, False, 0)
    for start in range(len(lines)):
        for size in range(1, WRAPPED_LINES + 1):
            passage = " ".join(lines[start:start + size])
            rank = (len(set(_words(passage)) & wanted), passage.endswith((".", "!", "?")), -len(passage))
            if rank > best_rank:
                best, best_rank = passage, rank
    return best, best_rank[0]


def verbatim(quote: str, transcript: str, speech: bool = True) -> str:
    """What the candidate actually said or wrote that backs up `quote`, so the app never shows
    words that are not theirs. The quote itself if the text has exactly that (ignoring case,
    punctuation and line breaks), otherwise the part of it that shares most words with the quote,
    otherwise an empty string.

    With speech, the text is a call transcript or pasted notes: lines labelled as the coach's or
    the interviewer's are not the candidate's. Without it, the text is a document (a CV, a README):
    every line counts, even one that happens to begin "Coach:"."""
    said = _said_by_candidate(transcript) if speech else transcript
    wanted = _words(quote)
    if not wanted:
        return ""
    if f" {' '.join(wanted)} " in f" {' '.join(_words(said))} ":
        return quote.strip()
    if speech:
        best, best_shared = "", 0
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", said):
            shared = len(set(_words(sentence)) & set(wanted))
            if shared > best_shared:
                best, best_shared = sentence.strip(), shared
    else:
        best, best_shared = _closest_passage([line.strip() for line in said.splitlines() if line.strip()], set(wanted))
    enough = best_shared >= MIN_SHARED_WORDS and best_shared / len(set(wanted)) >= MIN_SHARED_SHARE
    return best[:300] if enough else ""


def _key(text: str) -> str:
    """A wording reduced to its words, to tell whether two are the same."""
    return " ".join(_words(text))


def month(value) -> date | None:
    """A date the model gave as YYYY-MM. Anything else ("2021", "Summer 2022") is no date at all:
    a month is never guessed."""
    m = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", value.strip() if isinstance(value, str) else "")
    return date(int(m[1]), int(m[2]), 1) if m and 1950 <= int(m[1]) <= 2100 else None


NO_NUMBER = "Add a number"  # how the model marks a result with no figure, followed by what to measure
_PLACEHOLDER = re.compile(r"add a number\s*:?\s*<[^>]*>", re.I)


def _outcome(text: str) -> str:
    """A result as the model gave it, unless it copied the prompt's own "<what to measure>"
    placeholder: then only the marker is kept."""
    text = text.strip()
    return NO_NUMBER if _PLACEHOLDER.fullmatch(text) else text


def needs_number(achievement: dict) -> bool:
    """True when an achievement has no figure yet: neither its bullet nor its result holds a digit.
    A result that is only the extraction's "Add a number: ..." marker says what to measure and is
    not a figure; and the marker beside a bullet that already has a number is ignored."""
    outcome = (achievement.get("outcome") or "").strip()
    result = "" if outcome.lower().startswith("add a number") else outcome
    return not re.search(r"\d", f"{achievement.get('uk_version') or ''} {result}")


def _who(profile: dict) -> str:
    """One line on the candidate from the facts they typed in."""
    study = " at ".join(x for x in (profile.get("course"), profile.get("university")) if x)
    visa = f"{profile['visa_type'].capitalize()} visa" if profile.get("visa_type") else ""
    return ", ".join(x for x in (profile.get("full_name"), study, visa) if x)


# 1. A voice call, pasted text or the text of a CV file to achievements
def extract_achievements(text: str, profile: dict, source: str = "voice", existing=()) -> dict:
    """Achievements found in the text that are not in `existing` (the user's saved ones), each with
    `where`: the employer or institution it happened at, as the text names it."""
    system = (
        "Turn a candidate's spoken or written background into achievements written for UK employers. "
        "Each item is one achievement. Use only facts, tools, methods and data sources the text actually states; never add detail it does not contain. "
        "uk_version is a single UK CV bullet: action verb first, result with a number, scale. "
        "If the text gives no number, do not make one up: set outcome to 'Add a number: <what to measure>'. "
        "context_note explains something a UK recruiter would not know (an overseas employer, a local term, a grading scale, why it counts) "
        "or gives one UK framing tip. "
        "where is the employer, or the university, college or school, at which it happened, named exactly as the text names it. "
        "Use an empty string for a personal project or when the text does not say. "
        + ("Text taken from a CV file can arrive out of order, with a side column mixed into the main one: read it as a whole. " if source == "cv" else "")
        + ("Some achievements are already in the candidate's profile and are listed. Do not return those again: return only achievements that are not listed. "
           if existing else "")
        + "If the text contains no achievements at all, or none that are new, return an empty items list."
    )
    saved = [a.get("uk_version") or a.get("title") or "" for a in existing][:40]
    user = (
        f"Candidate: {_who(profile)}.\n"
        + (f"Already in the profile: {_j(saved)}\n" if existing else "")
        + f"{TEXT_NAME[source]}:\n{text}\n\n"
        'Return {"items":[{"title":str,"raw":str (an exact quote copied from the text, under 25 words),"uk_version":str,"skills":[str],'
        '"outcome":str,"scale":str,"context_note":str,"where":str}],'
        '"pitch":str (two sentences in the first person, starting with I am, for networking)}. '
        + ("3 to 6 items." if source == "voice" else f"Up to {MAX_ITEMS[source]} items, strongest first.")
    )
    template = {"items": [{"title": "", "raw": "", "uk_version": "", "skills": [""], "outcome": "", "scale": "", "context_note": "", "where": ""}],
                "pitch": ""}
    data = _run("achievements", system, user, template, 2800)
    items, seen = [], {_key(x) for a in existing for x in (a.get("uk_version") or "",) if x}
    for item in data["items"]:
        bullet = item["uk_version"].strip() or item["raw"].strip() or item["title"].strip()
        if not bullet or _key(bullet) in seen:  # nothing in it, or already saved or returned
            continue
        seen.add(_key(bullet))
        # "raw" is shown to the user as their own words, so it must be found in what they said or wrote
        items.append(item | {"uk_version": bullet, "title": item["title"].strip() or bullet[:60], "where": item["where"].strip(),
                             "outcome": _outcome(item["outcome"]), "raw": verbatim(item["raw"] or bullet, text, speech=source != "cv")})
    return {"items": items[:MAX_ITEMS[source]], "pitch": data["pitch"].strip()}


# 1b. The same text to the plain facts a CV is built from
def _named_in(name: str, words: set) -> bool:
    """Whether a name the model returned is really in the text: at least half of its words are.
    The check behind the prompt's "never invent an employer"."""
    parts = [w for w in _words(name) if len(w) >= 3] or _words(name)
    return bool(parts) and sum(w in words for w in parts) / len(parts) >= MIN_NAME_SHARE


def _period(start, end) -> dict:
    """Start and end months from what the model gave. An end before the start is dropped."""
    first, last = month(start), month(end)
    return {"start_month": first, "end_month": None if first and last and last < first else last}


def extract_facts(text: str, profile: dict, source: str = "cv") -> dict:
    """Jobs, courses, skills and spoken languages the text states, in the shape of the tables they
    are saved to. Everything the model returns is checked: a name must be in the text, a date must
    be a real month, and nothing is listed twice. Finding nothing is not an error."""
    system = (
        "List the plain CV facts stated in a candidate's CV, notes or spoken background: jobs, courses, skills and spoken languages. "
        "Use only what the text states; never add an employer, course, date or grade it does not contain. "
        "Text taken from a CV file can arrive out of order, with a side column mixed into the main one: read it as a whole. "
        "work_history lists each job, internship or placement. Volunteering, societies and personal projects are not jobs. "
        "education lists each course, including the one the candidate is on now. "
        "Dates are YYYY-MM. If the text gives only a year, or you are unsure of the month, leave the date empty: never guess a month. "
        "end is the word present for a job the candidate still does. "
        "location is the town or city. employer_context is one plain line on what the employer does, only if the text says so "
        "or the company is widely known; otherwise leave it empty. "
        "qualification is the award (MSc, BTech, A levels) and subject is what it is in. grade is the result as written (2:1, Merit, CGPA 8.4/10), or empty. "
        "skills are the tools, methods and technologies the text names, each a word or short phrase. "
        f"languages are spoken languages. level is one of {', '.join(LANGUAGE_LEVELS)}, or empty if the text does not say."
    )
    user = (
        f"Candidate: {_who(profile)}.\n{TEXT_NAME[source]}:\n{text}\n\n"
        'Return {"work_history":[{"employer":str,"job_title":str,"location":str,"country":str,"start":str,"end":str,"employer_context":str}],'
        '"education":[{"institution":str,"qualification":str,"subject":str,"start":str,"end":str,"grade":str,"country":str}],'
        '"skills":[str],"languages":[{"language":str,"level":str}]}'
    )
    template = {"work_history": [{"employer": "", "job_title": "", "location": "", "country": "", "start": "", "end": "", "employer_context": ""}],
                "education": [{"institution": "", "qualification": "", "subject": "", "start": "", "end": "", "grade": "", "country": ""}],
                "skills": [""], "languages": [{"language": "", "level": ""}]}
    data = _run("cv facts", system, user, template, 2200)
    words, seen = set(_words(text)), set()

    def fresh(*key) -> bool:
        if key in seen:
            return False
        seen.add(key)
        return True

    jobs = []
    for w in data["work_history"]:
        employer, current = w["employer"].strip()[:160], w["end"].strip().lower() in STILL_THERE
        period = _period(w["start"], "" if current else w["end"])
        if _named_in(employer, words) and fresh("job", _key(employer), _key(w["job_title"]), period["start_month"]):
            jobs.append({"employer": employer, "job_title": w["job_title"].strip()[:160], "location": w["location"].strip()[:120],
                         "country": w["country"].strip()[:80], **period, "is_current": current,
                         "employer_context": w["employer_context"].strip()[:300]})
    courses = []
    for e in data["education"]:
        institution = e["institution"].strip()[:160]
        if _named_in(institution, words) and fresh("course", _key(institution), _key(f"{e['qualification']} {e['subject']}")):
            courses.append({"institution": institution, "qualification": e["qualification"].strip()[:120], "subject": e["subject"].strip()[:160],
                            **_period(e["start"], e["end"]), "grade": e["grade"].strip()[:80], "country": e["country"].strip()[:80]})
    skills = [x.strip() for x in data["skills"]
              if 0 < len(x.strip()) <= MAX_SKILL_CHARS and _named_in(x, words) and fresh("skill", x.strip().lower())]
    languages = []
    for item in data["languages"]:
        name, given = item["language"].strip()[:40], item["level"].lower()
        if _named_in(name, words) and fresh("language", name.lower()):
            languages.append({"language": name, "level": next((level for level, hints in _LEVEL_WORDS if any(h in given for h in hints)), "")})
    return {"work_history": jobs, "education": courses, "skills": skills[:MAX_SKILLS], "languages": languages}


# 2. Achievements to role families
def suggest_families(achievements: list, profile: dict) -> dict:
    system = (
        "Propose role families for this candidate in the UK market. Mix: 2 direct fits, 1 or 2 near fits (about 70% overlap), "
        "1 stretch. For each give typical UK job titles and one sentence on why, tied to their achievements. "
        "For each family list 4 to 6 things UK employers expect, and for each name the candidate's achievement title "
        "that shows it, or an empty string if it is a gap."
    )
    user = (
        f"Candidate: {_who(profile)}\n"
        f"Achievements: {_j([{k: a.get(k) for k in ('title', 'uk_version', 'skills')} for a in achievements])}\n\n"
        'Return {"families":[{"name":str,"fit":"direct"|"near"|"stretch","overlap":int (0-100),"uk_titles":[str],'
        '"why":str,"needs":[{"need":str,"shown_by":str (an achievement title, or "")}]}]}'
    )
    template = {"families": [{"name": "", "fit": "", "overlap": 0, "uk_titles": [""], "why": "", "needs": [{"need": "", "shown_by": ""}]}]}
    data = _run("families", system, user, template, 2200, required=("families",))
    families, seen = [], set()
    for f in data["families"]:
        name = f["name"].strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        fit = next((x for x in FITS if x in f["fit"].lower()), "near")
        needs = [{"need": n["need"].strip(), "shown_by": "" if n["shown_by"].strip().lower() in NOT_SHOWN else n["shown_by"].strip()}
                 for n in f["needs"] if n["need"].strip()]
        families.append({"name": name, "fit": fit, "overlap": max(0, min(100, f["overlap"])),
                         "uk_titles": f["uk_titles"], "why": f["why"], "needs": needs})
    if not families:
        raise AIError("families")
    return {"families": families}


# 3. A pasted job description to a short summary
def summarise_job(title: str, company: str, description: str, family_names: list) -> dict:
    system = (
        "Summarise a UK job description for a candidate deciding whether to apply. The summary is about 60 words: "
        "what the role does and what it asks for. keywords are the 5 to 8 skills or tools the description stresses. "
        "family is the one role family from the list that this job belongs to, copied exactly, or an empty string if none fits."
    )
    user = (
        f"Job title: {title}\nCompany: {company}\nRole families: {_j(family_names)}\n"
        f"Job description:\n{description[:6000]}\n\n"
        'Return {"summary":str,"keywords":[str],"family":str}'
    )
    data = _run("job", system, user, {"summary": "", "keywords": [""], "family": ""}, 700, required=("summary",))
    known = {n.strip().lower(): n for n in family_names}
    return {"summary": data["summary"].strip(), "keywords": data["keywords"], "family": known.get(data["family"].strip().lower(), "")}


# 4. A full CV. The model writes what is a matter of wording: the profile paragraph, which
#    achievements to use and how each is put, and how the skills are sorted. Every fact on the CV
#    (employers, titles, dates, courses, grades, contact details) is copied from the stored records
#    by cv.assemble, and the model is never sent the candidate's name or contact details.
CV_BULLETS = 14     # about what two A4 pages hold beside the facts
ADVERT_TEXT = 6000  # characters of a job description sent
MAX_KEYWORDS, MAX_KEYWORD_CHARS, MAX_KEYWORD_WORDS, MAX_GAPS = 12, 40, 3, 5
# words an advert is full of that say nothing a CV could be searched for
FILLER = {"experience", "experienced", "desirable", "essential", "required", "requirements", "skills", "skill", "ability", "abilities",
          "strong", "good", "excellent", "team", "role", "join", "build", "write", "explain", "work", "working", "knowledge", "candidate",
          "opportunity", "responsibilities", "benefits"}
SKILL_GROUPS = ("technical", "tools")
LETTER_PARTS = ("why_them", "why_you", "what_you_deliver")


def _year_month(value) -> str:
    day = cv.as_date(value)
    return f"{day.year}-{day.month:02d}" if day else ""


def _length(job: dict, today: date) -> str:
    """How long a job lasted, in words, so the model never works a figure out for itself."""
    years, months = divmod(cv.months_worked([job], today), 12)
    parts = (f"{years} year{'' if years == 1 else 's'}" if years else "", f"{months} month{'' if months == 1 else 's'}" if months else "")
    return " ".join(p for p in parts if p)


def _candidate(profile: dict, education: list, work_history: list, today: date) -> dict:
    """What the model may know about the person: their course, their courses and their jobs. Not who they are."""
    return {
        "current_course": " at ".join(x for x in (profile.get("course"), profile.get("university")) if x),
        "graduation": _year_month(profile.get("graduation_date")),
        "education": [{"qualification": " ".join(x for x in (c.get("qualification"), c.get("subject")) if x), "institution": c.get("institution"),
                       "finished": _year_month(c.get("end_month")), "grade": c.get("grade") or ""} for c in education],
        "jobs": [{"job_title": j.get("job_title") or "", "employer": j.get("employer"), "country": j.get("country") or "",
                  "from": _year_month(j.get("start_month")), "to": "present" if j.get("is_current") else _year_month(j.get("end_month")),
                  "length": _length(j, today)} for j in work_history],
    }


def _where(achievement: dict, jobs: dict, courses: dict) -> str:
    """Where an achievement happened, as the model is told it."""
    job, course = jobs.get(str(achievement.get("work_history_id"))), courses.get(str(achievement.get("education_id")))
    if job:
        return f"job: {job.get('job_title') or 'role'} at {job.get('employer')}"
    return f"project on the course at {course.get('institution')}" if course else "project"


def _listed(achievements: list, education: list, work_history: list) -> list[dict]:
    jobs, courses = {str(j["id"]): j for j in work_history}, {str(c["id"]): c for c in education}
    return [{"id": str(a["id"]), "where": _where(a, jobs, courses), "bullet": a.get("uk_version") or "", "outcome": a.get("outcome") or "",
             "scale": a.get("scale") or "", "skills": a.get("skills") or []} for a in achievements]


def _advert(job: dict) -> str:
    return f"Job title: {job['title']}\nCompany: {job['company']}\nJob description:\n{(job.get('description') or '')[:ADVERT_TEXT]}\n\n"


HEDGES = ("about", "around", "roughly", "approximately", "approx", "nearly", "almost", "circa", "estimated", "up to")


def _hedged(text: str) -> bool:
    """Whether the text qualifies a figure: "about 8%", "up to 5 hours"."""
    words = f" {' '.join(_words(text))} "
    return any(f" {hedge} " in words for hedge in HEDGES)


def _faithful(wording: str, achievement: dict) -> bool:
    """Whether a reworded bullet kept the achievement's figures as the user gave them: every number
    of the stored bullet, none the achievement does not hold, and still "about" if it was "about"."""
    stored = achievement.get("uk_version") or ""
    held = _numbers(_j({k: achievement.get(k) for k in ("title", "raw", "uk_version", "outcome", "scale", "context_note")}), spelled=True)
    return _numbers(stored) <= _numbers(wording) <= held and (_hedged(wording) or not _hedged(stored))


def build_cv(profile: dict, education: list, work_history: list, achievements: list, skills: list, job: dict | None = None,
             today: date | None = None, avoid=()) -> dict:
    """The wording of a CV: {"profile", "bullets": [{"achievement_id", "text"}], "skills": {"technical", "tools"}}.
    A bullet is kept only for one of the user's achievements, once, and only reworded if it kept
    that achievement's numbers; otherwise the stored bullet stands. A skill is kept only if it is
    one of `skills`. A profile paragraph holding a number the candidate's facts do not is refused.
    `avoid` names things the job asks for that the candidate's facts do not show, when a first
    attempt claimed one of them."""
    today = today or date.today()
    aim = "this job" if job else "the candidate's field"
    system = (
        f"Write the parts of a UK CV that are a matter of wording, {'tailored to one job' if job else 'for any job in the field the candidate works in'}. "
        "The candidate's employers, job titles, dates, courses and grades are printed on the CV from their own records: do not restate or change them. "
        "Use only the facts given. Never add an employer, a date, a qualification, a skill, a tool or a number that is not in the input. "
        "profile is a personal profile of three to four lines, 50 to 70 words, written without 'I': who they are, their strongest evidence, "
        f"and what they are looking for{', in the words of the job description' if job else ''}. "
        "It may claim only what the candidate's facts show: where a job asks for a skill or experience they do not show, "
        "leave it out rather than say or imply they have it. "
        f"bullets are the achievements that best fit {aim}, the most relevant first, each reworded as one CV bullet: an action verb first, "
        "then what was done and its result. Give each bullet the id of the achievement it came from and use an achievement at most once. "
        "Keep every number exactly as the achievement writes it. Do not strengthen a claim: keep a hedge such as 'about' or 'roughly' "
        "where the achievement has one, and add no result, tool or detail the achievement does not state. "
        f"Within that, do reword: lead with what matters most to {aim}{', use its own words where they mean the same thing' if job else ''}, "
        "and cut what does not matter. "
        f"The CV must fit two A4 pages: at most five bullets for one job, one for each project, and about {CV_BULLETS} in all. "
        "skills sorts the candidate's own skills into technical (methods, programming languages, subject knowledge) and tools (software and platforms), "
        "the most relevant first. Use only skills from their list, spelled as they are, and leave out any that do not matter here."
        + (f" The job asks for these, and nothing in the candidate's facts shows them: {', '.join(avoid)}. "
           "Do not say or imply the candidate has them." if avoid else "")
    )
    facts = (f"Candidate: {_j(_candidate(profile, education, work_history, today))}\n"
             f"The candidate's own skills: {_j(list(skills))}\n"
             f"Achievements: {_j(_listed(achievements, education, work_history))}\n\n")
    user = ((_advert(job) if job else "") + facts
            + 'Return {"profile":str,"bullets":[{"achievement_id":str,"text":str}],"skills":{"technical":[str],"tools":[str]}}')
    template = {"profile": "", "bullets": [{"achievement_id": "", "text": ""}], "skills": {"technical": [""], "tools": [""]}}
    known = _numbers(facts, spelled=True)  # the advert's numbers are not the candidate's: "3 years' experience" asked for is not held
    data = _run("cv", system, user, template, 2200, required=("profile", "bullets"), check=lambda d: _numbers(d["profile"]) <= known)
    own, bullets, used = {str(a["id"]): a for a in achievements}, [], set()
    for item in data["bullets"]:
        achievement, wording = own.get(item["achievement_id"].strip()), item["text"].strip()
        if not achievement or str(achievement["id"]) in used:
            continue
        used.add(str(achievement["id"]))
        kept = wording if wording and _faithful(wording, achievement) else (achievement.get("uk_version") or "").strip()
        if kept:
            bullets.append({"achievement_id": str(achievement["id"]), "text": kept})
    if not bullets:
        raise AIError("cv")
    spelling, listed, taken = {s.lower(): s for s in reversed(list(skills))}, {}, set()
    for group in SKILL_GROUPS:
        listed[group] = []
        for skill in data["skills"][group]:
            name = spelling.get(skill.strip().lower())
            if name and name.lower() not in taken:
                taken.add(name.lower())
                listed[group].append(name)
    return {"profile": data["profile"].strip(), "bullets": bullets, "skills": listed}


# 4b. For one job: its main terms, the gaps to be ready for, and the body of a cover letter
def job_letter(job: dict, profile: dict, education: list, work_history: list, achievements: list) -> dict:
    """{"keywords", "gaps", "cover_letter": {"why_them", "why_you", "what_you_deliver"}}. A keyword is
    kept only if the advert says it. All three paragraphs are required, and a letter holding a
    number that is in neither the candidate's facts nor the job's title is refused."""
    system = (
        "Read one UK job advert beside one candidate's achievements and return three things. "
        f"keywords are up to {MAX_KEYWORDS} skills, tools, methods and qualifications the advert stresses most: the nouns and short noun phrases "
        "a recruiter would search a CV for, such as 'SQL', 'Power BI' or 'stakeholder management'. Copy each from the advert in the advert's "
        "own words, one to three words long, the most important first. Give fewer rather than pad: no verbs, no benefits, and no general "
        "words such as 'experience', 'skills' or 'desirable'. "
        "gaps are up to four honest gaps between what the advert asks for and what the achievements show, each one sentence addressed "
        "to the candidate as 'you', that they should be ready to talk about. "
        "cover_letter is the body of a UK cover letter in three short paragraphs, under 220 words in all, in the first person: "
        "why_them (why this company and this role, specific to the advert), why_you (two pieces of evidence from the achievements, each number "
        "as the achievement writes it, with a hedge such as 'about' where it has one), "
        "what_you_deliver (what they will do in their first months). No greeting, sign-off, date or address: those are added. "
        "Use only the facts given. Never add an employer, a skill or a number that is not in the input."
    )
    studying = " at ".join(x for x in (profile.get("course"), profile.get("university")) if x)
    facts = f"Candidate: {studying}\nAchievements: {_j([{k: a[k] for k in ('where', 'bullet', 'outcome', 'skills')} for a in _listed(achievements, education, work_history)])}\n\n"
    user = (_advert(job) + facts
            + 'Return {"keywords":[str],"gaps":[str],"cover_letter":{"why_them":str,"why_you":str,"what_you_deliver":str}}')
    template = {"keywords": [""], "gaps": [""], "cover_letter": dict.fromkeys(LETTER_PARTS, "")}
    known = _numbers(f"{job['title']} {job['company']} {facts}", spelled=True)

    def whole(d: dict) -> bool:
        letter = d["cover_letter"]
        return all(letter[k].strip() for k in LETTER_PARTS) and _numbers(" ".join(letter[k] for k in LETTER_PARTS)) <= known

    data = _run("cover letter", system, user, template, 1400, check=whole)
    advert, keywords, seen = f"{job['title']}\n{job.get('description') or ''}", [], set()
    for term in data["keywords"]:
        term = term.strip().strip(".,;:")
        short = 0 < len(term) <= MAX_KEYWORD_CHARS and len(term.split()) <= MAX_KEYWORD_WORDS  # a longer phrase is never found word for word in a CV
        if short and term.lower() not in seen | FILLER and cv.has_term(term, advert):
            seen.add(term.lower())
            keywords.append(term)
    return {"keywords": keywords[:MAX_KEYWORDS], "gaps": [g.strip() for g in data["gaps"] if g.strip()][:MAX_GAPS],
            "cover_letter": {k: data["cover_letter"][k].strip() for k in LETTER_PARTS}}


# 5. One achievement to a STAR story
STORY_KEYS = ("title", "competency", "situation", "task", "action", "result", "strength", "tip")
# The common UK competencies a story can show, as stored and as shown
COMPETENCIES = {"teamwork": "Teamwork", "leadership": "Leadership", "problem_solving": "Problem solving",
                "communication": "Communication", "setback": "Handling a setback", "initiative": "Initiative",
                "influencing": "Influencing", "deadlines": "Working to deadlines"}
MAX_COMPETENCIES = 3
_COMPETENCY_KEYS = {k: k for k in COMPETENCIES} | {label.lower(): k for k, label in COMPETENCIES.items()}
COMPETENCY_LIST = ", ".join(COMPETENCIES.values())


def _competencies(value) -> list[str]:
    """Competencies the model named, as stored keys: known ones only, no repeats, at most three."""
    found = []
    for item in value if isinstance(value, list) else []:
        key = _COMPETENCY_KEYS.get(" ".join(str(item).lower().replace("_", " ").split())) or _COMPETENCY_KEYS.get(str(item).strip().lower())
        if key and key not in found:
            found.append(key)
    return found[:MAX_COMPETENCIES]


def _story(data: dict, achievement: dict) -> dict:
    """A story as the model wrote it, with a title, a strength and competencies the UI knows."""
    strength = data["strength"].strip().lower()
    return {k: data[k] for k in STORY_KEYS} | {
        "title": data["title"].strip() or achievement.get("title", ""),
        "strength": strength if strength in STRENGTHS else "needs detail",
        # with none named, the story's own label counts when it is exactly one of the eight
        "competencies": _competencies(data.get("competencies")) or _competencies([data["competency"]]),
    }


def star(achievement: dict) -> dict:
    system = (
        "Turn one achievement into a STAR interview story a UK interviewer will score well. "
        "Situation and task one sentence each, action 2 to 3 sentences in first person with what 'I' did, result with the number. "
        "If a number is missing, keep it out and say so in tip."
    )
    user = (
        f"Achievement: {_j({k: achievement.get(k) for k in ('title', 'raw', 'uk_version', 'skills', 'outcome', 'scale')})}\n\n"
        'Return {"title":str,"competency":str (e.g. Influencing, Problem solving),"situation":str,"task":str,'
        '"action":str,"result":str,"strength":"strong"|"needs a number"|"needs detail","tip":str,'
        f'"competencies":[str] (one to three of: {COMPETENCY_LIST}; the ones this story shows)}}'
    )
    data = _run("star", system, user, dict.fromkeys(STORY_KEYS, "") | {"competencies": [""]}, 900, required=("situation", "action"))
    return _story(data, achievement)


# 6. Mock interview transcript to feedback
def interview_feedback(transcript: str, job: dict | None, profile: dict, interview_type: str) -> dict:
    system = (
        "You are a UK hiring manager and interview coach. Score the candidate's answers in a mock interview transcript. "
        "Judge STAR structure, clarity, use of evidence (numbers, own contribution) and UK tone "
        "(confident but understated, no overselling, 'I' for own part). Quote short phrases from the transcript in notes. "
        "If the transcript is very short, say so and score only what is there."
    )
    role = f"Role: {job['title']} at {job['company']}" if job else "Role: general practice, no specific job"
    user = (
        f"Session type: {interview_type}\n{role}\nCandidate: {profile.get('full_name', '')}\nTranscript:\n{transcript}\n\n"
        'Return {"scores":{"structure":int 1-5,"clarity":int 1-5,"evidence":int 1-5,"uk_tone":int 1-5},'
        '"summary":str (2 sentences),'
        '"strengths":[{"point":str,"you_said":str (the exact words of the candidate this is about, copied from the transcript, under 20 words)}],'
        '"fixes":[{"point":str (concrete),"you_said":str}] (max 3),'
        '"rewrite":{"question":str,"better_answer":str (a stronger STAR answer under 120 words, using only facts from the transcript)},'
        '"uk_tone_notes":[str]}'
    )
    point = {"point": "", "you_said": ""}
    template = {"scores": {"structure": 0, "clarity": 0, "evidence": 0, "uk_tone": 0}, "summary": "", "strengths": [point],
                "fixes": [point], "rewrite": {"question": "", "better_answer": ""}, "uk_tone_notes": [""]}

    def checked(points: list) -> list:
        # each comment keeps a quote only if the candidate really said it
        return [{"point": p["point"].strip(), "you_said": verbatim(p["you_said"], transcript)} for p in points if p["point"].strip()]

    data = _run("interview", system, user, template, 1600, required=("summary", "fixes"))
    fixes = checked(data["fixes"])
    if not fixes:
        raise AIError("interview")
    scores = {k: max(0, min(5, data["scores"][k])) for k in template["scores"]}
    return {k: data[k] for k in template} | {"scores": scores, "strengths": checked(data["strengths"]), "fixes": fixes}


# 7. UK tone decoder
def tone(text: str, mode: str) -> dict:
    if mode == "decode":
        system = "Explain what a British workplace or interview phrase really means to an international candidate, and how to respond."
        user = f'Phrase: "{text}"\n\nReturn {{"meaning":str,"how_to_respond":str,"warmth":"positive"|"neutral"|"negative"}}'
        return _run("tone", system, user, {"meaning": "", "how_to_respond": "", "warmth": ""}, 600, required=("meaning",))
    system = ("Rewrite the candidate's sentence in a UK professional tone: confident but understated, no overselling, "
              "polite without being overly formal. Keep their facts.")
    user = f'Sentence: "{text}"\n\nReturn {{"rewrite":str,"changes":[str] (what changed and why, max 3)}}'
    return _run("tone", system, user, {"rewrite": "", "changes": [""]}, 600, required=("rewrite",))


# 8. Tracker findings to one coaching note
def explain_diagnosis(findings: list, stats: dict, profile: dict) -> dict:
    system = (
        "You are a UK careers coach reviewing a candidate's application tracker. Using only the stats and findings given, "
        "write a short weekly review: what is working, the single biggest problem, and ONE specific change for the next "
        "batch of applications, plus what signal would show it worked. If there is too little data to judge, say so plainly."
    )
    user = (
        f"Candidate: {_who(profile)}, visa ends {profile.get('visa_end_date') or 'unknown'}\n"
        f"Funnel: {_j(stats['funnel'])}\nBy role family: {_j(stats['by_family'])}\nBy source: {_j(stats['by_source'])}\n"
        f"Timing: {_j(stats['timing'])}\nRule-based findings: {_j(findings)}\n\n"
        'Return {"headline":str (one sentence stating the main finding, not a title),"working":str,"problem":str,"one_change":str,"signal":str}'
    )
    template = {"headline": "", "working": "", "problem": "", "one_change": "", "signal": ""}
    return _run("diagnosis", system, user, template, 900, required=("headline", "one_change"))


# 8b. What one rejection may teach
ENDED_LABEL = {"cv": "at the CV stage", "screening": "after a phone screen", "interview": "after an interview",
               "final": "after a final interview"}
LESSON_PAGES = ("resume", "interview", "profile")
POSSIBLE = {"may", "might", "could", "possibly", "probably", "perhaps", "likely", "seems", "seem", "suggest", "suggests"}
# What the employer said, claimed when the user entered no feedback
CLAIMED_FEEDBACK = re.compile(r"\b(they|the employer|the recruiter|the interviewer|the panel|the hiring manager)\s+"
                              r"(said|told|mentioned|noted|felt|wrote)\b|\byou were told\b|\baccording to (them|the employer)\b", re.I)
ADVERT_WORDS = re.compile(r"\b(advert|advertisement|job description|job posting|listing)\b", re.I)
THIRD_PERSON = re.compile(r"\bthe candidate\b", re.I)
# a phrase in double quotes, straight or curly
DOUBLE_QUOTED = re.compile(r"[\"“”]([^\"“”]{3,})[\"“”]")
# a phrase in single quotes, curly or straight. A straight one opens only where no letter comes before it
# and closes only where none follows, so "you're" and "employer's" are not quotes
SINGLE_QUOTED = re.compile(r"‘([^‘’]{3,})’|(?<![\w'])'([^'\n]{3,}?)'(?![\w'])")


def _lesson_page(value, ended_at: str) -> str:
    text = str(value).lower()
    for page in LESSON_PAGES:
        if page in text:
            return page
    if re.search(r"\bcv\b", text):
        return "resume"
    return "resume" if ended_at == "cv" else "interview"


def rejection_lesson(*, job: dict | None, cv_text: str, ended_at: str, feedback: str) -> dict:
    """One rejection: why it may have happened and one change for next time, from the CV that was
    sent, the job description, where it ended and any feedback. The reason is worded as a
    possibility; feedback the user did not enter is never claimed, and a quote must come from the inputs."""
    system = (
        "You are a UK careers coach helping a candidate learn from one rejection. Compare the CV they sent with the job "
        "description, given where the process ended and any feedback, and suggest the single most useful change for next time. "
        "Nobody can know why they were rejected, so word the likely reason as a possibility (may, might, could), never as a fact. "
        "Never invent feedback: if none was given, do not say what the employer said or thought. Quote only words that appear "
        "in the inputs. If no job description was recorded, do not describe what the advert asked for; if no CV was recorded, "
        "you cannot know what it said, so say only what it may not have shown. Write to the candidate as 'you'."
    )
    user = (
        f"It ended {ENDED_LABEL[ended_at]}.\n"
        + (f'Feedback from the employer: "{feedback}"\n' if feedback else "No feedback was given.\n")
        + (_advert(job) if job else "No job description was recorded.\n\n")
        + (f"CV sent:\n{cv_text}\n\n" if cv_text else "No CV was recorded.\n\n")
        + 'Return {"likely_reason":str (one or two sentences, worded as a possibility),'
          '"one_change":str (one specific change for the next application, tied to this CV and job),'
          '"page":"resume"|"interview"|"profile" (resume: the CV\'s wording or tailoring; interview: answers and practice; '
          'profile: experience or evidence the candidate still needs)}'
    )
    sources = " ".join(_words(" ".join([feedback, cv_text, job["title"] if job else "", (job or {}).get("description") or ""])))

    def honest(data: dict) -> bool:
        reason, change = data["likely_reason"], data["one_change"]
        if not POSSIBLE & set(_words(reason)):
            return False
        if not feedback and (re.search(r"\bfeedback\b", reason, re.I) or CLAIMED_FEEDBACK.search(reason) or CLAIMED_FEEDBACK.search(change)):
            return False
        if job is None and ADVERT_WORDS.search(reason):
            return False
        if THIRD_PERSON.search(reason) or THIRD_PERSON.search(change):
            return False
        # in the reason any quoted phrase claims someone's words; in the change, single quotes are how the
        # model suggests new wording, so only double quotes there are taken as a quote
        quotes = (DOUBLE_QUOTED.findall(f"{reason} {change}")
                  + ["".join(groups) for groups in SINGLE_QUOTED.findall(reason)])
        return all(f" {' '.join(_words(q))} " in f" {sources} " for q in quotes)

    template = {"likely_reason": "", "one_change": "", "page": ""}
    data = _run("lesson", system, user, template, 700, required=("likely_reason", "one_change"), check=honest)
    return {"likely_reason": data["likely_reason"].strip(), "one_change": data["one_change"].strip(),
            "page": _lesson_page(data["page"], ended_at)}


# 8c. A follow-up message to copy
FOLLOW_UP_WORDS = 80  # the body; with the greeting and sign-off the message stays under 90
# "Dear Priya," or "Hello!", with or without the body on the same line; short, so it never eats a sentence
GREETING = re.compile(r"\s*(dear|hello|hi)\b[^,!.:\n]{0,40}([,!.:\n]|$)\s*", re.I)
SIGN_OFF = re.compile(r"\s*(kind regards|best regards|warm regards|regards|best wishes|many thanks|thanks|thank you|"
                      r"yours sincerely|yours faithfully|sincerely|best)\s*,?\s*$", re.I)
# a sign-off after the last sentence, with at most a name after it: "...can share. Best wishes". A closing
# sentence such as "Many thanks for considering my application." is not a sign-off and stays
TRAILING_SIGN_OFF = re.compile(r"(?<=[.!?])\s+(kind regards|best regards|warm regards|regards|best wishes|many thanks|"
                               r"yours sincerely|yours faithfully|sincerely)\b\s*,?[^.!?]{0,40}$", re.I)
PLACEHOLDER = re.compile(r"[\[\]<>{}]")


def _message_body(text: str) -> str:
    """The body of a message the model framed itself: its greeting and sign-off are dropped,
    since code adds the user's own."""
    match = GREETING.match(text)
    lines = text[match.end() if match else 0:].strip().splitlines()
    for i, line in enumerate(lines):
        if SIGN_OFF.fullmatch(line):
            lines = lines[:i]
            break
    return TRAILING_SIGN_OFF.sub("", "\n".join(lines).strip()).strip()


def follow_up(*, role: str, company: str, applied_on: date, contact_name: str, sender: str) -> dict:
    """A short follow-up for the user to copy. Only the role, company, date applied and the
    contact's name are sent; the greeting and the user's own name are added here."""
    applied, contact = cv.long_date(applied_on), contact_name.strip()
    system = (
        "Write a short follow-up message from a candidate to an employer about an application they sent. UK tone: polite, "
        "warm and brief, with one clear ask, such as an update on the timeline, and no pressure. Use only the details given "
        "and invent nothing about the candidate or the role. Write the body only, with no greeting and no sign-off, "
        f"in at most {FOLLOW_UP_WORDS} words, and no placeholders in brackets."
    )
    user = (f"Role: {role}\nCompany: {company}\nDate applied: {applied}\n"
            f"Written to: {contact or 'the hiring manager (no name known)'}\n\n"
            'Return {"subject":str (a short email subject line),"body":str}')
    allowed = _numbers(f"{applied} {role} {company}")

    def usable(data: dict) -> bool:
        body = _message_body(data["body"])
        return (bool(body) and not body[0].islower() and len(body.split()) <= FOLLOW_UP_WORDS  # lower case: it starts mid-sentence
                and not PLACEHOLDER.search(body + data["subject"])
                and _numbers(body + " " + data["subject"]) <= allowed)

    data = _run("follow up", system, user, {"subject": "", "body": ""}, 500, required=("subject", "body"), check=usable)
    return {"subject": data["subject"].strip(),
            "message": f"Dear {contact or 'Hiring Manager'},\n\n{_message_body(data['body'])}\n\nKind regards,\n{sender}"}


# 9. Job adverts against the candidate's achievements
MAX_REQUIREMENTS = 6
ADVERT_CHARS = 2500


def score_jobs(batch: list, achievements: list) -> dict:
    """What each advert asks for and which of the candidate's achievements shows it, keyed by
    the advert's number: {n: [{"need", "shown_by"}]}. An advert the model left out is simply
    absent. Only the achievements are sent, nothing else about the person."""
    system = (
        "Compare job adverts with a candidate's achievements. For every numbered advert, list the 4 to 6 main things it asks for: "
        "skills, tools, experience or qualifications. Leave out benefits, the company description and generic wishes such as 'team player'. "
        "List them for every advert, including ones the candidate plainly does not fit. "
        "For each one, shown_by is the title of the achievement that gives real evidence of it, copied exactly from the list: "
        "the same skill or tool, or the same kind of work, even if the advert words it differently. "
        "If no achievement gives real evidence, shown_by is an empty string. Do not credit a loosely related topic."
    )
    adverts = [{"n": b["n"], "title": b["title"], "employer": b["employer"], "advert": (b.get("description") or "")[:ADVERT_CHARS]} for b in batch]
    user = (
        f"Achievements: {_j([{k: a.get(k) for k in ('title', 'uk_version', 'skills')} for a in achievements])}\n\n"
        f"Adverts: {_j(adverts)}\n\n"
        'Return {"jobs":[{"n":int (the advert number),"requirements":[{"need":str (under 12 words),"shown_by":str (an achievement title, or "")}]}]}'
    )
    template = {"jobs": [{"n": 0, "requirements": [{"need": "", "shown_by": ""}]}]}
    data = _run("job fit", system, user, template, 400 + 320 * len(batch), required=("jobs",))
    sent, scored = {b["n"] for b in batch}, {}
    for job in data["jobs"]:
        if job["n"] not in sent or job["n"] in scored:
            continue
        requirements = [{"need": r["need"].strip(), "shown_by": "" if r["shown_by"].strip().lower() in NOT_SHOWN else r["shown_by"].strip()}
                        for r in job["requirements"] if r["need"].strip()]
        scored[job["n"]] = requirements[:MAX_REQUIREMENTS]
    if not scored:
        raise AIError("job fit")
    return scored


# 10. Public GitHub repositories to project achievements
def github_achievements(repos: list) -> dict:
    """One project achievement for each repository the model could describe, keyed by the
    repository's number: {n: item}. Each comes only from that repository's name, description,
    main language and README, and its quote is kept only if those really contain it."""
    system = (
        "Turn a candidate's own public code repositories into project achievements written for UK employers. "
        "One item per repository, from its name, description, main language and README only: never add a feature, tool, user or number they do not state. "
        "uk_version is a single UK CV bullet: action verb first, what was built and with what, and a result or scale only if the README gives one. "
        "If it gives no number, do not make one up: set outcome to the words 'Add a number: ' followed by what the candidate should measure, "
        "in your own words (for example how many people use it, or how much faster it runs). "
        "raw is an exact quote copied from that repository's README or description, under 25 words. "
        "skills are the languages, libraries and tools it names. context_note is one tip on presenting a personal project to a UK employer. "
        "Leave out a repository whose README and description say too little to tell what was built."
    )
    listed = [{"n": r["n"], "name": r["name"], "description": r.get("description") or "", "main_language": r.get("language") or "",
               "readme": r.get("readme") or ""} for r in repos]
    user = (
        f"Repositories: {_j(listed)}\n\n"
        'Return {"items":[{"n":int (the repository number),"title":str,"raw":str,"uk_version":str,"skills":[str],'
        '"outcome":str,"scale":str,"context_note":str}]}'
    )
    template = {"items": [{"n": 0, "title": "", "raw": "", "uk_version": "", "skills": [""], "outcome": "", "scale": "", "context_note": ""}]}
    data = _run("github", system, user, template, 400 + 380 * len(repos), required=("items",))
    sent, found = {r["n"]: r for r in repos}, {}
    for item in data["items"]:
        repo, bullet = sent.get(item["n"]), item["uk_version"].strip()
        if not repo or item["n"] in found or not bullet:
            continue
        own_words = f"{repo.get('description') or ''}\n{repo.get('readme') or ''}"
        found[item["n"]] = {"title": item["title"].strip() or repo["name"], "raw": verbatim(item["raw"], own_words, speech=False),
                            "uk_version": bullet, "skills": item["skills"], "outcome": _outcome(item["outcome"]),
                            "scale": item["scale"].strip(), "context_note": item["context_note"].strip()}
    if not found:
        raise AIError("github")
    return found


# 11. One achievement rewritten from its own facts and a note from the user
NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
                "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40",
                "fifty": "50", "hundred": "100", "thousand": "1000", "million": "1000000"}


def _numbers(text: str, spelled: bool = False) -> set:
    """Every figure in the text, with thousands separators removed. With spelled, numbers written
    as words count as their digits too."""
    found = {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}
    return found | {NUMBER_WORDS[w] for w in _words(text) if w in NUMBER_WORDS} if spelled else found


def improve(achievement: dict, note: str) -> dict:
    """A better bullet, result and scale for one achievement, from what it already holds and the
    user's note. A rewrite carrying a number found in neither is not accepted: on a CV an invented
    figure is the invention that does most harm."""
    system = (
        "Rewrite one CV achievement for a UK employer, using only the facts it already holds and the candidate's note. "
        "uk_version is a single CV bullet: action verb first, result with a number, scale. "
        "Never add a fact, tool, employer or number that is in neither the achievement nor the note. "
        "If there is still no number, leave numbers out and set outcome to 'Add a number: <what to measure>'. "
        "outcome is the result in a few words. scale is who or how much was affected, or an empty string."
    )
    facts = {k: achievement.get(k) for k in ("title", "raw", "uk_version", "skills", "outcome", "scale", "context_note")}
    user = (f"Achievement: {_j(facts)}\nCandidate's note: {note.strip() or '(none)'}\n\n"
            'Return {"uk_version":str,"outcome":str,"scale":str}')
    allowed = _numbers(f"{_j(facts)} {note}", spelled=True)
    data = _run("improve", system, user, {"uk_version": "", "outcome": "", "scale": ""}, 500, required=("uk_version",),
                check=lambda d: _numbers(f"{d['uk_version']} {d['outcome']} {d['scale']}") <= allowed)
    return {"uk_version": data["uk_version"].strip(), "outcome": _outcome(data["outcome"]), "scale": data["scale"].strip()}


# 12. Several achievements to STAR stories in one call
def story_bank(achievements: list, taken=()) -> dict:
    """A STAR story for each numbered achievement sent, keyed by its number: {n: story}. `taken`
    lists competencies the user's stories already cover, so new ones spread out where the facts allow."""
    system = (
        "Turn each numbered achievement into a STAR interview story a UK interviewer will score well. One story per achievement, "
        "using only the facts in that achievement. "
        "Situation and task one sentence each, action 2 to 3 sentences in first person with what 'I' did, result with the number. "
        "If a number is missing, keep it out and say so in tip. "
        "competency is what the story shows best, for example Problem solving, Teamwork, Influencing, Initiative, Delivering results, "
        "Communication, Leadership or Adaptability. Use a different competency for each story where the facts allow"
        + (f", and prefer ones not already covered: {', '.join(taken)}." if taken else ".")
    )
    listed = [{"n": a["n"]} | {k: a.get(k) for k in ("title", "raw", "uk_version", "skills", "outcome", "scale")} for a in achievements]
    user = (
        f"Achievements: {_j(listed)}\n\n"
        'Return {"stories":[{"n":int (the achievement number),"title":str,"competency":str,"situation":str,"task":str,'
        '"action":str,"result":str,"strength":"strong"|"needs a number"|"needs detail","tip":str,'
        f'"competencies":[str] (one to three of: {COMPETENCY_LIST}; the ones this story shows)}}]}}'
    )
    template = {"stories": [{"n": 0} | dict.fromkeys(STORY_KEYS, "") | {"competencies": [""]}]}
    data = _run("story bank", system, user, template, 300 + 450 * len(achievements), required=("stories",))
    sent, found = {a["n"]: a for a in achievements}, {}
    for story in data["stories"]:
        achievement = sent.get(story["n"])
        if achievement and story["n"] not in found and story["situation"].strip() and story["action"].strip():
            found[story["n"]] = _story(story, achievement)
    if not found:
        raise AIError("story bank")
    return found


# 14. Competencies for stories written before they were tagged
def tag_stories(stories: list[dict]) -> dict[str, list[str]]:
    """The competencies each story shows: {story id: [keys]}. Stories are sent by number, so ids stay
    on the server; a number that was not sent is ignored, and a story given none is left out."""
    numbered = {n: s for n, s in enumerate(stories, start=1)}
    system = (f"Say which of these UK interview competencies each STAR story shows: {COMPETENCY_LIST}. "
              "Give one to three per story, the ones its facts really show.")
    listed = [{"n": n} | {k: s.get(k, "") for k in ("title", "situation", "task", "action", "result")} for n, s in numbered.items()]
    user = f"Stories: {_j(listed)}\n\n" + 'Return {"stories":[{"n":int (the story number),"competencies":[str]}]}'

    def tagged(data: dict) -> dict:
        found = {}
        for item in data["stories"]:
            story = numbered.get(item["n"])
            keys = _competencies(item.get("competencies"))
            if story and keys and story["id"] not in found:
                found[story["id"]] = keys
        return found
    data = _run("tag stories", system, user, {"stories": [{"n": 0, "competencies": [""]}]}, 200 + 60 * len(stories),
                check=lambda d: bool(tagged(d)))
    return tagged(data)


# 13. A company brief from numbered passages the app fetched
BRIEF_SECTIONS = ("what_they_do", "size", "values", "products", "news", "competitors")
SECTION_CAP = {"what_they_do": 3, "size": 2, "values": 4, "products": 5, "news": 5, "competitors": 5}
NEWS_DAYS = 365
STATEMENT_CHARS = 300


def _long_date(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def _source(value, passages: dict) -> int | None:
    """A passage number the model wrote as 3, "3" or "[3]", if it is one that was sent."""
    if isinstance(value, bool) or value is None:
        return None
    m = re.fullmatch(r"\s*\[?\s*(\d+)(?:\.0+)?\s*\]?\s*", str(value))
    return int(m.group(1)) if m and int(m.group(1)) in passages else None


def _straight(text: str) -> str:
    return text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")


def _found_in(quote: str, text: str) -> str:
    """The words of `quote` as `text` writes them, ignoring case, spacing and curly quotes; "" if absent."""
    words = _straight(quote).strip(" \"'").split()
    if not words:
        return ""
    m = re.search(r"\s+".join(map(re.escape, words)), _straight(text), re.I)
    return text[m.start():m.end()] if m else ""


def _passage_words(p: dict) -> str:
    return f"{p['title']} {p['text']}" + (f" {_long_date(p['published_on'])} {p['published_on'].isoformat()}" if p.get("published_on") else "")


BIG_NUMBER_WORDS = {w: v for w, v in NUMBER_WORDS.items() if int(v) >= 10}  # "one" or "two" in a sentence is rarely a figure


def _figures(text: str) -> set:
    """Every figure a statement gives: in digits, or written as a word for ten or more ("forty", "thousand")."""
    return _numbers(text) | {BIG_NUMBER_WORDS[w] for w in _words(text) if w in BIG_NUMBER_WORDS}


def _brief_statement(raw: dict, passages: dict, since: date) -> dict | None:
    """One statement, if code can check it against the passage it cites; otherwise None."""
    section, text = raw["section"].strip().lower(), " ".join(raw["text"].split())
    n = _source(raw.get("source"), passages)
    if section not in BRIEF_SECTIONS or not text or len(text) > STATEMENT_CHARS or n is None:
        return None
    p = passages[n]
    if section == "news" and (p["kind"] != "news" or (p.get("published_on") and p["published_on"] < since)):
        return None
    source_text = _passage_words(p)
    if not _figures(text) <= _numbers(source_text, spelled=True):
        return None  # a figure the page does not give
    if any(not _found_in(q, source_text) for q in DOUBLE_QUOTED.findall(_straight(text))):
        return None  # words put in the company's mouth
    quote = ""
    if section == "values":
        quote = _found_in(raw["quote"], p["text"])
        if not quote:
            return None  # a value is shown in the company's own words, or not at all
    return {"section": section, "text": text, "source": n, "quote": quote}


def _brief_checked(data: dict, passages: dict, since: date) -> list[dict]:
    kept, seen, per_section = [], set(), {}
    for raw in data["statements"]:
        statement = _brief_statement(raw, passages, since)
        if not statement:
            continue
        key = _key(statement["text"])
        if key in seen or per_section.get(statement["section"], 0) >= SECTION_CAP[statement["section"]]:
            continue
        seen.add(key)
        per_section[statement["section"]] = per_section.get(statement["section"], 0) + 1
        kept.append(statement)
    return kept


def company_brief(company: str, passages: list[dict], today: date) -> list[dict]:
    """Short statements about a company, each citing the one passage that says it. Only passages
    the app fetched are sent; a statement code cannot check against its passage is dropped. A reply
    with statements of which none survive is asked for once more; a reply with none is an honest
    "nothing to say"."""
    by_n = {p["n"]: p for p in passages}
    since = today - timedelta(days=NEWS_DAYS)
    system = (
        "You write a short factual brief about one company for someone preparing for an interview there. "
        "Use only the numbered passages given. Never add anything from your own knowledge, even about a company you know. "
        "Each statement is one short sentence about the company, in the third person, and cites the one passage number that says it. "
        "Sections: what_they_do (what the company does); size (how big or how old it is); "
        "values (what it says it stands for, with the exact words from the passage in quote); products (products, services or projects); "
        "news (one news item, citing a news passage); competitors (a company the passage names as a competitor or alternative). "
        "Use no figure that is not in the passage you cite. Leave out a section no passage supports. "
        "If nothing in the passages is about this company, return no statements."
    )

    def heading(p: dict) -> str:
        return f"[{p['n']}] {p['kind']}" + (f", {_long_date(p['published_on'])}" if p.get("published_on") else "") + f": {p['title']}"
    listed = "\n\n".join(f"{heading(p)}\n{p['text']}" for p in passages)
    user = (f"Company: {company}\n\nPassages:\n{listed}\n\n"
            'Return {"statements":[{"section":str,"text":str,"source":int (the passage number),"quote":str (values only, else "")}]}')
    template = {"statements": [{"section": "", "text": "", "source": "", "quote": ""}]}
    data = _run("brief", system, user, template, 2000,
                check=lambda d: not d["statements"] or bool(_brief_checked(d, by_n, since)))
    return _brief_checked(data, by_n, since)


# 15. The prep pack: talking points, the pitch, likely questions and questions to ask
PITCH_WORDS = (110, 260)  # about a minute to 90 seconds spoken; the model writes about 120 to 140 words
MAX_TALKING_POINTS, MAX_QUESTIONS, MIN_QUESTIONS, MAX_TO_ASK, MIN_TO_ASK = 3, 8, 5, 5, 3
NO_ADVERT = "No job description was recorded for this role."


def _sentence(text: str) -> str:
    """Tidied, and starting with a capital letter."""
    text = " ".join(text.split())
    return text[:1].upper() + text[1:]


def _question_kind(value) -> str:
    """What a likely question tests: one of the eight competencies, motivation, or knowledge of the role."""
    text = " ".join(str(value).lower().replace("_", " ").split())
    return _COMPETENCY_KEYS.get(text) or ("motivation" if text == "motivation" else "role")


def prep_pack(*, job: dict, brief: list[dict], achievements: list, stories: list, profile: dict) -> dict:
    """The parts of a prep pack the model writes, checked: every talking point joins a real company
    fact to one of the user's achievements and uses only their figures; the pitch is 110 to 260
    words with no figure from outside the input; a likely question points only to one of the user's
    own stories. Achievements and stories are sent with short ids, mapped back here. Nothing that
    identifies the user is sent: no name, contact details or visa."""
    facts = {f["id"]: f for f in brief}
    mine = {f"a{n}": a for n, a in enumerate(achievements, start=1)}
    told = {f"s{n}": s for n, s in enumerate(stories, start=1)}
    advert = (job.get("description") or "").strip()
    graduating = cv.as_date(profile.get("graduation_date"))
    candidate = {"course": profile.get("course") or "", "university": profile.get("university") or "",
                 "graduating": f"{graduating:%B %Y}" if graduating else ""}
    listed = [{"id": k, "title": a.get("title", ""), "bullet": a.get("uk_version", ""), "result": a.get("outcome", ""),
               "scale": a.get("scale", ""), "skills": a.get("skills") or []} for k, a in mine.items()]
    story_list = [{"id": k, "title": s["title"], "competencies": [COMPETENCIES[c] for c in s.get("competencies") or []],
                   "result": s.get("result", "")} for k, s in told.items()]
    system = (
        "You help a graduate prepare for one interview with a UK employer. Use only the facts given. "
        "talking_points: three answers to 'Why this company?', each joining one company fact (fact_id) to one of the candidate's "
        "achievements (achievement_id, the id of the achievement the point describes), in the first person, one or two sentences, "
        "using no figure that is not in that fact or that achievement. "
        "pitch: the candidate's answer to 'Tell me about yourself' for this role, about 90 seconds spoken, in the first person, as "
        "three short paragraphs of 60 to 80 words each: their course and background; two achievements that fit this role, with their "
        "figures; why this role and this company. Use no figure that is not in the input. "
        "likely_questions: eight questions this interviewer is likely to ask, some from what the advert asks for and some standard UK "
        f"competency questions. competency is one of: {COMPETENCY_LIST}, Motivation or Role knowledge. story_id is the id of the "
        "candidate's story that best answers it, or \"\" when none fits. why is one short sentence on why it is likely, written to the candidate as 'you'. "
        "questions_to_ask: five questions the candidate could ask at the end, each drawn from a company fact (fact_id) where possible. "
        "Do not ask anything the company facts already answer; ask about the team, the work, how success is judged, or what a fact "
        "means for the role. No em dashes."
    )
    user = (
        f"Role: {job['title']} at {job['company']}\nAdvert: {advert[:ADVERT_TEXT] if advert else NO_ADVERT}\n\n"
        f"Company facts: {_j([{'id': i, 'text': f['text']} for i, f in facts.items()]) if facts else '(none found)'}\n\n"
        f"Candidate: {_j(candidate)}\nAchievements: {_j(listed)}\nStories: {_j(story_list) if story_list else '(none yet)'}\n\n"
        'Return {"talking_points":[{"text":str,"fact_id":str,"achievement_id":str}],"pitch":[str, str, str],'
        '"likely_questions":[{"question":str,"competency":str,"story_id":str,"why":str}],'
        '"questions_to_ask":[{"question":str,"fact_id":str}]}'
    )
    said = {item["id"]: _j(item) for item in listed}  # what each achievement told the model, figures included
    sent = f"{_j(candidate)} {advert} {_j(listed)} {_j(story_list)} {_j([f['text'] for f in facts.values()])}"
    allowed = _numbers(sent, spelled=True)

    def shaped(d: dict) -> dict | None:
        points, seen = [], set()
        for t in d["talking_points"]:
            text, fact, achievement = " ".join(t["text"].split()), facts.get(t["fact_id"].strip()), mine.get(t["achievement_id"].strip())
            source = f"{fact['text'] if fact else ''} {said.get(t['achievement_id'].strip(), '')}"
            if text and fact and achievement and _key(text) not in seen and _numbers(text) <= _numbers(source, spelled=True):
                seen.add(_key(text))
                points.append({"text": text, "fact_id": fact["id"], "achievement_id": achievement["id"]})
        pitch = "\n\n".join(" ".join(p.split()) for p in d["pitch"] if p.strip())  # its paragraphs, each tidied
        questions, asked = [], set()
        for q in d["likely_questions"]:
            text = " ".join(q["question"].split())
            if text and _key(text) not in asked:
                asked.add(_key(text))
                story = told.get(q["story_id"].strip())
                questions.append({"question": text, "competency": _question_kind(q["competency"]),
                                  "story_id": story["id"] if story else None, "why": _sentence(q["why"])})
        to_ask = [{"question": " ".join(q["question"].split()), "fact_id": q["fact_id"].strip() if q["fact_id"].strip() in facts else None}
                  for q in d["questions_to_ask"] if q["question"].strip()][:MAX_TO_ASK]
        if ((facts and not points) or not PITCH_WORDS[0] <= len(pitch.split()) <= PITCH_WORDS[1] or not _numbers(pitch) <= allowed
                or len(questions) < MIN_QUESTIONS or len(to_ask) < MIN_TO_ASK):
            return None
        return {"talking_points": points[:MAX_TALKING_POINTS], "pitch": pitch, "likely_questions": questions[:MAX_QUESTIONS],
                "questions_to_ask": to_ask}

    template = {"talking_points": [{"text": "", "fact_id": "", "achievement_id": ""}], "pitch": [""],
                "likely_questions": [{"question": "", "competency": "", "story_id": "", "why": ""}],
                "questions_to_ask": [{"question": "", "fact_id": ""}]}
    return shaped(_run("prep", system, user, template, 3000, check=lambda d: shaped(d) is not None))


# 14. Networking: a short message to someone the user wants to talk to, and preparation for an event
NOTE_CHARS = 200  # LinkedIn's limit on a connection note (help page, checked 14 October 2026)
DRAFT_WORDS = {"chat_request": 79, "follow_up": 60, "thank_you": 100, "referral_ask": 130, "recruiter_intro": 120, "reference_ask": 120}
DRAFT_SHAPES = {
    "connection_note": "a LinkedIn connection note: who the candidate is and the link between you, and no request of any kind",
    "chat_request": ("a request for an informational chat: who the candidate is, why this person, and one clear ask, "
                     "15 minutes for advice, never a job or a referral"),
    "follow_up": ("a friendly follow-up to the candidate's earlier message, which has had no reply for two weeks: say briefly that "
                  "you are following up, then repeat the one ask, in at most two sentences"),
    "thank_you": "a thank-you after an informational chat, mentioning the one thing the candidate learned",
    "referral_ask": ("a request for a referral for one role at their company: say which role, then two sentences on why the "
                     "candidate fits it, then ask whether they would be comfortable referring them, making it easy to say no"),
    "recruiter_intro": "an introduction to a recruiter: what the candidate does, what roles they are looking for, and when they can start",
    "reference_ask": ("a request to act as a referee for job applications. It asks only for a reference, never for a job: say which roles "
                      "the candidate is applying for, and never suggest the candidate is applying to the referee's own organisation"),
}
CONNECTION = {  # how the user knows them: the only connection a draft may claim
    "alumni": "They studied at the same university as the candidate{university}.",
    "tutor": "They taught the candidate, as a tutor or lecturer.",
    "supervisor": "They supervised the candidate at work or on a project.",
    "event": "The candidate met them at an event{event}.",
    "recruiter": "They are a recruiter. The candidate has no other connection with them.",
    "introduced": "Someone introduced the candidate to them.",
    "none": "The candidate has no connection with them yet.",
}
# What a draft may say only when the user entered that connection
CLAIMS = {
    "alumni": re.compile(r"\b(alumn\w*|both (studied|went|go|attended)|also studied|studied (there too|together)|"
                         r"fellow\b[^.?!]{0,60}\b(graduate|student)s?|same (university|course|cohort|class|programme|program|module)|"
                         r"class ?mates?|course ?mates?|you studied|we studied)\b", re.I),
    "tutor": re.compile(r"\b(you taught|taught me|your (module|modules|lecture|lectures|class|classes|seminar|seminars|course)|"
                        r"my (tutor|lecturer)|your student)\b", re.I),
    "supervisor": re.compile(r"\b(you supervised|supervised me|my supervisor|under your supervision|worked (together|with you|under you|for you)|"
                             r"(enjoyed|loved|liked|valued|miss) working (together|with you|under you|for you)|working (together|with you) on|"
                             r"my (manager|line manager)|we worked|former colleague|both worked|when we were at)\b", re.I),
    # having met, without saying where; and having met somewhere, which only someone met at an event may claim
    "event": re.compile(r"\b(we met|met you|(was|it's been|has been) (great|nice|lovely|good|a pleasure) to meet|meeting you (was|at))\b", re.I),
    "event_place": re.compile(r"\b((met|spoke|chatted|meeting|talking|speaking)\b[^.?!]{0,30}\bat (the|a|an|your|last)\b|"
                              r"to meet you at (the|a|an|your|last)\b|our (conversation|chat) at)", re.I),
    "introduced": re.compile(r"\b(introduced (me|us)|introduction (from|by|through)|mutual (friend|contact|connection|acquaintance)s?|"
                             r"recommended (that )?(i|me)|suggested (that )?(i|me)|referred me to you|passed on your|gave me your|"
                             r"pointed me)\b", re.I),
}
ALLOWED_CLAIMS = {"alumni": {"alumni"}, "tutor": {"tutor"}, "supervisor": {"supervisor"}, "event": {"event", "event_place"},
                  "introduced": {"introduced"}, "recruiter": set(), "none": set()}
# A request of any kind, which a connection note never makes
ANY_ASK = re.compile(r"\?|\b(would|could|can) you\b|\blet me know\b|\brefer me\b|\breferral\b|"
                     r"\b(i'?d|i would|i'm hoping|i am hoping)\b[^.?!]{0,40}\b(chat|call|coffee|advice|minutes|meet|catch up)\b", re.I)
JOB_ASK = re.compile(r"\b(referr\w*|refer me|vacanc\w*|job openings?|any (jobs|roles|openings|positions|vacancies)|hire me|"
                     r"a job|job offer)\b", re.I)
NOT_ASKING = re.compile(r"\b(not|never|n't)\s+(asking|looking|hoping)\s+for\b[^.?!;:]{0,60}", re.I)  # "I am not asking for a job"
FIFTEEN_MINUTES = re.compile(r"\b(15|fifteen)[- ]?min(ute)?s?\b", re.I)
FOLLOWS_UP = re.compile(r"\b(follow(ing)?[- ]up|my (earlier |last |previous |recent )?(message|note|email)|wrote to you|reached out|got in touch)\b", re.I)
DASHES = re.compile(r"\s*—\s*|\s+–\s+")  # an em dash, or an en dash used as one
VISA_WORDS = re.compile(r"\b(visas?|sponsor\w*|right to work|immigration|work permit)\b", re.I)
WEB_ADDRESS = re.compile(r"https?://|\bwww\.|\b[\w-]+\.(com|co\.uk|org|ac\.uk)\b", re.I)
# A month named in a draft must be in what was sent. Capitalised only, and never "May", which is mostly the verb
MONTH_NAMED = re.compile(r"\b(January|February|March|April|June|July|August|September|October|November|December)\b")
MONTH_GIVEN = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I)
TITLES = {"dr", "dr.", "prof", "prof.", "professor", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "miss", "mx", "sir", "dame"}
STOP_WORDS = {"the", "and", "for", "you", "your", "that", "with", "how", "was", "are", "they", "their", "this", "its", "about",
              "what", "when", "into", "from", "have", "has", "had", "can", "use", "uses", "one", "who", "why", "our", "but", "not"}
EVENT_INTRO_WORDS = (30, 90)  # about 30 seconds spoken
SHORT_WORDS = 30              # an opener or the goal


def _greeting_names(name: str) -> tuple[str, str]:
    """('Priya', 'Dr Shah') for 'Dr Priya Shah'; ('Priya', 'Priya Shah') for 'Priya Shah'; ('Dr Shah', 'Dr Shah') for
    'Dr Shah', since a title with only a surname is how the user addresses them."""
    parts = name.split()
    titled = len(parts) > 1 and parts[0].lower() in TITLES
    if titled and len(parts) == 2:
        return name.strip(), name.strip()
    first = parts[1] if titled else (parts[0] if parts else name)
    return first, f"{parts[0]} {parts[-1]}" if titled else name.strip()


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]


def _key_words(text: str) -> list[str]:
    return [w for w in dict.fromkeys(_words(text)) if len(w) >= 3 and w not in STOP_WORDS]


def _uses(learned: str, body: str) -> bool:
    """Whether the draft mentions what the user learned: at least half its key words, three at most needed."""
    wanted = _key_words(learned)
    have = set(_words(body))
    return sum(w in have for w in wanted) >= min(3, -(-len(wanted) // 2))


def _plain(text: str) -> str:
    return " ".join(text.lower().split())


CURRENTLY = re.compile(r"\b(currently|now) (work|working|employed|based)\b|\bI(?:'m|’m| am) (currently |now )?(working|employed)\b|\bI work\b", re.I)
JOINING_YOUR_TEAM = re.compile(r"\b(join|joining|contribute|contributing|apply|applying|position|vacanc\w*|role)\b[^.?!]{0,60}"
                               r"\byour (team|company|organisation|organization|department)\b|"
                               r"\byour (team|company|organisation|organization|department)\b[^.?!]{0,30}\b(position|vacanc\w*|role)\b", re.I)


def _claims_the_job(body: str, job: dict) -> bool:
    """A referral ask that says the candidate already works in the role or at the company they are applying to."""
    names = [n.lower() for n in (job.get("title") or "", job.get("company") or "") if n]
    return any(CURRENTLY.search(s) and any(n in s.lower() for n in names) for s in _sentences(body))


def _asks_the_referee_for_a_job(body: str, company: str) -> bool:
    """A reference request that says the candidate is applying to the referee's own organisation, or wants to join it."""
    applying_there = company and re.search(r"\bappl(y|ying|ied|ication)\b[^.?!,;]{0,60}\b(at|to|with)\s+" + re.escape(company), body, re.I)
    return bool(applying_there or JOINING_YOUR_TEAM.search(body))


def outreach_draft(*, kind: str, contact: dict, sender: str, about_me: str, university: str = "", event_name: str = "",
                   job: dict | None = None, achievements=(), learned: str = "", start: str = "", course_ends: str = "",
                   looking_for=()) -> dict:
    """A short message to one of the user's contacts, for them to copy and send themselves. The model
    is told the contact's role, company and how the user knows them, never their name or notes, nor
    the user's name: code adds the greeting and sign-off. The draft fits its limit or is asked for
    once more and then refused, never cut, and may claim no connection the user did not enter."""
    relationship = contact["relationship"]
    first, formal = _greeting_names(contact["name"])
    greeting = f"Dear {formal}," if kind == "reference_ask" else f"Hi {first},"
    sender_first = (sender.split() or [sender])[0]
    note_room = NOTE_CHARS - len(greeting) - len(sender_first) - 2
    connection = CONNECTION[relationship].format(university=f" ({university})" if university else "",
                                                 event=f" ({event_name})" if event_name else "")
    limit = (f"at most {note_room} characters (about {note_room // 7} words, two short sentences)" if kind == "connection_note"
             else f"under {DRAFT_WORDS[kind] + 1} words")
    system = (
        f"Write {DRAFT_SHAPES[kind]}, from an international student or graduate in the UK to someone they want to learn from. "
        "UK tone: warm, brief and specific, with no flattery and no pressure. Write the body only, with no greeting, no sign-off "
        f"and no placeholders in brackets, in {limit}. The only connection between them that you may mention is this one: "
        f"{connection} Do not claim any other shared university, employer, event, meeting or mutual contact. "
        "Use only the details given and invent nothing about the candidate. Do not mention visas or sponsorship, and do not "
        "include any web address."
    )
    details = [f"About the candidate: {about_me}", f"Their role: {contact.get('role') or 'not given'}",
               f"Their company: {contact.get('company') or 'not given'}", f"Connection: {connection}"]
    if kind == "thank_you":
        details.append(f"What the candidate learned in the chat: {learned}")
    if kind == "reference_ask":
        details.append(f"Roles the candidate is applying for: {', '.join(looking_for) or 'not given, so say graduate roles'}")
    if kind == "recruiter_intro":
        details.append(f"Roles the candidate is looking for: {', '.join(looking_for) or 'not given'}")
        details.append(f"When they can start: {start}" if start else
                       f"Their course ends: {course_ends}. Say only that, not a start date." if course_ends else "No start date given: leave it out.")
    if kind == "referral_ask" and job:
        details.append(f"The job the candidate wants a referral for (the candidate has not got it yet and does not work there): "
                       f"{job['title']} at {job['company']}. {job.get('summary') or ''}".strip())
        details += [f"Achievement: {a}" for a in achievements]
    user = "\n".join(details) + '\n\nReturn {"body":str}'
    sources = " ".join([about_me, university, event_name, learned, start, course_ends, *looking_for, *achievements,
                        contact.get("role") or "", contact.get("company") or "",
                        *([job["title"], job["company"], job.get("summary") or ""] if job else [])])
    allowed_numbers = _numbers(sources) | ({"15"} if kind in ("chat_request", "follow_up") else set())
    months = {m.lower() for m in MONTH_GIVEN.findall(sources)}
    claims = ALLOWED_CLAIMS[relationship] | ({"event"} if kind == "thank_you" else set())  # after a chat they have met, not at an event
    names = [n for n in (contact.get("company"), (job or {}).get("company"), event_name, university) if n]
    start_as_typed = _plain(DASHES.sub(", ", start))

    def body_of(data: dict) -> str:
        return DASHES.sub(", ", _message_body(data["body"]))

    def usable(data: dict) -> bool:
        body = body_of(data)
        unnamed = body
        for name in names:  # a company called "Booking.com" is a name, not a web address
            unnamed = re.sub(re.escape(name), " ", unnamed, flags=re.I)
        if not body or body[0].islower() or PLACEHOLDER.search(body) or WEB_ADDRESS.search(unnamed) or VISA_WORDS.search(body):
            return False
        if not _numbers(body) <= allowed_numbers or any(m.lower() not in months for m in MONTH_NAMED.findall(body)):
            return False
        if any(CLAIMS[c].search(body) for c in CLAIMS if c not in claims):
            return False
        if kind == "connection_note":
            return len(body) <= note_room and not ANY_ASK.search(body)
        if len(body.split()) > DRAFT_WORDS[kind]:
            return False
        if kind == "chat_request":
            return bool(FIFTEEN_MINUTES.search(body)) and not JOB_ASK.search(NOT_ASKING.sub(" ", body))
        if kind == "follow_up":
            return len(_sentences(body)) <= 2 and bool(FOLLOWS_UP.search(body))
        if kind == "thank_you":
            return _uses(learned, body)
        if kind == "referral_ask" and job and _claims_the_job(body, job):
            return False
        if kind == "reference_ask" and _asks_the_referee_for_a_job(body, contact.get("company") or ""):
            return False
        if kind == "recruiter_intro" and start:
            return start_as_typed in _plain(body)
        return True

    data = _run("outreach", system, user, {"body": ""}, 600, required=("body",), check=usable)
    body = body_of(data)
    if kind == "connection_note":
        message = f"{greeting}\n{body}\n{sender_first}"
    else:
        role = f"\n\nThe role: {job['title']}" + (f"\n{job['url']}" if job.get("url") else "") if kind == "referral_ask" and job else ""
        closing = "Kind regards" if kind == "reference_ask" else "Best wishes"
        message = f"{greeting}\n\n{body}{role}\n\n{closing},\n{sender}"
    return {"message": message, "words": len(body.split()), "characters": len(message)}


def event_prep(*, event: dict, about_me: str) -> dict:
    """For one saved event: a 30-second introduction from what the user says about themselves, three
    ways to start a conversation at that kind of event, and one small goal."""
    kind = networking.EVENT_TYPES.get(event["type"], "event")
    system = (
        "Help an international student or graduate in the UK prepare for a networking event. Write a 30-second introduction "
        f"in the first person ({EVENT_INTRO_WORDS[0]} to {EVENT_INTRO_WORDS[1]} words) from what they say about themselves, three "
        "short ways to start a conversation that suit this kind of event, and one small, specific goal for the event. Use only "
        "the details given and invent no achievements, employers or numbers. Do not mention visas or sponsorship."
    )
    user = (f"About the candidate: {about_me}\nEvent: {event['name']}\nKind of event: {kind}{', online' if event.get('online') else ''}\n\n"
            'Return {"introduction":str,"openers":[str,str,str],"goal":str}')
    allowed = _numbers(f"{about_me} {event['name']}")

    def usable(data: dict) -> bool:
        intro, openers, goal = data["introduction"], [o.strip() for o in data["openers"]], data["goal"]
        texts = [intro, goal, *openers]
        return (EVENT_INTRO_WORDS[0] <= len(intro.split()) <= EVENT_INTRO_WORDS[1] and _numbers(intro) <= allowed
                and len(openers) == 3 and all(openers) and all(len(t.split()) <= SHORT_WORDS for t in [goal, *openers])
                and not any(VISA_WORDS.search(t) or PLACEHOLDER.search(t) for t in texts))

    data = _run("event prep", system, user, {"introduction": "", "openers": [""], "goal": ""}, 700,
                required=("introduction", "goal"), check=usable)
    dashless = lambda t: DASHES.sub(", ", t.strip())  # noqa: E731
    return {"introduction": dashless(data["introduction"]), "openers": [dashless(o) for o in data["openers"]], "goal": dashless(data["goal"])}


# ---------- peers: a broad field to match buddies on ----------

def suggest_field(role_names: list[str]) -> str | None:
    """One of peers.FIELDS for the user's target roles, or None when the model answers with
    anything not on the list (the user then picks by hand). Only the role names are sent."""
    labels = list(peers.FIELDS.values())
    system = ("Choose the one broad area of work that best fits these job titles, from the list given. "
              "Answer with the area exactly as it is written in the list.")
    user = f"Areas: {_j(labels)}\nJob titles: {_j(role_names)}\n\nReturn {{\"field\": str (one area from the list, exactly as written)}}"
    data = _run("peers_field", system, user, {"field": ""}, 200, required=("field",))
    wanted = " ".join(data["field"].split()).lower()
    return next((key for key, label in peers.FIELDS.items() if label.lower() == wanted), None)
