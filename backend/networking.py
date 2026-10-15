"""The networking pipeline's own rules: how a contact moves on, what to do next and when, which
follow-ups are due, which saved events are coming up, and the finding about messages that get no
replies. Pure functions over the user's own rows, worked out on every read.

Days come in already as London dates (`on_day`)."""
from datetime import date, timedelta

from analytics import plural

RELATIONSHIPS = {  # how the user knows them: the only connection a draft may mention
    "alumni": "Alumnus of my university",
    "tutor": "Tutor or lecturer",
    "supervisor": "Supervisor",
    "event": "Met at an event",
    "recruiter": "Recruiter",
    "introduced": "Introduced by someone",
    "none": "No connection yet",
}
STATUSES = {  # the pipeline, in order
    "to_contact": "To contact",
    "messaged": "Messaged",
    "replied": "Replied",
    "chat_booked": "Chat booked",
    "chat_done": "Chat done",
    "referral_offered": "Referral offered",
}
KINDS = {"sent": "messaged", "replied": "replied", "chat_booked": "chat_booked", "chat_done": "chat_done",
         "referral_offered": "referral_offered"}  # a step recorded, and the status it implies
MESSAGE_TYPES = {
    "connection_note": "LinkedIn connection note",
    "chat_request": "Request for a chat",
    "follow_up": "Follow-up",
    "thank_you": "Thank-you",
    "referral_ask": "Referral ask",
    "recruiter_intro": "Recruiter introduction",
    "reference_ask": "Asking for a reference",
    "own": "My own message",
}
EVENT_TYPES = {"meetup": "Meetup", "careers_fair": "Careers fair", "webinar": "Webinar", "society": "Society",
               "employer_event": "Employer event"}
EVENT_STATUSES = {"interested": "Interested", "going": "Going", "attended": "Attended"}
FOLLOW_UP_DAYS = 14   # no reply this long after a message: follow up
AFTER_EVENT_DAYS = 2  # message someone you met within 48 hours
COMING_UP = 3
NO_REPLY_MESSAGES = 5
REPLIED = {"replied", "chat_booked", "chat_done", "referral_offered"}  # the contact answered at some point
_ORDER = {status: i for i, status in enumerate(STATUSES)}


def advanced(status: str, kind: str) -> str:
    """The status after a step is recorded: the further of where they are and where the step puts
    them, so a thank-you sent after a chat never moves a contact back to Messaged."""
    implied = KINDS[kind]
    return implied if _ORDER[implied] > _ORDER[status] else status


def _last(history: list[dict], kind: str, message_type: str | None = None) -> date | None:
    days = [h["on_day"] for h in history if h["kind"] == kind and (message_type is None or h["message_type"] == message_type)]
    return max(days) if days else None


def _ago(days: int) -> str:
    return "sent today" if days == 0 else "sent yesterday" if days == 1 else f"sent {days} days ago"


def _next(text: str, due_on: date | None, today: date) -> dict:
    return {"text": text, "due_on": due_on, "late": due_on is not None and today > due_on}


def next_step(contact: dict, history: list[dict], today: date, met_on: date | None) -> dict:
    """What to do next with this contact and by when. `history` is their recorded steps; `met_on`
    the day of the saved event where the user met them, if any."""
    status = contact["status"]
    if status == "to_contact":
        if met_on:
            return _next("Message within 48 hours of meeting", met_on + timedelta(days=AFTER_EVENT_DAYS), today)
        return _next("Send a first message", None, today)
    if status == "messaged":
        latest = _latest_message(history)
        if latest is None:  # set by hand, with no message recorded
            return _next("Waiting for a reply", None, today)
        last = latest["on_day"]
        days, due = (today - last).days, last + timedelta(days=FOLLOW_UP_DAYS)
        if days >= FOLLOW_UP_DAYS and latest["message_type"] == "follow_up":  # one follow-up, then move on
            return _next("No reply after your follow-up: move on to someone else", None, today)
        if days >= FOLLOW_UP_DAYS:
            return _next(f"Follow up: {days} days since your message", due, today)
        return _next(f"Waiting for a reply ({_ago(days)})", due, today)
    if status == "replied":
        return _next("Book a chat", None, today)
    if status == "chat_booked":
        return _next("Prepare for your chat", None, today)
    if status == "chat_done":
        chat, thanked = _last(history, "chat_done"), _last(history, "sent", "thank_you")
        if thanked is None or (chat is not None and thanked < chat):
            return _next("Send a thank-you within 24 hours", chat + timedelta(days=1) if chat else None, today)
        where = f" at {contact['company']}" if contact.get("company") else ""
        return _next(f"Stay in touch, and ask about a referral when a role opens{where}", None, today)
    return _next("Link them to your application", None, today)


