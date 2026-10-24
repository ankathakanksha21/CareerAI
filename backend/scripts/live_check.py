"""One real call to the configured model for each AI task, to prove the prompts and parsing
work end to end. Uses real credits. Prints a line per task; never prints prompts, replies or keys.

Run from backend/ with the venv active:  python scripts/live_check.py
To run only some checks, name them:      python scripts/live_check.py cv github "story bank"
(every check whose name contains one of the words is run)."""
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai  # noqa: E402
import cv  # noqa: E402
import cvbuild  # noqa: E402
import intake  # noqa: E402
import jobs  # noqa: E402
import companies_house  # noqa: E402
import research  # noqa: E402
from config import research_configured  # noqa: E402

PROFILE = {"full_name": "Sample Candidate", "course": "MSc Data Science", "university": "a UK university",
           "visa_type": "student", "visa_end_date": date(2027, 1, 31)}
BACKGROUND = (
    "Before my masters I worked for two years as a junior analyst at a logistics company. I built a weekly delivery "
    "delays report in SQL and Excel that about fifteen depot managers used, and late deliveries fell by roughly eight percent. "
    "I also wrote a Python script that merged three spreadsheets and saved around five hours a week. "
    "At university I did a group project forecasting bike hire demand. I would like a data analyst role."
)
ACHIEVEMENTS = [
    {"id": "a1", "title": "Delivery delays report", "raw": "weekly delays report in SQL and Excel",
     "uk_version": "Built a weekly delivery delays report in SQL and Excel used by 15 depot managers, with late deliveries falling about 8%.",
     "skills": ["SQL", "Excel"], "outcome": "About 8% fewer late deliveries", "scale": "15 managers"},
    {"id": "a2", "title": "Spreadsheet automation", "raw": "python script merging spreadsheets",
     "uk_version": "Automated a three-spreadsheet merge in Python, saving about 5 hours a week.",
     "skills": ["Python"], "outcome": "5 hours a week saved", "scale": "one team"},
]
DESCRIPTION = (
    "We are looking for a Data Analyst to join our operations team. You will write SQL queries, build dashboards, "
    "and explain findings to non-technical colleagues. Experience with Python and stakeholder communication is desirable."
)
JOB = {"title": "Data Analyst", "company": "a UK retailer", "description": DESCRIPTION, "keywords": ["SQL", "dashboards"]}
INTERVIEW = (
    "Interviewer: Tell me about a time you improved a process.\n"
    "Candidate: We had a report that took a long time so I wrote a Python script and it saved about five hours a week."
)
STATS = {"funnel": {"applied": 6, "responses": 1, "interviews": 0, "offers": 0, "response_rate": 0.17},
         "by_family": [], "by_source": [], "timing": {"avg_days": 4.0}}

OTHER_DESCRIPTION = (
    "We are looking for a Junior Marketing Executive. You will plan social media campaigns, write copy for email newsletters "
    "and manage relationships with design agencies. Experience with Canva and a marketing qualification are desirable."
)
ADVERTS = [{"n": 1, "title": "Data Analyst", "employer": "a UK retailer", "description": DESCRIPTION},
           {"n": 2, "title": "Junior Marketing Executive", "employer": "a UK charity", "description": OTHER_DESCRIPTION}]
# a full batch at a realistic advert length, to see how long one scoring call takes
FULL_BATCH = [{"n": n, "title": "Data Analyst", "employer": f"employer {n}", "description": (DESCRIPTION + " ") * 8} for n in range(1, 9)]
TITLES = [a["title"] for a in ACHIEVEMENTS]


def _percent(requirements) -> int:
    scored = jobs.fit(requirements, TITLES)
    return scored["percent"] if scored else -1


