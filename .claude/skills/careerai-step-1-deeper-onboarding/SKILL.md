---
name: careerai-step-1-deeper-onboarding
description: Use when building, continuing or reviewing step 1 of the CareerAI roadmap - CV file upload, GitHub project import, editing achievements, education and work history, skills, and the STAR story bank
---

# Step 1: deeper onboarding

**Status:** Built on branch `step-1-deeper-onboarding` (13 October 2026), not yet merged. **Not finished:** the hand checks that need the owner's own CV, GitHub account and login. See "Where it stands" straight below. Design approved by the owner, 12 October 2026; the task plan and the changes under "Changed at build time" approved 13 October 2026. **Depends on:** step 0. **Size:** medium (smaller than step 0).
**REQUIRED:** follow `careerai-building-a-step`.

## Where it stands (13 October 2026)

All fourteen tasks in `docs/superpowers/plans/2026-10-13-step-1-deeper-onboarding.md` are built and committed except the owner's hand checks. 907 backend tests pass; the real model passes all 21 checks; the pages were run against the real backend as a temporary user whose data was never saved (see `docs/ARCHITECTURE.md` section 18).

To finish the step, in this order:

1. With the owner signed in, do the seven hand checks below. The owner uploads their own CV (as PDF, then as Word) and types their own GitHub username.
2. Look at the pages by eye. They were checked by text and behaviour only: the four tiles, "We also found", the three new Profile sections, the achievement card's edit and improve forms, the story editor.
3. If a real CV reads badly, run `python scripts/cv_check.py <file>` from `backend/` to see the text the AI receives, and tell the owner before changing libraries.
4. Update `docs/ARCHITECTURE.md` section 18 and this section, then give the owner the pull request link when they ask.

Decisions made while building, beyond those in "Changed at build time", are in the plan's table and in `docs/ARCHITECTURE.md` sections 5 and 17.

## Goal

Everything the user has done ends up in their profile with little typing, in a shape a full UK CV can be built from, and they can correct whatever the AI got wrong.

After step 0 a profile can only be built by voice or pasted text, achievements cannot be edited, and the app holds no structured education or work history. Step 3 (the full CV) needs all of that.

## Decisions already made (do not re-ask)

| Decision | Detail | Decided by |
|---|---|---|
| New ways to import | CV file upload and GitHub projects. Voice and pasted text stay | Owner, 12 Oct 2026 |
| LinkedIn | Not included. Users can paste their LinkedIn text into the existing paste box | Owner, 12 Oct 2026 |
| Uploaded files | Read, then discarded. Only the extracted text and what is built from it are saved | Owner, 12 Oct 2026 |
| CV facts | Education, work history, skills and languages are collected and confirmed in this step, not in step 3 | Owner, 12 Oct 2026 |
| File types | PDF and Word (.docx), up to 5 MB. Text is cut at 30,000 characters with a notice | Recommended; approved 12 Oct 2026 |
| Unreadable files | A scanned or image-only PDF gets "We could not read any text in this file. Paste the text instead." No OCR | Recommended; approved 12 Oct 2026 |
| Editing | Every field of an achievement can be edited by hand. "Improve with AI" rewrites the bullet using the existing facts plus a short note the user types (for example the missing number) | Recommended; approved 12 Oct 2026 |
| Missing numbers | Achievements with no number show an "Add a number" prompt | Recommended; approved 12 Oct 2026 |
| Story bank | One button, "Build my story bank", writes STAR stories for up to 8 of the strongest achievements that have none, in one AI call. Stories can be edited and deleted | Recommended; approved 12 Oct 2026 |
| Duplicates | When importing from a second source the AI is given the existing achievements and told not to repeat them. The user deletes any that slip through | Recommended; approved 12 Oct 2026 |

## Changed at build time (13 October 2026)

The checks under "Verify at build time" were run and the owner approved these changes with the plan, `docs/superpowers/plans/2026-10-13-step-1-deeper-onboarding.md`, whose table of 24 decisions is the full list. Where this section and the rest of this document disagree, this section wins.

