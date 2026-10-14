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
    story = {"title": "t", "competency": "c", "situation": "s", "task": "t", "action": "a", "result": "r", "strength": "strong", "tip": ""}
    calls = model(story | {"situation": " "}, story)
    assert ai.star(ACHIEVEMENTS[0])["action"] == "a"
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
    # the model sometimes leaves its "add a number" marker beside a bullet that already has one: the bullet decides
    ({"uk_version": "Automated a merge in Python, saving about 5 hours a week", "outcome": "Add a number: hours saved per week"}, False),
    ({"uk_version": "Built a report for depot managers", "outcome": "add a number: the fall in late deliveries from 2024"}, True),
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


# ---------- step 1: the prompt's own placeholder must never reach the user ----------

PLACEHOLDER = "Add a number: <what to measure>"


def test_extract_does_not_pass_on_the_prompts_placeholder(model):
    model({"items": [item(outcome=PLACEHOLDER), item(title="Script", uk_version="Wrote a script", outcome="Add a number: hours saved a week")], "pitch": ""})
    outcomes = [i["outcome"] for i in ai.extract_achievements(CV, PROFILE, "cv")["items"]]
    assert outcomes == ["Add a number", "Add a number: hours saved a week"]


def test_github_does_not_pass_on_the_prompts_placeholder(model):
    model({"items": [project(1, outcome=" add a number: <What To Measure> ")]})
    assert ai.github_achievements(REPOS)[1]["outcome"] == "Add a number"


def test_improve_does_not_pass_on_the_prompts_placeholder(model):
    model({"uk_version": "Built a weekly delivery delays report for depot managers", "outcome": PLACEHOLDER, "scale": ""})
    assert ai.improve(WEAK, "")["outcome"] == "Add a number"


# ---------- the full CV: what the model may and may not decide ----------

DAY = date(2026, 10, 14)
CV_PROFILE = PROFILE | {"phone": "07700 900123", "city": "Zzqxtown", "linkedin_url": "linkedin.com/in/test-person",
                        "github_username": "zzqx-test", "graduation_date": date(2026, 9, 1)}
CV_JOBS = [{"id": "j1", "employer": "Zzqx Holdings Ltd", "job_title": "Data Analyst", "location": "Pune", "country": "India",
            "start_month": date(2023, 7, 1), "end_month": date(2025, 8, 1), "is_current": False}]
CV_COURSES = [{"id": "c1", "institution": "Zzqx City University", "qualification": "MSc", "subject": "Data Science",
               "end_month": date(2026, 9, 1), "grade": "Merit"}]
CV_ACHIEVEMENTS = [
    {"id": "a1", "title": "Delays report", "uk_version": "Built a weekly delays report in SQL used by 15 managers, cutting late deliveries by 8%",
     "skills": ["SQL", "Excel"], "outcome": "8% fewer late deliveries", "scale": "15 managers", "raw": "about fifteen depot managers used it",
     "work_history_id": "j1", "education_id": None},
    {"id": "a2", "title": "Bus times", "uk_version": "Built a bus arrival model in Python", "skills": ["Python"], "outcome": "", "scale": "",
     "work_history_id": None, "education_id": "c1"},
    {"id": "a3", "title": "Society treasurer", "uk_version": "Managed a society budget", "skills": [], "outcome": "", "scale": "",
     "work_history_id": None, "education_id": None},
]
CV_SKILLS = ["SQL", "Excel", "Python", "Power BI"]
FAITHFUL = "Built a weekly SQL delays report for 15 managers that cut late deliveries by 8%"
BODY = {"profile": "Data analyst with over 2 years of experience in logistics reporting.",
        "bullets": [{"achievement_id": "a1", "text": FAITHFUL}], "skills": {"technical": ["SQL"], "tools": ["Excel"]}}
LETTER = {"keywords": ["data"], "gaps": [], "cover_letter": {"why_them": "Your reporting team.", "why_you": "I built a report for 15 managers.",
                                                             "what_you_deliver": "A weekly findings report."}}


def cv_body(job=JOB):
    return ai.build_cv(CV_PROFILE, CV_COURSES, CV_JOBS, CV_ACHIEVEMENTS, CV_SKILLS, job, today=DAY)


def cv_letter(job=JOB):
    return ai.job_letter(job, CV_PROFILE, CV_COURSES, CV_JOBS, CV_ACHIEVEMENTS)


