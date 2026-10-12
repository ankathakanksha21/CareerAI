"""Shared listings and each user's private matches. The database these tests use also holds the
real register and real listings, so every value here is one that cannot occur in real data."""
from datetime import date, timedelta

import pytest

import repo
import sponsors

pytestmark = pytest.mark.db

TODAY = date.today()
SEARCH = ("zzqx role", "zzqx town")
SINCE = TODAY - timedelta(days=14)


def listing(n, **changes):
    return {"source": "reed", "source_id": f"zzqx-{n}", "title": f"Role {n}", "employer": "Zzqx Holdings Ltd", "employer_key": "zzqx",
            "posted_by": "employer", "location": "Zzqx Town", "salary_min": 28000, "salary_max": 32000, "salary_annual": True,
            "description": f"Short text {n}", "description_is_full": False, "url": f"https://www.reed.co.uk/jobs/{n}",
            "posted_on": TODAY} | changes


def register(conn, *names):
    for r in sponsors.with_keys([{"name": n, "town": "", "county": "", "route": "Skilled Worker", "rating": ""} for n in names]):
        conn.execute("insert into sponsors (name, name_key, route) values (%s, %s, %s)", (r["name"], r["name_key"], r["route"]))


def family(conn, user_id, name="Zzqx Analyst", targeted=True):
    fam = repo.sync_families(conn, user_id, [{"name": name, "fit": "direct", "overlap": 80, "uk_titles": ["Zzqx Role"]}])
    fam = next(f for f in fam if f["name"] == name)
    return repo.set_family_targeted(conn, user_id, fam["id"], targeted)["id"]


def stored(conn, *listings, search=SEARCH):
    """Store listings under one search; returns their ids in order."""
    return repo.store_searches(conn, {search: list(listings)})[search]


def matched(conn, user_id, *listings, family_id=None, location="zzqx town"):
    ids = stored(conn, *listings)
    repo.add_matches(conn, user_id, [{"listing_id": i, "role_family_id": family_id, "search_location": location} for i in ids])
    return [m["id"] for i in ids for m in repo.list_matches(conn, user_id, SINCE) if m["listing_id"] == i]


def row(conn, listing_id):
    return conn.execute("select * from job_listings where id = %s", (listing_id,)).fetchone()


# ---------- the shared search cache ----------

def test_a_search_is_due_until_stored_then_fresh_for_six_hours(conn):
    other = ("zzqx other", "zzqx town")
    assert repo.searches_due(conn, [SEARCH, other], 6) == {SEARCH, other}
    stored(conn, listing(1))
    assert repo.searches_due(conn, [SEARCH, other], 6) == {other}
    conn.execute("update job_searches set fetched_at = now() - interval '5 hours 59 minutes' where query = %s", (SEARCH[0],))
    assert repo.searches_due(conn, [SEARCH], 6) == set()
    conn.execute("update job_searches set fetched_at = now() - interval '6 hours 1 minute' where query = %s", (SEARCH[0],))
    assert repo.searches_due(conn, [SEARCH], 6) == {SEARCH}


def test_no_searches_means_nothing_due(conn):
    assert repo.searches_due(conn, [], 6) == set()


def test_storing_again_updates_the_same_listing(conn):
    first = stored(conn, listing(1))
    again = stored(conn, listing(1, title="Role 1, retitled"))
    assert first == again and row(conn, first[0])["title"] == "Role 1, retitled"


def test_the_same_advert_twice_in_one_batch_is_stored_once(conn):
    ids = stored(conn, listing(1), listing(1, title="Duplicate"), listing(2))
    assert len(ids) == 2 and row(conn, ids[0])["title"] == "Role 1"


def test_a_full_advert_is_not_overwritten_by_the_short_search_text(conn):
    (listing_id,) = stored(conn, listing(1))
    repo.set_listing_details(conn, listing_id, {"description": "The whole advert", "description_is_full": True,
                                               "salary_min": 30000, "salary_max": 35000, "salary_annual": True})
    stored(conn, listing(1, description="Short again", salary_min=1, salary_max=2, salary_annual=False))
    kept = row(conn, listing_id)
    assert kept["description"] == "The whole advert" and kept["description_is_full"] is True
    assert (kept["salary_min"], kept["salary_max"], kept["salary_annual"]) == (30000, 35000, True)


