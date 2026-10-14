from datetime import date, timedelta

import analytics

F, G = "fam-f", "fam-g"
FAMILIES = [{"id": F, "name": "Data Analyst"}, {"id": G, "name": "Product Analyst"}]
APPLIED = date(2026, 10, 1)


def app(**kw):
    return {"stage": "applied", "source": "Company site", "applied_on": APPLIED, "posted_on": None,
            "role_family_id": None, "cv_version_id": None} | kw


def posted(days_before: int, **kw):
    return app(posted_on=APPLIED - timedelta(days=days_before), **kw)


def finding(stats, finding_id):
    return next((f for f in stats["findings"] if f["id"] == finding_id), None)


EMPTY_STATE = {"achievements": [], "role_families": [], "saved_jobs": [], "cv_versions": [], "journal": [], "applications": []}


# ---------- stats ----------

def test_empty_tracker_has_no_findings_and_zero_rates():
    stats = analytics.compute([], [], [], [])
    assert stats["findings"] == []
    assert stats["funnel"]["applied"] == 0 and stats["funnel"]["response_rate"] == 0
    assert stats["timing"]["avg_days"] == 0
    assert stats["by_family"] == [] and stats["by_cv"] == [] and stats["by_source"] == []


def test_funnel_counts_stages():
    apps = [app(stage=s) for s in ("applied", "no_response", "rejected", "screening", "interview", "rejected_after_interview", "offer")]
    funnel = analytics.compute(apps, [], [], [])["funnel"]
    assert (funnel["applied"], funnel["responses"], funnel["interviews"], funnel["offers"]) == (7, 4, 3, 1)
    assert funnel["response_rate"] == 0.57


def test_by_family_labels_unknown_as_no_role_family():
    rows = analytics.compute([app(), app(role_family_id=F), app(role_family_id=F)], FAMILIES, [], [])["by_family"]
    assert [(r["label"], r["key"], r["applied"]) for r in rows] == [("Data Analyst", F, 2), ("No role family", None, 1)]


def test_by_cv_labels_missing_as_no_cv_recorded():
    cvs = [{"id": "cv1", "name": "Role A, Company A v1", "role_family_id": F}]
    rows = analytics.compute([app(), app(), app(cv_version_id="cv1")], FAMILIES, cvs, [])["by_cv"]
    assert [(r["label"], r["applied"]) for r in rows] == [("No CV recorded", 2), ("Role A, Company A v1", 1)]


# ---------- rule 1: low reply rate ----------

def test_low_reply_rule_fires_at_four_apps_under_15_percent():
    stats = analytics.compute([app(role_family_id=F, stage="no_response") for _ in range(4)], FAMILIES, [], [])
    f = finding(stats, f"cv-{F}")
    assert f["type"] == "cv"
    assert f["title"] == "Data Analyst applications are not getting replies"
    assert f["link"] == {"page": "resume", "label": "Tailor a CV"}


def test_low_reply_rule_silent_at_three_apps():
    stats = analytics.compute([app(role_family_id=F) for _ in range(3)], FAMILIES, [], [])
    assert finding(stats, f"cv-{F}") is None


def test_low_reply_rule_silent_at_15_percent_or_more():
    apps = [app(role_family_id=F) for _ in range(5)] + [app(role_family_id=F, stage="screening")]  # 1 of 6 = 17%
    assert finding(analytics.compute(apps, FAMILIES, [], []), f"cv-{F}") is None


def test_low_reply_detail_when_no_tailored_cv():
    stats = analytics.compute([app(role_family_id=F) for _ in range(4)], FAMILIES, [], [])
    assert finding(stats, f"cv-{F}")["evidence"] == "0 responses from 4 applications. None of them used a tailored CV."


def test_low_reply_detail_when_other_family_cv():
    cvs = [{"id": "cv9", "name": "Product CV v1", "role_family_id": G}]
    stats = analytics.compute([app(role_family_id=F, cv_version_id="cv9") for _ in range(4)], FAMILIES, cvs, [])
    evidence = finding(stats, f"cv-{F}")["evidence"]
    assert "a CV written for another role" in evidence and "Product CV v1" in evidence


def test_low_reply_no_detail_when_own_family_cv_used():
    cvs = [{"id": "cv1", "name": "Data CV v1", "role_family_id": F}]
    stats = analytics.compute([app(role_family_id=F, cv_version_id="cv1") for _ in range(4)], FAMILIES, cvs, [])
    assert finding(stats, f"cv-{F}")["evidence"] == "0 responses from 4 applications."


def test_low_reply_rule_covers_apps_without_a_family():
    f = finding(analytics.compute([app() for _ in range(4)], FAMILIES, [], []), "cv-none")
    assert f["title"] == "Applications without a role family are not getting replies"


# ---------- rule 2: interviews but no offers ----------

