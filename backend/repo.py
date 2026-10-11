"""All SQL lives here. Every function takes the caller's user_id and touches only that
user's rows, so no query can run without saying whose data it is.

Rows come back as plain dicts: ids as str, dates as datetime.date, timestamps as datetime."""
import uuid
from datetime import date

from psycopg.types.json import Jsonb


def _row(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()}


def _rows(cursor) -> list[dict]:
    return [_row(r) for r in cursor.fetchall()]


# ---------- profile ----------

def _profile(row: dict) -> dict:
    p = _row(row)
    return p | {"first_name": (p["full_name"].split() or [""])[0]}


def get_or_create_profile(conn, user_id, full_name: str) -> dict:
    conn.execute("insert into profiles (user_id, full_name) values (%s, %s) on conflict (user_id) do nothing",
                 (user_id, full_name.strip()))
    return _profile(conn.execute("select * from profiles where user_id = %s", (user_id,)).fetchone())


def update_profile(conn, user_id, *, full_name: str, university: str, course: str, graduation_date: date,
                   visa_type: str, visa_end_date: date, locations: list[str]) -> dict:
    values = (full_name.strip(), university.strip(), course.strip(), graduation_date.replace(day=1),
              visa_type, visa_end_date, [x.strip() for x in locations if x.strip()])
    row = conn.execute(
        "insert into profiles (user_id, full_name, university, course, graduation_date, visa_type, visa_end_date, locations) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s) "
        "on conflict (user_id) do update set full_name = excluded.full_name, university = excluded.university, "
        "course = excluded.course, graduation_date = excluded.graduation_date, visa_type = excluded.visa_type, "
        "visa_end_date = excluded.visa_end_date, locations = excluded.locations, updated_at = now() returning *",
        (user_id, *values)).fetchone()
    return _profile(row)


def set_pitch(conn, user_id, pitch: str) -> None:
    conn.execute("update profiles set pitch = %s, updated_at = now() where user_id = %s", (pitch, user_id))


def details_complete(profile: dict) -> bool:
    """True once the user has filled in the facts the app cannot work without."""
    texts = (profile.get("university"), profile.get("course"), profile.get("visa_type"))
    return (all(isinstance(t, str) and t.strip() for t in texts)
            and bool(profile.get("graduation_date")) and bool(profile.get("visa_end_date")) and bool(profile.get("locations")))


# ---------- achievements ----------

