# Step 3: The Full UK CV Implementation Plan

> **For agentic workers:** follow `careerai-building-a-step` stage 4. Every task is test-first: write the tests, watch them fail for the right reason, write the code, watch them pass, run the whole suite on its own, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For a saved job, or for no job at all, the app builds a complete two-page UK CV (and, for a job, a cover letter) from the user's stored records, lets them edit it on screen, and downloads it as Word and PDF. Every fact in it is copied from their profile, and the tracker knows exactly which wording was sent.

**Architecture:** A CV is one JSON document (`cv_versions.content`, format 2). Its facts (employers, titles, dates, institutions, grades, contact details) are copied from the stored records by code; the model only writes the profile paragraph, picks and rewords bullets by achievement id, and groups skills. One neutral list of print blocks (`cvprint.py`) is drawn by two writers, `cvword.py` and `cvpdf.py`, so the two files always say the same thing in the same order. Files are made in memory when downloaded and never stored. The page count is the number of pages of the generated PDF.

**Tech stack:** unchanged, plus two Python packages, `python-docx` (Word) and `fpdf2` (PDF), and two font files, Liberation Sans Regular and Bold.

**Step document:** `.claude/skills/careerai-step-3-full-uk-cv/SKILL.md`. Where this plan differs from it, the difference is listed under "Decisions this plan adds" for the owner to approve.

## Global constraints

- Everything in `CLAUDE.md` applies. The points that bite hardest here:
- **Facts are never written by the AI.** Whatever the model returns, an employer, job title, date, institution, qualification or grade on a CV equals the stored record. The same goes for contact details, which the model is never sent.
- **Only real data.** No sample CV in the product. Test fixtures use names that cannot be real ("Zzqx Holdings Ltd", "University of Zzqx").
- **Real result or an error.** A failed build saves nothing and shows Retry. Nothing is cut from a CV silently: the page says how many pages it runs to and what could be trimmed.
- **Nothing is written to disk.** A CV or letter file is built in memory for one download and dropped.
- **Every new route** gets a test that it answers 401 without a token, 422 for a malformed id and 404 for another user's id.
- **A sent version never changes.** Editing a version an application points at saves a new version.
- **No database connection across a model call.** Building a file is not an outside call, but it is done between two short transactions all the same.
- **All SQL stays in `repo.py`.** `cv.py` and `cvprint.py` are pure functions; `cvword.py` and `cvpdf.py` only draw.
- British English, no em dashes in UI copy or prompts.
- Commit after every task with the suite passing. Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push unless asked.

## What the checks before building found (13 October 2026)

| Checked | Result |
|---|---|
| Step 1 | Merged into `main` (pull request 7). Baseline on this branch: 907 backend tests pass, the frontend lints and builds |
| `fpdf2` 2.8.9 | A two-page test CV in 0.15 seconds. Read back with `pypdf`, every piece of text came out whole and in the order it was written, including "Nguyễn", "Çağla", "Łukasz", Greek, Cyrillic and a pound sign. It reports which characters its font cannot draw. Licence LGPL 3.0, used unchanged as a library. Chosen over `reportlab` because its drawing calls mirror `python-docx`'s, so one list of blocks drives both files |
| `python-docx` 1.2.0 | **Not already installed**: the step document says step 1 added it, but step 1 reads Word files with the standard library. It is a new package. A test file read back with real bullet lists, a heading style, no tables and nothing in the header or footer. Its default page is US Letter and its default author is "python-docx"; both are set explicitly |
| Font | Liberation Sans 2.1.5, downloaded with the owner's permission from the Liberation Fonts project's GitHub release (`liberation-fonts-ttf-2.1.5.tar.gz`, 2.4 MB; Regular 411 KB, Bold 414 KB). SIL Open Font Licence 1.1, which allows bundling with software if the licence travels with it. Every character below U+0250 has exactly Arial's width, and the line height is the same, so Word (Arial) and the PDF break lines alike. Covers Latin with every accent tested, Vietnamese, Greek and Cyrillic. **Does not cover** the rupee sign, Arabic, Hindi, Chinese, Japanese, Korean or Thai |
| Page count | Counted from the generated PDF. Against Word itself (through Word on this machine) on 11 test CVs of growing length: the same count on 10; on the one sitting at a page boundary Word said 3 and the PDF said 2. So the PDF's spacing is set slightly looser than Word's and checked again in task 5 |
| Vercel | Python functions may be 500 MB unpacked (docs updated 24 August 2026). The app is about 140 MB today; the two packages add about 50 MB. A response may be 4.5 MB; a CV file is about 60 KB |
| Step 2 | Shipped, so a tailored CV works from a pasted job and from a job saved from a listing. A job saved from a listing has no keyword list, which is one reason keywords are worked out afresh at build time |
| Right-to-work conventions | University careers services (Manchester, Nottingham, Bath) advise one short line giving the visa and its end date; Manchester adds "any relevant work restrictions". gov.uk says a Graduate visa holder can "work in most jobs" |

