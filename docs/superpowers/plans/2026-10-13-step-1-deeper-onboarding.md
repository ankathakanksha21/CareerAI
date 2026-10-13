# Step 1: Deeper Onboarding Implementation Plan

> **For agentic workers:** follow `careerai-building-a-step` stage 4. Every task is test-first: write the tests, watch them fail for the right reason, write the code, watch them pass, run the whole suite on its own, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user can build a complete profile from an uploaded CV or their GitHub projects, correct anything the AI got wrong, and ends up with work history, education, skills and a story bank saved in a shape step 3 can build a full UK CV from.

**Architecture:** A file is read in memory into plain text (`cvfile.py`) and thrown away; only the text travels on. One import runs two model calls side by side, one for achievements and one for CV facts, with no database connection open. Achievements are saved at once. Facts (jobs, courses, skills, languages) come back as proposals and are saved only when the user confirms them. GitHub is read through its public API with no login (`github.py`).

**Tech stack:** unchanged, plus one new Python package, `pypdf`. Word files are read with the standard library.

**Step document:** `.claude/skills/careerai-step-1-deeper-onboarding/SKILL.md`. Where this plan differs from it, the difference is listed under "Decisions this plan adds" for the owner to approve.

## Global constraints

- Everything in `CLAUDE.md` applies. The points that bite hardest here:
- **Only real data.** No sample CVs, employers or repositories in the product. Test fixtures use names that cannot be real ("Zzqx Holdings Ltd", "University of Zzqx").
- **Show the source.** A quote shown as "You said", "You wrote", "From your CV" or "From your repository" must be found in the text it came from (`ai.verbatim`), or it is not shown.
- **Uploaded files are never stored.** The bytes are held in memory, read, and dropped. Not written to disk, not written to the database, not logged.
- **Every new table and route** gets a test proving account B cannot read or change account A's rows.
- **No database connection across a model, GitHub or file-reading call.**
- **Each import, each "Improve with AI" and each story bank is one AI action** against the daily limit.
- **All SQL stays in `repo.py`.** `cvfile.py`, `github.py`, `intake.py` and `stories.py` hold parsing, HTTP and pure functions.
- **No key in any response or log.** Failures log the exception type only. Uploaded text and READMEs never reach a log.
- British English, no em dashes in UI copy or prompts.
- Commit after every task with the suite passing. Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push unless asked.

## What the checks before building found (13 October 2026)

| Checked | Result |
|---|---|
| `pypdf` on CV layouts | Six sample CVs made for the test: Word single column, Word two-column table with the name in the page header, each exported to PDF by Word itself, and two designed two-column PDFs (one stored in the worst possible order). In `pypdf`'s default mode every sentence came out whole and in order in all of them, and every fact was present. Its "layout" mode broke sentences in two-column files, so it is not used. A scanned PDF gave no text, as expected |
| The real model on that text | Read the jumbled two-column text correctly: 7 of 7 achievements with exact quotes, both jobs and both courses with the right months and grades. **One combined call took 27 to 34 seconds**, which is why decision 4 below splits it |
| GitHub | Without a token, 60 requests an hour for each server address (confirmed from the reply headers). Repository list, README and "no such user" (404) all behave as documented |
| Vercel | A request body may be at most **4.5 MB**; larger is refused with a 413 before it reaches the app. So decision 1 |

## Decisions this plan adds (for the owner to approve with the plan)