def test_story_rule_needs_three_interviews_no_offers():
    three = [app(stage="interview"), app(stage="interview"), app(stage="rejected_after_interview")]
    f = finding(analytics.compute(three, [], [], []), "story")
    assert f["link"] == {"page": "interview", "label": "Practise an interview"}
    assert f["action"] == "Run a mock interview and strengthen your STAR stories before the next one."
    assert finding(analytics.compute(three[:2], [], [], []), "story") is None
    assert finding(analytics.compute(three + [app(stage="offer")], [], [], []), "story") is None


def test_story_rule_wording_without_stories():
    three = [app(stage="interview") for _ in range(3)]
    assert "You have no STAR stories saved yet." in finding(analytics.compute(three, [], [], []), "story")["evidence"]


def test_story_rule_counts_weak_stories():
    three = [app(stage="interview") for _ in range(3)]
    stories = [{"strength": "strong"}, {"strength": "needs a number"}, {"strength": "needs detail"}]
    assert "2 of your 3 STAR stories" in finding(analytics.compute(three, [], [], stories), "story")["evidence"]


# ---------- rule 3: referrals ----------

def test_network_rule_has_no_link():
    apps = [app(source="Referral", stage="screening") for _ in range(2)] + [app(source="LinkedIn", stage="no_response") for _ in range(10)]
    f = finding(analytics.compute(apps, [], [], []), "network")
    assert f["link"] is None
    assert f["evidence"] == "Referrals got replies 2 of 2 times. Job boards: 0 of 10."
    assert f["action"] == "Ask people you know inside companies that are hiring for a referral before you apply."


def test_network_rule_silent_without_job_board_applications():
    apps = [app(source="Referral", stage="screening")] + [app(source="Company site") for _ in range(6)]
    assert finding(analytics.compute(apps, [], [], []), "network") is None


# ---------- rule 5: timing ----------

def test_timing_excludes_apps_without_posted_date():
    apps = [posted(1), posted(9)] + [app() for _ in range(3)]
    timing = analytics.compute(apps, [], [], [])["timing"]
    assert timing["fast"]["applied"] + timing["slow"]["applied"] == 2
    assert timing["avg_days"] == 5.0


def test_timing_rule_fires_with_four_timed_apps():
    apps = [posted(1, stage="screening"), posted(1, stage="screening"), posted(10), posted(10)]
    f = finding(analytics.compute(apps, [], [], []), "timing")
    assert f["link"] == {"page": "jobs", "label": "See new jobs"}
    assert f["evidence"] == "Average 5.5 days after posting. Within 48 hours: 2 of 2 replied. Later: 0 of 2."


def test_timing_rule_needs_four_timed_apps():
    apps = [posted(1, stage="screening"), posted(7), posted(7)] + [app() for _ in range(5)]
    assert finding(analytics.compute(apps, [], [], []), "timing") is None


def test_no_direction_rule():
    apps = [app(role_family_id=F) for _ in range(6)]
    assert all(f["type"] != "direction" for f in analytics.compute(apps, FAMILIES, [], [])["findings"])


def test_findings_are_sorted_most_severe_first():
    apps = ([posted(1, stage="screening"), posted(1, stage="screening"), posted(10), posted(10)]
            + [app(role_family_id=F, stage="no_response") for _ in range(8)])
    severities = [f["severity"] for f in analytics.compute(apps, FAMILIES, [], [])["findings"]]
    assert len(severities) >= 2 and severities == sorted(severities, reverse=True)


# ---------- next steps ----------

def test_next_steps_empty_state():
    steps = analytics.next_steps(EMPTY_STATE)
    assert [s["id"] for s in steps] == ["profile", "roles", "job", "cv", "interview", "application"]
    assert [s["page"] for s in steps] == ["profile", "pathways", "jobs", "resume", "interview", "applications"]
    assert steps[2]["text"] == "Save a job you want" and "paste an advert" in steps[2]["why"]
    assert not any(s["done"] for s in steps)
    assert steps[0]["text"] == "Build your profile"
    assert steps[0]["why"] == "Your CVs, stories and interview practice are all built from it."


def test_next_steps_progress():
    state = EMPTY_STATE | {"achievements": [{"id": "a1"}], "role_families": [{"id": F, "targeted": True}]}
    assert [s["done"] for s in analytics.next_steps(state)] == [True, True, False, False, False, False]


def test_next_steps_untargeted_family_does_not_count():
    state = EMPTY_STATE | {"role_families": [{"id": F, "targeted": False}]}
    assert analytics.next_steps(state)[1]["done"] is False


def test_next_steps_interview_needs_interview_journal_entry():
    state = EMPTY_STATE | {"journal": [{"type": "coach"}]}
    assert analytics.next_steps(state)[4]["done"] is False
    assert analytics.next_steps(EMPTY_STATE | {"journal": [{"type": "interview"}]})[4]["done"] is True


def test_next_steps_all_done():
    state = {"achievements": [1], "role_families": [{"targeted": True}], "saved_jobs": [1], "cv_versions": [1],
             "journal": [{"type": "interview"}], "applications": [1]}
    assert all(s["done"] for s in analytics.next_steps(state))


# ---------- few sponsoring employers in a target role ----------

def targeted(*ids):
    return [f | {"targeted": f["id"] in ids} for f in FAMILIES]


