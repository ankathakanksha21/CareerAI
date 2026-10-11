import pytest

import ai
import repo
import voice

pytestmark = pytest.mark.db

LIMIT = "You've reached today's limit. It resets at midnight."
ITEMS = [{"title": "Thing one", "raw": "r", "uk_version": "Built X for 40 users", "skills": ["SQL"], "outcome": "40 users", "scale": "", "context_note": ""},
         {"title": "Thing two", "raw": "r", "uk_version": "Automated Y", "skills": [], "outcome": "", "scale": "", "context_note": ""}]
TRANSCRIPT = "Coach: tell me about your work\nCandidate: I built X for 40 users and automated Y"
DESCRIPTION = "Analyse customer data and report findings to the team every week. " * 2
TAILORED = {"profile": "P", "bullets": [{"text": "Built X", "achievement_id": ""}], "keywords": ["SQL"],
            "cover_letter": {"why_them": "A", "why_you": "B", "what_you_deliver": "C"}, "gaps": []}
FEEDBACK = {"scores": {"structure": 3, "clarity": 4, "evidence": 2, "uk_tone": 3}, "summary": "Clear but late results.",
            "strengths": ["s1"], "fixes": ["f1"], "rewrite": {"question": "q", "better_answer": "a"}, "uk_tone_notes": []}
STORY = {"title": "Story", "competency": "c", "situation": "s", "task": "t", "action": "a", "result": "r", "strength": "strong", "tip": ""}


@pytest.fixture
def stub(monkeypatch):
    """Replace one ai.<name> with a function returning `result` (or raising it). Returns the calls made."""
    def install(name, result):
        calls = []

        def fake(*args, **kwargs):
            calls.append(args)
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(ai, name, fake)
        return calls
    return install


def state(client):
    return client.get("/api/state").json()


def seed_achievement(conn, user):
    return repo.add_achievements(conn, user, [ITEMS[0]], "paste")[0]


def seed_job(conn, user, **kw):
    fields = dict(title="Role A", company="Company A", location=None, url=None, description=DESCRIPTION, summary="s",
                  keywords=["SQL"], role_family_id=None) | kw
    return repo.add_job(conn, user, **fields)


# ---------- achievements ----------

def test_achievements_saved_and_journalled(client, stub):
    stub("extract_achievements", {"items": ITEMS, "pitch": "I am a pitch."})
    r = client.post("/api/ai/achievements", json={"transcript": TRANSCRIPT, "source": "paste"})
    assert r.status_code == 200
    assert [i["title"] for i in r.json()["items"]] == ["Thing one", "Thing two"] and r.json()["pitch"] == "I am a pitch."
    s = state(client)
    assert len(s["achievements"]) == 2 and all(a["source"] == "paste" for a in s["achievements"])
    assert s["profile"]["pitch"] == "I am a pitch."
    assert [(j["type"], j["title"]) for j in s["journal"]] == [("coach", "Profile built from your pasted background")]
    assert s["usage"]["ai"]["used"] == 1


def test_voice_source_journal_title(client, stub):
    stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    client.post("/api/ai/achievements", json={"transcript": TRANSCRIPT, "source": "voice"})
    s = state(client)
    assert s["journal"][0]["title"] == "Background call with your careers coach"
    assert s["profile"]["pitch"] is None  # an empty pitch does not overwrite


def test_achievements_none_found_422(client, stub):
    stub("extract_achievements", {"items": [], "pitch": ""})
    r = client.post("/api/ai/achievements", json={"transcript": TRANSCRIPT, "source": "paste"})
    assert r.status_code == 422
    assert r.json()["detail"] == "We could not find any achievements in that. Add more detail and try again."
    s = state(client)
    assert s["achievements"] == [] and s["journal"] == []


def test_achievements_short_transcript_422(client, stub):
    calls = stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    r = client.post("/api/ai/achievements", json={"transcript": "x" * 19, "source": "paste"})
    assert r.status_code == 422 and r.json()["detail"] == "Say or paste a bit more first."
    assert calls == [] and state(client)["usage"]["ai"]["used"] == 0