Each fills a gap the step document left to the build session, or changes it for a stated reason.

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| 1 | **Upload limit is 4 MB, not 5** | Vercel refuses anything over 4.5 MB. The step document says to lower the limit to match | A CV over 4 MB must be pasted. Real CVs are rarely over 1 MB |
| 2 | **The quote on an achievement cannot be edited.** Every other field can | The quote is the record of where the bullet came from. If it could be typed over, "From your CV" could be shown beside words the CV never had | The step document says "every field". A user who dislikes a quote must delete the achievement |
| 3 | The file is sent as the raw body of the request, not as a form upload, and `python-multipart` is not added | Form-upload handling writes any file over 1 MB to a temporary file on disk. Reading the raw body keeps it in memory, which is what "read, then discarded" promises | None for users |
| 4 | One import runs **two model calls side by side** (achievements; CV facts) and counts as one AI action | One combined call took about 30 seconds on the real model. Two smaller calls take about half | If the facts call fails and the achievements call works, the achievements are saved and the page says the work history and education could not be read this time |
| 5 | Up to **8 achievements** from one CV or pasted text; 3 to 6 from a voice call, as now | A CV holds more than a three-minute call. More than 8 pushes one import towards a minute | A long CV needs a second upload to pick up the rest (the AI is told what is already saved) |
| 6 | Word files are read with Python's standard library, not `python-docx` | Most CV templates are built from tables and text boxes, which `python-docx` skips unless every one is walked by hand. Tested on a table-layout CV with the name in the header | A very unusual Word file may read badly; the user can paste |
| 7 | The story bank writes in batches of 4, up to two calls side by side, one AI action | Eight stories in one call is about 40 seconds. The step document says "one AI call" | Stories in different batches may share a competency |
| 8 | The current course is a real row in `education`, made from "Your details" and kept in step with it. University, course and graduation month are changed in "Your details"; start month, grade and country are edited on the row. It cannot be deleted | Step 3 then reads one list. Two places to edit the same fact would drift | A little more code in `update_profile` |
| 9 | A found job or course that matches one already saved **fills in its blanks** (dates, grade, location) instead of making a duplicate | Every CV repeats the current course, with the start month and grade the details form never asked for | A wrong match would add a date to the wrong entry; the user sees what will be added and can untick it |
| 10 | `work_history` gets `is_current`. An end month that is not known stays empty | The step document's "null means present" would show "to present" for a past job whose end date the AI could not read | One more column |
| 11 | Dates are optional. An entry without them shows "Add dates" | The AI must leave a date empty when unsure, and such an entry still has to be saveable | Step 3 must cope with missing dates |
| 12 | An employer or institution the AI returns is kept only if at least half the words of its name appear in the text | A code check behind the prompt's "never invent employers" | A name the AI tidied heavily could be dropped; the user adds it by hand |
| 13 | "Improve with AI" is rejected if the new bullet has a number that is in neither the achievement nor the note. It saves at once and offers Undo | Numbers are the invention that hurts most on a CV | A note written as "five" where the AI writes "5" is handled; an unusual wording could be rejected and need a retry |
| 14 | "Add a number" shows when the result begins "Add a number" or when neither the bullet nor the result has a digit | The extraction already writes that marker when no number was given | A bullet whose only digit is a year counts as having a number |
| 15 | GitHub: the username is saved when an import succeeds. A repository already imported is skipped. Nothing checks the account belongs to the user | No login was decided. The card says "From your repository" and links to it | Someone could import another person's public work as their own |
| 16 | GitHub: the README is cut at 6,000 characters, and the main language comes from the repository list rather than a call per repository | 7 GitHub requests per import instead of 16, against 60 an hour without a token | A long README's later sections are not read |
| 17 | `GITHUB_TOKEN` is optional. Recommended before deploying: Vercel shares server addresses, so the 60 an hour may already be used by others | A token lifts it to 5,000 | Without one, imports on Vercel may answer "GitHub is busy" |
| 18 | The employer line ("what the employer does") is filled by the AI only when the text says it or the company is widely known, and is shown for the user to confirm and edit | The step document asks for this line; UK recruiters need it for overseas employers | The AI could describe a small company wrongly. It is never saved without the user confirming |
| 19 | One extra route, `POST /api/profile/facts`, saves everything the user ticked in one go and links the new achievements to their job or course | Achievements are saved before the job they belong to exists, so the link has to be made at confirmation | One more route than the step document lists |
| 20 | Proposed facts live in the browser until confirmed. Leaving the page loses them; uploading the same CV again brings them back without duplicating achievements | "Saved only when the user confirms" | One repeated upload for a user who closes the tab |
| 21 | Imports appear in the Journal under a new "Imports" filter, with the text that was read | The step document logs them as type `import` | None |
| 22 | Language levels are a fixed list: Native, Fluent, Professional, Conversational, Basic | A CV needs a consistent scale | A user wanting "B2" picks the nearest |
| 23 | `vercel.json`: the function's time limit goes from 60 to 120 seconds | An import is about 25 seconds, and one automatic retry could pass 60. Vercel's free plan allows up to 300 | Cannot be verified until something is deployed |
| 24 | The migration is `005_profile_depth` | 003 and 004 were used by step 2 | None |

## Review focus

Inputs most likely to break this, each with a test in the task named.

1. **Hostile or odd files.** Empty, over the limit, a `.txt` renamed `.pdf`, an old `.doc`, a zip that is not a Word file, a password-protected PDF, a corrupt PDF, a 300-page PDF, a Word file that unpacks to hundreds of megabytes, text containing NUL characters (which the database refuses). (Task 4)
2. **Odd model output.** A date such as "2021", "Summer 2022" or "present" as a start; an end before a start; an employer that is not in the text; the same job twice; a `where` that names nothing; a story for an achievement that was not sent; a rewrite with an invented number. (Tasks 6, 7, 8)
3. **Text that is not speech.** A CV line beginning "Coach:" must not be mistaken for a call transcript and wipe every quote; a sentence wrapped across PDF lines must still be matched. (Task 6)
4. **Ownership.** Linking an achievement to another user's job; confirming facts with another user's achievement or entry ids; editing or deleting another user's story, job or course. (Tasks 2, 3, 9)
5. **Limits and partial failure.** The daily limit reached (the file must not be sent to the AI); GitHub's rate limit; the facts call failing while the achievements call works; the same CV uploaded twice. (Tasks 5, 10)

