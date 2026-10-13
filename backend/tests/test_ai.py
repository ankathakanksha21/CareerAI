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

FEEDBACK = {"scores": {"structure": 3, "clarity": 3, "evidence": 3, "uk_tone": 3}, "summary": "s",
            "strengths": [{"point": "a", "you_said": ""}], "fixes": [{"point": "b", "you_said": ""}], "rewrite": {"question": "q", "better_answer": "a"}, "uk_tone_notes": []}


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


# ---------- "You said": quotes are only ever the candidate's own words ----------

CALL = ("Coach: What did you do before your course?\n"
        "Candidate: I worked at a logistics firm for two years. I built a weekly delays report that fifteen managers used.\n"
        "Coach: What was the result?\n"
        "Candidate: Late deliveries fell by about eight percent, and I saved five hours a week with a Python script.")


def test_verbatim_keeps_an_exact_quote():
    assert ai.verbatim("I built a weekly delays report", CALL) == "I built a weekly delays report"


def test_verbatim_ignores_case_and_punctuation():
    assert ai.verbatim("late deliveries fell by about eight percent!", CALL) == "late deliveries fell by about eight percent!"


def test_verbatim_replaces_a_paraphrase_with_what_was_said():
    assert ai.verbatim("built a delays report used by fifteen managers", CALL) == "I built a weekly delays report that fifteen managers used."


def test_verbatim_blank_when_nothing_like_it_was_said():
    assert ai.verbatim("I led a team of twenty engineers in Singapore", CALL) == ""
    assert ai.verbatim("", CALL) == ""


def test_verbatim_never_quotes_the_coach():
    assert ai.verbatim("What did you do before your course?", CALL) == ""


def test_verbatim_never_quotes_the_coach_when_the_candidate_said_nothing():
    only_coach = ("Coach: Hi there, what work or projects have you done so far?\n"
                  "Coach: Could you tell me about the delays report you built?")
    assert ai.verbatim("the delays report you built", only_coach) == ""


def test_verbatim_never_quotes_the_interviewer():
    call = "Interviewer: Tell me about a time you worked under pressure in a team.\nCandidate: Yes, of course."
    assert ai.verbatim("worked under pressure in a team", call) == ""


def test_verbatim_keeps_a_candidates_second_line():
    call = "Coach: Tell me more.\nCandidate: I built a report.\nIt saved the team five hours a week.\nCoach: Great."
    assert ai.verbatim("It saved the team five hours a week", call) == "It saved the team five hours a week"
    assert ai.verbatim("Great", call) == ""


def test_verbatim_does_not_match_inside_other_words():
    # "he said" must not be found inside "the said"
    assert ai.verbatim("he said", "Candidate: the said report was late.") == ""


def test_verbatim_uses_the_whole_text_when_there_are_no_speaker_labels():
    pasted = "Two years as a junior analyst. Built a delays report in SQL for fifteen managers."
    assert ai.verbatim("built a delays report in SQL", pasted) == "built a delays report in SQL"


def test_extract_raw_is_what_the_candidate_said(model):
    model({"items": [
        {"title": "Report", "raw": "I built a weekly delays report", "uk_version": "Built a weekly delays report used by 15 managers."},
        {"title": "Paraphrased", "raw": "saved five hours weekly using a Python script", "uk_version": "Automated a task in Python, saving 5 hours a week."},
        {"title": "Invented", "raw": "I managed a budget of two million pounds", "uk_version": "Did something."},
    ], "pitch": ""})
    raws = [i["raw"] for i in ai.extract_achievements(CALL, PROFILE)["items"]]
    assert raws[0] == "I built a weekly delays report"
    assert raws[1] == "Late deliveries fell by about eight percent, and I saved five hours a week with a Python script."
    assert raws[2] == ""


INTERVIEW_CALL = ("Interviewer: Tell me about a time you improved a process.\n"
                  "Candidate: We had a report that took a long time, so I wrote a Python script and it saved five hours a week.")