def test_build_cv_returns_only_wording(model):
    model(BODY | {"work": [{"employer": "Invented Ltd"}], "education": [{"grade": "Distinction"}]})
    out = cv_body()
    assert out == {"profile": BODY["profile"], "bullets": [{"achievement_id": "a1", "text": FAITHFUL}],
                   "skills": {"technical": ["SQL"], "tools": ["Excel"]}}


def test_build_cv_drops_a_bullet_for_an_unknown_id(model):
    model(BODY | {"bullets": [{"achievement_id": "zzz", "text": "Ran a team of 40"}, {"achievement_id": "a1", "text": FAITHFUL},
                              {"achievement_id": "", "text": "Did something"}]})
    assert cv_body()["bullets"] == [{"achievement_id": "a1", "text": FAITHFUL}]


def test_build_cv_keeps_one_bullet_per_achievement(model):
    model(BODY | {"bullets": [{"achievement_id": "a1", "text": FAITHFUL}, {"achievement_id": " a1 ", "text": "The same thing again for 15 managers, 8%"},
                              {"achievement_id": "a2", "text": "Modelled bus arrivals in Python"}]})
    assert [b["achievement_id"] for b in cv_body()["bullets"]] == ["a1", "a2"]


@pytest.mark.parametrize("wording", [
    "Built a weekly SQL delays report for 50 managers, cutting late deliveries by 8%",        # a number changed
    "Built a weekly SQL delays report for depot managers, cutting late deliveries by 8%",     # a number dropped
    "Built a weekly SQL delays report for 15 managers in 3 depots, cutting late deliveries by 8%",  # a number added
    "Built a weekly SQL delays report for fifteen managers, cutting late deliveries by 8%",   # a number respelled: not exactly as stored
    "   ",
])
def test_a_bullet_that_does_not_keep_the_numbers_falls_back_to_the_stored_one(model, wording):
    model(BODY | {"bullets": [{"achievement_id": "a1", "text": wording}]})
    assert cv_body()["bullets"] == [{"achievement_id": "a1", "text": CV_ACHIEVEMENTS[0]["uk_version"]}]


def test_a_faithful_rewording_is_kept(model):
    model(BODY | {"bullets": [{"achievement_id": "a1", "text": FAITHFUL}, {"achievement_id": "a2", "text": "Modelled bus arrival times in Python"}]})
    assert [b["text"] for b in cv_body()["bullets"]] == [FAITHFUL, "Modelled bus arrival times in Python"]


def test_a_bullet_may_use_a_number_held_elsewhere_in_the_achievement(model):
    model(BODY | {"bullets": [{"achievement_id": "a1", "text": FAITHFUL + " (15 depot managers)"}]})
    assert cv_body()["bullets"][0]["text"].endswith("(15 depot managers)")


def test_skills_only_from_the_users_own_in_their_spelling(model):
    model(BODY | {"skills": {"technical": ["sql", "Tableau", " PYTHON "], "tools": ["power bi", "Kubernetes", ""]}})
    assert cv_body()["skills"] == {"technical": ["SQL", "Python"], "tools": ["Power BI"]}


def test_a_skill_in_both_groups_is_listed_once(model):
    model(BODY | {"skills": {"technical": ["SQL", "Excel", "sql"], "tools": ["Excel", "Power BI"]}})
    assert cv_body()["skills"] == {"technical": ["SQL", "Excel"], "tools": ["Power BI"]}


def test_skills_of_the_wrong_shape_give_empty_groups(model):
    model(BODY | {"skills": ["SQL", "Excel"]})
    assert cv_body()["skills"] == {"technical": [], "tools": []}


def test_paragraph_with_an_invented_number_is_asked_for_again_then_fails(model):
    invented = BODY | {"profile": "Data analyst with 7 years of experience."}
    calls = model(invented, BODY)
    assert cv_body()["profile"] == BODY["profile"] and len(calls) == 2
    calls = model(invented, invented)
    with pytest.raises(ai.AIError):
        cv_body()
    assert len(calls) == 2


def test_a_number_the_advert_asks_for_is_not_the_candidates(model):
    asks = JOB | {"description": "You need 5 years of experience in reporting. " * 3}
    claims = BODY | {"profile": "Data analyst with 5 years of experience."}
    model(claims, claims)
    with pytest.raises(ai.AIError):
        cv_body(asks)


