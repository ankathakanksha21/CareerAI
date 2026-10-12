from datetime import date

import pytest

import jobs

MINE = ["Delivery delays report", "Spreadsheet automation"]


def need(text, shown_by=""):
    return {"need": text, "shown_by": shown_by}


# ---------- fit: requirements shown, out of requirements listed ----------

@pytest.mark.parametrize("percent, label", [(0, "none"), (39, "none"), (40, "stretch"), (59, "stretch"),
                                            (60, "near"), (79, "near"), (80, "direct"), (100, "direct")])
def test_fit_label_boundaries(percent, label):
    assert jobs.fit_label(percent) == label


def test_fit_counts_only_achievements_the_user_has():
    f = jobs.fit([need("SQL", "Delivery delays report"), need("Python", "An achievement they do not have"), need("Tableau")], MINE)
    assert f["percent"] == 33 and f["label"] == "none"
    assert f["shown"] == [{"need": "SQL", "achievement": "Delivery delays report"}]
    assert f["gaps"] == ["Python", "Tableau"]


def test_fit_ignores_case_and_outer_spaces_and_keeps_the_users_spelling():
    f = jobs.fit([need("SQL", "  delivery DELAYS report ")], MINE)
    assert f["percent"] == 100 and f["label"] == "direct"
    assert f["shown"] == [{"need": "SQL", "achievement": "Delivery delays report"}]


@pytest.mark.parametrize("requirements", [[], [need("  ")], [need("")]])
def test_fit_is_none_without_requirements(requirements):
    assert jobs.fit(requirements, MINE) is None  # no score, rather than a division by zero


def test_fit_rounds_to_a_whole_percent():
    f = jobs.fit([need("a", MINE[0]), need("b", MINE[1]), need("c")], MINE)
    assert f["percent"] == 67 and f["label"] == "near"


def test_fit_lists_at_most_three_shown_and_three_gaps():
    f = jobs.fit([need(f"s{i}", MINE[0]) for i in range(5)] + [need(f"g{i}") for i in range(4)], MINE)
    assert f["percent"] == 56
    assert [s["need"] for s in f["shown"]] == ["s0", "s1", "s2"] and f["gaps"] == ["g0", "g1", "g2"]


def test_fit_with_no_achievements_is_all_gaps():
    f = jobs.fit([need("SQL", "Delivery delays report")], [])
    assert f["percent"] == 0 and f["label"] == "none" and f["gaps"] == ["SQL"]


# ---------- which searches to run ----------

def fam(name, titles, targeted=True, id=None):
    return {"id": id or f"id-{name}", "name": name, "uk_titles": titles, "targeted": targeted}


def test_plan_searches_three_titles_per_targeted_family_in_each_location():
    families = [fam("Data", ["Data Analyst", "BI Analyst", "Insight Analyst", "Reporting Analyst"]), fam("Ops", ["Operations Analyst"], targeted=False)]
    plan = jobs.plan(families, ["London", "Manchester"])
    assert [(p["query"], p["location"]) for p in plan] == [
        ("data analyst", "london"), ("data analyst", "manchester"), ("bi analyst", "london"), ("bi analyst", "manchester"),
        ("insight analyst", "london"), ("insight analyst", "manchester")]
    assert {p["family_id"] for p in plan} == {"id-Data"}


def test_plan_uses_the_family_name_when_it_has_no_titles():
    assert [p["query"] for p in jobs.plan([fam("Data Analyst", []), fam("Ops", ["", "  "])], ["London"])] == ["data analyst", "ops"]


def test_plan_runs_a_repeated_search_once_under_the_first_family():
    plan = jobs.plan([fam("Data", [" Data  Analyst "]), fam("Insight", ["data analyst", "Insight Analyst"])], ["London", " london "])
    assert [(p["query"], p["location"], p["family_id"]) for p in plan] == [
        ("data analyst", "london", "id-Data"), ("insight analyst", "london", "id-Insight")]


def test_plan_is_empty_without_targets_or_locations():
    assert jobs.plan([fam("Data", ["Data Analyst"], targeted=False)], ["London"]) == []
    assert jobs.plan([fam("Data", ["Data Analyst"])], []) == []


# ---------- senior titles ----------

@pytest.mark.parametrize("title", ["Senior Data Analyst", "Head of Data", "Data Lead", "Analytics Manager", "PRINCIPAL Engineer",
                                   "Director, Insight", "Lead-Analyst"])
def test_senior_titles(title):
    assert jobs.is_senior(title) is True


