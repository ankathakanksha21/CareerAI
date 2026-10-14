"""A complete CV document (format 2) and helpers for reading generated files back. The person,
employers and universities cannot be real, and nothing here touches the disk."""
import copy
import io

PROFILE_TEXT = ("MSc Data Science student with two years as a data analyst in logistics. Built reporting used by 15 depot managers "
                "and saved £120,000 a year.")
CONTENT = {
    "contact": {"name": "Zarvin Quillfeather", "city": "Zzqxtown", "phone": "07700 900123", "email": "zarvin@example.test",
                "linkedin": "linkedin.com/in/zarvin-q", "github": "github.com/zarvin-q"},
    "job": {"title": "Junior Analyst", "company": "Zzqx Retail plc"},
    "profile": PROFILE_TEXT,
    "section_order": ["education", "work", "projects", "skills", "additional"],
    "education": [
        {"education_id": "c1", "institution": "Zzqx City University", "qualification": "MSc", "subject": "Data Science",
         "start_month": "2025-09-01", "end_month": "2026-09-01", "grade": "Merit", "country": "United Kingdom",
         "note": "Dissertation on bus arrival times", "hidden": False},
        {"education_id": "c2", "institution": "University of Zzqx", "qualification": "BTech", "subject": "Computer Science",
         "start_month": None, "end_month": "2023-05-01", "grade": "CGPA 8.4/10", "country": "India", "note": "", "hidden": False}],
    "work": [
        {"work_history_id": "j1", "employer": "Zzqx Holdings Ltd", "job_title": "Data Analyst", "location": "Pune", "country": "India",
         "start_month": "2023-07-01", "end_month": "2025-08-01", "is_current": False, "employer_context": "A logistics company with 40 depots.",
         "hidden": False,
         "bullets": [{"text": "Built a weekly delays report in SQL used by 15 depot managers", "achievement_id": "a1", "hidden": False},
                     {"text": "Automated a three-spreadsheet merge in Python, saving 5 hours a week", "achievement_id": "a2", "hidden": False}]},
        {"work_history_id": "j2", "employer": "Zzqx Foods", "job_title": "Intern", "location": "", "country": "", "start_month": None,
         "end_month": None, "is_current": False, "employer_context": "", "hidden": False, "bullets": []}],
    "projects": [{"achievement_id": "a3", "title": "Bus arrival predictor", "link": "github.com/zarvin-q/bus-times", "where": "", "hidden": False,
                  "bullets": [{"text": "Built a model predicting arrivals within 90 seconds for 12 routes", "achievement_id": "a3", "hidden": False}]}],
    "skills": {"technical": ["SQL", "Python"], "tools": ["Power BI", "Excel"], "languages": ["English (Fluent)", "Hindi (Native)"]},
    "additional": {"lines": [{"text": "Zzqx Cloud Practitioner (2025)", "hidden": False}]},
    "right_to_work": {"shown": False, "text": "Visa status: Student visa, valid until 30 January 2027."},
    "cover_letter": {"why_them": "Your depot network is growing and needs clear reporting.", "why_you": "I built a report used by 15 managers.",
                     "what_you_deliver": "A weekly findings report in my first month."},
    "keywords": {"terms": [], "covered": [], "available": [], "missing": []},
    "gaps": [],
}
# CONTENT exactly as it should print
BLOCKS = [
    ("name", "Zarvin Quillfeather"),
    ("contact", "Zzqxtown | 07700 900123 | zarvin@example.test | linkedin.com/in/zarvin-q | github.com/zarvin-q"),
    ("heading", "Personal profile"), ("para", PROFILE_TEXT),
    ("heading", "Education"),
    ("entry", "Zzqx City University", "Sep 2025 to Sep 2026"), ("sub", "MSc Data Science"), ("line", "Grade: Merit"),
    ("line", "Dissertation on bus arrival times"),
    ("entry", "University of Zzqx, India", "May 2023"), ("sub", "BTech Computer Science"), ("line", "Grade: CGPA 8.4/10"),
    ("heading", "Work experience"),
    ("entry", "Zzqx Holdings Ltd, Pune, India", "Jul 2023 to Aug 2025"), ("sub", "Data Analyst"), ("line", "A logistics company with 40 depots."),
    ("bullet", "Built a weekly delays report in SQL used by 15 depot managers"),
    ("bullet", "Automated a three-spreadsheet merge in Python, saving 5 hours a week"),
    ("entry", "Zzqx Foods", ""), ("sub", "Intern"),
    ("heading", "Projects"),
    ("entry", "Bus arrival predictor (github.com/zarvin-q/bus-times)", ""),
    ("bullet", "Built a model predicting arrivals within 90 seconds for 12 routes"),
    ("heading", "Skills"),
    ("line", "Technical: SQL, Python"), ("line", "Tools: Power BI, Excel"), ("line", "Languages: English (Fluent), Hindi (Native)"),
    ("heading", "Additional information"), ("line", "Zzqx Cloud Practitioner (2025)"),
]


def content(**changes) -> dict:
    """A fresh copy of the sample CV with whole top-level parts replaced."""
    return copy.deepcopy(CONTENT) | changes


def pieces(blocks: list[tuple]) -> list[str]:
    """Every piece of text the blocks print, in order."""
    return [text for block in blocks for text in block[1:] if text]


def squash(text: str) -> str:
    return " ".join(text.split())


def missing_or_out_of_order(wanted: list[str], text: str) -> list[str]:
    """The pieces that are not found in the text after the piece before them."""
    text, at, bad = squash(text), 0, []
    for piece in wanted:
        found = text.find(squash(piece), at)
        if found < 0:
            bad.append(piece)
        else:
            at = found + len(squash(piece))
    return bad


def pdf_pages(data: bytes) -> list[str]:
    """The text of each page of a PDF, as a text extractor reads it."""
    from pypdf import PdfReader
    return [page.extract_text() for page in PdfReader(io.BytesIO(data)).pages]


def pdf_text(data: bytes) -> str:
    return squash(" ".join(pdf_pages(data)))


def word(data: bytes):
    from docx import Document
    return Document(io.BytesIO(data))


def word_text(data: bytes) -> str:
    return squash(" ".join(p.text.replace("\t", " ") for p in word(data).paragraphs))