def test_interview_points_carry_checked_quotes(model):
    model(FEEDBACK | {
        "strengths": [{"point": "Gives a number.", "you_said": "it saved five hours a week"}, "A bare string strength"],
        "fixes": [{"point": "Say what you did.", "you_said": "I single-handedly rebuilt the platform"}, {"point": " ", "you_said": "x"}],
    })
    out = ai.interview_feedback(INTERVIEW_CALL, JOB, PROFILE, "Behavioural round")
    assert out["strengths"] == [{"point": "Gives a number.", "you_said": "it saved five hours a week"},
                                {"point": "A bare string strength", "you_said": ""}]
    assert out["fixes"] == [{"point": "Say what you did.", "you_said": ""}]


def test_interview_requires_at_least_one_fix(model):
    model(FEEDBACK | {"fixes": []}, FEEDBACK | {"fixes": [{"point": "", "you_said": ""}]})
    with pytest.raises(ai.AIError):
        ai.interview_feedback(INTERVIEW_CALL, JOB, PROFILE, "Behavioural round")


# ---------- job adverts against the candidate's achievements ----------

BATCH = [{"n": 1, "title": "Role A", "employer": "Company A", "description": "Needs SQL."},
         {"n": 2, "title": "Role B", "employer": "Company B", "description": "Needs Python."}]


def scored(n, *requirements):
    return {"n": n, "requirements": [{"need": need, "shown_by": by} for need, by in requirements]}


def test_score_jobs_returns_requirements_per_advert(model):
    model({"jobs": [scored(1, ("SQL", "Thing one")), scored(2, ("Python", ""))]})
    assert ai.score_jobs(BATCH, ACHIEVEMENTS) == {1: [{"need": "SQL", "shown_by": "Thing one"}], 2: [{"need": "Python", "shown_by": ""}]}


def test_score_jobs_keeps_only_adverts_that_were_sent(model):
    model({"jobs": [scored(7, ("SQL", "Thing one")), scored(2, ("Python", ""))]})
    assert list(ai.score_jobs(BATCH, ACHIEVEMENTS)) == [2]


def test_score_jobs_first_entry_for_an_advert_wins(model):
    model({"jobs": [scored(1, ("SQL", "Thing one")), scored(1, ("Something else", ""))]})
    assert ai.score_jobs(BATCH, ACHIEVEMENTS) == {1: [{"need": "SQL", "shown_by": "Thing one"}]}


def test_score_jobs_reads_the_advert_number_from_text(model):
    model({"jobs": [{"n": "2", "requirements": ["Python"]}, {"n": "Advert 1", "requirements": [{"need": "SQL", "shown_by": "Thing one"}]}]})
    assert ai.score_jobs(BATCH, ACHIEVEMENTS) == {2: [{"need": "Python", "shown_by": ""}], 1: [{"need": "SQL", "shown_by": "Thing one"}]}


def test_score_jobs_drops_blank_needs_and_keeps_six_at_most(model):
    model({"jobs": [scored(1, ("  ", "Thing one"), *[(f"need {i}", "") for i in range(9)])]})
    assert [r["need"] for r in ai.score_jobs(BATCH, ACHIEVEMENTS)[1]] == [f"need {i}" for i in range(6)]


@pytest.mark.parametrize("word", ["None", "gap", "N/A", "-", "null"])
def test_score_jobs_none_like_shown_by_is_a_gap(model, word):
    model({"jobs": [scored(1, ("SQL", word))]})
    assert ai.score_jobs(BATCH, ACHIEVEMENTS)[1] == [{"need": "SQL", "shown_by": ""}]


def test_score_jobs_keeps_an_advert_with_no_requirements_as_empty(model):
    model({"jobs": [scored(1), scored(2, ("Python", ""))]})
    assert ai.score_jobs(BATCH, ACHIEVEMENTS)[1] == []  # too little in the advert to judge: no score, and not asked again


def test_score_jobs_raises_when_no_advert_comes_back(model):
    calls = model({"jobs": []}, {"jobs": [scored(9, ("SQL", ""))]})
    with pytest.raises(ai.AIError):
        ai.score_jobs(BATCH, ACHIEVEMENTS)
    assert len(calls) == 2  # an empty reply is retried once; a reply about other adverts is not usable