@pytest.mark.parametrize("title", ["Data Analyst", "Leadership Graduate Scheme", "Headhunter Assistant", "Graduate Management Trainee",
                                   "Junior Analyst", ""])
def test_titles_that_are_not_senior(title):
    assert jobs.is_senior(title) is False


# ---------- the same advert posted twice ----------

def found(n, **changes):
    return {"id": f"L{n}", "title": "Data Analyst", "employer_key": "zzqx", "location": "London", "posted_on": date(2026, 10, 1 + n),
            "query": "data analyst", "search_location": "london"} | changes


def test_dedupe_keeps_the_newest_of_a_reposted_advert():
    kept = jobs.dedupe([found(1), found(3, title=" data analyst "), found(2, location="LONDON")])
    assert [x["id"] for x in kept] == ["L3"]


def test_dedupe_keeps_adverts_that_differ_in_title_employer_or_town():
    listings = [found(1), found(2, title="BI Analyst"), found(3, employer_key="qqzz"), found(4, location="Leeds")]
    assert [x["id"] for x in jobs.dedupe(listings)] == ["L1", "L2", "L3", "L4"]


def test_dedupe_keeps_adverts_with_no_known_employer_apart():
    assert len(jobs.dedupe([found(1, employer_key=""), found(2, employer_key="")])) == 2


# ---------- which adverts to score first ----------

def waiting(n, title="Data Analyst", description="", posted_on=date(2026, 10, 5)):
    return {"match_id": f"M{n}", "listing_id": f"L{n}", "source_id": str(n), "title": title, "employer": "Company A",
            "description": description, "description_is_full": False, "posted_on": posted_on}


def test_shortlist_hides_senior_titles_unless_allowed():
    candidates = [waiting(1, "Senior Data Analyst"), waiting(2), waiting(3, "Analytics Manager")]
    assert [c["match_id"] for c in jobs.shortlist(candidates, [], include_senior=False, limit=15)] == ["M2"]
    assert len(jobs.shortlist(candidates, [], include_senior=True, limit=15)) == 3


def test_shortlist_puts_adverts_mentioning_more_of_the_users_skills_first():
    candidates = [waiting(1, description="We use Excel."), waiting(2, description="SQL, Python and Excel daily."),
                  waiting(3, "SQL Developer", description="Databases.")]
    ranked = jobs.shortlist(candidates, ["SQL", "Python", "excel", "sql"], include_senior=False, limit=15)
    assert [c["match_id"] for c in ranked] == ["M2", "M1", "M3"]  # three skills, then one each in the order given


def test_shortlist_matches_whole_words_only():
    candidates = [waiting(1, "Recruiter", "Recruitment for retail."), waiting(2, description="Experience with R and C++ needed.")]
    assert jobs.shortlist(candidates, ["R", "C++"], include_senior=False, limit=1)[0]["match_id"] == "M2"


def test_shortlist_breaks_ties_by_newest_and_respects_the_limit():
    candidates = [waiting(1, posted_on=date(2026, 10, 1)), waiting(2, posted_on=date(2026, 10, 9)), waiting(3, posted_on=date(2026, 10, 5))]
    assert [c["match_id"] for c in jobs.shortlist(candidates, [], include_senior=False, limit=2)] == ["M2", "M3"]


def test_skills_come_from_achievements_without_repeats():
    achievements = [{"skills": ["SQL", "Excel"]}, {"skills": ["sql ", "Python", ""]}, {"skills": None}, {}]
    assert jobs.skills_of(achievements) == ["sql", "excel", "python"]


# ---------- calling Reed for several searches at once ----------

def test_fetch_returns_what_succeeded_and_counts_what_failed(monkeypatch):
    def search_both(query, location):
        if query == "bi analyst":
            raise jobs.reed.ReedError("down")
        return [{"source_id": f"{query}-{location}", "employer": "Zzqx Holdings Ltd"}]
    monkeypatch.setattr(jobs.reed, "search_both", search_both)
    searches = [{"query": "data analyst", "location": "london"}, {"query": "bi analyst", "location": "london"},
                {"query": "data analyst", "location": "leeds"}]
    got, failed = jobs.fetch(searches)
    assert failed == 1 and set(got) == {("data analyst", "london"), ("data analyst", "leeds")}
    assert got[("data analyst", "london")] == [{"source_id": "data analyst-london", "employer": "Zzqx Holdings Ltd", "employer_key": "zzqx"}]


