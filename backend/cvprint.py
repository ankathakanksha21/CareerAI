"""A CV or a cover letter as the list of blocks that is printed, top to bottom. The Word writer
and the PDF writer both draw exactly this list, so the two files always say the same thing in
the same order. Also the layout both writers share, and the name a file is saved under.

A block is (kind, text), or ("entry", left, right) for a line with its dates at the right margin:
  name     the candidate's name            heading  a section heading
  contact  the contact line                entry    an employer, institution or project
  sub      a job title or a qualification  line     one plain line
  para     a paragraph                     bullet   one bullet
  gap      a blank line (letters only)"""
import re
import unicodedata
from datetime import date

import cv

# The page both writers draw: A4, one column, Arial in Word and Liberation Sans (the same widths) in the PDF
PAGE_MM = (210, 297)
MARGIN_X_MM, MARGIN_Y_MM = 18, 16
BODY_PT, NAME_PT, HEADING_PT = 10.5, 16, 11.5
LINE_HEIGHT = 1.15                      # Arial's own line height, as a share of the type size
HEADING_BEFORE_PT, HEADING_AFTER_PT = 8, 3
ENTRY_BEFORE_PT, PARA_AFTER_PT = 5, 5
BULLET_INDENT_PT = 18                   # where a bullet's text starts; the bullet itself hangs to the left of it

PROFILE_HEADING = "Personal profile"
HEADINGS = {"education": "Education", "work": "Work experience", "projects": "Projects", "skills": "Skills",
            "additional": "Additional information"}
SKILL_LABELS = (("technical", "Technical"), ("tools", "Tools"), ("languages", "Languages"))
SHORT_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
HOME = {"united kingdom", "uk", "u.k.", "great britain", "gb", "england", "scotland", "wales", "northern ireland"}
PART_LABEL = {"cv": "CV", "letter": "Cover-Letter"}
PART_TITLE = {"cv": "CV", "letter": "cover letter"}
# letters that do not come apart into a plain letter and an accent
PLAIN = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
                       "ı": "i", "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D"})
MAX_NAME_CHARS = 120


def clean(text) -> str:
    """Text as both files can hold it: accents joined to their letters, and line breaks, tabs and
    control characters (which a Word file refuses outright) turned into single spaces."""
    text = unicodedata.normalize("NFC", text if isinstance(text, str) else "")
    kept = (" " if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch for ch in text
            if unicodedata.category(ch) != "Cs" and ch not in "￾￿")  # half a character, or not a character at all
    return " ".join("".join(kept).split())


def month(value) -> str:
    day = cv.as_date(value)
    return f"{SHORT_MONTHS[day.month - 1]} {day.year}" if day else ""


def period(entry: dict, lone_end: str = "Until {}") -> str:
    """When a job or course ran: "Jul 2023 to Aug 2025", "Jul 2023 to present", or nothing when no
    dates were given. A course with only the month it ends shows that month."""
    start, end = month(entry.get("start_month")), "present" if entry.get("is_current") else month(entry.get("end_month"))
    if start:
        return f"{start} to {end}" if end else f"From {start}"
    return "Current" if entry.get("is_current") else lone_end.format(end) if end else ""


def contact_line(contact: dict) -> str:
    return " | ".join(x for x in (clean(contact.get(k)) for k in ("city", "phone", "email", "linkedin", "github")) if x)


def _shown(items) -> list[dict]:
    return [x for x in items or [] if isinstance(x, dict) and not x.get("hidden")]


def _joined(*parts, sep: str = ", ") -> str:
    return sep.join(x for x in (clean(p) for p in parts) if x)


def _bullets(entry: dict) -> list[tuple]:
    return [("bullet", text) for b in _shown(entry.get("bullets")) if (text := clean(b.get("text")))]


def _education(content: dict) -> list[tuple]:
    out = []
    for course in _shown(content.get("education")):
        abroad = clean(course.get("country")).lower() not in HOME
        out.append(("entry", _joined(course.get("institution"), course.get("country") if abroad else ""), period(course, "{}")))
        out += [("sub", text)] if (text := _joined(course.get("qualification"), course.get("subject"), sep=" ")) else []
        out += [("line", f"Grade: {text}")] if (text := clean(course.get("grade"))) else []
        out += [("line", text)] if (text := clean(course.get("note"))) else []
    return out


