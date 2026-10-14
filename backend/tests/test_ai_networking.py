"""Outreach drafts and event preparation: the model's own words, checked in code. A draft fits its
limit or is asked for once more and then refused, never cut; it claims no connection the user did
not enter; and the model never sees the contact's name or notes, or the user's own name."""
import pytest

import ai

ABOUT = "I am an MSc Data Science student at University of Zzqx, finishing in September 2026. I built a sales dashboard used by 40 staff."
NOTE_BODY = "I am an MSc Data Science student and I would be glad to follow your work in analytics at Zzqx Holdings."
CHAT_BODY = ("I am studying data science and hope to start as an analyst. Would you have 15 minutes in the next few weeks to "
             "share some advice on how you got into the field?")


@pytest.fixture
def model(monkeypatch):
    """Script the model: each entry is a parsed reply, or an exception to raise. Returns the calls made."""
    def install(*script):
        replies, calls = list(script), []

        def fake(system, user, max_tokens=1500):
            calls.append({"system": system, "user": user})
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        monkeypatch.setattr(ai, "complete_json", fake)
        return calls
    return install


def contact(relationship="none", **kw):
    return {"name": "Priya Zzqx-Shah", "role": "Data Analyst", "company": "Zzqx Holdings", "relationship": relationship,
            "notes": "Private: met her brother once"} | kw


def draft(kind="chat_request", relationship="none", **kw):
    args = {"kind": kind, "contact": contact(relationship), "sender": "Test Person", "about_me": ABOUT} | kw
    return ai.outreach_draft(**args)


def words(n: int, start: str = "Would you have 15 minutes for advice") -> str:
    """A body of exactly n words."""
    base = start.split()
    return " ".join(base + ["word"] * (n - len(base))) + "."


# ---------- shape and limits ----------

def test_a_connection_note_has_the_greeting_and_name_and_fits_200_characters(model):
    model({"body": NOTE_BODY})
    result = draft("connection_note")
    assert result["message"] == f"Hi Priya,\n{NOTE_BODY}\nTest"
    assert result["characters"] == len(result["message"]) <= 200


def test_a_connection_note_over_200_characters_is_asked_for_again_then_refused(model):
    long = NOTE_BODY + " " + "I have worked on several analytics projects in recent years." * 2
    calls = model({"body": long}, {"body": long})
    with pytest.raises(ai.AIError):
        draft("connection_note")
    assert len(calls) == 2


def test_a_second_note_that_fits_is_used_whole(model):
    long = NOTE_BODY + " " + "I have worked on several analytics projects in recent years." * 2
    model({"body": long}, {"body": NOTE_BODY})
    assert NOTE_BODY in draft("connection_note")["message"]


@pytest.mark.parametrize("ask", ["Would you be free for a quick chat?", "Could you refer me for a role?", "I would value your advice."])
def test_a_connection_note_asks_for_nothing(model, ask):
    calls = model({"body": f"{NOTE_BODY} {ask}"}, {"body": NOTE_BODY})
    assert draft("connection_note")["message"].count("?") == 0
    assert len(calls) == 2


def test_a_chat_request_of_80_words_is_refused_and_79_accepted(model):
    model({"body": words(80)}, {"body": words(80)})
    with pytest.raises(ai.AIError):
        draft("chat_request")
    model({"body": words(79)})
    assert draft("chat_request")["words"] == 79


@pytest.mark.parametrize("body", [
    "I am studying data science. Would you have time to share some advice?",              # no 15 minutes
    "Would you have 15 minutes to talk? I would also love a referral for your open role.",  # asks for a job
])
def test_a_chat_request_asks_for_15_minutes_of_advice_not_a_job(model, body):
    calls = model({"body": body}, {"body": CHAT_BODY})
    assert draft("chat_request")["message"].count(CHAT_BODY) == 1
    assert len(calls) == 2


def test_a_follow_up_is_at_most_two_sentences(model):
    three = "I wanted to follow up on my message. I know you are busy. Would 15 minutes be possible?"
    two = "I wanted to follow up on my message from a fortnight ago. Would a short call in the coming weeks be possible?"
    calls = model({"body": three}, {"body": two})
    assert two in draft("follow_up")["message"]
    assert len(calls) == 2


def test_a_thank_you_uses_what_was_learned(model):
    learned = "how the analytics team tests its dbt models"
    vague = "Thank you for your time today. I learned a lot and really enjoyed our conversation."
    good = "Thank you for your time today. Hearing how your analytics team tests its models with dbt was really useful."
    calls = model({"body": vague}, {"body": good})
    assert good in draft("thank_you", learned=learned)["message"]
    assert len(calls) == 2


def test_a_recruiter_introduction_gives_the_start_date_as_typed(model):
    without = "I am a data science graduate looking for analyst roles in Leeds and can start soon."
    exact = "I am a data science graduate looking for analyst roles in Leeds and can start from 2 November."
    calls = model({"body": without}, {"body": exact})
    assert exact in draft("recruiter_intro", relationship="recruiter", start="from 2 November", looking_for=["Data Analyst"])["message"]
    assert len(calls) == 2


def test_a_referral_ask_gets_the_job_line_from_code(model):
    job = {"title": "Junior Data Analyst", "company": "Zzqx Holdings", "summary": "Reporting role.", "url": "https://www.reed.co.uk/jobs/123"}
    body = ("I saw the Junior Data Analyst role at Zzqx Holdings. My dashboard work for 40 staff matches its reporting focus. "
            "Would you be comfortable referring me?")
    model({"body": body})
    message = draft("referral_ask", relationship="alumni", university="University of Zzqx", job=job)["message"]
    assert message == (f"Hi Priya,\n\n{body}\n\nThe role: Junior Data Analyst\nhttps://www.reed.co.uk/jobs/123\n\n"
                       "Best wishes,\nTest Person")
    calls = model({"body": body + " See https://www.reed.co.uk/jobs/123"}, {"body": body})
    draft("referral_ask", relationship="alumni", university="University of Zzqx", job=job)
    assert len(calls) == 2  # the address comes from the saved job, never from the model


