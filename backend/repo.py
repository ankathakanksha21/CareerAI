"""All SQL lives here. Every function takes the caller's user_id and touches only that
user's rows, so no query can run without saying whose data it is.

Rows come back as plain dicts: ids as str, dates as datetime.date, timestamps as datetime."""
import json
import re
import uuid
from datetime import date, timedelta

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
    # the course typed here is the user's first education entry, kept in step with it. A start month
    # they added that now falls after the graduation month is cleared rather than left impossible
    conn.execute(
        "insert into education (user_id, institution, qualification, end_month, country, from_details) "
        "values (%s, %s, %s, %s, 'United Kingdom', true) "
        "on conflict (user_id) where from_details do update set institution = excluded.institution, "
        "qualification = excluded.qualification, end_month = excluded.end_month, updated_at = now(), "
        "start_month = case when education.start_month > excluded.end_month then null else education.start_month end",
        (user_id, values[1], values[2], values[3]))
    return _profile(row)


def set_pitch(conn, user_id, pitch: str) -> None:
    conn.execute("update profiles set pitch = %s, updated_at = now() where user_id = %s", (pitch, user_id))


def _tidy_skills(skills: list[str], languages: list[dict]) -> tuple[list[str], list[dict]]:
    """Trimmed, without blanks, and without a second spelling of the same skill or language."""
    kept, seen = [], set()
    for skill in skills:
        name = (skill or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            kept.append(name)
    spoken, seen = [], set()
    for item in languages:
        name = (item.get("language") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            spoken.append({"language": name, "level": (item.get("level") or "").strip()})
    return kept, spoken


def set_skills(conn, user_id, skills: list[str], languages: list[dict]) -> dict:
    """Replace the user's skills and spoken languages. Returns the profile."""
    skills, languages = _tidy_skills(skills, languages)
    return _profile(conn.execute(
        "insert into profiles (user_id, skills, languages) values (%s, %s, %s) on conflict (user_id) do update "
        "set skills = excluded.skills, languages = excluded.languages, updated_at = now() returning *",
        (user_id, skills, Jsonb(languages))).fetchone())


def add_skills(conn, user_id, skills: list[str], languages: list[dict]) -> dict:
    """Add skills and languages the user does not already have, ignoring case. Returns the profile."""
    row = conn.execute("select skills, languages from profiles where user_id = %s", (user_id,)).fetchone() or {"skills": [], "languages": []}
    return set_skills(conn, user_id, [*row["skills"], *skills], [*row["languages"], *languages])


def set_contact(conn, user_id, *, phone: str, city: str, linkedin_url: str) -> dict:
    """The contact line of the user's CVs. Returns the profile."""
    return _profile(conn.execute(
        "insert into profiles (user_id, phone, city, linkedin_url) values (%s, %s, %s, %s) on conflict (user_id) do update "
        "set phone = excluded.phone, city = excluded.city, linkedin_url = excluded.linkedin_url, updated_at = now() returning *",
        (user_id, phone.strip(), city.strip(), linkedin_url.strip())).fetchone())


def set_additional(conn, user_id, lines: list[str]) -> dict:
    """Replace the lines of "Additional information" (certifications, awards, volunteering),
    without blanks or a second copy of the same line. Returns the profile."""
    kept, seen = [], set()
    for line in lines:
        text = (line or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            kept.append(text)
    return _profile(conn.execute(
        "insert into profiles (user_id, additional) values (%s, %s) on conflict (user_id) do update "
        "set additional = excluded.additional, updated_at = now() returning *", (user_id, kept)).fetchone())


def set_github_username(conn, user_id, username: str) -> None:
    conn.execute("update profiles set github_username = %s, updated_at = now() where user_id = %s", (username, user_id))


def details_complete(profile: dict) -> bool:
    """True once the user has filled in the facts the app cannot work without."""
    texts = (profile.get("university"), profile.get("course"), profile.get("visa_type"))
    return (all(isinstance(t, str) and t.strip() for t in texts)
            and bool(profile.get("graduation_date")) and bool(profile.get("visa_end_date")) and bool(profile.get("locations")))


# ---------- references to the user's other rows ----------

def _own(conn, user_id, table: str, row_id):
    """row_id if it names one of this user's rows in `table`, else None. Stops a row
    from pointing at something that belongs to someone else or no longer exists."""
    if row_id is None:
        return None
    found = conn.execute(f"select id from {table} where id = %s and user_id = %s", (row_id, user_id)).fetchone()
    return found["id"] if found else None


# ---------- achievements ----------

def list_achievements(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from achievements where user_id = %s order by created_at desc, id", (user_id,)))


# What a user may edit. Not the quote (`raw`) or where it came from: those record the source
ACHIEVEMENT_FIELDS = ("title", "uk_version", "skills", "outcome", "scale", "context_note", "work_history_id", "education_id")
_HAPPENED_AT = {"work_history_id": "work_history", "education_id": "education"}


def _happened_at(conn, user_id, fields: dict) -> dict:
    """The job or course an achievement is linked to, kept only if it is this user's. An
    achievement happened in one or the other: naming one clears the other."""
    links = {k: _own(conn, user_id, table, fields[k]) for k, table in _HAPPENED_AT.items() if k in fields}
    if links.get("work_history_id"):
        links["education_id"] = None
    elif links.get("education_id"):
        links["work_history_id"] = None
    return links


def add_achievements(conn, user_id, items: list[dict], source: str) -> list[dict]:
    saved = []
    for item in items:
        links = {"work_history_id": None, "education_id": None} | _happened_at(conn, user_id, item)
        saved.append(_row(conn.execute(
            "insert into achievements (user_id, title, raw, uk_version, skills, outcome, scale, context_note, source, "
            "work_history_id, education_id, source_url) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
            (user_id, item["title"], item.get("raw", ""), item["uk_version"], item.get("skills") or [],
             item.get("outcome", ""), item.get("scale", ""), item.get("context_note", ""), source,
             links["work_history_id"], links["education_id"], item.get("source_url"))).fetchone()))
    return saved


def update_achievement(conn, user_id, achievement_id, fields: dict) -> dict | None:
    """Change only the fields given."""
    unknown = set(fields) - set(ACHIEVEMENT_FIELDS)
    if unknown:
        raise ValueError(f"not editable achievement fields: {sorted(unknown)}")
    values = {k: v for k, v in fields.items() if k not in _HAPPENED_AT} | _happened_at(conn, user_id, fields)
    if not values:
        return get_achievement(conn, user_id, achievement_id)
    assignments = ", ".join(f"{k} = %s" for k in values)
    return _row(conn.execute(f"update achievements set {assignments} where id = %s and user_id = %s returning *",
                             (*values.values(), achievement_id, user_id)).fetchone())


def link_achievements(conn, user_id, achievement_ids: list, *, work_history_id=None, education_id=None) -> int:
    """Say where several of the user's achievements happened. Returns how many were linked."""
    links = _happened_at(conn, user_id, {"work_history_id": work_history_id, "education_id": education_id})
    if not achievement_ids or not any(links.values()):
        return 0
    return conn.execute("update achievements set work_history_id = %s, education_id = %s where user_id = %s and id = any(%s)",
                        (links["work_history_id"], links["education_id"], user_id, list(achievement_ids))).rowcount


def imported_urls(conn, user_id) -> set[str]:
    """The repositories already turned into achievements."""
    rows = conn.execute("select source_url from achievements where user_id = %s and source_url is not null", (user_id,)).fetchall()
    return {r["source_url"] for r in rows}


def achievements_without_story(conn, user_id) -> list[dict]:
    return _rows(conn.execute(
        "select a.* from achievements a where a.user_id = %s and not exists (select 1 from stories s where s.achievement_id = a.id) "
        "order by a.created_at desc, a.id", (user_id,)))


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


def _document(content: dict) -> Jsonb:
    """A CV as it is stored. A date inside it (a start month copied from a record) becomes ISO text."""
    return Jsonb(content, dumps=lambda value: json.dumps(value, default=lambda d: d.isoformat()))


def _next_version(conn, user_id, base_name: str) -> int:
    """One more than the highest number used for this name, so a number is never given twice
    even after a version is deleted."""
    rows = conn.execute("select name from cv_versions where user_id = %s and starts_with(name, %s)", (user_id, f"{base_name} v")).fetchall()
    used = [int(number) for r in rows if re.fullmatch(r"\d+", number := r["name"][len(base_name) + 2:])]
    return max(used, default=0) + 1


def add_cv_version(conn, user_id, *, saved_job_id, role_family_id, base_name: str, content: dict, kind: str = "tailored",
                   format_version: int = 2, pages: int | None = None, contact_name: str = "") -> dict:
    """Save a CV as a new version, named "<base_name> v1", "v2", ..."""
    return _row(conn.execute(
        "insert into cv_versions (user_id, name, saved_job_id, role_family_id, content, kind, format_version, pages, contact_name) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
        (user_id, f"{base_name} v{_next_version(conn, user_id, base_name)}", _own(conn, user_id, "saved_jobs", saved_job_id),
         _own(conn, user_id, "role_families", role_family_id), _document(content), kind, format_version, pages, contact_name.strip())).fetchone())


def update_cv_version(conn, user_id, cv_version_id, *, content: dict, pages: int | None, contact_name: str) -> dict | None:
    """Save a user's edit over the version itself. Never called for a version an application points at."""
    return _row(conn.execute(
        "update cv_versions set content = %s, pages = %s, contact_name = %s, edited_at = now() where id = %s and user_id = %s returning *",
        (_document(content), pages, contact_name.strip(), cv_version_id, user_id)).fetchone())


def cv_version_in_use(conn, user_id, cv_version_id) -> bool:
    """Whether one of the user's applications was sent with this version: if so it must not change."""
    return conn.execute("select 1 from applications where user_id = %s and cv_version_id = %s limit 1",
                        (user_id, cv_version_id)).fetchone() is not None


def delete_cv_version(conn, user_id, cv_version_id) -> bool | None:
    """True once deleted; False if an application points at it, in which case it stays; None if it is not this user's."""
    if not get_cv_version(conn, user_id, cv_version_id):
        return None
    if cv_version_in_use(conn, user_id, cv_version_id):
        return False
    return conn.execute("delete from cv_versions where id = %s and user_id = %s", (cv_version_id, user_id)).rowcount == 1


# ---------- STAR stories ----------

def list_stories(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from stories where user_id = %s order by created_at desc, id", (user_id,)))


def add_story(conn, user_id, achievement_id, story: dict) -> dict:
    fields = ("title", "competency", "situation", "task", "action", "result", "strength", "tip")
    return _row(conn.execute(
        f"insert into stories (user_id, achievement_id, {', '.join(fields)}) values (%s, %s, {', '.join(['%s'] * len(fields))}) returning *",
        (user_id, _own(conn, user_id, "achievements", achievement_id), *(story.get(f, "") for f in fields))).fetchone())


STORY_FIELDS = ("title", "competency", "situation", "task", "action", "result")  # what a user may edit


def get_story(conn, user_id, story_id) -> dict | None:
    return _row(conn.execute("select * from stories where id = %s and user_id = %s", (story_id, user_id)).fetchone())


def update_story(conn, user_id, story_id, fields: dict) -> dict | None:
    """Change only the fields given."""
    unknown = set(fields) - set(STORY_FIELDS)
    if unknown:
        raise ValueError(f"not editable story fields: {sorted(unknown)}")
    if not fields:
        return get_story(conn, user_id, story_id)
    assignments = ", ".join(f"{k} = %s" for k in fields)
    return _row(conn.execute(f"update stories set {assignments} where id = %s and user_id = %s returning *",
                             (*fields.values(), story_id, user_id)).fetchone())


def delete_story(conn, user_id, story_id) -> bool:
    return conn.execute("delete from stories where id = %s and user_id = %s", (story_id, user_id)).rowcount == 1


# ---------- applications ----------

APPLICATION_FIELDS = ("company", "role", "role_family_id", "cv_version_id", "saved_job_id", "source", "stage",
                      "applied_on", "posted_on", "job_url", "contact_name", "contact", "notes", "sponsor_licence", "follow_up_on")
_REFERENCES = {"role_family_id": "role_families", "cv_version_id": "cv_versions", "saved_job_id": "saved_jobs"}
REJECTED = ("rejected", "rejected_after_interview")
CLOSED = ("offer", *REJECTED)  # an application that has ended: nothing to follow up
FOLLOW_UP_DAYS = 7
# Where a rejection ended, as the user answers it, and the stage that sets
ENDED_AT = {"cv": "rejected", "screening": "rejected", "interview": "rejected_after_interview", "final": "rejected_after_interview"}


def _application_values(conn, user_id, fields: dict) -> dict:
    unknown = set(fields) - set(APPLICATION_FIELDS)
    if unknown:
        raise ValueError(f"not application fields: {sorted(unknown)}")
    return {k: _own(conn, user_id, _REFERENCES[k], v) if k in _REFERENCES else v for k, v in fields.items()}


def list_applications(conn, user_id) -> list[dict]:
    return _rows(conn.execute("select * from applications where user_id = %s order by applied_on desc, created_at desc, id", (user_id,)))


def _record_stage(conn, user_id, app_id, from_stage: str | None, to_stage: str) -> None:
    conn.execute("insert into application_events (user_id, application_id, from_stage, to_stage) values (%s, %s, %s, %s)",
                 (user_id, app_id, from_stage, to_stage))


def add_application(conn, user_id, fields: dict) -> dict:
    """Log an application, with the first line of its history. An open application with no
    follow-up date is given one a week after applying."""
    # a field left out, or given as None where the column has a default (stage, applied_on), takes the default
    values = {k: v for k, v in _application_values(conn, user_id, fields).items() if v is not None}
    columns = ["user_id", *values]
    row = _row(conn.execute(
        f"insert into applications ({', '.join(columns)}) values ({', '.join(['%s'] * len(columns))}) returning *",
        (user_id, *values.values())).fetchone())
    if row["follow_up_on"] is None and row["stage"] not in CLOSED:
        row = _row(conn.execute("update applications set follow_up_on = applied_on + %s::int where id = %s returning *",
                                (FOLLOW_UP_DAYS, row["id"])).fetchone())
    _record_stage(conn, user_id, row["id"], None, row["stage"])
    return row


def update_application(conn, user_id, app_id, fields: dict) -> dict | None:
    """Change only the fields given. A new stage adds a line to the history; leaving a rejected
    stage clears what the rejection recorded. A suggested follow-up date that was never acted on
    moves with a corrected application date."""
    values = _application_values(conn, user_id, fields)
    before = _row(conn.execute("select * from applications where id = %s and user_id = %s for update", (app_id, user_id)).fetchone())
    if before is None:
        return None
    stage = values.get("stage") or before["stage"]
    if before["stage"] in REJECTED and stage not in REJECTED:
        values |= {"rejected_at_stage": None, "feedback_received": None, "lesson": None}
    suggested = before["applied_on"] + timedelta(days=FOLLOW_UP_DAYS)
    if (values.get("applied_on") and "follow_up_on" not in values and before["last_followed_up_on"] is None
            and before["follow_up_on"] == suggested):
        values["follow_up_on"] = values["applied_on"] + timedelta(days=FOLLOW_UP_DAYS)
    assignments = ", ".join([f"{k} = %s" for k in values] + ["updated_at = now()"])
    row = _row(conn.execute(f"update applications set {assignments} where id = %s and user_id = %s returning *",
                            (*values.values(), app_id, user_id)).fetchone())
    if stage != before["stage"]:
        _record_stage(conn, user_id, app_id, before["stage"], stage)
    return row


def get_application(conn, user_id, app_id) -> dict | None:
    return _row(conn.execute("select * from applications where id = %s and user_id = %s", (app_id, user_id)).fetchone())


def list_application_events(conn, user_id) -> list[dict]:
    """Every stage change of the user's applications, each with its London date, in order."""
    return _rows(conn.execute(
        "select application_id, from_stage, to_stage, at, (at at time zone 'Europe/London')::date as day "
        "from application_events where user_id = %s order by application_id, at, id", (user_id,)))


def reject_application(conn, user_id, app_id, *, ended_at: str, feedback: str) -> dict | None:
    """Record a rejection: the stage its answer implies, where it ended, any feedback given. A
    lesson written for an earlier answer is cleared, since it may no longer fit."""
    if update_application(conn, user_id, app_id, {"stage": ENDED_AT[ended_at]}) is None:
        return None
    return _row(conn.execute(
        "update applications set rejected_at_stage = %s, feedback_received = %s, lesson = null, updated_at = now() "
        "where id = %s and user_id = %s returning *", (ended_at, feedback.strip() or None, app_id, user_id)).fetchone())


def set_lesson(conn, user_id, app_id, lesson: dict) -> dict | None:
    return _row(conn.execute("update applications set lesson = %s, updated_at = now() where id = %s and user_id = %s returning *",
                             (Jsonb(lesson), app_id, user_id)).fetchone())


def mark_followed_up(conn, user_id, app_id, today: date) -> dict | None:
    """The user followed up today: the next follow-up is due a week from now."""
    return _row(conn.execute(
        "update applications set last_followed_up_on = %s, follow_up_on = %s, updated_at = now() "
        "where id = %s and user_id = %s returning *", (today, today + timedelta(days=FOLLOW_UP_DAYS), app_id, user_id)).fetchone())


def application_for_job(conn, user_id, saved_job_id) -> dict | None:
    """The user's application for one of their saved jobs, if they have logged one."""
    return _row(conn.execute("select * from applications where user_id = %s and saved_job_id = %s order by created_at limit 1",
                             (user_id, saved_job_id)).fetchone())


def delete_application(conn, user_id, app_id) -> bool:
    return conn.execute("delete from applications where id = %s and user_id = %s", (app_id, user_id)).rowcount == 1


# ---------- journal ----------

# A transcript can run to thousands of words, so entries are listed without it and it is fetched on demand
_JOURNAL = ("id, user_id, type, title, with_whom, summary, points, actions, scores, created_at, "
            "transcript is not null as has_transcript")


def list_journal(conn, user_id) -> list[dict]:
    return _rows(conn.execute(f"select {_JOURNAL} from journal_entries where user_id = %s order by created_at desc, id", (user_id,)))


def add_journal_entry(conn, user_id, *, type: str, title: str, with_whom: str, summary: str, points, actions,
                      scores=None, transcript: str | None = None) -> dict:
    return _row(conn.execute(
        "insert into journal_entries (user_id, type, title, with_whom, summary, points, actions, scores, transcript) "
        f"values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning {_JOURNAL}",
        (user_id, type, title, with_whom, summary, Jsonb(list(points)), Jsonb(list(actions)),
         Jsonb(scores) if scores is not None else None, transcript)).fetchone())


def practice_days(conn, user_id) -> list[date]:
    """The London date of each finished mock interview: what counts as practice for the weekly goal."""
    rows = conn.execute("select (created_at at time zone 'Europe/London')::date as day from journal_entries "
                        "where user_id = %s and type = 'interview' order by created_at", (user_id,)).fetchall()
    return [r["day"] for r in rows]


def get_journal_transcript(conn, user_id, entry_id) -> str | None:
    """What was said in that session, or None if the entry is not this user's or has no transcript."""
    row = conn.execute("select transcript from journal_entries where id = %s and user_id = %s", (entry_id, user_id)).fetchone()
    return row["transcript"] if row else None


# ---------- weekly goals and milestones ----------

def list_goals(conn, user_id) -> list[dict]:
    """Every goal the user has set, each applying from its Monday, oldest first."""
    return _rows(conn.execute("select effective_from, applications, practice from weekly_goals where user_id = %s "
                              "order by effective_from", (user_id,)))


def set_goal(conn, user_id, *, effective_from: date, applications: int, practice: int) -> dict:
    """Set the goal from one Monday. A second change before that Monday replaces the first."""
    return _row(conn.execute(
        "insert into weekly_goals (user_id, effective_from, applications, practice) values (%s, %s, %s, %s) "
        "on conflict (user_id, effective_from) do update set applications = excluded.applications, practice = excluded.practice, "
        "created_at = now() returning effective_from, applications, practice",
        (user_id, effective_from, applications, practice)).fetchone())


def account_started(conn, user_id) -> date | None:
    """The London date the user's profile was made: weeks before it count neither for nor against a streak."""
    row = conn.execute("select (created_at at time zone 'Europe/London')::date as day from profiles where user_id = %s",
                       (user_id,)).fetchone()
    return row["day"] if row else None


def mark_milestones_seen(conn, user_id, ids: list[str]) -> list[str]:
    """Add milestones to those already shown, keeping their order. Returns the whole list."""
    row = conn.execute("select milestones_seen from profiles where user_id = %s for update", (user_id,)).fetchone()
    if row is None:
        return []
    seen = list(row["milestones_seen"])
    seen += [i for i in dict.fromkeys(ids) if i not in seen]
    conn.execute("update profiles set milestones_seen = %s where user_id = %s", (Jsonb(seen), user_id))
    return seen


# ---------- work history and education ----------
# Two tables of the same shape, so one set of functions. `table` is always one of the two names
# below, written in this codebase, never taken from a request.

ENTRY_FIELDS = {
    "work_history": ("employer", "job_title", "location", "country", "start_month", "end_month", "is_current", "employer_context"),
    "education": ("institution", "qualification", "subject", "start_month", "end_month", "grade", "country"),
}
_ENTRY_ORDER = {
    "work_history": "is_current desc, coalesce(end_month, start_month) desc nulls last, created_at desc, id",
    "education": "from_details desc, coalesce(end_month, start_month) desc nulls last, created_at desc, id",
}
_MONTHS = ("start_month", "end_month")


def _entry_values(table: str, fields: dict) -> dict:
    if table not in ENTRY_FIELDS:
        raise ValueError(f"not a table of entries: {table}")
    unknown = set(fields) - set(ENTRY_FIELDS[table])
    if unknown:
        raise ValueError(f"not {table} fields: {sorted(unknown)}")
    values = {}
    for key, value in fields.items():
        if key in _MONTHS:
            values[key] = value.replace(day=1) if value else None
        elif key == "is_current":
            values[key] = bool(value)
        else:
            values[key] = (value or "").strip()
    return values


def list_entries(conn, user_id, table: str) -> list[dict]:
    _entry_values(table, {})
    return _rows(conn.execute(f"select * from {table} where user_id = %s order by {_ENTRY_ORDER[table]}", (user_id,)))


def get_entry(conn, user_id, table: str, entry_id) -> dict | None:
    _entry_values(table, {})
    return _row(conn.execute(f"select * from {table} where id = %s and user_id = %s", (entry_id, user_id)).fetchone())


def add_entry(conn, user_id, table: str, fields: dict, source: str = "manual") -> dict:
    values = _entry_values(table, fields)
    columns = ["user_id", "source", *values]
    return _row(conn.execute(
        f"insert into {table} ({', '.join(columns)}) values ({', '.join(['%s'] * len(columns))}) returning *",
        (user_id, source, *values.values())).fetchone())


def update_entry(conn, user_id, table: str, entry_id, fields: dict) -> dict | None:
    """Change only the fields given."""
    values = _entry_values(table, fields)
    assignments = ", ".join([f"{k} = %s" for k in values] + ["updated_at = now()"])
    return _row(conn.execute(f"update {table} set {assignments} where id = %s and user_id = %s returning *",
                             (*values.values(), entry_id, user_id)).fetchone())


def fill_entry(conn, user_id, table: str, entry_id, fields: dict) -> dict | None:
    """Fill in the fields that are empty now and leave the rest as the user has them. Left out:
    a month that would end a current job or put the end before the start, and "still there" for
    a job that has an end month."""
    values = _entry_values(table, fields)
    row = get_entry(conn, user_id, table, entry_id)
    if row is None:
        return None
    blanks = {k: v for k, v in values.items() if v and not row[k]}
    if row.get("is_current"):
        blanks.pop("end_month", None)
    if row.get("end_month"):
        blanks.pop("is_current", None)  # a job the user says has ended is not reopened
    start, end = blanks.get("start_month") or row["start_month"], blanks.get("end_month") or row["end_month"]
    if start and end and end < start:
        blanks = {k: v for k, v in blanks.items() if k not in _MONTHS}
    return update_entry(conn, user_id, table, entry_id, blanks) if blanks else row


def delete_entry(conn, user_id, table: str, entry_id) -> bool:
    _entry_values(table, {})
    return conn.execute(f"delete from {table} where id = %s and user_id = %s", (entry_id, user_id)).rowcount == 1


# ---------- everything one user owns ----------

def load_state(conn, user_id) -> dict:
    return {
        "achievements": list_achievements(conn, user_id),
        "work_history": list_entries(conn, user_id, "work_history"),
        "education": list_entries(conn, user_id, "education"),
        "role_families": list_families(conn, user_id),
        "saved_jobs": list_jobs(conn, user_id),
        "cv_versions": list_cv_versions(conn, user_id),
        "stories": list_stories(conn, user_id),
        "applications": list_applications(conn, user_id),
        "journal": list_journal(conn, user_id),
    }


# ---------- usage (daily limits now, streaks later) ----------

# midnight today in London, as a point in time
_LONDON_MIDNIGHT = "(date_trunc('day', now() at time zone 'Europe/London') at time zone 'Europe/London')"


def today(conn) -> date:
    """Today's date in London: the day a cover letter is dated, and the day "recently graduated" is judged from."""
    return conn.execute("select (now() at time zone 'Europe/London')::date as today").fetchone()["today"]


def count_usage_today(conn, user_id, kind: str) -> int:
    return conn.execute(f"select count(*) as n from usage_events where user_id = %s and kind = %s and created_at >= {_LONDON_MIDNIGHT}",
                        (user_id, kind)).fetchone()["n"]


def record_usage(conn, user_id, kind: str, action: str) -> None:
    conn.execute("insert into usage_events (user_id, kind, action) values (%s, %s, %s)", (user_id, kind, action))


def seconds_since_last_usage(conn, user_id, kind: str, action: str) -> float | None:
    row = conn.execute("select extract(epoch from now() - max(created_at)) as s from usage_events "
                       "where user_id = %s and kind = %s and action = %s", (user_id, kind, action)).fetchone()
    return float(row["s"]) if row["s"] is not None else None


# ---------- the sponsor register (shared public data, no user_id) ----------

SKILLED_WORKER = "Skilled Worker"
MIN_PREFIX_KEY = 4  # a shorter name is too little to guess a longer registered name from
_NOT_FOUND = {"status": "not_found", "name": None}
# name_key begins with the wanted key followed by a space. Written as a range ("!" sorts straight
# after a space) so the text_pattern_ops index is used even when the key comes from another column.
_STARTS_WITH = "s.name_key ~>=~ ({key} || ' ') and s.name_key ~<~ ({key} || '!')"


def replace_sponsors(conn, rows: list[dict], *, published_on, source_url: str, row_count: int) -> int:
    """Swap the whole register for `rows` (each with name_key: see sponsors.with_keys)."""
    conn.execute("delete from sponsors")
    fields = ("name", "name_key", "town", "county", "route", "rating")
    for start in range(0, len(rows), 5000):
        chunk = rows[start:start + 5000]
        conn.execute(
            f"insert into sponsors ({', '.join(fields)}) select * from unnest({', '.join(['%s::text[]'] * len(fields))})",
            [[r[f] for r in chunk] for f in fields])
    conn.execute(
        "insert into reference_meta (key, loaded_at, published_on, source_url, row_count) values ('sponsors', now(), %s, %s, %s) "
        "on conflict (key) do update set loaded_at = now(), published_on = excluded.published_on, "
        "source_url = excluded.source_url, row_count = excluded.row_count", (published_on, source_url, row_count))
    return len(rows)


def register_meta(conn) -> dict | None:
    """When the register was last loaded and the date gov.uk published that file."""
    return conn.execute("select loaded_at, published_on, source_url, row_count from reference_meta where key = 'sponsors'").fetchone()


def find_sponsor(conn, key: str) -> dict:
    """The register entry for a normalised employer name: "listed" when the names are the same,
    "possible" when a longer registered name starts with it, otherwise "not_found"."""
    if not key:
        return dict(_NOT_FOUND)
    row = conn.execute("select name from sponsors where name_key = %s and route = %s order by name limit 1", (key, SKILLED_WORKER)).fetchone()
    if row:
        return {"status": "listed", "name": row["name"]}
    if len(key) >= MIN_PREFIX_KEY:
        row = conn.execute(
            f"select s.name from sponsors s where {_STARTS_WITH.format(key='%s')} and s.route = %s order by length(s.name_key), s.name limit 1",
            (key, key, SKILLED_WORKER)).fetchone()
        if row:
            return {"status": "possible", "name": row["name"]}
    return dict(_NOT_FOUND)


def recheck_listing_sponsors(conn, listing_ids: list[str] | None = None) -> None:
    """Work out what the register says about stored listings that name their employer: all of
    them (after the register is reloaded) or just the ones given (when adverts are stored)."""
    only = "" if listing_ids is None else " and l.id = any(%s::uuid[])"
    ids = [] if listing_ids is None else [listing_ids]
    conn.execute(f"update job_listings l set sponsor_status = 'not_found', sponsor_name = null where l.posted_by = 'employer'{only}", ids)
    conn.execute(
        "update job_listings l set sponsor_status = 'listed', sponsor_name = "
        "(select s.name from sponsors s where s.name_key = l.employer_key and s.route = %s order by s.name limit 1) "
        "where l.posted_by = 'employer' and l.employer_key <> '' "
        f"and exists (select 1 from sponsors s where s.name_key = l.employer_key and s.route = %s){only}",
        [SKILLED_WORKER, SKILLED_WORKER, *ids])
    starts = _STARTS_WITH.format(key="l.employer_key")
    conn.execute(
        "update job_listings l set sponsor_status = 'possible', sponsor_name = "
        f"(select s.name from sponsors s where {starts} and s.route = %s order by length(s.name_key), s.name limit 1) "
        "where l.posted_by = 'employer' and l.sponsor_status = 'not_found' and length(l.employer_key) >= %s "
        f"and exists (select 1 from sponsors s where {starts} and s.route = %s){only}",
        [SKILLED_WORKER, MIN_PREFIX_KEY, SKILLED_WORKER, *ids])


# ---------- job listings and the search cache (shared public data, no user_id) ----------

JOB_SOURCE = "reed"
_LISTING = ("source", "source_id", "title", "employer", "employer_key", "posted_by", "location", "salary_min", "salary_max",
            "salary_annual", "description", "description_is_full", "url", "posted_on")
_LISTING_TYPES = {"salary_min": "numeric", "salary_max": "numeric", "salary_annual": "boolean", "description_is_full": "boolean",
                  "posted_on": "date"}
_PAIRS = "(select * from unnest(%s::text[], %s::text[]))"  # a list of (query, location) pairs


def _plain(value):
    """A salary as a float. One batch holds whole pounds (28000) beside rates (13.5), and a list
    sent to the database must be of one type."""
    return float(value) if isinstance(value, int) and not isinstance(value, bool) else value


def _pairs(searches) -> list[list[str]]:
    return [[q for q, _ in searches], [loc for _, loc in searches]]


def searches_due(conn, searches: list[tuple[str, str]], max_age_hours: int) -> set[tuple[str, str]]:
    """The (query, location) searches nobody has run within max_age_hours."""
    if not searches:
        return set()
    fresh = conn.execute(
        "select query, location from job_searches where source = %s and fetched_at > now() - make_interval(hours => %s) "
        f"and (query, location) in {_PAIRS}", [JOB_SOURCE, max_age_hours, *_pairs(searches)]).fetchall()
    return set(searches) - {(r["query"], r["location"]) for r in fresh}


def store_searches(conn, results: dict[tuple[str, str], list[dict]]) -> dict[tuple[str, str], list[str]]:
    """Store what each search found and mark it as run now. A listing seen before is updated in
    place; a search keeps only its latest results. Returns each search's listing ids, in order."""
    unique = {}
    for listings in results.values():
        for item in listings:
            unique.setdefault((item["source"], item["source_id"]), item)  # the same advert twice: the first wins
    ids = {}
    if unique:
        columns = [f"%s::{_LISTING_TYPES.get(f, 'text')}[]" for f in _LISTING]
        # the short text a search carries never replaces a full advert already stored, nor its salary
        keep_full = ", ".join(f"{f} = case when job_listings.description_is_full then job_listings.{f} else excluded.{f} end"
                              for f in ("description", "description_is_full", "salary_min", "salary_max", "salary_annual"))
        rows = conn.execute(
            f"insert into job_listings ({', '.join(_LISTING)}, sponsor_status) "
            "select t.*, case when t.posted_by = 'employer' then 'not_found' else 'agency' end "  # only a named employer is looked up
            f"from unnest({', '.join(columns)}) as t ({', '.join(_LISTING)}) "
            "on conflict (source, source_id) do update set title = excluded.title, employer = excluded.employer, "
            "employer_key = excluded.employer_key, posted_by = excluded.posted_by, location = excluded.location, url = excluded.url, "
            f"posted_on = excluded.posted_on, sponsor_status = excluded.sponsor_status, sponsor_name = null, fetched_at = now(), {keep_full} "
            "returning id, source, source_id",
            [[_plain(item[f]) for item in unique.values()] for f in _LISTING]).fetchall()
        ids = {(r["source"], r["source_id"]): str(r["id"]) for r in rows}
        recheck_listing_sponsors(conn, list(ids.values()))
    found = {}
    for (query, location), listings in results.items():
        search_id = conn.execute(
            "insert into job_searches (source, query, location) values (%s, %s, %s) "
            "on conflict (source, query, location) do update set fetched_at = now() returning id", (JOB_SOURCE, query, location)).fetchone()["id"]
        found[(query, location)] = list(dict.fromkeys(ids[(item["source"], item["source_id"])] for item in listings))
        conn.execute("delete from job_search_results where search_id = %s", (search_id,))
        conn.execute("insert into job_search_results (search_id, listing_id) select %s, unnest(%s::uuid[])", (search_id, found[(query, location)]))
    return found


def purge_old_listings(conn, days: int = 30) -> None:
    """Drop adverts posted more than `days` ago, and searches not run since. A saved job is a copy, so it stays."""
    conn.execute("delete from job_listings where posted_on < (now() at time zone 'Europe/London')::date - %s", (days,))
    conn.execute("delete from job_searches where fetched_at < now() - make_interval(days => %s)", (days,))


def listings_for_searches(conn, searches: list[tuple[str, str]], since: date) -> list[dict]:
    """The adverts those searches last found that were posted on or after `since`, each with the search that found it."""
    if not searches:
        return []
    return _rows(conn.execute(
        "select l.id, l.title, l.employer_key, l.location, l.posted_on, s.query, s.location as search_location "
        "from job_searches s join job_search_results r on r.search_id = s.id join job_listings l on l.id = r.listing_id "
        f"where s.source = %s and (s.query, s.location) in {_PAIRS} and l.posted_on >= %s order by l.posted_on desc, l.id",
        [JOB_SOURCE, *_pairs(searches), since]))


def set_listing_details(conn, listing_id, details: dict) -> None:
    """Replace a listing's short search text with the full advert (see reed.details)."""
    fields = [f for f in ("description", "description_is_full", "salary_min", "salary_max", "salary_annual", "posted_on") if f in details]
    conn.execute(f"update job_listings set {', '.join(f'{f} = %s' for f in fields)} where id = %s", [*(details[f] for f in fields), listing_id])


# ---------- job matches: one user's view of a listing ----------

# a match counts only while its advert is recent and its role family, if it still exists, is targeted
_LIVE = ("from job_matches m join job_listings l on l.id = m.listing_id left join role_families f on f.id = m.role_family_id "
         "where m.user_id = %s and l.posted_on >= %s and (f.id is null or f.targeted)")
_MATCH = ("m.id, m.listing_id, m.role_family_id, m.search_location, m.fit_percent, m.fit_label, m.shown, m.gaps, m.fit_from_summary, "
          "m.status, m.first_seen_at, m.scored_at, l.source, l.source_id, l.title, l.employer, l.posted_by, l.location, "
          "l.salary_min::float8 as salary_min, l.salary_max::float8 as salary_max, l.salary_annual, l.description_is_full, l.url, "
          "l.posted_on, l.sponsor_status, l.sponsor_name")
MIN_MATCH_PERCENT = 40  # below this an advert is "not a match"


def add_matches(conn, user_id, items: list[dict]) -> int:
    """Give the user a match for each listing they do not already have one for; returns how many
    were new. An existing match is left exactly as it is, so a hidden job stays hidden."""
    if not items:
        return 0
    return conn.execute(
        "insert into job_matches (user_id, listing_id, role_family_id, search_location) "
        "select %s, t.listing_id, (select rf.id from role_families rf where rf.id = t.family_id and rf.user_id = %s), t.place "
        "from unnest(%s::uuid[], %s::uuid[], %s::text[]) as t (listing_id, family_id, place) "
        "on conflict (user_id, listing_id) do nothing",
        (user_id, user_id, [i["listing_id"] for i in items], [i.get("role_family_id") for i in items],
         [i.get("search_location") or "" for i in items])).rowcount


def matched_listings(conn, user_id) -> list[dict]:
    """Every advert the user already has a match for, hidden ones included, with what identifies the job."""
    return _rows(conn.execute(
        "select l.id, l.title, l.employer_key, l.location, l.posted_on from job_matches m join job_listings l on l.id = m.listing_id "
        "where m.user_id = %s", (user_id,)))


def list_matches(conn, user_id, since: date) -> list[dict]:
    """The user's matches that are not hidden, newest advert first, with what the Jobs page shows."""
    return _rows(conn.execute(
        f"select {_MATCH}, left(l.description, 300) as snippet {_LIVE} and m.status <> 'hidden' "
        "order by l.posted_on desc, m.fit_percent desc nulls last, l.title, m.id", (user_id, since)))


def get_match(conn, user_id, match_id) -> dict | None:
    """One of the user's matches with the whole advert, or None if it is not theirs."""
    return _row(conn.execute(
        f"select {_MATCH}, l.description, l.employer_key from job_matches m join job_listings l on l.id = m.listing_id "
        "where m.id = %s and m.user_id = %s", (match_id, user_id)).fetchone())


def unscored_matches(conn, user_id, since: date) -> list[dict]:
    """Matches the model has not judged yet, with the advert text to judge them on."""
    return _rows(conn.execute(
        "select m.id as match_id, m.listing_id, l.source_id, l.title, l.employer, l.posted_by, l.description, l.description_is_full, l.posted_on "
        f"{_LIVE} and m.scored_at is null and m.status <> 'hidden' order by l.posted_on desc, m.id", (user_id, since)))


def save_scores(conn, user_id, scores: list[dict]) -> None:
    """Record the fit for each {"match_id", "fit" (see jobs.fit) or None, "from_summary"}. A match
    judged with nothing to go on gets no score but is marked as looked at, so it is not asked again."""
    for s in scores:
        fit = s["fit"] or {}
        conn.execute(
            "update job_matches set fit_percent = %s, fit_label = %s, shown = %s, gaps = %s, fit_from_summary = %s, scored_at = now() "
            "where id = %s and user_id = %s",
            (fit.get("percent"), fit.get("label"), Jsonb(fit.get("shown") or []), Jsonb(fit.get("gaps") or []),
             bool(s.get("from_summary")), s["match_id"], user_id))


def mark_matches_seen(conn, user_id) -> int:
    return conn.execute("update job_matches set status = 'seen' where user_id = %s and status = 'new'", (user_id,)).rowcount


def hide_match(conn, user_id, match_id) -> bool:
    return conn.execute("update job_matches set status = 'hidden' where id = %s and user_id = %s", (match_id, user_id)).rowcount == 1


def save_listing_as_job(conn, user_id, match_id) -> dict | None:
    """Copy a matched advert into the user's saved jobs, once. The copy outlives the listing."""
    match = get_match(conn, user_id, match_id)
    if not match:
        return None
    job = conn.execute("select * from saved_jobs where user_id = %s and listing_id = %s order by created_at limit 1",
                       (user_id, match["listing_id"])).fetchone()
    if not job:
        job = conn.execute(
            "insert into saved_jobs (user_id, title, company, location, url, description, summary, role_family_id, source, listing_id, posted_on) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning *",
            (user_id, match["title"], match["employer"], match["location"] or None, match["url"], match["description"],
             match["description"][:300], _own(conn, user_id, "role_families", match["role_family_id"]), match["source"],
             match["listing_id"], match["posted_on"])).fetchone()
    conn.execute("update job_matches set status = 'saved' where id = %s and user_id = %s", (match_id, user_id))
    return _row(job)


def job_counts(conn, user_id, since: date, fresh_since: date) -> dict:
    """How many matching jobs the user has not seen yet ("new"), and how many of those were
    posted on or after fresh_since ("fresh"). Only jobs scored as at least a stretch count."""
    return conn.execute(
        "select count(*) as new, count(*) filter (where l.posted_on >= %s) as fresh "
        f"{_LIVE} and m.status = 'new' and m.fit_percent >= %s", (fresh_since, user_id, since, MIN_MATCH_PERCENT)).fetchone()


def family_market(conn, user_id, since: date) -> dict[str, dict]:
    """For each targeted role family: live adverts matched, how many name their employer, how many
    of those employers are on the register, and the mid-point of every annual salary advertised.
    Training programmes are not jobs and are left out."""
    rows = conn.execute(
        "select m.role_family_id, count(*) as jobs, count(*) filter (where l.posted_by = 'employer') as named, "
        "count(*) filter (where l.sponsor_status = 'listed') as listed, "
        "coalesce(array_agg(((coalesce(l.salary_min, l.salary_max) + coalesce(l.salary_max, l.salary_min)) / 2)::float8) "
        "filter (where l.salary_annual and coalesce(l.salary_min, l.salary_max) is not null), '{}') as salaries "
        f"{_LIVE} and f.id is not null and m.status <> 'hidden' and l.posted_by <> 'training' group by m.role_family_id",
        (user_id, since)).fetchall()
    return {str(r["role_family_id"]): {k: r[k] for k in ("jobs", "named", "listed", "salaries")} for r in rows}


def set_include_senior(conn, user_id, value: bool) -> None:
    conn.execute("update profiles set include_senior = %s, updated_at = now() where user_id = %s", (value, user_id))
