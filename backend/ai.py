"""Every AI step: one prompt in, JSON out, shaped to what the UI expects.

A step returns the model's own result or raises AIError. Nothing is ever substituted for a
failed call, so a user never sees content that did not come from their own data."""
import json
import logging
import re
from datetime import date

import anthropic
import httpx

import cv
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
MAX_KEYWORDS, MAX_KEYWORD_CHARS, MAX_GAPS = 15, 40, 5
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


def _faithful(wording: str, achievement: dict) -> bool:
    """Whether a reworded bullet kept the achievement's figures: every number of the stored bullet,
    and none the achievement does not hold."""
    held = _numbers(_j({k: achievement.get(k) for k in ("title", "raw", "uk_version", "outcome", "scale", "context_note")}), spelled=True)
    return _numbers(achievement.get("uk_version") or "") <= _numbers(wording) <= held


def build_cv(profile: dict, education: list, work_history: list, achievements: list, skills: list, job: dict | None = None,
             today: date | None = None) -> dict:
    """The wording of a CV: {"profile", "bullets": [{"achievement_id", "text"}], "skills": {"technical", "tools"}}.
    A bullet is kept only for one of the user's achievements, once, and only reworded if it kept
    that achievement's numbers; otherwise the stored bullet stands. A skill is kept only if it is
    one of `skills`. A profile paragraph holding a number the candidate's facts do not is refused."""
    today = today or date.today()
    aim = "this job" if job else "the candidate's field"
    system = (
        f"Write the parts of a UK CV that are a matter of wording, {'tailored to one job' if job else 'for any job in the field the candidate works in'}. "
        "The candidate's employers, job titles, dates, courses and grades are printed on the CV from their own records: do not restate or change them. "
        "Use only the facts given. Never add an employer, a date, a qualification, a skill, a tool or a number that is not in the input. "
        "profile is a personal profile of three to four lines, 50 to 70 words, written without 'I': who they are, their strongest evidence, "
        f"and what they are looking for{', in the words of the job description' if job else ''}. "
        f"bullets are the achievements that best fit {aim}, the most relevant first, each reworded as one CV bullet: an action verb first, "
        "then what was done and its result. Give each bullet the id of the achievement it came from and use an achievement at most once. "
        "Keep every number exactly as the achievement writes it. "
        f"The CV must fit two A4 pages: at most five bullets for one job, one for each project, and about {CV_BULLETS} in all. "
        "skills sorts the candidate's own skills into technical (methods, programming languages, subject knowledge) and tools (software and platforms), "
        "the most relevant first. Use only skills from their list, spelled as they are, and leave out any that do not matter here."
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
        "keywords are the 8 to 15 skills, tools, methods and qualifications the advert stresses most, each copied from the advert in the "
        "advert's own words, one to three words long, the most important first. Leave out benefits and generic wishes such as 'team player'. "
        "gaps are up to four honest gaps between what the advert asks for and what the achievements show, each one sentence the candidate "
        "should be ready to talk about. "
        "cover_letter is the body of a UK cover letter in three short paragraphs, under 220 words in all, in the first person: "
        "why_them (why this company and this role, specific to the advert), why_you (two pieces of evidence from the achievements, with their numbers), "
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
        if term and len(term) <= MAX_KEYWORD_CHARS and term.lower() not in seen and cv.has_term(term, advert):
            seen.add(term.lower())
            keywords.append(term)
    return {"keywords": keywords[:MAX_KEYWORDS], "gaps": [g.strip() for g in data["gaps"] if g.strip()][:MAX_GAPS],
            "cover_letter": {k: data["cover_letter"][k].strip() for k in LETTER_PARTS}}


# 5. One achievement to a STAR story
STORY_KEYS = ("title", "competency", "situation", "task", "action", "result", "strength", "tip")


def _story(data: dict, achievement: dict) -> dict:
    """A story as the model wrote it, with a title and a strength the UI knows."""
    strength = data["strength"].strip().lower()
    return {k: data[k] for k in STORY_KEYS} | {
        "title": data["title"].strip() or achievement.get("title", ""),
        "strength": strength if strength in STRENGTHS else "needs detail",
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
        '"action":str,"result":str,"strength":"strong"|"needs a number"|"needs detail","tip":str}'
    )
    data = _run("star", system, user, dict.fromkeys(STORY_KEYS, ""), 900, required=("situation", "action"))
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
        '"action":str,"result":str,"strength":"strong"|"needs a number"|"needs detail","tip":str}]}'
    )
    template = {"stories": [{"n": 0} | dict.fromkeys(STORY_KEYS, "")]}
    data = _run("story bank", system, user, template, 300 + 450 * len(achievements), required=("stories",))
    sent, found = {a["n"]: a for a in achievements}, {}
    for story in data["stories"]:
        achievement = sent.get(story["n"])
        if achievement and story["n"] not in found and story["situation"].strip() and story["action"].strip():
            found[story["n"]] = _story(story, achievement)
    if not found:
        raise AIError("story bank")
    return found
