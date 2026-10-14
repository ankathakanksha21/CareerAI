"""Building, editing, downloading and deleting a CV through the API. The model is replaced; the
Word and PDF files are real and are read back. The people and employers cannot be real."""
import copy
import uuid
from contextlib import contextmanager
from datetime import date

import pytest

import ai
import cvbuild
import repo
from cvsample import pdf_text, word, word_text
from files import forbid_disk_writes

pytestmark = pytest.mark.db

LIMIT = "You've reached today's limit. It resets at midnight."
AI_FAILED = "The AI did not respond properly. Try again."
GONE = "That item no longer exists"
OLD_FORMAT = "This CV was made before full CVs. Rebuild it to edit or download it."
CV_IN_USE = "This CV is attached to an application. Remove it from the application first."
NO_LETTER = "A base CV has no cover letter."
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
OLD_CONTENT = {"profile": "P", "bullets": [{"text": "Built X", "achievement_id": ""}], "keywords": ["SQL"],
               "cover_letter": {"why_them": "A", "why_you": "B", "what_you_deliver": "C"}, "gaps": []}
LETTER = {"keywords": ["SQL", "Tableau"], "gaps": ["No Tableau yet"],
          "cover_letter": {"why_them": "Your depots need clear reports.", "why_you": "I built one for 15 managers.", "what_you_deliver": "A weekly report."}}
REPORT, MODEL = "Built a SQL delays report used by 15 managers", "Modelled bus arrival times in Python"
LONG = "Wrote a weekly report on depot delays for the regional managers and presented the findings every Monday morning. " * 5


def seed(conn, user) -> dict:
    """A profile with one job, the current course, two achievements (one at the job, one a GitHub project) and a saved job."""
    repo.update_profile(conn, user, full_name="Test Person", university="Zzqx City University", course="MSc Data Science",
                        graduation_date=date(2026, 9, 1), visa_type="student", visa_end_date=date(2027, 1, 30), locations=["Leeds"])
    job = repo.add_entry(conn, user, "work_history", {"employer": "Zzqx Holdings Ltd", "job_title": "Data Analyst", "location": "Pune",
                                                      "country": "India", "start_month": date(2023, 7, 1), "end_month": date(2025, 8, 1)})
    at_work = repo.add_achievements(conn, user, [{"title": "Delays report", "uk_version": "Built a delays report in SQL for 15 managers",
                                                  "skills": ["SQL"], "work_history_id": job["id"]}], "cv")[0]
    project = repo.add_achievements(conn, user, [{"title": "Bus times", "uk_version": "Built a bus arrival model in Python", "skills": ["Python"],
                                                  "source_url": "https://github.com/zzqx-test/bus-times"}], "github")[0]
    saved = repo.add_job(conn, user, title="Junior Analyst", company="Zzqx Retail plc", location=None, url=None,
                         description="We need SQL and Tableau skills for our depot reports. " * 3, summary="s", keywords=[], role_family_id=None)
    return {"job": job, "at_work": at_work, "project": project, "saved": saved}


def body(seeded: dict, **extra) -> dict:
    return {"profile": "Data analyst with logistics reporting experience.",
            "bullets": [{"achievement_id": seeded["at_work"]["id"], "text": REPORT}, {"achievement_id": seeded["project"]["id"], "text": MODEL}],
            "skills": {"technical": ["SQL"], "tools": ["Python"]}} | extra


@pytest.fixture
def seeded(conn, user_a):
    return seed(conn, user_a)


@pytest.fixture
def built(client, stub, seeded):
    """A tailored CV already built for user A's saved job."""
    stub("build_cv", body(seeded))
    stub("job_letter", LETTER)
    r = client.post("/api/ai/cv", json={"job_id": seeded["saved"]["id"]})
    assert r.status_code == 200, r.text
    return r.json()


def state(client):
    return client.get("/api/state").json()


def versions(client):
    return state(client)["cv_versions"]


def edit(client, version, change=lambda c: None, **extra):
    content = copy.deepcopy(version["content"])
    change(content)
    return client.patch(f"/api/cv-versions/{version['id']}", json={"content": content} | extra)


def download(client, version, kind, part="cv"):
    return client.get(f"/api/cv-versions/{version['id']}/download", params={"format": kind, "part": part})


