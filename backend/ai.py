"""Every AI step: one prompt in, JSON out, shaped to what the UI expects.

A step returns the model's own result or raises AIError. Nothing is ever substituted for a
failed call, so a user never sees content that did not come from their own data."""
import json
import logging
import re
from datetime import date

import anthropic
import httpx

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


def _run(task: str, system: str, user: str, template: dict, max_tokens: int = 1500, required: tuple = ()) -> dict:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            data = _conform(complete_json(BASE + "\n\n" + system, user, max_tokens), template)
        except (ValueError, httpx.HTTPError, anthropic.APIError) as e:
            # the exception type only: prompts and replies hold personal data and stay out of the logs
            log.warning("AI task %s, attempt %d: %s", task, attempt, type(e).__name__)
            continue
        missing = [k for k in required if _blank(data.get(k))]
        if not missing:
            return data
        log.warning("AI task %s, attempt %d: reply had no %s", task, attempt, ", ".join(missing))
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


def needs_number(achievement: dict) -> bool:
    """True when an achievement has no figure yet: the extraction marked it so, or neither the
    bullet nor the result holds a digit."""
    outcome = achievement.get("outcome") or ""
    return outcome.strip().lower().startswith("add a number") or not re.search(r"\d", f"{achievement.get('uk_version') or ''} {outcome}")


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
                             "raw": verbatim(item["raw"] or bullet, text, speech=source != "cv")})
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


# 4. A tailored CV and cover letter for one job
def tailor(job: dict, achievements: list, profile: dict) -> dict:
    system = (
        "Tailor a UK CV and cover letter for one job using only the candidate's achievements. "
        "UK CV rules: two pages, no photo or date of birth, bullets start with an action verb and carry a number. "
        "Pick and rewrite the 4 to 5 most relevant achievements in this job's language. "
        "Cover letter follows three short paragraphs: why them (specific to the company and role), why you (2 pieces of evidence), "
        "what you will deliver in the first months. Under 220 words total. List honest gaps the candidate should be ready to address."
    )
    user = (
        f"Job title: {job['title']}\nCompany: {job['company']}\nKeywords: {_j(job.get('keywords') or [])}\n"
        f"Job description:\n{(job.get('description') or '')[:6000]}\n\nCandidate: {_who(profile)}\n"
        f"Achievements: {_j([{k: a.get(k) for k in ('id', 'uk_version', 'skills', 'outcome')} for a in achievements])}\n\n"
        'Return {"profile":str (3-line CV profile),"bullets":[{"text":str,"achievement_id":str}],'
        '"keywords":[str] (job keywords now covered),'
        '"cover_letter":{"why_them":str,"why_you":str,"what_you_deliver":str},"gaps":[str]}'
    )
    template = {"profile": "", "bullets": [{"text": "", "achievement_id": ""}], "keywords": [""],
                "cover_letter": {"why_them": "", "why_you": "", "what_you_deliver": ""}, "gaps": [""]}
    data = _run("tailor", system, user, template, 2000, required=("bullets", "cover_letter"))
    own = {str(a.get("id")) for a in achievements}
    bullets = [{"text": b["text"].strip(), "achievement_id": b["achievement_id"] if b["achievement_id"] in own else ""}
               for b in data["bullets"] if b["text"].strip()]
    if not bullets:
        raise AIError("tailor")
    return {"profile": data["profile"], "bullets": bullets, "keywords": data["keywords"],
            "cover_letter": data["cover_letter"], "gaps": data["gaps"]}


# 5. One achievement to a STAR story
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
    template = {"title": "", "competency": "", "situation": "", "task": "", "action": "", "result": "", "strength": "", "tip": ""}
    data = _run("star", system, user, template, 900, required=("situation", "action"))
    strength = data["strength"].strip().lower()
    return {k: data[k] for k in template} | {
        "title": data["title"].strip() or achievement.get("title", ""),
        "strength": strength if strength in STRENGTHS else "needs detail",
    }


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