def test_score_jobs_prompt_cuts_long_adverts_and_names_the_achievements(model):
    calls = model({"jobs": [scored(1, ("SQL", ""))]})
    ai.score_jobs([BATCH[0] | {"description": "x" * 5000 + " TAILMARK"}], ACHIEVEMENTS)
    assert "TAILMARK" not in calls[0]["user"] and "Thing one" in calls[0]["user"]


def test_score_jobs_sends_nothing_about_the_person_but_their_achievements(model):
    calls = model({"jobs": [scored(1, ("SQL", ""))]})
    ai.score_jobs(BATCH, ACHIEVEMENTS)
    prompt = calls[0]["system"] + calls[0]["user"]
    assert "Test Person" not in prompt and "visa" not in prompt.lower() and "University A" not in prompt


# ---------- step 1: months, missing numbers, quotes from text that is not speech ----------

CV = """Zarvin Quillfeather
Systems Engineer, Zzqx Holdings Ltd, Pune, India
Jul 2023 - Aug 2025
Built a weekly delivery delays report in
SQL and Excel used by 15 depot
managers; late deliveries fell by about
8%.
Wrote a Python script that merged three spreadsheets.
Coach: Under-15 football team, weekends
BTech Computer Science, University of Zzqx, India, 2019 - 2023, CGPA 8.4/10
Skills: Python, SQL, Excel, Power BI
Languages: English (fluent), Hindi (native)"""


@pytest.mark.parametrize("given, expected", [
    ("2023-07", date(2023, 7, 1)), (" 2025-12 ", date(2025, 12, 1)), ("2023-7", None), ("2021", None), ("Summer 2022", None),
    ("present", None), ("", None), (None, None), ("2023-13", None), ("2023-00", None), ("07/2023", None), ("1023-07", None), (202307, None)])
def test_month_is_a_real_month_or_nothing(given, expected):
    assert ai.month(given) == expected


@pytest.mark.parametrize("achievement, expected", [
    ({"uk_version": "Built a report for depot managers", "outcome": "Add a number: how many managers used it"}, True),
    ({"uk_version": "Built a report for depot managers", "outcome": "Managers used it weekly"}, True),
    ({"uk_version": "Built a report for 15 depot managers", "outcome": ""}, False),
    ({"uk_version": "Built a report for depot managers", "outcome": "About 8% fewer late deliveries"}, False),
    ({"uk_version": "Built a report for 15 depot managers", "outcome": "add a number: the fall in late deliveries"}, True),
])
def test_needs_number(achievement, expected):
    assert ai.needs_number(achievement) is expected


def test_a_cv_line_that_looks_like_a_speaker_label_does_not_hide_the_rest():
    quote = "Wrote a Python script that merged three spreadsheets"
    assert ai.verbatim(quote, CV) == ""                    # read as a call transcript, only "Candidate:" lines count
    assert ai.verbatim(quote, CV, speech=False) == quote   # read as a document, every line is the user's


def test_a_quote_wrapped_across_lines_is_still_found_exactly():
    quote = "Built a weekly delivery delays report in SQL and Excel used by 15 depot managers"
    assert ai.verbatim(quote, CV, speech=False) == quote


def test_a_paraphrase_of_a_wrapped_sentence_comes_back_as_the_whole_sentence():
    assert ai.verbatim("built weekly delays report for fifteen depot managers using SQL", CV, speech=False) == \
        "Built a weekly delivery delays report in SQL and Excel used by 15 depot managers; late deliveries fell by about 8%."


def test_nothing_like_it_in_the_document():
    assert ai.verbatim("Led a team of forty engineers across three continents", CV, speech=False) == ""


# ---------- step 1: extraction knows the source, what is saved already, and where things happened ----------

def item(**kw):
    return {"title": "Delays report", "raw": "Built a weekly delivery delays report", "uk_version": "Built a weekly delays report for 15 managers",
            "skills": ["SQL"], "outcome": "8% fewer late deliveries", "scale": "15 managers", "context_note": "", "where": "Zzqx Holdings Ltd"} | kw


def test_extract_says_where_each_achievement_happened(model):
    model({"items": [item(where="  Zzqx Holdings Ltd "), item(title="Script", uk_version="Wrote a script", where="")], "pitch": "I am."})
    items = ai.extract_achievements(CV, PROFILE, "cv")["items"]
    assert [i["where"] for i in items] == ["Zzqx Holdings Ltd", ""]


