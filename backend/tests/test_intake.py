from datetime import date

import pytest

import ai
import intake
from llm import LLMNotConfigured

PROFILE = {"full_name": "Test Person", "course": "MSc Course A", "university": "Zzqx City University", "skills": ["SQL"],
           "languages": [{"language": "Hindi", "level": "Native"}]}
FOUND = {"items": [{"title": "Thing one", "uk_version": "Built X", "where": "Zzqx Holdings Ltd"}], "pitch": "I am."}
FACTS = {"work_history": [], "education": [], "skills": [], "languages": []}

SAVED_JOB = {"id": "w-saved", "employer": "Zzqx Holdings Ltd", "job_title": "Systems Engineer", "location": "", "country": "India",
             "start_month": date(2023, 7, 1), "end_month": None, "is_current": False, "employer_context": ""}
CURRENT_COURSE = {"id": "e-current", "institution": "Zzqx City University", "qualification": "MSc Course A", "subject": "",
                  "start_month": None, "end_month": date(2026, 9, 1), "grade": "", "country": "United Kingdom", "from_details": True}


def job(**kw):
    return {"employer": "Zzqx Retail Group", "job_title": "Analyst Intern", "location": "Leeds", "country": "UK",
            "start_month": date(2022, 1, 1), "end_month": date(2022, 6, 1), "is_current": False, "employer_context": "A retailer"} | kw


def course(**kw):
    return {"institution": "University of Zzqx", "qualification": "BTech", "subject": "Computer Science",
            "start_month": date(2019, 7, 1), "end_month": date(2023, 5, 1), "grade": "8.4/10", "country": "India"} | kw


# ---------- both calls, side by side ----------

@pytest.fixture
def calls(monkeypatch):
    """Replace the two extraction tasks. Each is a result to return or an exception to raise."""
    def install(achievements=FOUND, facts=FACTS):
        made = []

        def fake(name, result):
            def run(*args):
                made.append((name, args))
                if isinstance(result, Exception):
                    raise result
                return result
            return run
        monkeypatch.setattr(ai, "extract_achievements", fake("achievements", achievements))
        monkeypatch.setattr(ai, "extract_facts", fake("facts", facts))
        return made
    return install


def test_read_runs_both_tasks_on_the_same_text(calls):
    made = calls()
    saved = [{"title": "Old", "uk_version": "Did Y"}]
    assert intake.read("the text", PROFILE, "cv", saved) == {"items": FOUND["items"], "pitch": "I am.", "facts": FACTS}
    assert sorted(made) == [("achievements", ("the text", PROFILE, "cv", saved)), ("facts", ("the text", PROFILE, "cv"))]


def test_read_keeps_the_achievements_when_the_facts_task_fails(calls):
    made = calls(facts=ai.AIError("cv facts"))
    assert intake.read("the text", PROFILE, "cv", []) == {"items": FOUND["items"], "pitch": "I am.", "facts": None}
    assert len(made) == 2


def test_read_fails_when_the_achievements_task_fails(calls):
    made = calls(achievements=ai.AIError("achievements"))
    with pytest.raises(ai.AIError):
        intake.read("the text", PROFILE, "cv", [])
    assert len(made) == 2  # the facts task still ran; its result is simply not used


def test_read_does_not_hide_a_server_that_is_not_set_up(calls):
    calls(facts=LLMNotConfigured("no model"))
    with pytest.raises(LLMNotConfigured):
        intake.read("the text", PROFILE, "cv", [])


# ---------- two names for one place ----------

@pytest.mark.parametrize("a, b, expected", [
    ("Zzqx Holdings Ltd", "zzqx holdings ltd.", True),
    ("Systems Engineer, Zzqx Holdings Ltd, Pune", "Zzqx Holdings Ltd", True),
    ("Zzqx", "Zzqx Holdings Ltd", True),
    ("University of Zzqx", "Zzqx University", True),        # the same words in another order
    ("MSc Data Science", "MSc in Data Science", True),
    ("Zzqx Holdings Ltd", "Zzqx Retail Group", False),
    ("PROJECTS", "Zzqx Holdings Ltd", False),
    ("", "Zzqx Holdings Ltd", False), ("Zzqx Holdings Ltd", "", False),
    ("IT", "Zzqx IT Services", False),                      # too short to be a name on its own
])
def test_same(a, b, expected):
    assert intake.same(a, b) is expected and intake.same(b, a) is expected


# ---------- where each achievement happened ----------

def placed(where, facts=FACTS, work=(SAVED_JOB,), education=(CURRENT_COURSE,)):
    return intake.place([{"title": "T", "uk_version": "Did X", "where": where}], facts, list(work), list(education))[0]


def test_an_achievement_at_a_saved_job_is_linked_to_it():
    item = placed("Systems Engineer, Zzqx Holdings Ltd, Pune")
    assert item["work_history_id"] == "w-saved" and item["proposal"] is None and "education_id" not in item


def test_an_achievement_on_a_saved_course_is_linked_to_it():
    item = placed("Zzqx City University")
    assert item["education_id"] == "e-current" and item["proposal"] is None


