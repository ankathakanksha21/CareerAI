"""Networking through the API: contacts and their pipeline, drafts, saved events, search links,
the university events page, and what the state read carries. The model is replaced; the names
cannot be real."""
import uuid
from datetime import date, datetime, timedelta

import pytest

import ai
import repo

pytestmark = pytest.mark.db

GONE = "That item no longer exists"
LIMIT = "You've reached today's limit. It resets at midnight."
AI_FAILED = "The AI did not respond properly. Try again."
NO_JOB = "Save the job you want a referral for first."
NOTHING_LEARNED = "Write one thing you learned in the chat, so the thank-you can mention it."
NOT_A_REFEREE = "Ask a tutor, lecturer or supervisor for a reference."
BAD_LINK = "Enter a web address, for example linkedin.com/in/their-name."
BAD_EVENTS_PAGE = "Enter your university's careers events page, for example careers.youruni.ac.uk/events."
PERSON = {"name": "Zzqx Priya Shah", "role": "Data Analyst", "company": "Zzqx Holdings Ltd", "relationship": "alumni"}
EVENT = {"name": "Zzqx Data Meetup", "starts_at": "2026-10-20T18:30", "type": "meetup"}
DRAFT = {"message": "Hi Priya,\n\nWould you have 15 minutes?\n\nBest wishes,\nTest Person", "words": 4, "characters": 60}
PREP = {"introduction": "I am a data science student.", "openers": ["a?", "b?", "c?"], "goal": "Meet two people."}


def capture(monkeypatch, name: str, result) -> list:
    """Replace ai.<name>, recording the keyword arguments of each call."""
    calls = []

    def fake(*args, **kwargs):
        calls.append(kwargs)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(ai, name, fake)
    return calls


def add_person(client, **kw) -> dict:
    r = client.post("/api/contacts", json=PERSON | kw)
    assert r.status_code == 201, r.text
    return r.json()


def add_event(client, **kw) -> dict:
    r = client.post("/api/networking-events", json=EVENT | kw)
    assert r.status_code == 201, r.text
    return r.json()


def state(client) -> dict:
    return client.get("/api/state").json()


def usage(conn, user) -> int:
    return conn.execute("select count(*) as n from usage_events where user_id = %s and kind = 'ai'", (user,)).fetchone()["n"]


def save_job(conn, user, company="ZZQX HOLDINGS LIMITED") -> str:
    return repo.add_job(conn, user, title="Zzqx Analyst", company=company, location="Leeds", url="https://www.reed.co.uk/jobs/1",
                        description="Reporting role.", summary="Reporting role.", keywords=[], role_family_id=None)["id"]


# ---------- the standing rules ----------

ID = uuid.uuid4()
ROUTES = [("get", "/api/contacts"), ("post", "/api/contacts"), ("patch", f"/api/contacts/{ID}"), ("delete", f"/api/contacts/{ID}"),
          ("post", f"/api/contacts/{ID}/events"), ("post", "/api/ai/outreach"), ("get", "/api/networking-events"),
          ("post", "/api/networking-events"), ("patch", f"/api/networking-events/{ID}"), ("delete", f"/api/networking-events/{ID}"),
          ("post", f"/api/ai/networking-events/{ID}/prepare"), ("get", "/api/networking/links"), ("put", "/api/profile/events-url")]


@pytest.mark.parametrize("method, path", ROUTES)
def test_every_route_needs_a_login(method, path):
    from fastapi.testclient import TestClient

    import main
    assert getattr(TestClient(main.app), method)(path).status_code == 401


@pytest.mark.parametrize("method, path", [("patch", "/api/contacts/x"), ("delete", "/api/contacts/x"), ("post", "/api/contacts/x/events"),
                                          ("patch", "/api/networking-events/x"), ("delete", "/api/networking-events/x"),
                                          ("post", "/api/ai/networking-events/x/prepare")])
def test_malformed_ids_are_422(client, method, path):
    kwargs = {"json": {"kind": "replied"}} if method in ("patch", "post") else {}
    assert getattr(client, method)(path, **kwargs).status_code == 422


def test_another_user_cannot_read_change_record_or_draft_for_a_contact(client, as_user, user_b, monkeypatch):
    person = add_person(client)
    event = add_event(client)
    drafts, preps = capture(monkeypatch, "outreach_draft", DRAFT), capture(monkeypatch, "event_prep", PREP)
    as_user(user_b)
    assert client.get("/api/contacts").json() == []
    assert client.get("/api/networking-events").json() == []
    for r in (client.patch(f"/api/contacts/{person['id']}", json={"name": "Changed"}),
              client.post(f"/api/contacts/{person['id']}/events", json={"kind": "replied"}),
              client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "chat_request"}),
              client.delete(f"/api/contacts/{person['id']}"),
              client.patch(f"/api/networking-events/{event['id']}", json={"name": "Changed"}),
              client.post(f"/api/ai/networking-events/{event['id']}/prepare"),
              client.delete(f"/api/networking-events/{event['id']}")):
        assert r.status_code == 404 and r.json()["detail"] == GONE
    assert drafts == [] and preps == []