def test_a_search_keeps_only_its_latest_results(conn, user_a):
    stored(conn, listing(1), listing(2))
    stored(conn, listing(2), listing(3))
    found = {x["title"] for x in repo.listings_for_searches(conn, [SEARCH], SINCE)}
    assert found == {"Role 2", "Role 3"}


def test_listings_for_searches_carry_the_search_and_skip_old_adverts(conn):
    stored(conn, listing(1), listing(2, posted_on=TODAY - timedelta(days=15)))
    found = repo.listings_for_searches(conn, [SEARCH, ("zzqx other", "zzqx town")], SINCE)
    assert [(x["title"], x["query"], x["search_location"]) for x in found] == [("Role 1", "zzqx role", "zzqx town")]
    assert {"id", "employer_key", "location", "posted_on"} <= set(found[0])


# ---------- what the register says, worked out when a listing is stored ----------

def test_a_new_listing_gets_its_sponsor_status(conn):
    register(conn, "Zzqx Holdings Ltd", "Qqzz Stores Limited")
    ids = stored(conn, listing(1), listing(2, employer="Qqzz", employer_key="qqzz"), listing(3, employer="Zzqy Nobody", employer_key="zzqy nobody"),
                 listing(4, posted_by="agency"))
    got = [(row(conn, i)["sponsor_status"], row(conn, i)["sponsor_name"]) for i in ids]
    assert got == [("listed", "Zzqx Holdings Ltd"), ("possible", "Qqzz Stores Limited"), ("not_found", None), ("agency", None)]


def test_storing_again_rechecks_against_the_register(conn):
    (listing_id,) = stored(conn, listing(1))
    assert row(conn, listing_id)["sponsor_status"] == "not_found"
    register(conn, "Zzqx Holdings Ltd")
    stored(conn, listing(1))
    assert row(conn, listing_id)["sponsor_status"] == "listed"


def test_checking_some_listings_leaves_the_others_alone(conn):
    register(conn, "Zzqx Holdings Ltd")
    ids = stored(conn, listing(1), listing(2))
    conn.execute("delete from sponsors where name = 'Zzqx Holdings Ltd'")
    repo.recheck_listing_sponsors(conn, [ids[0]])
    assert [row(conn, i)["sponsor_status"] for i in ids] == ["not_found", "listed"]


# ---------- old adverts ----------

def test_purge_removes_adverts_older_than_thirty_days_only(conn):
    ids = stored(conn, listing(1, posted_on=TODAY - timedelta(days=31)), listing(2, posted_on=TODAY - timedelta(days=30)))
    repo.purge_old_listings(conn)
    assert row(conn, ids[0]) is None and row(conn, ids[1]) is not None


# ---------- matches: private to each user ----------

def test_adding_matches_again_changes_nothing_and_hidden_stays_hidden(conn, user_a):
    ids = stored(conn, listing(1), listing(2))
    items = [{"listing_id": i, "role_family_id": None, "search_location": "zzqx town"} for i in ids]
    assert repo.add_matches(conn, user_a, items) == 2
    hidden = next(m for m in repo.list_matches(conn, user_a, SINCE) if m["listing_id"] == ids[0])
    assert repo.hide_match(conn, user_a, hidden["id"]) is True
    assert repo.add_matches(conn, user_a, items) == 0
    assert [m["listing_id"] for m in repo.list_matches(conn, user_a, SINCE)] == [ids[1]]


def test_two_users_share_a_listing_but_not_their_matches(conn, user_a, user_b):
    (mine,) = matched(conn, user_a, listing(1))
    (theirs,) = matched(conn, user_b, listing(1))
    assert mine != theirs
    assert repo.hide_match(conn, user_a, mine) is True
    assert repo.list_matches(conn, user_a, SINCE) == []
    seen_by_b = repo.list_matches(conn, user_b, SINCE)
    assert len(seen_by_b) == 1 and seen_by_b[0]["status"] == "new"


