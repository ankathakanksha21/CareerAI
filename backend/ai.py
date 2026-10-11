"""Every AI step: one prompt in, JSON out, shaped to what the UI expects.

A step returns the model's own result or raises AIError. Nothing is ever substituted for a
failed call, so a user never sees content that did not come from their own data."""
import json
import logging
import re

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
    if isinstance(value, (list, str)):
        return not (value.strip() if isinstance(value, str) else value)
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


def _who(profile: dict) -> str:
    """One line on the candidate from the facts they typed in."""
    study = " at ".join(x for x in (profile.get("course"), profile.get("university")) if x)
    visa = f"{profile['visa_type'].capitalize()} visa" if profile.get("visa_type") else ""
    return ", ".join(x for x in (profile.get("full_name"), study, visa) if x)


# 1. Background transcript to achievements
def extract_achievements(transcript: str, profile: dict) -> dict:
    system = (
        "Turn a candidate's spoken or pasted background into achievements written for UK employers. "
        "Each item is one achievement. Use only facts, tools, methods and data sources the candidate actually stated; never add detail they did not say. "
        "uk_version is a single UK CV bullet: action verb first, result with a number, scale. "
        "If the candidate gave no number, do not make one up: set outcome to 'Add a number: <what to measure>'. "
        "context_note explains something a UK recruiter would not know (an overseas employer, a local term, why it counts) "
        "or gives one UK framing tip. If the text contains no achievements at all, return an empty items list."
    )
    user = (
        f"Candidate: {_who(profile)}.\nBackground transcript:\n{transcript}\n\n"
        'Return {"items":[{"title":str,"raw":str (their own words, short),"uk_version":str,"skills":[str],'
        '"outcome":str,"scale":str,"context_note":str}],'
        '"pitch":str (two sentences in the first person, starting with I am, for networking)}. 3 to 6 items.'
    )
    template = {"items": [{"title": "", "raw": "", "uk_version": "", "skills": [""], "outcome": "", "scale": "", "context_note": ""}], "pitch": ""}
    data = _run("achievements", system, user, template, 2500)
    items = []
    for item in data["items"]:
        text = item["uk_version"].strip() or item["raw"].strip() or item["title"].strip()
        if text:  # an item with nothing in it is not an achievement
            items.append(item | {"uk_version": text, "title": item["title"].strip() or text[:60]})
    return {"items": items, "pitch": data["pitch"].strip()}


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
        '"summary":str (2 sentences),"strengths":[str],"fixes":[str] (max 3, concrete),'
        '"rewrite":{"question":str,"better_answer":str (a stronger STAR answer under 120 words, using only facts from the transcript)},'
        '"uk_tone_notes":[str]}'
    )
    template = {"scores": {"structure": 0, "clarity": 0, "evidence": 0, "uk_tone": 0}, "summary": "", "strengths": [""],
                "fixes": [""], "rewrite": {"question": "", "better_answer": ""}, "uk_tone_notes": [""]}
    data = _run("interview", system, user, template, 1600, required=("summary", "fixes"))
    scores = {k: max(0, min(5, data["scores"][k])) for k in template["scores"]}
    return {k: data[k] for k in template} | {"scores": scores}


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
