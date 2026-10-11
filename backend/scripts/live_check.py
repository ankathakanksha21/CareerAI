"""One real call to the configured model for each AI task, to prove the prompts and parsing
work end to end. Uses real credits. Prints a line per task; never prints prompts, replies or keys.

Run from backend/ with the venv active:  python scripts/live_check.py"""
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai  # noqa: E402

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

CHECKS = [
    ("achievements", lambda: ai.extract_achievements(BACKGROUND, PROFILE), lambda r: len(r["items"]) >= 1),
    ("families", lambda: ai.suggest_families(ACHIEVEMENTS, PROFILE), lambda r: len(r["families"]) >= 2),
    ("job summary", lambda: ai.summarise_job("Data Analyst", "a UK retailer", DESCRIPTION, ["Data Analyst", "BI Analyst"]), lambda r: bool(r["summary"])),
    ("tailor", lambda: ai.tailor(JOB, ACHIEVEMENTS, PROFILE), lambda r: len(r["bullets"]) >= 1 and bool(r["cover_letter"]["why_them"])),
    ("star", lambda: ai.star(ACHIEVEMENTS[0]), lambda r: bool(r["action"])),
    ("interview feedback", lambda: ai.interview_feedback(INTERVIEW, JOB, PROFILE, "Behavioural round"), lambda r: bool(r["summary"])),
    ("tone decode", lambda: ai.tone("Not bad at all.", "decode"), lambda r: bool(r["meaning"])),
    ("tone rewrite", lambda: ai.tone("I am the best candidate you will ever meet.", "rewrite"), lambda r: bool(r["rewrite"])),
    ("diagnosis", lambda: ai.explain_diagnosis([], STATS, PROFILE), lambda r: bool(r["headline"])),
]


def main() -> int:
    failed = 0
    for name, call, ok in CHECKS:
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