def attach(conn, user, version):
    return repo.add_application(conn, user, {"company": "Zzqx Retail plc", "role": "Junior Analyst", "source": "Company site",
                                             "cv_version_id": version["id"]})


# ---------- building ----------

def test_tailored_cv_is_saved_as_format_two_with_pages(client, built, seeded):
    assert (built["kind"], built["format_version"], built["pages"], built["name"]) == ("tailored", 2, 1, "Junior Analyst, Zzqx Retail plc v1")
    assert built["saved_job_id"] == seeded["saved"]["id"] and built["edited_at"] is None and built["unsupported"] == ""
    content = built["content"]
    assert content["job"] == {"title": "Junior Analyst", "company": "Zzqx Retail plc"} and content["profile"] == "Data analyst with logistics reporting experience."
    assert content["cover_letter"] == LETTER["cover_letter"] and content["gaps"] == ["No Tableau yet"]
    assert content["keywords"]["covered"] == ["SQL"] and content["keywords"]["missing"] == ["Tableau"]
    assert content["section_order"][:2] == ["work", "education"]  # two years and two months of work: experience leads
    saved = versions(client)
    assert [v["id"] for v in saved] == [built["id"]] and saved[0]["content"] == content
    assert state(client)["usage"]["ai"]["used"] == 1


def test_every_fact_equals_the_record_whatever_the_model_returned(client, stub, seeded):
    stub("build_cv", body(seeded, work=[{"employer": "Invented Ltd", "start_month": "2001-01-01"}], education=[{"grade": "Distinction"}],
                          contact={"name": "Someone Else"}))
    stub("job_letter", LETTER | {"job": {"company": "Invented plc"}})
    content = client.post("/api/ai/cv", json={"job_id": seeded["saved"]["id"]}).json()["content"]
    job = content["work"][0]
    assert (job["work_history_id"], job["employer"], job["job_title"], job["location"], job["country"], job["start_month"], job["end_month"],
            job["is_current"]) == (seeded["job"]["id"], "Zzqx Holdings Ltd", "Data Analyst", "Pune", "India", "2023-07-01", "2025-08-01", False)
    assert job["bullets"] == [{"text": REPORT, "achievement_id": seeded["at_work"]["id"], "hidden": False}]
    course = content["education"][0]
    assert (course["institution"], course["qualification"], course["end_month"], course["grade"]) == ("Zzqx City University", "MSc Data Science", "2026-09-01", "")
    assert content["contact"] == {"name": "Test Person", "city": "", "phone": "", "email": "a@example.test", "linkedin": "", "github": ""}
    project = content["projects"][0]
    assert (project["achievement_id"], project["title"], project["link"]) == (seeded["project"]["id"], "Bus times", "github.com/zzqx-test/bus-times")
    assert content["job"] == {"title": "Junior Analyst", "company": "Zzqx Retail plc"} and "Invented" not in str(content) and "2001" not in str(content)
    assert content["right_to_work"] == {"shown": False, "text": "Visa status: Student visa, valid until 30 January 2027."}


def test_base_cv_needs_no_job_and_has_no_letter(client, stub, seeded):
    stub("build_cv", body(seeded))
    letters = stub("job_letter", LETTER)
    made = client.post("/api/ai/cv", json={}).json()
    assert (made["kind"], made["name"], made["saved_job_id"], made["format_version"]) == ("base", "Base CV v1", None, 2)
    assert made["content"]["cover_letter"] is None and made["content"]["job"] is None and made["content"]["keywords"]["terms"] == []
    assert letters == []
    assert client.post("/api/ai/cv", json={"job_id": None}).json()["name"] == "Base CV v2"


def test_the_model_is_given_the_users_own_records(client, stub, seeded):
    calls = stub("build_cv", body(seeded))
    letters = stub("job_letter", LETTER)
    client.post("/api/ai/cv", json={"job_id": seeded["saved"]["id"]})
    profile, education, work_history, achievements, skills, job, today = calls[0]
    assert [w["employer"] for w in work_history] == ["Zzqx Holdings Ltd"] and [e["institution"] for e in education] == ["Zzqx City University"]
    assert {a["id"] for a in achievements} == {seeded["at_work"]["id"], seeded["project"]["id"]} and sorted(skills) == ["Python", "SQL"]
    assert job["id"] == seeded["saved"]["id"] and isinstance(today, date) and letters[0][0]["id"] == seeded["saved"]["id"]


