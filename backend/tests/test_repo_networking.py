"""Contacts, their pipeline steps, saved events and the referral link to applications in the
database. Every function filters by the caller: user B can neither read nor change user A's rows."""
from datetime import date, datetime, timezone

import pytest

import repo

pytestmark = pytest.mark.db


def person(conn, user, **kw):
    return repo.add_contact(conn, user, {"name": "Zzqx Priya Shah", "relationship": "alumni"} | kw)


def saved_event(conn, user, **kw):
    return repo.add_networking_event(conn, user, {"name": "Zzqx Data Meetup", "starts_at": datetime(2026, 10, 20, 18, 30), "type": "meetup"} | kw)


# ---------- contacts ----------

def test_add_and_list_contacts_oldest_first(conn, user_a):
    first = person(conn, user_a, role="Data Analyst", company="Zzqx Holdings", link="https://www.linkedin.com/in/zzqx")
    second = person(conn, user_a, name="Zzqx Sam")
    conn.execute("update contacts set created_at = created_at - interval '1 minute' where id = %s", (first["id"],))  # one transaction, one now()
    assert (first["status"], first["role"], first["company"], first["link"]) == ("to_contact", "Data Analyst", "Zzqx Holdings",
                                                                                "https://www.linkedin.com/in/zzqx")
    assert [c["id"] for c in repo.list_contacts(conn, user_a)] == [first["id"], second["id"]]


def test_update_contact_changes_only_the_fields_given(conn, user_a):
    contact = person(conn, user_a, role="Analyst", notes="Met at the careers fair")
    updated = repo.update_contact(conn, user_a, contact["id"], {"company": "Zzqx Works"})
    assert (updated["role"], updated["company"], updated["notes"]) == ("Analyst", "Zzqx Works", "Met at the careers fair")


def test_another_user_cannot_read_or_change_a_contact(conn, user_a, user_b):
    contact = person(conn, user_a)
    assert repo.get_contact(conn, user_b, contact["id"]) is None
    assert repo.list_contacts(conn, user_b) == []
    assert repo.update_contact(conn, user_b, contact["id"], {"name": "Changed"}) is None
    assert repo.record_outreach(conn, user_b, contact["id"], "sent", "chat_request") is None
    assert repo.delete_contact(conn, user_b, contact["id"]) is False
    assert repo.list_outreach(conn, user_b) == [] and repo.list_outreach(conn, user_a) == []
    assert repo.get_contact(conn, user_a, contact["id"])["name"] == "Zzqx Priya Shah"


def test_a_contact_can_be_linked_only_to_the_users_own_event(conn, user_a, user_b):
    mine, theirs = saved_event(conn, user_a), saved_event(conn, user_b)
    assert person(conn, user_a, relationship="event", event_id=mine["id"])["event_id"] == mine["id"]
    assert person(conn, user_a, relationship="event", event_id=theirs["id"])["event_id"] is None
    contact = person(conn, user_a)
    assert repo.update_contact(conn, user_a, contact["id"], {"event_id": theirs["id"]})["event_id"] is None


def test_unknown_contact_fields_are_refused(conn, user_a):
    with pytest.raises(ValueError):
        repo.add_contact(conn, user_a, {"name": "Zzqx", "relationship": "none", "user_id": "someone"})


def test_delete_contact(conn, user_a):
    contact = person(conn, user_a)
    assert repo.delete_contact(conn, user_a, contact["id"]) is True
    assert repo.get_contact(conn, user_a, contact["id"]) is None


# ---------- the pipeline ----------

def test_a_message_marked_sent_twice_on_one_day_is_recorded_once(conn, user_a):
    contact = person(conn, user_a)
    first = repo.record_outreach(conn, user_a, contact["id"], "sent", "chat_request")
    again = repo.record_outreach(conn, user_a, contact["id"], "sent", "chat_request")
    assert first["status"] == again["status"] == "messaged"
    assert [(o["kind"], o["message_type"]) for o in repo.list_outreach(conn, user_a)] == [("sent", "chat_request")]


def test_a_step_only_moves_a_contact_forward(conn, user_a):
    contact = person(conn, user_a)
    repo.record_outreach(conn, user_a, contact["id"], "sent", "chat_request")
    assert repo.record_outreach(conn, user_a, contact["id"], "replied")["status"] == "replied"
    assert repo.record_outreach(conn, user_a, contact["id"], "sent", "thank_you")["status"] == "replied"
    assert len(repo.list_outreach(conn, user_a)) == 3


def test_a_status_set_back_by_hand_moves_forward_from_there(conn, user_a):
    contact = person(conn, user_a)
    repo.record_outreach(conn, user_a, contact["id"], "chat_done")
    repo.update_contact(conn, user_a, contact["id"], {"status": "messaged"})
    assert repo.record_outreach(conn, user_a, contact["id"], "replied")["status"] == "replied"


def test_outreach_carries_its_london_day(conn, user_a):
    contact = person(conn, user_a)
    repo.record_outreach(conn, user_a, contact["id"], "sent", "connection_note")
    [row] = repo.list_outreach(conn, user_a)
    assert row["on_day"] == repo.today(conn) and row["contact_id"] == contact["id"]


def test_messages_stay_counted_after_the_contact_is_deleted(conn, user_a):
    contact = person(conn, user_a)
    repo.record_outreach(conn, user_a, contact["id"], "sent", "chat_request")
    repo.delete_contact(conn, user_a, contact["id"])
    assert [(o["contact_id"], o["kind"]) for o in repo.list_outreach(conn, user_a)] == [(None, "sent")]


# ---------- saved events ----------