def test_achievements_oversize_422(client, stub):
    calls = stub("extract_achievements", {"items": ITEMS, "pitch": ""})
    assert client.post("/api/ai/achievements", json={"transcript": "x" * 30001, "source": "paste"}).status_code == 422
    assert calls == []


def test_ai_error_saves_nothing_and_is_502(client, stub):
    stub("extract_achievements", ai.AIError("achievements"))
    r = client.post("/api/ai/achievements", json={"transcript": TRANSCRIPT, "source": "paste"})
    assert r.status_code == 502 and r.json()["detail"] == "The AI did not respond properly. Try again."
    s = state(client)
    assert s["achievements"] == [] and s["journal"] == []


def test_ai_limit_429(client, stub, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "1")
    calls = stub("tone", {"meaning": "m", "how_to_respond": "h", "warmth": "neutral"})
    assert client.post("/api/ai/tone", json={"text": "Not bad", "mode": "decode"}).status_code == 200
    r = client.post("/api/ai/tone", json={"text": "Not bad", "mode": "decode"})
    assert r.status_code == 429 and r.json()["detail"] == LIMIT
    assert len(calls) == 1


def test_no_connection_held_during_ai(client, monkeypatch):
    import db
    inner = db.transaction
    open_now = []

    from contextlib import contextmanager

    @contextmanager
    def tracking():
        with inner() as c:
            open_now.append(1)
            try:
                yield c
            finally:
                open_now.pop()
    monkeypatch.setattr(db, "transaction", tracking)

    def fake_tone(text, mode):
        assert open_now == [], "a database transaction was open during the model call"
        return {"meaning": "m", "how_to_respond": "h", "warmth": "neutral"}
    monkeypatch.setattr(ai, "tone", fake_tone)
    assert client.post("/api/ai/tone", json={"text": "Not bad", "mode": "decode"}).status_code == 200


# ---------- role families ----------

def test_families_need_achievements(client, stub):
    calls = stub("suggest_families", {"families": []})
    r = client.post("/api/ai/families")
    assert r.status_code == 400 and r.json()["detail"] == "Build your profile first."
    assert calls == []


def test_families_synced(client, stub, conn, user_a):
    seed_achievement(conn, user_a)
    stub("suggest_families", {"families": [
        {"name": n, "fit": f, "overlap": o, "uk_titles": [n], "why": "w", "needs": [{"need": "SQL", "shown_by": "Thing one"}]}
        for n, f, o in (("Data Analyst", "direct", 85), ("BI Analyst", "near", 70), ("Data Scientist", "stretch", 50))]})
    r = client.post("/api/ai/families")
    assert [f["name"] for f in r.json()["families"]] == ["Data Analyst", "BI Analyst", "Data Scientist"]
    assert len(state(client)["role_families"]) == 3


# ---------- jobs ----------

JOB = {"title": "Role A", "company": "Company A", "description": DESCRIPTION}


def test_add_job_summarised_and_matched(client, stub, conn, user_a):
    fam = repo.sync_families(conn, user_a, [{"name": "Data Analyst", "fit": "direct", "overlap": 80}])[0]
    calls = stub("summarise_job", {"summary": "A short summary", "keywords": ["SQL"], "family": "Data Analyst"})
    r = client.post("/api/jobs", json=JOB | {"url": "https://example.test/j", "location": "London"})
    assert r.status_code == 201
    j = r.json()
    assert j["summary"] == "A short summary" and j["role_family_id"] == fam["id"] and j["keywords"] == ["SQL"]
    assert calls[0][3] == ["Data Analyst"]
    assert state(client)["usage"]["ai"]["used"] == 1


def test_add_job_survives_ai_failure(client, stub):
    stub("summarise_job", ai.AIError("job"))
    r = client.post("/api/jobs", json=JOB | {"description": "y" * 500})
    assert r.status_code == 201
    assert r.json()["summary"] == "y" * 300 and r.json()["role_family_id"] is None
    assert len(state(client)["saved_jobs"]) == 1


