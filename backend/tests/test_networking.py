"""The networking pipeline's rules: how a contact moves on, what to do next and when, which
follow-ups are due, what is coming up, and the finding about messages with no replies."""
from datetime import date, datetime, timedelta, timezone

import pytest

import networking

TODAY = date(2026, 10, 15)


def contact(status="to_contact", **kw):
    return {"id": kw.pop("id", "c1"), "name": "Zzqx Person", "role": "", "company": "", "relationship": "none",
            "status": status, "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc)} | kw


def sent(day, message_type="chat_request", contact_id="c1"):
    return {"contact_id": contact_id, "kind": "sent", "message_type": message_type, "on_day": day}


def step(kind, day, contact_id="c1"):
    return {"contact_id": contact_id, "kind": kind, "message_type": None, "on_day": day}


# ---------- moving through the pipeline ----------

@pytest.mark.parametrize("status, kind, expected", [
    ("to_contact", "sent", "messaged"),
    ("messaged", "replied", "replied"),
    ("replied", "chat_booked", "chat_booked"),
    ("to_contact", "referral_offered", "referral_offered"),
    ("chat_done", "sent", "chat_done"),         # a thank-you after a chat does not move them back
    ("referral_offered", "replied", "referral_offered"),
    ("chat_booked", "chat_booked", "chat_booked"),
])
def test_an_event_only_moves_a_contact_forward(status, kind, expected):
    assert networking.advanced(status, kind) == expected


def test_every_kind_implies_a_status_in_the_pipeline():
    assert set(networking.KINDS.values()) <= set(networking.STATUSES)
    assert list(networking.STATUSES)[0] == "to_contact"


# ---------- what to do next ----------

def test_someone_not_yet_contacted_gets_a_first_message():
    nxt = networking.next_step(contact(), [], TODAY, met_on=None)
    assert nxt == {"text": "Send a first message", "due_on": None, "late": False}


def test_someone_met_at_an_event_is_messaged_within_48_hours():
    met = TODAY - timedelta(days=1)
    nxt = networking.next_step(contact(relationship="event"), [], TODAY, met_on=met)
    assert nxt == {"text": "Message within 48 hours of meeting", "due_on": met + timedelta(days=2), "late": False}
    late = networking.next_step(contact(relationship="event"), [], TODAY, met_on=TODAY - timedelta(days=3))
    assert late["late"] is True


def test_a_message_is_followed_up_after_14_days():
    waiting = networking.next_step(contact("messaged"), [sent(TODAY - timedelta(days=13))], TODAY, met_on=None)
    assert waiting["text"] == "Waiting for a reply (sent 13 days ago)"
    assert waiting["due_on"] == TODAY + timedelta(days=1) and not waiting["late"]
    due = networking.next_step(contact("messaged"), [sent(TODAY - timedelta(days=14))], TODAY, met_on=None)
    assert due == {"text": "Follow up: 14 days since your message", "due_on": TODAY, "late": False}
    later = networking.next_step(contact("messaged"), [sent(TODAY - timedelta(days=20))], TODAY, met_on=None)
    assert later["text"] == "Follow up: 20 days since your message" and later["late"]


def test_the_follow_up_counts_from_the_latest_message():
    history = [sent(TODAY - timedelta(days=30)), sent(TODAY - timedelta(days=2), "follow_up")]
    assert networking.next_step(contact("messaged"), history, TODAY, met_on=None)["text"] == "Waiting for a reply (sent 2 days ago)"


@pytest.mark.parametrize("days, words", [(0, "sent today"), (1, "sent yesterday"), (5, "sent 5 days ago")])
def test_waiting_says_when_it_was_sent(days, words):
    nxt = networking.next_step(contact("messaged"), [sent(TODAY - timedelta(days=days))], TODAY, met_on=None)
    assert nxt["text"] == f"Waiting for a reply ({words})"


def test_messaged_by_hand_with_no_message_recorded():
    assert networking.next_step(contact("messaged"), [], TODAY, met_on=None) == {"text": "Waiting for a reply", "due_on": None, "late": False}


@pytest.mark.parametrize("status, text", [
    ("replied", "Book a chat"),
    ("chat_booked", "Prepare for your chat"),
    ("referral_offered", "Link them to your application"),
])
def test_later_steps(status, text):
    assert networking.next_step(contact(status), [], TODAY, met_on=None)["text"] == text


def test_a_thank_you_is_due_the_day_after_a_chat():
    chat = TODAY - timedelta(days=1)
    nxt = networking.next_step(contact("chat_done"), [step("chat_done", chat)], TODAY, met_on=None)
    assert nxt == {"text": "Send a thank-you within 24 hours", "due_on": chat + timedelta(days=1), "late": False}


def test_a_thank_you_sent_before_the_chat_does_not_count():
    chat = TODAY - timedelta(days=1)
    history = [sent(chat - timedelta(days=5), "thank_you"), step("chat_done", chat)]
    assert networking.next_step(contact("chat_done"), history, TODAY, met_on=None)["text"] == "Send a thank-you within 24 hours"


def test_after_the_thank_you_they_keep_in_touch():
    chat = TODAY - timedelta(days=3)
    history = [step("chat_done", chat), sent(chat, "thank_you")]
    nxt = networking.next_step(contact("chat_done", company="Zzqx Holdings"), history, TODAY, met_on=None)
    assert nxt == {"text": "Stay in touch, and ask about a referral when a role opens at Zzqx Holdings", "due_on": None, "late": False}
    assert networking.next_step(contact("chat_done"), history, TODAY, met_on=None)["text"] == "Stay in touch, and ask about a referral when a role opens"


# ---------- follow-ups due, and who is waiting for a first message ----------

def test_follow_ups_due_lists_contacts_messaged_14_or_more_days_ago():
    contacts = [contact("messaged", id="a", name="Zzqx Ann"), contact("messaged", id="b", name="Zzqx Bo"),
                contact("replied", id="c"), contact("messaged", id="d", name="Zzqx Di")]
    outreach = [sent(TODAY - timedelta(days=20), contact_id="a"), sent(TODAY - timedelta(days=13), contact_id="b"),
                sent(TODAY - timedelta(days=30), contact_id="c"), sent(TODAY - timedelta(days=14), contact_id="d")]
    due = networking.follow_ups_due(contacts, outreach, TODAY)
    assert [(c["id"], c["name"]) for c in due] == [("a", "Zzqx Ann"), ("d", "Zzqx Di")]  # the longest waiting first


def test_waiting_to_be_messaged_is_oldest_first():
    newer = contact(id="n", created_at=datetime(2026, 10, 10, tzinfo=timezone.utc))
    older = contact(id="o", created_at=datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert [c["id"] for c in networking.waiting_to_be_messaged([newer, contact("messaged", id="m"), older])] == ["o", "n"]


def test_outreach_days_are_the_days_messages_were_sent():
    outreach = [sent(TODAY), step("replied", TODAY), sent(TODAY - timedelta(days=8), contact_id=None)]
    assert networking.outreach_days(outreach) == [TODAY, TODAY - timedelta(days=8)]


# ---------- coming up ----------

def event(day, status="going", hour=18, **kw):
    starts = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
    return {"id": kw.pop("id", f"{day}-{hour}"), "name": "Zzqx Meetup", "status": status, "starts_at": starts, "on_day": day} | kw


def test_coming_up_keeps_today_and_later_and_drops_the_past():
    events = [event(TODAY, hour=22, id="tonight"), event(TODAY - timedelta(days=1), id="yesterday"),
              event(TODAY + timedelta(days=3), status="interested", id="soon")]
    assert [e["id"] for e in networking.coming_up(events, TODAY)] == ["tonight", "soon"]


def test_coming_up_leaves_out_attended_events_and_keeps_three_soonest():
    events = [event(TODAY + timedelta(days=d), id=f"d{d}") for d in (5, 1, 9, 3)] + [event(TODAY, status="attended", id="done")]
    assert [e["id"] for e in networking.coming_up(events, TODAY)] == ["d1", "d3", "d5"]


def test_coming_up_orders_one_day_by_time():
    events = [event(TODAY, hour=19, id="late"), event(TODAY, hour=9, id="early")]
    assert [e["id"] for e in networking.coming_up(events, TODAY)] == ["early", "late"]


# ---------- the finding ----------

def test_five_messages_and_no_replies_is_a_finding():
    contacts = [contact("messaged", id=str(i)) for i in range(5)]
    outreach = [sent(TODAY - timedelta(days=i), contact_id=str(i)) for i in range(5)]
    [finding] = networking.findings(outreach, contacts)
    assert finding["id"] == "outreach-no-replies" and finding["type"] == "network"
    assert finding["evidence"] == "5 messages sent and no replies yet."
    assert finding["link"] == {"page": "networking", "label": "Read the guide", "tab": "guide"}


def test_four_messages_is_not_yet_a_finding():
    outreach = [sent(TODAY - timedelta(days=i), contact_id=str(i)) for i in range(4)]
    assert networking.findings(outreach, [contact("messaged", id=str(i)) for i in range(4)]) == []


@pytest.mark.parametrize("kind", ["replied", "chat_booked", "chat_done", "referral_offered"])
def test_one_reply_or_later_step_ends_the_finding(kind):
    outreach = [sent(TODAY - timedelta(days=i), contact_id=str(i)) for i in range(6)] + [step(kind, TODAY, contact_id="0")]
    assert networking.findings(outreach, [contact("messaged", id=str(i)) for i in range(6)]) == []


def test_a_reply_set_by_hand_also_ends_it():
    outreach = [sent(TODAY - timedelta(days=i), contact_id=str(i)) for i in range(6)]
    contacts = [contact("messaged", id=str(i)) for i in range(5)] + [contact("replied", id="5")]
    assert networking.findings(outreach, contacts) == []


# ---------- chat preparation ----------

def test_chat_questions_use_the_role_and_company():
    questions = networking.chat_questions(contact(role="Data Analyst", company="Zzqx Holdings"))
    assert questions == ["What does your team at Zzqx Holdings work on at the moment?",
                         "What does good look like in the first six months in your role as Data Analyst?",
                         "What do you wish you had known before you joined Zzqx Holdings?"]


def test_chat_questions_without_a_role_or_company():
    questions = networking.chat_questions(contact())
    assert questions == ["What does your team work on at the moment?",
                         "What does good look like in someone's first six months in your team?",
                         "What do you wish you had known when you started in your field?"]


def test_every_label_and_text_is_plain_british_copy():
    texts = [*networking.RELATIONSHIPS.values(), *networking.STATUSES.values(), *networking.MESSAGE_TYPES.values(),
             *networking.EVENT_TYPES.values(), *networking.EVENT_STATUSES.values(),
             *networking.chat_questions(contact(role="Analyst", company="Zzqx")),
             networking.findings([sent(TODAY, contact_id=str(i)) for i in range(5)], [])[0]["action"]]
    assert not any("—" in t for t in texts)



# ---------- the final review: one follow-up, then move on ----------

def test_after_a_follow_up_with_no_reply_the_user_moves_on():
    history = [sent(TODAY - timedelta(days=40)), sent(TODAY - timedelta(days=20), "follow_up")]
    nxt = networking.next_step(contact("messaged"), history, TODAY, met_on=None)
    assert nxt == {"text": "No reply after your follow-up: move on to someone else", "due_on": None, "late": False}
    waiting = [sent(TODAY - timedelta(days=40)), sent(TODAY - timedelta(days=3), "follow_up")]
    assert networking.next_step(contact("messaged"), waiting, TODAY, met_on=None)["text"] == "Waiting for a reply (sent 3 days ago)"


def test_a_contact_already_followed_up_is_not_due_again():
    contacts = [contact("messaged", id="a", name="Zzqx Ann"), contact("messaged", id="b", name="Zzqx Bo")]
    outreach = [sent(TODAY - timedelta(days=40), contact_id="a"), sent(TODAY - timedelta(days=20), "follow_up", contact_id="a"),
                sent(TODAY - timedelta(days=20), contact_id="b")]
    assert [c["id"] for c in networking.follow_ups_due(contacts, outreach, TODAY)] == ["b"]