@pytest.mark.parametrize("source, label, count", [("voice", "Background transcript:", "3 to 6 items"), ("paste", "Pasted text:", "Up to 8 items"),
                                                  ("cv", "CV text:", "Up to 8 items")])
def test_extract_prompt_fits_the_source(model, source, label, count):
    calls = model({"items": [item()], "pitch": ""})
    ai.extract_achievements(CV, PROFILE, source)
    assert label in calls[0]["user"] and count in calls[0]["user"]
    assert ("out of order" in calls[0]["system"]) is (source == "cv")


def test_extract_is_told_what_is_already_saved_and_drops_a_repeat(model):
    saved = [{"title": "Delays report", "uk_version": "Built a weekly delays report for 15 managers."}]
    calls = model({"items": [item(uk_version="built a weekly delays report, for 15 managers"), item(title="Script", uk_version="Wrote a merge script")], "pitch": ""})
    items = ai.extract_achievements(CV, PROFILE, "cv", saved)["items"]
    assert "Built a weekly delays report for 15 managers." in calls[0]["user"] and "Do not return those again" in calls[0]["system"]
    assert [i["title"] for i in items] == ["Script"]


def test_extract_without_saved_achievements_does_not_mention_them(model):
    calls = model({"items": [item()], "pitch": ""})
    ai.extract_achievements(CV, PROFILE, "cv")
    assert "Already in the profile" not in calls[0]["user"] and "Do not return those again" not in calls[0]["system"]


def test_extract_drops_the_same_achievement_returned_twice(model):
    model({"items": [item(), item(title="The same again")], "pitch": ""})
    assert len(ai.extract_achievements(CV, PROFILE, "cv")["items"]) == 1


def test_extract_keeps_no_more_than_the_source_allows(model):
    many = [item(title=f"T{n}", uk_version=f"Did thing number {n}") for n in range(12)]
    model({"items": many, "pitch": ""}, {"items": many, "pitch": ""})
    assert len(ai.extract_achievements(CV, PROFILE, "cv")["items"]) == 8
    assert len(ai.extract_achievements(CV, PROFILE, "voice")["items"]) == 6


def test_a_cv_quote_is_checked_against_the_cv_as_a_document(model):
    model({"items": [item(raw="Wrote a Python script that merged three spreadsheets"),
                     item(title="Invented", uk_version="Led forty engineers", raw="Led a team of forty engineers across three continents")], "pitch": ""})
    items = ai.extract_achievements(CV, PROFILE, "cv")["items"]
    assert items[0]["raw"] == "Wrote a Python script that merged three spreadsheets"
    assert items[1]["raw"] == ""


# ---------- step 1: CV facts ----------

def job(**kw):
    return {"employer": "Zzqx Holdings Ltd", "job_title": "Systems Engineer", "location": "Pune", "country": "India",
            "start": "2023-07", "end": "2025-08", "employer_context": "IT services"} | kw


def course(**kw):
    return {"institution": "University of Zzqx", "qualification": "BTech", "subject": "Computer Science",
            "start": "2019", "end": "2023", "grade": "CGPA 8.4/10", "country": "India"} | kw


def facts(model, **reply):
    model({"work_history": [], "education": [], "skills": [], "languages": []} | reply)
    return ai.extract_facts(CV, PROFILE, "cv")


def test_facts_come_back_in_the_shape_of_the_tables(model):
    found = facts(model, work_history=[job()], education=[course()], skills=["Python", " SQL "],
                  languages=[{"language": "English", "level": "fluent"}, {"language": "Hindi", "level": "Native speaker"}])
    assert found["work_history"] == [{"employer": "Zzqx Holdings Ltd", "job_title": "Systems Engineer", "location": "Pune", "country": "India",
                                      "start_month": date(2023, 7, 1), "end_month": date(2025, 8, 1), "is_current": False, "employer_context": "IT services"}]
    assert found["education"] == [{"institution": "University of Zzqx", "qualification": "BTech", "subject": "Computer Science",
                                   "start_month": None, "end_month": None, "grade": "CGPA 8.4/10", "country": "India"}]
    assert found["skills"] == ["Python", "SQL"]
    assert found["languages"] == [{"language": "English", "level": "Fluent"}, {"language": "Hindi", "level": "Native"}]