# Step 1. The text of a two-column CV as a PDF gives it up: a side column of skills mixed into the
# main one, sentences wrapped mid-way. The employer and universities are made up.
CV = """Sample Candidate | London, UK | sample.candidate@example.test
SKILLS
PROFILE
Python
MSc Data Science student with two years as a systems engineer in
Pune. Comfortable with SQL, Python and stakeholder reporting.
SQL
EXPERIENCE
Excel
Systems Engineer, Zzqx Holdings Ltd, Pune, India
Power BI
Jul 2023 - Aug 2025
Built a weekly delivery delays report in SQL and Excel used by 15 depot
managers; late deliveries fell by about 8%.
Wrote a Python script that merged three spreadsheets, saving the team
around 5 hours a week.
LANGUAGES
Data Analyst Intern, Zzqx Foods, Gurugram, India
English (fluent)
Jan 2023 - Jun 2023
Hindi (native)
Analysed 1.2 million order records to find the causes of late deliveries in
three cities.
EDUCATION
MSc Data Science, Zzqx City University, UK, Sep 2025 - Sep 2026, predicted Merit
BTech Computer Science, University of Zzqx, India, 2019 - 2023, CGPA 8.4/10
PROJECTS
Hostel mess feedback app: built a Flask app used by 400 students to rate meals."""
CV_PROFILE = PROFILE | {"course": "MSc Data Science", "university": "Zzqx City University"}
REPOS = [
    {"n": 1, "name": "delay-report", "description": "Weekly delivery delays report", "language": "Python",
     "readme": "# Delay report\nLoads depot delivery data with pandas, joins it to the route table in SQL and writes a weekly "
               "delays report to Excel for depot managers.\n\n## Run\npython report.py --week 2025-30"},
    {"n": 2, "name": "mess-feedback", "description": "", "language": "Python",
     "readme": "A Flask app that lets students rate hostel meals. Used by 400 students in its first term. SQLite storage, Chart.js dashboards."},
]
NO_NUMBER = {"title": "Delays report", "raw": "I built a weekly delays report", "uk_version": "Built a weekly delivery delays report for depot managers",
             "skills": ["SQL", "Excel"], "outcome": "Add a number: how many managers used it", "scale": "", "context_note": ""}
FOUR = [a | {"n": n} for n, a in enumerate([
    ACHIEVEMENTS[0], ACHIEVEMENTS[1],
    {"id": "a3", "title": "Order analysis", "raw": "analysed 1.2 million order records",
     "uk_version": "Analysed 1.2 million order records to find the causes of late deliveries in three cities.",
     "skills": ["SQL", "Python"], "outcome": "Causes found in three cities", "scale": "1.2 million records"},
    {"id": "a4", "title": "Mess feedback app", "raw": "built a Flask app used by 400 students",
     "uk_version": "Built a Flask app used by 400 students to rate hostel meals, leading to menu changes.",
     "skills": ["Flask", "Python"], "outcome": "Menu changed", "scale": "400 students"}], start=1)]
_digits = ai._numbers  # the figures in a text


def _import_twice() -> int:
    """How many achievements a second reading of the same CV returns once told what the first saved."""
    first = ai.extract_achievements(CV, CV_PROFILE, "cv")["items"]
    return len(ai.extract_achievements(CV, CV_PROFILE, "cv", first)["items"])


def _both_at_once() -> dict:
    found = intake.read(CV, CV_PROFILE, "cv", [])
    return found | {"placed": intake.place(found["items"], found["facts"], [], [])}


def _facts_ok(r: dict) -> bool:
    jobs_found = {w["employer"]: w for w in r["work_history"]}
    first = jobs_found.get("Zzqx Holdings Ltd")
    year_only = next((e for e in r["education"] if "University of Zzqx" in e["institution"]), None)
    return (len(jobs_found) == 2 and first is not None and first["start_month"] == date(2023, 7, 1) and first["end_month"] == date(2025, 8, 1)
            and len(r["education"]) == 2 and year_only is not None and year_only["start_month"] is None and year_only["end_month"] is None
            and len(r["skills"]) >= 4 and {x["language"]: x["level"] for x in r["languages"]} == {"English": "Fluent", "Hindi": "Native"})


# Step 3. A candidate with one job, the current course, three achievements at the job and one GitHub
# project. The CV body must only choose and reword: every bullet for a real achievement with its
# numbers intact, and no skill the candidate does not have.
CV_JOBS = [{"id": "j1", "employer": "Zzqx Holdings Ltd", "job_title": "Systems Engineer", "location": "Pune", "country": "India",
            "start_month": date(2023, 7, 1), "end_month": date(2025, 8, 1), "is_current": False,
            "employer_context": "A logistics company with 40 depots across India."}]