def test_add_job_skips_ai_when_limit_reached(client, stub, monkeypatch):
    monkeypatch.setenv("DAILY_AI_LIMIT", "0")
    calls = stub("summarise_job", {"summary": "s", "keywords": [], "family": ""})
    assert client.post("/api/jobs", json=JOB).status_code == 201
    assert calls == []


def test_add_job_short_description_422(client, stub):
    stub("summarise_job", {"summary": "s", "keywords": [], "family": ""})
    r = client.post("/api/jobs", json=JOB | {"description": "too short"})
    assert r.status_code == 422 and r.json()["detail"] == "Paste the full job description."
    assert client.post("/api/jobs", json=JOB | {"description": "z" * 20001}).status_code == 422


# ---------- tailoring and stories ----------

def test_tailor_creates_named_version(client, stub, conn, user_a):
    a, j = seed_achievement(conn, user_a), seed_job(conn, user_a)
    stub("tailor", TAILORED | {"bullets": [{"text": "Built X", "achievement_id": a["id"]}]})
    first = client.post("/api/ai/tailor", json={"job_id": j["id"]}).json()
    assert first["name"] == "Role A, Company A v1" and first["saved_job_id"] == j["id"]
    assert first["content"]["cover_letter"]["why_them"] == "A"
    assert client.post("/api/ai/tailor", json={"job_id": j["id"]}).json()["name"] == "Role A, Company A v2"
    assert len(state(client)["cv_versions"]) == 2


def test_tailor_needs_achievements(client, stub, conn, user_a):
    stub("tailor", TAILORED)
    r = client.post("/api/ai/tailor", json={"job_id": seed_job(conn, user_a)["id"]})
    assert r.status_code == 400 and r.json()["detail"] == "Build your profile first."


def test_tailor_other_users_job_404(client, stub, conn, user_a, user_b, as_user):
    j = seed_job(conn, user_a)
    seed_achievement(conn, user_b)
    calls = stub("tailor", TAILORED)
    as_user(user_b)
    assert client.post("/api/ai/tailor", json={"job_id": j["id"]}).status_code == 404
    assert calls == []


def test_star_saves_story(client, stub, conn, user_a):
    a = seed_achievement(conn, user_a)
    stub("star", STORY)
    s = client.post("/api/ai/star", json={"achievement_id": a["id"]}).json()
    assert s["achievement_id"] == a["id"] and s["strength"] == "strong"
    assert len(state(client)["stories"]) == 1


def test_star_other_users_achievement_404(client, stub, conn, user_a, user_b, as_user):
    a = seed_achievement(conn, user_a)
    calls = stub("star", STORY)
    as_user(user_b)
    assert client.post("/api/ai/star", json={"achievement_id": a["id"]}).status_code == 404
    assert calls == []


# ---------- interviews and diagnosis ----------

def test_interview_feedback_without_job(client, stub):
    calls = stub("interview_feedback", FEEDBACK)
    r = client.post("/api/ai/interview-feedback", json={"transcript": TRANSCRIPT, "interview_type": "HR screening call"})
    assert r.status_code == 200 and r.json()["scores"]["clarity"] == 4
    assert calls[0][1] is None
    entry = state(client)["journal"][0]
    assert entry["title"] == "HR screening call: general practice" and entry["type"] == "interview"


def test_interview_feedback_journal_has_scores(client, stub, conn, user_a):
    j = seed_job(conn, user_a)
    stub("interview_feedback", FEEDBACK)
    client.post("/api/ai/interview-feedback", json={"transcript": TRANSCRIPT, "job_id": j["id"], "interview_type": "Behavioural round"})
    s = state(client)
    entry = s["journal"][0]
    assert entry["title"] == "Behavioural round: Role A, Company A"
    assert entry["scores"] == FEEDBACK["scores"] and entry["points"] == ["s1"] and entry["actions"] == ["f1"]
    assert s["next_steps"][4]["done"] is True