def test_build_stops_at_the_daily_limit(client, stub, seeded, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "1")
    calls = stub("build_cv", body(seeded))
    stub("job_letter", LETTER)
    assert client.post("/api/ai/cv", json={}).status_code == 200
    r = client.post("/api/ai/cv", json={"job_id": seeded["saved"]["id"]})
    assert r.status_code == 429 and r.json()["detail"] == LIMIT
    assert len(calls) == 1 and len(versions(client)) == 1


@pytest.mark.parametrize("failing", ["build_cv", "job_letter"])
def test_nothing_is_saved_when_either_call_fails(client, stub, seeded, failing):
    stub("build_cv", body(seeded))
    stub("job_letter", LETTER)
    stub(failing, ai.AIError(failing))
    r = client.post("/api/ai/cv", json={"job_id": seeded["saved"]["id"]})
    assert r.status_code == 502 and r.json()["detail"] == AI_FAILED
    assert versions(client) == []


def test_build_needs_achievements(client, stub, conn, user_a):
    calls = stub("build_cv", {})
    r = client.post("/api/ai/cv", json={})
    assert r.status_code == 400 and r.json()["detail"] == "Build your profile first."
    assert calls == [] and state(client)["usage"]["ai"]["used"] == 0


def test_build_for_another_users_job_404(client, stub, seeded, conn, user_b, as_user):
    seed(conn, user_b)
    calls = stub("build_cv", body(seeded))
    as_user(user_b)
    r = client.post("/api/ai/cv", json={"job_id": seeded["saved"]["id"]})
    assert r.status_code == 404 and r.json()["detail"] == GONE and calls == []


def test_malformed_job_id_422(client, seeded):
    assert client.post("/api/ai/cv", json={"job_id": "not-an-id"}).status_code == 422


def test_no_connection_is_held_while_the_cv_is_written(client, seeded, monkeypatch):
    import db
    inner, open_now = db.transaction, []

    @contextmanager
    def tracking():
        with inner() as c:
            open_now.append(1)
            try:
                yield c
            finally:
                open_now.pop()
    monkeypatch.setattr(db, "transaction", tracking)

    def write(*args, **kwargs):
        assert open_now == [], "a database transaction was open during the model call"
        return body(seeded)
    monkeypatch.setattr(ai, "build_cv", write)
    assert client.post("/api/ai/cv", json={}).status_code == 200


def test_no_name_or_contact_detail_reaches_the_model(client, seeded, conn, user_a, monkeypatch):
    repo.set_contact(conn, user_a, phone="07700 900123", city="Zzqxtown", linkedin_url="linkedin.com/in/test-person")
    repo.set_github_username(conn, user_a, "zzqx-test")
    prompts = []

    def model(system, user, max_tokens=1500):
        prompts.append(system + user)
        return body(seeded) if '"bullets"' in user else LETTER
    monkeypatch.setattr(ai, "complete_json", model)
    made = client.post("/api/ai/cv", json={"job_id": seeded["saved"]["id"]}).json()
    assert made["content"]["contact"] == {"name": "Test Person", "city": "Zzqxtown", "phone": "07700 900123", "email": "a@example.test",
                                          "linkedin": "linkedin.com/in/test-person", "github": "github.com/zzqx-test"}
    assert len(prompts) == 2
    for private in ("Test Person", "07700", "Zzqxtown", "linkedin", "a@example.test", "zzqx-test/", "visa"):
        assert not any(private in prompt for prompt in prompts), private


# ---------- editing ----------

def test_edit_is_saved_in_place_and_pages_recounted(client, built):
    def change(c):
        c["profile"] = "My own paragraph."
        c["work"][0]["bullets"] = [{"text": LONG, "achievement_id": "", "hidden": False}] * 12
    r = edit(client, built, change, contact_name=" Ms Patel ")
    assert r.status_code == 200
    saved = r.json()
    assert (saved["id"], saved["name"], saved["replaced"], saved["contact_name"]) == (built["id"], built["name"], None, "Ms Patel")
    assert saved["content"]["profile"] == "My own paragraph." and saved["edited_at"] is not None and saved["pages"] >= 2
    assert versions(client)[0]["content"] == saved["content"] and len(versions(client)) == 1

    def hide(c):
        for bullet in c["work"][0]["bullets"]:
            bullet["hidden"] = True
    shorter = edit(client, saved, hide).json()
    assert shorter["pages"] == 1 and shorter["contact_name"] == "Ms Patel"  # a name not sent again is kept
    assert state(client)["usage"]["ai"]["used"] == 1  # editing costs nothing