def test_another_user_cannot_read_hide_save_or_score_a_match(conn, user_a, user_b):
    (mine,) = matched(conn, user_a, listing(1))
    assert repo.get_match(conn, user_b, mine) is None
    assert repo.hide_match(conn, user_b, mine) is False
    assert repo.save_listing_as_job(conn, user_b, mine) is None
    repo.save_scores(conn, user_b, [{"match_id": mine, "fit": {"percent": 90, "label": "direct", "shown": [], "gaps": []}, "from_summary": False}])
    assert repo.mark_matches_seen(conn, user_b) == 0
    untouched = repo.get_match(conn, user_a, mine)
    assert untouched["status"] == "new" and untouched["fit_percent"] is None and untouched["scored_at"] is None
    assert repo.list_jobs(conn, user_b) == []


def test_a_match_cannot_point_at_another_users_role_family(conn, user_a, user_b):
    theirs = family(conn, user_b)
    (mine,) = matched(conn, user_a, listing(1), family_id=theirs)
    assert repo.get_match(conn, user_a, mine)["role_family_id"] is None


def test_list_matches_has_what_the_page_needs_newest_first(conn, user_a):
    fam = family(conn, user_a)
    matched(conn, user_a, listing(1, posted_on=TODAY - timedelta(days=3)), listing(2, description="x" * 500), family_id=fam)
    got = repo.list_matches(conn, user_a, SINCE)
    assert [m["title"] for m in got] == ["Role 2", "Role 1"]
    newest = got[0]
    assert len(newest["snippet"]) == 300 and "description" not in newest
    assert newest["role_family_id"] == fam and newest["search_location"] == "zzqx town" and newest["status"] == "new"
    assert (newest["salary_min"], newest["salary_max"], newest["salary_annual"]) == (28000, 32000, True)
    for key in ("employer", "location", "url", "posted_on", "posted_by", "source", "sponsor_status", "sponsor_name",
                "fit_percent", "fit_label", "shown", "gaps", "fit_from_summary", "description_is_full"):
        assert key in newest, key


def test_list_matches_leaves_out_old_adverts_and_untargeted_families(conn, user_a):
    on, off = family(conn, user_a, "Zzqx On"), family(conn, user_a, "Zzqx Off", targeted=False)
    matched(conn, user_a, listing(1), family_id=on)
    matched(conn, user_a, listing(2), family_id=off)
    matched(conn, user_a, listing(3, posted_on=TODAY - timedelta(days=15)), family_id=on)
    assert [m["title"] for m in repo.list_matches(conn, user_a, SINCE)] == ["Role 1"]


def test_scores_are_saved_on_the_users_own_match(conn, user_a):
    one, two = matched(conn, user_a, listing(1), listing(2))
    fit = {"percent": 67, "label": "near", "shown": [{"need": "SQL", "achievement": "Thing one"}], "gaps": ["Python"]}
    repo.save_scores(conn, user_a, [{"match_id": one, "fit": fit, "from_summary": True}, {"match_id": two, "fit": None, "from_summary": False}])
    scored = repo.get_match(conn, user_a, one)
    assert (scored["fit_percent"], scored["fit_label"], scored["fit_from_summary"]) == (67, "near", True)
    assert scored["shown"] == fit["shown"] and scored["gaps"] == ["Python"] and scored["scored_at"] is not None
    judged = repo.get_match(conn, user_a, two)  # nothing in the advert to judge: no score, but not asked again
    assert judged["fit_percent"] is None and judged["fit_label"] is None and judged["scored_at"] is not None
    assert repo.unscored_matches(conn, user_a, SINCE) == []


def test_unscored_matches_have_the_advert_text_and_skip_hidden(conn, user_a):
    one, two = matched(conn, user_a, listing(1), listing(2))
    repo.hide_match(conn, user_a, two)
    waiting = repo.unscored_matches(conn, user_a, SINCE)
    assert [w["match_id"] for w in waiting] == [one]
    assert {"listing_id", "source_id", "title", "employer", "description", "description_is_full", "posted_on"} <= set(waiting[0])


def test_marking_seen_changes_new_matches_only(conn, user_a):
    one, two, three = matched(conn, user_a, listing(1), listing(2), listing(3))
    repo.hide_match(conn, user_a, two)
    repo.save_listing_as_job(conn, user_a, three)
    assert repo.mark_matches_seen(conn, user_a) == 1
    assert repo.get_match(conn, user_a, one)["status"] == "seen"
    assert repo.get_match(conn, user_a, two)["status"] == "hidden" and repo.get_match(conn, user_a, three)["status"] == "saved"


