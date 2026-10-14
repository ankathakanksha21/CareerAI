"""UK Career Navigator API. Routes only: check who is calling, validate the input, call the
modules, return JSON. Every route except /api/config needs a signed-in user and touches
only that user's rows."""
import hmac
import logging
import re
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

import ai
import analytics
import companies_house
import content
import cv
import cvbuild
import cvfile
import db
import fetcher
import github
import habits
import intake
import jobs
import limits
import prep
import reed
import repo
import research
import sponsors
import stories
import visa
import voice
from auth import User, current_user
from config import cron_secret, env, jobs_configured, llm_configured, research_configured, supabase_url, voice_configured
from llm import LLMNotConfigured
from parallel import together

logging.basicConfig(level=logging.INFO)
# httpx logs the address of every outside call it makes. Those addresses can hold what a user typed
# (a GitHub username) or who they are (the account being deleted), so only its warnings are kept
logging.getLogger("httpx").setLevel(logging.WARNING)
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


@app.exception_handler(github.GitHubError)
def github_failed(request, exc):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


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


def _pages() -> set[str]:
    """The pages this build has, so the weekly plan never offers a task on one that is not there."""
    return {"home", "profile", "pathways", "resume", "interview", "applications", "journal"} | ({"jobs"} if jobs_configured() else set())


def _habits(state: dict, profile: dict, tracked: dict, stats: dict, fresh_jobs: int) -> dict:
    """This week, the streak, milestones, follow-ups due and the weekly plan, all worked out now
    from the user's own rows. `tracked` holds the rows read for them (see get_state)."""
    apps, practice, goals, today = state["applications"], tracked["practice"], tracked["goals"], tracked["today"]
    week = habits.this_week(applications=apps, practice_days=practice, goals=goals, today=today)
    streak = habits.streaks(applications=apps, practice_days=practice, goals=goals, started=tracked["started"], today=today)
    reached = habits.milestones(applications=apps, events=tracked["events"], practice_count=len(practice),
                                story_count=len(state["stories"]), best_streak=streak["best"])
    follow_ups = habits.follow_ups_due(apps, tracked["events"], today)
    plan = habits.weekly_plan(follow_ups=follow_ups, findings=stats["findings"], fresh_jobs=fresh_jobs, week=week,
                              story_count=len(state["stories"]), missing_numbers=sum(a["needs_number"] for a in state["achievements"]),
                              pages=_pages())
    return {
        "habits": {"this_week": week, "streak": streak["current"], "best_streak": streak["best"], "milestones": reached,
                   "new_milestones": [{"id": m, "text": habits.MILESTONES[m]} for m in reached if m not in profile["milestones_seen"]]},
        "follow_ups_due": follow_ups,
        "plan": plan,
    }


def _with_history(applications: list, events: list) -> list:
    history = {}
    for e in events:
        history.setdefault(e["application_id"], []).append({"from_stage": e["from_stage"], "to_stage": e["to_stage"], "at": e["at"]})
    return [a | {"history": history.get(a["id"], [])} for a in applications]


