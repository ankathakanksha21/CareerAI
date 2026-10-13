"""UK Career Navigator API. Routes only: check who is calling, validate the input, call the
modules, return JSON. Every route except /api/config needs a signed-in user and touches
only that user's rows."""
import hmac
import logging
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

import ai
import analytics
import content
import db
import intake
import jobs
import limits
import reed
import repo
import sponsors
import visa
import voice
from auth import User, current_user
from config import cron_secret, env, jobs_configured, llm_configured, supabase_url, voice_configured
from llm import LLMNotConfigured

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")
app = FastAPI(title="UK Career Navigator")

GONE = "That item no longer exists"
CurrentUser = Annotated[User, Depends(current_user)]
Source = Literal[analytics.SOURCES]
Stage = Literal[analytics.STAGES]


def Text(max_length: int, min_length: int = 1):
    """A trimmed string that must have between min_length and max_length characters."""
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


# ---------- errors every route can raise ----------

@app.exception_handler(limits.LimitReached)
def limit_reached(request, exc):
    return JSONResponse({"detail": "You've reached today's limit. It resets at midnight."}, status_code=429)


@app.exception_handler(ai.AIError)
def ai_failed(request, exc):
    return JSONResponse({"detail": "The AI did not respond properly. Try again."}, status_code=502)


@app.exception_handler(LLMNotConfigured)
def ai_not_configured(request, exc):
    return JSONResponse({"detail": "AI is not set up on the server."}, status_code=503)


@app.exception_handler(psycopg.OperationalError)
def database_unreachable(request, exc):
    log.error("database unreachable: %s", type(exc).__name__)
    return JSONResponse({"detail": "We can't reach the server. Try again in a minute."}, status_code=503)


def _found(row):
    if not row:
        raise HTTPException(404, GONE)
    return row


def _achievement(row: dict) -> dict:
    """An achievement as the pages get it: with whether it still lacks a number."""
    return row | {"needs_number": ai.needs_number(row)}


def _job_dates() -> tuple[date, date]:
    """The oldest posting date still shown, and the oldest that counts as just posted."""
    today = date.today()
    return today - timedelta(days=jobs.FRESH_DAYS), today - timedelta(days=jobs.NEW_DAYS)


# ---------- config and state ----------

@app.get("/api/config")
def get_config():
    """What the browser needs before anyone is signed in. Nothing here is secret."""
    return {"supabase_url": supabase_url(), "supabase_publishable_key": env("SUPABASE_PUBLISHABLE_KEY"),
            "contact_email": env("CONTACT_EMAIL")}


@app.get("/api/state")
def get_state(user: CurrentUser):
    since, fresh_since = _job_dates()
    with db.transaction() as conn:
        profile = repo.get_or_create_profile(conn, user.id, user.name)
        state = repo.load_state(conn, user.id)
        state["achievements"] = [_achievement(a) for a in state["achievements"]]
        usage = limits.usage(conn, user.id)
        job_counts = repo.job_counts(conn, user.id, since, fresh_since)
        market = jobs.market(repo.family_market(conn, user.id, since))
    return state | {
        "profile": profile | {"email": user.email},
        "details_complete": repo.details_complete(profile),
        "stats": analytics.compute(state["applications"], state["role_families"], state["cv_versions"], state["stories"], market),
        "next_steps": analytics.next_steps(state),
        "content": content.load(),
        "usage": usage,
        "jobs": job_counts,   # matching adverts not yet seen, and how many of those were just posted
        "market": market,     # live figures for each targeted role family
        "options": {"sources": analytics.SOURCES, "stages": analytics.STAGES, "language_levels": ai.LANGUAGE_LEVELS},
        "config": {"llm": llm_configured(), "jobs": jobs_configured(),
                   "voice": {"onboarding": voice_configured("onboarding"), "interviewer": voice_configured("interviewer")}},
    }


# ---------- profile and account ----------

class ProfileIn(BaseModel):
    full_name: Text(120)
    university: Text(160)
    course: Text(160)
    graduation_date: date
    visa_type: Literal["student", "graduate"]
    visa_end_date: date
    locations: Annotated[list[Text(60)], Field(min_length=1, max_length=5)]


@app.put("/api/profile")
def put_profile(body: ProfileIn, user: CurrentUser):
    with db.transaction() as conn:
        return repo.update_profile(conn, user.id, **body.model_dump()) | {"email": user.email}