# ---------- saving a listing as one of the user's jobs ----------

def test_saving_copies_the_listing_and_doing_it_twice_gives_the_same_job(conn, user_a):
    fam = family(conn, user_a)
    (match_id,) = matched(conn, user_a, listing(1, description="d" * 400), family_id=fam)
    job = repo.save_listing_as_job(conn, user_a, match_id)
    assert (job["title"], job["company"], job["location"], job["source"]) == ("Role 1", "Zzqx Holdings Ltd", "Zzqx Town", "reed")
    assert job["url"] == "https://www.reed.co.uk/jobs/1" and job["posted_on"] == TODAY and job["role_family_id"] == fam
    assert job["description"] == "d" * 400 and job["summary"] == "d" * 300 and job["keywords"] == []
    assert repo.get_match(conn, user_a, match_id)["status"] == "saved"
    assert repo.save_listing_as_job(conn, user_a, match_id)["id"] == job["id"]
    assert len(repo.list_jobs(conn, user_a)) == 1


def test_a_saved_job_survives_the_listing_being_deleted(conn, user_a):
    (match_id,) = matched(conn, user_a, listing(1))
    job = repo.save_listing_as_job(conn, user_a, match_id)
    conn.execute("delete from job_listings where id = %s", (job["listing_id"],))
    kept = repo.get_job(conn, user_a, job["id"])
    assert kept["title"] == "Role 1" and kept["listing_id"] is None


# ---------- counts for the menu, Home and the role family cards ----------

def scored(conn, user_id, match_id, percent):
    label = "direct" if percent >= 80 else "near" if percent >= 60 else "stretch" if percent >= 40 else "none"
    repo.save_scores(conn, user_id, [{"match_id": match_id, "fit": {"percent": percent, "label": label, "shown": [], "gaps": []}, "from_summary": False}])


def test_job_counts(conn, user_a, user_b):
    fam = family(conn, user_a)
    today, old, weak, unscored, seen, hidden = matched(
        conn, user_a, listing(1), listing(2, posted_on=TODAY - timedelta(days=3)), listing(3), listing(4), listing(5), listing(6), family_id=fam)
    for match_id, percent in ((today, 85), (old, 60), (weak, 39), (seen, 90), (hidden, 90)):
        scored(conn, user_a, match_id, percent)
    conn.execute("update job_matches set status = 'seen' where id = %s", (seen,))
    repo.hide_match(conn, user_a, hidden)
    # new: not yet seen and scored 40 or more. fresh: those posted in the last two days
    assert repo.job_counts(conn, user_a, SINCE, TODAY - timedelta(days=2)) == {"new": 2, "fresh": 1}
    assert repo.job_counts(conn, user_b, SINCE, TODAY - timedelta(days=2)) == {"new": 0, "fresh": 0}


def test_family_market_figures(conn, user_a, user_b):
    register(conn, "Zzqx Holdings Ltd")
    on, off = family(conn, user_a, "Zzqx On"), family(conn, user_a, "Zzqx Off", targeted=False)
    matched(conn, user_a,
            listing(1),                                                     # named, listed, £30,000
            listing(2, employer="Zzqy Nobody", employer_key="zzqy nobody", salary_min=40000, salary_max=None),  # named, £40,000
            listing(3, posted_by="agency", salary_min=450, salary_max=500, salary_annual=False),  # agency, a rate
            listing(4, salary_min=None, salary_max=None, salary_annual=False),                    # named, listed, no salary
            family_id=on)
    (gone,) = matched(conn, user_a, listing(5), family_id=on)
    repo.hide_match(conn, user_a, gone)
    matched(conn, user_a, listing(6), family_id=off)
    market = repo.family_market(conn, user_a, SINCE)
    assert set(market) == {on}
    assert market[on]["jobs"] == 4 and market[on]["named"] == 3 and market[on]["listed"] == 2
    assert sorted(market[on]["salaries"]) == [30000, 40000]
    assert repo.family_market(conn, user_b, SINCE) == {}


def test_include_senior_setting(conn, user_a):
    assert repo.get_or_create_profile(conn, user_a, "Test Person")["include_senior"] is False
    repo.set_include_senior(conn, user_a, True)
    assert repo.get_or_create_profile(conn, user_a, "Test Person")["include_senior"] is True