@pytest.mark.parametrize("word", ["present", "Present", "current", "now", "ongoing", "to date"])
def test_a_job_still_held_is_current_with_no_end(model, word):
    found = facts(model, work_history=[job(end=word)])["work_history"][0]
    assert found["is_current"] is True and found["end_month"] is None


@pytest.mark.parametrize("start, end", [("2021", "Summer 2022"), ("", "2023"), ("present", "")])
def test_a_date_that_is_not_a_month_is_left_empty_never_guessed(model, start, end):
    found = facts(model, work_history=[job(start=start, end=end)])["work_history"][0]
    assert found["start_month"] is None and found["end_month"] is None and found["is_current"] is False


def test_an_end_before_the_start_is_dropped(model):
    found = facts(model, work_history=[job(start="2025-08", end="2023-07")], education=[course(start="2023-05", end="2019-07")])
    assert found["work_history"][0]["start_month"] == date(2025, 8, 1) and found["work_history"][0]["end_month"] is None
    assert found["education"][0]["end_month"] is None


def test_an_employer_or_institution_that_is_not_in_the_text_is_dropped(model):
    found = facts(model, work_history=[job(employer="Tata Consultancy Services"), job(employer="Zzqx Holdings Limited"), job(employer="")],
                  education=[course(institution="Indian Institute of Technology Bombay"), course(institution="Zzqx University")])
    assert [w["employer"] for w in found["work_history"]] == ["Zzqx Holdings Limited"]   # half its words are in the text
    assert [e["institution"] for e in found["education"]] == ["Zzqx University"]


def test_the_same_job_or_course_twice_is_kept_once(model):
    found = facts(model, work_history=[job(), job(employer="zzqx holdings ltd."), job(job_title="Intern", start="2022-01", end="2022-06")],
                  education=[course(), course(grade="")])
    assert [w["job_title"] for w in found["work_history"]] == ["Systems Engineer", "Intern"]
    assert len(found["education"]) == 1


def test_skills_and_languages_are_only_those_the_text_names(model):
    found = facts(model, skills=["Python", "python", "Kubernetes", "Power BI", "", "x" * 80],
                  languages=[{"language": "Hindi", "level": "mother tongue"}, {"language": "French", "level": "Basic"},
                             {"language": "English", "level": "C1"}, {"language": "hindi", "level": "Basic"}])
    assert found["skills"] == ["Python", "Power BI"]
    assert found["languages"] == [{"language": "Hindi", "level": "Native"}, {"language": "English", "level": ""}]


def test_no_more_than_forty_skills(model):
    text = " ".join(f"tool{n}" for n in range(60))
    model({"work_history": [], "education": [], "skills": [f"tool{n}" for n in range(60)], "languages": []})
    assert len(ai.extract_facts(text, PROFILE, "paste")["skills"]) == 40


def test_facts_with_nothing_found_are_four_empty_lists_not_an_error(model):
    assert facts(model) == {"work_history": [], "education": [], "skills": [], "languages": []}
    model({})
    assert ai.extract_facts(CV, PROFILE, "cv") == {"work_history": [], "education": [], "skills": [], "languages": []}


def test_facts_fail_when_the_model_does(model):
    model(ValueError("bad json"), ValueError("bad json"))
    with pytest.raises(ai.AIError):
        ai.extract_facts(CV, PROFILE, "cv")


def test_facts_prompt_forbids_guessing_and_names_the_levels(model):
    calls = model({})
    ai.extract_facts(CV, PROFILE, "cv")
    assert "never guess a month" in calls[0]["system"] and all(level in calls[0]["system"] for level in ai.LANGUAGE_LEVELS)
    assert "CV text:" in calls[0]["user"] and CV in calls[0]["user"]


# ---------- step 1: GitHub repositories to project achievements ----------

REPOS = [
    {"n": 1, "name": "delay-report", "description": "Weekly delivery delays report", "language": "Python",
     "readme": "# Delay report\nLoads depot delivery data with pandas and builds a weekly delays report in SQL."},
    {"n": 2, "name": "mess-feedback", "description": "", "language": "Python",
     "readme": "A Flask app used by 400 students to rate hostel meals."},
]