# ---------- contacts and the pipeline ----------

def test_add_a_contact_and_see_what_to_do_next(client):
    person = add_person(client, link="www.linkedin.com/in/zzqx-priya")
    assert (person["status"], person["link"], person["next"]["text"]) == ("to_contact", "https://www.linkedin.com/in/zzqx-priya",
                                                                          "Send a first message")
    assert len(person["chat_questions"]) == 3 and person["history"] == []
    assert [c["id"] for c in client.get("/api/contacts").json()] == [person["id"]]


@pytest.mark.parametrize("link", ["javascript:alert(1)", "http://localhost/x", "not a link"])
def test_an_unsafe_profile_link_is_refused(client, link):
    r = client.post("/api/contacts", json=PERSON | {"link": link})
    assert r.status_code == 422 and BAD_LINK in r.text


def test_no_email_or_phone_is_taken(client):
    person = add_person(client, email="zzqx@example.test", phone="07000 000000")
    assert "email" not in person and "phone" not in person


def test_marking_a_message_sent_twice_counts_once(client):
    person = add_person(client)
    for _ in range(2):
        r = client.post(f"/api/contacts/{person['id']}/events", json={"kind": "sent", "message_type": "chat_request"})
        assert r.status_code == 200 and r.json()["status"] == "messaged"
    assert state(client)["habits"]["this_week"]["outreach"] == 1


def test_a_message_sent_without_a_draft_is_the_users_own(client):
    person = add_person(client)
    after = client.post(f"/api/contacts/{person['id']}/events", json={"kind": "sent"}).json()
    assert after["history"][0]["message_type"] == "own"


def test_a_reply_moves_a_contact_on_and_a_thank_you_does_not_move_them_back(client):
    person = add_person(client)
    client.post(f"/api/contacts/{person['id']}/events", json={"kind": "chat_done"})
    after = client.post(f"/api/contacts/{person['id']}/events", json={"kind": "sent", "message_type": "thank_you"}).json()
    assert after["status"] == "chat_done" and after["next"]["text"].startswith("Stay in touch")


def test_a_status_can_be_corrected_by_hand(client):
    person = add_person(client)
    client.post(f"/api/contacts/{person['id']}/events", json={"kind": "replied"})
    assert client.patch(f"/api/contacts/{person['id']}", json={"status": "messaged"}).json()["status"] == "messaged"


def test_deleting_a_contact_keeps_the_application_and_the_week(client):
    person = add_person(client, relationship="none")
    client.post(f"/api/contacts/{person['id']}/events", json={"kind": "sent", "message_type": "chat_request"})
    application = client.post("/api/applications", json={"company": "Zzqx Holdings Ltd", "role": "Analyst", "source": "LinkedIn",
                                                          "contact_id": person["id"]}).json()
    assert client.delete(f"/api/contacts/{person['id']}").status_code == 204
    s = state(client)
    assert s["contacts"] == [] and s["habits"]["this_week"]["outreach"] == 1
    assert next(a for a in s["applications"] if a["id"] == application["id"])["contact_id"] is None


def test_linking_a_referral_sets_the_source(client):
    person = add_person(client)
    client.post(f"/api/contacts/{person['id']}/events", json={"kind": "referral_offered"})
    application = client.post("/api/applications", json={"company": "Zzqx Holdings Ltd", "role": "Analyst", "source": "LinkedIn"}).json()
    linked = client.patch(f"/api/applications/{application['id']}", json={"contact_id": person["id"]}).json()
    assert (linked["source"], linked["contact_name"], linked["contact_id"]) == ("Referral", "Zzqx Priya Shah", person["id"])


# ---------- drafts ----------

def test_a_draft_counts_one_ai_action_and_sends_no_name(client, conn, user_a, monkeypatch):
    calls = capture(monkeypatch, "outreach_draft", DRAFT)
    person = add_person(client)
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "chat_request"})
    assert r.status_code == 200 and r.json() == DRAFT
    assert usage(conn, user_a) == 1
    [call] = calls
    assert call["kind"] == "chat_request" and call["sender"] == "Test Person" and call["contact"]["relationship"] == "alumni"
    assert "Test Person" not in call["about_me"]