# ---------- honesty ----------

@pytest.mark.parametrize("claim", [
    "We both studied at University of Zzqx, so I thought I would reach out.",
    "It was great to meet you at the careers fair last week.",
    "A mutual friend suggested I contact you.",
    "I remember when we worked together at the bank.",
    "I enjoyed your lectures on statistics.",
])
def test_no_connection_yet_means_no_claimed_connection(model, claim):
    calls = model({"body": f"{claim} {CHAT_BODY}"}, {"body": CHAT_BODY})
    assert claim not in draft("chat_request", relationship="none")["message"]
    assert len(calls) == 2


def test_an_alumnus_may_be_called_a_fellow_graduate_but_not_someone_met(model):
    fellow = f"As a fellow University of Zzqx graduate, I would value your view. {CHAT_BODY}"
    model({"body": fellow})
    assert fellow in draft("chat_request", relationship="alumni", university="University of Zzqx")["message"]
    calls = model({"body": f"We met at the fair. {CHAT_BODY}"}, {"body": CHAT_BODY})
    draft("chat_request", relationship="alumni", university="University of Zzqx")
    assert len(calls) == 2


def test_a_thank_you_may_say_it_was_good_to_meet(model):
    body = "It was great to meet you today. Hearing how your analytics team tests its dbt models was really useful."
    model({"body": body})
    assert body in draft("thank_you", learned="how the analytics team tests its dbt models")["message"]


def test_a_supervisor_may_mention_working_together(model):
    body = ("I hope you are well. I enjoyed working with you on the inventory project and wondered whether you would be "
            "willing to act as a referee for graduate analyst roles.")
    model({"body": body})
    assert body in draft("reference_ask", relationship="supervisor")["message"]


@pytest.mark.parametrize("bad", [
    "I will need visa sponsorship for this role.",                      # visas are never sent, so never mentioned
    "I can start in March.",                                            # a month not in the inputs
    "I have 7 years of experience in analytics.",                      # a figure not in the inputs
    "You can see my work at www.zzqx-portfolio.com.",                  # a web address
    "I worked at [Company] on data projects.",                         # a placeholder
])
def test_nothing_invented_and_no_visa_talk(model, bad):
    calls = model({"body": f"{CHAT_BODY} {bad}"}, {"body": CHAT_BODY})
    assert bad not in draft("chat_request")["message"]
    assert len(calls) == 2


def test_the_model_never_sees_names_or_notes(model):
    calls = model({"body": CHAT_BODY})
    draft("chat_request")
    prompt = calls[0]["system"] + calls[0]["user"]
    assert "Priya" not in prompt and "Shah" not in prompt and "brother" not in prompt and "Test Person" not in prompt
    assert "Data Analyst" in prompt and "Zzqx Holdings" in prompt and "no connection" in prompt.lower()


def test_greetings_and_sign_offs_are_written_by_code(model):
    model({"body": f"Dear Priya,\n\n{CHAT_BODY}\n\nBest wishes"})
    assert draft("chat_request")["message"] == f"Hi Priya,\n\n{CHAT_BODY}\n\nBest wishes,\nTest Person"


def test_a_title_is_skipped_in_hi_and_kept_in_dear(model):
    model({"body": CHAT_BODY})
    assert draft("chat_request", contact=contact(name="Dr Priya Shah"))["message"].startswith("Hi Priya,\n")
    body = "I hope you are well. Would you be willing to act as an academic referee for graduate analyst roles?"
    model({"body": body})
    message = draft("reference_ask", contact=contact("tutor", name="Dr Priya Shah"))["message"]
    assert message.startswith("Dear Dr Shah,\n") and message.endswith("Kind regards,\nTest Person")


def test_em_dashes_become_commas(model):
    model({"body": CHAT_BODY.replace("analyst. Would", "analyst — would")})
    assert "—" not in draft("chat_request")["message"]


# ---------- event preparation ----------

EVENT = {"name": "Zzqx Data Meetup", "type": "meetup", "online": False}
OPENERS = ["What brought you here tonight?", "Which talk are you most looking forward to?", "How long have you worked in data?"]
GOAL = "Talk to two people and ask each who else you should meet."


def intro(n: int) -> str:
    return " ".join(["I", "am", "studying", "data", "science"] + ["word"] * (n - 5)) + "."


def test_event_preparation(model):
    calls = model({"introduction": intro(60), "openers": OPENERS, "goal": GOAL})
    prep = ai.event_prep(event=EVENT, about_me=ABOUT)
    assert prep == {"introduction": intro(60), "openers": OPENERS, "goal": GOAL}
    assert "Zzqx Data Meetup" in calls[0]["user"] and "Meetup" in calls[0]["user"]


@pytest.mark.parametrize("bad", [
    {"introduction": intro(29)},                                   # too short for 30 seconds
    {"introduction": intro(91)},                                   # too long
    {"introduction": intro(40) + " I have managed 12 people."},   # a figure not in the pitch
    {"openers": OPENERS[:2]},                                      # not three
    {"goal": ""},
])
def test_event_preparation_is_checked(model, bad):
    good = {"introduction": intro(60), "openers": OPENERS, "goal": GOAL}
    calls = model(good | bad, good | bad)
    with pytest.raises(ai.AIError):
        ai.event_prep(event=EVENT, about_me=ABOUT)
    assert len(calls) == 2
