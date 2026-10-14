"""What a CV and a cover letter print, in what order. Pure functions, no database."""
from datetime import date

import pytest

import cvprint
from cvsample import BLOCKS, content

TODAY = date(2026, 10, 13)


def kinds(blocks, kind):
    return [b[1] for b in blocks if b[0] == kind]


# ---------- the CV ----------

def test_the_sample_cv_prints_exactly_this():
    assert cvprint.blocks(content()) == BLOCKS


def test_sections_print_in_the_chosen_order():
    blocks = cvprint.blocks(content(section_order=["skills", "work", "additional", "projects", "education"]))
    assert kinds(blocks, "heading") == ["Personal profile", "Skills", "Work experience", "Additional information", "Projects", "Education"]
    assert blocks[:2] == BLOCKS[:2]  # the name and contact line always lead


def test_a_section_left_out_of_the_order_still_prints():
    assert kinds(cvprint.blocks(content(section_order=["work", "nonsense"])), "heading") == [
        "Personal profile", "Work experience", "Education", "Projects", "Skills", "Additional information"]


def test_hidden_bullets_entries_and_lines_are_not_printed():
    c = content()
    c["work"][0]["bullets"][0]["hidden"] = True
    c["work"][1]["hidden"] = True
    c["education"][1]["hidden"] = True
    c["additional"]["lines"].append({"text": "Hidden line", "hidden": True})
    printed = str(cvprint.blocks(c))
    for gone in ("Built a weekly delays report", "Zzqx Foods", "Intern", "University of Zzqx", "BTech", "Hidden line"):
        assert gone not in printed, gone
    assert "Automated a three-spreadsheet merge" in printed and "Zzqx City University" in printed


@pytest.mark.parametrize("change, heading", [
    ({"work": []}, "Work experience"), ({"projects": []}, "Projects"), ({"education": []}, "Education"),
    ({"skills": {"technical": [], "tools": [], "languages": []}}, "Skills"), ({"additional": {"lines": []}}, "Additional information"),
    ({"profile": "  "}, "Personal profile"),
])
def test_an_empty_section_prints_no_heading(change, heading):
    headings = kinds(cvprint.blocks(content(**change)), "heading")
    assert heading not in headings and len(headings) == 5


def test_a_section_with_everything_hidden_prints_no_heading():
    c = content()
    c["projects"][0]["hidden"] = True
    c["additional"]["lines"][0]["hidden"] = True
    for job in c["work"]:
        job["hidden"] = True
    assert kinds(cvprint.blocks(c), "heading") == ["Personal profile", "Education", "Skills"]


def test_a_project_with_no_bullet_showing_is_not_printed():
    c = content()
    c["projects"][0]["bullets"][0]["hidden"] = True
    assert "Projects" not in kinds(cvprint.blocks(c), "heading") and "Bus arrival predictor" not in str(cvprint.blocks(c))


def test_a_job_with_no_bullets_still_prints_its_line():
    assert ("entry", "Zzqx Foods", "") in cvprint.blocks(content()) and ("sub", "Intern") in cvprint.blocks(content())


@pytest.mark.parametrize("entry, expected", [
    ({"start_month": "2023-07-01", "end_month": "2025-08-01"}, "Jul 2023 to Aug 2025"),
    ({"start_month": "2023-07-01", "is_current": True}, "Jul 2023 to present"),
    ({"start_month": date(2023, 7, 1)}, "From Jul 2023"),
    ({"end_month": "2025-08-01"}, "Until Aug 2025"),
    ({"is_current": True}, "Current"),
    ({}, ""), ({"start_month": "nonsense", "end_month": None}, ""),
])
def test_dates_print_as_months(entry, expected):
    assert cvprint.period(entry) == expected


def test_a_course_with_only_its_end_shows_that_month():
    assert cvprint.period({"end_month": "2026-09-01"}, "{}") == "Sep 2026"


@pytest.mark.parametrize("country, shown", [("India", "University of Zzqx, India"), ("United Kingdom", "University of Zzqx"),
                                            ("uk", "University of Zzqx"), ("Scotland", "University of Zzqx"), ("", "University of Zzqx")])
def test_only_an_overseas_institution_names_its_country(country, shown):
    c = content()
    c["education"] = [c["education"][1] | {"country": country}]
    assert cvprint.blocks(c)[5][1] == shown


def test_project_line_carries_where_and_the_link():
    c = content()
    c["projects"] = [c["projects"][0] | {"where": "Zzqx City University"}, c["projects"][0] | {"achievement_id": "a4", "link": "", "title": "Mess app"},
                     c["projects"][0] | {"achievement_id": "a5", "title": ""}]
    assert [b[1] for b in cvprint.blocks(c) if b[0] == "entry"][-3:] == [
        "Bus arrival predictor, Zzqx City University (github.com/zarvin-q/bus-times)", "Mess app", "github.com/zarvin-q/bus-times"]


