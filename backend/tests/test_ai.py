import inspect
from datetime import date

import httpx
import pytest

import ai
from llm import LLMNotConfigured

PROFILE = {"full_name": "Test Person", "course": "MSc Course A", "university": "University A",
           "visa_type": "student", "visa_end_date": date(2027, 1, 31)}
ACHIEVEMENTS = [{"id": "a1", "title": "Thing one", "uk_version": "Built X for 40 users", "skills": ["SQL"], "outcome": "40 users"}]
JOB = {"title": "Role A", "company": "Company A", "description": "Analyse data and report findings. " * 5, "keywords": ["SQL"]}
TAILORED = {"profile": "P", "bullets": [{"text": "Built X", "achievement_id": "a1"}], "keywords": ["SQL"],
            "cover_letter": {"why_them": "A", "why_you": "B", "what_you_deliver": "C"}, "gaps": []}
TONE = {"meaning": "m", "how_to_respond": "h", "warmth": "neutral"}


@pytest.fixture
def model(monkeypatch):
    """Script the model: each entry is a parsed reply, or an exception to raise. Returns the calls made."""
    def install(*script):
        replies, calls = list(script), []

        def fake(system, user, max_tokens=1500):
            calls.append({"system": system, "user": user})
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        monkeypatch.setattr(ai, "complete_json", fake)
        return calls
    return install


def family(**kw):
    return {"name": "Data Analyst", "fit": "direct", "overlap": 80, "uk_titles": ["Data Analyst"], "why": "w", "needs": []} | kw


# ---------- the retry rule ----------

def test_run_retries_once_on_malformed_json(model):
    calls = model(ValueError("bad json"), TONE)
    assert ai.tone("Not bad", "decode")["meaning"] == "m"
    assert len(calls) == 2


def test_run_retries_once_on_missing_required(model):
    calls = model({"bullets": []}, TAILORED)
    assert ai.tailor(JOB, ACHIEVEMENTS, PROFILE)["bullets"][0]["text"] == "Built X"
    assert len(calls) == 2


def test_run_retries_once_on_network_error(model):
    calls = model(httpx.ReadTimeout("slow"), TONE)
    assert ai.tone("Not bad", "decode")["meaning"] == "m"
    assert len(calls) == 2


def test_run_raises_ai_error_after_two_failures(model):
    calls = model(ValueError("bad"), ValueError("bad again"))
    with pytest.raises(ai.AIError):
        ai.tone("Not bad", "decode")
    assert len(calls) == 2


def test_not_configured_is_not_retried(model):
    calls = model(LLMNotConfigured("no model"))
    with pytest.raises(LLMNotConfigured):
        ai.tone("Not bad", "decode")
    assert len(calls) == 1


# ---------- achievements ----------

def test_extract_drops_items_without_text(model):
    model({"items": [{"title": "", "raw": "", "uk_version": ""}, {"title": "Kept", "raw": "r", "uk_version": "Did Y"}], "pitch": "I am"})
    out = ai.extract_achievements("a long enough transcript", PROFILE)
    assert [i["title"] for i in out["items"]] == ["Kept"]
    assert out["pitch"] == "I am"


def test_extract_fills_uk_version_from_raw(model):
    model({"items": [{"title": "", "raw": "x", "uk_version": ""}], "pitch": ""})
    item = ai.extract_achievements("a long enough transcript", PROFILE)["items"][0]
    assert item["uk_version"] == "x"
    assert item["title"] == "x"
    assert item["skills"] == [] and item["outcome"] == "" and item["context_note"] == ""


def test_extract_zero_usable_items_returns_empty(model):
    calls = model({"items": [{"title": "", "raw": "", "uk_version": ""}], "pitch": ""})
    assert ai.extract_achievements("hello hello hello hello", PROFILE) == {"items": [], "pitch": ""}
    assert len(calls) == 1


def test_extract_prompt_uses_the_profile(model):
    calls = model({"items": [], "pitch": ""})
    ai.extract_achievements("my transcript text", PROFILE)
    assert "Test Person" in calls[0]["user"]
    assert "MSc Course A" in calls[0]["user"] and "University A" in calls[0]["user"]
    assert "my transcript text" in calls[0]["user"]


# ---------- role families ----------

def test_families_normalised(model):
    model({"families": [
        family(name="A", fit="Direct Fit", overlap="85%"),
        family(name="B", fit="unknown", overlap=150),
        family(name="C", fit="STRETCH", overlap=-5),
    ]})
    out = ai.suggest_families(ACHIEVEMENTS, PROFILE)["families"]
    assert [(f["fit"], f["overlap"]) for f in out] == [("direct", 85), ("near", 100), ("stretch", 0)]


def test_families_deduplicated_case_insensitively(model):
    model({"families": [family(name="Data Analyst", why="first"), family(name="data analyst ", why="second"), family(name=" ")]})
    out = ai.suggest_families(ACHIEVEMENTS, PROFILE)["families"]
    assert [(f["name"], f["why"]) for f in out] == [("Data Analyst", "first")]


def test_families_needs_are_objects(model):
    model({"families": [family(needs=["SQL", {"need": "Dashboards", "shown_by": "Thing one"}, {"need": "", "shown_by": "x"}])]})
    needs = ai.suggest_families(ACHIEVEMENTS, PROFILE)["families"][0]["needs"]
    assert needs == [{"need": "SQL", "shown_by": ""}, {"need": "Dashboards", "shown_by": "Thing one"}]