## File map

```
backend/
  migrations/005_profile_depth.sql   create   two tables, three altered, the current course copied in
  cvfile.py                          create   bytes of a PDF or .docx to plain text, with every refusal
  github.py                          create   GitHub client: a user's repositories, one README
  parallel.py                        create   together(): run calls side by side (moved out of jobs.py)
  intake.py                          create   the two extraction calls, linking achievements to jobs and courses, proposals
  stories.py                         create   which achievements the story bank writes for, in which batches
  ai.py                              modify   + month, needs_number, extract_facts, github_achievements, improve, story_bank; extract_achievements and verbatim widened
  repo.py                            modify   + work history, education, skills, achievement editing and links, story editing
  main.py                            modify   + 14 routes; /api/ai/achievements and /api/state widened
  jobs.py                            modify   uses parallel.together
  requirements.txt                   modify   + pypdf
  .env.example                       modify   + GITHUB_TOKEN
  scripts/live_check.py              modify   + the new AI tasks
  scripts/cv_check.py                create   what one real CV file reads as (counts and the first lines, local only)
  tests/                             create   test_cvfile, test_github, test_intake, test_stories, test_repo_history, test_routes_profile
                                     modify   test_migrate, test_ai, test_repo_profile, test_repo_records, test_routes_ai, test_routes_data, test_jobs
frontend/src/
  api.js                             modify   + upload()
  ui.jsx                             modify   + Quote (source-aware label), month helpers
  components/BackgroundInput.jsx     modify   four tiles: coach, upload, paste, GitHub
  components/GitHubImport.jsx        create   username, repository tick-list, import
  components/FoundFacts.jsx          create   "We also found": tick and confirm
  components/History.jsx             create   Work history, Education, Skills and languages sections with their forms
  components/AchievementCard.jsx     create   one achievement: view, edit, where it happened, improve, add a number
  pages/Onboarding.jsx               modify   proposals carried between steps; confirm on Continue
  pages/Profile.jsx                  modify   the three new sections; cards replaced by AchievementCard
  pages/Interview.jsx                modify   Build my story bank; edit and delete a story
  pages/Journal.jsx                  modify   imports
  pages/Privacy.jsx                  modify   uploaded CV text, GitHub
  index.css                          modify   a few classes for the new forms
vercel.json                          modify   maxDuration 120
docs/ARCHITECTURE.md, CLAUDE.md, README.md, the step document   modify
```

---

### Task 1: Schema (`005_profile_depth.sql`)

**Files:** create `backend/migrations/005_profile_depth.sql`; modify `backend/tests/test_migrate.py`.

**Produces:**

```sql
work_history (id, user_id → auth.users cascade, employer text not null, job_title, location, country, employer_context text not null default '',
              start_month date, end_month date, is_current boolean not null default false,
              source text not null default 'manual' check (source in ('manual','voice','paste','cv','github')), created_at, updated_at,
              check (start_month is null or end_month is null or end_month >= start_month),
              check (not (is_current and end_month is not null)))
education    (id, user_id, institution text not null, qualification, subject, grade, country text not null default '',
              start_month date, end_month date, from_details boolean not null default false, source (as above), created_at, updated_at,
              same date check; unique index on (user_id) where from_details)
profiles     + skills text[] not null default '{}', languages jsonb not null default '[]', github_username text
achievements + work_history_id → work_history on delete set null, education_id → education on delete set null, source_url text;
               achievements_source_check replaced: source in ('voice','paste','cv','github')
journal_entries: journal_entries_type_check replaced: type in ('coach','interview','import')
```

Both new tables: row-level security on, all privileges revoked from `anon` and `authenticated`. Last statement copies the current course of every profile that has a university and a course into `education` (`institution` = university, `qualification` = course, `end_month` = graduation date, `country` = 'United Kingdom', `from_details` = true).

- [ ] **Step 1: tests** in `test_migrate.py`: add both tables to `TABLES` (covers RLS and browser privileges); `test_history_and_education_deleted_with_user`; `test_deleting_a_job_or_course_keeps_the_achievement_and_clears_the_link`; `test_end_before_start_rejected` (both tables, `CheckViolation`); `test_current_job_cannot_have_an_end_month`; `test_one_current_course_per_user` (`UniqueViolation` on a second `from_details` row; another user may have one); `test_achievement_sources` (`cv` and `github` accepted, `linkedin` rejected); `test_journal_import_type` (`import` accepted, `other` rejected); `test_profile_defaults` (`skills == []`, `languages == []`, `github_username is None`).
- [ ] **Step 2:** run, see them fail (tables missing).
- [ ] **Step 3:** write the migration; `python migrate.py`.
- [ ] **Step 4:** run the suite; commit `feat: schema for work history, education, skills and achievement links`.

