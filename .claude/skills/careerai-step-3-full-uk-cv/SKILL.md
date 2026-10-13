---
name: careerai-step-3-full-uk-cv
description: Use when building, continuing or reviewing step 3 of the CareerAI roadmap - the complete UK-standard ATS-safe CV, in-app CV editing, Word and PDF download, keyword coverage and the cover letter export
---

# Step 3: the full UK CV

**Status:** In progress on branch `step-3-full-uk-cv`. Open questions settled with the owner on 13 October 2026; the plan is `docs/superpowers/plans/2026-10-13-step-3-full-uk-cv.md`. Design approved by the owner, 12 October 2026. **Depends on:** step 1 (needs work history, education and skills). **Size:** medium.
**REQUIRED:** follow `careerai-building-a-step`.

## Goal

For any job the user has saved, the app produces a complete two-page UK CV and cover letter that an applicant-tracking system can read, the user can edit on screen, and downloads as Word or PDF. The tracker knows exactly which wording was sent.

Today "tailoring" produces a profile paragraph, four or five bullets and a cover letter on screen. There is no education, no dates, no download.

## Decisions already made (do not re-ask)

| Decision | Detail | Decided by |
|---|---|---|
| Formats | Word (.docx) and PDF, generated from the same content | Owner, 12 Oct 2026 |
| Layouts | One ATS-safe, single-column layout | Owner, 12 Oct 2026 |
| Editing | In the app. The saved version keeps the user's edits | Owner, 12 Oct 2026 |
| Two kinds of CV | A base CV from the whole profile (no job), and a tailored CV per saved job | Recommended; approved 12 Oct 2026 |
| Facts are never written by the AI | Employers, job titles, dates, institutions, qualifications and grades are copied from the stored records. The AI writes only the profile paragraph, chooses and rewords bullets, and orders skills | Recommended; approved 12 Oct 2026 |
| Sent versions do not change | Editing a CV version that is already attached to an application creates a new version, so reply rates by version stay true | Recommended; approved 12 Oct 2026 |
| Length | Two pages. The app shows the page count and says what to trim; it never cuts content silently | Recommended; approved 12 Oct 2026 |
| Right-to-work line | Off by default. The user can switch it on and edit the wording. The app offers neutral wording stating the current visa and its end date and makes no claim about future eligibility | Recommended; approved 12 Oct 2026 |
| Right-to-work wording | Graduate visa: "Right to work in the UK: Graduate visa, valid until 14 March 2028." Student visa: "Visa status: Student visa, valid until 30 January 2027." A Student visa limits working hours, so that line does not say "right to work". No hour figures | Owner, 13 Oct 2026 |
| Achievements linked to no job or course | They go under Projects, with GitHub projects and course projects. The page says how many are unlinked and links to Profile | Owner, 13 Oct 2026 |
| Certifications, awards and volunteering | A box on the Profile, one per line, used by every CV; a line can be hidden on one CV. One more column, `profiles.additional` | Owner, 13 Oct 2026 |
| PDF font | Liberation Sans (SIL Open Font Licence 1.1, the same letter widths as Arial), bundled in `backend/fonts`. Characters it cannot draw are named on the page, which points to the Word file | Owner, 13 Oct 2026 |

## In scope

1. A full CV document model with all sections.
2. AI building of a base CV and a tailored CV.
3. On-screen editing: reword, reorder, hide, restore.
4. Word and PDF download of the CV and of the cover letter.
5. Keyword coverage against the job description.
6. Contact details on the profile.
7. Opening and upgrading CV versions made before this step.

## Out of scope

Multiple layouts; photos or graphics; importing an edited Word file back in; LinkedIn profile text (a later idea); applying on the user's behalf.

## The CV layout

Single column, standard fonts (Arial or Calibri, 10.5 to 11 pt), real bullet lists, standard headings, no tables, text boxes, columns, images, or content in the page header or footer. Dates are aligned with tab stops, not tables.

| Order | Section | Content |
|---|---|---|
| 1 | Name and contact line | Name, town or city, phone, email, LinkedIn and GitHub addresses if given. No photo, date of birth, nationality, marital status or full postal address |
| 2 | Personal profile | Three to four lines written for this job |
| 3 | Education | Institution, qualification, subject, dates, grade. Relevant modules or dissertation as an optional line |
| 4 | Work experience | Newest first: employer, town and country, job title, dates; one line saying what an overseas employer does; three to five bullets, each starting with an action and carrying a number where the user has one |
| 5 | Projects | University and GitHub projects, each with one or two bullets and a link |
| 6 | Skills | Grouped: technical, tools, languages |
| 7 | Additional | Certifications, volunteering, the optional right-to-work line |

Education comes before work experience when the user is still studying or graduated within the last two years and has under two years of work experience; otherwise work experience comes first. The user can reorder sections.

File name: `Firstname-Lastname-CV-<Company>.docx` (or `.pdf`); the base CV omits the company.

## What the user sees

**Resume page.** A job picker with "Base CV (no job)" as the first choice. Building takes one AI action.

- **Left:** the CV as it will print. Clicking any text edits it. Each bullet and entry can be dragged to reorder, hidden, or restored. "Add a bullet from my profile" lists achievements not yet used.
- **Right:** page count with a warning over two pages; keyword coverage; "Be ready to talk about" (gaps); Download Word, Download PDF; the cover letter with its own editing and downloads and a Copy button; "Applied with this CV".

**Keyword coverage** lists the main terms from the job description in three groups: covered in this CV; in your profile but not in this CV (with "Add" where an achievement evidences it); not in your profile (a gap, shown for honesty, never added automatically).