def test_the_daily_limit_applies_to_drafts_and_preparation(client, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    drafts, preps = capture(monkeypatch, "outreach_draft", DRAFT), capture(monkeypatch, "event_prep", PREP)
    person, event = add_person(client), add_event(client)
    for r in (client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "chat_request"}),
              client.post(f"/api/ai/networking-events/{event['id']}/prepare")):
        assert r.status_code == 429 and r.json()["detail"] == LIMIT
    assert drafts == [] and preps == [] and client.get("/api/networking-events").json()[0]["prep"] is None


def test_a_failed_draft_is_an_error_with_retry(client, monkeypatch):
    capture(monkeypatch, "outreach_draft", ai.AIError("outreach"))
    person = add_person(client)
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "chat_request"})
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED


def test_a_thank_you_needs_what_was_learned(client, conn, user_a, monkeypatch):
    calls = capture(monkeypatch, "outreach_draft", DRAFT)
    person = add_person(client)
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "thank_you", "learned": "  "})
    assert r.status_code == 422 and r.json()["detail"] == NOTHING_LEARNED
    assert calls == [] and usage(conn, user_a) == 0


def test_a_reference_is_asked_only_of_a_tutor_or_supervisor(client, monkeypatch):
    capture(monkeypatch, "outreach_draft", DRAFT)
    stranger, tutor = add_person(client, relationship="none"), add_person(client, relationship="tutor")
    r = client.post("/api/ai/outreach", json={"contact_id": stranger["id"], "type": "reference_ask"})
    assert r.status_code == 422 and r.json()["detail"] == NOT_A_REFEREE
    assert client.post("/api/ai/outreach", json={"contact_id": tutor["id"], "type": "reference_ask"}).status_code == 200


def test_a_referral_ask_needs_a_saved_job_at_their_company(client, conn, user_a, monkeypatch):
    calls = capture(monkeypatch, "outreach_draft", DRAFT)
    person = add_person(client)
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "referral_ask"})
    assert r.status_code == 422 and r.json()["detail"] == NO_JOB
    elsewhere = save_job(conn, user_a, company="Zzqx Other Plc")
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "referral_ask", "job_id": elsewhere})
    assert r.status_code == 422 and r.json()["detail"] == NO_JOB
    same = save_job(conn, user_a)  # "ZZQX HOLDINGS LIMITED" is the contact's "Zzqx Holdings Ltd"
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "referral_ask", "job_id": same})
    assert r.status_code == 200 and calls[0]["job"]["url"] == "https://www.reed.co.uk/jobs/1"


def test_another_users_job_cannot_be_used_for_a_referral(client, conn, user_b, monkeypatch):
    capture(monkeypatch, "outreach_draft", DRAFT)
    person = add_person(client)
    theirs = save_job(conn, user_b)
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "referral_ask", "job_id": theirs})
    assert r.status_code == 422 and r.json()["detail"] == NO_JOB


def test_a_recruiter_introduction_gets_the_start_date_and_target_roles(client, monkeypatch):
    calls = capture(monkeypatch, "outreach_draft", DRAFT)
    person = add_person(client, relationship="recruiter")
    client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": "recruiter_intro", "start": "from 2 November"})
    assert calls[0]["start"] == "from 2 November" and isinstance(calls[0]["looking_for"], list)


def test_only_the_event_name_of_someone_met_there_is_sent(client, monkeypatch):
    calls = capture(monkeypatch, "outreach_draft", DRAFT)
    event = add_event(client)
    met = add_person(client, relationship="event", event_id=event["id"])
    client.post("/api/ai/outreach", json={"contact_id": met["id"], "type": "chat_request"})
    assert calls[0]["event_name"] == "Zzqx Data Meetup"


# ---------- saved events ----------

def test_save_an_event_and_prepare_for_it(client, conn, user_a, monkeypatch):
    calls = capture(monkeypatch, "event_prep", PREP)
    event = add_event(client, online=True, link="www.meetup.com/zzqx-data/events/1")
    assert (event["status"], event["link"], event["on_day"]) == ("interested", "https://www.meetup.com/zzqx-data/events/1", "2026-10-20")
    prepared = client.post(f"/api/ai/networking-events/{event['id']}/prepare")
    assert prepared.status_code == 200 and prepared.json()["prep"] == PREP
    assert usage(conn, user_a) == 1 and calls[0]["event"]["name"] == "Zzqx Data Meetup"
    assert client.get("/api/networking-events").json()[0]["prep"] == PREP


def test_an_event_can_be_moved_and_marked_attended(client):
    event = add_event(client)
    moved = client.patch(f"/api/networking-events/{event['id']}", json={"status": "attended", "starts_at": "2026-10-21T09:00"}).json()
    assert (moved["status"], moved["on_day"]) == ("attended", "2026-10-21")


def test_deleting_an_event_keeps_the_people_met_there(client):
    event = add_event(client)
    met = add_person(client, relationship="event", event_id=event["id"])
    assert client.delete(f"/api/networking-events/{event['id']}").status_code == 204
    assert client.get("/api/contacts").json()[0]["id"] == met["id"]