def test_right_to_work_prints_last_and_only_when_shown():
    assert "Student visa" not in str(cvprint.blocks(content()))
    blocks = cvprint.blocks(content(right_to_work={"shown": True, "text": "Visa status: Student visa, valid until 30 January 2027."}))
    assert blocks[-2:] == [("line", "Zzqx Cloud Practitioner (2025)"), ("line", "Visa status: Student visa, valid until 30 January 2027.")]
    alone = cvprint.blocks(content(additional={"lines": []}, right_to_work={"shown": True, "text": "My line."}))
    assert alone[-2:] == [("heading", "Additional information"), ("line", "My line.")]
    assert "Additional information" not in kinds(cvprint.blocks(content(additional={"lines": []}, right_to_work={"shown": True, "text": " "})), "heading")


def test_contact_line_leaves_out_what_is_blank():
    c = content(contact={"name": "Zarvin Quillfeather", "city": "", "phone": " ", "email": "zarvin@example.test", "linkedin": "", "github": ""})
    assert cvprint.blocks(c)[:2] == [("name", "Zarvin Quillfeather"), ("contact", "zarvin@example.test")]
    bare = cvprint.blocks(content(contact={"name": "", "city": "", "phone": "", "email": "", "linkedin": "", "github": ""}))
    assert bare[0] == ("heading", "Personal profile")


def test_line_breaks_and_control_characters_become_spaces():
    c = content(profile="First line.\nSecond\tline.\x07 End here.  ")
    assert ("para", "First line. Second line. End here.") in cvprint.blocks(c)
    assert cvprint.clean("José") == "José" and cvprint.clean(None) == "" and cvprint.clean("a\ud800b￾") == "ab"


def test_a_cv_of_the_wrong_shape_prints_what_it_can():
    assert cvprint.blocks({}) == []
    assert cvprint.blocks({"profile": "P", "work": [None, "x", {"employer": "Zzqx Foods", "bullets": [None, {"text": "Did X"}]}]}) == [
        ("heading", "Personal profile"), ("para", "P"), ("heading", "Work experience"), ("entry", "Zzqx Foods", ""), ("bullet", "Did X")]


# ---------- the cover letter ----------

def test_letter_to_hiring_manager_is_yours_faithfully():
    assert cvprint.letter_blocks(content(), "", TODAY) == [
        BLOCKS[0], BLOCKS[1], ("gap", ""), ("line", "13 October 2026"), ("gap", ""), ("line", "Hiring Manager"), ("line", "Zzqx Retail plc"),
        ("gap", ""), ("line", "Dear Hiring Manager,"), ("gap", ""),
        ("para", "Your depot network is growing and needs clear reporting."), ("para", "I built a report used by 15 managers."),
        ("para", "A weekly findings report in my first month."),
        ("line", "Yours faithfully,"), ("gap", ""), ("line", "Zarvin Quillfeather")]


def test_letter_to_a_name_is_yours_sincerely():
    blocks = cvprint.letter_blocks(content(), "  Ms Patel ", TODAY)
    assert ("line", "Ms Patel") in blocks and ("line", "Dear Ms Patel,") in blocks and ("line", "Yours sincerely,") in blocks
    assert "Hiring Manager" not in str(blocks) and "faithfully" not in str(blocks)


def test_letter_carries_the_date_given():
    assert ("line", "3 January 2027") in cvprint.letter_blocks(content(), "", date(2027, 1, 3))


def test_letter_without_a_company_leaves_that_line_out():
    blocks = cvprint.letter_blocks(content(job=None), "", TODAY)
    assert blocks[5:8] == [("line", "Hiring Manager"), ("gap", ""), ("line", "Dear Hiring Manager,")]


# ---------- file names and titles ----------

@pytest.mark.parametrize("name, company, part, extension, expected", [
    ("Zarvin Quillfeather", "Zzqx Retail plc", "cv", "docx", "Zarvin-Quillfeather-CV-Zzqx-Retail-plc.docx"),
    ("Zarvin Quillfeather", "Zzqx Retail plc", "letter", "pdf", "Zarvin-Quillfeather-Cover-Letter-Zzqx-Retail-plc.pdf"),
    ("José Nuñez", "Zzqx & Søn", "cv", "pdf", "Jose-Nunez-CV-Zzqx-Son.pdf"),
    ("Łukasz Örn-Weiß", "", "cv", "pdf", "Lukasz-Orn-Weiss-CV.pdf"),
    ("张伟", "Zzqx Retail", "cv", "pdf", "CV-Zzqx-Retail.pdf"),
    ("", "", "cv", "docx", "CV.docx"),
    ("../../etc/passwd", 'a"b\r\nc', "cv", "pdf", "etc-passwd-CV-a-b-c.pdf"),
])
def test_file_names(name, company, part, extension, expected):
    c = content(job={"title": "Role A", "company": company} if company else None)
    c["contact"]["name"] = name
    assert cvprint.file_name(c, part, extension) == expected


def test_a_very_long_name_is_cut():
    c = content(job={"title": "Role A", "company": "Zzqx " * 60})
    name = cvprint.file_name(c, "cv", "pdf")
    assert len(name) <= 124 and name.endswith(".pdf") and not name[:-4].endswith("-")


def test_titles():
    assert cvprint.title(content(), "cv") == "Zarvin Quillfeather CV"
    assert cvprint.title(content(), "letter") == "Zarvin Quillfeather cover letter"