**Contact details.** The first time a CV is built, the user is asked for phone, town or city and LinkedIn address. They are saved on the profile and editable there.

**Cover letter.** UK letter form: date, greeting, the three paragraphs (why them, why you with two pieces of evidence, what you will deliver), sign-off. "Dear Hiring Manager" with "Yours faithfully" unless the user enters a name, then "Yours sincerely".

**Older versions.** A CV made before this step opens read-only with "Rebuild as a full CV".

## Data changes (migration `00N_full_cv`)

| Change | Detail |
|---|---|
| `profiles` | Add `phone`, `city`, `linkedin_url` |
| `cv_versions` | Add `kind` (`base` or `tailored`), `format_version int` (1 for old content, 2 for the full document), `edited_at`, `contact_name text` for the letter |
| `cv_versions.content` (format 2) | `{profile, section_order, education: [...], work: [{work_history_id, bullets: [{text, achievement_id, hidden}], hidden}], projects: [...], skills: {...}, additional: {...}, right_to_work: {shown, text}, cover_letter: {...}, keywords: {covered, available, missing}, gaps}` |

Each education and work entry in the content stores the record's id plus a copy of its facts at build time, so a later profile edit does not silently change a CV that was sent.

## API

| Route | Purpose |
|---|---|
| `POST /api/ai/cv` | `{job_id}` or `{}` for the base CV → a new format-2 version. One AI action |
| `PATCH /api/cv-versions/{id}` | Save edits. If the version is attached to an application, saves as a new version and returns it |
| `DELETE /api/cv-versions/{id}` | Refused while an application points at it |
| `GET /api/cv-versions/{id}/download?format=docx\|pdf&part=cv\|letter` | The file, with the right content type and file name |
| `PUT /api/profile/contact` | Phone, town or city, LinkedIn address |

`POST /api/ai/tailor` is replaced by `POST /api/ai/cv`. The download is fetched with the login token and saved by the browser, because a plain link cannot carry the token.

## AI task

`build_cv(profile, education, work_history, achievements, skills, job or none)` returns: the profile paragraph; for each job and project, which achievements to use, in what order, reworded for this job; the skills order; the keyword groups; the gaps; the cover letter. It receives achievement ids and returns them, and any bullet whose id is not one of the user's is dropped. It is told the page budget.

Rules in the prompt, each backed by a test: use only the facts given; never add a skill, tool, employer, date or number that is not in the input; keep each number exactly as stored.

## Outside services and settings

None. New Python packages: `python-docx` for Word (already added in step 1) and a pure-Python PDF library.

## Behaviours that must have tests

In addition to the standing list in `careerai-building-a-step`:

- Every employer, job title, date, institution, qualification and grade in a generated CV equals the stored record, whatever the model returned.
- A bullet with an achievement id the user does not own is dropped.
- A number in a stored achievement appears unchanged in the reworded bullet, or the stored bullet is used instead.
- The Word file, read back with `python-docx`, contains every visible section in order, uses no tables, and has no content in headers or footers.
- The PDF, read back with a text extractor, yields the same text in the same order (it is real text, not an image).
- Hidden bullets and entries appear in neither file.
- Names with accents or non-Latin characters, and a pound sign, survive in both files.
- A profile with no work history, or no education beyond the current course, still builds a valid CV with that section omitted.
- Section order follows the education-first rule at its boundaries (graduated 23 months ago against 25; 1 year of work against 3).
- Editing a version attached to an application returns a new version and leaves the old one unchanged.
- Deleting a version attached to an application is refused with a plain message.
- A format-1 version opens and can be rebuilt.
- Keyword coverage never lists as "covered" a term absent from the CV text.
- The right-to-work line is absent unless switched on.
- Downloading another user's version answers 404.

## Check by hand

1. Build a base CV and a tailored CV from a real profile; read both for accuracy.
2. Download Word: open in Word or Google Docs; two pages, headings and bullets intact, text editable.
3. Download PDF: text can be selected and copied in reading order.
4. Edit a bullet, reorder two, hide one; download again; the files match the screen.
5. Go over two pages: the warning appears; trim until it clears.
6. Attach a CV to an application, edit it, and confirm a new version is created.
7. Optional, the owner's choice because it sends a CV to a third party: run the Word file through a public ATS parsing checker.

## Task outline

1. Migration; contact details on the profile.
2. The CV document model, the section-order rule, and assembly from stored records.
3. The `build_cv` AI task with its integrity checks.
4. Word generation with the round-trip tests.
5. PDF generation with the round-trip tests.
6. Routes: build, edit, download, delete.
7. Resume page: preview, inline editing, reorder, hide and restore.
8. Keyword coverage and page count.
9. Cover letter form, editing and downloads.
10. Upgrade path for older versions; live checks, hand checks, documentation.

## Done when

A user with a complete profile can go from a saved job to a downloaded two-page Word and PDF CV and cover letter in a few minutes, every fact in them is theirs, and the tracker shows which version went to which employer.

## Verify at build time

- Which pure-Python PDF library runs on Vercel within the bundle limit and supports the needed characters (candidates: `fpdf2` with a bundled Unicode font, `reportlab`). Check the font's licence allows redistribution.
- How to count pages reliably: from the generated PDF rather than an estimate.
- Current UK CV conventions for the right-to-work line, and agree the suggested wording with the owner.
- Whether step 2 has shipped: if so, a tailored CV can start from a job saved from a listing; if not, only pasted jobs exist. Both must work.
