# UK Career Navigator: scope, architecture and handover

Last updated: 12 October 2026. This is the living document for the project. It is updated at the end of every build step.

## 1. What this is

A career agent for **international students on a Student visa and recent graduates on the Graduate visa, already in the UK**, who are looking for work here.

The problem it addresses: these users do not know how UK hiring works, apply without a plan, and cannot tell why applications fail. The product gives them one profile built from their own experience, and uses it everywhere: UK-standard CVs, interview practice, and a tracker that says what to fix.

Design principles:

- **Only real data.** Every screen shows the signed-in person's own information. Nothing is seeded, invented or filled in when the AI fails.
- **Show where things came from.** A CV bullet shows the words it was built from; interview feedback quotes what the user actually said.
- **One next step.** The home page answers "what should I do next, and why".
- **Minimal UI.** A feature appears in the menu only when it genuinely works.

## 2. Roadmap and status

Every step has a document holding its goal, every decision made for it, the design, the behaviours to test, the hand checks and what "done" means. All eight designs were agreed with the project owner on 12 October 2026. To build a step, open a new session in this repository and say "build step N".

| Step | What | Depends on | Status | Document |
|---|---|---|---|---|
| 0 | Accounts, saved data, removal of the demo persona | – | Built. Three hand checks left (section 13) | `careerai-step-0-accounts-and-saved-data` |
| 1 | Deeper onboarding: CV upload, GitHub import, editing achievements, education and work history, story bank | 0 | Designed | `careerai-step-1-deeper-onboarding` |
| 2 | Real jobs from Reed, fit scoring, sponsor register, visa salary facts | 0 | Built on branch `step-2-real-jobs` and run against the real Reed API. The signed-in hand checks are left (section 16) | `careerai-step-2-real-jobs` |
| 3 | Full UK CV: all sections, editing in the app, Word and PDF | 1 | Designed | `careerai-step-3-full-uk-cv` |
| 4 | Tracker detail, follow-ups, a lesson from each rejection, weekly goals, streaks, weekly plan | 0 | Designed | `careerai-step-4-tracker-and-habits` |
| 5 | Interview prep: sourced company research, prep pack, questions matched to stories | 0 | Designed | `careerai-step-5-interview-prep` |
| 6 | Hidden market: contacts, outreach drafts, saved events, referrals | 4 | Designed | `careerai-step-6-hidden-market` |
| 7 | Peers: opt-in buddy groups of two or three | 4 | Designed | `careerai-step-7-peers` |

The documents live in `.claude/skills/<name>/SKILL.md`. The method every step follows is `careerai-building-a-step`, in the same folder. Project-wide rules are in `CLAUDE.md`.

**Agreed build order:** 2, 1, 3, 4, 5, 6, 7. Real jobs come first because they are the largest gap and need nothing but step 0.

**How a step is built.** One step per session, on its own branch from `main`: orient and run the tests; re-check anything listed under "Verify at build time"; write a task-by-task plan against the code as it then is, for the owner to approve; build test-first; verify by tests, real-model checks and by hand; update this document. The owner merges the branch into `main` through a pull request.

**What the step documents fix, and what they leave to the build session.** Fixed: what is built, every product decision, the data model, the routes, the tests that must exist. Left to the session: the file-by-file task list, and anything about an outside service that may have changed (prices, limits, exact fields, current visa figures).

## 3. System overview

```
Browser (React + Vite)
 ├─ supabase-js ───────────────► Supabase Auth    sign up / sign in / reset → short-lived access token
 ├─ /api/* + Bearer token ─────► FastAPI (one Vercel function, London)
 │                                 ├─ verifies the token against Supabase's public keys
 │                                 ├─ Postgres on Supabase (transaction pooler)   ← all user data
 │                                 ├─ AWS Bedrock, Mantle endpoint                ← the language model
 │                                 ├─ ElevenLabs API                              ← mints voice session tokens
 │                                 ├─ Reed API                                    ← job adverts (titles and locations sent, nothing personal)
 │                                 └─ gov.uk                                      ← the register of licensed sponsors, weekly
 └─ WebRTC audio ──────────────► ElevenLabs agents (onboarding coach, mock interviewer)
```

- **FastAPI is the only gateway to user data and the only holder of secrets.** The browser talks to Supabase for login only.
- The browser's audio goes straight to ElevenLabs. The transcript comes back to the browser, which sends it to FastAPI for the AI step.

