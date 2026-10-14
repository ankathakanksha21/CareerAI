"""The CV document: pure functions, no database. Names here cannot be real."""
import copy
from datetime import date

import pytest

import cv

TODAY = date(2026, 10, 14)
PROFILE = {"full_name": "Test Person", "city": "Zzqxtown", "phone": "07700 900123", "linkedin_url": "linkedin.com/in/test-person",
           "github_username": "zzqx-test", "graduation_date": date(2026, 9, 1), "visa_type": "student", "visa_end_date": date(2027, 1, 30),
           "skills": ["SQL", "Python"], "languages": [{"language": "English", "level": "Fluent"}, {"language": "Hindi", "level": ""}],
           "additional": ["Zzqx Cloud Practitioner (2025)"]}
EMAIL = "test.person@example.test"
JOB1 = {"id": "j1", "employer": "Zzqx Holdings Ltd", "job_title": "Data Analyst", "location": "Pune", "country": "India",
        "start_month": date(2023, 7, 1), "end_month": date(2025, 8, 1), "is_current": False, "employer_context": "A logistics company."}
JOB2 = {"id": "j2", "employer": "Zzqx Foods", "job_title": "Intern", "location": "Gurugram", "country": "India",
        "start_month": date(2023, 1, 1), "end_month": date(2023, 6, 1), "is_current": False, "employer_context": ""}
COURSE1 = {"id": "c1", "institution": "Zzqx City University", "qualification": "MSc", "subject": "Data Science",
           "start_month": date(2025, 9, 1), "end_month": date(2026, 9, 1), "grade": "Merit", "country": "United Kingdom"}
COURSE2 = {"id": "c2", "institution": "University of Zzqx", "qualification": "BTech", "subject": "Computer Science",
           "start_month": None, "end_month": date(2023, 5, 1), "grade": "CGPA 8.4/10", "country": "India"}
SAVED_JOB = {"id": "s1", "title": "Junior Analyst", "company": "Zzqx Retail plc", "description": "SQL, dashboards and Tableau."}


def achievement(n, **kw):
    return {"id": f"a{n}", "title": f"Thing {n}", "uk_version": f"Built thing {n} in SQL for {n}0 users", "skills": ["SQL"],
            "outcome": "", "scale": "", "work_history_id": None, "education_id": None, "source": "cv", "source_url": None} | kw


def bullet(n, text=None):
    return {"achievement_id": f"a{n}", "text": text or f"Reworded thing {n} for {n}0 users"}


def written(bullets, **kw):
    return {"profile": " A paragraph. ", "bullets": bullets, "skills": {"technical": ["SQL"], "tools": ["Python"]},
            "keywords": ["SQL", "Tableau"], "gaps": ["No Tableau yet "],
            "cover_letter": {"why_them": "Them.", "why_you": "Me.", "what_you_deliver": "This."}} | kw


def build(achievements, bullets, *, job=SAVED_JOB, work=(JOB1, JOB2), education=(COURSE1, COURSE2), profile=PROFILE, **kw):
    return cv.assemble(profile=profile, email=EMAIL, education=list(education), work_history=list(work), achievements=achievements,
                       written=written(bullets, **kw), job=job, today=TODAY)


def edit(stored, change, *, achievements, work=(JOB1, JOB2), education=(COURSE1, COURSE2), profile=PROFILE, email=EMAIL, refresh=False):
    edited = copy.deepcopy(stored)
    change(edited)
    return cv.merge(stored, edited, profile=profile, email=email, education=list(education), work_history=list(work),
                    achievements=achievements, refresh=refresh)


# ---------- which section comes first ----------

def job(start, end=None, current=False):
    return {"start_month": start, "end_month": end, "is_current": current}