def project(n, **kw):
    return {"n": n, "title": "Delay report", "raw": "builds a weekly delays report in SQL", "uk_version": "Built a weekly delays report in SQL and pandas",
            "skills": ["SQL", "pandas"], "outcome": "Add a number: how many depots", "scale": "", "context_note": "Say who used it."} | kw


def test_github_gives_one_achievement_per_repository(model):
    model({"items": [project(1), project(2, title="", raw="A Flask app used by 400 students", uk_version="Built a Flask app used by 400 students")]})
    found = ai.github_achievements(REPOS)
    assert set(found) == {1, 2}
    assert found[1] == {"title": "Delay report", "raw": "builds a weekly delays report in SQL", "uk_version": "Built a weekly delays report in SQL and pandas",
                        "skills": ["SQL", "pandas"], "outcome": "Add a number: how many depots", "scale": "", "context_note": "Say who used it."}
    assert found[2]["title"] == "mess-feedback" and found[2]["raw"] == "A Flask app used by 400 students"


def test_a_github_quote_must_come_from_that_repository(model):
    model({"items": [project(1, raw="A Flask app used by 400 students to rate hostel meals"),   # the other repository's README
                     project(2, raw="Weekly delivery delays report", uk_version="Built a meal rating app")]})  # the other one's description
    found = ai.github_achievements(REPOS)
    assert found[1]["raw"] == "" and found[2]["raw"] == ""


def test_a_github_quote_may_come_from_the_description(model):
    model({"items": [project(1, raw="Weekly delivery delays report")]})
    assert ai.github_achievements(REPOS)[1]["raw"] == "Weekly delivery delays report"


def test_github_ignores_a_repository_that_was_not_sent_a_repeat_and_an_empty_bullet(model):
    model({"items": [project(7), project(1), project(1, uk_version="A second go at the same one"), project(2, uk_version="  ")]})
    found = ai.github_achievements(REPOS)
    assert list(found) == [1] and found[1]["uk_version"] == "Built a weekly delays report in SQL and pandas"


def test_github_reads_a_repository_number_given_as_text(model):
    model({"items": [project("2", raw="")]})
    assert list(ai.github_achievements(REPOS)) == [2]


def test_github_with_nothing_usable_is_an_error(model):
    model({"items": [project(7)]})
    with pytest.raises(ai.AIError):
        ai.github_achievements(REPOS)
    model({"items": []}, {"items": []})
    with pytest.raises(ai.AIError):
        ai.github_achievements(REPOS)


def test_github_prompt_holds_the_readmes_and_forbids_invention(model):
    calls = model({"items": [project(1)]})
    ai.github_achievements([REPOS[0] | {"stars": 950}])
    assert "builds a weekly delays report in SQL" in calls[0]["user"] and "delay-report" in calls[0]["user"]
    assert "950" not in calls[0]["user"] and "do not make one up" in calls[0]["system"]


# ---------- step 1: improving one achievement ----------

WEAK = {"id": "a1", "title": "Delays report", "raw": "I built a weekly delays report", "uk_version": "Built a weekly delivery delays report for depot managers",
        "skills": ["SQL", "Excel"], "outcome": "Add a number: how many managers used it", "scale": "", "context_note": ""}


def better(**kw):
    return {"uk_version": "Built a weekly delivery delays report used by 15 depot managers", "outcome": "Used by 15 managers", "scale": "15 managers"} | kw


def test_improve_uses_the_note_and_returns_the_three_fields(model):
    calls = model(better(uk_version="  Built a weekly delivery delays report used by 15 depot managers  "))
    assert ai.improve(WEAK, "15 depot managers used it") == better()
    assert "15 depot managers used it" in calls[0]["user"] and "Built a weekly delivery delays report for depot managers" in calls[0]["user"]


def test_improve_rejects_a_number_that_is_in_neither_the_achievement_nor_the_note(model):
    calls = model(better(uk_version="Built a weekly report used by 15 managers, cutting delays by 30%"), better())
    assert ai.improve(WEAK, "15 depot managers used it") == better()
    assert len(calls) == 2