## 4. Tech stack and why

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 19, Vite 8, no router, no UI library, one stylesheet | Few moving parts. Navigation is by URL hash |
| Backend | Python 3.12, FastAPI | Already in place; the AI and analytics code is Python |
| Login | Supabase Auth, email and password | Passwords never touch our code. Google sign-in can be added later without other changes |
| Database | Postgres on Supabase, London region | Real tables for tracker analytics and, later, cross-user features. UK data residency |
| Database access | `psycopg` 3, plain SQL, no ORM | Few dependencies, fast cold starts, every query visible in one file |
| Language model | AWS Bedrock through the Mantle endpoint; model set by `BEDROCK_MODEL_ID` | One key; swapping models is a settings change. Currently `qwen.qwen3-235b-a22b-2507` |
| Voice | ElevenLabs Agents over WebRTC, WebSocket as automatic fallback | Real-time speech with a transcript stream |
| Job adverts | Reed's official API, through a shared six-hour cache | Free, legal, has full descriptions and a direct-employer filter. Adzuna is left out for now (section 15) |
| Sponsor data | The gov.uk register of licensed sponsors, stored in Postgres and reloaded weekly | The authoritative list; Open Government Licence |
| Hosting | Vercel: one Python function serving the API and the built frontend | Already set up |
| Tests | `pytest` | Backend logic, data isolation and routes |

Minimum versions: Node 20.19 or 22.12 (Vite 8 will not run on older), Python 3.12.

## 5. Decisions and trade-offs

| Decision | Gain | Cost | Revisit when |
|---|---|---|---|
| FastAPI as the single gateway | One place for logic and security; secrets stay server-side | One extra network hop per request | Real-time features are needed |
| Plain SQL, no ORM | Simple, fast to start, transparent | Queries written by hand | The schema passes roughly 20 tables |
| One `/api/state` read returning everything | The pages needed little change | Payload grows with history | A user has hundreds of rows |
| Deny-all row-level security, checks in code | One enforcement point that is tested | RLS is a backstop, not a second independent check | The browser ever reads Supabase directly |
| No fallback content when the AI fails | Users never see invented content | A model outage shows an error and a Retry button | – |
| Hiding unbuilt features | Nothing fake, small UI | The app looks smaller until later steps land | Each step restores its page |
| Transcripts saved with journal entries | The user can always see what was heard | More personal data stored | – |
| "You said" quotes checked against the transcript | The app never attributes words the user did not say | Some comments show no quote | – |
| Usage counted per attempt | Simple, protects the bill | A failed AI call still uses one of the day's allowance | Users hit limits because of failures |
| A voice session counted only after ElevenLabs issues the token | A failed start does not use up a session | Two simultaneous requests could overshoot the cap by one | Abuse is seen |
| Language model in `us-east-1` | Uses the key and model available | Personal data is processed outside the UK | A UK or EU model is available on the account |
| One Supabase project for development and live | Simple | Test accounts sit beside real ones | Before a public launch |
| Email confirmation off | Sign-up works without an email provider | Unverified emails; password reset depends on Supabase's limited mailer | Before a public launch |
| Environment variables override `backend/.env` | Standard behaviour; tests can set values | A stray machine-level variable could override the file | – |
| Reed only; Adzuna left out | No allowance or terms risk | Fewer adverts than two sources would give | Adzuna agrees a higher allowance and consents to totals (section 15) |
| Listings and the register are shared tables with no `user_id` | Many users reuse one search; the register is stored once | The one exception to "every row belongs to a user"; tests must not assume these tables are empty | – |
| Each Reed search runs twice (direct employers, agencies) | An agency is never mistaken for the employer in the sponsor label | Twice the calls | Reed starts marking the poster in results |
| A company whose name marks it as a recruiter, job board or trainer is not treated as the employer; an advert that sells a programme is kept apart as "training" | Course adverts do not pose as jobs or as sponsors; figures are not skewed | A real employer with "recruit", "career", "training" or "learning" in its name is treated as a recruiter. Recruiters with none of those words still pass as employers | Users report either kind of miss |
| Only the first 100 results per search and poster are used | They are the relevant ones; later pages were mostly off-topic | Reed sorts by relevance and has no date sort, so some of the newest adverts in a very large search are missed | Reed adds a date sort |
| Sponsor status is stored on the shared listing | Worked out once per advert, in three statements however many adverts | Must be recomputed when the register reloads (it is) | – |
| "Possible match" only when a longer registered name starts with the advert's name | Deterministic, explainable, uses an index | A true match under a very different registered name shows as "not found" (the label says so) | Users report misses |
| Fit is strict: a requirement counts only with real evidence in a named achievement | No flattering scores; gaps are actionable | A thin profile scores low on most adverts | Hand checks show it is too harsh |
| Scoring runs as three model calls side by side, one AI action | About 13 seconds for 15 adverts instead of 40 | A failed call loses its five adverts until the next check | – |
| The offer check is a POST | A salary and employer never sit in an address or a server log | Not cacheable | – |
| Jobs is in the menu only when a Reed key is set | The menu never shows something that cannot work | A missing key hides the feature rather than explaining it | – |
| Reading the jobs list never changes data; "seen" is its own call | Safe under React strict mode and retries | One extra route | – |