def test_keywords_follow_the_edit(client, built):
    def change(c):
        c["skills"]["technical"] = []
        c["work"][0]["bullets"][0]["text"] = "Built a Tableau dashboard"
    words = edit(client, built, change).json()["content"]["keywords"]
    assert words["covered"] == ["Tableau"] and [x["term"] for x in words["available"]] == ["SQL"] and words["missing"] == []


def test_editing_a_sent_version_makes_a_new_one_and_leaves_the_old_untouched(client, built, conn, user_a):
    attach(conn, user_a, built)
    before = copy.deepcopy(versions(client)[0])
    r = edit(client, built, lambda c: c.update(profile="Changed after sending."), contact_name="Ms Patel")
    assert r.status_code == 200
    new = r.json()
    assert new["id"] != built["id"] and new["replaced"] == built["id"] and new["name"] == "Junior Analyst, Zzqx Retail plc v2"
    assert (new["kind"], new["saved_job_id"], new["format_version"], new["contact_name"]) == ("tailored", built["saved_job_id"], 2, "Ms Patel")
    assert new["content"]["profile"] == "Changed after sending."
    after = {v["id"]: v for v in versions(client)}
    assert len(after) == 2 and after[built["id"]] == before  # the version that was sent: exactly as it was
    assert state(client)["applications"][0]["cv_version_id"] == built["id"]
    again = edit(client, new, lambda c: c.update(profile="And again.")).json()
    assert again["id"] == new["id"] and again["replaced"] is None  # the new one has not been sent: it changes in place


def test_an_application_attached_while_the_edit_is_worked_out_still_protects_it(client, built, conn, user_a, monkeypatch):
    real = cvbuild.revise

    def slow(*args, **kwargs):
        attach(conn, user_a, built)  # the user logs the application in another tab meanwhile
        return real(*args, **kwargs)
    monkeypatch.setattr(cvbuild, "revise", slow)
    new = edit(client, built, lambda c: c.update(profile="Changed.")).json()
    assert new["replaced"] == built["id"]
    assert {v["id"]: v["content"]["profile"] for v in versions(client)}[built["id"]] == built["content"]["profile"]


def test_edit_cannot_change_facts_or_borrow_another_users_rows(client, built, conn, user_b):
    theirs = seed(conn, user_b)

    def change(c):
        c["work"][0] |= {"employer": "Invented Ltd", "start_month": "2001-01-01"}
        c["work"][0]["bullets"].append({"text": "Borrowed", "achievement_id": theirs["at_work"]["id"], "hidden": False})
        c["work"].append({"work_history_id": theirs["job"]["id"], "employer": "Their Employer", "bullets": []})
        c["projects"].append({"achievement_id": theirs["project"]["id"], "title": "Their project", "bullets": [{"text": "x"}]})
        c["contact"]["email"] = "someone@else.test"
    content = edit(client, built, change).json()["content"]
    assert [(w["employer"], w["start_month"]) for w in content["work"]] == [("Zzqx Holdings Ltd", "2023-07-01")]
    assert content["work"][0]["bullets"][-1] == {"text": "Borrowed", "achievement_id": "", "hidden": False}
    assert [p["title"] for p in content["projects"]] == ["Bus times"] and content["contact"]["email"] == "a@example.test"


def test_refresh_facts_picks_up_a_profile_change(client, built, seeded, conn, user_a):
    repo.update_entry(conn, user_a, "work_history", seeded["job"]["id"], {"employer": "Zzqx Holdings Limited"})
    repo.set_contact(conn, user_a, phone="07700 900123", city="", linkedin_url="")
    untouched = edit(client, built).json()["content"]
    assert untouched["work"][0]["employer"] == "Zzqx Holdings Ltd" and untouched["contact"]["phone"] == ""
    fresh = edit(client, built, refresh_facts=True).json()["content"]
    assert fresh["work"][0]["employer"] == "Zzqx Holdings Limited" and fresh["contact"]["phone"] == "07700 900123"
    assert fresh["work"][0]["bullets"] == built["content"]["work"][0]["bullets"]