## Settled with the owner today

| Question | Answer |
|---|---|
| Suggested right-to-work wording | Graduate visa: "Right to work in the UK: Graduate visa, valid until 14 March 2028." Student visa: "Visa status: Student visa, valid until 30 January 2027." No hour figures, no word on future eligibility. Off by default; the user can edit it |
| Achievements linked to no job or course | They go under Projects, beside GitHub projects and course projects. The page says how many are unlinked and links to Profile |
| Certifications, awards and volunteering | A new box on the Profile, one per line, used by every CV. A line can be hidden on one CV. One new column, `profiles.additional` |
| PDF font and other scripts | Bundle Liberation Sans. If a CV has characters it cannot draw, the page names them and points to the Word file |

## Decisions this plan adds (for the owner to approve with the plan)

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| 1 | `python-docx` is added as a new package | The step document assumed it was there | About 13 MB more on the server |
| 2 | Facts on a CV cannot be typed over on the CV. They are corrected on the Profile, and a CV that has not been sent offers **Update from profile** | The step document says "clicking any text edits it". If an employer or a date could be retyped on one CV, the profile and the CV would disagree and "every fact equals the stored record" would stop being true. Wording, order and what is shown stay fully editable | Fixing a typo in an employer's name takes two clicks more |
| 3 | Each edit is saved as it is made; there is no Save button. Editing a version already attached to an application switches the page to the new version and says so | Nothing is lost by leaving the page, and downloads always match the screen | More requests; each is small |
| 4 | Building a tailored CV is **two model calls side by side** (the CV body; then keywords, gaps and the letter), one AI action. If either fails nothing is saved | One call would write about 1,100 words' worth, roughly 25 seconds. Two take about 15 | The letter is written without seeing which bullets were picked. Both draw on the same achievements |
| 5 | The model returns one ordered list of bullets, each with its achievement id. Code puts each under the job it is linked to. At most 5 bullets show under a job and 4 projects show; any more the model picked are kept, hidden, for the user to bring back | Where an achievement happened is a stored fact, so the model is not asked to repeat it. The caps keep a first build near two pages | A user with one long job may want more than 5; they restore them |
| 6 | A reworded bullet is kept only if it has every number of the stored bullet and no number the achievement does not hold. Otherwise the stored bullet is used as it is | "Keep each number exactly as stored", checked in code | A good rewording that drops a number is discarded |
| 7 | The profile paragraph and the letter may not contain a number that appears nowhere in what the model was given. One automatic retry, then an error with Retry | The same rule as "Improve with AI" in step 1 | An unusual phrasing can cost a retry |
| 8 | Skills on a CV come only from the user's own (the profile's and their achievements'). The model sorts them into "Technical" and "Tools"; anything else it returns is dropped. Spoken languages are copied with their levels | "Never add a skill" checked in code | A skill the model respelled is dropped; the user adds it from the list |
| 9 | Keywords: the model lists the advert's main terms, each kept only if those words are in the advert. Whether a term is covered is worked out in code by exact wording (a plural is tolerated), again after every edit | The step document requires that "covered" never lists a term absent from the CV. Applicant-tracking systems match words literally too | "Stakeholder management" does not count as covered by "managed stakeholders". The term then shows as in your profile, or missing |
| 10 | A job with no bullet picked still appears, with its title and dates | A UK CV should not show unexplained gaps | A long history takes more room; the user can hide an entry |
| 11 | Contact details are optional. The Resume page asks for them once, before the first CV, with "Build without them". The email comes from the login; the GitHub address from the username saved at import. A LinkedIn address must be on linkedin.com | A CV is valid without a phone number | A CV could go out with only an email on it; the page shows the contact line before download |
| 12 | The model is never sent the phone number, email, town or LinkedIn address | It does not need them | None |
| 13 | A character the PDF font cannot draw (and any right-to-left script, which it cannot lay out) is printed as "?" in the PDF. The page lists those characters before download and says the Word file shows them | The owner's answer, made exact | A user who misses the note sends a PDF with "?" in it |
| 14 | The Word file names its font as Arial and does not embed it | Every Word, Google Docs and applicant-tracking system has Arial | On a machine without Arial a near-identical font is substituted |
| 15 | New column `cv_versions.pages`, worked out when a CV is built and after every edit | The step document asks for a page count from the real PDF; making the PDF on every page view would be wasteful | One more column |
| 16 | The cover letter is dated the day it is downloaded, is addressed to "Hiring Manager" at the company unless the user types a name, and the job's title and company are copied into the CV when it is built | A letter should carry the date it is sent; a saved job can be removed later | None |
| 17 | File names are plain ASCII: "José Nuñez" gives `Jose-Nunez-CV-Acme.pdf` | Upload forms on employer sites often mishandle other characters | A name with no Latin letters gives `CV-Acme.pdf` |
| 18 | A CV made before this step opens read-only and cannot be downloaded or edited. "Rebuild as a full CV" is offered while its job is still saved | It holds no education, dates or contact details, so a file made from it would be a half CV | A user whose job was removed adds it again or builds a base CV |
| 19 | Deleting a version attached to an application answers 409 with "This CV is attached to an application. Remove it from the application first." | The step document says refused with a plain message | None |
| 20 | Reordering works by dragging and also by up and down buttons | Dragging alone cannot be used from a keyboard | A little more on screen |
| 21 | One route more than the step document lists: `PUT /api/profile/additional`. `PATCH /api/cv-versions/{id}` also takes `refresh_facts` | The Profile box and "Update from profile" | None |
| 22 | The migration is `006_full_cv` | 005 was used by step 1 | None |