def adverts(named, listed, jobs=None):
    return {"jobs": jobs or named, "named": named, "listed": listed, "salary_median": None, "salary_n": 0}


def test_sponsor_finding_fires_at_ten_named_adverts_under_twenty_percent():
    stats = analytics.compute([], targeted(F), [], [], market={F: adverts(named=10, listed=1, jobs=14)})
    f = finding(stats, f"sponsor-{F}")
    assert f["type"] == "sponsor" and f["title"] == "Few Data Analyst roles come from licensed sponsors"
    assert f["evidence"] == "1 of 10 current adverts that name their employer are from employers on the sponsor register."
    assert f["link"] == {"page": "jobs", "label": "Open Jobs"} and "Sponsors only" in f["action"]


def test_sponsor_finding_is_silent_with_nine_named_adverts():
    assert analytics.compute([], targeted(F), [], [], market={F: adverts(named=9, listed=0)})["findings"] == []


def test_sponsor_finding_is_silent_at_twenty_percent():
    assert analytics.compute([], targeted(F), [], [], market={F: adverts(named=10, listed=2)})["findings"] == []


def test_sponsor_finding_is_only_for_targeted_families():
    market = {F: adverts(named=20, listed=0), G: adverts(named=20, listed=0)}
    stats = analytics.compute([], targeted(G), [], [], market=market)
    assert [f["id"] for f in stats["findings"]] == [f"sponsor-{G}"]


def test_no_market_figures_means_no_sponsor_finding():
    assert analytics.compute([], targeted(F), [], [])["findings"] == []
    assert analytics.compute([], targeted(F), [], [], market={})["findings"] == []


def test_a_cv_finding_still_outranks_a_sponsor_finding():
    apps = [app(role_family_id=F) for _ in range(4)]
    stats = analytics.compute(apps, targeted(F), [], [], market={F: adverts(named=10, listed=0)})
    assert [f["type"] for f in stats["findings"]] == ["cv", "sponsor"]


def test_reed_is_a_source_and_counts_as_a_job_board():
    assert "Reed" in analytics.SOURCES and "Reed" in analytics.JOB_BOARDS
    apps = [app(source="Referral", stage="interview") for _ in range(2)] + [app(source="Reed") for _ in range(10)]
    network = finding(analytics.compute(apps, FAMILIES, [], []), "network")
    assert network and "Job boards: 0 of 10" in network["evidence"]


# ---------- step 4: rejections after a phone screen, and lessons that repeat ----------

def lesson(page: str, change: str = "Lead with the SQL project.", made_on: str = "2026-10-10") -> dict:
    return {"likely_reason": "The CV may not have shown enough SQL.", "one_change": change, "page": page, "made_on": made_on}


def rejected(company: str, page: str, **kw) -> dict:
    return app(stage="rejected", rejected_at_stage="cv", company=company, lesson=lesson(page, **kw))


def test_rejection_after_screen_counts_as_reply():
    funnel = analytics.compute([app(stage="rejected", rejected_at_stage="screening")], [], [], [])["funnel"]
    assert (funnel["responses"], funnel["interviews"]) == (1, 0)


def test_rejection_at_cv_is_not_a_reply():
    funnel = analytics.compute([app(stage="rejected", rejected_at_stage="cv"), app(stage="rejected")], [], [], [])["funnel"]
    assert funnel["responses"] == 0


def test_three_lessons_on_one_page_make_a_finding():
    apps = [rejected("Zzqx One", "resume", change="Change one", made_on="2026-10-01"),
            rejected("Zzqx Three", "resume", change="Change three", made_on="2026-10-09"),
            rejected("Zzqx Two", "resume", change="Change two", made_on="2026-10-05")]
    found = finding(analytics.compute(apps, [], [], []), "lessons-resume")
    assert found["type"] == "lessons" and found["severity"] == 3
    assert found["title"] == "3 of your rejections point to your CV"
    assert found["action"] == "Change three"  # the latest lesson's change
    assert all(name in found["evidence"] for name in ("Zzqx One", "Zzqx Two", "Zzqx Three"))
    assert found["link"]["page"] == "resume"


def test_two_lessons_make_no_finding():
    apps = [rejected("Zzqx One", "interview"), rejected("Zzqx Two", "interview"), app(stage="rejected", company="Zzqx Three")]
    assert finding(analytics.compute(apps, [], [], []), "lessons-interview") is None


def test_lessons_on_applications_no_longer_rejected_do_not_count():
    apps = [rejected(name, "resume") | {"stage": "screening"} for name in ("Zzqx One", "Zzqx Two", "Zzqx Three")]
    assert finding(analytics.compute(apps, [], [], []), "lessons-resume") is None


def test_lessons_on_different_pages_do_not_combine():
    apps = [rejected("Zzqx One", "resume"), rejected("Zzqx Two", "interview"), rejected("Zzqx Three", "profile")]
    assert [f for f in analytics.compute(apps, [], [], [])["findings"] if f["type"] == "lessons"] == []