@pytest.mark.parametrize("payload", [{}, {"content": "text"}, {"content": []}, {"content": {}, "contact_name": "x" * 121}, {"content": {}, "refresh_facts": "maybe"}])
def test_edit_of_the_wrong_shape_is_422(client, built, payload):
    assert client.patch(f"/api/cv-versions/{built['id']}", json=payload).status_code == 422
    assert versions(client)[0]["content"] == built["content"]


def test_a_version_made_before_this_step_cannot_be_edited_or_downloaded(client, conn, user_a):
    old = repo.add_cv_version(conn, user_a, saved_job_id=None, role_family_id=None, base_name="Role A, Zzqx Holdings Ltd", content=OLD_CONTENT,
                              format_version=1)
    listed = versions(client)[0]
    assert (listed["format_version"], listed["unsupported"], listed["content"]) == (1, "", OLD_CONTENT)
    for r in (client.patch(f"/api/cv-versions/{old['id']}", json={"content": {"profile": "x"}}), download(client, old, "pdf"), download(client, old, "docx")):
        assert r.status_code == 422 and r.json()["detail"] == OLD_FORMAT
    assert versions(client)[0]["content"] == OLD_CONTENT
    assert client.delete(f"/api/cv-versions/{old['id']}").status_code == 204  # it can still be deleted


def test_another_users_version_is_not_found_and_not_changed(client, built, user_b, as_user):
    as_user(user_b)
    for r in (edit(client, built, lambda c: c.update(profile="Theirs now")), client.delete(f"/api/cv-versions/{built['id']}"),
              download(client, built, "pdf"), download(client, built, "docx", "letter")):
        assert r.status_code == 404 and r.json()["detail"] == GONE
    assert versions(client) == []
    as_user(built["user_id"], "Test Person")
    assert versions(client)[0]["content"]["profile"] == built["content"]["profile"]


def test_malformed_and_unknown_version_ids(client, built):
    for method, path in (("patch", "/api/cv-versions/{}"), ("delete", "/api/cv-versions/{}"), ("get", "/api/cv-versions/{}/download?format=pdf")):
        assert client.request(method, path.format("not-an-id"), json={"content": {}}).status_code == 422, method
        assert client.request(method, path.format(uuid.uuid4()), json={"content": {}}).status_code == 404, method


# ---------- deleting ----------

def test_delete_refused_while_attached_then_allowed(client, built, conn, user_a):
    sent = attach(conn, user_a, built)
    r = client.delete(f"/api/cv-versions/{built['id']}")
    assert r.status_code == 409 and r.json()["detail"] == CV_IN_USE
    assert [v["id"] for v in versions(client)] == [built["id"]]
    repo.delete_application(conn, user_a, sent["id"])
    assert client.delete(f"/api/cv-versions/{built['id']}").status_code == 204
    assert versions(client) == [] and client.delete(f"/api/cv-versions/{built['id']}").status_code == 404


# ---------- downloading ----------

def test_download_word_and_pdf(client, built, monkeypatch):
    forbid_disk_writes(monkeypatch)
    as_word, as_pdf = download(client, built, "docx"), download(client, built, "pdf")
    assert as_word.status_code == 200 and as_word.headers["content-type"] == DOCX
    assert as_word.headers["content-disposition"] == 'attachment; filename="Test-Person-CV-Zzqx-Retail-plc.docx"'
    assert as_pdf.status_code == 200 and as_pdf.headers["content-type"] == "application/pdf"
    assert as_pdf.headers["content-disposition"] == 'attachment; filename="Test-Person-CV-Zzqx-Retail-plc.pdf"'
    assert as_word.headers["cache-control"] == as_pdf.headers["cache-control"] == "no-store"
    in_word, in_pdf = word_text(as_word.content), pdf_text(as_pdf.content)
    for said in ("Test Person", "a@example.test", "Zzqx Holdings Ltd, Pune, India", "Jul 2023 to Aug 2025", "Data Analyst", REPORT, MODEL,
                 "Bus times (github.com/zzqx-test/bus-times)", "Zzqx City University", "Technical: SQL", "Tools: Python"):
        assert said in in_word and said in in_pdf, said
    assert "Your depots need clear reports" not in in_word + in_pdf and "Student visa" not in in_word + in_pdf
    assert word(as_word.content).core_properties.author == "Test Person"