CV_COURSES = [{"id": "c1", "institution": "Zzqx City University", "qualification": "MSc", "subject": "Data Science",
               "start_month": date(2025, 9, 1), "end_month": date(2026, 9, 1), "grade": "Merit", "country": "United Kingdom"}]
CV_ACHIEVEMENTS = [a | {"work_history_id": "j1", "education_id": None, "source": "cv", "source_url": None} for a in FOUR[:3]] + [
    FOUR[3] | {"work_history_id": None, "education_id": None, "source": "github", "source_url": "https://github.com/sample-candidate/mess-feedback"}]
CV_SKILLS = ["SQL", "Python", "Excel", "Flask", "Power BI"]
CV_WHOLE_PROFILE = CV_PROFILE | {"graduation_date": date(2026, 9, 1), "skills": CV_SKILLS, "additional": [], "phone": "07700 900123",
                                 "city": "Leeds", "linkedin_url": "linkedin.com/in/sample-candidate", "github_username": "sample-candidate",
                                 "languages": [{"language": "English", "level": "Fluent"}, {"language": "Hindi", "level": "Native"}]}
_OWN = {a["id"]: a for a in CV_ACHIEVEMENTS}


def _body_ok(r: dict) -> bool:
    bullets, listed = r["bullets"], r["skills"]["technical"] + r["skills"]["tools"]
    return (bool(r["profile"]) and len(bullets) >= 3 and all(b["achievement_id"] in _OWN for b in bullets)
            and all(_digits(_OWN[b["achievement_id"]]["uk_version"]) <= _digits(b["text"]) for b in bullets)
            and any(b["text"] != _OWN[b["achievement_id"]]["uk_version"] for b in bullets)  # rewording survives the number rule
            and bool(listed) and set(listed) <= set(CV_SKILLS))


def _letter_ok(r: dict) -> bool:
    return (all(r["cover_letter"].values()) and len(r["keywords"]) >= 3
            and all(cv.has_term(k, f"{JOB['title']} {DESCRIPTION}") for k in r["keywords"]))


def _whole_build() -> tuple:
    return cvbuild.build(profile=CV_WHOLE_PROFILE, email="sample.candidate@example.test", education=CV_COURSES, work_history=CV_JOBS,
                         achievements=CV_ACHIEVEMENTS, job=JOB, today=date.today())


def _build_ok(built: tuple) -> bool:
    content, pages = built
    job = content["work"][0]
    return (pages <= 2 and (job["employer"], job["start_month"], job["end_month"]) == ("Zzqx Holdings Ltd", "2023-07-01", "2025-08-01")
            and len(job["bullets"]) >= 2 and len(content["projects"]) == 1 and content["projects"][0]["link"] == "github.com/sample-candidate/mess-feedback"
            and bool(content["cover_letter"]["why_them"]) and bool(content["keywords"]["terms"]) and content["contact"]["phone"] == "07700 900123")


LESSON_CV = "\n".join([a["uk_version"] for a in CV_ACHIEVEMENTS] + CV_SKILLS)


def _lesson_ok(r: dict) -> bool:
    return r["page"] in ai.LESSON_PAGES and bool(r["likely_reason"]) and bool(r["one_change"])


def _draft_ok(r: dict) -> bool:
    message = r["message"]
    return (bool(r["subject"]) and message.startswith("Dear Priya Shah,\n\n") and message.endswith("Kind regards,\nSample Candidate")
            and len(message.split()) < 90)