### Task 2: Work history, education and skills (`repo.py`)

**Files:** modify `backend/repo.py`; create `backend/tests/test_repo_history.py`; modify `backend/tests/test_repo_profile.py`.

**Produces:**

```python
ENTRY_FIELDS = {"work_history": ("employer", "job_title", "location", "country", "start_month", "end_month", "is_current", "employer_context"),
                "education": ("institution", "qualification", "subject", "start_month", "end_month", "grade", "country")}
def list_entries(conn, user_id, table) -> list[dict]      # work: current first, then latest; education: the current course first
def get_entry(conn, user_id, table, entry_id) -> dict | None
def add_entry(conn, user_id, table, fields: dict, source: str = "manual") -> dict
def update_entry(conn, user_id, table, entry_id, fields: dict) -> dict | None      # only the fields given
def fill_entry(conn, user_id, table, entry_id, fields: dict) -> dict | None        # only fields that are empty now
def delete_entry(conn, user_id, table, entry_id) -> bool
def set_skills(conn, user_id, skills: list[str], languages: list[dict]) -> dict    # replaces both; returns the profile
def add_skills(conn, user_id, skills: list[str], languages: list[dict]) -> dict    # adds what is not there, ignoring case
def set_github_username(conn, user_id, username: str) -> None
```

`table` is checked against `ENTRY_FIELDS`; anything else raises `ValueError` (it is never user input). Months are stored as the first of the month. `update_profile` also inserts or updates the `from_details` education row. `load_state` gains `work_history` and `education`.

- [ ] **Step 1: tests**: add, list order, update changes only the fields sent, months normalised to day 1; `fill_entry` leaves a field that already has a value and fills an empty one; every function with `user_b` returns nothing and changes nothing; unknown table and unknown field raise `ValueError`; `update_profile` creates the current-course row once, updates it on a second save and never makes a second; `set_skills` replaces, `add_skills` keeps existing and skips "sql" when "SQL" is there; `load_state` has both lists.
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: work history, education and skills in the database layer`.

### Task 3: Editing achievements and stories (`repo.py`)

**Files:** modify `backend/repo.py`, `backend/tests/test_repo_profile.py`, `backend/tests/test_repo_records.py`.

**Produces:**

```python
ACHIEVEMENT_FIELDS = ("title", "uk_version", "skills", "outcome", "scale", "context_note", "work_history_id", "education_id")   # not raw, not source
def add_achievements(conn, user_id, items, source) -> list[dict]     # each item may now carry work_history_id, education_id, source_url
def update_achievement(conn, user_id, achievement_id, fields: dict) -> dict | None
def link_achievements(conn, user_id, achievement_ids: list, *, work_history_id=None, education_id=None) -> int
def imported_urls(conn, user_id) -> set[str]                         # source_url of every achievement that has one
STORY_FIELDS = ("title", "competency", "situation", "task", "action", "result")
def get_story(conn, user_id, story_id) -> dict | None
def update_story(conn, user_id, story_id, fields: dict) -> dict | None
def delete_story(conn, user_id, story_id) -> bool
def achievements_without_story(conn, user_id) -> list[dict]
```

A link is stored only if the job or course is the caller's (`_own`), else null. Setting one link clears the other: an achievement happened in a job or on a course, not both.

- [ ] **Step 1: tests**: update changes only the fields sent and refuses `raw` and `source` (`ValueError`); linking to `user_b`'s job stores null; setting `education_id` clears `work_history_id`; deleting the job keeps the achievement with a null link; `link_achievements` ignores ids that are not the caller's; story update, delete and get for owner and for `user_b`; `achievements_without_story` leaves out one that has a story; `imported_urls`.
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: edit achievements and stories; link achievements to a job or course`.

### Task 4: Reading a CV file (`cvfile.py`)

**Files:** create `backend/cvfile.py`, `backend/tests/test_cvfile.py`; modify `backend/requirements.txt` (+ `pypdf`).

**Produces:**

```python
MAX_BYTES = 4 * 1024 * 1024
MAX_CHARS = 30_000      # the same cap as pasted text
MIN_CHARS = 100         # fewer non-space characters than this is a scan, not a CV
MAX_PAGES = 20
MAX_UNPACKED = 20 * 1024 * 1024
class Unreadable(Exception): ...            # str(e) is the message shown to the user
def text(data: bytes) -> tuple[str, bool]   # (plain text, whether it was cut at MAX_CHARS)
```

The type is decided from the bytes, never from a name: `%PDF-` is a PDF; a zip holding `word/document.xml` is a Word file. PDF: `pypdf` default extraction, first `MAX_PAGES` pages, stopping once `MAX_CHARS` is passed; an encrypted file is tried with an empty password. Word: the page headers, then the body, every paragraph in document order including tables and text boxes, skipping the `mc:Fallback` copy Word keeps of each text box; a part declaring a DOCTYPE is refused. Cleaning: NUL and other control characters removed, the replacement character Word bullets turn into dropped, three or more blank lines collapsed.