Smaller behaviours worth knowing:

- The "applications are not getting replies" finding also covers applications with no role family.
- The referral finding stays silent when the user has no job-board applications, because it compares against them.
- The "you apply too slowly" finding needs at least four applications that have a posted date.
- A pasted job is still saved, without an AI summary, if the AI fails or the daily limit is reached.
- Role family suggestions carry no salary or sponsorship figures from the model. A targeted family shows live figures computed from real adverts instead.
- The app gives no visa advice. It shows the user's own visa dates, the figures gov.uk publishes with their source and the date checked, and what the register says. It never says whether a job can be sponsored.
- A salary counts as annual only when Reed says so, or when the search figure is £10,000 or more. A day or hourly rate is never compared with a visa figure.
- A job the user saved or dismissed does not come back when the employer posts it again under a new advert.
- An application made from a listing records whether the employer was on the register: yes, no, or unknown for a possible match or an agency advert.

## 6. Code map

```
backend/
  main.py          routes only: who is calling, validate input, call modules, return JSON
  auth.py          access token → User. FastAPI dependency current_user
  db.py            connection helper for the pooled Postgres connection
  repo.py          ALL SQL. Every function takes (conn, user_id, ...), except those for the shared job and sponsor tables
  jobs.py          which searches to run, de-duplication, shortlist, fit maths, parallel calls to Reed and the model
  reed.py          Reed client: search, one advert in full, HTML to text. Everything Reed-specific
  sponsors.py      the gov.uk register: find, download, check, load; employer name matching
  visa.py          salary facts from data/visa_rules.json
  limits.py        per-user daily caps
  analytics.py     tracker stats, diagnosis rules, getting-started checklist. Pure functions
  ai.py            one function per AI task: prompt, output shaping, quote checking
  llm.py           one call path to Bedrock, fallback model, JSON parsing
  voice.py         ElevenLabs token minting and transcript fetch (owner only)
  content.py       loads data/content.json, the static guidance copy
  data/visa_rules.json   the visa figures, their gov.uk sources and the date checked. The only place they are written
  config.py        settings from the environment, then backend/.env
  migrate.py       applies migrations/*.sql not yet recorded in schema_migrations
  setup_agents.py  creates or updates the two ElevenLabs agents and writes their ids to .env
  scripts/live_check.py   one real call per AI task (uses credits)
  scripts/refresh_sponsors.py   load today's sponsor register
  scripts/reed_check.py   one real Reed search and advert; prints the reply's shape, never the key
  tests/           pytest suite
frontend/src/
  App.jsx          session gate and app shell
  supabase.js      Supabase client built from /api/config
  api.js           fetch wrapper: bearer token, one refresh-and-retry on 401
  ui.jsx           shared pieces: menu, FamilyCard, ErrorRetry, Empty, date helpers
  VoiceAgent.jsx   one ElevenLabs call with the live transcript panel
  components/      DetailsForm, BackgroundInput (voice or paste), Jobs (picker and paste-a-job),
                   Visa (sponsor line, salary facts, sources line)
  pages/           Landing, Auth, Privacy, Onboarding, Home, Profile, Pathways, Jobs, Resume,
                   Interview, Applications, Journal, Account
app.py             Vercel entry point: the API plus the built frontend
```

## 7. Data model

All tables are in the `public` schema. Every row of a per-user table has `user_id` referencing `auth.users` with `on delete cascade`, so deleting a login removes all of that person's data. Five tables added in step 2 hold public data shared by everyone and have no `user_id`; they are marked below. Row-level security is on with no policies, and the browser-facing roles (`anon`, `authenticated`) have no privileges.

