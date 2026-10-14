# Step 5: Interview Preparation Implementation Plan

> **For agentic workers:** follow `careerai-building-a-step` stage 4. Every task is test-first: write the tests, watch them fail for the right reason, write the code, watch them pass, run the whole suite on its own, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status, 14 October 2026:** tasks 1 to 13 are built and committed. A fresh review of the whole branch found nothing critical; two of its findings are fixed and the rest are listed as still open in ARCHITECTURE section 24. Changes from this plan made while building are the rulings in the step document's "Changed at build time" table.

**Goal:** For a saved job or an application, the user confirms the company and gets one printable prep pack: a company brief in which every line links to the page it came from, three talking points joining a company fact to one of their achievements, a 90-second "tell me about yourself", eight likely questions each matched to one of their stories or a named gap, five questions to ask, their right-to-work line and an "On the day" checklist. Stories carry competencies shown as a coverage grid, and the mock interviewer asks from the pack.

**Architecture:** Three small outside clients (`companies_house.py`, `fetcher.py` for employers' websites, `websearch.py` for Tavily), each with its own errors and tests against a mock transport. `research.py` gathers the three side by side, numbers every passage, asks the model for statements that cite a passage number, and keeps only statements code can check against their passage. The result is stored once in the shared `companies` table and reused by every user for 14 days. `prep.py` holds the pure pack rules (right-to-work line, edits, rebuilds, what the interviewer is told). Two new AI tasks in `ai.py` (company brief, prep pack) and one for story competencies follow the existing pattern: the model's own result checked in code, or an error with Retry. All SQL stays in `repo.py`.

**Tech stack:** unchanged packages (`httpx`, the standard library's `socket`, `ipaddress`, `urllib.robotparser` and `html.parser`). New outside services: Companies House API, Tavily. New settings: `COMPANIES_HOUSE_API_KEY`, `SEARCH_PROVIDER`, `SEARCH_API_KEY`, `DAILY_RESEARCH_LIMIT`.

**Step document:** `.claude/skills/careerai-step-5-interview-prep/SKILL.md`. Where this plan adds to it, the addition is listed under "Decisions this plan adds" for the owner to approve.

## Global constraints

- Everything in `CLAUDE.md` applies. The points that bite hardest here:
- **Nothing from the model's memory.** A brief statement exists only if it cites a passage the app fetched and passes the checks in task 5. With no passages at all, no model call is made.
- **Real result or an error.** A failed brief or pack shows Retry. Nothing is substituted, and nothing is cached from a failed research.
- **No database connection across an outside call.** Companies House, website fetches, Tavily and the model are all called between two short transactions.
- **What a user types never goes in an address.** A company name or website travels in a request body. A Companies House number is checked against `^[A-Z0-9]{8}$` before it is put in an address.
- **Keys never appear** in a response, a stored record or a log line. Failures log the service and the error type only.
- **Shared tables are real.** `companies` holds live public data with no `user_id`. Tests use names that cannot be real ("Zzqx Holdings Ltd"), never count or clear the table, and use `own_transaction` for anything that calls `db.transaction()`.
- **Every new table and route** gets the standing tests: rows deleted with the account (per-user tables), RLS on, no browser privileges; 401 without a token, 422 for a malformed id, 404 for another user's id; the daily limit where it costs money.
- **The user's name, email, phone, town and LinkedIn address never go to the model or to Tavily.** Only a company's name and website go to Tavily.
- British English, no em dashes in UI copy or prompts.
- Commit after every task with the suite passing. Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push unless asked.

## What the checks before building found (14 October 2026)

| Checked | Result |
|---|---|
| Earlier steps | 0 to 4 are merged into `main` (step 4 as pull request 9, `7f9177f`). The story bank (step 1) and application stages and the detail panel (step 4) exist, so "Prepare" goes on the panel at Phone screen and Interview |
| Baseline | Branch `step-5-interview-prep` from `main` at `7f9177f`: 1,341 backend tests pass, the frontend lints and builds |
| Settings | `COMPANIES_HOUSE_API_KEY`, `SEARCH_PROVIDER` and `SEARCH_API_KEY` are not in `backend/.env` yet. Tasks 1 to 12 build and test without them; the live checks and hand checks need them |
| Companies House API | Free key from the developer hub, sent as the HTTP Basic username with a blank password. `GET /search/companies?q=&items_per_page=` and `GET /company/{number}`. 600 requests per 5 minutes for the whole app |
| Tavily | `POST https://api.tavily.com/search`, `Authorization: Bearer <key>`. `topic: "news"` returns `published_date` (Tavily's estimate; may be the last update); `start_date` limits by date; `max_results` up to 20; basic search 1 credit. Free: 1,000 credits a month, no card. Terms (4 May 2026) do not restrict keeping results |
| Brave, rejected | Terms (1 September 2026) forbid storing results "other than transient storage", which the agreed 14-day shared cache needs |
| Time limit | `vercel.json` gives the function 120 seconds (Hobby allows up to 300). Research (about 20 seconds of fetching plus one model call) and the pack (one model call) are therefore two requests the page makes in turn, with progress shown between them |
| ElevenLabs | The docs give no limit on a dynamic variable's length. The interviewer already receives up to 900 characters of CV summary; the pack adds at most 600 characters of company summary and 1,200 of questions. Checked in a real call (task 13). `setup_agents.py` must be run again after the prompt changes |
| SIC codes | Companies House returns codes only. gov.uk publishes the condensed SIC 2007 list (`SIC07_CH_condensed_list_en.csv`) under the Open Government Licence; it becomes `backend/data/sic_codes.json` |
| Right to work | gov.uk "Prove your right to work to an employer" (`gov.uk/prove-right-to-work`) is where a share code is made; the in-person checklist links there |
| `usage_events.kind` | Checked as `in ('ai', 'voice')` by a constraint from `001_initial`; the migration replaces it |

## Settled with the owner today

| Question | Answer |
|---|---|
| Search service | Tavily |
| Right-to-work wording | Graduate: "I have the right to work in the UK on a Graduate visa until 30 January 2027." Student: "I am in the UK on a Student visa until 30 January 2027." Under it: "Employers often ask next whether you will need sponsorship. That answer is yours to add. This is not immigration advice." Editable |
| Story competencies | Tagged by the call that writes a story; "Tag my stories" (one AI action) for existing ones; ticked or unticked by hand when editing |
| Where packs live | A fourth tab, "Prep packs", in Interview coach |

## Decisions this plan adds (for the owner to approve with the plan)

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| 1 | Two requests, not one: `POST /api/companies/research` (fetch, search, brief; cached) then `POST /api/ai/prep` (the pack). The page shows "Researching <company>" then "Writing your pack" | Each fits the 120-second limit with room; the user sees progress | One more route |
| 2 | The company search is `POST /api/companies/search` with the name in the body, not `GET ?name=` | `CLAUDE.md`: what a user types never goes in an address | Not cacheable; it never needs to be |
| 3 | Companies House lines are written by code, never by the model: registered name and number, status, incorporated date, registered office town, nature of business (SIC descriptions from gov.uk). Each links to the company's Companies House page | Exact facts from the register need no model and cannot be misquoted | None |
| 4 | The shared research is found by the Companies House number (or the normalised name when there is none) together with the website's host. A different website gives a different record | One user typing a wrong website for a real company never changes another user's brief | The same company can be researched twice if two users type different addresses for it |
| 5 | A pack keeps a copy of the brief it was built from | Like a sent CV: another user refreshing the shared research never changes your pack under you, and talking points always point at facts the pack shows | A pack shows its own research date until the user presses Refresh |
| 6 | One pack per saved job, or per application that has no saved job. "Prepare" on something that has a pack opens it. An application with a saved job uses that job's pack | No duplicates; a pack follows the job through the tracker | None |
| 7 | Refresh researches again now (one research use, whatever the cache holds) and rewrites the pack (one AI action). An edited "Tell me about yourself" and right-to-work line are kept; the ticks on questions to ask are cleared, since the questions change | The user's own words are never thrown away | A refreshed pack keeps an older pitch the user had edited |
| 8 | Checks on every brief statement: its source number must be one that was sent; its section must be one of six (what they do, size and age, values, products and projects, news, competitors); a value must carry a quote found word for word in its passage (spacing, case and curly quotes aside); any quoted phrase and every number in the statement must be in its passage; a news statement must cite a news result, takes its date from that result, and is dropped if older than 12 months; an undated one is shown as "Undated". Competitors are shown "according to <site>". One retry when no statement survives, then an error with Retry | "Every statement must come from fetched text" checked in code, not just asked for | An honest statement worded with a number the page writes differently ("1.2m" for "1,200,000") is dropped |
| 9 | With no passages at all (no register entry, no website, no results), no model call is made and the brief reads "We could not find anything about <company> in the sources we checked." The research use is still counted | Never filled from the model | None |
| 10 | The research limit counts once per newly researched company. A retry of the same company within 10 minutes (after a failure) is not counted again. The brief's model call belongs to the research use; the pack is one AI action; "Tag my stories" is one AI action | Follows "counts once per newly researched company"; a failed attempt should not use two of five | A user can fail and retry the same company for free within 10 minutes |
| 11 | Fetching limits: the home page plus at most 5 pages of the same site whose link or address mentions about, careers, values, culture, mission, who we are, what we do, our story, news or press; 1 MB of decoded text per page; 8 seconds per page; 3 redirects; HTML only. `robots.txt` is read for the agent "UKCareerNavigator" (falling back to "*"); an unreachable one (timeout, 5xx) means "do not fetch", a missing one (4xx) means "allowed" (RFC 9309). User agent: `UKCareerNavigator/1.0 (interview preparation; reads public pages only)` | The step document's safety rules made exact | A site behind a bot wall gives no website lines; the brief says so |
| 12 | Every address is resolved by the server and each resolved address must be public (`ipaddress.is_global`); the connection is then made to that checked address, with the host name kept for the certificate. Redirects go through the same check | Covers redirects and a name that resolves differently a second time | None |
| 13 | The website is typed by the user (optional). It is never guessed from search results. `acme.co.uk` becomes `https://acme.co.uk/`; an address with a user name, a port, or a host that is an IP address or has no dot is refused | A guessed site could be the wrong company | Users must find the address themselves |
| 14 | Competencies are stored as keys: `teamwork`, `leadership`, `problem_solving`, `communication`, `setback` (Handling a setback), `initiative`, `influencing`, `deadlines` (Working to deadlines), at most three per story. The migration tags existing stories whose current one-word competency is exactly one of the eight labels; the rest wait for "Tag my stories". The edit form's free-text competency becomes eight tick boxes; the old text column is kept, not shown | The grid needs a fixed list; stories already written keep what can be read for certain | Stories with a label like "Problem-solving" (hyphen) are not tagged until the button is pressed |
| 15 | Likely questions: eight asked for, at least five kept. Each has a competency (one of the eight, or "motivation" or "role") and a story id; an id that is not the user's becomes "No story yet". Questions to ask: five; the user ticks at most three. Talking points: three asked for, at least one kept; each must name a brief fact and an achievement that exist, and every number in it must be in that fact or achievement. The pitch: 150 to 260 words; every number in it must be in the user's achievements, profile or the advert | "Matched only to a story the user owns" and "no invented figures" checked in code | A good pitch with a figure worded differently is retried once |
| 16 | Interview type on the pack: Phone, Video or In person, chosen on the pack. It starts at Phone for an application at Phone screen and at Video otherwise. "On the day" shows the UK norms already in the app and a short checklist for that type (new `interview_day` in `content.json`) | "A checklist for the interview type" needs types; these three cover a graduate's first rounds | None |
| 17 | `GET /api/state` lists packs (id, role, company, job or application, updated); a pack's content is read when it is opened. `DELETE /api/prep/{id}` is added | State stays small; a user can remove a pack | One route beyond the step document |
| 18 | Prep packs and the Prepare buttons appear only when `COMPANIES_HOUSE_API_KEY`, `SEARCH_PROVIDER=tavily`, `SEARCH_API_KEY` and the model are set | The menu shows only features that genuinely work | A missing key hides the feature |
| 19 | The mock interviewer, when the chosen job has a pack, is told a company summary (what they do, products and news lines, at most 600 characters) and the pack's likely questions (at most 1,200), and asks from them. The HR screening session also gets the company summary. I run `setup_agents.py` to update the interviewer on your ElevenLabs account | "The interviewer is given the company summary and asks from the pack's likely questions" | None; re-running restores either prompt |
| 20 | The migration is `008_interview_prep`. Research records are refreshed in place and never deleted (public data) | Step 4 used 007 | The table grows by one row per company researched |

## Review focus

Inputs most likely to break this, each with a test in the task named.

1. **Hostile addresses.** `localhost`, `http://10.0.0.1`, `file:///etc/passwd`, `https://acme.test@127.0.0.1`, `http://[::1]`, `acme.test:8080`, a public page redirecting to `http://169.254.169.254/`, a name resolving to one public and one private address. (Task 3)
2. **Odd model output in the brief.** A source number as `"3"`, `"[3]"`, `0`, `-1` or one past the end; a value quoted with curly quotes against straight ones in the page; "1,200" against "1200"; a news statement citing a website passage; a statement with no section or an unknown one; the same statement twice. (Task 5)
3. **The shared cache.** Two users, same company, different websites; one user refreshing while another has a pack; research exactly 14 days old; a failed research leaving nothing cached; a cached company still counting nothing. (Tasks 6, 9)
4. **Missing pieces.** An application with no saved job (no advert); a saved job deleted after its pack was built; no stories; no achievements; no visa end date; a dissolved company; "not a UK company"; Companies House down. (Tasks 2, 8, 9)
5. **Size and time.** A 5 MB home page, a page that never finishes, a `robots.txt` that times out or answers 500, a page in Latin-1, a compressed page that expands past the limit, a PDF linked as "About us". (Task 3)

## File map

| File | What changes |
|---|---|
| `backend/migrations/008_interview_prep.sql` | New |
| `backend/config.py`, `backend/limits.py`, `backend/.env.example` | Research settings and the research limit |
| `backend/companies_house.py` | New: search and company profile |
| `backend/data/sic_codes.json` | New: SIC 2007 code to description (from gov.uk, OGL) |
| `backend/fetcher.py` | New: safe fetching, `robots.txt`, a site's useful pages as text |
| `backend/websearch.py` | New: Tavily news and competitor searches |
| `backend/research.py` | New: gather sources, number passages, the cited brief, the cache key |
| `backend/prep.py` | New, pure: right-to-work line, pack content, edits, rebuilds, what the interviewer is told |
| `backend/ai.py` | `company_brief`, `prep_pack`, `tag_stories`; `star` and `story_bank` return competencies |
| `backend/repo.py` | Companies (shared), prep packs, story competencies; state lists packs |
| `backend/main.py` | Nine routes (task 9, task 7); state gains `prep_packs`, `options.competencies`, `options.interview_types`, `config.prep` |
| `backend/data/content.json` | `interview_day` checklists |
| `backend/setup_agents.py` | Interviewer prompt and two placeholders |
| `backend/scripts/live_check.py` | Real brief, pack and tagging |
| `backend/tests/` | New: `test_companies_house`, `test_fetcher`, `test_websearch`, `test_research`, `test_prep`, `test_repo_prep`, `test_routes_prep`. Changed: `test_migrate`, `test_config`, `test_limits`, `test_ai`, `test_stories`, `test_routes_ai`, `test_content`, `test_setup_agents` |
| `frontend/src/components/` | New: `PrepPacks` (list and start), `CompanyConfirm`, `PrepPack` (the pack, printable), `StoryCoverage` |
| `frontend/src/pages/Interview.jsx` | Fourth tab, Prepare beside the job picker, competency tick boxes, the coverage grid, pack variables for the interviewer |
| `frontend/src/components/ApplicationPanel.jsx` | "Prepare for this interview" at Phone screen and Interview |
| `frontend/src/pages/Privacy.jsx` | What research sends and to whom |
| `frontend/src/index.css` | Pack sections, source links, the grid, print styles |

---

### Task 1: Settings, the research limit and the schema

**Produces:** `config.research_configured() -> bool` (Companies House key, `SEARCH_PROVIDER == "tavily"`, search key, all set); `config.companies_house_key()`, `config.search_key()`; `DAILY_LIMIT_DEFAULTS["research"] = 5`; `limits.KINDS = ("ai", "voice", "research")`.

```sql
-- 008_interview_prep.sql
companies  (id uuid pk, lookup_key text not null unique, name text not null, company_number text,
            website text, registry jsonb, facts jsonb not null default '[]', missing jsonb not null default '[]',
            researched_at timestamptz not null default now())            -- shared: no user_id
prep_packs (id uuid pk, user_id → auth.users cascade, saved_job_id → saved_jobs on delete set null,
            application_id → applications on delete set null, company_id → companies on delete set null,
            role text not null, company text not null, content jsonb not null,
            created_at, updated_at timestamptz not null default now())
            unique (user_id, saved_job_id) where saved_job_id is not null
            unique (user_id, application_id) where application_id is not null and saved_job_id is null
            index (user_id)
stories    + competencies text[] not null default '{}'
             check (competencies <@ array['teamwork','leadership','problem_solving','communication',
                                          'setback','initiative','influencing','deadlines'])
             backfill: lower(competency) equal to a label → that key
usage_events: replace the kind check with in ('ai', 'voice', 'research')
```

Both new tables: RLS on, `revoke all ... from anon, authenticated`.

- [ ] **Step 1: tests.** `test_migrate.py`: add `companies`, `prep_packs` to `TABLES`; `test_packs_cascade_on_user_delete`; `test_pack_survives_its_job_being_deleted` (job deleted → `saved_job_id` null, pack kept); `test_one_pack_per_job`; `test_story_competencies_checked` (`CheckViolation` for `'cooking'`); `test_research_is_a_usage_kind`; `test_backfill_maps_exact_labels` (insert a story with `competency='Teamwork'`, run the backfill statement, get `{teamwork}`; `'Problem-solving'` stays empty). `test_config.py`: `test_research_needs_all_three_settings` (any one missing, or `SEARCH_PROVIDER=brave`, gives False); `test_research_limit_defaults_to_5`. `test_limits.py`: `test_research_limit_counts_separately_from_ai`.
- [ ] **Step 2:** run them, see them fail.
- [ ] **Step 3:** write the migration, the settings and the kind; add the four settings to `.env.example` with where to get each; `python migrate.py`.
- [ ] **Step 4:** run the suite; commit `feat: schema, settings and daily limit for interview prep`.

### Task 2: Companies House client (`companies_house.py`)

**Produces:**
- `class CompaniesHouseError(Exception)` with `.message` (user-facing: "We could not reach Companies House. You can carry on without it.")
- `search(name: str) -> list[dict]`: at most 5 of `{number, name, status, town, incorporated_on: date | None}`
- `profile(number: str) -> dict`: `{number, name, status, incorporated_on, town, type, sic: [{code, description}], url}`, `url` = `https://find-and-update.company-information.service.gov.uk/company/{number}`
- `NUMBER = re.compile(r"^[A-Z0-9]{8}$")`; `_client()` (replaced in tests, like `reed._client`); key as Basic username, blank password; 10-second timeout.
- `backend/data/sic_codes.json` built once from gov.uk's condensed list; an unknown code keeps the code with no description.

- [ ] **Step 1: tests** in `test_companies_house.py` with `httpx.MockTransport`: `test_search_shapes_five_matches` (seven items in, five out, status words as Companies House gives them, town from `address.locality`); `test_search_sends_the_name_as_a_parameter_and_the_key_as_basic_auth`; `test_profile_reads_sic_descriptions` (`62012` → "Business and domestic software development"); `test_bad_number_never_reaches_the_api` (`"../x"` raises `ValueError` with no request made); `test_not_found_profile_raises` (404 → `CompaniesHouseError`); `test_timeout_and_500_raise_without_the_key` (`caplog` and the message never contain the key); `test_no_matches_is_an_empty_list`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write `companies_house.py` and `data/sic_codes.json` (download the CSV, convert, commit the JSON; note the source and licence in the module docstring).
- [ ] **Step 4:** run the suite; commit `feat: Companies House search and company profile`.

### Task 3: Safe fetching (`fetcher.py`)

**Produces:**
- Constants: `USER_AGENT`, `ROBOTS_AGENT = "UKCareerNavigator"`, `MAX_BYTES = 1_000_000`, `TIMEOUT_S = 8`, `MAX_REDIRECTS = 3`, `MAX_EXTRA_PAGES = 5`, `USEFUL = re.compile(r"about|careers?|jobs|values|culture|mission|who-we-are|what-we-do|our-story|news|press", re.I)`.
- `class Refused(Exception)` with `.reason` in `{"address", "robots", "redirects", "not_html", "timeout", "unreachable", "status"}`.
- `website(raw: str) -> str | None`: a typed address to `https://host/` or None (decision 13).
- `fetch(url: str, robots: dict) -> dict` → `{url, title, text, links: [(href, link_text)]}`. `robots` is a per-run cache keyed by host. Raises `Refused`.
- `site(home: str) -> tuple[list[dict], list[str]]`: the home page and up to five same-host useful pages, as `[{url, title, text}]`, and the reasons any could not be read. Never raises.
- `_resolve(host: str, port: int) -> list[str]` (wraps `socket.getaddrinfo`; replaced in tests) and `_client()`.

How the address check works: every request (including each redirect hop and `robots.txt`) resolves the host, refuses unless every resolved address is `is_global`, then requests the first address with the original host in the `Host` header and `extensions={"sni_hostname": host}` so the certificate is still checked against the name. Redirects are followed by hand. The body is read with `iter_bytes` (decoded) and stops at `MAX_BYTES`. HTML is turned into text by the parser `reed.clean` uses, moved to a shared helper `textify.py` so both use it (with `<nav>`, `<footer>`, `<header>`, `<form>` added to what is hidden for websites).

- [ ] **Step 1: tests** in `test_fetcher.py`, all with a mock transport and `_resolve` replaced: `test_website_normalises` (`"acme.test"` → `"https://acme.test/"`; `"http://acme.test/about"` → `"https://acme.test/"`); parametrised `test_website_refuses` (`localhost`, `10.0.0.1`, `[::1]`, `file:///etc/passwd`, `acme.test:8080`, `https://x@acme.test`, `""`); `test_private_resolution_is_refused` (resolves to `10.0.0.5` → `Refused("address")`, no request made); `test_mixed_public_and_private_resolution_is_refused`; `test_redirect_to_metadata_address_is_refused` (302 to `http://169.254.169.254/` → refused); `test_connects_to_the_checked_address_with_the_host_name` (request URL host is the IP, `Host` header and `sni_hostname` are the name); `test_too_many_redirects`; `test_size_limit_stops_reading` (a 5 MB body: reading stops at `MAX_BYTES` and the page's text is what was read; the top of a page is the useful part, so a long page is cut, not refused); `test_compressed_page_is_limited_after_decoding`; `test_timeout` (`httpx.ReadTimeout` → `Refused("timeout")`); `test_not_html_is_refused` (`application/pdf`); `test_robots_disallow_is_respected`; `test_robots_missing_allows` (404); `test_robots_unreachable_forbids` (500 and timeout); `test_robots_read_once_per_host`; `test_site_picks_useful_same_host_links` (links to `/about-us`, `/careers`, `/basket`, `https://other.test/about` → only the first two); `test_site_collects_reasons_and_never_raises`; `test_text_drops_scripts_navigation_and_footers`; `test_latin1_page_reads`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write `textify.py` (moved from `reed.py`, `reed` imports it; `test_reed.py` still passes) and `fetcher.py`.
- [ ] **Step 4:** run the suite; commit `feat: fetch an employer's website safely`.

### Task 4: Tavily client (`websearch.py`)

**Produces:**
- `class SearchError(Exception)`; `API = "https://api.tavily.com/search"`; `NEWS_DAYS = 365`, `MAX_NEWS = 8`, `MAX_COMPETITORS = 5`; `_client()`.
- `news(company: str, today: date) -> list[dict]`: `topic "news"`, the name in quotes, `start_date` 365 days back, basic depth. Each `{title, url, snippet, published_on: date | None}`; a result dated before the window is dropped here too; a result with no date is kept with `None`.
- `competitors(company: str) -> list[dict]`: `topic "general"`, query `"<company> competitors"`, `country "united kingdom"`; same shape.
- Only `http(s)` result addresses are kept. A snippet is cut at 600 characters.

- [ ] **Step 1: tests** in `test_websearch.py`: `test_news_request_shape` (bearer key, topic, quoted name, `start_date`); `test_news_parses_rfc_and_iso_dates` (`"Mon, 13 Oct 2026 10:00:00 GMT"` and `"2026-10-13"`); `test_old_news_is_dropped_and_undated_kept`; `test_competitors_request_shape`; `test_non_http_results_dropped`; `test_error_status_and_timeout_raise_search_error_without_the_key` (a 401 body echoing the key; `caplog` and the message never contain it).
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write `websearch.py`.
- [ ] **Step 4:** run the suite; commit `feat: news and competitor search through Tavily`.

### Task 5: The cited company brief (`ai.company_brief`)

**Consumes:** passages from task 6's numbering: `{n: int, kind: "website" | "news" | "competitors", url, title, text, published_on}`.

**Produces:** `BRIEF_SECTIONS = ("what_they_do", "size", "values", "products", "news", "competitors")`, `SECTION_CAP = {"what_they_do": 3, "size": 2, "values": 4, "products": 5, "news": 5, "competitors": 5}`; `company_brief(company: str, passages: list[dict], today: date) -> list[dict]` → `[{section, text, source: n, quote}]`, every one checked (decision 8). Prompt: only the passages, never outside knowledge; one source number per statement; a value carries the exact words from its passage in `quote`; third person about the company; plain British English; no em dashes. `_run(..., check=...)` retries once when nothing survives, then `AIError`.

- [ ] **Step 1: tests** in `test_ai.py` (model replaced): `test_brief_drops_statement_with_unknown_source` (parametrised over `99`, `0`, `-1`, `None`, `"x"`); `test_brief_reads_source_written_as_text` (`"3"`, `"[3]"`); `test_brief_drops_value_whose_quote_is_not_in_its_passage`; `test_brief_value_quote_matches_across_curly_quotes_case_and_spacing`; `test_brief_drops_statement_with_number_not_in_its_passage` and `test_brief_number_matches_with_thousands_separator`; `test_brief_drops_double_quoted_phrase_not_in_its_passage`; `test_news_must_cite_a_news_result`; `test_news_older_than_12_months_dropped` (the passage date, not the model's); `test_unknown_section_dropped`; `test_duplicates_and_caps`; `test_brief_retries_then_fails_when_nothing_survives`; `test_brief_prompt_holds_only_the_passages` (the user message contains every passage and nothing else about the company).
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write `company_brief`.
- [ ] **Step 4:** run the suite; commit `feat: a company brief where every statement cites a fetched passage`.

### Task 6: Research and the shared cache (`research.py`, `repo.py`)

**Consumes:** tasks 2 to 5.

**Produces:**
- `research.FRESH_DAYS = 14`; `PASSAGE_CHARS = 700`; `MAX_WEBSITE_PASSAGES = 18`.
- `lookup_key(*, name: str, number: str | None, website: str | None) -> str`: `ch:<number>|<host>` or `name:<sponsors.normalise(name)>|<host>`, `<host>` lowercased without `www.`, empty when there is no website.
- `gather(*, name: str, number: str | None, website: str | None, today: date) -> dict`: `{registry, pages, news, competitors, missing}`, the four outside calls side by side with `parallel.together`. A failure of any one adds a line to `missing` ("Companies House", "their website", "the news search", "the competitor search") and never raises.
- `registry_facts(registry: dict) -> list[dict]`: the code-written lines of decision 3, with `kind "registry"`, the Companies House address, and "Companies House lists this company as dissolved" when it is.
- `passages(gathered: dict) -> list[dict]`: numbered from 1: website text split on paragraph boundaries into passages of at most `PASSAGE_CHARS`, then news, then competitors.
- `brief(name: str, gathered: dict, today: date) -> dict`: `{facts: [{id: "f1"…, section, text, quote, url, source_title, kind, published_on}], missing}`. No passages: no model call, registry facts only, plus `NOTHING_FOUND` when there are none of those either.
- `repo.find_company(conn, lookup_key: str, fresh_days: int) -> dict | None`, `repo.save_company(conn, lookup_key: str, *, name, company_number, website, registry, facts, missing) -> dict` (insert or replace; `researched_at = now()`), `repo.get_company(conn, company_id) -> dict | None`. Shared table: no `user_id`, like the sponsor functions.

- [ ] **Step 1: tests.** `test_research.py` (clients and `ai.company_brief` replaced): `test_lookup_key_by_number_and_host`; `test_lookup_key_by_name_when_not_on_the_register`; `test_gather_runs_all_four_and_survives_each_failing` (each source raising in turn names itself in `missing`); `test_not_uk_skips_companies_house`; `test_no_website_skips_fetching`; `test_registry_facts_for_active_and_dissolved`; `test_passages_numbered_and_split`; `test_brief_with_no_passages_makes_no_model_call`; `test_brief_attaches_source_details_by_code` (url, title, kind, date come from the passage, never the model). `test_repo_prep.py`: `test_company_found_within_14_days_not_after` (set `researched_at` 13 and 15 days back); `test_save_company_replaces_in_place`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write `research.py` and the three repo functions.
- [ ] **Step 4:** run the suite; commit `feat: research a company once and share it for 14 days`.

### Task 7: Story competencies

**Produces:** `ai.COMPETENCIES = {"teamwork": "Teamwork", "leadership": "Leadership", "problem_solving": "Problem solving", "communication": "Communication", "setback": "Handling a setback", "initiative": "Initiative", "influencing": "Influencing", "deadlines": "Working to deadlines"}`; `ai._competencies(value) -> list[str]` (keys or labels in, known keys out, at most 3, order kept); `star()` and `story_bank()` also return `competencies`; `ai.tag_stories(stories: list[dict]) -> dict[str, list[str]]` (story id to keys; an id not sent is ignored; a story given none is left out). `repo.add_story` writes `competencies`; `repo.STORY_FIELDS` gains it; `repo.set_story_competencies(conn, user_id, tags: dict) -> int`. Routes: `PATCH /api/stories/{id}` takes `competencies: list[Literal[keys]]` (at most 3); `POST /api/ai/stories/tag` tags the user's stories that have none (400 "You have no stories yet." / "Every story already has competencies."), one AI action, returns the updated stories. The story bank's "already covered" list is built from `competencies`.

- [ ] **Step 1: tests.** `test_ai.py`: `test_star_returns_known_competencies` (`["Teamwork", "cooking", "teamwork", "Problem solving", "initiative", "leadership"]` → `["teamwork", "problem_solving", "initiative"]`); `test_story_bank_returns_competencies`; `test_tag_stories_keeps_only_sent_ids_and_known_keys`. `test_repo_records.py` (or `test_stories.py`): `test_story_competencies_saved_and_edited`; `test_set_competencies_only_touches_own_stories` (user B's story id changes nothing). `test_routes_ai.py`: `test_tag_my_stories_tags_only_untagged` (stub; the tagged story is not sent); `test_tag_my_stories_refusals`; `test_tag_counts_one_ai_action`; `test_patch_story_competencies_validated` (unknown key and four keys → 422).
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write the code; extend the two prompts ("competencies: one to three of <labels>, the ones this story shows").
- [ ] **Step 4:** run the suite; commit `feat: stories carry competencies`.

### Task 8: The prep pack task and its rules (`ai.prep_pack`, `prep.py`)

**Produces:**
- `ai.prep_pack(*, job: dict, brief: list[dict], achievements: list, stories: list, profile: dict) -> dict` → `{talking_points: [{text, fact_id, achievement_id}], pitch, likely_questions: [{question, competency, story_id, why}], questions_to_ask: [{question, fact_id}]}`, checked as decision 15. `job` is `{title, company, description}` (description may be empty: the prompt says no advert was recorded). The profile sent is course, university and graduation month only. A story is sent as id, title, competencies and result.
- `prep.right_to_work(profile: dict) -> str` (the agreed wording; `""` without a visa type and end date); `prep.RIGHT_TO_WORK_NOTE`.
- `prep.INTERVIEW_TYPES = ("phone", "video", "in_person")`; `prep.default_type(stage: str | None) -> str`.
- `prep.content(*, written: dict, brief: dict, researched_at, interview_type: str, right_to_work: str) -> dict`: the stored pack (`brief` copy, written parts, `ticked: []`, `pitch_edited: False`, `right_to_work_edited: False`).
- `prep.rebuild(old: dict, new: dict) -> dict`: decision 7.
- `prep.edit(content: dict, changes: dict) -> dict`: `pitch` (sets `pitch_edited`), `right_to_work` (sets its flag), `ticked` (indexes into `questions_to_ask`, unique, at most 3, each in range, else `ValueError`), `interview_type`.
- `prep.for_interviewer(content: dict) -> dict`: `{company_brief, likely_questions}`, cut to 600 and 1,200 characters at a sentence or question boundary.

- [ ] **Step 1: tests.** `test_ai.py`: `test_pack_story_id_not_owned_becomes_no_story`; `test_pack_talking_point_needs_real_fact_and_achievement`; `test_pack_talking_point_number_must_be_in_its_fact_or_achievement`; `test_pack_pitch_length_and_numbers_checked` (retry then `AIError`); `test_pack_keeps_five_to_eight_questions`; `test_pack_question_to_ask_with_unknown_fact_keeps_question_drops_link`; `test_pack_prompt_has_no_name_contact_or_visa` (the user message holds none of the profile's name, email, phone, city, LinkedIn, visa); `test_pack_without_advert_says_so`. `test_prep.py`: `test_right_to_work_wording` (parametrised: graduate, student, missing date, missing type); `test_default_type_from_stage`; `test_edit_ticks_validated`; `test_edit_marks_pitch_and_line_as_the_users`; `test_rebuild_keeps_edited_pitch_and_line_and_clears_ticks`; `test_rebuild_takes_new_pitch_when_not_edited`; `test_for_interviewer_caps_lengths`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write `ai.prep_pack` and `prep.py`.
- [ ] **Step 4:** run the suite; commit `feat: the prep pack: talking points, pitch, likely questions, questions to ask`.

### Task 9: Prep routes and packs in `repo.py`

**Produces:** `repo.list_packs(conn, user_id) -> list[dict]` (no content), `repo.get_pack`, `repo.find_pack(conn, user_id, *, saved_job_id=None, application_id=None)`, `repo.save_pack(conn, user_id, *, saved_job_id, application_id, company_id, role, company, content) -> dict` (insert, or update the one for that job or application; `updated_at = now()`), `repo.update_pack_content(conn, user_id, pack_id, content) -> dict | None`, `repo.delete_pack(conn, user_id, pack_id) -> bool`; `load_state` gains `prep_packs`. A `saved_job_id` or `application_id` that is not the user's is stored as null (as with applications).

Routes (all need a user; all answer 503 "Interview prep is not set up on the server." when `research_configured()` is false):

| Route | Body | Does |
|---|---|---|
| `POST /api/companies/search` | `{name: Text(160)}` | Up to 5 matches. 502 with the client's message when Companies House fails |
| `POST /api/companies/research` | `{name: Text(160), company_number: str \| None (pattern), website: Text(300, 0) = "", not_uk: bool = False}` | 422 for a website `fetcher.website` refuses ("Enter the company's website, for example acme.co.uk."). Cached and fresh: returned, nothing counted. Otherwise one research use (retry window 600 seconds, action `research <lookup_key>`), gather and brief with no connection held, save. Returns `{company_id, name, researched_at, facts, missing, cached}` |
| `POST /api/ai/prep` | `{job_id: UUID \| None, application_id: UUID \| None, company_id: UUID, interview_type: Literal \| None}` | Exactly one of the two ids (422 otherwise); 404 for one that is not the user's, or an unknown company. Reads the job (the application's saved job when it has one), achievements, stories, profile; 400 "Build your profile first." with no achievements. One AI action. Saves a new pack, or rebuilds the existing one (decision 7). Returns the pack |
| `GET /api/prep/{id}` | | The pack |
| `PATCH /api/prep/{id}` | `{pitch: Text(2500, 0)?, right_to_work: Text(300, 0)?, ticked: list[int]?, interview_type: Literal?}` | `prep.edit`; 422 on `ValueError` |
| `DELETE /api/prep/{id}` | | 204 |
| `POST /api/prep/{id}/refresh` | | Research the pack's company again ignoring the cache (one research use), save it, return the company. The page then calls `/api/ai/prep` |

- [ ] **Step 1: tests** in `test_routes_prep.py` (outside clients and AI tasks replaced; `client`, `as_user`, `own_transaction`): the standing set for each route (401, 422 malformed id, 404 other user's pack, job or application); `test_routes_hidden_without_settings` (503); `test_search_name_travels_in_the_body`; `test_companies_house_down_is_502_with_message`; `test_research_counts_once_and_is_shared` (user A researches, user B researches the same name, number and website: the fetch, search and brief stubs ran once; A has one research use, B none; both get the same facts); `test_different_website_is_a_different_record`; `test_research_retry_within_window_not_counted_twice` (first brief raises `AIError`, second succeeds: one use, nothing cached after the failure); `test_research_limit_reached_is_429`; `test_search_failure_still_gives_a_brief_with_missing`; `test_no_sources_gives_nothing_found_without_model`; `test_not_uk_company_flow`; `test_dissolved_company_flow`; `test_bad_website_is_422`; `test_pack_for_job_then_prepare_again_rebuilds_same_pack`; `test_pack_for_application_uses_its_saved_job`; `test_pack_for_application_without_job_has_no_advert`; `test_pack_story_matching_only_own_stories` (B's story id in the stub's output becomes no story); `test_pack_counts_one_ai_action`; `test_pack_refused_without_achievements`; `test_patch_pack` and `test_patch_ticks_over_three_is_422`; `test_refresh_researches_again_and_counts`; `test_user_b_cannot_read_change_refresh_or_delete_a_pack`; `test_state_lists_packs_without_content`; `test_no_key_in_any_response` (every route's JSON, with keys set to recognisable values, never contains them); `test_no_connection_held_during_research_or_pack` (the stubs assert no `db.transaction` is open, as `test_routes_ai.test_no_connection_held_during_ai` does).
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write the repo functions and routes; state gains `prep_packs`, `options.competencies` (`[[key, label], …]`), `options.interview_types`, `config.prep`.
- [ ] **Step 4:** run the suite; commit `feat: routes to research a company and build, edit and refresh a prep pack`.

### Task 10: The pack in the browser

**Produces:** `components/PrepPacks.jsx` (the tab: packs newest first, each opening; "Prepare for a job" with the job picker; empty state with one action), `components/CompanyConfirm.jsx` (the employer name, prefilled and editable; Companies House matches as name, town, status and year; "This one", "None of these", "It is not a UK company"; the website box; "Build my pack"), `components/PrepPack.jsx` (the sections in the step document's order; every brief line ends with its source link; "Researched on <date>" and Refresh; the missing-sources notice; talking points; editable pitch saved on leaving the box; likely questions with "Use your story: <title>" or "No story yet" and a button to the STAR stories tab; questions to ask with tick boxes, at most three; the right-to-work line with the agreed note and "This is not immigration advice"; interview type and "On the day" with `content.tone_norms` and `content.interview_day[type]`; Print). `index.css`: pack layout and `@media print` (menu, buttons and tabs hidden; sources printed as their addresses).

Flow: Prepare → if a pack exists for that job or application, open it; else CompanyConfirm → `POST /api/companies/research` (shows "Researching <company>: their website, Companies House and the news. About 30 seconds.") → `POST /api/ai/prep` ("Writing your pack. About 30 seconds.") → the pack. Each step has its own Retry; a failed pack keeps the research.

Entry points: Interview coach → Practice sessions: "Prepare" beside the job picker (disabled until a job is picked). ApplicationPanel: "Prepare for this interview" at Phone screen and Interview. Both go to `interview/prep` with `focus.prepJobId` or `focus.prepAppId`. All hidden unless `s.config.prep`.

`content.json` gains `interview_day: {phone: [...], video: [...], in_person: [...]}` (three to five lines each, written plainly; in person includes "If they ask to check your right to work, they will ask for a share code. You can get one at gov.uk/prove-right-to-work."). `test_content.py`: `test_interview_day_has_every_type`.

- [ ] **Step 1: tests.** `test_content.py` as above (frontend has no unit tests in this project; the page is checked in the browser in task 13).
- [ ] **Step 2:** run, see it fail.
- [ ] **Step 3:** write the content and the components; `npm run lint && npm run build`.
- [ ] **Step 4:** run the suite; commit `feat: the Prep packs tab, company confirmation and the printable pack`.

### Task 11: Story coverage and competency editing

**Produces:** `components/StoryCoverage.jsx`: the eight competencies, each with the titles of the stories tagged with it or "No story yet"; "Tag my stories" when any story has no competencies (one AI action, with Retry). In `Interview.jsx`: the story edit form's free-text competency becomes eight tick boxes (at most three); the story card shows its competencies as chips.

- [ ] **Step 1:** no new backend behaviour (task 7 tested it); `npm run lint && npm run build`.
- [ ] **Step 2:** write the components.
- [ ] **Step 3:** run the suite; commit `feat: story coverage by competency`.

### Task 12: The interviewer uses the pack

**Produces:** `setup_agents.py`: the interviewer prompt gains "Company background, from research: {{company_brief}}" and "Likely questions for this role: {{likely_questions}}", with the rule "When likely questions are given, ask your three questions from them, in your own words, choosing ones that fit this session type"; placeholders `company_brief: "Not provided."`, `likely_questions: "None given."`. `Interview.jsx` Sessions: when the picked job has a pack, it fetches it and passes `prep.for_interviewer`'s two values (worked out on the server and returned with the pack as `interviewer`), and the intro line says "Using your prep pack".

- [ ] **Step 1: tests.** `test_setup_agents.py`: `test_every_prompt_variable_has_a_placeholder` already exists and covers the new ones; add `test_interviewer_prompt_uses_the_pack`. `test_routes_prep.py`: `test_pack_carries_interviewer_values`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write the code; `npm run lint && npm run build`.
- [ ] **Step 4:** run the suite; commit `feat: the mock interviewer asks from the prep pack`.
- [ ] **Step 5:** run `python setup_agents.py` to update the interviewer agent on the owner's ElevenLabs account (approved with this plan).

### Task 13: Privacy, live checks, hand checks, documentation

- [ ] **Privacy page:** company research sends the employer's name and website to Tavily and Companies House, and our server reads the employer's public pages; nothing about the user is sent to either. The pack sends the job, achievements, stories and course to the model (as other features do). Research is shared: another user preparing for the same company sees the same public facts, never your pack.
- [ ] **Live checks** (`scripts/live_check.py`, needs the keys): "company brief" (real Companies House, website, Tavily and model for one well-known UK employer; at least one statement in three sections, every source number valid, every news date within a year); "prep pack" (real model on that brief and a synthetic profile; story ids valid, pitch length in range); "tag stories". Each prints counts only, never keys or page text.
- [ ] **Browser checks** with the throwaway-user harness (memory: checking signed-in pages without a login): the Prep packs tab empty state; Prepare from Interview coach and from an application at Phone screen; Companies House matches, "None of these", "not a UK company"; the pack's sections, ticks (a fourth is refused), pitch edit kept after reload, Refresh keeps the edit; print preview; the coverage grid and tick boxes; a second user sees no packs. The database is checked clean afterwards.
- [ ] **Owner's hand checks** (the step document's seven, with a real login): listed in the report as not verified until done.
- [ ] **Docs:** ARCHITECTURE (roadmap, decisions, code map, data model, migrations, API, AI layer, security rows for fetching and shared research, tests table, limitations, a new section for step 5 and its verification record); the step skill's status and "Changed at build time"; this plan's status note.
- [ ] Commit `docs: step 5 built; what is verified and what the owner still has to check`.

## Self-review

- **Spec coverage.** In scope 1 (tasks 2, 9, 10), 2 (tasks 2, 3, 4), 3 (tasks 5, 6), 4 (tasks 8, 9, 10), 5 (tasks 7, 8), 6 (tasks 7, 11), 7 (task 12). Every "must have tests" line maps to a named test: unsourced statements and bad numbers (5), quoted values (5), old and undated news (4, 5), private addresses and redirects (3), size, slow, robots, non-HTML (3), no match, not UK, dissolved, identical names (2, 6, 9; identical names are told apart by town, number and year on screen), search failing (6, 9), no sources (6, 9), second user cached (9), story matching (8, 9), research limit (9), keys (2, 4, 9), isolation (6, 7, 9).
- **Out of scope kept out:** no daily drill, no longer interviews, no salary or assessment practice, nothing from the model's own knowledge.