| Change | Why | Decided by |
|---|---|---|
| **The upload limit is 4 MB**, not 5 | Vercel refuses a request body over 4.5 MB | Forced; owner told |
| **The quote on an achievement is read-only.** Every other field can be edited | An edited quote could show "From your CV" beside words the CV never had | Owner, 13 Oct 2026 |
| The file travels as the raw request body, not a multipart form. `python-multipart` and `python-docx` are not added; `pypdf` is the only new package | A form upload writes files over 1 MB to disk. Word files are read with the standard library, which reaches the tables and text boxes CV templates use | Approved with the plan |
| One import is **two model calls side by side** (achievements; CV facts), one AI action. The story bank writes in batches of four | A single combined call took 27 to 34 seconds on the real model | Approved with the plan |
| Up to 8 achievements from a CV or pasted text; 3 to 6 from a voice call | A CV holds more than a short call | Approved with the plan |
| The current course is a real `education` row made from "Your details" and kept in step with it | Step 3 reads one list | Approved with the plan |
| A found job or course matching a saved one fills in its blanks instead of duplicating it | Every CV repeats the current course | Approved with the plan |
| `work_history.is_current` is added; an unknown end month stays empty. All dates are optional | "Null means present" would claim a past job is current when the AI could not read its end date | Approved with the plan |
| One extra route, `POST /api/profile/facts`, saves what the user ticked and links the new achievements | The link can only be made once the job or course exists | Approved with the plan |
| The migration is `005_profile_depth` | 003 and 004 were used by step 2 | Forced |
| **The repository list is `POST /api/github/repos`** with the username in the body, not `GET /api/github/{username}/repos` | A real run showed the typed username in the server log. The same reasoning as step 2's offer check | Found while building |
| "Add a number" shows only when neither the bullet nor a real result has a digit | On a real CV the model left its "Add a number" marker beside a bullet that already said "5 hours a week" | Found while building |
| A GitHub achievement whose quote is not in that repository's README or description is kept without a quote | The same rule as every other source | Found while building |
| A repository with no README and no description is refused before the AI is called | There is nothing to read | Found while building |

**What the checks found.** `pypdf` in its default mode returned every sentence whole and in order from six sample CVs, including two-column Word layouts exported to PDF by Word; its "layout" mode did not and is not used. GitHub allows 60 requests an hour per server address without a token. Vercel's request body limit is 4.5 MB.

## In scope

1. Upload a CV (PDF or .docx) in onboarding and on the Profile page.
2. Import GitHub projects by username.
3. Structured CV facts: education, work history, skills, languages. Extracted by AI, confirmed and editable by the user.
4. Link each achievement to the job or course where it happened.
5. Edit and improve achievements; edit and delete STAR stories.
6. "Build my story bank".
7. Source-aware labels for quotes.

## Out of scope

LinkedIn import; OCR; storing original files; the CV layout and export (step 3); company research (step 5).

## What the user sees

**Onboarding step 2, "Your background"** offers four tiles: Talk to the coach, Upload your CV, Paste text, Add GitHub projects. Any can be used, and more than one.

**After any import** the profile step shows the achievements found, each with its source quote, plus "We also found" listing education, jobs and skills for the user to confirm.

**Profile page** gains three sections above Achievements:

| Section | Each entry holds | Actions |
|---|---|---|
| Work history | Employer, job title, location, country, start and end month (or "present"), one line on what the employer does | Add, edit, delete |
| Education | Institution, qualification, subject, start and end month, grade or classification, country | Add, edit, delete |
| Skills and languages | Skills as tags; languages with level | Add, remove |

The user's current course from "Your details" appears as the first education entry and is not asked for again.

**Achievement cards** gain: an Edit button (all fields, plus "Where did this happen?" choosing a job or course), "Improve with AI" with a one-line note box, and an "Add a number" prompt when the outcome has none.

**Quote labels by source:** voice "You said", pasted text "You wrote", CV "From your CV", GitHub "From your repository".

**GitHub import:** the user types a username, sees their public, non-fork repositories (name, description, main language, stars, last updated), ticks up to 5, and each becomes a project achievement with a link to the repository. The username is saved on the profile.

**Interview coach → STAR stories:** "Build my story bank" (hidden once 8 stories exist), and Edit and Delete on each story.

## Data changes (migration `005_profile_depth`)

| Change | Detail |
|---|---|
| New table `work_history` | `employer`, `job_title`, `location`, `country`, `start_month date`, `end_month date` (null means present), `employer_context text`, `source` |
| New table `education` | `institution`, `qualification`, `subject`, `start_month`, `end_month`, `grade`, `country`, `source` |
| `profiles` | Add `skills text[]`, `languages jsonb` (list of `{language, level}`), `github_username text` |
| `achievements` | Add `work_history_id`, `education_id` (nullable, set null on delete), `source_url text`. Allow `source` values `cv` and `github` as well as `voice` and `paste` |
| `journal_entries` | Allow `type` value `import`, so a CV upload or GitHub import is logged with its extracted text as the transcript |

Both new tables follow the standing rules: `user_id` with cascade delete, row-level security on, no privileges for browser roles.

## API

