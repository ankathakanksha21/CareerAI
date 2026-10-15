"""The rules of buddy groups (step 7), as pure functions: the fields people choose, the code of
conduct, what a contact link may be, how this week and the group streak are told to the group,
when a member counts as inactive, and how the person or group to propose is chosen.

What a member may see of another is decided in peerdb.peer_view, the one place that reads it."""
import re
from datetime import date, timedelta
from urllib.parse import urlsplit

from habits import monday

FIELDS = {
    "accounting": "Accounting and finance",
    "banking": "Banking and investment",
    "consulting": "Consulting",
    "data": "Data and analytics",
    "software": "Software and IT",
    "engineering": "Engineering",
    "science": "Science and research",
    "healthcare": "Healthcare and life sciences",
    "law": "Law",
    "marketing": "Marketing, advertising and PR",
    "sales": "Sales and business development",
    "hr": "Human resources",
    "operations": "Operations, logistics and supply chain",
    "product": "Project and product management",
    "design": "Design, media and creative",
    "education": "Education",
    "public": "Public sector and policy",
    "charity": "Charity and social care",
    "property": "Property, architecture and construction",
    "energy": "Energy and sustainability",
    "hospitality": "Hospitality, retail and tourism",
}

# Approved by the owner, 15 October 2026 (step document)
CONDUCT = (
    "Be kind. Encourage; never mock, insult or pressure anyone.",
    "Keep it to the job search. No selling, no recruiting for money, no asking for money or favours.",
    "Keep what you see in the group to yourself. Never share another member's details or check-ins elsewhere.",
    "Never ask anyone for passwords, documents, bank details or anything about their visa.",
    "If you ever meet in person, meet somewhere public.",
    "Report anything that makes you uncomfortable. Every report is reviewed, and anyone who breaks these rules loses access to buddy groups.",
)

REPORT_REASONS = {
    "unkind": "Unkind, harassing or threatening",
    "spam": "Selling, spam or asking for money",
    "personal": "Asked for personal details or documents",
    "other": "Something else",
}

NUDGE = "{name} sent you a nudge: one step today keeps your week on track."
CHECKIN_CHARS = 140
DETAILS_CHARS = 500
PROPOSAL_DAYS = 7
INACTIVE_DAYS = 21
MAX_MEMBERS = 3
TARGETS = ("applications", "practice", "outreach")

# ---------- contact links ----------

BAD_CONTACT_LINK = ("Use your LinkedIn profile address (https://www.linkedin.com/in/your-name) "
                    "or a WhatsApp link (https://wa.me/447700900123).")
LINKEDIN_HOST = re.compile(r"(?:www\.|[a-z]{2}\.)?linkedin\.com")
LINKEDIN_PATH = re.compile(r"/(?i:in)/([A-Za-z0-9\-_%]{3,100})/?")
WHATSAPP_PATH = re.compile(r"/([0-9]{7,15})/?")


def contact_link(value: str) -> str:
    """A LinkedIn profile or a WhatsApp chat address, tidied to one form, or ValueError. Only the
    two forms checked on 15 October 2026 are accepted: linkedin.com/in/<handle> and
    wa.me/<international number in digits>. Typed without a scheme it is read as https."""
    text = (value or "").strip()
    if not text:
        raise ValueError(BAD_CONTACT_LINK)
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise ValueError(BAD_CONTACT_LINK) from None
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or parts.username or parts.password or port is not None or "@" in parts.netloc:
        raise ValueError(BAD_CONTACT_LINK)
    if LINKEDIN_HOST.fullmatch(host) and (found := LINKEDIN_PATH.fullmatch(parts.path)):
        return f"https://www.linkedin.com/in/{found.group(1)}"
    if host == "wa.me" and (found := WHATSAPP_PATH.fullmatch(parts.path)):
        return f"https://wa.me/{found.group(1)}"
    raise ValueError(BAD_CONTACT_LINK)


# ---------- this week, the group streak, inactivity ----------

def progress(week: dict) -> dict:
    """How many of the three weekly targets are met, from habits.this_week. Counts are never shown."""
    return {"met": sum(week[k] >= week["goal"][k] for k in TARGETS), "of": len(TARGETS)}


def group_streak(members: list[tuple[int, bool]], active_since: date, today: date) -> int:
    """Weeks in a row, ending last week, in which every member met all their targets, plus this week
    once all have. Each member is (their streak, all targets met this week): their streak less this
    week is their run to last week. Only weeks since the group became active count."""
    if not members:
        return 0
    weeks_together = (monday(today) - monday(active_since)).days // 7
    run = min(min(streak - met for streak, met in members), weeks_together)
    return max(run, 0) + all(met for _, met in members)


def inactive(last_active: date | None, joined: date, today: date) -> bool:
    """Nothing counted for three weeks (an application with a CV, a mock interview, a message sent,
    a check-in), after being in the group at least that long."""
    limit = today - timedelta(days=INACTIVE_DAYS)
    return joined <= limit and (last_active is None or last_active <= limit)


# ---------- matching ----------

def _norm(values) -> set[str]:
    return {v.strip().lower() for v in values if v and v.strip() and v.strip().lower() != "remote"}


def rank(me: dict, candidates: list[dict]) -> dict | None:
    """The candidate to propose, or None. Same field first; within it a shared city, then the same
    university, then a person before a group, then whoever has waited longest. A group with room is
    offered only to someone in the field of every member; a different field is the last resort."""
    places, university = _norm(me["places"]), (me["university"] or "").strip().lower()

    def key(c: dict):
        same_field = c["fields"] == {me["field"]}
        return (not same_field, not (places & _norm(c["places"])), not (university and university in _norm(c["universities"])),
                c["kind"] != "person", c["since"])

    allowed = [c for c in candidates if c["kind"] == "person" or c["fields"] == {me["field"]}]
    return min(allowed, key=key) if allowed else None
