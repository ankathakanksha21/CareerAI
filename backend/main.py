"""UK Career Navigator API. Routes only: check who is calling, validate the input, call the
modules, return JSON. Every route except /api/config needs a signed-in user and touches
only that user's rows."""
import logging
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints, model_validator

import ai
import analytics
import content
import db
import limits
import repo
import voice
from auth import User, current_user
from config import env, llm_configured, supabase_url, voice_configured
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


# ---------- config and state ----------

@app.get("/api/config")
def get_config():
    """What the browser needs before anyone is signed in. Nothing here is secret."""
    return {"supabase_url": supabase_url(), "supabase_publishable_key": env("SUPABASE_PUBLISHABLE_KEY"),
            "contact_email": env("CONTACT_EMAIL")}


@app.get("/api/state")
def get_state(user: CurrentUser):
    with db.transaction() as conn:
        profile = repo.get_or_create_profile(conn, user.id, user.name)
        state = repo.load_state(conn, user.id)
        usage = limits.usage(conn, user.id)
    return state | {
        "profile": profile | {"email": user.email},
        "details_complete": repo.details_complete(profile),
        "stats": analytics.compute(state["applications"], state["role_families"], state["cv_versions"], state["stories"]),
        "next_steps": analytics.next_steps(state),
        "content": content.load(),
        "usage": usage,
        "options": {"sources": analytics.SOURCES, "stages": analytics.STAGES},
        "config": {"llm": llm_configured(),
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
            points=[i["title"] for i in items], actions=["Review your profile and add any missing numbers"])
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
                               summary=feedback["summary"], points=feedback["strengths"], actions=feedback["fixes"], scores=feedback["scores"])
    return feedback


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