| Input | Message |
|---|---|
| No bytes | "That file is empty." |
| Over `MAX_BYTES` | "That file is over 4 MB. Upload a smaller one, or paste the text instead." |
| Neither type (including a renamed `.txt` and an old `.doc`) | "Upload a PDF or a Word (.docx) file." |
| Password needed | "This PDF is password-protected. Remove the password, or paste the text instead." |
| Cannot be opened, or unpacks too large | "We could not open that file. Save it again as PDF or .docx, or paste the text instead." |
| Fewer than `MIN_CHARS` of text | "We could not read any text in this file. Paste the text instead." |

- [ ] **Step 1: tests.** Fixtures are built in memory: a PDF written by a small helper (one text stream per page), a Word file written with `zipfile`. One test per row of the table, plus: a PDF and a Word file each give back their sentences in order; a Word table and a page header are read; a text box is read once, not twice; a 300-page PDF reads only 20 pages; text over 30,000 characters comes back cut with `True`; NUL characters never appear in the result; a zip whose `word/document.xml` claims 500 MB is refused without being unpacked; `builtins.open` and `tempfile` are replaced with functions that fail the test, proving nothing touches the disk.
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: read a PDF or Word CV into text, in memory`.

### Task 5: GitHub client (`github.py`)

**Files:** create `backend/github.py`, `backend/tests/test_github.py`; modify `backend/config.py` (`github_token()`), `backend/.env.example`.

**Produces:**

```python
USERNAME = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"      # GitHub's own rule; also keeps anything odd out of the address
README_CHARS = 6_000
class GitHubError(Exception): status: int; message: str
def repos(username: str) -> list[dict]     # public, not forks, most recently pushed first, at most 100:
                                           # {"name", "description", "language", "stars", "pushed_on": date, "url"}
def readme(username: str, repo: str) -> str   # "" when the repository has none
def _client() -> httpx.Client              # replaced in tests; sends the token when one is set
```

| GitHub answers | Raised |
|---|---|
| 404 for the user | `GitHubError(404, "No GitHub user with that name")` |
| 403 or 429 with no requests remaining | `GitHubError(429, "GitHub is busy. Try again in a few minutes.")` |
| Timeout, connection error, anything else | `GitHubError(502, "We could not reach GitHub. Try again shortly.")` |

`url` is used only if it begins `https://github.com/`; otherwise it is rebuilt from the username and repository name.

- [ ] **Step 1: tests** with `_client` replaced: the request shape (`type=owner`, `sort=pushed`, `per_page=100`, the API version header, the token header only when set); forks left out; each row of the table; a README answering 404 gives `""`; a long README is cut; a link from outside github.com is replaced; the token appears in no error message and no log line (`caplog`).
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: GitHub client for public repositories and READMEs`.

### Task 6: Extraction (`ai.py`)

**Files:** modify `backend/ai.py`, `backend/tests/test_ai.py`.

**Produces:**

```python
LANGUAGE_LEVELS = ("Native", "Fluent", "Professional", "Conversational", "Basic")
MAX_ITEMS = {"voice": 6, "paste": 8, "cv": 8}
def month(value) -> date | None                       # "2023-07" → date(2023, 7, 1); anything else → None
def needs_number(achievement: dict) -> bool           # decision 14
def verbatim(quote: str, text: str, speech: bool = True) -> str
def extract_achievements(text, profile, source="voice", existing=()) -> {"items": [... + "where": str], "pitch": str}
def extract_facts(text, profile, work=(), education=()) -> {"work_history": [...], "education": [...], "skills": [str], "languages": [{"language", "level"}]}
```

`verbatim(..., speech=False)` treats all the text as the user's (no "Coach:" filtering) and, when it falls back to the closest sentence, joins a sentence that was wrapped across lines. `extract_achievements` is told what is already saved and must not repeat it; an item whose bullet matches a saved one, ignoring case and punctuation, is dropped in code; `where` is the employer or institution as the text names it, or empty. `extract_facts` returns entries with `start_month`, `end_month` (dates or None) and `is_current`; an entry is dropped when its name is empty, fails decision 12, or repeats an earlier one; a language level outside the list becomes `""`; skills are de-duplicated ignoring case and capped at 40.

- [ ] **Step 1: tests**: `month` for "2023-07", "2023-7", "2021", "Summer 2022", "present", "", None, "2023-13"; `needs_number` for the marker, no digit, and a real number; `verbatim` with `speech=False` on a CV containing a "Coach: Under-15 football" line, and on a sentence split over three lines; extraction prompt carries the saved achievements and the right item cap for each source; a repeat of a saved bullet is dropped; quotes for `cv` are checked against the CV text; facts: "present" sets `is_current`, an end before a start drops the end, an employer not in the text is dropped, a duplicate is dropped, "2021" gives an empty month, an unknown level becomes `""`, an empty reply gives four empty lists and does not raise.
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: extraction returns where each achievement happened, and CV facts`.

