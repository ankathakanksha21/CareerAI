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
