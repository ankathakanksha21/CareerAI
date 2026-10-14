"""Does the page count shown in the app match what Word makes of the same CV?

The app counts the pages of the PDF it generates. This makes sample CVs of growing length, saves
each as a Word file in a folder you name, asks Word itself how many pages each takes, and prints
the two counts side by side. The PDF must never say fewer pages than Word: a CV the app calls two
pages has to be two pages when the Word file is opened.

Windows with Microsoft Word only. The samples are made up; nothing is sent anywhere.

Run from backend/ with the venv active:  python scripts/page_check.py C:\\some\\empty\\folder"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cvpdf  # noqa: E402
import cvprint  # noqa: E402
import cvword  # noqa: E402

WHO = {"title": "Sample Candidate CV", "author": "Sample Candidate"}
SHORT = "Built a weekly delivery delays report in SQL and Excel for 15 depot managers."
LONG = ("Automated the monthly reconciliation of three regional spreadsheets in Python, cutting the time it took from five hours to "
        "twenty minutes and removing the copying errors that had delayed two board reports.")
WORD_PAGES = r"""
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  foreach ($file in Get-ChildItem -LiteralPath $args[0] -Filter 'sample-*.docx' | Sort-Object Name) {
    $doc = $word.Documents.Open($file.FullName, $false, $true)
    Write-Output ("{0} {1}" -f $file.BaseName, $doc.ComputeStatistics(2))
    $doc.Close($false)
  }
} finally { $word.Quit() }
"""


PER_JOB = 4
SAMPLES = range(4, 64)  # bullets in the CV: from under a page to four pages, a line or two at a time


def sample(count: int) -> dict:
    """A CV with this many bullets, one-line and two-line in turn, four to a job."""
    bullets = [{"text": LONG if n % 2 else SHORT, "achievement_id": "", "hidden": False} for n in range(count)]
    jobs = [bullets[at:at + PER_JOB] for at in range(0, count, PER_JOB)]
    return {
        "contact": {"name": "Sample Candidate", "city": "Leeds", "phone": "07700 900123", "email": "sample.candidate@example.test",
                    "linkedin": "linkedin.com/in/sample-candidate", "github": "github.com/sample-candidate"},
        "profile": ("MSc Data Science student with two years as a data analyst in logistics. Built reporting used by 15 depot managers and "
                    "automated a reconciliation that saved five hours a month. Looking for a graduate analyst role in operations."),
        "section_order": ["education", "work", "projects", "skills", "additional"],
        "education": [{"institution": "Sample City University", "qualification": "MSc", "subject": "Data Science", "start_month": "2025-09-01",
                       "end_month": "2026-09-01", "grade": "Merit", "country": "United Kingdom", "note": "Dissertation on bus arrival times"},
                      {"institution": "University of Sample", "qualification": "BTech", "subject": "Computer Science", "end_month": "2023-05-01",
                       "grade": "CGPA 8.4/10", "country": "India"}],
        "work": [{"employer": f"Sample Holdings {n + 1} Ltd", "job_title": "Data Analyst", "location": "Pune", "country": "India",
                  "start_month": "2023-07-01", "end_month": "2025-08-01", "employer_context": "A logistics company with 40 depots across India.",
                  "bullets": held} for n, held in enumerate(jobs)],
        "projects": [{"title": "Bus arrival predictor", "link": "github.com/sample-candidate/bus-times", "bullets": bullets[:1]}],
        "skills": {"technical": ["SQL", "Python", "Statistics"], "tools": ["Power BI", "Excel", "Git"], "languages": ["English (Fluent)", "Hindi (Native)"]},
        "additional": {"lines": [{"text": "Sample Cloud Practitioner (2025)"}]},
        "right_to_work": {"shown": True, "text": "Visa status: Student visa, valid until 30 January 2027."},
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    in_pdf = {}
    for count in SAMPLES:
        blocks = cvprint.blocks(sample(count))
        (folder / f"sample-{count:02d}.docx").write_bytes(cvword.render(blocks, **WHO))
        in_pdf[f"sample-{count:02d}"] = cvpdf.render(blocks, **WHO)[1]
    asked = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", f"& {{{WORD_PAGES}}} '{folder}'"],
                           capture_output=True, text=True, timeout=600)
    in_word = {name: int(pages) for name, pages in (line.split() for line in asked.stdout.splitlines() if line.strip())}
    if len(in_word) != len(in_pdf):
        print(f"Word answered for {len(in_word)} of {len(in_pdf)} files. Is Microsoft Word installed?\n{asked.stderr.strip()[:300]}")
        return 1
    short = 0
    print("sample      PDF  Word")
    for name, pages in in_pdf.items():
        short += pages < in_word[name]
        if pages != in_word[name]:  # only the samples that differ are listed
            print(f"{name}  {pages:>3}  {in_word[name]:>4}  {'PDF says fewer: fix the spacing' if pages < in_word[name] else 'PDF one over (safe)'}")
    print(f"\n{sum(pages == in_word[name] for name, pages in in_pdf.items())} of {len(in_pdf)} the same; {short} where the PDF says fewer pages than Word.")
    return 1 if short else 0


if __name__ == "__main__":
    sys.exit(main())
