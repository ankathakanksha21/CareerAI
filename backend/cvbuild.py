"""One CV from start to finish: the model calls a build takes, an edit applied, the page count,
and the file a version downloads as. It ties together cv (the document), ai (the wording),
cvprint (what is printed) and the two writers.

No database here: the routes read the user's records first and save what comes back. Files are
made in memory and returned; nothing is kept."""
from datetime import date

import ai
import cv
import cvpdf
import cvprint
import cvword
from parallel import together

MEDIA = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "pdf": "application/pdf"}


def _about(content: dict, part: str) -> dict:
    return {"title": cvprint.title(content, part), "author": (content.get("contact") or {}).get("name") or ""}


def pages(content: dict) -> int:
    """How many pages the CV runs to: counted from the PDF it prints as, never estimated."""
    return cvpdf.render(cvprint.blocks(content), **_about(content, "cv"))[1]


def build(*, profile: dict, email: str, education: list, work_history: list, achievements: list, job: dict | None, today: date) -> tuple[dict, int]:
    """A new CV and its page count. For a job, the body and the letter are written side by side,
    which halves the wait; if either call fails the build fails and there is nothing to save."""
    skills = cv.own_skills(profile, achievements)
    tasks = [lambda: ai.build_cv(profile, education, work_history, achievements, skills, job, today)]
    if job:
        tasks.append(lambda: ai.job_letter(job, profile, education, work_history, achievements))
    written = {}
    for part in together(lambda task: task(), tasks):
        written |= part
    content = cv.assemble(profile=profile, email=email, education=education, work_history=work_history, achievements=achievements,
                          written=written, job=job, today=today)
    return content, pages(content)


def revise(stored: dict, edited: dict, *, profile: dict, email: str, education: list, work_history: list, achievements: list,
           refresh: bool = False) -> tuple[dict, int]:
    """A stored CV with the user's edit applied, and its new page count."""
    content = cv.merge(stored, edited, profile=profile, email=email, education=education, work_history=work_history,
                       achievements=achievements, refresh=refresh)
    return content, pages(content)


def _blocks(content: dict, contact_name: str, part: str, today: date) -> list[tuple]:
    return cvprint.blocks(content) if part == "cv" else cvprint.letter_blocks(content, contact_name, today)


def file(content: dict, contact_name: str, part: str, extension: str, today: date) -> tuple[bytes, str]:
    """The CV ("cv") or its cover letter ("letter") as a Word or PDF file, and the name to save it under."""
    blocks = _blocks(content, contact_name, part, today)
    data = cvword.render(blocks, **_about(content, part)) if extension == "docx" else cvpdf.render(blocks, **_about(content, part))[0]
    return data, cvprint.file_name(content, part, extension)


def unsupported(content: dict, contact_name: str = "") -> str:
    """The characters in the CV and its letter that a PDF cannot show, for the page to name before a download."""
    printed = _blocks(content, contact_name, "cv", date.today())
    if content.get("cover_letter"):
        printed = printed + _blocks(content, contact_name, "letter", date.today())
    return cvpdf.unsupported(" ".join(text for block in printed for text in block[1:]))