def _delete_auth_user(user_id: str) -> None:
    """Remove the login from Supabase. Every row the user owns goes with it (on delete cascade)."""
    key = env("SUPABASE_SECRET_KEY")
    r = httpx.delete(f"{supabase_url()}/auth/v1/admin/users/{user_id}", timeout=15,
                     headers={"apikey": key, "Authorization": f"Bearer {key}"})
    r.raise_for_status()


@app.delete("/api/account", status_code=204)
def delete_account(user: CurrentUser):
    try:
        _delete_auth_user(user.id)
    except httpx.HTTPError:
        log.exception("account deletion failed")
        raise HTTPException(502, "Could not delete the account. Try again.")
    return Response(status_code=204)


# ---------- achievements, role families, saved jobs ----------

@app.delete("/api/achievements/{achievement_id}", status_code=204)
def delete_achievement(achievement_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        _found(repo.delete_achievement(conn, user.id, str(achievement_id)))
    return Response(status_code=204)


class Targeted(BaseModel):
    targeted: bool


@app.post("/api/families/{family_id}/target")
def target_family(family_id: UUID, body: Targeted, user: CurrentUser):
    with db.transaction() as conn:
        return _found(repo.set_family_targeted(conn, user.id, str(family_id), body.targeted))


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        _found(repo.delete_job(conn, user.id, str(job_id)))
    return Response(status_code=204)


class AchievementPatch(BaseModel):
    """What a user may change on an achievement. Not its quote or its source: sending either is refused."""
    model_config = ConfigDict(extra="forbid")
    title: Text(160) = None
    uk_version: Text(600) = None
    skills: Annotated[list[Text(60)], Field(max_length=20)] = None
    outcome: Text(300, 0) = None
    scale: Text(200, 0) = None
    context_note: Text(600, 0) = None
    work_history_id: UUID | None = None  # where it happened: one of the user's jobs...
    education_id: UUID | None = None     # ...or one of their courses


@app.patch("/api/achievements/{achievement_id}")
def update_achievement(achievement_id: UUID, body: AchievementPatch, user: CurrentUser):
    with db.transaction() as conn:
        return _achievement(_found(repo.update_achievement(conn, user.id, str(achievement_id), _ids_as_text(body.model_dump(exclude_unset=True)))))


class StoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Text(200) = None
    competency: Text(80, 0) = None
    situation: Text(2000, 0) = None
    task: Text(2000, 0) = None
    action: Text(2000, 0) = None
    result: Text(2000, 0) = None


@app.patch("/api/stories/{story_id}")
def update_story(story_id: UUID, body: StoryPatch, user: CurrentUser):
    with db.transaction() as conn:
        return _found(repo.update_story(conn, user.id, str(story_id), body.model_dump(exclude_unset=True)))


@app.delete("/api/stories/{story_id}", status_code=204)
def delete_story(story_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        _found(repo.delete_story(conn, user.id, str(story_id)))
    return Response(status_code=204)


# ---------- work history, education, skills ----------

END_BEFORE_START = "The end month cannot be before the start month."
CURRENT_HAS_NO_END = "A job you still do has no end month."
FROM_DETAILS = "Your current course comes from Your details. Change it there."
ENTRY_CHECKS = {"work_history_current_has_no_end": CURRENT_HAS_NO_END}  # the other check on these tables is the order of the months
SET_IN_DETAILS = ("institution", "qualification", "end_month")
HAPPENED_AT = {"work_history": "work_history_id", "education": "education_id"}


def _first_of_month(value: date) -> date:
    if not 1950 <= value.year <= 2100:
        raise ValueError("Enter a real month.")
    return value.replace(day=1)


Month = Annotated[date, AfterValidator(_first_of_month)]


class Period(BaseModel):
    start_month: Month | None = None
    end_month: Month | None = None

    @model_validator(mode="after")
    def months_in_order(self):
        if getattr(self, "is_current", False) and self.end_month:
            raise ValueError(CURRENT_HAS_NO_END)
        if self.start_month and self.end_month and self.end_month < self.start_month:
            raise ValueError(END_BEFORE_START)
        return self


class JobEntry(Period):
    employer: Text(160)
    job_title: Text(160, 0) = ""
    location: Text(120, 0) = ""
    country: Text(80, 0) = ""
    is_current: bool = False
    employer_context: Text(300, 0) = ""  # one line on what the employer does, for a UK reader


class JobEntryPatch(Period):
    employer: Text(160) = None
    job_title: Text(160, 0) = None
    location: Text(120, 0) = None
    country: Text(80, 0) = None
    is_current: bool = None
    employer_context: Text(300, 0) = None


class CourseEntry(Period):
    institution: Text(160)
    qualification: Text(120, 0) = ""
    subject: Text(160, 0) = ""
    grade: Text(80, 0) = ""
    country: Text(80, 0) = ""


class CourseEntryPatch(Period):
    institution: Text(160) = None
    qualification: Text(120, 0) = None
    subject: Text(160, 0) = None
    grade: Text(80, 0) = None
    country: Text(80, 0) = None


def _months_refused(error: psycopg.errors.CheckViolation) -> HTTPException:
    """A change that, with what is already stored, would break the order of the months."""
    return HTTPException(422, ENTRY_CHECKS.get(error.diag.constraint_name, END_BEFORE_START))


def _add_entry(table: str, body: BaseModel, user: User) -> dict:
    with db.transaction() as conn:
        return repo.add_entry(conn, user.id, table, body.model_dump())


def _update_entry(table: str, entry_id: UUID, body: BaseModel, user: User) -> dict:
    fields = body.model_dump(exclude_unset=True)
    try:
        with db.transaction() as conn:
            row = _found(repo.get_entry(conn, user.id, table, str(entry_id)))
            if row.get("from_details") and any(k in fields and fields[k] != row[k] for k in SET_IN_DETAILS):
                raise HTTPException(422, FROM_DETAILS)
            return _found(repo.update_entry(conn, user.id, table, str(entry_id), fields))
    except psycopg.errors.CheckViolation as e:
        raise _months_refused(e)


def _delete_entry(table: str, entry_id: UUID, user: User) -> Response:
    with db.transaction() as conn:
        row = _found(repo.get_entry(conn, user.id, table, str(entry_id)))
        if row.get("from_details"):
            raise HTTPException(422, FROM_DETAILS)
        repo.delete_entry(conn, user.id, table, str(entry_id))
    return Response(status_code=204)


@app.post("/api/work-history", status_code=201)
def add_work_history(body: JobEntry, user: CurrentUser):
    return _add_entry("work_history", body, user)


@app.patch("/api/work-history/{entry_id}")
def update_work_history(entry_id: UUID, body: JobEntryPatch, user: CurrentUser):
    return _update_entry("work_history", entry_id, body, user)


@app.delete("/api/work-history/{entry_id}", status_code=204)
def delete_work_history(entry_id: UUID, user: CurrentUser):
    return _delete_entry("work_history", entry_id, user)


@app.post("/api/education", status_code=201)
def add_education(body: CourseEntry, user: CurrentUser):
    return _add_entry("education", body, user)


@app.patch("/api/education/{entry_id}")
def update_education(entry_id: UUID, body: CourseEntryPatch, user: CurrentUser):
    return _update_entry("education", entry_id, body, user)


@app.delete("/api/education/{entry_id}", status_code=204)
def delete_education(entry_id: UUID, user: CurrentUser):
    return _delete_entry("education", entry_id, user)


class Language(BaseModel):
    language: Text(40)
    level: Literal["", *ai.LANGUAGE_LEVELS] = ""


Skills = Annotated[list[Text(60)], Field(max_length=60)]
Languages = Annotated[list[Language], Field(max_length=10)]


class SkillsIn(BaseModel):
    skills: Skills
    languages: Languages


@app.put("/api/profile/skills")
def put_skills(body: SkillsIn, user: CurrentUser):
    with db.transaction() as conn:
        repo.get_or_create_profile(conn, user.id, user.name)
        return repo.set_skills(conn, user.id, body.skills, [x.model_dump() for x in body.languages]) | {"email": user.email}


# What an import found, as the user confirmed it. An entry with an id adds to one they already
# have; one without is new. Each carries the new achievements that happened there.
class Found(BaseModel):
    id: UUID | None = None
    achievement_ids: Annotated[list[UUID], Field(max_length=50)] = []


class FoundJob(JobEntryPatch, Found):
    @model_validator(mode="after")
    def new_job_names_its_employer(self):
        if self.id is None and not self.employer:
            raise ValueError("A job needs its employer.")
        return self


class FoundCourse(CourseEntryPatch, Found):
    @model_validator(mode="after")
    def new_course_names_its_institution(self):
        if self.id is None and not self.institution:
            raise ValueError("A course needs its university, college or school.")
        return self


class FactsIn(BaseModel):
    source: Literal["voice", "paste", "cv"]
    work_history: Annotated[list[FoundJob], Field(max_length=20)] = []
    education: Annotated[list[FoundCourse], Field(max_length=20)] = []
    skills: Skills = []
    languages: Languages = []


@app.post("/api/profile/facts")
def confirm_facts(body: FactsIn, user: CurrentUser):
    """Save the jobs, courses, skills and languages the user ticked after an import, all or
    nothing. An entry that repeats one already saved fills in its blanks instead of adding a
    second, so confirming twice changes nothing."""
    try:
        with db.transaction() as conn:
            repo.get_or_create_profile(conn, user.id, user.name)
            for table, entries in (("work_history", body.work_history), ("education", body.education)):
                for entry in entries:
                    fields = entry.model_dump(exclude={"id", "achievement_ids"}, exclude_unset=True)
                    if entry.id:
                        row = repo.fill_entry(conn, user.id, table, str(entry.id), fields)
                        if row is None:  # not this user's entry: nothing is added to it or linked to it
                            continue
                    else:
                        repeats = intake.match(fields, table, repo.list_entries(conn, user.id, table))
                        row = (repo.fill_entry(conn, user.id, table, repeats["id"], fields) if repeats
                               else repo.add_entry(conn, user.id, table, fields, body.source))
                    repo.link_achievements(conn, user.id, [str(x) for x in entry.achievement_ids], **{HAPPENED_AT[table]: row["id"]})
            profile = repo.add_skills(conn, user.id, body.skills, [x.model_dump() for x in body.languages])
            return {"work_history": repo.list_entries(conn, user.id, "work_history"),
                    "education": repo.list_entries(conn, user.id, "education"), "profile": profile | {"email": user.email}}
    except psycopg.errors.CheckViolation as e:
        raise _months_refused(e)


# ---------- applications ----------

POSTED_AFTER_APPLIED = "The posting date cannot be after the application date."


class ApplicationIn(BaseModel):
    company: Text(160)
    role: Text(160)
    source: Source
    stage: Stage = "applied"
    applied_on: date | None = None  # None: today in London
    posted_on: date | None = None
    role_family_id: UUID | None = None
    cv_version_id: UUID | None = None
    saved_job_id: UUID | None = None
    job_url: Text(500, 0) | None = None
    contact: Text(200, 0) | None = None
    notes: Text(4000, 0) | None = None
    sponsor_licence: bool | None = None  # what the sponsor register said about the employer, if known
    follow_up_on: date | None = None

    @model_validator(mode="after")
    def posted_before_applied(self):
        if self.posted_on and self.applied_on and self.posted_on > self.applied_on:
            raise ValueError(POSTED_AFTER_APPLIED)
        return self


class ApplicationPatch(BaseModel):
    company: Text(160) = None
    role: Text(160) = None
    source: Source = None
    stage: Stage = None
    applied_on: date = None
    posted_on: date | None = None
    role_family_id: UUID | None = None
    cv_version_id: UUID | None = None
    saved_job_id: UUID | None = None
    job_url: Text(500, 0) | None = None
    contact: Text(200, 0) | None = None
    notes: Text(4000, 0) | None = None
    sponsor_licence: bool | None = None  # what the sponsor register said about the employer, if known
    follow_up_on: date | None = None


def _ids_as_text(fields: dict) -> dict:
    return {k: str(v) if isinstance(v, UUID) else v for k, v in fields.items()}


@app.post("/api/applications", status_code=201)
def add_application(body: ApplicationIn, user: CurrentUser):
    try:
        with db.transaction() as conn:
            return repo.add_application(conn, user.id, _ids_as_text(body.model_dump()))
    except psycopg.errors.CheckViolation:  # posted_on given without applied_on, and later than today
        raise HTTPException(422, POSTED_AFTER_APPLIED)


@app.patch("/api/applications/{app_id}")
def update_application(app_id: UUID, body: ApplicationPatch, user: CurrentUser):
    try:
        with db.transaction() as conn:
            return _found(repo.update_application(conn, user.id, str(app_id), _ids_as_text(body.model_dump(exclude_unset=True))))
    except psycopg.errors.CheckViolation:
        raise HTTPException(422, POSTED_AFTER_APPLIED)


@app.delete("/api/applications/{app_id}", status_code=204)
def delete_application(app_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        _found(repo.delete_application(conn, user.id, str(app_id)))
    return Response(status_code=204)


# ---------- jobs: real adverts matched to the user ----------
# /api/jobs/{job_id} (DELETE, above) names one of the user's saved jobs. The routes below that
# take {match_id} name the user's match with a live advert.

REED_DOWN = "We could not reach Reed. Try again shortly."
SOME_SEARCHES_FAILED = "Some searches could not be completed. Check again shortly."
NOT_SCORED_LIMIT = "You have reached today's AI limit, so new jobs were not scored. It resets at midnight."
SOME_NOT_SCORED = "Some jobs could not be scored. Check again to score them."
SPONSOR_LICENCE = {"listed": True, "not_found": False}  # a possible match or an agency advert is unknown


def _register(conn) -> dict | None:
    """How current the stored sponsor register is, for the line under every sponsorship fact."""
    meta = repo.register_meta(conn)
    return {"published_on": meta["published_on"], "loaded_at": meta["loaded_at"]} if meta else None


def _pairs(searches: list[dict]) -> list[tuple[str, str]]:
    return [(s["query"], s["location"]) for s in searches]


@app.get("/api/jobs")
def list_matched_jobs(user: CurrentUser):
    """The user's matched adverts and what the page needs around them. Changes nothing."""
    since, _ = _job_dates()
    with db.transaction() as conn:
        profile = repo.get_or_create_profile(conn, user.id, user.name)
        searches = jobs.plan(repo.list_families(conn, user.id), profile["locations"])
        due = repo.searches_due(conn, _pairs(searches), jobs.CACHE_HOURS)
        matches = repo.list_matches(conn, user.id, since)
        register = _register(conn)
    return {"matches": [m | {"senior": jobs.is_senior(m["title"])} for m in matches], "due": bool(due), "searches": len(searches),
            "register": register, "visa": visa.rules(), "include_senior": profile["include_senior"], "configured": jobs_configured(),
            "fresh_days": jobs.FRESH_DAYS, "new_days": jobs.NEW_DAYS, "score_per_refresh": jobs.SCORE_PER_REFRESH}


@app.post("/api/jobs/refresh")
def refresh_jobs(user: CurrentUser):
    """Fetch the user's searches that are due, match the adverts found, and score the most promising
    unscored ones. Reed and the model are called with no database connection open."""
    since, _ = _job_dates()
    with db.transaction() as conn:
        profile = repo.get_or_create_profile(conn, user.id, user.name)
        achievements = repo.list_achievements(conn, user.id)
        searches = jobs.plan(repo.list_families(conn, user.id), profile["locations"])
        due = repo.searches_due(conn, _pairs(searches), jobs.CACHE_HOURS)
    if not searches:
        raise HTTPException(400, "Pick your target roles first.")
    if not achievements:
        raise HTTPException(400, "Build your profile first.")
    to_run = [s for s in searches if (s["query"], s["location"]) in due]
    if to_run and not jobs_configured():
        raise HTTPException(503, "Job search is not set up on the server.")
    batch = to_run[:jobs.SEARCHES_PER_REFRESH]

    found, failed = jobs.fetch(batch)
    notices = [REED_DOWN] if batch and failed == len(batch) else [SOME_SEARCHES_FAILED] if failed else []

    family_of = {(s["query"], s["location"]): s["family_id"] for s in searches}
    with db.transaction() as conn:
        repo.store_searches(conn, found)
        repo.purge_old_listings(conn)
        listings = jobs.dedupe(repo.listings_for_searches(conn, list(family_of), since), keep=repo.matched_listings(conn, user.id))
        new = repo.add_matches(conn, user.id, [
            {"listing_id": item["id"], "role_family_id": family_of[(item["query"], item["search_location"])],
             "search_location": item["search_location"]} for item in listings])
        shortlist = jobs.shortlist(repo.unscored_matches(conn, user.id, since), jobs.skills_of(achievements),
                                   profile["include_senior"], jobs.SCORE_PER_REFRESH)
        scoring = bool(shortlist) and limits.allowed(conn, user.id, "ai")
        if scoring:
            repo.record_usage(conn, user.id, "ai", "jobs")
    if shortlist and not scoring:  # the adverts are still listed, just not judged
        notices.append(NOT_SCORED_LIMIT)

    scored = 0
    if scoring:
        details = jobs.fetch_details(shortlist)
        failure = None
        try:
            rows, missed = jobs.score([c | details.get(c["listing_id"], {}) for c in shortlist], achievements)
        except ai.AIError as e:
            rows, missed, failure = [], 0, e
        with db.transaction() as conn:
            for listing_id, full in details.items():  # adverts are public facts, kept whatever the model did
                repo.set_listing_details(conn, listing_id, full)
            repo.save_scores(conn, user.id, rows)
        if failure:
            raise failure
        scored = len(rows)
        if missed:
            notices.append(SOME_NOT_SCORED)
    return {"searched": len(found), "remaining": len(to_run) - len(batch), "new": new, "scored": scored, "notice": " ".join(notices) or None}


@app.post("/api/jobs/seen", status_code=204)
def jobs_seen(user: CurrentUser):
    """The user has looked at their new matches. Separate from the list so that reading it changes nothing."""
    with db.transaction() as conn:
        repo.mark_matches_seen(conn, user.id)
    return Response(status_code=204)


class JobPreferences(BaseModel):
    include_senior: bool


@app.put("/api/jobs/preferences")
def put_job_preferences(body: JobPreferences, user: CurrentUser):
    with db.transaction() as conn:
        repo.get_or_create_profile(conn, user.id, user.name)
        repo.set_include_senior(conn, user.id, body.include_senior)
    return {"include_senior": body.include_senior}


def _save_match(user: User, match_id: str) -> tuple[dict, dict]:
    """Copy a matched advert into the user's saved jobs, fetching the full text first if only the
    short search text is stored. Returns the saved job and the match."""
    with db.transaction() as conn:
        match = _found(repo.get_match(conn, user.id, match_id))
    full = None
    if not match["description_is_full"]:
        try:
            full = reed.details(match["source_id"])
        except reed.ReedError:
            raise HTTPException(502, "We could not fetch the full advert from Reed. Try again.")
    with db.transaction() as conn:
        if full:
            repo.set_listing_details(conn, match["listing_id"], full)
        return _found(repo.save_listing_as_job(conn, user.id, match_id)), match


@app.post("/api/jobs/{match_id}/save")
def save_matched_job(match_id: UUID, user: CurrentUser):
    return _save_match(user, str(match_id))[0]


@app.post("/api/jobs/{match_id}/hide", status_code=204)
def hide_matched_job(match_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        _found(repo.hide_match(conn, user.id, str(match_id)))
    return Response(status_code=204)


@app.post("/api/jobs/{match_id}/track", status_code=201)
def track_matched_job(match_id: UUID, user: CurrentUser, response: Response):
    """Save the advert and log an application for it, carrying its link, posting date and what
    the register says about the employer. Doing it twice gives the same application."""
    job, match = _save_match(user, str(match_id))
    with db.transaction() as conn:
        existing = repo.application_for_job(conn, user.id, job["id"])
        if existing:
            response.status_code = 200
            return existing
        return repo.add_application(conn, user.id, {
            "company": job["company"], "role": job["title"], "saved_job_id": job["id"], "role_family_id": job["role_family_id"],
            "source": "Reed", "job_url": job["url"], "posted_on": min(job["posted_on"], date.today()),
            "sponsor_licence": SPONSOR_LICENCE.get(match["sponsor_status"])})


class Offer(BaseModel):
    salary: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    employer: Text(160, 0) | None = None


@app.post("/api/visa-facts")
def visa_facts(body: Offer, user: CurrentUser):
    """The offer check: a salary beside the published Skilled Worker figures, and what the register
    says about an employer. Facts with their sources, never a verdict. The offer travels in the
    request body, so it never appears in an address or a log line."""
    with db.transaction() as conn:
        sponsor = sponsors.status(conn, body.employer) if body.employer else None
        register = _register(conn)
    return visa.salary_facts(body.salary, body.salary, bool(body.salary)) | {"sponsor": sponsor, "register": register}


@app.get("/api/internal/refresh-sponsors")
def refresh_sponsor_register(authorization: Annotated[str | None, Header()] = None):
    """Reload the sponsor register from gov.uk. For the weekly scheduled job, which sends the
    shared secret; nobody is signed in. Vercel's scheduler calls with GET."""
    secret = cron_secret()
    if not secret or not hmac.compare_digest((authorization or "").encode(), f"Bearer {secret}".encode()):
        raise HTTPException(401, "Not allowed.")
    try:
        done = sponsors.refresh()
    except sponsors.RegisterError as e:
        log.error("sponsor register reload failed: %s", e)
        raise HTTPException(502, "The sponsor register could not be reloaded. The stored copy is unchanged.")
    return done


# ---------- AI ----------
# Each route reads what it needs and counts the use in one short transaction, calls the model
# with no database connection open, then writes the result in a second transaction.

MIN_TEXT, MAX_TEXT = 20, 30_000
MIN_JOB, MAX_JOB = 30, 20_000


def _check_length(text: str, minimum: int, maximum: int, too_short: str) -> str:
    text = text.strip()
    if len(text) < minimum:
        raise HTTPException(422, too_short)
    if len(text) > maximum:
        raise HTTPException(422, "That is too long. Shorten it and try again.")
    return text


def _start_ai(user: User, action: str) -> dict:
    """Count one AI action for the user and return their profile for the prompt."""
    with db.transaction() as conn:
        limits.check_and_record(conn, user.id, "ai", action)
        return repo.get_or_create_profile(conn, user.id, user.name)


class Background(BaseModel):
    transcript: str
    source: Literal["voice", "paste"] = "voice"


@app.post("/api/ai/achievements")
def ai_achievements(body: Background, user: CurrentUser):
    transcript = _check_length(body.transcript, MIN_TEXT, MAX_TEXT, "Say or paste a bit more first.")
    profile = _start_ai(user, "achievements")
    result = ai.extract_achievements(transcript, profile)
    if not result["items"]:
        raise HTTPException(422, "We could not find any achievements in that. Add more detail and try again.")
    with db.transaction() as conn:
        items = repo.add_achievements(conn, user.id, result["items"], body.source)
        if result["pitch"]:
            repo.set_pitch(conn, user.id, result["pitch"])
        repo.add_journal_entry(
            conn, user.id, type="coach", with_whom="Careers coach",
            title="Background call with your careers coach" if body.source == "voice" else "Profile built from your pasted background",
            summary=f"{analytics.plural(len(items), 'achievement')} captured and rewritten for UK employers.",
            points=[i["title"] for i in items], actions=["Review your profile and add any missing numbers"],
            transcript=transcript)
    return {"items": items, "pitch": result["pitch"]}


@app.post("/api/ai/families")
def ai_families(user: CurrentUser):
    with db.transaction() as conn:
        achievements = repo.list_achievements(conn, user.id)
    if not achievements:
        raise HTTPException(400, "Build your profile first.")
    profile = _start_ai(user, "families")
    result = ai.suggest_families(achievements, profile)
    with db.transaction() as conn:
        return {"families": repo.sync_families(conn, user.id, result["families"])}


class JobIn(BaseModel):
    title: Text(160)
    company: Text(160)
    description: str
    url: Text(500, 0) | None = None
    location: Text(120, 0) | None = None


@app.post("/api/jobs", status_code=201)
def add_job(body: JobIn, user: CurrentUser):
    description = _check_length(body.description, MIN_JOB, MAX_JOB, "Paste the full job description.")
    with db.transaction() as conn:
        families = repo.list_families(conn, user.id)
        use_ai = limits.allowed(conn, user.id, "ai")
        if use_ai:
            repo.record_usage(conn, user.id, "ai", "job")
    summary = {"summary": description[:300], "keywords": [], "family": ""}  # the job is saved even if the AI is not available
    if use_ai:
        try:
            summary = ai.summarise_job(body.title, body.company, description, [f["name"] for f in families])
        except (ai.AIError, LLMNotConfigured):
            log.warning("job summary unavailable; saving the job without one")
    family_id = next((f["id"] for f in families if f["name"] == summary["family"]), None)
    with db.transaction() as conn:
        return repo.add_job(conn, user.id, title=body.title, company=body.company, location=body.location or None,
                            url=body.url or None, description=description, summary=summary["summary"],
                            keywords=summary["keywords"], role_family_id=family_id)


class JobRef(BaseModel):
    job_id: UUID


@app.post("/api/ai/tailor")
def ai_tailor(body: JobRef, user: CurrentUser):
    with db.transaction() as conn:
        job = _found(repo.get_job(conn, user.id, str(body.job_id)))
        achievements = repo.list_achievements(conn, user.id)
    if not achievements:
        raise HTTPException(400, "Build your profile first.")
    profile = _start_ai(user, "tailor")
    tailored = ai.tailor(job, achievements, profile)
    with db.transaction() as conn:
        return repo.add_cv_version(conn, user.id, saved_job_id=job["id"], role_family_id=job["role_family_id"],
                                   base_name=f"{job['title']}, {job['company']}", content=tailored)


class AchievementRef(BaseModel):
    achievement_id: UUID


@app.post("/api/ai/star")
def ai_star(body: AchievementRef, user: CurrentUser):
    with db.transaction() as conn:
        achievement = _found(repo.get_achievement(conn, user.id, str(body.achievement_id)))
    _start_ai(user, "star")
    story = ai.star(achievement)
    with db.transaction() as conn:
        return repo.add_story(conn, user.id, achievement["id"], story)


class InterviewIn(BaseModel):
    transcript: str
    job_id: UUID | None = None
    interview_type: Text(80) = "Job-specific interview"


@app.post("/api/ai/interview-feedback")
def ai_interview(body: InterviewIn, user: CurrentUser):
    transcript = _check_length(body.transcript, MIN_TEXT, MAX_TEXT, "Say or paste a bit more first.")
    job = None
    if body.job_id:
        with db.transaction() as conn:
            job = _found(repo.get_job(conn, user.id, str(body.job_id)))
    profile = _start_ai(user, "interview")
    feedback = ai.interview_feedback(transcript, job, profile, body.interview_type)
    about = f"{job['title']}, {job['company']}" if job else "general practice"
    with db.transaction() as conn:
        repo.add_journal_entry(conn, user.id, type="interview", title=f"{body.interview_type}: {about}", with_whom="Mock interviewer",
                               summary=feedback["summary"], points=[p["point"] for p in feedback["strengths"]],
                               actions=[p["point"] for p in feedback["fixes"]], scores=feedback["scores"], transcript=transcript)
    return feedback


@app.get("/api/journal/{entry_id}/transcript")
def journal_transcript(entry_id: UUID, user: CurrentUser):
    """What was said in a coach call or mock interview. Fetched on demand, since it can be long."""
    with db.transaction() as conn:
        return {"transcript": _found(repo.get_journal_transcript(conn, user.id, str(entry_id)))}


class ToneIn(BaseModel):
    text: Text(1000)
    mode: Literal["decode", "rewrite"] = "decode"


@app.post("/api/ai/tone")
def ai_tone(body: ToneIn, user: CurrentUser):
    _start_ai(user, "tone")
    return ai.tone(body.text, body.mode)


@app.post("/api/ai/diagnosis")
def ai_diagnosis(user: CurrentUser):
    with db.transaction() as conn:
        state = repo.load_state(conn, user.id)
    if not state["applications"]:
        raise HTTPException(400, "Log some applications first.")
    profile = _start_ai(user, "diagnosis")
    stats = analytics.compute(state["applications"], state["role_families"], state["cv_versions"], state["stories"])
    return ai.explain_diagnosis(stats["findings"], stats, profile)


# ---------- voice ----------

VOICE_DOWN = "Voice is unavailable right now."
RETRY_WINDOW_S = 120  # the browser's automatic WebSocket retry of the same call is not a second session


@app.get("/api/voice/token")
def voice_token(agent: Literal["onboarding", "interviewer"], user: CurrentUser,
                transport: Literal["webrtc", "websocket"] = "webrtc"):
    if not voice_configured(agent):
        raise HTTPException(503, VOICE_DOWN)
    with db.transaction() as conn:
        since = repo.seconds_since_last_usage(conn, user.id, "voice", agent) if transport == "websocket" else None
        is_retry = since is not None and since <= RETRY_WINDOW_S
        if not is_retry and not limits.allowed(conn, user.id, "voice"):
            raise limits.LimitReached("voice")
    try:
        minted = {"signed_url": voice.signed_url(agent)} if transport == "websocket" else {"token": voice.conversation_token(agent)}
    except Exception:
        log.exception("ElevenLabs token request failed")
        raise HTTPException(502, VOICE_DOWN)
    if not is_retry:  # counted only once a session could actually start
        with db.transaction() as conn:
            repo.record_usage(conn, user.id, "voice", agent)
    return minted


@app.get("/api/voice/transcript/{conversation_id}")
def voice_transcript(conversation_id: str, user: CurrentUser):
    try:
        return {"turns": voice.fetch_transcript(conversation_id, user.id)}
    except PermissionError:
        raise HTTPException(404, GONE)
    except Exception:
        log.exception("transcript fetch failed")
        raise HTTPException(502, "Could not fetch the transcript.")