| Route | Purpose |
|---|---|
| `POST /api/ai/achievements/upload` | Multipart file. Extract text, discard the file, run the same extraction as pasted text with source `cv`. Returns achievements plus proposed education, work history, skills, languages |
| `POST /api/github/repos` | `{username}` → the user's public non-fork repositories (see "Changed at build time") |
| `POST /api/ai/achievements/github` | `{username, repos: [names]}` (1 to 5). Reads each README and description, returns project achievements |
| `POST`, `PATCH`, `DELETE /api/work-history[/{id}]` | Work history |
| `POST`, `PATCH`, `DELETE /api/education[/{id}]` | Education |
| `PUT /api/profile/skills` | Replace skills and languages |
| `PATCH /api/achievements/{id}` | Edit any field, including the link to a job or course |
| `POST /api/ai/achievements/{id}/improve` | `{note}` → rewritten bullet, saved |
| `POST /api/ai/stories/bank` | Write stories for up to 8 achievements without one |
| `PATCH`, `DELETE /api/stories/{id}` | Edit or delete a story |

`POST /api/ai/achievements` (voice and paste) also returns the proposed CV facts. Proposed facts are saved only when the user confirms them.

## AI tasks

| Task | Notes |
|---|---|
| Extraction (changed) | Also returns `education`, `work_history`, `skills`, `languages`, and for each achievement which job or course it belongs to. Receives the existing achievements and must not repeat them. Dates it is unsure of are left empty, never guessed |
| GitHub project to achievement | From repository name, description, languages and README only. The quote comes from the README or description |
| Improve an achievement | Uses the existing fields and the user's note. Must not add any fact that is in neither |
| Story bank | One call, up to 8 stories, one per chosen achievement, covering different competencies where possible |

Each import (one upload, one GitHub batch, one story bank) counts as one AI action.

## Outside services and settings

| Service | Use | Setting |
|---|---|---|
| GitHub REST API | Public repositories and READMEs, no login | `GITHUB_TOKEN` optional: without it GitHub allows about 60 requests an hour per server address, which is tight on shared hosting |
| New Python packages | `pypdf`, `python-docx`, `python-multipart` | – |

## Behaviours that must have tests

In addition to the standing list in `careerai-building-a-step`:

- A 6 MB file, a `.txt` renamed `.pdf`, an image-only PDF and an empty file are each refused with a plain message and never reach the AI.
- The uploaded file's bytes are not written to disk or the database; only extracted text is stored.
- Extracted text over 30,000 characters is cut and the response says so.
- A CV quote is checked against the CV text; a GitHub quote against the README or description (`ai.verbatim`).
- An achievement cannot be linked to another user's job or course (stored as null).
- Deleting a job or course keeps its achievements and clears the link.
- Editing an achievement changes only the fields sent.
- "Improve with AI" keeps the bullet unchanged and returns an error if the model fails.
- The story bank skips achievements that already have a story and never creates more than 8 stories in total.
- GitHub: an unknown username answers 404 "No GitHub user with that name"; a rate-limit answer from GitHub shows "GitHub is busy. Try again in a few minutes."; forks are left out; more than 5 repositories answers 422.
- End month before start month answers 422.
- The model returning a date such as "2021" or "Summer 2022" is stored as empty, not as a wrong month.

## Check by hand

1. Upload a real CV as PDF, then as .docx: achievements, jobs, education and skills appear and are correct enough to confirm.
2. Upload a scanned PDF: the plain message appears.
3. Import two repositories from a real GitHub account: each card links to its repository.
4. Edit an achievement, link it to a job, and use "Improve with AI" with a number.
5. Add, edit and delete a job and a course; reload; changes persist.
6. Build the story bank; edit one story; delete one.
7. A second account sees none of it.

## Task outline

1. Migration and database functions for work history, education, skills, achievement links.
2. Text extraction from PDF and .docx with the size and type checks.
3. Extraction prompt returning CV facts; confirm-and-save flow.
4. Upload route and the onboarding and Profile upload UI.
5. Work history, education and skills sections on the Profile page.
6. Edit and improve achievements.
7. GitHub listing and import.
8. Story bank; edit and delete stories.
9. Source-aware quote labels; privacy page update (uploaded CV text, GitHub username).
10. Live checks, hand checks, documentation.

## Done when

A new user can build a complete profile from an uploaded CV alone, correct anything in it, and has work history, education and skills in the database ready for step 3. All tests pass, the hand checks are done, and `docs/ARCHITECTURE.md` is updated.

## Verify at build time

- Whether `pypdf` reads typical UK and Indian CV layouts (two-column CVs often extract out of order). If quality is poor, tell the owner before choosing another library.
- GitHub's current unauthenticated rate limit and README endpoint.
- Vercel's request body limit for the upload (historically about 4.5 MB on serverless functions). If it is below 5 MB, lower the app's limit to match and say so.
