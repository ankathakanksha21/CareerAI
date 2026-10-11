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