def test_downloads_match_the_screen_after_an_edit(client, built):
    def change(c):
        c["work"][0]["bullets"][0]["hidden"] = True
        c["projects"][0]["bullets"][0]["text"] = "Predicted bus arrivals for 12 routes"
        c["right_to_work"]["shown"] = True
        c["section_order"] = ["projects", "work", "education", "skills", "additional"]
    saved = edit(client, built, change).json()
    for text in (word_text(download(client, saved, "docx").content), pdf_text(download(client, saved, "pdf").content)):
        assert REPORT not in text and MODEL not in text
        assert "Predicted bus arrivals for 12 routes" in text and "Visa status: Student visa, valid until 30 January 2027." in text
        assert text.index("Projects") < text.index("Work experience") < text.index("Education")


def test_letter_downloads_with_todays_date_and_who_it_is_to(client, built, conn):
    today = repo.today(conn)
    saved = edit(client, built, contact_name="Ms Patel").json()
    as_word, as_pdf = download(client, saved, "docx", "letter"), download(client, saved, "pdf", "letter")
    assert as_word.headers["content-disposition"] == 'attachment; filename="Test-Person-Cover-Letter-Zzqx-Retail-plc.docx"'
    assert as_pdf.headers["content-disposition"] == 'attachment; filename="Test-Person-Cover-Letter-Zzqx-Retail-plc.pdf"'
    dated = f"{today.day} {today:%B} {today.year}"
    for text in (word_text(as_word.content), pdf_text(as_pdf.content)):
        for said in ("Test Person", dated, "Ms Patel", "Zzqx Retail plc", "Dear Ms Patel,", "Your depots need clear reports.", "I built one for 15 managers.",
                     "A weekly report.", "Yours sincerely,"):
            assert said in text, said
        assert REPORT not in text and "Hiring Manager" not in text
    plain = word_text(download(client, built | {"id": edit(client, saved, contact_name="").json()["id"]}, "docx", "letter").content)
    assert "Dear Hiring Manager," in plain and "Yours faithfully," in plain


def test_base_cv_has_no_letter_to_download(client, stub, seeded):
    stub("build_cv", body(seeded))
    base = client.post("/api/ai/cv", json={}).json()
    r = download(client, base, "pdf", "letter")
    assert r.status_code == 422 and r.json()["detail"] == NO_LETTER
    named = download(client, base, "pdf")
    assert named.status_code == 200 and named.headers["content-disposition"] == 'attachment; filename="Test-Person-CV.pdf"'


@pytest.mark.parametrize("params", [{"format": "doc"}, {"format": "html"}, {}, {"format": "pdf", "part": "everything"}])
def test_download_of_another_format_or_part_is_422(client, built, params):
    assert client.get(f"/api/cv-versions/{built['id']}/download", params=params).status_code == 422


# ---------- contact details and the lines of "Additional information" ----------

@pytest.mark.parametrize("typed, stored", [
    ("https://www.linkedin.com/in/test-person/", "linkedin.com/in/test-person"), ("linkedin.com/in/test-person", "linkedin.com/in/test-person"),
    ("http://uk.linkedin.com/in/test-person?trk=x", "uk.linkedin.com/in/test-person"), ("  LinkedIn.com/in/Test-Person ", "linkedin.com/in/Test-Person"),
    ("", ""),
])
def test_contact_details_saved(client, typed, stored):
    r = client.put("/api/profile/contact", json={"phone": " +44 (0)7700 900-123 ", "city": " Zzqxtown ", "linkedin_url": typed})
    assert r.status_code == 200
    assert (r.json()["phone"], r.json()["city"], r.json()["linkedin_url"], r.json()["email"]) == ("+44 (0)7700 900-123", "Zzqxtown", stored, "a@example.test")
    profile = state(client)["profile"]
    assert (profile["phone"], profile["city"], profile["linkedin_url"]) == ("+44 (0)7700 900-123", "Zzqxtown", stored)


