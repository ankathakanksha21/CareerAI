from datetime import date

import pytest

import repo

pytestmark = pytest.mark.db

CONTENT = {"profile": "P", "education": [], "work": [{"employer": "Zzqx Holdings Ltd", "start_month": date(2023, 7, 1), "bullets": []}]}
STORED = {"profile": "P", "education": [], "work": [{"employer": "Zzqx Holdings Ltd", "start_month": "2023-07-01", "bullets": []}]}


def job(conn, user, **kw):
    fields = dict(title="Role A", company="Zzqx Holdings Ltd", location=None, url=None, description="Analyse data. " * 5,
                  summary="A summary", keywords=[], role_family_id=None) | kw
    return repo.add_job(conn, user, **fields)


def cv(conn, user, **kw):
    fields = dict(saved_job_id=None, role_family_id=None, base_name="Role A, Zzqx Holdings Ltd", content=CONTENT) | kw
    return repo.add_cv_version(conn, user, **fields)


def application(conn, user, **kw):
    return repo.add_application(conn, user, {"company": "Zzqx Holdings Ltd", "role": "Role A", "source": "Company site"} | kw)


# ---------- adding ----------

def test_new_version_is_format_two_with_kind_and_pages(conn, user_a):
    j = job(conn, user_a)
    saved = cv(conn, user_a, saved_job_id=j["id"], pages=2, contact_name="Ms Patel")
    assert (saved["kind"], saved["format_version"], saved["pages"], saved["contact_name"]) == ("tailored", 2, 2, "Ms Patel")
    assert saved["edited_at"] is None and saved["saved_job_id"] == j["id"]
    base = cv(conn, user_a, base_name="Base CV", kind="base")
    assert (base["kind"], base["name"], base["saved_job_id"], base["pages"]) == ("base", "Base CV v1", None, None)


def test_dates_in_the_content_are_stored_as_text(conn, user_a):
    saved = cv(conn, user_a)
    assert saved["content"] == STORED
    assert repo.get_cv_version(conn, user_a, saved["id"])["content"] == STORED


def test_base_versions_number_on_their_own(conn, user_a):
    j = job(conn, user_a)
    assert cv(conn, user_a, saved_job_id=j["id"])["name"] == "Role A, Zzqx Holdings Ltd v1"
    assert cv(conn, user_a, base_name="Base CV", kind="base")["name"] == "Base CV v1"
    assert cv(conn, user_a, saved_job_id=j["id"])["name"] == "Role A, Zzqx Holdings Ltd v2"
    assert cv(conn, user_a, base_name="Base CV", kind="base")["name"] == "Base CV v2"


def test_number_follows_the_highest_not_the_count(conn, user_a):
    first, second = cv(conn, user_a), cv(conn, user_a)
    assert repo.delete_cv_version(conn, user_a, first["id"]) is True
    assert second["name"] == "Role A, Zzqx Holdings Ltd v2"
    assert cv(conn, user_a)["name"] == "Role A, Zzqx Holdings Ltd v3"


def test_a_name_that_only_begins_the_same_is_another_cv(conn, user_a):
    cv(conn, user_a, base_name="Role A, Zzqx Holdings Ltd UK")
    cv(conn, user_a, base_name="Role A, Zzqx Holdings Ltd UK")
    assert cv(conn, user_a)["name"] == "Role A, Zzqx Holdings Ltd v1"


def test_numbering_is_per_user(conn, user_a, user_b):
    cv(conn, user_a)
    assert cv(conn, user_b)["name"] == "Role A, Zzqx Holdings Ltd v1"


def test_a_percent_sign_in_a_name_is_only_a_character(conn, user_a):
    cv(conn, user_a, base_name="Role A, Zzqx 100% Ltd")
    assert cv(conn, user_a, base_name="Role A, Zzqx 100% Ltd")["name"] == "Role A, Zzqx 100% Ltd v2"
    assert cv(conn, user_a, base_name="Role A, Zzqx 1")["name"] == "Role A, Zzqx 1 v1"


def test_other_users_job_is_not_linked(conn, user_a, user_b):
    theirs = job(conn, user_b)
    assert cv(conn, user_a, saved_job_id=theirs["id"])["saved_job_id"] is None


# ---------- editing ----------

def test_update_changes_content_and_marks_edited(conn, user_a):
    saved = cv(conn, user_a, pages=2)
    updated = repo.update_cv_version(conn, user_a, saved["id"], content={"profile": "Edited"}, pages=3, contact_name="Ms Patel")
    assert (updated["content"], updated["pages"], updated["contact_name"]) == ({"profile": "Edited"}, 3, "Ms Patel")
    assert updated["edited_at"] is not None and updated["name"] == saved["name"] and updated["id"] == saved["id"]


def test_update_other_users_version_changes_nothing(conn, user_a, user_b):
    saved = cv(conn, user_a, pages=2)
    assert repo.update_cv_version(conn, user_b, saved["id"], content={"profile": "Theirs"}, pages=9, contact_name="X") is None
    kept = repo.get_cv_version(conn, user_a, saved["id"])
    assert (kept["content"], kept["pages"], kept["contact_name"], kept["edited_at"]) == (STORED, 2, "", None)


# ---------- in use, and deleting ----------

def test_in_use_only_for_the_owners_application(conn, user_a, user_b):
    saved = cv(conn, user_a)
    assert repo.cv_version_in_use(conn, user_a, saved["id"]) is False
    application(conn, user_b, cv_version_id=saved["id"])  # stored without the link: it is not their CV
    assert repo.cv_version_in_use(conn, user_a, saved["id"]) is False
    application(conn, user_a, cv_version_id=saved["id"])
    assert repo.cv_version_in_use(conn, user_a, saved["id"]) is True
    assert repo.cv_version_in_use(conn, user_b, saved["id"]) is False


def test_delete_refused_while_an_application_points_at_it(conn, user_a):
    saved = cv(conn, user_a)
    sent = application(conn, user_a, cv_version_id=saved["id"])
    assert repo.delete_cv_version(conn, user_a, saved["id"]) is False
    assert repo.get_cv_version(conn, user_a, saved["id"]) is not None
    repo.update_application(conn, user_a, sent["id"], {"cv_version_id": None})
    assert repo.delete_cv_version(conn, user_a, saved["id"]) is True
    assert repo.get_cv_version(conn, user_a, saved["id"]) is None


def test_delete_other_users_version_returns_none(conn, user_a, user_b):
    saved = cv(conn, user_a)
    assert repo.delete_cv_version(conn, user_b, saved["id"]) is None
    assert repo.get_cv_version(conn, user_a, saved["id"]) is not None


def test_delete_a_version_that_does_not_exist_returns_none(conn, user_a):
    assert repo.delete_cv_version(conn, user_a, "00000000-0000-0000-0000-000000000000") is None