## Review focus

Inputs most likely to break this, each with a test in the task named.

1. **Odd model output.** A bullet with an id that is not the user's, the same id twice, a changed or invented number, a skill the user does not have, a keyword that is not in the advert, an empty profile paragraph, a letter with a paragraph missing, and employers or dates the model was never asked for. (Tasks 3, 4)
2. **Thin profiles.** No work history; no education beyond the current course; no skills; every achievement unlinked; jobs with no dates; a base CV. Each must still give a valid CV with empty sections left out. (Tasks 3, 5, 6)
3. **Text that breaks files.** Accents, Cyrillic, a pound sign, a rupee sign, Chinese, emoji, an ampersand and angle brackets, a control character (which Word's XML refuses), a 200-character address with no spaces. (Tasks 5, 6)
4. **Ownership.** Saving edits that name another user's achievement, job or course; downloading, editing or deleting another user's version. (Tasks 2, 7)
5. **Sent versions.** Editing one makes a new version and leaves the old one byte for byte; deleting one is refused; an application attached between the read and the write still protects it. (Tasks 2, 7)
6. **Length.** Three pages or more; a heading at the foot of a page; the page count after hiding a bullet. (Tasks 5, 6, 7)

## File map

```
backend/
  migrations/006_full_cv.sql   create   profiles + phone, city, linkedin_url, additional; cv_versions + kind, format_version, edited_at, contact_name, pages
  fonts/                       create   LiberationSans-Regular.ttf, LiberationSans-Bold.ttf, LICENSE, AUTHORS
  cv.py                        create   the CV document: section order, assembling from records, applying edits, keyword coverage, right-to-work wording
  cvprint.py                   create   a CV or letter as a list of print blocks; file names
  cvword.py                    create   blocks to a .docx, in memory
  cvpdf.py                     create   blocks to a PDF and its page count, in memory; which characters the font lacks
  ai.py                        modify   + build_cv, job_letter; tailor removed
  repo.py                      modify   + contact details, additional lines, CV version kinds, update, delete, in use
  main.py                      modify   + 5 routes, POST /api/ai/tailor replaced by POST /api/ai/cv
  requirements.txt             modify   + python-docx, fpdf2
  scripts/live_check.py        modify   tailor replaced by the two new tasks and a whole build
  scripts/page_check.py        create   sample CVs of growing length: PDF pages beside Word's own count (Windows with Word only)
  tests/                       create   test_cv, test_cvprint, test_cvword, test_cvpdf, test_repo_cv, test_routes_cv
                               modify   test_migrate, test_ai, test_repo_records, test_repo_profile, test_routes_ai, test_routes_data
frontend/src/
  api.js                       modify   + download()
  ui.jsx                       modify   + EditableText
  components/ContactForm.jsx   create   phone, town or city, LinkedIn; used on Profile and before the first CV
  components/CvSheet.jsx       create   the CV as it will print: edit, reorder, hide, restore, add from profile
  components/CvSide.jsx        create   page count, keyword coverage, gaps, downloads, cover letter, applied with this CV
  components/OldCv.jsx         create   a version made before this step, read-only
  pages/Resume.jsx             rewrite  picker with "Base CV (no job)", build, versions, the two components above
  pages/Profile.jsx            modify   "For your CV": contact details and the certifications box
  pages/Privacy.jsx            modify   contact details; files made on request and not kept
  index.css                    modify   the CV sheet and its editing controls
docs/ARCHITECTURE.md, CLAUDE.md, README.md, the step document   modify
```

---

### Task 1: Schema and packages (`006_full_cv.sql`)

**Files:** create `backend/migrations/006_full_cv.sql`, `backend/fonts/` (four files); modify `backend/requirements.txt`, `backend/tests/test_migrate.py`.

**Produces:**

```sql
profiles    + phone text not null default '', city text not null default '', linkedin_url text not null default '',
              additional text[] not null default '{}'
cv_versions + kind text not null default 'tailored' check (kind in ('base', 'tailored')),
              format_version int not null default 1 check (format_version in (1, 2)),
              edited_at timestamptz, contact_name text not null default '', pages int
```

Every existing version becomes `kind = 'tailored'`, `format_version = 1`. No new table, so row-level security and privileges are unchanged.

- [ ] **Step 1: tests** in `test_migrate.py`: `test_profile_cv_defaults` (the four new profile columns default to empty); `test_cv_version_defaults` (a row inserted the old way is `tailored`, format 1, no pages, no `edited_at`); `test_cv_kind_and_format_checked` (`kind = 'other'` and `format_version = 3` raise `CheckViolation`).
- [ ] **Step 2:** run, see them fail (columns missing).
- [ ] **Step 3:** write the migration; `python migrate.py`. Add `python-docx` and `fpdf2` to `requirements.txt` and install them. Copy the two font files with `LICENSE` and `AUTHORS` into `backend/fonts/`.
- [ ] **Step 4:** run the suite; commit `feat: schema, packages and font for the full CV`.

### Task 2: Contact details and CV versions (`repo.py`)

**Files:** modify `backend/repo.py`, `backend/tests/test_repo_profile.py`, `backend/tests/test_repo_records.py`; create `backend/tests/test_repo_cv.py`.

**Produces:**

```python
set_contact(conn, user_id, *, phone: str, city: str, linkedin_url: str) -> dict        # the profile
set_additional(conn, user_id, lines: list[str]) -> dict                                # trimmed, blanks and repeats dropped
add_cv_version(conn, user_id, *, saved_job_id, role_family_id, base_name: str, content: dict,
               kind: str = "tailored", format_version: int = 2, pages: int | None = None, contact_name: str = "") -> dict
update_cv_version(conn, user_id, cv_version_id, *, content: dict, pages: int | None, contact_name: str) -> dict | None   # sets edited_at
cv_version_in_use(conn, user_id, cv_version_id) -> bool                                # an application of this user points at it
delete_cv_version(conn, user_id, cv_version_id) -> bool | None                         # None: not theirs; False: in use
```

`add_cv_version` numbers a name from the highest number already used for that base name (`"Base CV v3"` after `v2` even if `v1` was deleted), not from a count. `content` is stored with dates as ISO text.

- [ ] **Step 1: tests.** `test_repo_profile.py`: contact details saved and trimmed; additional lines trimmed, blanks and repeats dropped; both leave user B's profile alone. `test_repo_cv.py`: `test_new_version_is_format_two_with_kind_and_pages`; `test_base_versions_number_on_their_own` (base and tailored names do not share a counter); `test_number_follows_the_highest_not_the_count` (delete `v1`, the next is `v3`); `test_update_changes_content_and_marks_edited`; `test_update_other_users_version_changes_nothing` (returns None, row unchanged); `test_in_use_only_for_the_owners_application`; `test_delete_refused_while_an_application_points_at_it` (returns False, row kept); `test_delete_removes_an_unused_version`; `test_delete_other_users_version_returns_none`. `test_repo_records.py`: the existing version tests updated for the new arguments.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: contact details and CV version kinds`.

### Task 3: The CV document (`cv.py`)

**Files:** create `backend/cv.py`, `backend/tests/test_cv.py`.

**The document (format 2):**

```json
{"contact": {"name", "city", "phone", "email", "linkedin", "github"},
 "job": {"title", "company"} | null,
 "profile": "the paragraph",
 "section_order": ["education", "work", "projects", "skills", "additional"],
 "education": [{"education_id", "institution", "qualification", "subject", "start_month", "end_month", "grade", "country", "note", "hidden"}],
 "work": [{"work_history_id", "employer", "job_title", "location", "country", "start_month", "end_month", "is_current", "employer_context", "hidden",
           "bullets": [{"text", "achievement_id", "hidden"}]}],
 "projects": [{"achievement_id", "title", "link", "where", "hidden", "bullets": [{"text", "achievement_id", "hidden"}]}],
 "skills": {"technical": [str], "tools": [str], "languages": [str]},
 "additional": {"lines": [{"text", "hidden"}]},
 "right_to_work": {"shown": false, "text": str},
 "cover_letter": {"why_them", "why_you", "what_you_deliver"} | null,
 "keywords": {"terms": [str], "covered": [str], "available": [{"term", "achievement_ids"}], "missing": [str]},
 "gaps": [str]}
```

The name and the profile paragraph always come first; `section_order` holds the other five.

**Produces:**

```python
SECTIONS = ("education", "work", "projects", "skills", "additional")
MAX_JOB_BULLETS, MAX_PROJECTS = 5, 4
RECENT_MONTHS = WORK_MONTHS = 24

months_worked(work_history: list, today: date) -> int        # months covered by jobs that have a start; overlaps counted once
education_first(profile: dict, work_history: list, today: date) -> bool
right_to_work(profile: dict) -> str                           # the agreed wording for their visa, "" if the visa is not known
contact(profile: dict, email: str) -> dict
own_skills(profile: dict, achievements: list) -> list[str]    # the profile's skills, then those of achievements, one spelling each
assemble(*, profile, email, education, work_history, achievements, written: dict, job: dict | None, today: date) -> dict
merge(stored: dict, edited: dict, *, profile, email, education, work_history, achievements, refresh: bool = False) -> dict
text(content: dict) -> str                                    # every word a reader of the CV sees; hidden parts and the letter left out
has_term(term: str, text: str) -> bool                        # the same words in the same order; a plural is tolerated
coverage(terms: list[str], content: dict, achievements: list, skills: list[str]) -> dict
unused(content: dict, achievements: list) -> list[dict]       # achievements with no bullet on this CV
```

`written` is what the model returned after `ai`'s own checks: `{"profile", "bullets": [{"achievement_id", "text"}], "skills": {"technical", "tools"}, "keywords", "gaps", "cover_letter"}`.

Rules: education first when the user is still studying or graduated at most 24 months ago, and has worked under 24 months. A bullet goes under the job its achievement is linked to, in the model's order; otherwise it becomes a project (its link the repository address without "https://", its `where` the institution of a linked course). `merge` takes wording, order and hidden flags from `edited` and every fact from the stored copy, or from the user's own record when the entry is new to this CV, or from the record again when `refresh` is set; an entry or bullet naming a row that is not the user's is dropped; `section_order` is accepted only if it is the five sections once each.

- [ ] **Step 1: tests** in `test_cv.py`: education first at the boundaries (`graduated 23 months ago` yes, `25 months ago` no; `12 months of work` yes, `36 months` no; still studying with 36 months of work no); `months_worked` counts overlapping jobs once, a current job up to today, a job with no start as nothing; `test_facts_come_from_the_records_whatever_the_model_wrote` (`written` carrying an `employer` and dates is ignored); `test_bullets_sit_under_their_own_job_in_the_models_order`; `test_a_sixth_bullet_for_one_job_is_kept_hidden`; `test_a_fifth_project_is_kept_hidden`; `test_a_job_with_no_bullets_still_appears`; `test_unlinked_course_and_github_achievements_become_projects` (link and institution set); `test_no_work_history_gives_no_work_entries`; `test_only_the_current_course`; `test_base_cv_has_no_letter_keywords_or_gaps`; `test_right_to_work_is_off_and_worded_by_visa` (both wordings exactly; a date written "14 March 2028"); `test_languages_are_copied_with_their_level`; `test_additional_lines_come_from_the_profile`; merge: `test_edit_cannot_change_a_fact` (an edited employer, date and email are ignored), `test_edit_changes_wording_order_and_hidden`, `test_a_bullet_naming_another_users_achievement_loses_the_link`, `test_an_entry_naming_another_users_job_is_dropped`, `test_a_new_entry_takes_its_facts_from_the_record`, `test_refresh_recopies_facts_and_contact`, `test_a_removed_record_keeps_its_stored_copy`, `test_bad_section_order_keeps_the_stored_one`, `test_lengths_are_capped`; coverage: `test_covered_only_when_the_words_are_in_the_cv`, `test_a_hidden_bullet_does_not_cover_a_term`, `test_available_names_the_achievements_that_show_it`, `test_missing_when_nowhere_in_the_profile`, `test_plural_and_case_are_tolerated`, `test_cpp_and_csharp_are_not_confused`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: the CV document, built from stored records`.

### Task 4: The two AI tasks (`ai.py`)

**Files:** modify `backend/ai.py`, `backend/tests/test_ai.py`.

**Produces:**

```python
build_cv(profile: dict, education: list, work_history: list, achievements: list, skills: list[str], job: dict | None = None) -> dict
    # {"profile": str, "bullets": [{"achievement_id", "text"}], "skills": {"technical": [str], "tools": [str]}}
job_letter(job: dict, profile: dict, achievements: list) -> dict
    # {"keywords": [str], "gaps": [str], "cover_letter": {"why_them", "why_you", "what_you_deliver"}}
```

`tailor` is removed. `build_cv` is told the page budget (two A4 pages: up to five bullets for a job, one or two for a project) and, for each achievement, where it happened. It is sent the candidate's course, jobs with dates and the length of each, never their contact details. Checks in code: a bullet whose id is not one of the user's is dropped, as is a second bullet for the same id; a reworded bullet missing a number of the stored bullet, or holding a number the achievement does not, is replaced by the stored bullet; a skill is kept only if it is one of `skills` (ignoring case, in the user's spelling) and only once; the paragraph is required, and a number in it that is nowhere in the input fails the attempt. `job_letter` keeps a keyword only if its words are in the advert's title or text, at most 15; all three paragraphs are required; a number that is nowhere in the input fails the attempt.

- [ ] **Step 1: tests** in `test_ai.py` (the model replaced, as in every test there): `test_build_cv_drops_a_bullet_for_an_unknown_id`; `test_build_cv_keeps_one_bullet_per_achievement`; `test_a_bullet_that_changed_a_number_falls_back_to_the_stored_one` ("15 managers" to "50 managers"); `test_a_bullet_that_dropped_a_number_falls_back`; `test_a_bullet_that_added_a_number_falls_back`; `test_a_faithful_rewording_is_kept`; `test_skills_only_from_the_users_own_in_their_spelling`; `test_a_skill_in_both_groups_is_listed_once`; `test_paragraph_with_an_invented_number_is_asked_for_again_then_fails`; `test_build_cv_needs_a_paragraph_and_a_bullet`; `test_build_cv_prompt_has_no_contact_details` (phone, email, LinkedIn and town absent from the prompt); `test_build_cv_prompt_names_where_each_achievement_happened`; `test_base_cv_prompt_names_no_job`; `test_keywords_must_be_in_the_advert`; `test_letter_needs_all_three_paragraphs`; `test_letter_with_an_invented_number_fails`; `test_job_letter_prompt_cuts_a_long_advert`. The four `tailor` tests are removed.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: AI tasks for the CV body and the cover letter`.

### Task 5: Print blocks and the PDF (`cvprint.py`, `cvpdf.py`)

**Files:** create `backend/cvprint.py`, `backend/cvpdf.py`, `backend/scripts/page_check.py`, `backend/tests/test_cvprint.py`, `backend/tests/test_cvpdf.py`; modify `backend/tests/files.py`.

**Produces:**

```python
# cvprint.py: what is printed, in order. A block is (kind, text) or ("entry", left, right)
# kinds: name, contact, heading, entry, sub, line, para, bullet, gap
blocks(content: dict) -> list[tuple]
letter_blocks(content: dict, contact_name: str, today: date) -> list[tuple]
file_name(content: dict, part: str, extension: str) -> str     # "Firstname-Lastname-CV-Company.pdf"
period(entry: dict) -> str                                       # "Sep 2025 to Sep 2026", "Jul 2022 to present", "" with no dates

# cvpdf.py
render(blocks: list[tuple], *, title: str, author: str) -> tuple[bytes, int]    # the file and its page count
unsupported(text: str) -> str                                                     # characters the PDF cannot show, each once, in order met
```

Section headings: "Personal profile", "Education", "Work experience", "Projects", "Skills", "Additional information". A section with nothing visible is left out, heading and all. An education entry prints the institution (with its country unless that is the United Kingdom) and dates, then qualification and subject, then "Grade: ..." and the optional note. A work entry prints employer, town and country with the dates, then the job title, then the employer line, then its visible bullets. Skills print as "Technical: ...", "Tools: ...", "Languages: ...". The right-to-work line prints last, only when switched on. The letter: name, contact line, date, "Hiring Manager" or the name typed, the company, "Dear Hiring Manager," with "Yours faithfully," or "Dear <name>," with "Yours sincerely,", the three paragraphs, the name. The PDF is A4, Liberation Sans 10.5 pt, real text, with a heading never left alone at the foot of a page.

- [ ] **Step 1: tests.** `test_cvprint.py`: `test_sections_print_in_the_chosen_order`; `test_hidden_bullets_entries_and_lines_are_not_printed`; `test_an_empty_section_prints_no_heading` (no work history; no projects; no skills); `test_dates_print_as_months` and with no dates the right side is empty; `test_overseas_institution_names_its_country`; `test_right_to_work_prints_only_when_shown`; `test_contact_line_leaves_out_what_is_blank`; `test_letter_to_hiring_manager_is_yours_faithfully`; `test_letter_to_a_name_is_yours_sincerely`; `test_letter_carries_the_date_given` ("13 October 2026"); `test_file_names` (accents folded, a company with "&", the base CV has no company, a name with no Latin letters). `test_cvpdf.py`: `test_pdf_text_comes_back_in_block_order` (read with `pypdf`); `test_accents_cyrillic_greek_and_a_pound_sign_survive`; `test_unsupported_names_each_missing_character_once` (rupee sign, Chinese, an emoji, Hebrew as right-to-left) and they print as "?"; `test_page_count_grows_with_content` (one page, then three); `test_a_heading_is_not_left_at_the_foot_of_a_page`; `test_a_long_unbroken_address_does_not_fail`; `test_title_and_author_are_set_and_no_file_is_written` (`forbid_disk_writes`).
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement. Then run `scripts/page_check.py` and set the PDF's spacing so that on every sample its count is Word's or one more, never one fewer.
- [ ] **Step 4:** run the suite; commit `feat: the CV as print blocks and as a PDF`.

### Task 6: The Word file (`cvword.py`)

**Files:** create `backend/cvword.py`, `backend/tests/test_cvword.py`.

**Produces:**

```python
render(blocks: list[tuple], *, title: str, author: str) -> bytes
```

A4, Arial 10.5 pt, black. Headings use Word's own heading style, bullets its list style, dates a right-hand tab stop. No tables, text boxes, columns or images, nothing in the header or footer. Characters Word's XML refuses are removed. The author is the user's name.

- [ ] **Step 1: tests** in `test_cvword.py`, each reading the file back with `python-docx`: `test_every_block_is_there_in_order`; `test_no_tables_and_nothing_in_header_or_footer`; `test_headings_use_the_heading_style_and_bullets_the_list_style`; `test_dates_follow_a_tab_not_a_table`; `test_page_is_a4_and_font_is_arial`; `test_accents_other_scripts_and_a_pound_sign_survive` (including Chinese and the rupee sign, which Word can show); `test_ampersand_angle_brackets_and_a_control_character`; `test_author_is_the_user_not_the_library`; `test_no_file_is_written`; and one test across both writers, `test_word_and_pdf_say_the_same_thing_in_the_same_order`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: the CV as a Word file`.

### Task 7: Routes (`main.py`)

**Files:** modify `backend/main.py`, `backend/tests/test_routes_ai.py`, `backend/tests/test_routes_data.py`; create `backend/tests/test_routes_cv.py`.

| Route | Behaviour |
|---|---|
| `POST /api/ai/cv` | `{"job_id"}` or `{}`. 404 for a job that is not theirs; 400 "Build your profile first." with no achievements. One AI action. Reads records, calls the model with no connection open (`build_cv`, and for a job `job_letter` beside it), assembles, counts the pages, saves a format-2 version named "<title>, <company> vN" or "Base CV vN" |
| `PATCH /api/cv-versions/{id}` | `{"content", "contact_name", "refresh_facts"}`. Applies the edit with `cv.merge`, recounts pages and keywords. Attached to an application: saved as a new version, returned with `"replaced": <old id>`. A format-1 version: 422 "This CV was made before full CVs. Rebuild it to edit it." |
| `DELETE /api/cv-versions/{id}` | 204, or 409 while an application points at it |
| `GET /api/cv-versions/{id}/download?format=docx\|pdf&part=cv\|letter` | The file, with its content type, `Content-Disposition` and `Cache-Control: no-store`. 422 for any other format or part, for the letter of a base CV, and for a format-1 version |
| `PUT /api/profile/contact` | Phone (digits, spaces and `+ ( ) -`), town or city, LinkedIn address (linkedin.com only; stored without "https://") |
| `PUT /api/profile/additional` | Up to 12 lines of up to 200 characters |

`POST /api/ai/tailor` is removed. Every version in `/api/state` and in these answers carries `unsupported` (the characters its PDF cannot show).

- [ ] **Step 1: tests** in `test_routes_cv.py`: `test_tailored_cv_is_saved_as_format_two_with_pages`; `test_every_fact_equals_the_record_whatever_the_model_returned`; `test_base_cv_needs_no_job_and_has_no_letter`; `test_build_counts_one_ai_action_and_the_limit_applies` (429, the model not called); `test_nothing_is_saved_when_either_call_fails` (502 for each of the two); `test_build_needs_achievements`; `test_build_for_another_users_job_404`; `test_malformed_job_id_422`; `test_edit_is_saved_in_place_and_pages_recounted`; `test_editing_a_sent_version_makes_a_new_one_and_leaves_the_old_untouched`; `test_edit_cannot_change_facts_or_borrow_another_users_rows`; `test_refresh_facts_picks_up_a_profile_change`; `test_edit_old_format_refused`; `test_edit_delete_download_another_users_version_404`; `test_malformed_version_id_422`; `test_delete_refused_while_attached` (409 and the row is still there); `test_delete_unused`; `test_download_word_and_pdf` (content types, file name, the Word file opens and holds the user's name, the PDF's text holds a bullet); `test_downloads_match_after_hiding_a_bullet` (gone from both files); `test_letter_downloads_and_base_cv_has_none`; `test_download_bad_format_422`; `test_download_old_format_refused`; `test_contact_saved_and_linkedin_must_be_linkedin`; `test_contact_appears_on_the_next_cv_and_not_in_any_prompt`; `test_additional_lines_saved_and_capped`; `test_state_versions_carry_unsupported`. `test_routes_data.py`: the new routes added to the list checked for 401 without a token. `test_routes_ai.py`: the three `tailor` route tests removed.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: routes to build, edit, download and delete a CV`.

### Task 8: Real-model check (`scripts/live_check.py`)

**Files:** modify `backend/scripts/live_check.py`.

- [ ] **Step 1:** replace the `tailor` check with: `cv body, tailored` (every bullet id is real, every stored number survives, skills are a subset of the user's own), `cv body, base`, `cover letter` (three paragraphs, keywords all in the advert), and `cv build, both at once` (the whole build as the route does it, timed, and the assembled CV is two pages or fewer as a PDF).
- [ ] **Step 2:** run them against the real model. If a check fails, fix the prompt or the code check, not the test; record timings.
- [ ] **Step 3:** run the suite; commit `feat: real-model checks for the full CV`.

### Task 9: Resume page, building and versions

**Files:** modify `frontend/src/api.js`, `frontend/src/ui.jsx`, `frontend/src/pages/Resume.jsx`, `frontend/src/pages/Profile.jsx`, `frontend/src/index.css`; create `frontend/src/components/ContactForm.jsx`, `frontend/src/components/OldCv.jsx`.

- [ ] **Step 1:** `api.js`: `download(path)` fetches with the login token (with the same refresh-and-retry as every call) and hands the browser the file under the name the server gave. `ContactForm`: phone, town or city, LinkedIn. Profile gets a "For your CV" card: the contact form and "Certifications, awards and volunteering", one per line.
- [ ] **Step 2:** `Resume.jsx`: the picker starts with "Base CV (no job)"; "Build CV" (or "Build CV and cover letter" for a job). Before the first CV, when no contact detail is saved, the contact form is shown with "Save and build" and "Build without them". Empty states: no achievements links to Profile; no saved job still offers the base CV. A line says how many achievements are linked to no job or course, with a link to Profile. "Your CV versions" lists every version with Delete; a refused delete shows the server's message. A version made before this step opens in `OldCv` with "Rebuild as a full CV".
- [ ] **Step 3:** `npm run lint && npm run build`; commit `feat: build a base or tailored CV; contact details on the profile`.

### Task 10: Editing on screen

**Files:** create `frontend/src/components/CvSheet.jsx`; modify `frontend/src/ui.jsx`, `frontend/src/pages/Resume.jsx`, `frontend/src/index.css`.

- [ ] **Step 1:** `EditableText`: click to edit, Enter or leaving the field keeps the change, Escape drops it. `CvSheet` draws the CV in its print order and typeface: the profile paragraph, bullets, a project's title, the education note, skills, additional lines and the right-to-work line are editable; facts are plain text with "Edit on Profile". Each bullet and entry has move up, move down, a drag handle and Hide; hidden ones are listed under their section with Restore. Sections move up and down. "Add a bullet from my profile" lists achievements not on this CV.
- [ ] **Step 2:** saving: every change goes to `PATCH` in order, one at a time; the page shows "Saving" then "Saved", or the error with Retry. When the answer is a new version the page switches to it and says "This CV was sent with an application, so your changes are saved as a new version." When the profile's facts differ from the CV's copy, "Update from profile" is offered.
- [ ] **Step 3:** `npm run lint && npm run build`; commit `feat: edit, reorder, hide and restore on the CV`.

### Task 11: Page count, keywords, downloads and the letter

**Files:** create `frontend/src/components/CvSide.jsx`; modify `frontend/src/pages/Resume.jsx`, `frontend/src/pages/Privacy.jsx`, `frontend/src/index.css`.

- [ ] **Step 1:** `CvSide`: the page count ("2 pages", or a warning over two with what could be trimmed: the entry with most bullets, the number of projects shown, the length of the profile paragraph); keyword coverage in its three groups, with Add where an achievement shows the term; "Be ready to talk about"; Download Word and Download PDF; the note naming characters the PDF cannot show; the cover letter with its three editable paragraphs, "Who to address it to", Copy, and its own downloads; "Applied with this CV", as today.
- [ ] **Step 2:** Privacy page: phone, town and LinkedIn address are collected for the CV; CV and letter files are made when downloaded and not kept.
- [ ] **Step 3:** `npm run lint && npm run build`; commit `feat: page count, keyword coverage, downloads and the cover letter`.

### Task 12: Verify and document

- [ ] **Step 1:** whole suite, 0 skipped; frontend lints and builds; `live_check.py` in full.
- [ ] **Step 2:** run the pages against the real backend and model as a temporary user whose data is never saved (the method used in step 1): build a base and a tailored CV, edit, reorder, hide, restore, add from profile, go over two pages and back, download all four files and read them back, open both Word files in Word for their page count, attach a version to an application and edit it, try to delete it. Fix what this finds. Remove every temporary file and confirm the database is clean.
- [ ] **Step 3:** a self-review of the whole diff against "Review focus".
- [ ] **Step 4:** `docs/ARCHITECTURE.md` (roadmap, stack, decisions, code map, data model, API, AI layer, security, tests, limitations, a section on the CV and a verification record), `CLAUDE.md`, `README.md`, the step document. Commit `docs: step 3 built; what is verified and what the owner still has to check`.
- [ ] **Step 5:** the owner's seven hand checks from the step document, with their own profile and login.

## Order and what blocks what

Tasks 1 to 4 in order (4 needs nothing from 2 or 3 but shares fixtures with 3). Tasks 5 and 6 need 3. Task 7 needs 2 to 6. Task 8 needs 4 and 5. Tasks 9 to 11 need 7, in order. Task 12 last.