@pytest.mark.parametrize("reply", [BODY | {"profile": " "}, BODY | {"bullets": []}])
def test_build_cv_needs_a_paragraph_and_a_bullet(model, reply):
    model(reply, reply)
    with pytest.raises(ai.AIError):
        cv_body()


def test_build_cv_with_no_usable_bullet_fails(model):
    model(BODY | {"bullets": [{"achievement_id": "zzz", "text": "Ran a team"}]})
    with pytest.raises(ai.AIError):
        cv_body()


def test_build_cv_prompt_has_no_name_or_contact_details(model):
    calls = model(BODY)
    cv_body()
    prompt = calls[0]["system"] + calls[0]["user"]
    for private in ("Test Person", "07700", "Zzqxtown", "linkedin", "zzqx-test", "visa"):
        assert private not in prompt, private


def test_build_cv_prompt_says_where_each_achievement_happened(model):
    calls = model(BODY)
    cv_body()
    user = calls[0]["user"]
    assert "job: Data Analyst at Zzqx Holdings Ltd" in user and "project on the course at Zzqx City University" in user
    assert '"where": "project"' in user and '"length": "2 years 2 months"' in user and '"from": "2023-07"' in user
    assert "MSc Course A at University A" in user and '"Power BI"' in user


def test_build_cv_prompt_states_the_rules(model):
    calls = model(BODY)
    cv_body()
    system = calls[0]["system"]
    assert "Use only the facts given" in system and "Never add an employer, a date, a qualification, a skill, a tool or a number" in system
    assert "Keep every number exactly as the achievement writes it" in system and "two A4 pages" in system
    assert "tailored to one job" in system and "Job description:" in calls[0]["user"]


def test_base_cv_prompt_names_no_job(model):
    calls = model(BODY)
    cv_body(None)
    assert "Job description" not in calls[0]["user"] and "Company:" not in calls[0]["user"]
    assert "for any job in the field" in calls[0]["system"] and "tailored" not in calls[0]["system"]


def test_build_cv_prompt_cuts_a_long_advert(model):
    calls = model(BODY)
    cv_body(JOB | {"description": "x" * 10000})
    assert "x" * 6000 in calls[0]["user"] and "x" * 6001 not in calls[0]["user"]


def test_keywords_must_be_in_the_advert(model):
    model(LETTER | {"keywords": ["data", "Tableau", " Report findings. ", "DATA", "", "analyse data and report findings and much more besides this"]})
    assert cv_letter()["keywords"] == ["data", "Report findings"]


def test_at_most_twelve_keywords(model):
    words = [f"zzqx{n}" for n in range(30)]
    model(LETTER | {"keywords": words})
    assert cv_letter(JOB | {"description": " ".join(words)})["keywords"] == words[:12]


def test_letter_needs_all_three_paragraphs(model):
    partial = LETTER | {"cover_letter": {"why_them": "A", "why_you": "B", "what_you_deliver": " "}}
    calls = model(partial, partial)
    with pytest.raises(ai.AIError):
        cv_letter()
    assert len(calls) == 2
    model(partial, LETTER)
    assert cv_letter()["cover_letter"] == LETTER["cover_letter"]


def test_letter_with_an_invented_number_fails(model):
    invented = LETTER | {"cover_letter": LETTER["cover_letter"] | {"why_you": "I saved 99 hours a week."}}
    model(invented, invented)
    with pytest.raises(ai.AIError):
        cv_letter()


def test_letter_may_use_the_candidates_numbers_and_the_jobs_title(model):
    reply = LETTER | {"cover_letter": {"why_them": "The Level 3 Analyst role suits me.", "why_you": "I cut late deliveries by 8% for 15 managers.",
                                       "what_you_deliver": "A weekly report."}}
    model(reply)
    assert cv_letter(JOB | {"title": "Level 3 Analyst"})["cover_letter"]["why_you"] == "I cut late deliveries by 8% for 15 managers."


def test_gaps_are_trimmed_and_capped(model):
    model(LETTER | {"gaps": [" No Tableau yet ", "", "a", "b", "c", "d", "e"]})
    assert cv_letter()["gaps"] == ["No Tableau yet", "a", "b", "c", "d"]


