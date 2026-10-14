"""One build from start to finish, with the model replaced: which calls are made, and what happens
when the wording claims something the user's profile does not show. No database."""
from datetime import date

import pytest

import ai
import cvbuild

TODAY = date(2026, 10, 14)
PROFILE = {"full_name": "Test Person", "course": "MSc Data Science", "university": "Zzqx City University", "graduation_date": date(2026, 9, 1),
           "visa_type": "student", "visa_end_date": date(2027, 1, 30), "skills": ["SQL", "Excel"], "languages": [], "additional": []}
WORK = [{"id": "j1", "employer": "Zzqx Holdings Ltd", "job_title": "Systems Engineer", "location": "Pune", "country": "India",
         "start_month": date(2023, 7, 1), "end_month": date(2025, 8, 1), "is_current": False, "employer_context": ""}]
EDUCATION = [{"id": "c1", "institution": "Zzqx City University", "qualification": "MSc", "subject": "Data Science", "start_month": None,
              "end_month": date(2026, 9, 1), "grade": "", "country": "United Kingdom"}]
STORED = "Built a weekly delays report in SQL for 15 managers"
ACHIEVEMENTS = [{"id": "a1", "title": "Delays report", "uk_version": STORED, "skills": ["SQL"], "outcome": "", "scale": "",
                 "work_history_id": "j1", "education_id": None, "source": "cv", "source_url": None}]
JOB = {"id": "s1", "title": "Junior Analyst", "company": "Zzqx Retail plc", "description": "SQL, Tableau and dashboards for depot managers.",
       "role_family_id": None}
BODY = {"profile": "Analyst with reporting experience in SQL.", "bullets": [{"achievement_id": "a1", "text": "Built a weekly SQL delays report for 15 managers"}],
        "skills": {"technical": ["SQL"], "tools": ["Excel"]}}
LETTER = {"keywords": ["SQL", "Tableau", "dashboards", "Junior Analyst"], "gaps": ["No Tableau yet"],
          "cover_letter": {"why_them": "A.", "why_you": "B.", "what_you_deliver": "C."}}


def build(job=JOB):
    return cvbuild.build(profile=PROFILE, email="test.person@example.test", education=EDUCATION, work_history=WORK, achievements=ACHIEVEMENTS,
                         job=job, today=TODAY)


@pytest.fixture
def bodies(monkeypatch):
    """Script ai.build_cv: one reply per call. Returns the `avoid` each call was given."""
    def install(*replies):
        replies, avoided = list(replies), []

        def write(*args, avoid=()):
            avoided.append(list(avoid))
            return replies.pop(0)
        monkeypatch.setattr(ai, "build_cv", write)
        return avoided
    return install


def test_a_job_takes_both_calls_and_a_base_cv_one(stub):
    bodies, letters = stub("build_cv", BODY), stub("job_letter", LETTER)
    content, pages = build()
    assert (len(bodies), len(letters), pages) == (1, 1, 1)
    assert content["profile"] == BODY["profile"] and content["cover_letter"] == LETTER["cover_letter"]
    assert content["work"][0]["bullets"][0]["text"] == "Built a weekly SQL delays report for 15 managers"
    assert content["keywords"]["covered"] == ["SQL"]
    base, _ = build(job=None)
    assert (len(bodies), len(letters)) == (2, 1) and base["cover_letter"] is None


def test_a_paragraph_claiming_what_the_profile_does_not_show_is_asked_for_again(bodies, stub):
    avoided = bodies(BODY | {"profile": "Analyst skilled in SQL, Tableau and dashboard design."}, BODY)
    stub("job_letter", LETTER)
    content, _ = build()
    assert avoided == [[], ["Tableau", "dashboards"]]  # told, the second time, what the profile does not show
    assert content["profile"] == BODY["profile"]


def test_a_paragraph_that_still_claims_it_fails_the_build(bodies, stub):
    claiming = BODY | {"profile": "Analyst skilled in SQL and Tableau."}
    avoided = bodies(claiming, claiming)
    stub("job_letter", LETTER)
    with pytest.raises(ai.AIError):
        build()
    assert len(avoided) == 2


def test_the_jobs_own_title_may_be_named(bodies, stub):
    avoided = bodies(BODY | {"profile": "Analyst with SQL reporting experience, seeking a Junior Analyst role."})
    stub("job_letter", LETTER)
    assert build()[0]["profile"].endswith("seeking a Junior Analyst role.") and avoided == [[]]


def test_what_the_profile_shows_may_be_claimed(bodies, stub):
    avoided = bodies(BODY | {"profile": "Systems Engineer with an MSc in Data Science, strong in SQL and Excel."})
    stub("job_letter", LETTER | {"keywords": ["SQL", "Excel", "MSc", "Systems Engineer", "Data Science"]})
    assert "Systems Engineer with an MSc" in build()[0]["profile"] and avoided == [[]]


def test_a_bullet_that_brings_in_what_the_profile_does_not_show_goes_back_to_the_stored_wording(bodies, stub):
    bodies(BODY | {"bullets": [{"achievement_id": "a1", "text": "Built weekly Tableau dashboards in SQL for 15 managers"}]})
    stub("job_letter", LETTER)
    content, _ = build()
    assert content["work"][0]["bullets"][0] == {"text": STORED, "achievement_id": "a1", "hidden": False}
    assert content["keywords"]["covered"] == ["SQL"] and content["keywords"]["missing"] == ["Tableau", "dashboards", "Junior Analyst"]


def test_a_base_cv_is_not_checked_against_any_job(bodies, stub):
    avoided = bodies(BODY | {"profile": "Analyst skilled in SQL and Tableau."})
    letters = stub("job_letter", LETTER)
    assert build(job=None)[0]["profile"] == "Analyst skilled in SQL and Tableau." and avoided == [[]] and letters == []


@pytest.mark.parametrize("failing", ["build_cv", "job_letter"])
def test_either_call_failing_fails_the_build(stub, failing):
    stub("build_cv", BODY)
    stub("job_letter", LETTER)
    stub(failing, ai.AIError(failing))
    with pytest.raises(ai.AIError):
        build()


def test_unsupported_names_characters_in_the_cv_and_in_the_letter(stub):
    stub("build_cv", BODY | {"profile": "Saved ₹5 lakh with SQL."})
    stub("job_letter", LETTER | {"cover_letter": {"why_them": "中.", "why_you": "B.", "what_you_deliver": "C."}})
    content, _ = build()
    assert cvbuild.unsupported(content, "Ms 张") == "₹张中" and cvbuild.unsupported(content) == "₹中"
    assert cvbuild.unsupported(build(job=None)[0]) == "₹"