def test_an_event_time_is_london_time(conn, user_a):
    october = saved_event(conn, user_a)
    december = saved_event(conn, user_a, starts_at=datetime(2026, 12, 3, 18, 30))
    assert october["starts_at"] == datetime(2026, 10, 20, 17, 30, tzinfo=timezone.utc)
    assert december["starts_at"] == datetime(2026, 12, 3, 18, 30, tzinfo=timezone.utc)
    assert (october["on_day"], december["on_day"]) == (date(2026, 10, 20), date(2026, 12, 3))


def test_a_late_evening_event_keeps_its_london_day(conn, user_a):
    late = saved_event(conn, user_a, starts_at=datetime(2026, 10, 20, 23, 30))  # 22:30 UTC
    assert late["on_day"] == date(2026, 10, 20)
    assert repo.list_networking_events(conn, user_a)[0]["on_day"] == date(2026, 10, 20)


def test_events_soonest_first_and_updated_in_place(conn, user_a):
    later = saved_event(conn, user_a, starts_at=datetime(2026, 11, 2, 9, 0))
    sooner = saved_event(conn, user_a)
    assert [e["id"] for e in repo.list_networking_events(conn, user_a)] == [sooner["id"], later["id"]]
    moved = repo.update_networking_event(conn, user_a, later["id"], {"status": "going", "starts_at": datetime(2026, 10, 19, 9, 0)})
    assert (moved["status"], moved["on_day"]) == ("going", date(2026, 10, 19))
    assert repo.list_networking_events(conn, user_a)[0]["id"] == later["id"]


def test_event_preparation_is_saved_on_the_event(conn, user_a):
    event = saved_event(conn, user_a)
    prep = {"introduction": "I am a data student.", "openers": ["a", "b", "c"], "goal": "Meet two people."}
    assert repo.set_event_prep(conn, user_a, event["id"], prep)["prep"] == prep


def test_another_user_cannot_read_or_change_an_event(conn, user_a, user_b):
    event = saved_event(conn, user_a)
    assert repo.get_networking_event(conn, user_b, event["id"]) is None
    assert repo.list_networking_events(conn, user_b) == []
    assert repo.update_networking_event(conn, user_b, event["id"], {"name": "Changed"}) is None
    assert repo.set_event_prep(conn, user_b, event["id"], {"goal": "x"}) is None
    assert repo.delete_networking_event(conn, user_b, event["id"]) is False
    assert repo.get_networking_event(conn, user_a, event["id"])["name"] == "Zzqx Data Meetup"


def test_deleting_an_event_keeps_its_contacts(conn, user_a):
    event = saved_event(conn, user_a)
    contact = person(conn, user_a, relationship="event", event_id=event["id"])
    assert repo.delete_networking_event(conn, user_a, event["id"]) is True
    assert repo.get_contact(conn, user_a, contact["id"])["event_id"] is None


# ---------- the profile and goals ----------

def test_university_events_page(conn, user_a):
    repo.get_or_create_profile(conn, user_a, "Test Person")
    assert repo.set_university_events_url(conn, user_a, "https://careers.zzqx.ac.uk/events")["university_events_url"] == "https://careers.zzqx.ac.uk/events"
    assert repo.set_university_events_url(conn, user_a, None)["university_events_url"] is None


def test_goals_carry_the_outreach_target(conn, user_a):
    saved = repo.set_goal(conn, user_a, effective_from=date(2026, 10, 19), applications=5, practice=2, outreach=3)
    assert saved["outreach"] == 3
    assert repo.list_goals(conn, user_a)[0]["outreach"] == 3


# ---------- a referral recorded against an application ----------

APP = {"company": "Zzqx Holdings Ltd", "role": "Role A", "source": "LinkedIn"}


def test_linking_a_contact_who_offered_a_referral_makes_the_source_referral(conn, user_a):
    contact = person(conn, user_a, status="referral_offered")
    added = repo.add_application(conn, user_a, APP | {"contact_id": contact["id"]})
    assert (added["contact_id"], added["source"], added["contact_name"]) == (contact["id"], "Referral", "Zzqx Priya Shah")
    other = repo.add_application(conn, user_a, APP)
    updated = repo.update_application(conn, user_a, other["id"], {"contact_id": contact["id"]})
    assert (updated["source"], updated["contact_name"]) == ("Referral", "Zzqx Priya Shah")


def test_linking_any_other_contact_copies_only_the_name(conn, user_a):
    contact = person(conn, user_a, name="Zzqx Sam", status="replied")
    application = repo.add_application(conn, user_a, APP | {"contact_name": "Someone Else"})
    updated = repo.update_application(conn, user_a, application["id"], {"contact_id": contact["id"]})
    assert (updated["source"], updated["contact_name"]) == ("LinkedIn", "Zzqx Sam")


def test_unlinking_keeps_the_name_and_source(conn, user_a):
    contact = person(conn, user_a, status="referral_offered")
    application = repo.add_application(conn, user_a, APP | {"contact_id": contact["id"]})
    updated = repo.update_application(conn, user_a, application["id"], {"contact_id": None})
    assert (updated["contact_id"], updated["source"], updated["contact_name"]) == (None, "Referral", "Zzqx Priya Shah")


def test_another_users_contact_cannot_be_linked(conn, user_a, user_b):
    theirs = person(conn, user_b, status="referral_offered")
    added = repo.add_application(conn, user_a, APP | {"contact_id": theirs["id"]})
    assert (added["contact_id"], added["source"], added["contact_name"]) == (None, "LinkedIn", None)


def test_state_carries_contacts_events_and_outreach(conn, user_a):
    contact = person(conn, user_a)
    repo.record_outreach(conn, user_a, contact["id"], "sent", "chat_request")
    saved_event(conn, user_a)
    state = repo.load_state(conn, user_a)
    assert (len(state["contacts"]), len(state["networking_events"]), len(state["outreach"])) == (1, 1, 1)