def test_job_letter_prompt_cuts_a_long_advert_and_names_nobody(model):
    calls = model(LETTER)
    cv_letter(JOB | {"description": "x" * 10000})
    prompt = calls[0]["system"] + calls[0]["user"]
    assert "x" * 6000 in prompt and "x" * 6001 not in prompt
    for private in ("Test Person", "07700", "Zzqxtown", "linkedin", "zzqx-test", "visa"):
        assert private not in prompt, private
    assert "job: Data Analyst at Zzqx Holdings Ltd" in prompt and "MSc Course A at University A" in prompt


@pytest.mark.parametrize("wording, kept", [
    ("Built a weekly SQL delays report for 15 managers, cutting late deliveries by about 8%", True),
    ("Built a weekly SQL delays report for 15 managers, cutting late deliveries by roughly 8%", True),   # another hedge will do
    ("Built a weekly SQL delays report for 15 managers, cutting late deliveries by 8%", False),          # "about 8%" became a flat 8%
])
def test_a_bullet_that_drops_a_hedge_falls_back_to_the_stored_one(model, wording, kept):
    hedged = CV_ACHIEVEMENTS[0] | {"uk_version": "Built a weekly delays report in SQL used by 15 managers, cutting late deliveries by about 8%"}
    model(BODY | {"bullets": [{"achievement_id": "a1", "text": wording}]})
    out = ai.build_cv(CV_PROFILE, CV_COURSES, CV_JOBS, [hedged, *CV_ACHIEVEMENTS[1:]], CV_SKILLS, JOB, today=DAY)
    assert out["bullets"][0]["text"] == (wording if kept else hedged["uk_version"])


def test_build_cv_prompt_forbids_strengthening_a_claim(model):
    calls = model(BODY)
    cv_body()
    assert "Do not strengthen a claim" in calls[0]["system"] and "about" in calls[0]["system"]


def test_build_cv_is_told_what_not_to_claim(model):
    calls = model(BODY, BODY)
    ai.build_cv(CV_PROFILE, CV_COURSES, CV_JOBS, CV_ACHIEVEMENTS, CV_SKILLS, JOB, DAY, avoid=["Tableau", "dbt"])
    cv_body()
    assert "nothing in the candidate's facts shows them: Tableau, dbt" in calls[0]["system"] and "Do not say or imply" in calls[0]["system"]
    assert "Tableau" not in calls[1]["system"] and "nothing in the candidate's facts shows" not in calls[1]["system"]


def test_build_cv_prompt_limits_the_paragraph_to_what_the_facts_show(model):
    calls = model(BODY)
    cv_body()
    assert "It may claim only what the candidate's facts show" in calls[0]["system"] and "leave it out" in calls[0]["system"]


def test_filler_words_are_not_keywords(model):
    advert = JOB | {"description": "Strong Excel skills and SQL experience are essential. Tableau is desirable. You will build reports."}
    model(LETTER | {"keywords": ["SQL", "experience", "Desirable", "build", "skills", "Excel skills", "Tableau", "essential"]})
    assert cv_letter(advert)["keywords"] == ["SQL", "Excel skills", "Tableau"]


def test_a_keyword_is_at_most_three_words(model):
    advert = JOB | {"description": "A degree in a quantitative subject, SQL and stakeholder management skills. Automate recurring reports."}
    model(LETTER | {"keywords": ["degree in a quantitative subject", "SQL", "stakeholder management", "Automate recurring reports", "stakeholder management skills too"]})
    assert cv_letter(advert)["keywords"] == ["SQL", "stakeholder management", "Automate recurring reports"]


def test_gaps_are_written_to_the_user(model):
    calls = model(LETTER)
    cv_letter()
    assert "addressed to the candidate as 'you'" in calls[0]["system"]


# ---------- the lesson from a rejection (step 4) ----------

ADVERT = {"title": "Zzqx Analyst", "company": "Zzqx Holdings Ltd", "description": "We need strong SQL and stakeholder reporting. " * 3}
CV_TEXT = "Graduate analyst.\nBuilt a Python dashboard used by 40 staff.\nPython\nExcel"
GOOD_LESSON = {"likely_reason": "The CV may not have shown the SQL the advert asked for.",
               "one_change": "Put the SQL from your dashboard project in its first bullet.", "page": "resume"}


def lesson(**kw):
    return ai.rejection_lesson(**(dict(job=ADVERT, cv_text=CV_TEXT, ended_at="cv", feedback="") | kw))