def test_an_achievement_at_a_job_only_just_found_points_at_the_proposal():
    facts = FACTS | {"work_history": [job(employer="Zzqx Other Ltd"), job()], "education": [course()]}
    assert placed("Zzqx Retail Group", facts)["proposal"] == ("work_history", 1)
    assert placed("University of Zzqx", facts)["proposal"] == ("education", 0)


def test_a_saved_entry_wins_over_a_proposal_of_the_same_place():
    item = placed("Zzqx Holdings Ltd", FACTS | {"work_history": [job(employer="Zzqx Holdings Limited")]})
    assert item["work_history_id"] == "w-saved" and item["proposal"] is None


@pytest.mark.parametrize("where", ["PROJECTS", "", "Somewhere Else Ltd"])
def test_an_achievement_that_names_no_known_place_is_left_unlinked(where):
    item = placed(where, FACTS | {"work_history": [job()]})
    assert item["proposal"] is None and "work_history_id" not in item and "education_id" not in item


def test_place_works_when_the_facts_could_not_be_read():
    assert placed("Zzqx Retail Group", None)["proposal"] is None
    assert placed("Zzqx Holdings Ltd", None)["work_history_id"] == "w-saved"


# ---------- what to offer the user ----------

def offered(facts, items=(), saved=(), work=(SAVED_JOB,), education=(CURRENT_COURSE,)):
    return intake.proposals(facts, list(items), list(saved), list(work), list(education), PROFILE)


def test_nothing_to_offer_when_the_facts_could_not_be_read():
    assert offered(None) is None


def test_a_new_job_and_course_are_offered_whole_with_their_achievements():
    facts = FACTS | {"work_history": [job()], "education": [course()]}
    items = [{"proposal": ("work_history", 0)}, {"proposal": None}, {"proposal": ("education", 0)}, {"proposal": ("work_history", 0)}]
    saved = [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}, {"id": "a4"}]
    found = offered(facts, items, saved)
    assert found["work_history"] == [job() | {"achievement_ids": ["a1", "a4"]}]
    assert found["education"] == [course() | {"achievement_ids": ["a3"]}]


def test_a_course_already_saved_in_full_is_not_offered_again():
    full = CURRENT_COURSE | {"start_month": date(2025, 9, 1), "grade": "Merit"}
    facts = FACTS | {"education": [course(institution="Zzqx City University", qualification="MSc", subject="Course A", country="UK")]}
    assert offered(facts, education=[full])["education"] == []


def test_a_found_course_that_matches_the_current_one_offers_only_what_it_adds():
    facts = FACTS | {"education": [course(institution="Zzqx City University", qualification="MSc", subject="Course A",
                                          start_month=date(2025, 9, 1), end_month=date(2026, 9, 1), grade="Predicted Merit", country="UK")]}
    assert offered(facts)["education"] == [{"id": "e-current", "name": "MSc Course A, Zzqx City University",
                                            "adds": {"start_month": date(2025, 9, 1), "grade": "Predicted Merit"}, "achievement_ids": []}]


def test_a_found_job_that_matches_a_saved_one_offers_only_what_it_adds():
    facts = FACTS | {"work_history": [job(employer="Zzqx Holdings Limited", job_title="Systems Engineer", location="Pune", country="India",
                                          start_month=date(2020, 1, 1), end_month=date(2025, 8, 1), employer_context="IT services")]}
    assert offered(facts)["work_history"] == [{"id": "w-saved", "name": "Systems Engineer, Zzqx Holdings Ltd",
                                               "adds": {"location": "Pune", "end_month": date(2025, 8, 1), "employer_context": "IT services"},
                                               "achievement_ids": []}]


def test_another_role_at_the_same_employer_is_a_new_job():
    facts = FACTS | {"work_history": [job(employer="Zzqx Holdings Ltd", job_title="Intern")]}
    assert offered(facts)["work_history"] == [job(employer="Zzqx Holdings Ltd", job_title="Intern") | {"achievement_ids": []}]


def test_a_matched_entry_with_nothing_to_add_is_still_offered_when_achievements_need_linking():
    facts = FACTS | {"work_history": [job(employer="Zzqx Holdings Limited", job_title="Systems Engineer", location="", country="",
                                          start_month=None, end_month=None, employer_context="")]}
    found = offered(facts, [{"proposal": ("work_history", 0)}], [{"id": "a1"}])
    assert found["work_history"] == [{"id": "w-saved", "name": "Systems Engineer, Zzqx Holdings Ltd", "adds": {}, "achievement_ids": ["a1"]}]


def test_only_skills_and_languages_the_profile_lacks_are_offered():
    facts = FACTS | {"skills": ["sql", "Python", "Excel"], "languages": [{"language": "hindi", "level": "Fluent"}, {"language": "English", "level": "Fluent"}]}
    found = offered(facts)
    assert found["skills"] == ["Python", "Excel"]
    assert found["languages"] == [{"language": "English", "level": "Fluent"}]