### Task 7: GitHub projects, improve, story bank (`ai.py`)

**Files:** modify `backend/ai.py`, `backend/tests/test_ai.py`.

**Produces:**

```python
def github_achievements(repos: list[dict]) -> dict[int, dict]   # repos: {"n", "name", "description", "language", "readme"} → {n: achievement item}
def improve(achievement: dict, note: str) -> dict               # {"uk_version", "outcome", "scale"}
def story_bank(achievements: list[dict], taken: list[str]) -> dict[int, dict]   # achievements carry "n"; taken: competencies already covered
```

`github_achievements`: one item per repository at most, from its name, description, language and README only; `raw` is checked against that repository's own description and README; a repository the model skipped or whose quote cannot be found is absent; raises `AIError` when nothing comes back. `improve`: every number in the three returned fields must appear in the achievement's existing fields or the note (digits compared with commas removed; "one" to "twelve" in the inputs count as their digits); a reply that breaks this counts as a failed attempt and is retried once, then `AIError`. `story_bank`: one story per achievement sent, normalised exactly as `star` normalises (shared helper); a number that was not sent, or sent twice, is ignored.

- [ ] **Step 1: tests**: GitHub quote from another repository's README is dropped; a repository number that was not sent is ignored; all empty raises; improve keeps a number from the note, rejects an invented one, accepts "5" when the note says "five", retries once then raises; story bank ignores an unknown and a repeated number, normalises strength, and returns only what it was sent.
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: AI tasks for GitHub projects, improving a bullet and the story bank`.

### Task 8: Putting an import together (`parallel.py`, `intake.py`, `stories.py`)

**Files:** create `backend/parallel.py`, `backend/intake.py`, `backend/stories.py`, `backend/tests/test_intake.py`, `backend/tests/test_stories.py`; modify `backend/jobs.py` and `backend/tests/test_jobs.py` (use `parallel.together`).

**Produces:**

```python
# parallel.py
def together(work, items, workers: int = 8) -> list

# intake.py
FACTS_FAILED = "We could not pick out your education and work history this time. Add them on your Profile page."
def read(text, profile, source, achievements, work, education) -> dict
    # both calls side by side → {"items", "pitch", "facts": dict | None}. AIError from the achievements call propagates; from the facts call gives facts None
def place(items, facts, work, education) -> list[dict]
    # each item gains work_history_id or education_id when its "where" names a saved entry, else "proposal": ("work_history" | "education", index) or None
def proposals(facts, saved_items, work, education, profile) -> dict
    # {"work_history": [entry + "achievement_ids" + optional "id" and "adds"], "education": [...], "skills": [new only], "languages": [new only]}
def same(a: str, b: str) -> bool     # two names for one employer or institution: equal, or one contains the other, ignoring case and punctuation

# stories.py
BANK, BATCH = 8, 4
def pick(without_story: list[dict], story_count: int) -> list[dict]   # at most BANK - story_count; those with a number first, then newest
def write(chosen: list[dict], taken: list[str]) -> tuple[list[tuple[str, dict]], int]   # [(achievement_id, story)], how many were missed
```

A proposed entry that is `same` as a saved one (and, for education, has the same qualification and subject words) carries the saved entry's `id` and `adds`, the fields it would fill; if it would add nothing it is left out.

- [ ] **Step 1: tests**: `read` runs both calls even when the facts call fails, and returns `facts None`; an achievements failure raises; `place` links "Systems Engineer, Zzqx Holdings Ltd, Pune" to the saved "Zzqx Holdings Ltd", links to a proposed entry by index, and leaves "PROJECTS" unlinked; `proposals` leaves out a course already saved in full, marks one that adds a start month and grade, drops skills already on the profile ignoring case, and attaches each new achievement's id to its entry; `stories.pick` never returns more than `8 - story_count` and returns nothing at 8; `stories.write` splits 7 into batches of 4 and 3, keeps one batch's stories when the other fails, raises when all fail.
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: run an import as two calls side by side and work out what to propose`.

### Task 9: Routes for data (`main.py`)

**Files:** modify `backend/main.py`; create `backend/tests/test_routes_profile.py`; modify `backend/tests/test_routes_data.py`.