| Table | Holds |
|---|---|
| `profiles` | One row per user: name, university, course, graduation month, visa type, visa end date, preferred locations, pitch |
| `achievements` | What they said (`raw`), the UK CV bullet (`uk_version`), skills, outcome, scale, context note, source (voice or paste) |
| `role_families` | AI-suggested families: fit, estimated overlap, UK titles, requirements shown or missing, targeted or not. Unique per user by name, ignoring case |
| `saved_jobs` | Jobs the user pasted: title, company, description, AI summary, keywords, matched role family |
| `cv_versions` | Each tailored CV and cover letter in full, named "<title>, <company> vN" |
| `stories` | STAR stories, linked to their achievement |
| `applications` | Tracker rows: company, role, family, CV version, source, stage, applied and posted dates, plus link, contact, notes, sponsor licence and follow-up date for step 4 |
| `journal_entries` | Coach calls and mock interviews: summary, points, actions, scores, and the transcript |
| `usage_events` | One row per AI action or voice session: daily limits now, streaks later |
| `job_listings` (shared) | One row per advert: source and its id, title, employer, who really posted it (employer, agency, or training for an advert that sells a course), location, salary and whether it is annual, description and whether it is the full text, link, posting date, and what the register says about the employer |
| `job_searches`, `job_search_results` (shared) | The search cache: each search anyone has run, when, and the adverts it last found |
| `sponsors` (shared) | The register's Skilled Worker entries: registered name, normalised name, town, county, rating. A trading name gets its own row |
| `reference_meta` (shared) | When the register was last loaded and the date gov.uk published that file |
| `job_matches` | One user's view of one advert: role family, fit percentage and label, what they show and lack, new, seen, saved or hidden |
| `schema_migrations` | Which migration files have been applied |

Schema changes are numbered SQL files in `backend/migrations/`, applied with `python migrate.py`. Applied so far: `001_initial`, `002_journal_transcript`, `003_jobs` (which also adds `listing_id` and `posted_on` to `saved_jobs`, and `include_senior` to `profiles`), `004_training_adverts`.

Adverts older than 30 days are deleted on each refresh. A saved job is a copy, so it stays.