def test_lesson_returns_its_three_parts(model):
    model(GOOD_LESSON)
    assert lesson() == GOOD_LESSON


def test_lesson_stated_as_fact_is_retried_then_refused(model):
    certain = GOOD_LESSON | {"likely_reason": "The CV did not show SQL."}
    calls = model(certain, certain)
    with pytest.raises(ai.AIError):
        lesson()
    assert len(calls) == 2
    model(certain, GOOD_LESSON)
    assert lesson() == GOOD_LESSON


def test_lesson_needs_a_reason_and_a_change(model):
    empty = GOOD_LESSON | {"one_change": " "}
    model(empty, empty)
    with pytest.raises(ai.AIError):
        lesson()


@pytest.mark.parametrize("part, wording", [
    ("likely_reason", "Their feedback suggests the SQL may have looked thin."),
    ("one_change", "As they said, put SQL first."),
    ("one_change", "You were told the CV may be too long, so cut it."),
])
def test_lesson_repeating_feedback_that_was_never_given_is_refused(model, part, wording):
    invented = GOOD_LESSON | {part: wording}
    model(invented, invented)
    with pytest.raises(ai.AIError):
        lesson(feedback="")


def test_lesson_may_use_feedback_that_was_given(model):
    using = GOOD_LESSON | {"likely_reason": "Their feedback suggests the SQL may have looked thin."}
    model(using)
    assert lesson(feedback="We wanted more SQL experience.") == using


def test_lesson_may_suggest_asking_for_feedback(model):
    asking = GOOD_LESSON | {"one_change": "Ask for feedback next time, and put SQL first."}
    model(asking)
    assert lesson() == asking


def test_lesson_quote_must_be_in_the_inputs(model):
    made_up = GOOD_LESSON | {"likely_reason": 'The advert asked for "five years of Tableau", which the CV may not show.'}
    model(made_up, made_up)
    with pytest.raises(ai.AIError):
        lesson()
    real = GOOD_LESSON | {"likely_reason": "The advert asked for “strong SQL”, which the CV may not show."}
    model(real)
    assert lesson() == real
    from_feedback = GOOD_LESSON | {"likely_reason": 'They may have meant it when they said "not enough SQL".'}
    model(from_feedback)
    assert lesson(feedback="Not enough SQL, sorry.") == from_feedback


def test_lesson_without_advert_may_not_describe_it(model):
    describing = GOOD_LESSON | {"likely_reason": "The job description may have wanted more SQL."}
    model(describing, describing)
    with pytest.raises(ai.AIError):
        lesson(job=None)
    model(describing)
    assert lesson() == describing  # with an advert recorded it may


def test_lesson_written_to_you_not_about_the_candidate(model):
    # the real model wrote "The candidate may have lacked..." on 14 October 2026
    third_person = GOOD_LESSON | {"likely_reason": "The candidate may not have shown enough SQL."}
    calls = model(third_person, third_person)
    with pytest.raises(ai.AIError):
        lesson()
    assert "'you'" in calls[0]["system"]


def test_lesson_without_cv_may_still_say_what_it_should_have_shown(model):
    # with no CV recorded the real model always wrote about the CV; worded as a possibility that is a fair guess,
    # and refusing it would leave every application tracked without a CV with no lesson at all
    guess = GOOD_LESSON | {"likely_reason": "Your CV may not have shown the SQL the advert asked for."}
    model(guess)
    assert lesson(cv_text="") == guess


@pytest.mark.parametrize("ended_at, page, expected", [("cv", "Resume", "resume"), ("cv", "linkedin", "resume"), ("cv", "your CV", "resume"),
                                                      ("interview", "", "interview"), ("final", "Interview coach", "interview"),
                                                      ("screening", "PROFILE", "profile")])
def test_lesson_page_normalised(model, ended_at, page, expected):
    model(GOOD_LESSON | {"page": page})
    assert lesson(ended_at=ended_at)["page"] == expected


def test_lesson_prompt_says_what_was_recorded_and_what_was_not(model):
    calls = model(GOOD_LESSON | {"likely_reason": "The CV may not have shown enough SQL."})
    lesson(job=None, ended_at="final")
    prompt = calls[0]["user"]
    assert "No job description was recorded" in prompt and "No feedback was given" in prompt
    assert "Built a Python dashboard used by 40 staff." in prompt and "after a final interview" in prompt
    calls = model(GOOD_LESSON | {"likely_reason": "The advert may have wanted more SQL than they saw."})
    lesson(cv_text="", feedback="We wanted more SQL.")
    prompt = calls[0]["user"]
    assert "No CV was recorded" in prompt and "We need strong SQL" in prompt and "We wanted more SQL." in prompt