| Route | Body | Answers |
|---|---|---|
| `POST /api/work-history`, `PATCH`, `DELETE /api/work-history/{id}` | the `work_history` fields | the entry; 204 |
| `POST /api/education`, `PATCH`, `DELETE /api/education/{id}` | the `education` fields | the entry; 204 |
| `PUT /api/profile/skills` | `{skills: [≤60], languages: [{language, level}] ≤10}` | the profile |
| `POST /api/profile/facts` | `{source, work_history: [entry + achievement_ids + id?] ≤20, education: [same] ≤20, skills, languages}` | `{work_history, education, profile}` |
| `PATCH /api/achievements/{id}` | any of `ACHIEVEMENT_FIELDS` | the achievement |
| `PATCH`, `DELETE /api/stories/{id}` | any of `STORY_FIELDS` | the story; 204 |

`/api/state` gains `work_history`, `education`, `options.language_levels`, and `needs_number` on each achievement. Months arrive as dates and are stored as the first of the month. 422 messages: "The end month cannot be before the start month."; on the current course, changing institution, qualification or end month, or deleting it: "Your current course comes from Your details. Change it there."

- [ ] **Step 1: tests**, for every route: 401 without a token, 422 for a malformed id, 404 for another user's id. Plus: only the fields sent change; end before start is 422 from both the validator and the database check; a current job with an end month is 422; the current course cannot be deleted or renamed but takes a grade and start month; `facts` creates entries with the given source, fills blanks on one with an `id`, links only the caller's achievements, adds skills without repeating, and saves nothing if any part is invalid; an achievement cannot be linked to `user_b`'s job (stored null, 200); `raw` in a PATCH is rejected (422); a story edit and delete; `user_b` sees none of it in `/api/state`.
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: routes for work history, education, skills, and editing achievements and stories`.

### Task 10: Routes for imports and AI (`main.py`)

**Files:** modify `backend/main.py`, `backend/tests/test_routes_ai.py`, `backend/tests/test_routes_profile.py`.

| Route | Does |
|---|---|
| `POST /api/ai/achievements` (changed) | As now, through `intake.read`. Answers `{items, pitch, facts, notice}`. With no new achievements but facts found, answers 200 with an empty `items`; with neither, the existing 422 |
| `POST /api/ai/achievements/upload` | Raw body. Read at most `MAX_BYTES + 1` bytes (413 with the over-4-MB message beyond that, also when `Content-Length` already says so) → `cvfile.text` (422 with its message) → count one AI action → `intake.read` with source `cv` → save → journal entry of type `import`, "Profile built from your uploaded CV", the extracted text as its transcript. Answers as above plus `cut` |
| `GET /api/github/{username}/repos` | 422 unless the name matches `github.USERNAME`. `{username, repos}`, each marked `imported` when its link is already on an achievement |
| `POST /api/ai/achievements/github` | `{username, repos: [1 to 5 names]}`. Lists the account again; a name not in the list is 422 "Pick repositories from the list."; already-imported ones are skipped (all skipped: 422 "Those repositories are already in your profile."); READMEs fetched side by side; then one AI action; saves achievements with source `github` and `source_url`, the username, and a journal entry "Projects imported from GitHub" |
| `POST /api/ai/achievements/{id}/improve` | `{note ≤300}` → `{achievement, previous: {uk_version, outcome, scale}}` |
| `POST /api/ai/stories/bank` | 400 "Build your profile first." with no achievements; 400 "You already have 8 stories." or "Every achievement already has a story."; else `{stories, notice}` |

Order in every route: free checks first, then the AI action is counted, then the model, then one write. A GitHub or file failure never uses up an AI action.

- [ ] **Step 1: tests**: upload of a real in-memory PDF saves achievements with source `cv` and a journal entry whose transcript is the extracted text and not the file; each `cvfile` refusal answers its message, calls no AI function and records no usage; a 5 MB body is 413; at the daily limit each of the four AI routes (upload, GitHub import, improve, story bank) answers 429 and calls no AI function; a cut file answers `cut: true`; `open` and `tempfile` replaced as in task 4 during an upload; the facts call failing still saves achievements and returns the notice; the achievements call failing saves nothing (502); the same CV twice returns no duplicate achievements and still proposes facts; GitHub: 404, busy, 422 for six names, for a bad username and for a name not in the list, forks never listed, an imported repository skipped, `source_url` saved, the username saved only on success, no token in any response; improve: bullet unchanged and 502 when the model fails, 404 for another user's achievement, `previous` returned; bank: skips achievements with a story, never takes the total past 8, one failed batch gives a notice, all failed saves nothing; no database connection is open during any of the new model calls (the existing check, extended).
- [ ] **Step 2 to 4:** fail, implement, pass, suite, commit `feat: CV upload, GitHub import, improve with AI and the story bank`.

### Task 11: Importing in the browser

**Files:** modify `frontend/src/api.js`, `ui.jsx`, `components/BackgroundInput.jsx`, `pages/Onboarding.jsx`, `index.css`; create `components/GitHubImport.jsx`, `components/FoundFacts.jsx`.

- `api.upload(path, file)` sends the file as the raw body with `Content-Type: application/octet-stream`, through the same token and retry path.
- `ui.jsx`: `QUOTE_LABEL = { voice: 'You said', paste: 'You wrote', cv: 'From your CV', github: 'From your repository' }`, a `Quote` component used wherever an achievement's quote is shown, `fmtMonth`, `period(entry)` ("Jul 2023 to Aug 2025", "Jul 2023 to present", "Add dates").
- `BackgroundInput`: four tiles in the step document's order and words. Upload: a file picker for `.pdf` and `.docx`, refused in the browser when over 4 MB with the server's message, "Reading your CV. This takes about half a minute." while it runs, and the cut notice when it applies. `onBuilt(result)` now receives `facts` and `notice`.
- `GitHubImport`: username, "Find repositories", the list (name, description, language, stars, last updated) with at most 5 ticks, already-imported ones shown as such, "Import".
- `FoundFacts`: "We also found", every item ticked to begin with; a matched entry reads "Adds to <entry>: start month, grade". Profile page: "Add to my profile" and "Dismiss". Onboarding: the step's main button reads "Save and continue" and confirms what is ticked before finding roles.
- Onboarding keeps the proposals in its own state so they survive moving between "Your background" and "Your profile".

- [ ] **Step 1:** build the pieces. **Step 2:** `npm run lint && npm run build`. **Step 3:** signed-out pages in the browser pane with no console errors. **Step 4:** commit `feat: upload a CV or import GitHub projects, and confirm what was found`.

### Task 12: The Profile page

**Files:** create `frontend/src/components/History.jsx`, `components/AchievementCard.jsx`; modify `pages/Profile.jsx`, `index.css`.

- Three sections above Achievements, as the step document lays them out: Work history, Education, Skills and languages. Each entry shows one line and its period, with Edit and Delete; "Add" opens the same form empty. Months are a month and a year list. The current course shows "From your details" in place of Delete, with its university, course and end month read-only.
- Every section has an empty state with one action ("Add a job", "Add a course", "Add a skill").
- `AchievementCard`: the existing card, plus Edit (title, bullet, result, scale, skills, note for UK recruiters, "Where did this happen?"), "Improve with AI" with a one-line note box, an "Add a number" prompt when `needs_number`, where it happened under the title, a link to the repository for a GitHub project, and "Rewritten. Undo" after an improvement.

- [ ] **Step 1:** build. **Step 2:** lint and build. **Step 3:** commit `feat: work history, education, skills and editable achievements on the Profile page`.

### Task 13: Stories, Journal, Privacy

**Files:** modify `frontend/src/pages/Interview.jsx`, `Journal.jsx`, `Privacy.jsx`.

- Stories tab: "Build my story bank" (hidden at 8 stories or when every achievement has one), "Writing your stories. This takes about half a minute.", then Edit and Delete on each story.
- Journal: a third filter, "Imports"; an import shows no "with"; its link reads "View the text we read".
- Privacy: the text read from an uploaded CV is kept and the file is not; the GitHub username and the public text of imported repositories; GitHub added under "Who processes it" ("We send it the username you type, nothing else about you").

- [ ] **Step 1:** build. **Step 2:** lint and build. **Step 3:** commit `feat: story bank, imports in the journal, privacy notice`.

### Task 14: Verify and document

**Files:** modify `backend/scripts/live_check.py`, `vercel.json`, `docs/ARCHITECTURE.md`, `CLAUDE.md`, `README.md`, the step document; create `backend/scripts/cv_check.py`.

- [ ] **Step 1:** `live_check.py` gains one real call each for: achievements from CV text, CV facts, both side by side (timed), GitHub projects, improve (a note with a number, and proof an invented number is refused), story bank of four (timed). Run it.
- [ ] **Step 2:** `scripts/cv_check.py <file>`: how many characters a real file reads as, whether it was cut, and its first 20 lines, on the local screen only.
- [ ] **Step 3:** suite with 0 skipped; lint and build.
- [ ] **Step 4:** the seven hand checks in the step document, with the owner signed in. The owner uploads their own CV and types their own GitHub username.
- [ ] **Step 5:** `vercel.json` time limit to 120 seconds.
- [ ] **Step 6:** `docs/ARCHITECTURE.md` (roadmap, decisions, code map, data model, API, AI layer, security, tests, a verification record for step 1, limitations), `CLAUDE.md` (new command), the step document (status, "Changed at build time", "Where it stands"). Commit.
- [ ] **Step 7:** final report to the owner: built, verified and how, not verified, every judgement call, what they need to do.

## Order and what blocks what

Tasks 1 to 3 are the database. 4 and 5 stand alone. 6 and 7 are the AI tasks. 8 needs 6 and 7. 9 needs 1 to 3. 10 needs everything before it. 11 to 13 need 9 and 10. Nothing is blocked on the owner until the hand checks in task 14. A `GITHUB_TOKEN` is not needed to build or test.