def _work(content: dict) -> list[tuple]:
    out = []
    for job in _shown(content.get("work")):
        out.append(("entry", _joined(job.get("employer"), job.get("location"), job.get("country")), period(job)))
        out += [("sub", text)] if (text := clean(job.get("job_title"))) else []
        out += [("line", text)] if (text := clean(job.get("employer_context"))) else []
        out += _bullets(job)
    return out


def _projects(content: dict) -> list[tuple]:
    out = []
    for project in _shown(content.get("projects")):
        bullets = _bullets(project)
        if bullets:  # a project is its bullets: with none showing there is nothing to say about it
            title, link = _joined(project.get("title"), project.get("where")), clean(project.get("link"))
            out += [("entry", f"{title} ({link})" if title and link else title or link, ""), *bullets]
    return out


def _skills(content: dict) -> list[tuple]:
    skills = content.get("skills") or {}
    return [("line", f"{label}: {listed}") for group, label in SKILL_LABELS if (listed := _joined(*(skills.get(group) or [])))]


def _additional(content: dict) -> list[tuple]:
    lines = [clean(line.get("text")) for line in _shown((content.get("additional") or {}).get("lines"))]
    visa = content.get("right_to_work") or {}
    return [("line", text) for text in [*lines, clean(visa.get("text")) if visa.get("shown") else ""] if text]


_SECTIONS = {"education": _education, "work": _work, "projects": _projects, "skills": _skills, "additional": _additional}


def _top(content: dict) -> list[tuple]:
    contact = content.get("contact") or {}
    return [(kind, text) for kind, text in (("name", clean(contact.get("name"))), ("contact", contact_line(contact))) if text]


def blocks(content: dict) -> list[tuple]:
    """The CV, in print order. A section with nothing to show prints nothing, not even its heading."""
    out = _top(content)
    if profile := clean(content.get("profile")):
        out += [("heading", PROFILE_HEADING), ("para", profile)]
    order = [s for s in content.get("section_order") or [] if s in _SECTIONS]
    for section in [*order, *(s for s in cv.SECTIONS if s not in order)]:
        body = _SECTIONS[section](content)
        if body:
            out += [("heading", HEADINGS[section]), *body]
    return out


def letter_blocks(content: dict, contact_name: str, today: date) -> list[tuple]:
    """The cover letter in UK letter form. To a named person it ends "Yours sincerely"; to
    "Hiring Manager", "Yours faithfully"."""
    letter, job, to = content.get("cover_letter") or {}, content.get("job") or {}, clean(contact_name)
    name = clean((content.get("contact") or {}).get("name"))
    out = [*_top(content), ("gap", ""), ("line", cv.long_date(today)), ("gap", ""), ("line", to or "Hiring Manager")]
    out += [("line", company)] if (company := clean(job.get("company"))) else []
    out += [("gap", ""), ("line", f"Dear {to or 'Hiring Manager'},"), ("gap", "")]
    out += [("para", text) for k in cv.LETTER_PARTS if (text := clean(letter.get(k)))]
    out += [("line", "Yours sincerely," if to else "Yours faithfully,"), ("gap", "")]
    return out + ([("line", name)] if name else [])


def _plain(text) -> str:
    """Words in plain ASCII joined by hyphens, as a file name an employer's upload form will accept."""
    folded = unicodedata.normalize("NFKD", clean(text).translate(PLAIN)).encode("ascii", "ignore").decode()
    return "-".join(re.findall(r"[A-Za-z0-9]+", folded))


def file_name(content: dict, part: str, extension: str) -> str:
    """Firstname-Lastname-CV-Company.docx; a base CV has no company."""
    contact, job = content.get("contact") or {}, content.get("job") or {}
    stem = "-".join(x for x in (_plain(contact.get("name")), PART_LABEL[part], _plain(job.get("company"))) if x)
    return f"{stem[:MAX_NAME_CHARS].rstrip('-')}.{extension}"


def title(content: dict, part: str) -> str:
    """What the file calls itself in its own properties."""
    return _joined((content.get("contact") or {}).get("name"), PART_TITLE[part], sep=" ")