def test_coming_up_keeps_today_and_drops_yesterday(client, conn):
    today = repo.today(conn)
    tonight = add_event(client, name="Zzqx Tonight", starts_at=f"{today}T23:30", status="going")
    add_event(client, name="Zzqx Yesterday", starts_at=f"{today - timedelta(days=1)}T18:00")
    add_event(client, name="Zzqx Done", starts_at=f"{today + timedelta(days=2)}T18:00", status="attended")
    assert [e["id"] for e in state(client)["coming_up"]] == [tonight["id"]]


# ---------- links and the university page ----------

def test_search_links_come_from_the_profile(client):
    r = client.put("/api/profile/events-url", json={"url": "careers.zzqx.ac.uk/events"})
    assert r.status_code == 200 and r.json()["university_events_url"] == "https://careers.zzqx.ac.uk/events"
    links = client.get("/api/networking/links").json()
    assert links["university"] == {"label": "Your university's careers events", "url": "https://careers.zzqx.ac.uk/events"}
    assert set(links) == {"people", "meetup", "eventbrite", "university", "bodies"}


def test_an_unsafe_events_page_is_refused_and_an_empty_one_clears_it(client):
    r = client.put("/api/profile/events-url", json={"url": "javascript:alert(1)"})
    assert r.status_code == 422 and BAD_EVENTS_PAGE in r.text
    assert client.put("/api/profile/events-url", json={"url": ""}).json()["university_events_url"] is None


# ---------- the outreach target ----------

def test_a_new_account_has_a_target_of_two_messages(client):
    week = state(client)["habits"]["this_week"]
    assert (week["goal"]["outreach"], week["outreach_chosen"]) == (2, False)


def test_an_account_from_before_this_step_starts_at_zero(client, conn, user_a):
    state(client)
    conn.execute("update profiles set outreach_default = 0 where user_id = %s", (user_a,))
    week = state(client)["habits"]["this_week"]
    assert (week["goal"]["outreach"], week["outreach_chosen"], week["met"]) == (0, False, False)


def test_an_outreach_target_is_saved_with_the_goals(client, conn):
    r = client.put("/api/profile/goals", json={"applications": 1, "practice": 0, "outreach": 3})
    assert r.status_code == 200 and r.json()["goal"] == {"applications": 1, "practice": 0, "outreach": 3}
    week = state(client)["habits"]["this_week"]
    assert (week["goal"]["outreach"], week["outreach_chosen"]) == (3, True)
    assert client.put("/api/profile/goals", json={"applications": 1, "practice": 0, "outreach": 21}).status_code == 422


def test_the_state_carries_the_networking_rows_and_options(client):
    person = add_person(client)
    add_event(client)
    s = state(client)
    assert s["contacts"][0]["id"] == person["id"] and s["contacts"][0]["next"]["text"] == "Send a first message"
    assert len(s["networking_events"]) == 1 and "outreach" not in s
    assert {"relationships", "contact_statuses", "message_types", "event_types", "event_statuses"} <= set(s["options"])
    assert any(t["id"] == "outreach" for t in s["plan"])  # two messages to send, and Priya to message


def test_a_reference_request_gets_the_target_roles(client, conn, user_a, monkeypatch):
    calls = capture(monkeypatch, "outreach_draft", DRAFT)
    [family] = repo.sync_families(conn, user_a, [{"name": "Zzqx Analyst", "fit": "direct", "overlap": 80, "uk_titles": [], "why": "", "needs": []}])
    repo.set_family_targeted(conn, user_a, family["id"], True)
    tutor = add_person(client, relationship="tutor")
    client.post("/api/ai/outreach", json={"contact_id": tutor["id"], "type": "reference_ask"})
    assert calls[0]["looking_for"] == ["Zzqx Analyst"]



# ---------- the final review ----------

NO_VISA_OR_ADDRESS = "Leave out visas, sponsorship and web addresses: a draft never mentions them."


@pytest.mark.parametrize("field, value", [("start", "Now, Graduate visa, no sponsorship needed"), ("start", "see www.zzqx.example.com"),
                                          ("learned", "how their visa sponsorship works")])
def test_typed_text_a_draft_can_never_use_is_refused_before_an_ai_action(client, conn, user_a, monkeypatch, field, value):
    calls = capture(monkeypatch, "outreach_draft", DRAFT)
    person = add_person(client, relationship="recruiter")
    kind = "recruiter_intro" if field == "start" else "thank_you"
    r = client.post("/api/ai/outreach", json={"contact_id": person["id"], "type": kind, field: value})
    assert r.status_code == 422 and r.json()["detail"] == NO_VISA_OR_ADDRESS
    assert calls == [] and usage(conn, user_a) == 0