# step 5: passages in the shape research numbers them, about a made-up retailer
TODAY = date.today()
PASSAGES = [
    {"n": 1, "kind": "website", "url": "https://northwind.example/", "title": "Northwind Goods | Home", "published_on": None,
     "text": "Northwind Goods runs 140 homeware shops across the UK and an online store. We have been trading since 1987."},
    {"n": 2, "kind": "website", "url": "https://northwind.example/about", "title": "About us", "published_on": None,
     "text": "Our values: Put customers first. Be straightforward. Look after each other. Around 6,000 colleagues work in our shops, "
             "distribution centres and our head office in Leeds."},
    {"n": 3, "kind": "website", "url": "https://northwind.example/careers", "title": "Careers", "published_on": None,
     "text": "Our data team builds the forecasts that decide what goes on every shelf. Graduates join a two-year rotation."},
    {"n": 4, "kind": "news", "url": "https://news.example/northwind-app", "title": "Northwind launches click and collect app",
     "published_on": TODAY - timedelta(days=60), "text": "Northwind Goods has launched a click and collect app for its 140 shops."},
    {"n": 5, "kind": "news", "url": "https://news.example/northwind-old", "title": "Northwind opens first shop",
     "published_on": TODAY - timedelta(days=900), "text": "Northwind Goods opened a shop in York."},
    {"n": 6, "kind": "competitors", "url": "https://compare.example/homeware", "title": "UK homeware retailers compared", "published_on": None,
     "text": "Northwind Goods competes with Larkspur Home and Fenwick Living for mid-priced homeware."},
]
FACTS = [{"id": f"f{i}", "section": s, "text": t} for i, (s, t) in enumerate([
    ("what_they_do", "Northwind Goods runs 140 homeware shops across the UK and an online store."),
    ("values", "Northwind says it puts customers first."),
    ("products", "Its data team builds the forecasts that decide what goes on every shelf."),
    ("news", "Northwind launched a click and collect app."),
    ("competitors", "Northwind competes with Larkspur Home and Fenwick Living.")], start=1)]
STORIES = [{"id": "story-1", "title": "The delays report", "competencies": ["problem_solving"], "situation": "Deliveries were often late.",
            "task": "Find out why.", "action": "I built a weekly report in SQL and walked the managers through it.", "result": "Late deliveries fell by about 8%."},
           {"id": "story-2", "title": "Merging the spreadsheets", "competencies": [], "situation": "Three teams kept separate sheets.",
            "task": "Save the weekly copying.", "action": "I wrote a Python script and agreed the columns with each team.", "result": "About 5 hours a week saved."}]


def _brief_ok(statements: list) -> bool:
    sections = {x["section"] for x in statements}
    return len(sections) >= 3 and all(1 <= x["source"] <= len(PASSAGES) and x["source"] != 5 for x in statements if x["section"] == "news")


def _real_research() -> dict:
    """A real well-known employer through Companies House, its website and the search service. Needs the research keys."""
    if not research_configured():
        return {"skipped": True}
    match = companies_house.search("Monzo Bank")[0]
    gathered = research.gather(name="Monzo", number=match["number"], website="https://monzo.com/", today=TODAY)
    return research.brief("Monzo", gathered, TODAY) | {"pages": len(gathered["pages"]), "news": len(gathered["news"])}


def _real_ok(r: dict) -> bool:
    if r.get("skipped"):
        print("  (research keys not set: skipped, not counted)", flush=True)
        return True
    print(f"  {r['pages']} pages, {r['news']} news results, {len(r['facts'])} lines, missing: {r['missing']}", flush=True)
    year_ago = (TODAY - timedelta(days=365)).isoformat()
    return (len({f["section"] for f in r["facts"]}) >= 3 and all(f["url"].startswith("https://") for f in r["facts"])
            and all(f["published_on"] is None or f["published_on"] >= year_ago for f in r["facts"] if f["section"] == "news"))


def _pack_ok(r: dict) -> bool:
    return (bool(r["talking_points"]) and 110 <= len(r["pitch"].split()) <= 260 and len(r["likely_questions"]) >= 5
            and all(q["story_id"] in (None, "story-1", "story-2") for q in r["likely_questions"]) and len(r["questions_to_ask"]) >= 3)


ABOUT_ME = ("I am an MSc Data Science student with two years in logistics analytics. "
            "I build SQL and Power BI reports that managers use to make decisions.")
OUTREACH = [  # (kind, how the user knows them, what else the user gives)
    ("connection_note", "none", {}),
    ("chat_request", "alumni", {"university": "University of Leeds"}),
    ("follow_up", "none", {}),
    ("thank_you", "event", {"event_name": "Leeds Data Meetup", "learned": "how her team checks every report against last week before it goes out"}),
    ("referral_ask", "alumni", {"university": "University of Leeds", "job": {"title": "Junior Data Analyst", "company": "Northwind Goods",
                                                                              "summary": "Reporting role.", "url": "https://www.reed.co.uk/jobs/1"},
                                "achievements": [a["uk_version"] for a in ACHIEVEMENTS]}),
    ("recruiter_intro", "recruiter", {"start": "from 2 November", "looking_for": ["Data Analyst"]}),
    ("reference_ask", "tutor", {"looking_for": ["Data Analyst"]}),
]


