# Step 2: Real Jobs Implementation Plan

> **For agentic workers:** follow `careerai-building-a-step` stage 4. Every task is test-first: write the tests, watch them fail for the right reason, write the code, watch them pass, run the whole suite, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status, 12 October 2026:** tasks 1 to 12 are built and committed. Still open: task 5 step 1 (looking at Reed's real replies) and, in task 13, everything that needs the Reed key or the owner signed in. Task 5 was built against Reed's documented reply because no key was available. Three things changed from this plan while building, each for a stated reason: the offer check became `POST /api/visa-facts` so an offer never reaches a log; `SCORE_BATCH` is 5, so scoring is three calls side by side; and a repost of a job the user already has, or dismissed, is never matched again.

**Goal:** A signed-in user who has picked target roles opens Jobs and sees real, current Reed adverts for those roles and locations, each scored against their own achievements, labelled with what the gov.uk sponsor register says about the employer and the current visa salary figures, and can save, tailor, practise for, track or dismiss any of them in one click.

**Architecture:** Reed is searched server-side through a shared six-hour cache. Listings and the sponsor register are shared public tables with no `user_id`; each user's view of a listing is a private `job_matches` row. A refresh reads its plan in one short transaction, calls Reed and the model with no connection open, then writes. The register is reloaded weekly from gov.uk by a scheduled job or a script.

**Tech stack:** unchanged. No new dependencies: `httpx` for Reed and gov.uk, the standard library for CSV and HTML.

**Step document:** `.claude/skills/careerai-step-2-real-jobs/SKILL.md`, including its "Changed at build time" section, which this plan follows.

## Global constraints

- Everything in `CLAUDE.md` applies. The points that bite hardest here:
- **Only real data.** No sample jobs, no sample sponsors, no made-up salaries. Empty states instead.
- **Shared tables are the one exception to the per-user rule** and hold no personal data: `job_listings`, `job_searches`, `job_search_results`, `sponsors`, `reference_meta`. They still have row-level security on and no browser privileges. `job_matches` is per user and every function touching it takes `(conn, user_id, ...)`.
- **No database connection across Reed, gov.uk or model calls.**
- **All SQL stays in `repo.py`.** `reed.py`, `sponsors.py`, `jobs.py` and `visa.py` hold HTTP calls and pure functions.
- **Tests run against the real database**, where the real register and real listings will be present. Tests use names that cannot occur in real data (for example "Zzqx Holdings Ltd") and never assert on whole-table counts.
- **No key in any response or log.** Reed's key travels in the Basic-auth header. Failures log the exception type only.
- Test fixtures use obviously synthetic values in Reed's real field shape.
- British English, no em dashes in UI copy or prompts.
- Commit after every task with the suite passing. Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push unless asked.

## Decisions this plan adds (for the owner to approve with the plan)

These fill gaps the step document left to the build session. Each is a judgement call.

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| 1 | Each search runs as two Reed calls: one for direct employers, one for recruitment agencies | Reed's results do not say who posted an advert, and the sponsor label must not treat an agency as the employer. Filtering by poster is the only exact way to know | Twice the Reed calls |
| 2 | Up to 3 job titles per target role, in each preferred location; at most 20 searches per refresh. If more are due, the page offers "Search the remaining N" | Keeps one refresh inside Vercel's 60-second limit and polite to an API with no published limit | A user with many roles and cities clicks once more |
| 3 | Reed's separate "graduate" filter is not searched. Senior titles are hidden by default instead, and fit scoring does the rest | It would add a third call per search for little gain | Some graduate-scheme adverts with unusual titles are missed |
| 4 | Sponsor status is stored on the shared listing, not on each user's match, and recomputed for all listings when the register reloads | It is a fact about the advert, identical for every user | None for users |
| 5 | "Possible match" means the advert's employer name is the start of a longer registered name ("Tesco" and "Tesco Stores Limited"). Never the other way round, so "Acme Recruitment" does not match "Acme" | Deterministic and explainable. No fuzzy matching | Some true matches under very different registered names show as "not found", which the label already warns about |
| 6 | "Sponsors only" keeps both "on the register" and "possible match" | Hiding possible matches would hide many large employers | A few non-sponsors appear, clearly labelled |
| 7 | Seen-marking is its own call (`POST /api/jobs/seen`), not a side effect of `GET /api/jobs` | The app runs React in strict mode, which loads pages twice in development; a GET that changes data would wipe the "new" markers | One extra route |
| 8 | "Add to tracker" is one server route (`POST /api/jobs/{match_id}/track`) that saves the job and creates the application together | Makes "link, posted date and sponsor status carry through" one tested operation | One extra route |
| 9 | Saving a job fetches the full advert from Reed at that moment if only the short version is stored. If Reed cannot be reached, the save fails with a message; nothing half-saved | The CV tailor needs the full description | A save can fail when Reed is down |
| 10 | Saving a listing does not spend an AI action. Its summary is the first 300 characters of the advert, and its role family comes from the search that found it | The search already knows the family | Saved listings have no AI keyword list until tailored |
| 11 | A salary counts as annual only when Reed's details say so, or when the search figure is £10,000 or more. Anything else is shown as "a rate, see the advert" and gets no visa comparison | Reed's search results give numbers with no period | A monthly figure of £10,000 or more would be misread as annual. Very rare |
| 12 | Fit scoring: 15 jobs per refresh in two model calls run side by side, counted as one AI action. If one call fails, the other's results are kept and the page says some jobs were not scored | Halves the wait and the damage from one bad reply | Slightly more complex than one call |
| 13 | If today's AI allowance is used up, the refresh still fetches and shows jobs, unscored, with a notice. It does not answer 429 | The fetch succeeded; hiding it would be wrong | None |
| 14 | "Few sponsor-listed roles" finding fires for a target role when at least 10 current adverts name their employer and under 20% of those employers are on the register | A threshold is needed; these are conservative | Tunable constants |
| 15 | Home shows "N new matching jobs posted in the last 48 hours" ahead of tracker findings, counting only jobs scored 40% or more and not yet seen | The step document says it becomes the next best step when there are any | Ordering preference |
| 16 | Reed gives a posting date, not a time. "Last 48 hours" means posted today, yesterday or the day before, UK time | No time is available | Up to a day of slack |
| 17 | `profiles.jobs_last_seen_at` from the step document is not added; the match status (`new`, `seen`) carries the same information | One source of truth | None |
| 18 | "Reed" is added to the application sources and counted as a job board in tracker statistics | Applications created from listings need a truthful source | None |

## Review focus

Inputs most likely to break this, each with a test in the task named.

1. **Reed's data is untidy.** Missing employer, null salary, day rates, HTML descriptions, dates as `dd/mm/yyyy`, the same advert reposted under a new id, a link that is not on reed.co.uk. (Tasks 5, 7)
2. **Employer names.** Agencies, trading-as names, "&" against "and", punctuation, two-letter names, the same name registered in several towns. (Task 2)
3. **Odd model output.** A job number that was not sent, a `shown_by` that is not one of the user's achievements, no requirements, the same job twice, a truncated reply. (Task 4)
4. **Limits and timing.** No target roles, no achievements, the AI allowance used up mid-refresh, Reed down or slow, a register file that is empty or has changed shape. (Tasks 2, 5, 8)
5. **Privacy across the shared tables.** Two users read one listing; neither sees the other's match, saved or hidden state. (Tasks 6, 8)

## File map

```
backend/
  migrations/003_jobs.sql       create   six new tables, two altered
  sponsors.py                   create   name normalising, register download and parsing
  visa.py                       create   loads data/visa_rules.json, builds the salary facts
  data/visa_rules.json          create   figures, sources, date checked
  reed.py                       create   Reed client: search, details, parsing, HTML to text
  jobs.py                       create   search plan, senior filter, de-duplication, shortlist, fit maths, parallel fetch
  ai.py                         modify   + score_jobs
  repo.py                       modify   + listings, searches, matches, sponsors, market figures
  analytics.py                  modify   + sponsor finding, "Reed" source, next-step copy
  config.py                     modify   + jobs_configured(), cron_secret()
  main.py                       modify   + nine routes, state additions
  scripts/refresh_sponsors.py   create   load the register from the command line
  scripts/reed_check.py         create   one real search and one real details call; prints field names only
  scripts/live_check.py         modify   + fit scoring check
  .env.example                  modify   + REED_API_KEY, CRON_SECRET
  tests/test_sponsors.py, test_visa.py, test_reed.py, test_jobs.py,
        test_repo_jobs.py, test_routes_jobs.py                       create
  tests/test_migrate.py, test_ai.py, test_analytics.py, test_routes_data.py, test_config.py   modify
frontend/src/
  pages/Jobs.jsx                create   the Jobs page
  ui.jsx                        modify   menu item, FamilyCard market line, shared labels
  App.jsx                       modify   page registration, new-jobs count
  pages/Home.jsx, Pathways.jsx, Applications.jsx, Resume.jsx, Privacy.jsx   modify
  index.css                     modify   job card styles
vercel.json                     modify   weekly scheduled job
docs/ARCHITECTURE.md, the step document   modify at the end
```

---

### Task 1: Schema (`003_jobs.sql`)

**Files:** create `backend/migrations/003_jobs.sql`; modify `backend/tests/test_migrate.py`.

**Schema:**

| Table | Columns |
|---|---|
| `job_listings` (shared) | `id uuid pk`, `source text`, `source_id text`, unique together; `title`, `employer`, `employer_key text` (normalised), `posted_by` (`employer` or `agency`), `location`, `salary_min numeric`, `salary_max numeric`, `salary_annual boolean`, `description`, `description_is_full boolean`, `url`, `posted_on date`, `sponsor_status` (`listed`, `possible`, `not_found`, `agency`), `sponsor_name text`, `fetched_at` |
| `job_searches` (shared) | `id uuid pk`, `source`, `query`, `location`, unique together; `fetched_at` |
| `job_search_results` (shared) | `search_id`, `listing_id`, both cascading; primary key on the pair |
| `sponsors` (shared) | `id bigint identity`, `name`, `name_key`, `town`, `county`, `route`, `rating`; index on `name_key text_pattern_ops` |
| `reference_meta` (shared) | `key text pk`, `loaded_at`, `published_on date`, `source_url`, `row_count int` |
| `job_matches` (per user) | `id uuid pk`, `user_id` (cascade), `listing_id` (cascade), unique together; `role_family_id` (set null), `search_location`, `fit_percent int 0..100`, `fit_label` (`direct`, `near`, `stretch`, `none`), `shown jsonb`, `gaps jsonb`, `fit_from_summary boolean`, `status` (`new`, `seen`, `saved`, `hidden`), `first_seen_at`, `scored_at` |
| `saved_jobs` | add `listing_id uuid` (set null), `posted_on date` |
| `profiles` | add `include_senior boolean not null default false` |

Row-level security on, and all privileges revoked from `anon` and `authenticated`, for all six new tables.

- [ ] **Step 1: Failing tests** in `test_migrate.py`:
  - add the six tables to `TABLES` (covers existence, RLS, no policies, no browser privileges);
  - `test_job_match_deleted_with_user`: a match for `user_a` disappears when the login is deleted; the shared listing stays;
  - `test_match_and_search_results_deleted_with_listing`: deleting a listing removes its matches and search links, and sets `saved_jobs.listing_id` to null while the saved job stays;
  - `test_listing_unique_per_source`: the same `(source, source_id)` twice raises `UniqueViolation`;
  - `test_one_match_per_user_per_listing`: the same pair twice raises; another user may match the same listing;
  - `test_fit_label_and_status_are_checked`: `fit_label = 'perfect'` and `status = 'gone'` raise `CheckViolation`.
- [ ] **Step 2: Run.** Expected: failures (tables missing).
- [ ] **Step 3: Write the migration; apply with `python migrate.py`.**
- [ ] **Step 4: Run the suite.** Expected: all pass.
- [ ] **Step 5: Commit** `feat: schema for job listings, matches and the sponsor register`.

---

### Task 2: The sponsor register (`sponsors.py`)

**Files:** create `backend/sponsors.py`, `backend/scripts/refresh_sponsors.py`, `backend/tests/test_sponsors.py`; modify `backend/repo.py`.

**Interfaces:**
- `sponsors.normalise(name: str) -> str`: lower case; `&` becomes `and`; punctuation becomes spaces; a leading `the` and trailing `ltd`, `limited`, `plc`, `llp`, `lp`, `inc`, `group`, `holdings`, `uk`, `co`, `company` are dropped repeatedly; spaces collapsed.
- `sponsors.keys(name: str) -> list[str]`: the key of the legal name; for "X T/A Y" or "X trading as Y", the keys of both X and Y.
- `sponsors.latest() -> {"url": str, "published_on": date}`: reads the gov.uk content API for the publication and returns its CSV attachment.
- `sponsors.parse(text: str) -> list[dict]`: rows `{"name","town","county","route","rating"}` for route `Skilled Worker` only, names trimmed. Raises `RegisterError` if the header is not exactly the five expected columns or fewer than `MIN_ROWS = 50_000` rows survive.
- `sponsors.refresh() -> {"rows": int, "published_on": date}`: `latest`, download, `parse`, then one transaction: `repo.replace_sponsors` and `repo.recheck_listing_sponsors`. Any failure before the transaction leaves the stored register untouched.
- `repo.replace_sponsors(conn, rows, *, published_on, source_url) -> int`: delete all, insert in chunks of 5,000 with `unnest`, one row per key from `sponsors.keys`, update `reference_meta['sponsors']`.
- `repo.find_sponsor(conn, employer: str) -> {"status": "listed"|"possible"|"not_found", "name": str | None}`: exact key match first; otherwise, for a key of 4 characters or more, the shortest registered key beginning with `<key> `. Route `Skilled Worker` only.
- `repo.register_meta(conn) -> dict | None`.
- `repo.recheck_listing_sponsors(conn) -> int`: recomputes `sponsor_status` and `sponsor_name` for every listing whose `posted_by` is `employer`.

- [ ] **Step 1: Failing tests.**
  - `test_normalise_company_forms`: "Zzqx Ltd", "ZZQX LIMITED", "Zzqx", " The Zzqx Group (UK) Ltd. " all give `zzqx`.
  - `test_normalise_keeps_distinguishing_words`: "Zzqx Recruitment" gives `zzqx recruitment`.
  - `test_normalise_ampersand_and_punctuation`: "Zzqx & Sons, Ltd" equals "Zzqx and Sons Limited".
  - `test_keys_for_trading_as`: "ZZQX FOODS LTD T/A Qqzz Kitchen" gives `["zzqx foods", "qqzz kitchen"]`; "trading as" works the same; a plain name gives one key.
  - `test_parse_keeps_skilled_worker_only`: a fixture with two Skilled Worker rows and one "Creative Worker" row (and `MIN_ROWS` patched to 1) returns the two, trimmed.
  - `test_parse_rejects_empty_file`, `test_parse_rejects_changed_header`, `test_parse_rejects_too_few_rows`: each raises `RegisterError`.
  - `test_latest_reads_attachment` (HTTP faked): returns the CSV address and the publication date; a reply with no CSV attachment raises `RegisterError`.
  - `test_find_sponsor_exact` (db): after inserting "Zzqx Holdings Ltd", lookups for "Zzqx Ltd", "ZZQX LIMITED" and "Zzqx" all return `listed` with the registered name.
  - `test_find_sponsor_possible` (db): register has "Zzqx Stores Limited"; "Zzqx" returns `possible` with that name.
  - `test_longer_advert_name_does_not_match` (db): register has "Zzqx"; "Zzqx Recruitment" returns `not_found`.
  - `test_only_skilled_worker_counts` (db): a row with route "Creative Worker" is never returned.
  - `test_trading_name_matches` (db): "Qqzz Kitchen" finds "ZZQX FOODS LTD T/A Qqzz Kitchen".
  - `test_short_names_match_exactly_only` (db): register has "Zq Stores Ltd"; "Zq" returns `not_found`.
  - `test_replace_sponsors_swaps_the_register_and_records_meta` (db).
  - `test_refresh_failure_leaves_register_in_place` (db, HTTP faked to return an empty file): raises `RegisterError`; the previously inserted row is still there.
- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement.** `scripts/refresh_sponsors.py` calls `sponsors.refresh()` and prints the row count, the publication date and the seconds taken.
- [ ] **Step 4: Run the suite.**
- [ ] **Step 5: Load the real register** with the script. Record rows and seconds. If it takes over 45 seconds, raise `maxDuration` for the function in Task 12.
- [ ] **Step 6: Commit** `feat: gov.uk sponsor register load and employer matching`.

---

### Task 3: Visa salary facts (`visa.py`)

**Files:** create `backend/visa.py`, `backend/data/visa_rules.json`, `backend/tests/test_visa.py`.

`visa_rules.json` holds, as read from gov.uk on 12 October 2026: `checked_on`, `standard_salary` 41700, `lower_salary` 33400, the source addresses (`/skilled-worker-visa/your-job`, `/skilled-worker-visa/when-you-can-be-paid-less`, the eligible occupations and going rates publications, `/graduate-visa`, `/student-visa`, the register publication). No figure appears anywhere else in the code.

**Interfaces:**
- `visa.rules() -> dict`.
- `visa.salary_facts(salary_min, salary_max, annual: bool) -> dict`: `{"advertised": {"min","max"} | None, "standard_salary", "lower_salary", "sources": [{"label","url"}], "checked_on"}`. `advertised` is `None` when there is no stated annual salary. There is no verdict field.

- [ ] **Step 1: Failing tests.**
  - `test_rules_file_has_figures_sources_and_date`: figures are whole numbers; every source address starts `https://www.gov.uk/`; `checked_on` parses as a date.
  - `test_facts_always_carry_source_and_date`: with and without a salary.
  - `test_no_salary_means_no_comparison`; `test_rate_is_not_compared` (`annual=False`).
  - `test_no_verdict_in_facts`: the result has none of the keys `eligible`, `meets`, `verdict`, `ok`.
  - `test_figures_live_only_in_the_rules_file`: neither `41700` nor `33400` (with or without a comma) appears in any `backend/*.py` or `frontend/src/**` file.
- [ ] **Steps 2 to 4:** run, implement, run.
- [ ] **Step 5: Commit** `feat: visa salary facts from a dated rules file`.

---

### Task 4: Fit maths and the scoring task

**Files:** create `backend/jobs.py`, `backend/tests/test_jobs.py`; modify `backend/ai.py`, `backend/tests/test_ai.py`, `backend/scripts/live_check.py`.

**Interfaces:**
- `jobs.fit_label(percent: int) -> "direct" | "near" | "stretch" | "none"`: 80 and over, 60 to 79, 40 to 59, under 40.
- `jobs.fit(requirements: list[dict], achievement_titles: list[str]) -> dict | None`: a requirement counts as shown only if `shown_by` equals one of the user's achievement titles, ignoring case and outer spaces. Returns `{"percent", "label", "shown": [{"need","achievement"}] (up to 3), "gaps": [str] (up to 3)}`, or `None` when there are no requirements.
- `ai.score_jobs(batch: list[dict], achievements: list[dict], profile: dict) -> dict[int, list[dict]]`: `batch` items are `{"n": int, "title", "employer", "description"}`; returns requirements per `n`. Only numbers that were sent are kept; a repeated number keeps its first entry; blank needs are dropped; at most 6 requirements per job; descriptions are cut to 2,500 characters in the prompt. Raises `AIError` if no job comes back usable.

Prompt, in outline: for each numbered job list the 4 to 6 main things the advert asks for (skills, experience, qualifications; not benefits or company description); for each, give the title of the candidate's achievement that clearly shows it, copied exactly, or an empty string. Be strict.

- [ ] **Step 1: Failing tests.**
  - `test_fit_label_boundaries`: 39 none, 40 stretch, 59 stretch, 60 near, 79 near, 80 direct, 100 direct.
  - `test_fit_counts_only_real_achievements`: a `shown_by` naming an achievement the user does not have is a gap.
  - `test_fit_ignores_case_and_spaces`; `test_fit_none_without_requirements`; `test_fit_lists_at_most_three_each`.
  - `test_fit_rounds_to_whole_percent`: 2 of 3 gives 67.
  - `test_score_jobs_keeps_only_sent_numbers`; `test_score_jobs_first_entry_wins`; `test_score_jobs_drops_blank_needs_and_caps_at_six`; `test_score_jobs_reads_number_from_text` (`"n": "2"`); `test_score_jobs_raises_when_nothing_usable`; `test_score_jobs_normalises_not_shown_words` ("none", "gap", "n/a" become empty).
- [ ] **Steps 2 to 4:** run, implement, run.
- [ ] **Step 5: Real model.** Add a "job fit" check to `live_check.py` (two synthetic adverts against the sample achievements; passes when both come back with requirements and at least one is shown by a real achievement). Run it and record the seconds.
- [ ] **Step 6: Commit** `feat: fit scoring against the user's own achievements`.

---

### Task 5: Reed client (`reed.py`) **[needs `REED_API_KEY`]**

**Files:** create `backend/reed.py`, `backend/scripts/reed_check.py`, `backend/tests/test_reed.py`; modify `backend/config.py`, `backend/tests/test_config.py`, `backend/.env.example`.

- [ ] **Step 1: Look at the real thing.** `scripts/reed_check.py` makes one search and one details call and prints field names, value types, the number of results, the order of posting dates and the length of each description. It never prints the key. Record the findings in the step document. **If the fields, the date format, the ordering or the description length differ from what is assumed below, stop and tell the owner before continuing.**

Assumed until then: search `GET https://www.reed.co.uk/api/1.0/search` with `keywords`, `locationName`, `postedByDirectEmployer` or `postedByRecruitmentAgency`, `resultsToTake=100`; key as the Basic-auth username; results under `results` with `jobId`, `employerName`, `jobTitle`, `locationName`, `minimumSalary`, `maximumSalary`, `date` (`dd/mm/yyyy`), `jobDescription` (shortened), `jobUrl`. Details at `/jobs/{id}` with the full `jobDescription` as HTML, `yearlyMinimumSalary`, `yearlyMaximumSalary`, `salaryType`, `datePosted`.

**Interfaces:**
- `config.jobs_configured() -> bool`.
- `reed.ReedError`.
- `reed.search(keywords: str, location: str | None, posted_by: "employer" | "agency") -> list[dict]`: one call; listings in the shape of a `job_listings` row. A location of "remote" (any case) is sent as an extra keyword with no location.
- `reed.search_both(keywords, location) -> list[dict]`: both posters.
- `reed.details(source_id: str) -> dict`: `{"description", "description_is_full": True, "salary_min", "salary_max", "salary_annual", "posted_on"}`.
- `reed.clean(html: str) -> str`: tags removed, list items and paragraphs on their own lines, entities decoded.
- Timeout 10 seconds per call. Any HTTP error, timeout, 429 or unreadable body raises `ReedError`.

- [ ] **Step 2: Failing tests** (HTTP faked with `httpx.MockTransport`).
  - `test_search_sends_key_as_basic_auth_username_and_filters_by_poster`.
  - `test_search_parses_a_listing`: every field, including the date as a `date`.
  - `test_remote_becomes_a_keyword`.
  - `test_listing_without_employer_or_title_is_skipped`.
  - `test_salary_annual_rule`: 28000 to 32000 is annual; 15 to 18 and 450 are not; missing is `None`.
  - `test_link_must_be_on_reed`: a `jobUrl` on another host, or not `https`, is replaced by `https://www.reed.co.uk/jobs/<id>`.
  - `test_clean_turns_html_into_text`: paragraphs, list items, `&amp;`, a `<script>` block removed.
  - `test_details_uses_yearly_figures`.
  - `test_errors_become_reed_error`: 500, 429, a timeout, a body that is not JSON.
  - `test_error_and_logs_do_not_contain_the_key` (with `caplog`).
  - `test_jobs_configured` in `test_config.py`.
- [ ] **Steps 3 to 5:** run, implement, run.
- [ ] **Step 6: Commit** `feat: Reed job search client`.

---

### Task 6: Storing listings and matches (`repo.py`)

**Files:** modify `backend/repo.py`; create `backend/tests/test_repo_jobs.py`.

**Interfaces** (shared functions take `conn`; per-user functions take `(conn, user_id, ...)`):
- `searches_due(conn, searches: list[tuple[str, str]], max_age_hours: int) -> set[tuple[str, str]]`.
- `store_search(conn, query, location, listings: list[dict]) -> list[str]`: upserts the listings (keeping a full description and its salary once stored, computing `employer_key` and sponsor status for new rows), records the search as fetched now, replaces its result links. Returns listing ids.
- `purge_old_listings(conn, days: int = 30) -> int`.
- `listings_for_searches(conn, searches, since: date) -> list[dict]`: listings linked to those searches and posted on or after `since`, each with the search's `query` and `location`.
- `add_matches(conn, user_id, items: list[dict]) -> int`: inserts `{"listing_id","role_family_id","search_location"}`; an existing match is left exactly as it is. Returns how many were new.
- `list_matches(conn, user_id, since: date) -> list[dict]`: match fields plus the listing's title, employer, location, salary, link, posted date, poster, sponsor fields, a 300-character snippet and `description_is_full`. Excludes hidden matches and families that are no longer targeted. Newest first.
- `get_match(conn, user_id, match_id) -> dict | None`: with the listing's full description.
- `unscored_matches(conn, user_id, since) -> list[dict]`.
- `save_scores(conn, user_id, scores: list[dict]) -> None`.
- `set_listing_details(conn, listing_id, details: dict) -> None` (shared).
- `mark_matches_seen(conn, user_id) -> int`; `hide_match(conn, user_id, match_id) -> bool`.
- `save_listing_as_job(conn, user_id, match_id) -> dict | None`: copies the listing into `saved_jobs` (`source = 'reed'`, `listing_id`, `posted_on`), sets the match to `saved`. A second call returns the same saved job.
- `job_counts(conn, user_id, since, fresh_since) -> {"new": int, "fresh": int}`.
- `family_market(conn, user_id, since) -> dict[str, dict]`: per family `{"jobs", "salaries": [midpoints of annual salaries], "named", "listed"}`.
- `set_include_senior(conn, user_id, value: bool) -> None`.

- [ ] **Step 1: Failing tests** (all db).
  - `test_search_due_until_stored_then_fresh_then_due_again_after_six_hours` (ages the row with SQL).
  - `test_store_search_upserts_by_source_id` and `test_full_description_is_not_overwritten_by_a_short_one`.
  - `test_new_listing_gets_sponsor_status`: employer on the test register is `listed`; an agency advert is `agency` whatever its name.
  - `test_purge_removes_listings_older_than_thirty_days_only`.
  - `test_add_matches_is_idempotent_and_keeps_hidden_hidden`: hide, add again, still hidden.
  - `test_two_users_share_a_listing_but_not_matches`: A hides it; B still sees it as new; A's list does not include it; B cannot hide, save or read A's match (returns `False` / `None`).
  - `test_list_matches_excludes_untargeted_families_and_old_listings`.
  - `test_save_scores_only_touches_own_matches`.
  - `test_mark_seen_changes_only_new_and_only_mine`.
  - `test_save_listing_copies_fields_and_is_idempotent`; `test_saved_job_survives_listing_deletion`.
  - `test_job_counts`: fresh counts only new, scored 40 or more, posted within the window.
  - `test_family_market_counts`: agency adverts are left out of `named`; rate salaries are left out of `salaries`.
- [ ] **Steps 2 to 4:** run, implement, run.
- [ ] **Step 5: Commit** `feat: storage for shared listings and per-user matches`.

---

### Task 7: Search plan, shortlist and parallel fetch (`jobs.py`)

**Files:** modify `backend/jobs.py`, `backend/tests/test_jobs.py`.

**Constants:** `CACHE_HOURS = 6`, `FRESH_DAYS = 14`, `NEW_DAYS = 2`, `TITLES_PER_FAMILY = 3`, `SEARCHES_PER_REFRESH = 20`, `SCORE_PER_REFRESH = 15`, `SCORE_BATCH = 8`, `FETCH_WORKERS = 8`.

**Interfaces:**
- `jobs.plan(families: list[dict], locations: list[str]) -> list[dict]`: `{"family_id","query","location"}` for each targeted family's first three UK titles (the family name if it has none) in each location; queries and locations lower-cased and trimmed; the same `(query, location)` appears once, under the first family.
- `jobs.is_senior(title: str) -> bool`: whole words senior, lead, principal, head, director, manager.
- `jobs.dedupe(listings: list[dict]) -> list[dict]`: one per `(title, employer_key, location)` ignoring case, keeping the most recently posted.
- `jobs.shortlist(candidates, skills: list[str], include_senior: bool, limit: int) -> list[dict]`: drops senior titles unless allowed; ranks by how many distinct skills appear as whole words in the title and description, then by the title containing the search query, then newest.
- `jobs.fetch(searches: list[dict]) -> tuple[dict, int]`: runs `reed.search_both` for each in a thread pool; returns `{(query, location): listings}` for those that succeeded and the number that failed.
- `jobs.fetch_details(listings) -> dict[str, dict]`: details for those without a full description, in parallel; failures are simply absent.
- `jobs.score(listings, achievements, profile) -> tuple[list[dict], int]`: splits into batches of 8, runs `ai.score_jobs` side by side, applies `jobs.fit`; returns the score rows and how many jobs came back unscored. Raises `AIError` only if every batch failed.
- `jobs.median(values) -> int | None`.

- [ ] **Step 1: Failing tests.**
  - `test_plan_uses_three_titles_per_targeted_family_in_each_location`; `test_plan_skips_untargeted`; `test_plan_falls_back_to_family_name`; `test_plan_removes_repeats`.
  - `test_is_senior`: "Senior Data Analyst", "Head of Data", "Data Lead", "Analytics Manager" are; "Data Analyst", "Leadership Graduate Scheme", "Headhunter Assistant" are not.
  - `test_dedupe_keeps_newest_of_reposts`; `test_dedupe_keeps_different_towns`.
  - `test_shortlist_hides_senior_by_default_and_shows_when_allowed`; `test_shortlist_ranks_by_skill_overlap`; `test_shortlist_matches_whole_words` ("R" does not match "Recruiter"); `test_shortlist_respects_limit`.
  - `test_fetch_returns_successes_and_counts_failures` (`reed.search_both` patched: one raises).
  - `test_fetch_details_skips_failures_and_full_descriptions`.
  - `test_score_batches_and_keeps_good_batch_when_one_fails`; `test_score_raises_when_all_batches_fail`; `test_score_reports_jobs_the_model_left_out`.
  - `test_median`: empty is `None`; odd and even counts.
- [ ] **Steps 2 to 4:** run, implement, run.
- [ ] **Step 5: Commit** `feat: job search plan, shortlist and parallel fetch`.

---

### Task 8: Routes (`main.py`)

**Files:** modify `backend/main.py`, `backend/config.py`, `backend/tests/test_routes_data.py`; create `backend/tests/test_routes_jobs.py`.

| Route | Behaviour |
|---|---|
| `GET /api/jobs` | `{"matches", "due": bool, "remaining_searches": int, "register": {"published_on","loaded_at"} or null, "visa": visa.rules(), "include_senior"}`. Changes nothing |
| `POST /api/jobs/refresh` | See the flow below. Returns `{"searched", "remaining", "new", "scored", "notice"}` |
| `POST /api/jobs/seen` | 204. Marks the caller's new matches seen |
| `PUT /api/jobs/preferences` | `{"include_senior": bool}` |
| `POST /api/jobs/{match_id}/save` | The saved job. Fetches the full advert first if needed (502 "We could not fetch the full advert from Reed. Try again." on failure) |
| `POST /api/jobs/{match_id}/hide` | 204 |
| `POST /api/jobs/{match_id}/track` | 201, the application: company, role, `saved_job_id`, `role_family_id`, source "Reed", `job_url`, `posted_on`, `sponsor_licence` (true for `listed`, false for `not_found`, null otherwise) |
| `GET /api/visa-facts?salary=&employer=` | `visa.salary_facts` plus `{"sponsor": {"status","name"} or null, "register": ...}`. `salary` 0 to 10,000,000; `employer` up to 160 characters; both optional |
| `GET /api/internal/refresh-sponsors` | 401 unless `Authorization: Bearer <CRON_SECRET>` matches (compared in constant time; always 401 when the secret is not set). Runs `sponsors.refresh()`; 502 with a plain message on `RegisterError` |

`GET /api/state` gains `jobs: {"new","fresh"}`, `market: {family_id: {"jobs","salary_median","salary_n","named","listed"}}`, `config.jobs`, and "Reed" in `options.sources`.

**Refresh flow.**
1. Transaction 1: profile, targeted families, achievements, the plan, which searches are due.
   - No targeted family: 400 "Pick your target roles first."
   - No achievements: 400 "Build your profile first."
   - Reed not configured and searches are due: 503 "Job search is not set up on the server."
2. No connection: `jobs.fetch` for up to 20 due searches.
3. Transaction 2: store the results, purge old listings, add matches for every planned search (fresh or cached) after `jobs.dedupe`, build the shortlist of 15 unscored matches. If there is a shortlist and the AI allowance permits, record one AI action.
4. No connection: `jobs.fetch_details` for the shortlist, then `jobs.score`.
5. Transaction 3: store details and scores.
6. Notices, joined when more than one applies: every due search failed, "We could not reach Reed. Try again shortly."; some failed, "Some searches could not be completed. Check again shortly."; allowance used up, "You have reached today's AI limit, so new jobs were not scored. It resets at midnight."; some jobs unscored, "Some jobs could not be scored. Check again to score them."
7. If every batch of the model failed, the jobs already stored stay stored and the answer is 502 with the usual AI message.

- [ ] **Step 1: Failing tests** (`reed` and `ai.score_jobs` patched; real database).
  - Add `match_id` to the id names in `test_every_route_but_config_needs_a_token`, so all nine new routes are proved to answer 401.
  - `test_internal_refresh_needs_the_secret`: no header, a wrong secret, and no secret configured all answer 401; the right one calls `sponsors.refresh`.
  - `test_internal_refresh_failure_is_502_and_keeps_register`.
  - `test_refresh_needs_targets`, `test_refresh_needs_achievements`, `test_refresh_503_without_reed_key`.
  - `test_refresh_fetches_scores_and_lists`: one targeted family, one location; matches appear in `GET /api/jobs` newest first with fit, shown and gaps.
  - `test_second_refresh_inside_six_hours_makes_no_reed_call`; `test_refresh_after_six_hours_calls_reed_once_per_search` (rows aged with SQL).
  - `test_reed_down_keeps_stored_jobs_and_says_so`; `test_partial_failure_returns_the_rest_with_a_notice`.
  - `test_same_job_twice_appears_once`.
  - `test_senior_titles_hidden_until_setting_is_on`: not scored and flagged by default; scored after `PUT /api/jobs/preferences`.
  - `test_ai_limit_reached_still_lists_jobs_unscored` (limit set to 0; the model is never called).
  - `test_ai_failure_keeps_jobs_and_answers_502`; `test_nothing_scored_is_saved_when_the_model_fails`.
  - `test_refresh_counts_one_ai_action`; `test_refresh_with_nothing_to_score_counts_none`.
  - `test_at_most_twenty_searches_per_refresh_and_remaining_reported`.
  - `test_hide_survives_refresh`.
  - `test_seen_clears_new_but_get_does_not`.
  - `test_save_copies_listing_and_fetches_full_advert`; `test_save_twice_returns_same_job`; `test_save_fails_cleanly_when_reed_is_down`.
  - `test_track_creates_application_with_link_posted_date_and_sponsor_status`: for `listed`, `not_found` and `agency`.
  - `test_malformed_match_id_422`; `test_unknown_match_id_404`.
  - `test_user_b_cannot_see_save_hide_or_track_user_a_match`: 404 each; B's own refresh shows the same listing as B's own new match.
  - `test_visa_facts_always_has_source_and_date`; `test_visa_facts_with_employer_looks_up_register`; `test_visa_facts_validation` (negative salary, 200-character employer: 422).
  - `test_state_has_job_counts_market_and_reed_source`.
  - `test_no_key_in_any_jobs_response`: with `REED_API_KEY` and `CRON_SECRET` set to marker values, no response body contains either.
- [ ] **Steps 2 to 4:** run, implement, run. Generate `CRON_SECRET` into `backend/.env` (random, never printed).
- [ ] **Step 5: Commit** `feat: jobs, visa facts and register reload routes`.

---

### Task 9: Tracker findings and next steps (`analytics.py`)

**Files:** modify `backend/analytics.py`, `backend/tests/test_analytics.py`.

- `SOURCES` gains "Reed"; `JOB_BOARDS` gains "Reed".
- `compute(applications, families, cv_versions, stories, market=None)`.
- New finding, type `sponsor`, severity 2, one per targeted family where `named >= 10` and `listed / named < 0.2`: title "Few <family> roles come from licensed sponsors", evidence "<listed> of <named> current adverts that name their employer are from employers on the sponsor register.", action "Turn on Sponsors only in Jobs, or look at a neighbouring role where more employers sponsor.", link `{"page": "jobs", "label": "Open Jobs"}`.
- The timing finding's link becomes `{"page": "jobs", "label": "See new jobs"}`.
- Next step `job`: text "Save a job you want", why "Pick one from Jobs, or paste an advert, so your CV and practice fit a real role.", page `jobs`.

- [ ] **Step 1: Failing tests.** `test_sponsor_finding_fires_at_ten_named_adverts_under_twenty_percent`; `test_sponsor_finding_silent_with_nine`; `test_sponsor_finding_silent_at_twenty_percent`; `test_sponsor_finding_only_for_targeted_families`; `test_compute_without_market_has_no_sponsor_finding`; `test_reed_counts_as_a_job_board`; `test_job_step_points_to_jobs`.
- [ ] **Steps 2 to 4:** run, implement, run.
- [ ] **Step 5: Commit** `feat: sponsor finding and Reed as an application source`.

---

### Task 10: The Jobs page

**Files:** create `frontend/src/pages/Jobs.jsx`; modify `frontend/src/ui.jsx`, `frontend/src/App.jsx`, `frontend/src/index.css`.

- Menu: "Jobs" between Career pathways and Resume, with a count of new matches.
- On open: load `GET /api/jobs`; if `due`, run the refresh once and show "Searching Reed for your target roles"; then reload. After showing the list, call `POST /api/jobs/seen` (the markers already on screen stay).
- Head: the visa line for the user's visa type, with its gov.uk link.
- Filters (in the browser): role family, location, "Sponsors only", "Include senior roles" (saved through the preferences route). "Check for new jobs" button; "Search the remaining N" when present.
- Under the filters: "Sponsor register as of <date>. Visa rules checked on <date>. This is not immigration advice."
- Each job: title, employer, location, "Reed"; "View advert" (new tab, `rel="noopener noreferrer"`); posted date with a "Posted in the last 48 hours" marker and a "New" marker; salary ("£X to £Y a year", "A rate, see the advert" or "Salary not stated"); fit label and percentage with up to three "You show" lines naming the achievement and up to three gaps, and "Fit based on a short summary" where it applies; the sponsorship sentence for its status; the salary fact in the agreed wording, shown only for an annual salary; the five actions.
- Three groups: scored 40% or more; "Not checked yet (N)" with "Check fit for the next 15"; "Not a match (N)", closed by default.
- Actions: Save job; Tailor CV (save, then open Resume on that job); Practise interview (save, then open Interview coach on that job); Add to tracker (the track route, then a toast); Not for me (hide, with the card removed at once).
- Empty states, each with one action: no target roles ("Pick your target roles" opens Career pathways); no jobs found ("No jobs posted in the last 14 days matched your target roles. Check again tomorrow, or add a location in your profile."); job search not set up; errors with Retry.

- [ ] **Step 1: Build the page.** There are no frontend tests in this project; it is verified by lint, build and by hand.
- [ ] **Step 2:** `npm run lint && npm run build`.
- [ ] **Step 3: Commit** `feat: Jobs page`.

---

### Task 11: Home, Career pathways, Applications, Resume

**Files:** modify `frontend/src/pages/Home.jsx`, `Pathways.jsx`, `Applications.jsx`, `Resume.jsx`, `frontend/src/ui.jsx`.

- **Home:** when `s.jobs.fresh > 0`, the next best step is "<N> new matching jobs posted in the last 48 hours", why "Roles get most of their applications in the first few days.", button "See jobs".
- **Career pathways:** each targeted family card gains one line from `s.market`: "<jobs> live jobs. Median advertised salary £X from <n> adverts. <listed> of <named> named employers are on the sponsor register." Parts with no data are left out; with no jobs it reads "No live jobs found yet". A new "Check an offer" panel: salary and employer name in, the salary facts and the register result out, with the same sources line.
- **Applications:** the finding kind `sponsor` is labelled "Sponsorship". A card shows "View advert" when it has a link, and "On the sponsor register" or "Not found on the register" when the status is known.
- **Resume:** the empty state offers "Find jobs" beside "Add a job".

- [ ] **Step 1: Build.** **Step 2:** lint and build. **Step 3: Commit** `feat: live job figures on Home, Career pathways and Applications`.

---

### Task 12: Privacy page, settings example, scheduled job

**Files:** modify `frontend/src/pages/Privacy.jsx`, `backend/.env.example`, `vercel.json`.

- Privacy: under "Who processes it", "Reed supplies job adverts. We send it job titles and locations from your target roles, never your name or anything else about you." Under "What we collect", "Which jobs you save or dismiss."
- `.env.example`: `REED_API_KEY`, `CRON_SECRET`, each with where it comes from.
- `vercel.json`: `"crons": [{"path": "/api/internal/refresh-sponsors", "schedule": "0 5 * * 1"}]`; raise `maxDuration` only if Task 2 measured over 45 seconds.

- [ ] **Step 1: Edit.** **Step 2:** lint, build, full backend suite. **Step 3: Commit** `docs: privacy notice, settings example and weekly register reload`.

---

### Task 13: Verify and document

- [ ] Whole backend suite: 0 failed, 0 skipped. Frontend lints and builds.
- [ ] `scripts/live_check.py`: every check passes, including "job fit".
- [ ] `scripts/reed_check.py` and one real refresh timed end to end; it must finish well inside 60 seconds.
- [ ] The eight hand checks from the step document, in the browser. The owner signs in; a second account is the owner's to create.
- [ ] `docs/ARCHITECTURE.md`: roadmap status, decisions and trade-offs (the table above), code map, data model, API, outside services, the verification record with dates, known limitations.
- [ ] The step document: status, the Reed findings, anything that changed.
- [ ] Final report to the owner: built, verified and how, **not verified**, every judgement call and its cost, what they need to do.

**Expected to be reported as not verified:** the weekly scheduled job on Vercel (nothing is deployed yet), and Reed's terms of use and call limits (unpublished).

## Order and what blocks what

Tasks 1 to 4 need nothing new and can start as soon as this plan is approved. Task 5 onward needs `REED_API_KEY` in `backend/.env`. Tasks 6 to 9 are backend, 10 to 12 frontend and configuration, 13 is verification.