def test_fetch_with_nothing_to_do_makes_no_calls(monkeypatch):
    monkeypatch.setattr(jobs.reed, "search_both", lambda *a: pytest.fail("called"))
    assert jobs.fetch([]) == ({}, 0)


def test_fetch_details_skips_full_adverts_and_failures(monkeypatch):
    asked = []

    def details(source_id):
        asked.append(source_id)
        if source_id == "2":
            raise jobs.reed.ReedError("gone")
        return {"description": f"full {source_id}", "description_is_full": True}
    monkeypatch.setattr(jobs.reed, "details", details)
    candidates = [waiting(1), waiting(2), waiting(3) | {"description_is_full": True}]
    assert jobs.fetch_details(candidates) == {"L1": {"description": "full 1", "description_is_full": True}}
    assert sorted(asked) == ["1", "2"]


# ---------- scoring in batches ----------

ACHIEVEMENTS = [{"title": "Thing one", "uk_version": "Built X", "skills": ["SQL"]}]


def test_score_numbers_each_batch_from_one_and_maps_the_results_back(monkeypatch):
    batches = []

    def score_jobs(batch, achievements):
        batches.append([b["n"] for b in batch])
        return {b["n"]: [{"need": b["title"], "shown_by": "Thing one"}] for b in batch}
    monkeypatch.setattr(jobs.ai, "score_jobs", score_jobs)
    monkeypatch.setattr(jobs, "SCORE_BATCH", 2)
    rows, missed = jobs.score([waiting(1, "A"), waiting(2, "B"), waiting(3, "C") | {"description_is_full": True}], ACHIEVEMENTS)
    assert sorted(batches) == [[1], [1, 2]] and missed == 0
    by_match = {r["match_id"]: r for r in rows}
    assert by_match["M3"]["fit"]["shown"] == [{"need": "C", "achievement": "Thing one"}] and by_match["M3"]["from_summary"] is False
    assert by_match["M1"]["fit"]["percent"] == 100 and by_match["M1"]["from_summary"] is True


def test_score_keeps_the_good_batch_when_another_fails(monkeypatch):
    def score_jobs(batch, achievements):
        if batch[0]["title"] == "A":
            raise jobs.ai.AIError("job fit")
        return {b["n"]: [{"need": "x", "shown_by": ""}] for b in batch}
    monkeypatch.setattr(jobs.ai, "score_jobs", score_jobs)
    monkeypatch.setattr(jobs, "SCORE_BATCH", 1)
    rows, missed = jobs.score([waiting(1, "A"), waiting(2, "B")], ACHIEVEMENTS)
    assert [r["match_id"] for r in rows] == ["M2"] and missed == 1


def test_score_raises_when_every_batch_fails(monkeypatch):
    def score_jobs(batch, achievements):
        raise jobs.ai.AIError("job fit")
    monkeypatch.setattr(jobs.ai, "score_jobs", score_jobs)
    with pytest.raises(jobs.ai.AIError):
        jobs.score([waiting(1), waiting(2)], ACHIEVEMENTS)


def test_score_reports_adverts_the_model_left_out_and_keeps_unjudgeable_ones(monkeypatch):
    monkeypatch.setattr(jobs.ai, "score_jobs", lambda batch, achievements: {1: [], 3: [{"need": "x", "shown_by": ""}]})
    rows, missed = jobs.score([waiting(1), waiting(2), waiting(3)], ACHIEVEMENTS)
    assert missed == 1
    assert {r["match_id"]: r["fit"] and r["fit"]["percent"] for r in rows} == {"M1": None, "M3": 0}


def test_score_with_nothing_to_score_calls_nothing(monkeypatch):
    monkeypatch.setattr(jobs.ai, "score_jobs", lambda *a: pytest.fail("called"))
    assert jobs.score([], ACHIEVEMENTS) == ([], 0)


# ---------- figures for the role family cards ----------

def test_median():
    assert jobs.median([]) is None
    assert jobs.median([30000]) == 30000 and jobs.median([30000, 40000, 100000]) == 40000
    assert jobs.median([30000, 35001]) == 32500  # a whole number of pounds


def test_market_summarises_each_family():
    raw = {"f1": {"jobs": 4, "named": 3, "listed": 2, "salaries": [30000.0, 40000.0]}, "f2": {"jobs": 1, "named": 0, "listed": 0, "salaries": []}}
    assert jobs.market(raw) == {"f1": {"jobs": 4, "named": 3, "listed": 2, "salary_median": 35000, "salary_n": 2},
                                "f2": {"jobs": 1, "named": 0, "listed": 0, "salary_median": None, "salary_n": 0}}