A reference from one row to another (for example an application's CV version) is stored only if the target belongs to the same user; otherwise it is saved as null.

## 8. API

`GET /api/config` is public and returns only values safe to expose. Every other route needs a valid token (401 without one) and touches only the caller's rows; the one exception is the register reload, which needs the scheduler's secret instead. Ids are UUIDs: a malformed id answers 422, an unknown or foreign one 404.

| Route | Purpose |
|---|---|
| `GET /api/state` | Everything the pages need for the signed-in user, plus stats, next steps, guidance content and today's usage |
| `PUT /api/profile` | Save "Your details" |
| `DELETE /api/account` | Delete the login and all data |
| `DELETE /api/achievements/{id}` | Remove an achievement |
| `POST /api/families/{id}/target` | Tick or untick a role family |
| `POST /api/jobs`, `DELETE /api/jobs/{id}` | Add a pasted job (with an AI summary), remove a saved job |
| `GET /api/jobs` | The user's matched adverts, whether a search is due, the register's date and the visa figures. Changes nothing |
| `POST /api/jobs/refresh` | Run the searches that are due, match the adverts, score up to 15. One AI action when anything is scored |
| `POST /api/jobs/seen` | Mark new matches as seen |
| `PUT /api/jobs/preferences` | "Include senior roles" |
| `POST /api/jobs/{match_id}/save`, `/hide`, `/track` | Copy the advert into saved jobs; dismiss it; save it and log an application with its link, posting date and sponsor status |
| `POST /api/visa-facts` | The offer check: a salary beside the published figures, and a register lookup |
| `GET /api/internal/refresh-sponsors` | Reload the register. Not for users: needs `Authorization: Bearer <CRON_SECRET>` |
| `POST`, `PATCH`, `DELETE /api/applications[/{id}]` | Tracker |
| `GET /api/journal/{id}/transcript` | What was said in that session |
| `POST /api/ai/achievements` | Transcript or pasted text → achievements and pitch |
| `POST /api/ai/families` | Achievements → role families |
| `POST /api/ai/tailor` | Saved job → tailored CV and cover letter, saved as a version |
| `POST /api/ai/star` | Achievement → STAR story |
| `POST /api/ai/interview-feedback` | Mock interview transcript → scores and feedback |
| `POST /api/ai/tone` | Decode a British phrase, or rewrite a sentence in UK tone |
| `POST /api/ai/diagnosis` | Weekly review from tracker stats |
| `GET /api/voice/token` | Start a voice session (counts against the daily limit) |
| `GET /api/voice/transcript/{conversation_id}` | Fallback transcript, only for the session's owner |

Error responses always carry a plain `detail` message the UI shows as-is: 422 invalid input, 429 daily limit ("You've reached today's limit. It resets at midnight."), 502 AI or voice failure, 503 service not configured or database unreachable.

## 9. AI layer

- **One prompt in, JSON out.** `ai.py` has one function per task. Replies are coerced to the expected shape, and values are normalised (fit labels, overlap clamped to 0–100, scores to 0–5).
- **Real result or an error.** A task returns the model's own output or raises. One automatic retry on malformed output or a network error. Nothing is saved from a failed call.
- **Fallback model.** If the main model is refused (403 or 404) and `BEDROCK_FALLBACK_MODEL_ID` is set, the request is tried once there.
- **Reasoning text.** The current model can emit a `<think>` block; it is removed before parsing.
- **Stray characters.** The model sometimes adds an extra bracket or quote after a complete answer (3 of 12 real calls on 12 October 2026). The parser reads the first complete JSON value and ignores what follows.
- **Job fit.** The model lists what each advert asks for and names the achievement that shows each requirement. A requirement counts only if that achievement is really one of the user's. Only achievements are sent, nothing else about the person.
- **No invention.** The base prompt forbids inventing employers, numbers or achievements. On top of that, every quote shown as "You said" is checked against the user's own lines of the transcript (`ai.verbatim`): kept if they said exactly that, replaced by their closest sentence if the model paraphrased, dropped otherwise.
- **Privacy in logs.** Failures log the task name and the error type only, never prompts or replies.
- **No database connection is held during a model call.** Each AI route reads and counts usage in one short transaction, calls the model, then writes in a second.

To check the prompts against the real model: `python scripts/live_check.py` from `backend/` (uses credits).

## 10. Voice

- Two private ElevenLabs agents, created and updated by `setup_agents.py`: an onboarding coach and a mock interviewer. Their prompts live in that file. Run it again after editing a prompt.
- The backend mints a short-lived token; the ElevenLabs key never reaches the browser.
- The coach is told the user's first name, course, university and visa type, so it spends the call on experience.
- The interviewer is told the job (or "general practice"), the session type and a summary of the user's achievements.
- **Live transcript.** During a call the user sees what was heard, sentence by sentence. ElevenLabs sends the user's words after each finished sentence, not word by word. The transcript stays on screen after the call and is saved with the journal entry.
- Every session is tagged with the user's id. The server-side transcript fallback returns a transcript only to that user.
- Each call is capped at 7 minutes by the agent configuration.

## 11. Security and privacy

| Concern | Handling |
|---|---|
| Passwords | Handled entirely by Supabase Auth |
| Token checking | Signature verified against the project's public keys (ES256 or RS256); expiry, issuer, audience and role checked. Tokens signed with the older shared secret are validated by asking Supabase, with the answer cached until the token expires |
| Who can see what | Every query filters by the caller's user id. Automated tests prove account A cannot read, change or delete account B's rows, including transcripts |
| Direct database access from browsers | Blocked: deny-all row-level security and no privileges for browser roles |
| Secrets | Only in `backend/.env` (git-ignored) and Vercel project settings |
| Cost abuse | Daily limits per user: `DAILY_AI_LIMIT` (40) and `DAILY_VOICE_LIMIT` (3), midnight to midnight UK time. A jobs refresh that scores anything is one AI action; Reed calls are free and bounded by the shared cache and 20 searches per refresh |
| Shared tables | Hold only public adverts and the public register. A user's fit, saved and dismissed jobs live in `job_matches`, filtered by user id like everything else |
| What Reed is told | Job titles and locations from the user's target roles. Never a name, an email or anything from their profile |
| The scheduled reload | Refused unless the request carries the secret; refused always when no secret is set. Compared in constant time |
| Links from outside | An advert's link is used only if it is on reed.co.uk over https; anything else is replaced by Reed's standard address |
| Right to erasure | "Delete my account" removes the login; cascading deletes remove every row |
| Transparency | A privacy notice page lists what is collected, why, and who processes it. Sign-up requires agreeing to it |
| Data location | Database and login in London. The language model runs in the United States; ElevenLabs processes audio outside the UK. The privacy notice says so |

**Before any public launch:**

1. Have the privacy notice reviewed, and set `CONTACT_EMAIL`.
2. Turn email confirmation back on, with a proper email provider connected to Supabase.
3. Use a separate Supabase project for live data.
4. Rotate every key that has ever been shared outside `backend/.env`.
5. ~~Add "not immigration advice" wording wherever visa rules appear.~~ Done in step 2.
6. Read Reed's terms of use (they are not published on its developer page) and ask Reed about call limits.
7. Re-read the gov.uk pages in `backend/data/visa_rules.json` and update the figures and the date. Nothing reminds you; the date on screen shows how old they are.

## 12. Running, testing and deploying

**Settings.** Copy `backend/.env.example` to `backend/.env` and fill it in. Each line has a comment saying where the value comes from. `DATABASE_URL` must be the Supabase **transaction pooler** string (port 6543); the direct database host is IPv6-only and will not resolve on most networks or on Vercel. A password containing `@`, `#` or `/` must be URL-encoded in that string.

**First-time setup.**

```
py -3.12 -m venv backend/.venv
backend\.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
cd backend
.venv\Scripts\python migrate.py          # create or update the tables
.venv\Scripts\python setup_agents.py     # create or update the voice agents
.venv\Scripts\python scripts/refresh_sponsors.py   # load the sponsor register (about 20 seconds)
cd ..\frontend
npm ci
```

**Run locally** (two terminals):

```
cd backend && .venv\Scripts\python -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

Open http://localhost:5173. Vite forwards `/api` to port 8000.

**Supabase settings the app relies on:** Authentication → Email → "Confirm email" off (for now); URL Configuration → Site URL and Redirect URLs include the app's address (`http://localhost:5173/**` locally, plus the Vercel address when deployed).

**Tests.**

```
cd backend && .venv\Scripts\python -m pytest tests
```

| Suite | Proves |
|---|---|
| `test_auth` | Valid tokens accepted; expired, forged, unsigned, wrong-issuer and wrong-role tokens rejected |
| `test_repo_*`, `test_migrate` | Every table's reads and writes; cascade on account deletion; one user's functions never return or change another's rows |
| `test_limits` | Caps, the UK-midnight boundary, the voice retry window |
| `test_analytics` | Stats and each diagnosis rule on empty and realistic data; the getting-started checklist |
| `test_llm`, `test_ai` | Fallback model, `<think>` stripping, retry, output normalisation, quote checking |
| `test_routes_*` | Every route needs a token; validation; isolation between two users through the API; limits; nothing saved when the AI fails |
| `test_voice`, `test_setup_agents`, `test_content`, `test_config` | Transcript ownership, agent variables, guidance content, settings |
| `test_sponsors` | Name normalising, the possible-match rule, Skilled Worker only, a bad register file leaving the stored one in place |
| `test_reed` | Request shape, parsing, salary and date rules, links, HTML to text, every failure as one error type, the key in no error or log |
| `test_jobs`, `test_repo_jobs` | Search plan, reposts, senior titles, shortlist, fit boundaries; the cache window; two users sharing a listing but not their matches |
| `test_routes_jobs` | Refresh end to end with Reed and the model replaced: cache, failures, limits, save, hide, track, the scheduler's secret, no key in any response |
| `test_visa` | Facts always carry source and date; no verdict; the figures appear nowhere but the rules file |
| `test_fixtures` | The test helpers never commit to the shared database |

Database tests run against the real database inside transactions that are rolled back, so they leave nothing behind. Because the real register and real adverts are in that database, tests use names that cannot occur in real data and never count whole tables. Run the suite on its own: a second database-heavy job at the same time has caused dropped connections.

**Deploy to Vercel.** Not yet done for this version. `vercel.json` schedules the register reload for 05:00 UTC every Monday; it works only if `CRON_SECRET` is set in the Vercel project. Add every variable from `backend/.env` to the Vercel project (use `BEDROCK_REGION`, not `AWS_REGION`, which Vercel reserves), add the Vercel address to Supabase's Site URL and Redirect URLs, then deploy. `vercel.json` builds the frontend, runs `app.py` as one function in London (`lhr1`), and leaves tests and scripts out of the bundle.

## 13. Verification record for step 0

| Check | Result | Date |
|---|---|---|
| Automated backend suite | 247 passed, 0 skipped, against the real Supabase database | 12 Oct 2026 |
| Real model, one call per AI task (`live_check.py`) | 11 of 11 passed, 2 to 8 seconds each | 12 Oct 2026 |
| Verified quotes on the real model | 3 of 3 achievements and 5 of 5 feedback points carried a quote that passed the transcript check | 12 Oct 2026 |
| Voice agents | Both created in ElevenLabs with the full configuration | 12 Oct 2026 |
| Signed-out pages in the browser | Landing, sign-up validation (no request sent on invalid input), privacy page, app pages blocked when signed out, "Sign in" visible at phone width | 12 Oct 2026 |
| Signed-in flow, by the project owner | Sign-up, details, voice onboarding, role families, a saved job, a tailored CV, stories, an application, a mock interview, and the live transcript | 12 Oct 2026 |
| Database after the owner's test | One account with rows in every table; 6 of 6 achievements carry a "You said" quote | 12 Oct 2026 |

**Not yet verified:**

- A second account in the browser seeing none of the first account's data (proved by automated tests, not yet by hand).
- Account deletion end to end against Supabase (the request is tested; a real deletion has not been run).
- The password-reset email flow.
- A Vercel deployment of this version.

## 14. Known limitations

- The tailored CV is a profile paragraph, selected bullets and a cover letter, not a full downloadable CV (step 3).
- Achievements can be deleted but not edited (step 1).
- No streaks, milestones or weekly plan yet (step 4); the home page shows a getting-started checklist and tracker findings.
- Networking and Peers are removed until their steps make them real.
- The user's speech appears in the live transcript per finished sentence, not word by word.
- Reply rates count recent applications that may not have had time to get a reply.
- The frontend has no automated tests; it is verified by hand.
- Job adverts come from Reed only. Graduate boards (Prospects, Bright Network, Handshake) have no public API and are not searched.
- Reed gives a posting date, not a time, so "posted in the last 48 hours" means today, yesterday or the day before.
- An agency advert does not name the employer, so nothing can be said about sponsorship for it. On Reed that is most adverts: in five real searches, 28 of 324 recent adverts came from a named employer.
- Reed sorts results by relevance and offers no date sort. The app takes the first 100 per search from employers and 100 from agencies.
- A recruiter that Reed lists as a direct employer, and whose name does not say what it is, is shown as an employer that is "not found on the register".
- Going rates and eligible occupations are linked to on gov.uk, not looked up per job: the app does not know a job's occupation code.
- The visa figures are updated by hand in `backend/data/visa_rules.json`.
- The production JavaScript bundle is large (over 500 kB) because of the voice library.

## 15. Jobs, sponsorship and visa facts (step 2)

**What a refresh does.** `POST /api/jobs/refresh`, called when the Jobs page opens with a search due, or from "Check for new jobs":

1. Reads the user's targeted role families and locations and builds the searches: up to three UK job titles per family in each location.
2. Skips any search somebody ran in the last six hours. Runs up to 20 of the rest on Reed, side by side, each as two calls (direct employers, agencies).
3. Stores the adverts, works out what the register says about each named employer, and deletes adverts over 30 days old.
4. Gives the user a private match for each advert posted in the last 14 days, merging reposts of the same job.
5. Picks the 15 unscored adverts that mention most of the user's skills (senior titles left out unless they asked for them), fetches each one's full text, and asks the model what each asks for and which achievement shows it.
6. Fit is requirements shown over requirements listed: 80% and over is a direct fit, 60 to 79 near, 40 to 59 a stretch, under 40 "not a match".

If the AI allowance is used up the adverts are still listed, unscored. If Reed is down the stored adverts stay and the page says so.

**Who really placed an advert** (`jobs.poster`). Reed's "direct employer" filter cannot be taken at face value. On 12 October 2026, in five real searches, 136 of 324 recent adverts came from four training and recruitment companies listed as direct employers, many selling a paid course ("No experience required", "our specialised career programme"), and one of those companies is on the sponsor register. So each advert is classed again when it is fetched:

| Class | When | Effect |
|---|---|---|
| `employer` | Reed says direct employer and the name does not say otherwise | Looked up on the register; counted in the figures |
| `agency` | Reed says agency, or the name contains recruit, career, staffing, resourcing or RPO | "Advertised by a recruiter or job board; the employer is not named." Scored and shown as a job |
| `training` | The name contains training, learning, course or bootcamp; or a recruiter-named company's advert reads like a programme; or the same company was seen selling one in the same fetch | Shown in a closed group, "Training programmes, not jobs". Never scored, never looked up, left out of the figures, and no Save or Track buttons |

A real employer's trainee job is left alone: the wording alone never reclassifies an advert.

**Sponsorship.** `sponsors.py` reduces a company name to what identifies it ("The Acme Group (UK) Ltd." and "ACME" both give `acme`) and compares it with the register:

| Result | Meaning | Shown as |
|---|---|---|
| `listed` | The names are the same after normalising | "On the sponsor register as <name> (Skilled Worker)." |
| `possible` | A longer registered name starts with the advert's name | "Possible match on the register: <name>. Check before applying." |
| `not_found` | Neither | "Not found on the register. Employers sometimes appear under a different registered name." |
| `agency` | A recruitment agency placed the advert | "Advertised by a recruitment agency; the employer is not named." |

The register is reloaded by `python scripts/refresh_sponsors.py`, or weekly on Vercel. A file that is missing, empty, too short or laid out differently is rejected and the stored copy is left as it was.

**Visa facts.** `backend/data/visa_rules.json` holds the two Skilled Worker salary figures, the gov.uk pages they came from and the date they were read (12 October 2026: £41,700 standard; £33,400 for those on a Student or Graduate visa or under 26). The wording on screen was agreed with the project owner and gives no verdict. A test fails if either figure is typed anywhere else in the code.

**Why Adzuna was left out.** Checked on 12 October 2026: the default allowance is 25 calls a minute, 250 a day, 1,000 a week and 2,500 a month, which a per-title search design uses up with a handful of users. Its terms allow showing adverts if each carries an "Adzuna" label linking to its site, but totals such as vacancy counts and average salaries need written consent. To add it: write to Adzuna first; then add a client beside `reed.py` and a second entry where `jobs.fetch` chooses its source.

## 16. Verification record for step 2

| Check | Result | Date |
|---|---|---|
| Automated backend suite | 542 passed, 0 skipped, against the real database | 12 Oct 2026 |
| Frontend | Lints with no errors; builds | 12 Oct 2026 |
| Real model, one call per AI task (`live_check.py`) | 13 of 13 passed, including job fit: a matching advert credited to real achievements, an unrelated one scored 0% | 12 Oct 2026 |
| Job fit on the real model, repeated | 8 of 8 runs complete and valid after the parser fix (3 of 12 failed before it) | 12 Oct 2026 |
| Scoring time for a full refresh | 15 adverts in 13 seconds (three calls side by side) | 12 Oct 2026 |
| Real sponsor register | 123,175 Skilled Worker sponsors loaded in 22 seconds from the file gov.uk published that day. Spot checks: Deloitte LLP and Monzo Bank listed; Tesco and Barclays possible matches; a made-up name not found | 12 Oct 2026 |
| Visa figures | Read from gov.uk the same day; the guide was last changed on 14 Sep 2026 | 12 Oct 2026 |
| Signed-out pages in the browser | Landing and privacy pages show the new copy with no console errors | 12 Oct 2026 |
| Reed's real replies (`reed_check.py`) | Every field, the date format and the links are as `reed.py` assumed: 200 of 200 adverts read. Search descriptions are about 450 characters; the full advert runs to 2,000 to 3,500 | 12 Oct 2026 |
| Real searches, five titles and places | 0 failures; about one second for a search of 200 adverts | 12 Oct 2026 |
| Real adverts stored and matched to the register, in a transaction then rolled back | 390 adverts stored in 0.3 seconds. Named employers found correctly: FDM Group, Isio, Unipart, Brown & Brown listed; Live Nation, Sagacity, Shift4 possible. One doubtful possible match ("The Hyde Group" to "Hyde Farm Limited"), which the wording asks the user to check | 12 Oct 2026 |
| Real adverts scored against a sample profile | 7 of 7 scored in 17 seconds after fetching each full advert; fits from 17% to 67% | 12 Oct 2026 |
| The training rule on real adverts | 136 of 324 classed as training, from five companies; none of the 28 left as employers read like a programme | 12 Oct 2026 |

**Not yet verified:**

- **A refresh through the app for a real account.** Every part has run on real data separately (search, storing, register matching, full adverts, scoring), but not yet as one request from the Jobs page.
- **The Jobs page, the role family figures and the offer check on screen**, signed in. Verified by lint, build and the API tests only.
- **Fit scores on a real profile.** Checked only against a two-achievement sample.
- **All eight hand checks in the step document.**
- **The weekly reload on Vercel.** Nothing is deployed. The route is tested; the schedule and the 60-second limit there are not.
- **Reed's terms of use and call limits.** Not published on its developer page.