def test_improve_fails_and_returns_nothing_when_every_reply_invents_a_number(model):
    model(better(outcome="Saved 40 hours"), better(scale="200 depots"))
    with pytest.raises(ai.AIError):
        ai.improve(WEAK, "15 depot managers used it")


@pytest.mark.parametrize("note, bullet", [
    ("it saved five hours a week", "Built a report saving 5 hours a week"),
    ("about 1200 orders a day", "Built a report covering 1,200 orders a day"),
    ("late deliveries fell eight percent", "Built a report that cut late deliveries by 8%"),
    ("", "Built a weekly delivery delays report for depot managers in SQL and Excel"),
])
def test_improve_accepts_the_same_number_written_differently(model, note, bullet):
    model({"uk_version": bullet, "outcome": "", "scale": ""})
    assert ai.improve(WEAK, note)["uk_version"] == bullet


def test_improve_keeps_numbers_the_achievement_already_had(model):
    strong = WEAK | {"uk_version": "Built a report for 15 managers", "outcome": "8% fewer late deliveries"}
    model({"uk_version": "Built a weekly report for 15 depot managers, cutting late deliveries by 8%", "outcome": "8% fewer late deliveries", "scale": "15 managers"})
    assert "8%" in ai.improve(strong, "make it tighter")["uk_version"]


def test_improve_needs_a_bullet_back(model):
    model({"uk_version": "", "outcome": "x", "scale": ""}, {"uk_version": " ", "outcome": "", "scale": ""})
    with pytest.raises(ai.AIError):
        ai.improve(WEAK, "15 managers")


# ---------- step 1: the story bank ----------

BANK = [{"n": 1, "id": "a1", "title": "Delays report", "raw": "r", "uk_version": "Built a weekly delays report for 15 managers", "skills": ["SQL"], "outcome": "8% fewer", "scale": ""},
        {"n": 2, "id": "a2", "title": "Merge script", "raw": "r", "uk_version": "Wrote a merge script", "skills": ["Python"], "outcome": "", "scale": ""}]


def told(n, **kw):
    return {"n": n, "title": "The delays report", "competency": "Problem solving", "situation": "s", "task": "t", "action": "a", "result": "r",
            "strength": "Strong", "tip": ""} | kw


def test_story_bank_writes_one_story_per_achievement_sent(model):
    model({"stories": [told(1), told(2, title="", competency="Initiative", strength="superb")]})
    found = ai.story_bank(BANK)
    assert set(found) == {1, 2}
    assert found[1] == {"title": "The delays report", "competency": "Problem solving", "situation": "s", "task": "t", "action": "a", "result": "r",
                        "strength": "strong", "tip": ""}
    assert found[2]["title"] == "Merge script" and found[2]["strength"] == "needs detail"


def test_story_bank_ignores_an_unknown_number_a_repeat_and_a_story_with_no_action(model):
    model({"stories": [told(9), told(1), told(1, title="Again"), told(2, action="")]})
    found = ai.story_bank(BANK)
    assert list(found) == [1] and found[1]["title"] == "The delays report"


def test_story_bank_with_nothing_usable_is_an_error(model):
    model({"stories": [told(9)]})
    with pytest.raises(ai.AIError):
        ai.story_bank(BANK)


def test_story_bank_prompt_asks_for_different_competencies_and_avoids_those_covered(model):
    calls = model({"stories": [told(1)]}, {"stories": [told(1)]})
    ai.story_bank(BANK, ["Teamwork", "Influencing"])
    ai.story_bank(BANK)
    assert "different competency" in calls[0]["system"] and "Teamwork, Influencing" in calls[0]["system"]
    assert "already covered" not in calls[1]["system"]
    assert "Built a weekly delays report for 15 managers" in calls[0]["user"] and '"id"' not in calls[0]["user"]


def test_star_still_normalises_through_the_shared_helper(model):
    model(told(0, title="", strength="NEEDS A NUMBER"))
    story = ai.star({"title": "Delays report", "uk_version": "Built X"})
    assert story["title"] == "Delays report" and story["strength"] == "needs a number" and "n" not in story
