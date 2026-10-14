"""A prep pack's own rules: the right-to-work line, what is stored, the user's edits, what a
rebuild keeps, and what the mock interviewer is told. Pure functions; the model's part is
ai.prep_pack and the company's is research.brief."""
import copy

from cv import as_date, long_date

RIGHT_TO_WORK = {"graduate": "I have the right to work in the UK on a Graduate visa until {ends}.",
                 "student": "I am in the UK on a Student visa until {ends}."}
RIGHT_TO_WORK_NOTE = ("Employers often ask next whether you will need sponsorship. That answer is yours to add. "
                      "This is not immigration advice.")
INTERVIEW_TYPES = ("phone", "video", "in_person")
MAX_TICKS = 3
COMPANY_SUMMARY_CHARS = 600
QUESTIONS_CHARS = 1200
INTERVIEWER_SECTIONS = ("what_they_do", "products", "news")
NOT_PROVIDED = "Not provided."


def right_to_work(profile: dict) -> str:
    """One spoken line from the user's own visa type and end date; nothing about what comes after."""
    line, ends = RIGHT_TO_WORK.get(profile.get("visa_type")), as_date(profile.get("visa_end_date"))
    return line.format(ends=long_date(ends)) if line and ends else ""


def default_type(stage: str | None) -> str:
    """A phone screen is usually by phone; anything else starts as a video interview."""
    return "phone" if stage == "screening" else "video"


def content(*, written: dict, brief: dict, researched_at: str, interview_type: str, right_to_work: str) -> dict:
    """A pack as it is stored: its own copy of the brief, what the model wrote, and the user's parts."""
    return {"brief": {"facts": brief["facts"], "missing": brief["missing"], "notice": brief.get("notice"), "researched_at": researched_at},
            "talking_points": written["talking_points"], "pitch": written["pitch"], "pitch_edited": False,
            "likely_questions": written["likely_questions"], "questions_to_ask": written["questions_to_ask"], "ticked": [],
            "right_to_work": right_to_work, "right_to_work_edited": False, "interview_type": interview_type}


def edit(pack: dict, changes: dict) -> dict:
    """The pack with the user's changes: their pitch, their right-to-work line, the questions they
    ticked (at most three) and the interview type. ValueError for ticks or a type that cannot be."""
    changed = copy.deepcopy(pack)
    if "pitch" in changes:  # an emptied pitch is not the user's own: the next rebuild writes one again
        changed["pitch"], changed["pitch_edited"] = changes["pitch"], bool(changes["pitch"].strip())
    if "right_to_work" in changes:
        changed["right_to_work"], changed["right_to_work_edited"] = changes["right_to_work"], True
    if "ticked" in changes:
        ticked = changes["ticked"]
        if (len(ticked) > MAX_TICKS or len(set(ticked)) != len(ticked)
                or any(not 0 <= i < len(changed["questions_to_ask"]) for i in ticked)):
            raise ValueError("tick at most three of the questions shown")
        changed["ticked"] = list(ticked)
    if "interview_type" in changes:
        if changes["interview_type"] not in INTERVIEW_TYPES:
            raise ValueError("not an interview type")
        changed["interview_type"] = changes["interview_type"]
    return changed


def fill_right_to_work(pack: dict, profile: dict) -> dict:
    """The pack with today's right-to-work line when it has none and the user has not written or
    cleared one, so visa details added after the pack was built show without rebuilding it."""
    if pack.get("right_to_work") or pack.get("right_to_work_edited"):
        return pack
    return pack | {"right_to_work": right_to_work(profile)}


def rebuild(old: dict, new: dict) -> dict:
    """A rewritten pack that keeps what the user wrote: an edited pitch and right-to-work line, and
    the interview type they chose. Ticks are cleared, since the questions to ask are new."""
    kept = dict(new, interview_type=old["interview_type"], ticked=[])
    if old.get("pitch_edited"):
        kept |= {"pitch": old["pitch"], "pitch_edited": True}
    if old.get("right_to_work_edited"):
        kept |= {"right_to_work": old["right_to_work"], "right_to_work_edited": True}
    return kept


def _within(parts: list[str], limit: int) -> str:
    """Whole parts joined by spaces, as many as fit in `limit` characters."""
    text = ""
    for part in parts:
        longer = f"{text} {part}".strip()
        if len(longer) > limit:
            break
        text = longer
    return text


def for_interviewer(pack: dict) -> dict:
    """What the mock interviewer is told: a short company summary (what they do, products, news)
    and the likely questions, each cut to whole sentences or whole questions."""
    facts = [f["text"] for f in pack["brief"]["facts"] if f["section"] in INTERVIEWER_SECTIONS]
    questions = [q["question"] for q in pack["likely_questions"]]
    return {"company_brief": _within(facts, COMPANY_SUMMARY_CHARS) or NOT_PROVIDED,
            "likely_questions": _within(questions, QUESTIONS_CHARS) or "None given."}