@pytest.mark.parametrize("change, message", [
    ({"linkedin_url": "https://example.test/in/test-person"}, "Enter your LinkedIn address, for example linkedin.com/in/your-name."),
    ({"linkedin_url": "linkedin.com.example.test/in/x"}, "Enter your LinkedIn address, for example linkedin.com/in/your-name."),
    ({"linkedin_url": "linkedin.com"}, "Enter your LinkedIn address, for example linkedin.com/in/your-name."),
    ({"linkedin_url": "javascript:alert(1)//linkedin.com/in/x"}, "Enter your LinkedIn address, for example linkedin.com/in/your-name."),
    ({"phone": "call me maybe"}, "Enter a phone number using digits, spaces and + ( ) - only."),
    ({"phone": "0" * 41}, None), ({"city": "x" * 81}, None), ({"linkedin_url": "linkedin.com/in/" + "x" * 200}, None),
])
def test_contact_details_refused(client, change, message):
    r = client.put("/api/profile/contact", json={"phone": "", "city": "", "linkedin_url": ""} | change)
    assert r.status_code == 422
    if message:
        assert r.json()["detail"][0]["msg"].endswith(message)
    assert state(client)["profile"]["phone"] == "" and state(client)["profile"]["linkedin_url"] == ""


def test_additional_lines_saved_and_capped(client):
    r = client.put("/api/profile/additional", json={"lines": [" Zzqx Cloud Practitioner (2025) ", "", "Volunteer tutor", "volunteer tutor"]})
    assert r.status_code == 200 and r.json()["additional"] == ["Zzqx Cloud Practitioner (2025)", "Volunteer tutor"] and r.json()["email"] == "a@example.test"
    assert state(client)["profile"]["additional"] == ["Zzqx Cloud Practitioner (2025)", "Volunteer tutor"]
    assert client.put("/api/profile/additional", json={"lines": ["x"] * 13}).status_code == 422
    assert client.put("/api/profile/additional", json={"lines": ["x" * 201]}).status_code == 422
    assert client.put("/api/profile/additional", json={}).status_code == 422
    assert state(client)["profile"]["additional"] == ["Zzqx Cloud Practitioner (2025)", "Volunteer tutor"]


def test_one_users_contact_details_are_not_anothers(client, user_b, as_user):
    client.put("/api/profile/contact", json={"phone": "07700 900123", "city": "Zzqxtown", "linkedin_url": ""})
    client.put("/api/profile/additional", json={"lines": ["Volunteer tutor"]})
    as_user(user_b)
    theirs = state(client)["profile"]
    assert (theirs["phone"], theirs["city"], theirs["additional"]) == ("", "", [])


def test_contact_and_additional_lines_appear_on_the_next_cv(client, stub, seeded):
    client.put("/api/profile/contact", json={"phone": "07700 900123", "city": "Zzqxtown", "linkedin_url": "linkedin.com/in/test-person"})
    client.put("/api/profile/additional", json={"lines": ["Zzqx Cloud Practitioner (2025)"]})
    stub("build_cv", body(seeded))
    made = client.post("/api/ai/cv", json={}).json()
    assert made["content"]["contact"]["phone"] == "07700 900123" and made["content"]["contact"]["linkedin"] == "linkedin.com/in/test-person"
    assert made["content"]["additional"] == {"lines": [{"text": "Zzqx Cloud Practitioner (2025)", "hidden": False}]}
    text = pdf_text(download(client, made, "pdf").content)
    assert "Zzqxtown | 07700 900123 | a@example.test | linkedin.com/in/test-person" in text and "Zzqx Cloud Practitioner (2025)" in text


# ---------- what the PDF cannot show ----------

def test_versions_say_which_characters_the_pdf_cannot_show(client, built):
    def change(c):
        c["profile"] = "Saved ₹5 lakh a year."
        c["cover_letter"]["why_you"] = "I studied at 中文 University."
    saved = edit(client, built, change, contact_name="Ms 张").json()
    assert saved["unsupported"] == "₹张中文"
    assert versions(client)[0]["unsupported"] == "₹张中文"
    assert "Saved ?5 lakh a year." in pdf_text(download(client, saved, "pdf").content)
    assert "Saved ₹5 lakh a year." in word_text(download(client, saved, "docx").content)