def _outreach(kind: str, relationship: str, **extra) -> dict:
    contact = {"name": "Dr Priya Shah", "role": "Senior Data Analyst", "company": "Northwind Goods", "relationship": relationship}
    return ai.outreach_draft(kind=kind, contact=contact, sender="Sample Candidate", about_me=ABOUT_ME, **extra)


def _outreach_ok(r: dict) -> bool:
    if os.environ.get("SHOW_DRAFTS"):
        print(r["message"], end="\n\n")
    note = r["message"].endswith("\nSample")  # a connection note signs with the first name only
    return bool(r["message"]) and r["characters"] == len(r["message"]) <= (ai.NOTE_CHARS if note else 2000)


CHECKS = [
    ("achievements", lambda: ai.extract_achievements(BACKGROUND, PROFILE), lambda r: len(r["items"]) >= 1),
    # "You said" quotes must survive the check against the text, or the proof-of-hearing feature shows nothing
    ("achievement quotes", lambda: ai.extract_achievements(BACKGROUND, PROFILE), lambda r: sum(bool(i["raw"]) for i in r["items"]) >= 1),
    ("interview quotes", lambda: ai.interview_feedback(INTERVIEW, JOB, PROFILE, "Behavioural round"),
     lambda r: any(p["you_said"] for p in r["strengths"] + r["fixes"])),
    ("families", lambda: ai.suggest_families(ACHIEVEMENTS, PROFILE), lambda r: len(r["families"]) >= 2),
    ("job summary", lambda: ai.summarise_job("Data Analyst", "a UK retailer", DESCRIPTION, ["Data Analyst", "BI Analyst"]), lambda r: bool(r["summary"])),
    ("star", lambda: ai.star(ACHIEVEMENTS[0]), lambda r: bool(r["action"])),
    # step 3: the model writes wording only; ids, numbers and skills are checked against what it was given
    ("cv body, tailored", lambda: ai.build_cv(CV_WHOLE_PROFILE, CV_COURSES, CV_JOBS, CV_ACHIEVEMENTS, CV_SKILLS, JOB), _body_ok),
    ("cv body, base", lambda: ai.build_cv(CV_WHOLE_PROFILE, CV_COURSES, CV_JOBS, CV_ACHIEVEMENTS, CV_SKILLS), _body_ok),
    ("cover letter", lambda: ai.job_letter(JOB, CV_WHOLE_PROFILE, CV_COURSES, CV_JOBS, CV_ACHIEVEMENTS), _letter_ok),
    # what one build costs the user in waiting: both calls side by side, assembled and counted as a PDF
    ("cv build, whole", _whole_build, _build_ok),
    ("interview feedback", lambda: ai.interview_feedback(INTERVIEW, JOB, PROFILE, "Behavioural round"), lambda r: bool(r["summary"])),
    ("tone decode", lambda: ai.tone("Not bad at all.", "decode"), lambda r: bool(r["meaning"])),
    ("tone rewrite", lambda: ai.tone("I am the best candidate you will ever meet.", "rewrite"), lambda r: bool(r["rewrite"])),
    ("diagnosis", lambda: ai.explain_diagnosis([], STATS, PROFILE), lambda r: bool(r["headline"])),
    # the matching advert must be credited to a real achievement, and score above the unrelated one
    ("job fit", lambda: ai.score_jobs(ADVERTS, ACHIEVEMENTS),
     lambda r: set(r) == {1, 2} and all(r.values()) and any(x["shown_by"] in TITLES for x in r[1]) and _percent(r[1]) > _percent(r[2])),
    ("job fit, 8 adverts", lambda: ai.score_jobs(FULL_BATCH, ACHIEVEMENTS), lambda r: len(r) == 8 and all(r.values())),
    # step 1: a jumbled two-column CV must still give achievements with real quotes and the place each happened
    ("cv achievements", lambda: ai.extract_achievements(CV, CV_PROFILE, "cv"),
     lambda r: len(r["items"]) >= 3 and sum(bool(i["raw"]) for i in r["items"]) >= 3 and sum(bool(i["where"]) for i in r["items"]) >= 2),
    # months only where the CV gives them; a year alone must come back empty, never as a guessed month
    ("cv facts", lambda: ai.extract_facts(CV, CV_PROFILE, "cv"), _facts_ok),
    # what one upload costs the user in waiting: both calls side by side, and achievements tied to the jobs found
    ("cv import, both at once", _both_at_once, lambda r: r["facts"] is not None and sum(bool(i["proposal"]) for i in r["placed"]) >= 2),
    ("cv again adds nothing", _import_twice, lambda n: n <= 1),
    ("github projects", lambda: ai.github_achievements(REPOS), lambda r: set(r) == {1, 2} and all(i["raw"] for i in r.values())),
    ("improve with a number", lambda: ai.improve(NO_NUMBER, "about 15 depot managers used it every week"), lambda r: "15" in r["uk_version"]),
    ("improve adds no number", lambda: ai.improve(NO_NUMBER, "make it read better"), lambda r: not _digits(r["uk_version"])),
    ("story bank of four", lambda: ai.story_bank(FOUR), lambda r: set(r) == {1, 2, 3, 4} and len({s["competency"] for s in r.values()}) >= 2),
    # step 4: a lesson worded as a possibility that never claims feedback nobody gave; a follow-up with only the details given
    ("lesson, with feedback", lambda: ai.rejection_lesson(job=JOB, cv_text=LESSON_CV, ended_at="interview",
                                                          feedback="We went with someone with more stakeholder experience."), _lesson_ok),
    ("lesson, no feedback", lambda: ai.rejection_lesson(job=JOB, cv_text=LESSON_CV, ended_at="cv", feedback=""), _lesson_ok),
    ("lesson, no advert", lambda: ai.rejection_lesson(job=None, cv_text=LESSON_CV, ended_at="screening", feedback=""), _lesson_ok),
    ("follow-up draft", lambda: ai.follow_up(role=JOB["title"], company=JOB["company"], applied_on=date.today() - timedelta(days=7),
                                             contact_name="Priya Shah", sender="Sample Candidate"), _draft_ok),
    # step 5: every statement cites a passage it is checked against; old news is never kept; the pack points only at the user's stories
    ("company brief", lambda: ai.company_brief("Northwind Goods", PASSAGES, TODAY), _brief_ok),
    ("company research, real", _real_research, _real_ok),
    ("prep pack", lambda: ai.prep_pack(job=JOB, brief=FACTS, achievements=ACHIEVEMENTS, stories=STORIES, profile=PROFILE), _pack_ok),
    ("tag stories", lambda: ai.tag_stories(STORIES), lambda r: set(r) <= {"story-1", "story-2"} and len(r) >= 1),
    ("star competencies", lambda: ai.star(ACHIEVEMENTS[0]), lambda r: len(r["competencies"]) >= 1),
    # step 6: seven kinds of message, each within its limit and claiming no connection that was not entered; event preparation
    *[(f"draft, {kind}", lambda kind=kind, who=who, extra=extra: _outreach(kind, who, **extra), _outreach_ok) for kind, who, extra in OUTREACH],
    ("event preparation", lambda: ai.event_prep(event={"name": "Leeds Data Meetup", "type": "meetup", "online": False}, about_me=ABOUT_ME),
     lambda r: len(r["openers"]) == 3 and 30 <= len(r["introduction"].split()) <= 90 and bool(r["goal"])),
    # step 7: a broad field for buddy matching, from the user's target role names only
    ("peers field, data", lambda: ai.suggest_field(["Data Analyst", "Business Intelligence Analyst"]), lambda r: r == "data"),
    ("peers field, law", lambda: ai.suggest_field(["Trainee Solicitor", "Paralegal"]), lambda r: r == "law"),
]


def main() -> int:
    failed, wanted = 0, [w.lower() for w in sys.argv[1:]]
    for name, call, ok in CHECKS:
        if wanted and not any(w in name for w in wanted):
            continue
        started = time.time()
        try:
            outcome = "PASS" if ok(call()) else "FAIL (empty result)"
        except Exception as e:  # report the kind of failure only
            outcome = f"FAIL ({type(e).__name__})"
        failed += outcome != "PASS"
        print(f"{name:<20} {outcome:<28} {time.time() - started:5.1f}s", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