def _latest_message(history: list[dict]) -> dict | None:
    """The message sent most recently (rows come oldest first, so on one day the later row wins)."""
    sent = [h for h in history if h["kind"] == "sent"]
    return sorted(sent, key=lambda h: h["on_day"])[-1] if sent else None


def follow_ups_due(contacts: list[dict], outreach: list[dict], today: date) -> list[dict]:
    """Contacts still at Messaged whose last message was 14 or more days ago, the longest waiting first.
    Someone already followed up once is not due again: the guide says to move on."""
    by_contact = {}
    for row in outreach:
        if row["contact_id"]:
            by_contact.setdefault(row["contact_id"], []).append(row)
    latest = {cid: _latest_message(rows) for cid, rows in by_contact.items()}
    due = [c for c in contacts if c["status"] == "messaged" and latest.get(c["id"])
           and latest[c["id"]]["message_type"] != "follow_up" and (today - latest[c["id"]]["on_day"]).days >= FOLLOW_UP_DAYS]
    return sorted(due, key=lambda c: latest[c["id"]]["on_day"])


def waiting_to_be_messaged(contacts: list[dict]) -> list[dict]:
    """Contacts at To contact, the one added longest ago first."""
    return sorted((c for c in contacts if c["status"] == "to_contact"), key=lambda c: c["created_at"])


def outreach_days(outreach: list[dict]) -> list[date]:
    """The day of each message marked as sent: what counts toward the weekly outreach target."""
    return [row["on_day"] for row in outreach if row["kind"] == "sent"]


def coming_up(events: list[dict], today: date) -> list[dict]:
    """Saved events the user is interested in or going to, from today (London) on, soonest first.
    An event today stays until midnight."""
    upcoming = [e for e in events if e["status"] != "attended" and e["on_day"] >= today]
    return sorted(upcoming, key=lambda e: e["starts_at"])[:COMING_UP]


def findings(outreach: list[dict], contacts: list[dict]) -> list[dict]:
    """Five or more messages sent and nobody has replied yet: the messages, not the people, may be the problem."""
    messages = len(outreach_days(outreach))
    answered = any(row["kind"] in REPLIED for row in outreach) or any(c["status"] in REPLIED for c in contacts)
    if messages < NO_REPLY_MESSAGES or answered:
        return []
    return [{
        "id": "outreach-no-replies", "type": "network", "severity": 2,
        "title": "Your messages are not getting replies yet",
        "evidence": f"{plural(messages, 'message')} sent and no replies yet.",
        "action": "Send shorter messages that ask for 15 minutes of advice, not a job, and read how networking works in the UK.",
        "link": {"page": "networking", "label": "Read the guide", "tab": "guide"},
    }]


def chat_questions(contact: dict) -> list[str]:
    """Three questions for an informational chat, worded for the contact's role and company."""
    role, company = contact.get("role", "").strip(), contact.get("company", "").strip()
    return [
        f"What does your team at {company} work on at the moment?" if company else "What does your team work on at the moment?",
        (f"What does good look like in the first six months in your role as {role}?" if role
         else "What does good look like in someone's first six months in your team?"),
        f"What do you wish you had known before you joined {company}?" if company else "What do you wish you had known when you started in your field?",
    ]
