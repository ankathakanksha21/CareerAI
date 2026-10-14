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