@app.get("/api/state")
def get_state(user: CurrentUser):
    since, fresh_since = _job_dates()
    with db.transaction() as conn:
        profile = repo.get_or_create_profile(conn, user.id, user.name)
        state = repo.load_state(conn, user.id)
        state["achievements"] = [_achievement(a) for a in state["achievements"]]
        state["cv_versions"] = [_version(v) for v in state["cv_versions"]]
        usage = limits.usage(conn, user.id)
        job_counts = repo.job_counts(conn, user.id, since, fresh_since)
        market = jobs.market(repo.family_market(conn, user.id, since))
        tracked = {"events": repo.list_application_events(conn, user.id), "goals": repo.list_goals(conn, user.id),
                   "practice": repo.practice_days(conn, user.id), "started": repo.account_started(conn, user.id),
                   "today": repo.today(conn)}
    stats = analytics.compute(state["applications"], state["role_families"], state["cv_versions"], state["stories"], market)
    progress = _habits(state, profile, tracked, stats, job_counts["fresh"] if jobs_configured() else 0)
    state["applications"] = _with_history(state["applications"], tracked["events"])
    return state | progress | {
        "profile": profile | {"email": user.email},
        "details_complete": repo.details_complete(profile),
        "stats": stats,
        "next_steps": analytics.next_steps(state),
        "content": content.load(),
        "usage": usage,
        "jobs": job_counts,   # matching adverts not yet seen, and how many of those were just posted
        "market": market,     # live figures for each targeted role family
        "options": {"sources": analytics.SOURCES, "stages": analytics.STAGES, "language_levels": ai.LANGUAGE_LEVELS,
                    "competencies": [[k, label] for k, label in ai.COMPETENCIES.items()], "interview_types": prep.INTERVIEW_TYPES},
        "config": {"llm": llm_configured(), "jobs": jobs_configured(), "prep": research_configured() and llm_configured(),
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
    competencies: list[Literal[tuple(ai.COMPETENCIES)]] = Field(None, max_length=ai.MAX_COMPETENCIES)

    @field_validator("competencies")
    @classmethod
    def _once_each(cls, value):
        return list(dict.fromkeys(value)) if value is not None else value


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


BAD_PHONE = "Enter a phone number using digits, spaces and + ( ) - only."
BAD_LINKEDIN = "Enter your LinkedIn address, for example linkedin.com/in/your-name."
LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?((?:[a-z]{2,3}\.)?linkedin\.com)(/[\w\-.~%/+@]+)", re.I)


def _linkedin(value: str) -> str:
    """A LinkedIn address as a CV prints it: on linkedin.com, with no scheme, no "www." and nothing after the path."""
    if not value:
        return ""
    found = LINKEDIN.fullmatch(value.split("?")[0].split("#")[0].rstrip("/"))
    if not found:
        raise ValueError(BAD_LINKEDIN)
    return f"{found[1].lower()}{found[2]}"


class ContactIn(BaseModel):
    """The contact line of a CV. All optional: the name and the email come from the account."""
    phone: Text(40, 0) = ""
    city: Text(80, 0) = ""
    linkedin_url: Text(200, 0) = ""

    @field_validator("phone")
    @classmethod
    def phone_characters(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9+() .\-]*", value):
            raise ValueError(BAD_PHONE)
        return value

    @field_validator("linkedin_url")
    @classmethod
    def on_linkedin(cls, value: str) -> str:
        return _linkedin(value)


@app.put("/api/profile/contact")
def put_contact(body: ContactIn, user: CurrentUser):
    with db.transaction() as conn:
        repo.get_or_create_profile(conn, user.id, user.name)
        return repo.set_contact(conn, user.id, **body.model_dump()) | {"email": user.email}


class AdditionalIn(BaseModel):
    lines: Annotated[list[Text(200, 0)], Field(max_length=12)]  # certifications, awards, volunteering: one line each


@app.put("/api/profile/additional")
def put_additional(body: AdditionalIn, user: CurrentUser):
    with db.transaction() as conn:
        repo.get_or_create_profile(conn, user.id, user.name)
        return repo.set_additional(conn, user.id, body.lines) | {"email": user.email}


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


# ---------- CVs ----------
# A CV is built by POST /api/ai/cv (with the other AI routes, below), then edited, downloaded
# and deleted here. Its facts are the user's records; only wording, order and what is shown change.

OLD_FORMAT = "This CV was made before full CVs. Rebuild it to edit or download it."
CV_IN_USE = "This CV is attached to an application. Remove it from the application first."
NO_LETTER = "A base CV has no cover letter."
BASE_CV = "Base CV"


def _version(row: dict) -> dict:
    """A CV version as the pages get it: with the characters its PDF cannot show."""
    full = row["format_version"] == 2
    return row | {"unsupported": cvbuild.unsupported(row["content"], row["contact_name"]) if full else ""}


def _full_cv(row: dict) -> dict:
    """A version that holds the whole document. One made before full CVs can only be read, rebuilt or deleted."""
    if row["format_version"] != 2:
        raise HTTPException(422, OLD_FORMAT)
    return row


def _cv_records(conn, user: User) -> dict:
    """Everything of the user's that a CV is made from."""
    return {"profile": repo.get_or_create_profile(conn, user.id, user.name), "email": user.email,
            "education": repo.list_entries(conn, user.id, "education"), "work_history": repo.list_entries(conn, user.id, "work_history"),
            "achievements": repo.list_achievements(conn, user.id)}


class CvEdit(BaseModel):
    content: dict                             # the CV as edited: its wording, order and what is hidden are kept, never a fact
    contact_name: Text(120, 0) | None = None  # who the cover letter is to; left out: as it was
    refresh_facts: bool = False               # copy employers, dates, courses and contact details from the profile again


@app.patch("/api/cv-versions/{version_id}")
def update_cv(version_id: UUID, body: CvEdit, user: CurrentUser):
    """Save an edit. A version an application was sent with never changes: the edit is saved as a
    new version instead, and the answer says which one it replaced on screen."""
    with db.transaction() as conn:
        stored = _full_cv(_found(repo.get_cv_version(conn, user.id, str(version_id))))
        records = _cv_records(conn, user)
    content, pages = cvbuild.revise(stored["content"], body.content, **records, refresh=body.refresh_facts)
    contact_name = stored["contact_name"] if body.contact_name is None else body.contact_name
    with db.transaction() as conn:
        if repo.cv_version_in_use(conn, user.id, stored["id"]):  # asked now, not earlier: it may have been sent a moment ago
            saved = repo.add_cv_version(conn, user.id, saved_job_id=stored["saved_job_id"], role_family_id=stored["role_family_id"],
                                        base_name=re.sub(r" v\d+$", "", stored["name"]), content=content, kind=stored["kind"], pages=pages,
                                        contact_name=contact_name)
            return _version(saved) | {"replaced": stored["id"]}
        saved = _found(repo.update_cv_version(conn, user.id, stored["id"], content=content, pages=pages, contact_name=contact_name))
        return _version(saved) | {"replaced": None}


@app.delete("/api/cv-versions/{version_id}", status_code=204)
def delete_cv(version_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        deleted = repo.delete_cv_version(conn, user.id, str(version_id))
    if deleted is None:
        raise HTTPException(404, GONE)
    if not deleted:
        raise HTTPException(409, CV_IN_USE)
    return Response(status_code=204)


@app.get("/api/cv-versions/{version_id}/download")
def download_cv(version_id: UUID, user: CurrentUser, kind: Annotated[Literal["docx", "pdf"], Query(alias="format")],
                part: Literal["cv", "letter"] = "cv"):
    """The CV or its cover letter as a Word or PDF file, made now from the saved version and not kept."""
    with db.transaction() as conn:
        version = _full_cv(_found(repo.get_cv_version(conn, user.id, str(version_id))))
        today = repo.today(conn)
    if part == "letter" and not version["content"].get("cover_letter"):
        raise HTTPException(422, NO_LETTER)
    data, name = cvbuild.file(version["content"], version["contact_name"], part, kind, today)
    return Response(data, media_type=cvbuild.MEDIA[kind],
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


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
    contact_name: Text(120, 0) | None = None  # the only part of the contact ever sent to the AI
    contact: Text(200, 0) | None = None       # how to reach them
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
    contact_name: Text(120, 0) | None = None
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


# ---------- the tracker's habits: rejections, follow-ups, goals, milestones ----------

NOTHING_TO_COMPARE = ("No CV or job description was recorded for this application, so there is nothing to compare. "
                      "Attach both next time.")
ENDED = "This application has ended, so there is nothing to follow up."
LESSON_CHANGED = ("This application changed while the lesson was being written, so it was not saved. "
                  "Ask for it again from the application.")


class RejectIn(BaseModel):
    ended_at: Literal[tuple(repo.ENDED_AT)]
    feedback: Text(2000, 0) = ""


def _cv_text(version: dict | None) -> str:
    """What a reader of the CV that was sent would see. Never the contact line: it is not the model's business."""
    if not version:
        return ""
    content = version["content"]
    if version["format_version"] == 2:
        return cv.text(content)
    return "\n".join(p for p in [content.get("profile"), *[b.get("text") for b in content.get("bullets") or []]] if p)


@app.post("/api/applications/{app_id}/reject")
def reject_application(app_id: UUID, body: RejectIn, user: CurrentUser):
    """Record where a rejection ended and any feedback, then write one lesson from the CV that was
    sent and the job description. The rejection is saved first, so it stands if the daily limit is
    reached or the model fails; sending the same answers again retries the lesson."""
    with db.transaction() as conn:
        application = _found(repo.reject_application(conn, user.id, str(app_id), ended_at=body.ended_at, feedback=body.feedback))
        version = repo.get_cv_version(conn, user.id, application["cv_version_id"]) if application["cv_version_id"] else None
        job_id = application["saved_job_id"] or (version or {}).get("saved_job_id")
        job = repo.get_job(conn, user.id, job_id) if job_id else None
    cv_text = _cv_text(version)
    if not cv_text and not job:
        return {"application": application, "lesson": None, "notice": NOTHING_TO_COMPARE}
    _start_ai(user, "lesson")
    lesson = ai.rejection_lesson(job=job, cv_text=cv_text, ended_at=body.ended_at, feedback=application["feedback_received"] or "")
    with db.transaction() as conn:
        lesson["made_on"] = repo.today(conn).isoformat()
        saved = repo.set_lesson(conn, user.id, application["id"], lesson, ended_at=body.ended_at)
        if saved is None:  # moved out of Rejected, or answered again, while the model was writing
            return {"application": _found(repo.get_application(conn, user.id, application["id"])), "lesson": None, "notice": LESSON_CHANGED}
    return {"application": saved, "lesson": saved["lesson"], "notice": None}


@app.post("/api/ai/applications/{app_id}/follow-up")
def ai_follow_up(app_id: UUID, user: CurrentUser):
    """A short follow-up message for the user to copy. Nothing is ever sent for them."""
    with db.transaction() as conn:
        application = _found(repo.get_application(conn, user.id, str(app_id)))
    if application["stage"] in repo.CLOSED:
        raise HTTPException(400, ENDED)
    profile = _start_ai(user, "follow up")
    return ai.follow_up(role=application["role"], company=application["company"], applied_on=application["applied_on"],
                        contact_name=application["contact_name"] or "", sender=profile["full_name"])


@app.post("/api/applications/{app_id}/followed-up")
def followed_up(app_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        return _found(repo.mark_followed_up(conn, user.id, str(app_id), repo.today(conn)))


class GoalsIn(BaseModel):
    applications: int = Field(ge=1, le=30)  # never 0: a goal of nothing would build a streak from nothing
    practice: int = Field(ge=0, le=14)


@app.put("/api/profile/goals")
def put_goals(body: GoalsIn, user: CurrentUser):
    """Set the weekly goals. The first goal a user sets applies to this week; any later change
    from next Monday, so a week in progress can never be made easier."""
    with db.transaction() as conn:
        starts = habits.goal_starts(repo.today(conn), repo.list_goals(conn, user.id))
        saved = repo.set_goal(conn, user.id, effective_from=starts, applications=body.applications, practice=body.practice)
    return {"goal": {"applications": saved["applications"], "practice": saved["practice"]}, "starts_on": saved["effective_from"]}


class MilestonesSeen(BaseModel):
    ids: list[Literal[tuple(habits.MILESTONES)]] = Field(max_length=len(habits.MILESTONES))


@app.post("/api/milestones/seen", status_code=204)
def milestones_seen(body: MilestonesSeen, user: CurrentUser):
    with db.transaction() as conn:
        repo.get_or_create_profile(conn, user.id, user.name)
        repo.mark_milestones_seen(conn, user.id, body.ids)
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


# ---------- building a profile: a coach call, pasted text, a CV file, GitHub ----------

NOTHING_FOUND = "We could not find any achievements in that. Add more detail and try again."
FILE_CUT = "That file is long, so only the first part of it was read."
# How each kind of import is counted against the daily limit and logged in the journal: action, entry type, with whom, title
IMPORTS = {
    "voice": ("achievements", "coach", "Careers coach", "Background call with your careers coach"),
    "paste": ("achievements", "coach", "Careers coach", "Profile built from your pasted background"),
    "cv": ("cv", "import", "", "Profile built from your uploaded CV"),
}


def _import_background(user: User, text: str, source: str) -> dict:
    """Turn a user's own account of their background into saved achievements and proposed CV
    facts. Achievements are saved at once, each linked to the job or course it happened in when
    that is already saved. Jobs, courses, skills and languages are only offered: they are saved
    when the user confirms them (POST /api/profile/facts)."""
    action, kind, with_whom, title = IMPORTS[source]
    with db.transaction() as conn:
        limits.check_and_record(conn, user.id, "ai", action)
        profile = repo.get_or_create_profile(conn, user.id, user.name)
        achievements = repo.list_achievements(conn, user.id)
        work, education = repo.list_entries(conn, user.id, "work_history"), repo.list_entries(conn, user.id, "education")
    found = intake.read(text, profile, source, achievements)
    placed = intake.place(found["items"], found["facts"], work, education)
    with db.transaction() as conn:
        saved = repo.add_achievements(conn, user.id, placed, source)
        offered = intake.proposals(found["facts"], placed, saved, work, education, profile)
        if not saved and not (offered and any(offered.values())):
            raise HTTPException(422, NOTHING_FOUND)
        if found["pitch"] and saved:
            repo.set_pitch(conn, user.id, found["pitch"])
        repo.add_journal_entry(
            conn, user.id, type=kind, with_whom=with_whom, title=title,
            summary=(f"{analytics.plural(len(saved), 'achievement')} captured and rewritten for UK employers." if saved
                     else "Nothing new to add as achievements. Your work history and education were read for you to confirm."),
            points=[i["title"] for i in saved], actions=["Review your profile and add any missing numbers"], transcript=text)
    return {"items": [_achievement(a) for a in saved], "pitch": found["pitch"], "facts": offered,
            "notice": intake.FACTS_FAILED if found["facts"] is None else None}


class Background(BaseModel):
    transcript: str
    source: Literal["voice", "paste"] = "voice"


@app.post("/api/ai/achievements")
def ai_achievements(body: Background, user: CurrentUser):
    transcript = _check_length(body.transcript, MIN_TEXT, MAX_TEXT, "Say or paste a bit more first.")
    return _import_background(user, transcript, body.source)


async def upload_bytes(request: Request, user: CurrentUser) -> bytes:
    """The body of an upload, held in memory and never more than one chunk past the limit. It is
    read as the raw request body, not as a form: a form upload would be spooled to a temporary
    file on disk, and an uploaded CV must never be written anywhere. Signed-in users only."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > cvfile.MAX_BYTES:
        raise HTTPException(413, cvfile.TOO_BIG)
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > cvfile.MAX_BYTES:
            raise HTTPException(413, cvfile.TOO_BIG)
    return bytes(data)


@app.post("/api/ai/achievements/upload")
def ai_achievements_upload(data: Annotated[bytes, Depends(upload_bytes)], user: CurrentUser):
    """A PDF or Word CV. The file is read into text and dropped; a file that cannot be read is
    refused before anything is counted or sent to the model."""
    try:
        text, cut = cvfile.text(data)
    except cvfile.Unreadable as e:
        raise HTTPException(422, str(e))
    result = _import_background(user, text, "cv")
    notices = [FILE_CUT] if cut else []
    return result | {"cut": cut, "notice": " ".join(notices + [result["notice"] or ""]).strip() or None}


GitHubUser = StringConstraints(pattern=f"^{github.USERNAME}$")
MAX_REPOS = 5
NOT_LISTED = "Pick repositories from the list."
ALREADY_IMPORTED = "Those repositories are already in your profile."
NOTHING_TO_READ = "Those repositories have no README or description to read."


class GitHubName(BaseModel):
    username: Annotated[str, GitHubUser]


@app.post("/api/github/repos")
def github_repos(body: GitHubName, user: CurrentUser):
    """A GitHub user's public repositories that are their own work, each marked if already imported.
    The username travels in the request body, so it never appears in an address or an access log."""
    found = github.repos(body.username)
    with db.transaction() as conn:
        imported = repo.imported_urls(conn, user.id)
    return {"username": body.username, "repos": [r | {"imported": r["url"] in imported} for r in found]}


class GitHubImport(BaseModel):
    username: Annotated[str, GitHubUser]
    repos: Annotated[list[Annotated[str, StringConstraints(pattern=f"^{github.REPO}$")]], Field(min_length=1, max_length=MAX_REPOS)]


@app.post("/api/ai/achievements/github")
def ai_achievements_github(body: GitHubImport, user: CurrentUser):
    """Turn up to five of a GitHub user's repositories into project achievements. Everything
    that can fail without the model (GitHub, a name that is not theirs, nothing to read) is
    settled before the AI action is counted."""
    listed = {r["name"]: r for r in github.repos(body.username)}
    names = list(dict.fromkeys(body.repos))
    if any(name not in listed for name in names):  # also a fork or a private repository: those are never listed
        raise HTTPException(422, NOT_LISTED)
    with db.transaction() as conn:
        imported = repo.imported_urls(conn, user.id)
    chosen = [listed[name] for name in names if listed[name]["url"] not in imported]
    if not chosen:
        raise HTTPException(422, ALREADY_IMPORTED)
    readmes = together(lambda r: github.readme(body.username, r["name"]), chosen)
    readable = [r | {"readme": text} for r, text in zip(chosen, readmes) if text or r["description"]]
    if not readable:
        raise HTTPException(422, NOTHING_TO_READ)
    repos = [r | {"n": n} for n, r in enumerate(readable, start=1)]

    _start_ai(user, "github")
    found = ai.github_achievements(repos)
    items = [found[r["n"]] | {"source_url": r["url"]} for r in repos if r["n"] in found]
    missed = len(chosen) - len(items)
    with db.transaction() as conn:
        saved = repo.add_achievements(conn, user.id, items, "github")
        repo.set_github_username(conn, user.id, body.username)
        repo.add_journal_entry(
            conn, user.id, type="import", with_whom="", title="Projects imported from GitHub",
            summary=f"{analytics.plural(len(saved), 'project')} added from github.com/{body.username}.",
            points=[i["title"] for i in saved], actions=["Add a number to each project where you can"],
            transcript="\n\n".join(f"{r['name']}\n{r['description']}\n{r['readme']}".strip() for r in repos))
    notice = f"{missed} {'repository' if missed == 1 else 'repositories'} said too little to describe." if missed else None
    return {"items": [_achievement(a) for a in saved], "notice": notice}


class ImproveIn(BaseModel):
    note: Text(300, 0) = ""  # what the user adds: usually the missing number


@app.post("/api/ai/achievements/{achievement_id}/improve")
def ai_improve(achievement_id: UUID, body: ImproveIn, user: CurrentUser):
    """Rewrite one achievement from its own facts and the user's note, and save it. The answer
    carries what it replaced, so the page can offer to undo."""
    with db.transaction() as conn:
        achievement = _found(repo.get_achievement(conn, user.id, str(achievement_id)))
    _start_ai(user, "improve")
    better = ai.improve(achievement, body.note)
    with db.transaction() as conn:
        updated = _found(repo.update_achievement(conn, user.id, achievement["id"], better))
    return {"achievement": _achievement(updated), "previous": {k: achievement[k] for k in better}}


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


class CvIn(BaseModel):
    job_id: UUID | None = None  # none: a base CV from the whole profile


@app.post("/api/ai/cv")
def ai_cv(body: CvIn, user: CurrentUser):
    """Build a CV: for one saved job, with a cover letter, or a base CV for no job. The model
    writes the profile paragraph, picks and rewords bullets and sorts skills; every fact is copied
    from the user's records. One AI action; nothing is saved unless every call succeeds."""
    with db.transaction() as conn:
        job = _found(repo.get_job(conn, user.id, str(body.job_id))) if body.job_id else None
        records = _cv_records(conn, user)
        today = repo.today(conn)
    if not records["achievements"]:
        raise HTTPException(400, "Build your profile first.")
    _start_ai(user, "cv")
    content, pages = cvbuild.build(**records, job=job, today=today)
    with db.transaction() as conn:
        return _version(repo.add_cv_version(
            conn, user.id, saved_job_id=job["id"] if job else None, role_family_id=job["role_family_id"] if job else None,
            base_name=f"{job['title']}, {job['company']}" if job else BASE_CV, content=content, kind="tailored" if job else "base", pages=pages))


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


@app.post("/api/ai/stories/bank")
def ai_story_bank(user: CurrentUser):
    """Write STAR stories for the strongest achievements that have none, until the user has eight."""
    with db.transaction() as conn:
        existing = repo.list_stories(conn, user.id)
        without = repo.achievements_without_story(conn, user.id)
        any_achievement = bool(without) or bool(repo.list_achievements(conn, user.id))
    if not any_achievement:
        raise HTTPException(400, "Build your profile first.")
    if len(existing) >= stories.BANK:
        raise HTTPException(400, f"You already have {stories.BANK} stories.")
    if not without:
        raise HTTPException(400, "Every achievement already has a story.")
    _start_ai(user, "story bank")
    covered = sorted({ai.COMPETENCIES[k] for s in existing for k in s["competencies"]})
    written, missed = stories.write(stories.pick(without, len(existing)), covered)
    with db.transaction() as conn:
        room = stories.BANK - len(repo.list_stories(conn, user.id))  # counted again: another request may have added some meanwhile
        saved = [repo.add_story(conn, user.id, achievement_id, story) for achievement_id, story in written[:max(0, room)]]
    return {"stories": saved, "notice": "Some stories could not be written. Try again to write the rest." if missed else None}


@app.post("/api/ai/stories/tag")
def ai_tag_stories(user: CurrentUser):
    """Competencies for the user's stories that have none. One AI action."""
    with db.transaction() as conn:
        existing = repo.list_stories(conn, user.id)
    if not existing:
        raise HTTPException(400, "You have no stories yet.")
    untagged = [s for s in existing if not s["competencies"]]
    if not untagged:
        raise HTTPException(400, "Every story already has competencies.")
    _start_ai(user, "tag stories")
    tags = ai.tag_stories(untagged)
    with db.transaction() as conn:
        repo.set_story_competencies(conn, user.id, {k: v for k, v in tags.items() if k in {s["id"] for s in untagged}})
        return {"stories": repo.list_stories(conn, user.id)}


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


# ---------- interview prep: company research and prep packs ----------
# Research reaches Companies House, the employer's website and the search service, so those routes
# need the research settings. A pack already made can always be read, edited and deleted.

PREP_OFF = "Interview prep is not set up on the server."
BAD_WEBSITE = "Enter the company's website, for example acme.co.uk."
BAD_TICKS = "Tick at most three of the questions shown."
CompanyNumber = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z0-9]{8}$")]


def _prep_on() -> None:
    if not research_configured():
        raise HTTPException(503, PREP_OFF)


class CompanyName(BaseModel):
    name: Text(160)


@app.post("/api/companies/search")
def search_companies(body: CompanyName, user: CurrentUser):
    """Up to five Companies House entries for a name, for the user to pick from. The name travels in the body."""
    _prep_on()
    try:
        return {"matches": companies_house.search(body.name)}
    except companies_house.CompaniesHouseError as e:
        raise HTTPException(502, e.message)


class ResearchIn(BaseModel):
    name: Text(160)
    company_number: CompanyNumber | None = None
    website: Text(300, 0) = ""
    not_uk: bool = False


def _company(row: dict, cached: bool) -> dict:
    return {"company_id": row["id"], "name": row["name"], "researched_at": row["researched_at"], "facts": row["facts"],
            "missing": row["missing"], "notice": None if row["facts"] else research.NOTHING_FOUND.format(name=row["name"]),
            "cached": cached}


def _research(user: User, *, name: str, number: str | None, website: str | None, again: bool = False) -> dict:
    """A company's brief: the shared one if it is fresh (and `again` is not set), otherwise researched
    now, which uses one of the day's research allowance."""
    key = research.lookup_key(name=name, number=number, website=website)
    with db.transaction() as conn:
        kept = None if again else repo.find_company(conn, key, research.FRESH_DAYS)
        if kept:
            return _company(kept, cached=True)
        limits.check_and_record(conn, user.id, "research", f"research {key}")  # every attempt costs searches, so every attempt counts
        today = repo.today(conn)
    gathered = research.gather(name=name, number=number, website=website, today=today)
    found = research.brief(name, gathered, today)
    with db.transaction() as conn:
        saved = repo.save_company(conn, key, name=name, company_number=number, website=website, registry=gathered["registry"],
                                  facts=found["facts"], missing=found["missing"])
    return _company(saved, cached=False)


@app.post("/api/companies/research")
def research_company(body: ResearchIn, user: CurrentUser):
    """Research a company the user confirmed, or reuse research of it from the last 14 days."""
    _prep_on()
    website = fetcher.website(body.website) if body.website else None
    if body.website and not website:
        raise HTTPException(422, BAD_WEBSITE)
    return _research(user, name=body.name, number=None if body.not_uk else body.company_number, website=website)


class PrepIn(BaseModel):
    job_id: UUID | None = None
    application_id: UUID | None = None
    company_id: UUID
    interview_type: Literal[prep.INTERVIEW_TYPES] | None = None

    @model_validator(mode="after")
    def _one_target(self):
        if (self.job_id is None) == (self.application_id is None):
            raise ValueError("Pick a job or an application.")
        return self


def _pack(row: dict) -> dict:
    """A pack as the page gets it: with what the mock interviewer is told from it."""
    return row | {"interviewer": prep.for_interviewer(row["content"])}


@app.post("/api/ai/prep")
def ai_prep(body: PrepIn, user: CurrentUser):
    """Build (or rebuild) the pack for a saved job, or for an application: the application's saved job
    when it has one. One AI action. A rebuild keeps the user's own pitch and right-to-work line."""
    _prep_on()
    with db.transaction() as conn:
        application = _found(repo.get_application(conn, user.id, str(body.application_id))) if body.application_id else None
        job_id = str(body.job_id) if body.job_id else application["saved_job_id"]
        job = repo.get_job(conn, user.id, job_id) if job_id else None
        if body.job_id:
            _found(job)
        company = _found(repo.get_company(conn, str(body.company_id)))
        achievements, told = repo.list_achievements(conn, user.id), repo.list_stories(conn, user.id)
        profile = repo.get_or_create_profile(conn, user.id, user.name)
        existing = repo.find_pack(conn, user.id, saved_job_id=job["id"] if job else None,
                                  application_id=None if job else application["id"])
    if not achievements:
        raise HTTPException(400, "Build your profile first.")
    _start_ai(user, "prep")
    role, employer = (job["title"], job["company"]) if job else (application["role"], application["company"])
    written = ai.prep_pack(job={"title": role, "company": employer, "description": job["description"] if job else ""},
                           brief=company["facts"], achievements=achievements, stories=told, profile=profile)
    brief = {"facts": company["facts"], "missing": company["missing"],
             "notice": None if company["facts"] else research.NOTHING_FOUND.format(name=company["name"])}
    made = prep.content(written=written, brief=brief, researched_at=company["researched_at"].isoformat(),
                        interview_type=body.interview_type or prep.default_type(application["stage"] if application else None),
                        right_to_work=prep.right_to_work(profile))
    if existing:
        made = prep.rebuild(existing["content"], made)
    with db.transaction() as conn:
        return _pack(repo.save_pack(conn, user.id, saved_job_id=job["id"] if job else None,
                                    application_id=application["id"] if application else None,
                                    company_id=company["id"], role=role, company=employer, content=made))


@app.get("/api/prep/{pack_id}")
def get_prep(pack_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        return _pack(_found(repo.get_pack(conn, user.id, str(pack_id))))


class PrepPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pitch: Text(2500, 0) = None
    right_to_work: Text(300, 0) = None
    ticked: list[int] = Field(None, max_length=prep.MAX_TICKS)
    interview_type: Literal[prep.INTERVIEW_TYPES] = None


@app.patch("/api/prep/{pack_id}")
def update_prep(pack_id: UUID, body: PrepPatch, user: CurrentUser):
    """Save the user's pitch, their right-to-work line, the questions they ticked, or the interview type."""
    with db.transaction() as conn:
        pack = _found(repo.get_pack(conn, user.id, str(pack_id)))
        try:
            changed = prep.edit(pack["content"], body.model_dump(exclude_unset=True))
        except ValueError:
            raise HTTPException(422, BAD_TICKS)
        return _pack(repo.update_pack_content(conn, user.id, pack["id"], changed))


@app.delete("/api/prep/{pack_id}", status_code=204)
def delete_prep(pack_id: UUID, user: CurrentUser):
    with db.transaction() as conn:
        _found(repo.delete_pack(conn, user.id, str(pack_id)))
    return Response(status_code=204)


@app.post("/api/prep/{pack_id}/refresh")
def refresh_prep(pack_id: UUID, user: CurrentUser):
    """Research the pack's company again now, whatever is kept. The page then rebuilds the pack."""
    _prep_on()
    with db.transaction() as conn:
        pack = _found(repo.get_pack(conn, user.id, str(pack_id)))
        company = _found(repo.get_company(conn, pack["company_id"]) if pack["company_id"] else None)
    return _research(user, name=company["name"], number=company["company_number"], website=company["website"], again=True)


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