# ---------- a follow-up draft (step 4) ----------

GOOD_DRAFT = {"subject": "Zzqx Analyst application",
              "body": "I applied for the Zzqx Analyst role on 7 October 2026 and wanted to check whether you need anything else from me. "
                      "I remain very interested in the role. Could you let me know when you expect to make a decision?"}


def draft(**kw):
    return ai.follow_up(**(dict(role="Zzqx Analyst", company="Zzqx Holdings Ltd", applied_on=date(2026, 10, 7),
                                contact_name="Zzqx Person", sender="Test Person") | kw))


def test_draft_wrapped_with_greeting_and_name(model):
    model(GOOD_DRAFT)
    assert draft() == {"subject": GOOD_DRAFT["subject"],
                       "message": f"Dear Zzqx Person,\n\n{GOOD_DRAFT['body']}\n\nKind regards,\nTest Person"}
    model(GOOD_DRAFT)
    assert draft(contact_name="  ")["message"].startswith("Dear Hiring Manager,\n\n")


def test_users_name_never_sent(model):
    calls = model(GOOD_DRAFT)
    draft(sender="Zzqx Sendername")
    sent = calls[0]["system"] + calls[0]["user"]
    assert "Zzqx Sendername" not in sent
    assert all(part in sent for part in ("Zzqx Person", "Zzqx Analyst", "Zzqx Holdings Ltd", "7 October 2026"))


def test_draft_over_80_words_retried(model):
    calls = model(GOOD_DRAFT | {"body": "I am writing to follow up on my application. " * 10}, GOOD_DRAFT)
    assert GOOD_DRAFT["body"] in draft()["message"] and len(calls) == 2


@pytest.mark.parametrize("placeholder", ["[Your name]", "<date>", "{company}"])
def test_draft_with_placeholder_retried(model, placeholder):
    calls = model(GOOD_DRAFT | {"body": f"Thank you for considering me, {placeholder}."}, GOOD_DRAFT)
    assert placeholder not in draft()["message"] and len(calls) == 2


def test_draft_with_invented_number_retried(model):
    calls = model(GOOD_DRAFT | {"body": "I applied on 7 October 2026 and bring 3 years of SQL."}, GOOD_DRAFT)
    assert "3 years" not in draft()["message"] and len(calls) == 2


def test_draft_numbers_from_role_and_company_allowed(model):
    named = {"subject": "Analyst 2 application", "body": "I applied for Analyst 2 at Zzqx 360 on 7 October 2026. Is there any news?"}
    model(named)
    assert named["body"] in draft(role="Analyst 2", company="Zzqx 360")["message"]


def test_draft_greeting_on_the_same_line_as_the_body_removed(model):
    # as the real model wrote it on 14 October 2026: greeting and body in one line
    model(GOOD_DRAFT | {"body": f"Dear Zzqx, {GOOD_DRAFT['body']}"})
    assert draft()["message"] == f"Dear Zzqx Person,\n\n{GOOD_DRAFT['body']}\n\nKind regards,\nTest Person"


@pytest.mark.parametrize("ending", [" Best wishes", " Kind regards, [Your name]", " Many thanks,\nZzqx"])
def test_draft_sign_off_at_the_end_of_the_body_removed(model, ending):
    # as the real model wrote it on 14 October 2026: "...any update you can share. Best wishes"
    model(GOOD_DRAFT | {"body": GOOD_DRAFT["body"] + ending})
    assert draft()["message"] == f"Dear Zzqx Person,\n\n{GOOD_DRAFT['body']}\n\nKind regards,\nTest Person"


def test_draft_own_greeting_and_sign_off_removed(model):
    framed = GOOD_DRAFT | {"body": f"Dear Zzqx Person,\n\n{GOOD_DRAFT['body']}\n\nKind regards,\n[Your name]"}
    model(framed)
    message = draft()["message"]
    assert message == f"Dear Zzqx Person,\n\n{GOOD_DRAFT['body']}\n\nKind regards,\nTest Person"