@pytest.mark.parametrize("word", ["None", "gap", "N/A", "-", "null"])
def test_families_none_like_shown_by_is_a_gap(model, word):
    model({"families": [family(needs=[{"need": "SQL", "shown_by": word}])]})
    assert ai.suggest_families(ACHIEVEMENTS, PROFILE)["families"][0]["needs"] == [{"need": "SQL", "shown_by": ""}]


def test_families_prompt_has_no_salary_or_sponsorship(model):
    calls = model({"families": [family()]})
    out = ai.suggest_families(ACHIEVEMENTS, PROFILE)["families"][0]
    prompt = (calls[0]["system"] + calls[0]["user"]).lower()
    assert "salary" not in prompt and "sponsor" not in prompt
    assert "salary" not in out and "sponsorship" not in out


def test_families_required(model):
    model({"families": []}, {"families": []})
    with pytest.raises(ai.AIError):
        ai.suggest_families(ACHIEVEMENTS, PROFILE)


# ---------- jobs, CVs, stories ----------

def test_summarise_job_family_must_be_known(model):
    model({"summary": "s", "keywords": ["SQL"], "family": "Astronaut"})
    assert ai.summarise_job("Role A", "Company A", "desc", ["Data Analyst"])["family"] == ""


def test_summarise_job_family_uses_the_callers_spelling(model):
    model({"summary": "s", "keywords": ["SQL"], "family": " data analyst"})
    assert ai.summarise_job("Role A", "Company A", "desc", ["Data Analyst"])["family"] == "Data Analyst"


def test_tailor_requires_bullets_and_letter(model):
    no_letter = {k: v for k, v in TAILORED.items() if k != "cover_letter"}
    model(no_letter, no_letter)
    with pytest.raises(ai.AIError):
        ai.tailor(JOB, ACHIEVEMENTS, PROFILE)


def test_tailor_unknown_achievement_id_blanked(model):
    model(TAILORED | {"bullets": [{"text": "Built X", "achievement_id": "a1"}, {"text": "Did Z", "achievement_id": "zzz"}, {"text": " "}]})
    assert ai.tailor(JOB, ACHIEVEMENTS, PROFILE)["bullets"] == [
        {"text": "Built X", "achievement_id": "a1"}, {"text": "Did Z", "achievement_id": ""}]


def test_tailor_prompt_truncates_long_description(model):
    calls = model(TAILORED)
    ai.tailor(JOB | {"description": "x" * 10000}, ACHIEVEMENTS, PROFILE)
    assert "x" * 6000 in calls[0]["user"]
    assert "x" * 6001 not in calls[0]["user"]


@pytest.mark.parametrize("given,expected", [("strong", "strong"), (" Strong ", "strong"), ("needs a number", "needs a number"), ("excellent", "needs detail"), ("", "needs detail")])
def test_star_strength_normalised(model, given, expected):
    model({"title": "t", "competency": "c", "situation": "s", "task": "t", "action": "a", "result": "r", "strength": given, "tip": ""})
    assert ai.star(ACHIEVEMENTS[0])["strength"] == expected


# ---------- interviews, tone, diagnosis ----------

FEEDBACK = {"scores": {"structure": 3, "clarity": 3, "evidence": 3, "uk_tone": 3}, "summary": "s", "strengths": ["a"],
            "fixes": ["b"], "rewrite": {"question": "q", "better_answer": "a"}, "uk_tone_notes": []}


def test_interview_scores_clamped(model):
    model(FEEDBACK | {"scores": {"structure": 9, "clarity": "4/5", "evidence": -1, "uk_tone": "three"}})
    assert ai.interview_feedback("Interviewer: hi\nCandidate: hello", JOB, PROFILE, "HR screening call")["scores"] == {
        "structure": 5, "clarity": 4, "evidence": 0, "uk_tone": 0}


def test_interview_without_job_says_general_practice(model):
    calls = model(FEEDBACK)
    ai.interview_feedback("Interviewer: hi\nCandidate: hello", None, PROFILE, "Behavioural round")
    assert "Role: general practice, no specific job" in calls[0]["user"]


def test_interview_with_job_names_it(model):
    calls = model(FEEDBACK)
    ai.interview_feedback("Interviewer: hi\nCandidate: hello", JOB, PROFILE, "Job-specific interview")
    assert "Role: Role A at Company A" in calls[0]["user"]


def test_tone_rewrite_requires_a_rewrite(model):
    model({"changes": ["x"]}, {"changes": ["x"]})
    with pytest.raises(ai.AIError):
        ai.tone("I am the best", "rewrite")


def test_diagnosis_accepts_dates_in_stats(model):
    model({"headline": "h", "working": "w", "problem": "p", "one_change": "c", "signal": "s"})
    stats = {"funnel": {"applied": 1}, "by_family": [], "by_source": [], "timing": {"since": date(2026, 10, 1)}}
    assert ai.explain_diagnosis([], stats, PROFILE)["headline"] == "h"


# ---------- no demo content ----------

def test_no_demo_content_in_module():
    source = inspect.getsource(ai)
    for word in ("Aditi", "Infosys", "Exeter", "Lumen", "fallback"):
        assert word not in source, f"{word!r} is still in ai.py"


def test_removed_functions_are_gone():
    assert not hasattr(ai, "outreach") and not hasattr(ai, "peer_notes") and not hasattr(ai, "extract_evidence")