def test_months_worked_counts_each_month_once():
    assert cv.months_worked([job(date(2024, 1, 1), date(2024, 12, 1))], TODAY) == 12
    assert cv.months_worked([job(date(2024, 1, 1), date(2024, 12, 1)), job(date(2024, 6, 1), date(2025, 3, 1))], TODAY) == 15
    assert cv.months_worked([job(date(2026, 8, 1), current=True)], TODAY) == 3   # August, September, October
    assert cv.months_worked([job(None, date(2025, 1, 1)), job(None)], TODAY) == 0  # no start: cannot be counted
    assert cv.months_worked([job(date(2025, 3, 1))], TODAY) == 1                   # no end and not current: its first month
    assert cv.months_worked([job("2024-01-01", "2024-12-01")], TODAY) == 12        # as stored inside a CV
    assert cv.months_worked([], TODAY) == 0


@pytest.mark.parametrize("graduated, months_of_work, expected", [
    (date(2024, 11, 1), 12, True),    # graduated 23 months ago, a year of work
    (date(2024, 10, 1), 12, True),    # exactly 24 months ago
    (date(2024, 9, 1), 12, False),    # 25 months ago
    (date(2027, 6, 1), 12, True),     # still studying
    (date(2027, 6, 1), 36, False),    # still studying, but three years of work
    (date(2024, 11, 1), 23, True),
    (date(2024, 11, 1), 24, False),   # two years of work: experience leads
    (None, 0, True),                  # no graduation month on record: treated as studying
])
def test_education_first_at_its_boundaries(graduated, months_of_work, expected):
    history = [job(date(2020, 1, 1), date(2020 + (months_of_work - 1) // 12, (months_of_work - 1) % 12 + 1, 1))] if months_of_work else []
    assert cv.months_worked(history, TODAY) == months_of_work
    assert cv.education_first({"graduation_date": graduated}, history, TODAY) is expected
    first = cv.section_order({"graduation_date": graduated}, history, TODAY)
    assert first == (["education", "work"] if expected else ["work", "education"]) + ["projects", "skills", "additional"]


# ---------- assembling ----------

def test_facts_come_from_the_records_whatever_the_model_wrote():
    a = achievement(1, work_history_id="j1")
    made = build([a], [bullet(1) | {"employer": "Invented Ltd", "start_month": "2001-01"}],
                 work_history=[{"employer": "Invented Ltd"}], education=(COURSE1,), contact={"email": "x@invented.test"})
    assert [(w["work_history_id"], w["employer"], w["job_title"], w["location"], w["country"], w["start_month"], w["end_month"], w["is_current"],
             w["employer_context"]) for w in made["work"]] == [
        ("j1", "Zzqx Holdings Ltd", "Data Analyst", "Pune", "India", "2023-07-01", "2025-08-01", False, "A logistics company."),
        ("j2", "Zzqx Foods", "Intern", "Gurugram", "India", "2023-01-01", "2023-06-01", False, "")]
    assert made["education"] == [{"education_id": "c1", "institution": "Zzqx City University", "qualification": "MSc", "subject": "Data Science",
                                  "start_month": "2025-09-01", "end_month": "2026-09-01", "grade": "Merit", "country": "United Kingdom",
                                  "note": "", "hidden": False}]
    assert made["contact"] == {"name": "Test Person", "city": "Zzqxtown", "phone": "07700 900123", "email": EMAIL,
                               "linkedin": "linkedin.com/in/test-person", "github": "github.com/zzqx-test"}
    assert made["work"][0]["bullets"] == [{"text": "Reworded thing 1 for 10 users", "achievement_id": "a1", "hidden": False}]
    assert "Invented" not in str(made) and "2001" not in str(made)


def test_bullets_sit_under_their_own_job_in_the_models_order():
    achievements = [achievement(1, work_history_id="j1"), achievement(2, work_history_id="j2"), achievement(3, work_history_id="j1")]
    made = build(achievements, [bullet(3), bullet(2), bullet(1)])
    assert [[b["achievement_id"] for b in w["bullets"]] for w in made["work"]] == [["a3", "a1"], ["a2"]]
    assert made["projects"] == []


def test_a_sixth_bullet_for_one_job_is_kept_hidden():
    achievements = [achievement(n, work_history_id="j1") for n in range(1, 8)]
    made = build(achievements, [bullet(n) for n in range(1, 8)])
    assert [b["hidden"] for b in made["work"][0]["bullets"]] == [False] * 5 + [True] * 2


def test_a_fifth_project_is_kept_hidden():
    achievements = [achievement(n) for n in range(1, 7)]
    made = build(achievements, [bullet(n) for n in range(1, 7)])
    assert [p["hidden"] for p in made["projects"]] == [False] * 4 + [True] * 2
    assert all(len(p["bullets"]) == 1 and not p["bullets"][0]["hidden"] for p in made["projects"])


def test_a_job_with_no_bullets_still_appears():
    made = build([achievement(1, work_history_id="j1")], [bullet(1)])
    assert [(w["employer"], w["hidden"], w["bullets"]) for w in made["work"]][1] == ("Zzqx Foods", False, [])


def test_unlinked_course_and_github_achievements_become_projects():
    achievements = [achievement(1), achievement(2, education_id="c2"),
                    achievement(3, source="github", source_url="https://github.com/zzqx-test/bus-times/")]
    made = build(achievements, [bullet(1), bullet(2), bullet(3)])
    assert [(p["achievement_id"], p["title"], p["link"], p["where"]) for p in made["projects"]] == [
        ("a1", "Thing 1", "", ""), ("a2", "Thing 2", "", "University of Zzqx"), ("a3", "Thing 3", "github.com/zzqx-test/bus-times", "")]
    assert all(w["bullets"] == [] for w in made["work"])


def test_an_achievement_linked_to_a_job_that_is_gone_becomes_a_project():
    made = build([achievement(1, work_history_id="j9")], [bullet(1)])
    assert [p["achievement_id"] for p in made["projects"]] == ["a1"]


def test_bullets_for_unknown_or_repeated_achievements_are_left_out():
    made = build([achievement(1)], [bullet(9), bullet(1), bullet(1, "Again"), {"achievement_id": "a1", "text": "  "}])
    assert [(p["achievement_id"], p["bullets"][0]["text"]) for p in made["projects"]] == [("a1", "Reworded thing 1 for 10 users")]


def test_no_work_history_gives_no_work_entries():
    made = build([achievement(1)], [bullet(1)], work=())
    assert made["work"] == [] and made["section_order"][:2] == ["education", "work"]


def test_only_the_current_course():
    made = build([achievement(1)], [bullet(1)], education=(COURSE1,))
    assert [e["institution"] for e in made["education"]] == ["Zzqx City University"]


def test_base_cv_has_no_letter_keywords_or_gaps():
    made = build([achievement(1)], [bullet(1)], job=None)
    assert made["job"] is None and made["cover_letter"] is None and made["gaps"] == []
    assert made["keywords"] == {"terms": [], "covered": [], "available": [], "missing": []}


def test_tailored_cv_keeps_the_job_the_letter_and_the_gaps():
    made = build([achievement(1)], [bullet(1)])
    assert made["job"] == {"title": "Junior Analyst", "company": "Zzqx Retail plc"}
    assert made["cover_letter"] == {"why_them": "Them.", "why_you": "Me.", "what_you_deliver": "This."}
    assert made["gaps"] == ["No Tableau yet"] and made["profile"] == "A paragraph."


@pytest.mark.parametrize("visa, ends, line", [
    ("graduate", date(2028, 3, 14), "Right to work in the UK: Graduate visa, valid until 14 March 2028."),
    ("student", date(2027, 1, 30), "Visa status: Student visa, valid until 30 January 2027."),
    ("student", None, ""), ("", date(2027, 1, 30), ""), ("tourist", date(2027, 1, 30), ""),
])
def test_right_to_work_is_off_and_worded_by_visa(visa, ends, line):
    profile = PROFILE | {"visa_type": visa, "visa_end_date": ends}
    assert cv.right_to_work(profile) == line
    assert build([achievement(1)], [bullet(1)], profile=profile)["right_to_work"] == {"shown": False, "text": line}


def test_skills_languages_and_additional_lines():
    made = build([achievement(1)], [bullet(1)])
    assert made["skills"] == {"technical": ["SQL"], "tools": ["Python"], "languages": ["English (Fluent)", "Hindi"]}
    assert made["additional"] == {"lines": [{"text": "Zzqx Cloud Practitioner (2025)", "hidden": False}]}


def test_skills_the_model_did_not_sort_are_still_listed():
    made = build([achievement(1, skills=["Excel", "sql"])], [bullet(1)], skills={"technical": [], "tools": []})
    assert made["skills"]["technical"] == ["SQL", "Python", "Excel"] and made["skills"]["tools"] == []


def test_own_skills_are_the_profiles_then_the_achievements_once_each():
    assert cv.own_skills({"skills": ["SQL", " Python "]}, [{"skills": ["sql", "Excel", ""]}, {"skills": None}]) == ["SQL", "Python", "Excel"]


def test_contact_leaves_out_what_is_not_on_the_profile():
    assert cv.contact({"full_name": "Test Person"}, "") == {"name": "Test Person", "city": "", "phone": "", "email": "", "linkedin": "", "github": ""}


# ---------- applying an edit ----------

LINKED = [achievement(1, work_history_id="j1"), achievement(2, work_history_id="j1"), achievement(3)]


def stored_cv():
    return build(LINKED, [bullet(1), bullet(2), bullet(3)])


def test_an_unchanged_edit_gives_the_same_cv():
    stored = stored_cv()
    assert edit(stored, lambda c: None, achievements=LINKED) == stored


def test_edit_cannot_change_a_fact():
    def change(c):
        c["work"][0] |= {"employer": "Invented Ltd", "start_month": "2001-01-01", "job_title": "Director"}
        c["education"][0] |= {"institution": "Invented University", "grade": "Distinction"}
        c["contact"] = {"name": "Someone Else", "email": "x@invented.test"}
        c["projects"][0] |= {"link": "github.com/someone/else", "where": "Invented University"}
        c["job"] = {"title": "CEO", "company": "Invented"}
        c["gaps"] = ["Invented gap"]
    stored = stored_cv()
    assert edit(stored, change, achievements=LINKED) == stored


def test_edit_changes_wording_order_and_hidden():
    def change(c):
        c["profile"] = "  My own words.  "
        c["work"] = [c["work"][1], c["work"][0]]
        c["work"][1]["bullets"] = [c["work"][1]["bullets"][1] | {"text": "Edited bullet"}, c["work"][1]["bullets"][0] | {"hidden": True}]
        c["work"][0]["hidden"] = True
        c["education"][1]["note"] = "Dissertation on bus arrival times"
        c["projects"][0]["title"] = "A better title"
        c["skills"] = {"technical": ["Python", " ", "SQL"], "tools": [], "languages": ["English (Fluent)"]}
        c["additional"]["lines"] = [{"text": "Typed here", "hidden": True}, {"text": "  "}]
        c["right_to_work"] = {"shown": True, "text": "My own line."}
        c["cover_letter"]["why_you"] = "Because."
        c["section_order"] = ["skills", "work", "education", "projects", "additional"]
    made = edit(stored_cv(), change, achievements=LINKED)
    assert made["profile"] == "My own words."
    assert [(w["employer"], w["hidden"]) for w in made["work"]] == [("Zzqx Foods", True), ("Zzqx Holdings Ltd", False)]
    assert made["work"][1]["bullets"] == [{"text": "Edited bullet", "achievement_id": "a2", "hidden": False},
                                          {"text": "Reworded thing 1 for 10 users", "achievement_id": "a1", "hidden": True}]
    assert made["education"][1]["note"] == "Dissertation on bus arrival times" and made["education"][1]["institution"] == "University of Zzqx"
    assert made["projects"][0]["title"] == "A better title"
    assert made["skills"] == {"technical": ["Python", "SQL"], "tools": [], "languages": ["English (Fluent)"]}
    assert made["additional"] == {"lines": [{"text": "Typed here", "hidden": True}]}
    assert made["right_to_work"] == {"shown": True, "text": "My own line."}
    assert made["cover_letter"] == {"why_them": "Them.", "why_you": "Because.", "what_you_deliver": "This."}
    assert made["section_order"] == ["skills", "work", "education", "projects", "additional"]


def test_a_bullet_naming_another_users_achievement_loses_the_link():
    def change(c):
        c["work"][0]["bullets"].append({"text": "Borrowed", "achievement_id": "someone-elses", "hidden": False})
    made = edit(stored_cv(), change, achievements=LINKED)
    assert made["work"][0]["bullets"][-1] == {"text": "Borrowed", "achievement_id": "", "hidden": False}


def test_an_entry_naming_another_users_row_is_dropped():
    def change(c):
        c["work"].append({"work_history_id": "someone-elses", "employer": "Their Employer", "bullets": []})
        c["education"].append({"education_id": "someone-elses", "institution": "Their University"})
        c["projects"].append({"achievement_id": "someone-elses", "title": "Their project", "bullets": [{"text": "x"}]})
    stored = stored_cv()
    assert edit(stored, change, achievements=LINKED) == stored


def test_a_new_entry_takes_its_facts_from_the_record():
    stored = build(LINKED, [bullet(1)], work=(JOB1,), education=(COURSE1,))

    def change(c):
        c["work"].append({"work_history_id": "j2", "employer": "Typed by the page", "bullets": [{"text": "From my profile", "achievement_id": "a2"}]})
        c["education"].append({"education_id": "c2"})
        c["projects"].append({"achievement_id": "a3", "bullets": [{"text": "A project", "achievement_id": "a3"}]})
    made = edit(stored, change, achievements=LINKED + [achievement(4, education_id="c2")])
    assert (made["work"][1]["employer"], made["work"][1]["job_title"], made["work"][1]["start_month"]) == ("Zzqx Foods", "Intern", "2023-01-01")
    assert made["work"][1]["bullets"] == [{"text": "From my profile", "achievement_id": "a2", "hidden": False}]
    assert (made["education"][1]["institution"], made["education"][1]["grade"], made["education"][1]["note"]) == ("University of Zzqx", "CGPA 8.4/10", "")
    assert (made["projects"][0]["achievement_id"], made["projects"][0]["title"]) == ("a3", "Thing 3")


def test_the_same_entry_twice_is_kept_once():
    def change(c):
        c["work"].append(copy.deepcopy(c["work"][0]))
        c["projects"].append(copy.deepcopy(c["projects"][0]))
    stored = stored_cv()
    assert edit(stored, change, achievements=LINKED) == stored


def test_refresh_recopies_facts_and_contact_and_brings_in_new_records():
    stored = build(LINKED, [bullet(1), bullet(3)], work=(JOB1,), education=(COURSE1,))
    renamed = JOB1 | {"employer": "Zzqx Holdings Limited", "end_month": None, "is_current": True}
    profile = PROFILE | {"phone": "07700 900999", "full_name": "Test Q Person"}
    same = edit(stored, lambda c: None, achievements=LINKED, work=(renamed, JOB2), education=(COURSE1, COURSE2), profile=profile)
    assert same == stored  # a profile change alone never alters a CV
    made = edit(stored, lambda c: None, achievements=LINKED, work=(renamed, JOB2), education=(COURSE1, COURSE2), profile=profile,
                email="new@example.test", refresh=True)
    assert (made["work"][0]["employer"], made["work"][0]["end_month"], made["work"][0]["is_current"]) == ("Zzqx Holdings Limited", None, True)
    assert made["work"][0]["bullets"] == stored["work"][0]["bullets"]
    assert [(w["employer"], w["bullets"], w["hidden"]) for w in made["work"]][1] == ("Zzqx Foods", [], False)
    assert [e["institution"] for e in made["education"]] == ["Zzqx City University", "University of Zzqx"]
    assert (made["contact"]["phone"], made["contact"]["name"], made["contact"]["email"]) == ("07700 900999", "Test Q Person", "new@example.test")


def test_a_removed_record_keeps_its_stored_copy():
    stored = stored_cv()
    made = edit(stored, lambda c: None, achievements=[], work=(), education=(), refresh=True)
    assert [w["employer"] for w in made["work"]] == ["Zzqx Holdings Ltd", "Zzqx Foods"]
    assert [e["institution"] for e in made["education"]] == ["Zzqx City University", "University of Zzqx"]
    assert [p["title"] for p in made["projects"]] == ["Thing 3"]
    assert all(b["achievement_id"] == "" for b in made["work"][0]["bullets"])  # the achievements are gone, the wording stays


@pytest.mark.parametrize("order", [["work", "education"], ["work", "work", "education", "projects", "skills"], "work", None,
                                   ["work", "education", "projects", "skills", "additional", "profile"]])
def test_bad_section_order_keeps_the_stored_one(order):
    stored = stored_cv()

    def change(c):
        c["section_order"] = order
    assert edit(stored, change, achievements=LINKED)["section_order"] == stored["section_order"]


def test_lengths_are_capped():
    def change(c):
        c["profile"] = "p" * 5000
        c["work"][0]["bullets"] = [{"text": "b" * 2000, "achievement_id": "a1"}] * 40
        c["skills"]["technical"] = ["s" * 200] * 100
        c["additional"]["lines"] = [{"text": "l" * 1000}] * 50
        c["right_to_work"]["text"] = "r" * 1000
        c["cover_letter"]["why_them"] = "w" * 9000
        c["education"][0]["note"] = "n" * 1000
    made = edit(stored_cv(), change, achievements=LINKED)
    assert len(made["profile"]) == 1500
    assert len(made["work"][0]["bullets"]) == 12 and len(made["work"][0]["bullets"][0]["text"]) == 600
    assert len(made["skills"]["technical"]) == 40 and len(made["skills"]["technical"][0]) == 60
    assert len(made["additional"]["lines"]) == 12 and len(made["additional"]["lines"][0]["text"]) == 300
    assert len(made["right_to_work"]["text"]) == 300 and len(made["cover_letter"]["why_them"]) == 2500
    assert len(made["education"][0]["note"]) == 300


@pytest.mark.parametrize("edited", [None, "text", [], {"work": "x", "education": 3, "projects": [1, "a"], "skills": [], "additional": [],
                                                        "right_to_work": "on", "cover_letter": "Dear", "profile": 7}])
def test_an_edit_of_the_wrong_shape_empties_rather_than_breaks(edited):
    stored = stored_cv()
    made = cv.merge(stored, edited, profile=PROFILE, email=EMAIL, education=[COURSE1, COURSE2], work_history=[JOB1, JOB2], achievements=LINKED)
    assert made["contact"] == stored["contact"] and made["job"] == stored["job"] and made["section_order"] == stored["section_order"]
    assert (made["work"], made["education"], made["projects"], made["profile"]) == ([], [], [], "")
    assert made["cover_letter"] == {"why_them": "", "why_you": "", "what_you_deliver": ""}


def test_a_base_cv_never_gains_a_letter():
    stored = build(LINKED, [bullet(1)], job=None)

    def change(c):
        c["cover_letter"] = {"why_them": "x", "why_you": "y", "what_you_deliver": "z"}
    assert edit(stored, change, achievements=LINKED)["cover_letter"] is None


# ---------- what a reader sees, and keyword coverage ----------

def test_text_is_what_prints_and_nothing_hidden():
    def change(c):
        c["work"][0]["bullets"][1]["hidden"] = True
        c["work"][1]["hidden"] = True
        c["additional"]["lines"].append({"text": "Hidden line", "hidden": True})
    words = cv.text(edit(stored_cv(), change, achievements=LINKED))
    assert "Reworded thing 1 for 10 users" in words and "Zzqx Holdings Ltd" in words and "Data Scientist" not in words
    assert "Reworded thing 2" not in words and "Zzqx Foods" not in words and "Hidden line" not in words
    assert "Student visa" not in words and "Them." not in words  # the visa line is off; the letter is not the CV
    assert "Zzqx Cloud Practitioner (2025)" in words and "English (Fluent)" in words and "Merit" in words


def test_the_visa_line_counts_once_switched_on():
    def change(c):
        c["right_to_work"]["shown"] = True
    assert "Visa status: Student visa" in cv.text(edit(stored_cv(), change, achievements=LINKED))


@pytest.mark.parametrize("term, text, found", [
    ("SQL", "Built reports in SQL.", True), ("sql", "Built reports in SQL, weekly", True), ("SQL", "Built reports in MySQL", False),
    ("dashboards", "Built a dashboard", True), ("dashboard", "Built dashboards", True), ("process", "Improved three processes", True),
    ("stakeholder management", "Stakeholder management for 14 teams", True), ("stakeholder management", "Managed stakeholders", False),
    ("stakeholder management", "management of stakeholder groups", False),
    ("C++", "Wrote C++ and Python", True), ("C", "Wrote C++ and C#", False), ("C#", "Wrote C++", False), ("C#", "Wrote C# services", True),
    ("Java", "Wrote JavaScript", False), ("Node.js", "Built it in Node.js.", True), ("A/B testing", "Ran A/B testing on prices", True),
    ("Python", "Used Python/SQL daily", True), ("Power BI", "Power-BI dashboards", True), ("bachelor's degree", "Bachelors degree in maths", True),
    ("", "anything", False), ("!!", "anything", False), ("SQL", "", False),
])
def test_has_term(term, text, found):
    assert cv.has_term(term, text) is found


def test_coverage_sorts_each_term_into_one_group():
    achievements = [achievement(1, work_history_id="j1"), achievement(2, uk_version="Built Tableau dashboards for 20 users", skills=["Tableau"]),
                    achievement(3, uk_version="Trained 12 colleagues", skills=[])]
    made = build(achievements, [bullet(1, "Built weekly reports in SQL for 10 users")], keywords=["SQL", "Tableau", "Excel", "Python", "Kubernetes"],
                 profile=PROFILE | {"skills": ["SQL", "Python", "Excel"]}, skills={"technical": ["SQL"], "tools": []})
    assert made["keywords"] == {
        "terms": ["SQL", "Tableau", "Excel", "Python", "Kubernetes"],
        "covered": ["SQL"],                                                    # the words are in the CV
        "available": [{"term": "Tableau", "achievement_ids": ["a2"]},          # an achievement not on the CV shows it
                      {"term": "Excel", "achievement_ids": []},                # only in the skills list
                      {"term": "Python", "achievement_ids": []}],
        "missing": ["Kubernetes"]}


def test_a_hidden_bullet_does_not_cover_a_term():
    achievements = [achievement(1, work_history_id="j1", uk_version="Built Tableau dashboards for 10 users", skills=[])]
    stored = build(achievements, [bullet(1, "Built Tableau dashboards for 10 users")], keywords=["Tableau"], profile=PROFILE | {"skills": []},
                   skills={"technical": [], "tools": []})
    assert stored["keywords"]["covered"] == ["Tableau"]

    def change(c):
        c["work"][0]["bullets"][0]["hidden"] = True
    made = edit(stored, change, achievements=achievements, profile=PROFILE | {"skills": []})
    assert made["keywords"]["covered"] == [] and made["keywords"]["available"] == [{"term": "Tableau", "achievement_ids": ["a1"]}]
    assert made["keywords"]["terms"] == ["Tableau"]


def test_covered_never_lists_a_term_whose_words_are_not_in_the_cv():
    achievements = [achievement(1, work_history_id="j1")]
    made = build(achievements, [bullet(1)], keywords=["SQL", "Tableau", "users"], profile=PROFILE | {"skills": ["SQL"]})
    words = cv.text(made)
    assert made["keywords"]["covered"] and all(cv.has_term(term, words) for term in made["keywords"]["covered"])
    reworded = edit(made, lambda c: c["skills"].update(technical=[]), achievements=achievements, profile=PROFILE | {"skills": ["SQL"]})
    assert "SQL" not in reworded["keywords"]["covered"] and {"term": "SQL", "achievement_ids": []} in reworded["keywords"]["available"]


# ---------- dates ----------

def test_dates():
    assert cv.as_date("2023-07-01") == date(2023, 7, 1) and cv.as_date(date(2023, 7, 1)) == date(2023, 7, 1)
    assert cv.as_date("2023-07-01T00:00:00") == date(2023, 7, 1)
    assert cv.as_date(None) is None and cv.as_date("") is None and cv.as_date("July 2023") is None and cv.as_date(7) is None
    assert cv.long_date(date(2026, 10, 3)) == "3 October 2026"