def test_interview_feedback_unknown_job_404(client, stub):
    stub("interview_feedback", FEEDBACK)
    r = client.post("/api/ai/interview-feedback", json={"transcript": TRANSCRIPT, "job_id": "11111111-1111-1111-1111-111111111111",
                                                        "interview_type": "Behavioural round"})
    assert r.status_code == 404


def test_diagnosis_needs_applications(client, stub):
    calls = stub("explain_diagnosis", {"headline": "h"})
    r = client.post("/api/ai/diagnosis")
    assert r.status_code == 400 and r.json()["detail"] == "Log some applications first."
    assert calls == []


def test_diagnosis_with_applications(client, stub):
    client.post("/api/applications", json={"company": "Company A", "role": "Role A", "source": "Company site"})
    stub("explain_diagnosis", {"headline": "h", "working": "w", "problem": "p", "one_change": "c", "signal": "s"})
    assert client.post("/api/ai/diagnosis").json()["headline"] == "h"


# ---------- voice ----------

@pytest.fixture
def voice_ready(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_ONBOARDING_AGENT_ID", "agent_a")
    monkeypatch.setenv("ELEVENLABS_INTERVIEWER_AGENT_ID", "agent_b")
    monkeypatch.setattr(voice, "conversation_token", lambda agent: "t")
    monkeypatch.setattr(voice, "signed_url", lambda agent: "wss://example.test/s")


def test_voice_token_counts_and_limits(client, voice_ready, monkeypatch):
    monkeypatch.setenv("DAILY_VOICE_LIMIT", "1")
    assert client.get("/api/voice/token?agent=onboarding").json() == {"token": "t"}
    r = client.get("/api/voice/token?agent=interviewer")
    assert r.status_code == 429 and r.json()["detail"] == LIMIT
    assert state(client)["usage"]["voice"]["used"] == 1


def test_voice_websocket_retry_is_free(client, voice_ready, monkeypatch):
    monkeypatch.setenv("DAILY_VOICE_LIMIT", "1")
    assert client.get("/api/voice/token?agent=onboarding").status_code == 200
    assert client.get("/api/voice/token?agent=onboarding&transport=websocket").json() == {"signed_url": "wss://example.test/s"}
    assert state(client)["usage"]["voice"]["used"] == 1


def test_voice_unconfigured_503(client, monkeypatch, no_env_file):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    r = client.get("/api/voice/token?agent=onboarding")
    assert r.status_code == 503 and r.json()["detail"] == "Voice is unavailable right now."
    assert state(client)["usage"]["voice"]["used"] == 0


def test_voice_token_failure_is_502_and_not_counted(client, voice_ready, monkeypatch):
    def boom(agent):
        raise RuntimeError("elevenlabs down")
    monkeypatch.setattr(voice, "conversation_token", boom)
    r = client.get("/api/voice/token?agent=onboarding")
    assert r.status_code == 502 and r.json()["detail"] == "Voice is unavailable right now."
    assert state(client)["usage"]["voice"]["used"] == 0


def test_voice_bad_agent_422(client, voice_ready):
    assert client.get("/api/voice/token?agent=robot").status_code == 422
    assert client.get("/api/voice/token?agent=onboarding&transport=smoke").status_code == 422


def test_transcript_owner_only(client, voice_ready, monkeypatch, user_a):
    seen = []

    def refuse(conversation_id, user_id):
        seen.append(user_id)
        raise PermissionError("not yours")
    monkeypatch.setattr(voice, "fetch_transcript", refuse)
    assert client.get("/api/voice/transcript/conv_1").status_code == 404
    assert seen == [user_a]
    monkeypatch.setattr(voice, "fetch_transcript", lambda c, u: [{"role": "agent", "message": "Hi"}])
    assert client.get("/api/voice/transcript/conv_1").json() == {"turns": [{"role": "agent", "message": "Hi"}]}
