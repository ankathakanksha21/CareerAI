"""Company research (shared by everyone) and prep packs (one user's)."""
import pytest

import repo

pytestmark = pytest.mark.db

KEY = "ch:ZZ000001|zzqx-never-real.test"  # cannot be a real company number
FACTS = [{"id": "f1", "section": "what_they_do", "text": "Zzqx builds things.", "quote": "", "url": "https://zzqx.test/",
          "source_title": "Zzqx", "kind": "website", "published_on": None}]


def save(conn, key=KEY, **kw):
    fields = {"name": "Zzqx Holdings Ltd", "company_number": "ZZ000001", "website": "https://zzqx-never-real.test/",
              "registry": None, "facts": FACTS, "missing": []} | kw
    return repo.save_company(conn, key, **fields)


def age(conn, company_id, days: int):
    conn.execute("update companies set researched_at = now() - make_interval(days => %s) where id = %s", (days, company_id))


def test_company_found_within_14_days_not_after(conn):
    company = save(conn)
    assert repo.find_company(conn, KEY, 14)["id"] == company["id"]
    age(conn, company["id"], 13)
    assert repo.find_company(conn, KEY, 14)["id"] == company["id"]
    age(conn, company["id"], 15)
    assert repo.find_company(conn, KEY, 14) is None


def test_unknown_key_finds_nothing(conn):
    assert repo.find_company(conn, KEY + "x", 14) is None


def test_save_company_replaces_in_place(conn):
    first = save(conn)
    age(conn, first["id"], 20)
    again = save(conn, facts=[], missing=["the news search"], registry={"number": "ZZ000001", "incorporated_on": "2004-03-12"})
    assert again["id"] == first["id"]
    assert (again["facts"], again["missing"], again["registry"]["incorporated_on"]) == ([], ["the news search"], "2004-03-12")
    assert repo.find_company(conn, KEY, 14)["id"] == first["id"]  # fresh again


def test_get_company(conn):
    company = save(conn)
    assert repo.get_company(conn, company["id"])["facts"] == FACTS
    assert repo.get_company(conn, "00000000-0000-0000-0000-000000000000") is None


def age_hours(conn, company_id, hours: float):
    conn.execute("update companies set researched_at = now() - make_interval(secs => %s) where id = %s", (hours * 3600, company_id))


def find(conn):
    return repo.find_company(conn, KEY, 14, transient=["the news search", "Companies House"], retry_hours=1)


def test_research_missing_a_source_for_a_moment_is_kept_for_an_hour(conn):
    company = save(conn, missing=["the news search"])
    age_hours(conn, company["id"], 0.5)
    assert find(conn)["id"] == company["id"]
    age_hours(conn, company["id"], 2)
    assert find(conn) is None


def test_research_missing_a_source_for_good_is_kept_14_days(conn):
    company = save(conn, missing=["their website, which asks automated readers not to read it"])
    age_hours(conn, company["id"], 24 * 13)
    assert find(conn)["id"] == company["id"]


# ---------- packs ----------

def application(conn, user):
    return repo.add_application(conn, user, {"company": "Zzqx", "role": "Zzqx Analyst", "source": "Company site"})


def job(conn, user):
    return repo.add_job(conn, user, title="Zzqx Analyst", company="Zzqx", location=None, url=None, description="d" * 40,
                        summary="s", keywords=[], role_family_id=None)


def pack(conn, user, **kw):
    fields = {"saved_job_id": None, "application_id": None, "company_id": None, "role": "Zzqx Analyst", "company": "Zzqx",
              "content": {"pitch": "p", "pitch_edited": False, "ticked": []}} | kw
    return repo.save_pack(conn, user, **fields)


def test_two_edits_made_from_the_same_old_copy_both_survive(conn, user_a):
    made = pack(conn, user_a, application_id=application(conn, user_a)["id"])
    repo.merge_pack_content(conn, user_a, made["id"], {"pitch": "Mine.", "pitch_edited": True})
    repo.merge_pack_content(conn, user_a, made["id"], {"ticked": [1]})
    assert repo.get_pack(conn, user_a, made["id"])["content"] == {"pitch": "Mine.", "pitch_edited": True, "ticked": [1]}


def test_merging_touches_only_ones_own_pack(conn, user_a, user_b):
    made = pack(conn, user_a, application_id=application(conn, user_a)["id"])
    assert repo.merge_pack_content(conn, user_b, made["id"], {"pitch": "Taken over."}) is None
    assert repo.get_pack(conn, user_a, made["id"])["content"]["pitch"] == "p"


def test_find_pack_can_lock_the_row(conn, user_a):
    made = pack(conn, user_a, application_id=application(conn, user_a)["id"])
    assert repo.find_pack(conn, user_a, application_id=made["application_id"], lock=True)["id"] == made["id"]


def test_save_pack_stores_another_users_job_or_application_as_null(conn, user_a, user_b):
    made = pack(conn, user_a, saved_job_id=job(conn, user_b)["id"], application_id=application(conn, user_b)["id"])
    assert (made["saved_job_id"], made["application_id"]) == (None, None)


def test_an_applications_pack_is_kept_when_its_job_is_linked_later(conn, user_a):
    app = application(conn, user_a)
    first = pack(conn, user_a, application_id=app["id"])
    j = job(conn, user_a)
    again = pack(conn, user_a, saved_job_id=j["id"], application_id=app["id"])
    assert again["id"] == first["id"] and again["saved_job_id"] == j["id"]
    repo.delete_job(conn, user_a, j["id"])  # once answered 500: two job-less packs for one application
    assert [p["id"] for p in repo.list_packs(conn, user_a)] == [first["id"]]