def list_achievements(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from achievements where user_id = %s order by created_at desc, id", (user_id,)))


def add_achievements(conn, user_id, items: list[dict], source: str) -> list[dict]:
    saved = []
    for item in items:
        saved.append(_row(conn.execute(
            "insert into achievements (user_id, title, raw, uk_version, skills, outcome, scale, context_note, source) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
            (user_id, item["title"], item.get("raw", ""), item["uk_version"], item.get("skills") or [],
             item.get("outcome", ""), item.get("scale", ""), item.get("context_note", ""), source)).fetchone()))
    return saved


def get_achievement(conn, user_id, achievement_id) -> dict | None:
    return _row(conn.execute("select * from achievements where id = %s and user_id = %s", (achievement_id, user_id)).fetchone())


def delete_achievement(conn, user_id, achievement_id) -> bool:
    return conn.execute("delete from achievements where id = %s and user_id = %s", (achievement_id, user_id)).rowcount == 1


# ---------- role families ----------

def list_families(conn, user_id) -> list[dict]:
    return _rows(conn.execute(
        "select * from role_families where user_id = %s "
        "order by array_position(array['direct', 'near', 'stretch'], fit), overlap desc, name", (user_id,)))


def sync_families(conn, user_id, families: list[dict]) -> list[dict]:
    """Replace the user's suggested families with a fresh list, matched by name ignoring case.
    Existing families keep their id and "targeted" tick. One that is no longer suggested is
    removed only if it is untargeted and nothing (application, CV, saved job) points at it."""
    fresh = {}
    for f in families:
        fresh.setdefault(f["name"].strip().lower(), f)  # first spelling wins
    for key, f in fresh.items():
        conn.execute(
            "insert into role_families (user_id, name, fit, overlap, uk_titles, why, needs) values (%s, %s, %s, %s, %s, %s, %s) "
            "on conflict (user_id, lower(name)) do update set fit = excluded.fit, overlap = excluded.overlap, "
            "uk_titles = excluded.uk_titles, why = excluded.why, needs = excluded.needs",
            (user_id, f["name"].strip(), f["fit"], f["overlap"], f.get("uk_titles") or [], f.get("why", ""), Jsonb(f.get("needs") or [])))
    conn.execute(
        "delete from role_families f where f.user_id = %s and not f.targeted and not (lower(f.name) = any(%s)) "
        "and not exists (select 1 from applications a where a.role_family_id = f.id) "
        "and not exists (select 1 from cv_versions c where c.role_family_id = f.id) "
        "and not exists (select 1 from saved_jobs j where j.role_family_id = f.id)",
        (user_id, list(fresh)))
    return list_families(conn, user_id)


def set_family_targeted(conn, user_id, family_id, targeted: bool) -> dict | None:
    return _row(conn.execute("update role_families set targeted = %s where id = %s and user_id = %s returning *",
                             (targeted, family_id, user_id)).fetchone())


# ---------- references to the user's other rows ----------

def _own(conn, user_id, table: str, row_id):
    """row_id if it names one of this user's rows in `table`, else None. Stops a row
    from pointing at something that belongs to someone else or no longer exists."""
    if row_id is None:
        return None
    found = conn.execute(f"select id from {table} where id = %s and user_id = %s", (row_id, user_id)).fetchone()
    return found["id"] if found else None


# ---------- saved jobs ----------

def list_jobs(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from saved_jobs where user_id = %s order by created_at desc, id", (user_id,)))


def get_job(conn, user_id, job_id) -> dict | None:
    return _row(conn.execute("select * from saved_jobs where id = %s and user_id = %s", (job_id, user_id)).fetchone())


def add_job(conn, user_id, *, title: str, company: str, location, url, description: str, summary: str,
            keywords: list[str], role_family_id) -> dict:
    return _row(conn.execute(
        "insert into saved_jobs (user_id, title, company, location, url, description, summary, keywords, role_family_id) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (user_id, title, company, location, url, description, summary, keywords or [],
         _own(conn, user_id, "role_families", role_family_id))).fetchone())


def delete_job(conn, user_id, job_id) -> bool:
    return conn.execute("delete from saved_jobs where id = %s and user_id = %s", (job_id, user_id)).rowcount == 1


# ---------- CV versions ----------

def list_cv_versions(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from cv_versions where user_id = %s order by created_at desc, name desc", (user_id,)))


def get_cv_version(conn, user_id, cv_version_id) -> dict | None:
    return _row(conn.execute("select * from cv_versions where id = %s and user_id = %s", (cv_version_id, user_id)).fetchone())


def add_cv_version(conn, user_id, *, saved_job_id, role_family_id, base_name: str, content: dict) -> dict:
    """Save a tailored CV. Versions are numbered per job: "<base_name> v1", "v2", ..."""
    job_id = _own(conn, user_id, "saved_jobs", saved_job_id)
    n = conn.execute("select count(*) as n from cv_versions where user_id = %s and saved_job_id is not distinct from %s",
                     (user_id, job_id)).fetchone()["n"]
    return _row(conn.execute(
        "insert into cv_versions (user_id, name, saved_job_id, role_family_id, content) values (%s, %s, %s, %s, %s) returning *",
        (user_id, f"{base_name} v{n + 1}", job_id, _own(conn, user_id, "role_families", role_family_id), Jsonb(content))).fetchone())


# ---------- STAR stories ----------

def list_stories(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from stories where user_id = %s order by created_at desc, id", (user_id,)))


def add_story(conn, user_id, achievement_id, story: dict) -> dict:
    fields = ("title", "competency", "situation", "task", "action", "result", "strength", "tip")
    return _row(conn.execute(
        f"insert into stories (user_id, achievement_id, {', '.join(fields)}) values (%s, %s, {', '.join(['%s'] * len(fields))}) returning *",
        (user_id, _own(conn, user_id, "achievements", achievement_id), *(story.get(f, "") for f in fields))).fetchone())


# ---------- applications ----------

APPLICATION_FIELDS = ("company", "role", "role_family_id", "cv_version_id", "saved_job_id", "source", "stage",
                      "applied_on", "posted_on", "job_url", "contact", "notes", "sponsor_licence", "follow_up_on")
_REFERENCES = {"role_family_id": "role_families", "cv_version_id": "cv_versions", "saved_job_id": "saved_jobs"}


def _application_values(conn, user_id, fields: dict) -> dict:
    unknown = set(fields) - set(APPLICATION_FIELDS)
    if unknown:
        raise ValueError(f"not application fields: {sorted(unknown)}")
    return {k: _own(conn, user_id, _REFERENCES[k], v) if k in _REFERENCES else v for k, v in fields.items()}


def list_applications(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from applications where user_id = %s order by applied_on desc, created_at desc, id", (user_id,)))


def add_application(conn, user_id, fields: dict) -> dict:
    # a field left out, or given as None where the column has a default (stage, applied_on), takes the default
    values = {k: v for k, v in _application_values(conn, user_id, fields).items() if v is not None}
    columns = ["user_id", *values]
    return _row(conn.execute(
        f"insert into applications ({', '.join(columns)}) values ({', '.join(['%s'] * len(columns))}) returning *",
        (user_id, *values.values())).fetchone())


def update_application(conn, user_id, app_id, fields: dict) -> dict | None:
    values = _application_values(conn, user_id, fields)
    assignments = ", ".join([f"{k} = %s" for k in values] + ["updated_at = now()"])
    return _row(conn.execute(f"update applications set {assignments} where id = %s and user_id = %s returning *",
                             (*values.values(), app_id, user_id)).fetchone())


def delete_application(conn, user_id, app_id) -> bool:
    return conn.execute("delete from applications where id = %s and user_id = %s", (app_id, user_id)).rowcount == 1


# ---------- journal ----------

def list_journal(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from journal_entries where user_id = %s order by created_at desc, id", (user_id,)))


def add_journal_entry(conn, user_id, *, type: str, title: str, with_whom: str, summary: str, points, actions, scores=None) -> dict:
    return _row(conn.execute(
        "insert into journal_entries (user_id, type, title, with_whom, summary, points, actions, scores) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (user_id, type, title, with_whom, summary, Jsonb(list(points)), Jsonb(list(actions)),
         Jsonb(scores) if scores is not None else None)).fetchone())


# ---------- everything one user owns ----------

def load_state(conn, user_id) -> dict:
    return {
        "achievements": list_achievements(conn, user_id),
        "role_families": list_families(conn, user_id),
        "saved_jobs": list_jobs(conn, user_id),
        "cv_versions": list_cv_versions(conn, user_id),
        "stories": list_stories(conn, user_id),
        "applications": list_applications(conn, user_id),
        "journal": list_journal(conn, user_id),
    }
