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
| 2 | Real jobs from Adzuna and Reed, fit scoring, sponsor register, visa salary facts | 0 | Designed | `careerai-step-2-real-jobs` |
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
 │                                 └─ ElevenLabs API                              ← mints voice session tokens
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

Smaller behaviours worth knowing:

- The "applications are not getting replies" finding also covers applications with no role family.
- The referral finding stays silent when the user has no job-board applications, because it compares against them.
- The "you apply too slowly" finding needs at least four applications that have a posted date.
- A pasted job is still saved, without an AI summary, if the AI fails or the daily limit is reached.
- Role family suggestions carry no salary or sponsorship figures. In the demo those were model guesses; they return in step 2 computed from real listings.
- Step 0 gives no visa advice. It shows only the user's own visa end date and a countdown.

## 6. Code map

```
backend/
  main.py          routes only: who is calling, validate input, call modules, return JSON
  auth.py          access token → User. FastAPI dependency current_user
  db.py            connection helper for the pooled Postgres connection
  repo.py          ALL SQL. Every function takes (conn, user_id, ...)
  limits.py        per-user daily caps
  analytics.py     tracker stats, diagnosis rules, getting-started checklist. Pure functions
  ai.py            one function per AI task: prompt, output shaping, quote checking
  llm.py           one call path to Bedrock, fallback model, JSON parsing
  voice.py         ElevenLabs token minting and transcript fetch (owner only)
  content.py       loads data/content.json, the static guidance copy
  config.py        settings from the environment, then backend/.env
  migrate.py       applies migrations/*.sql not yet recorded in schema_migrations
  setup_agents.py  creates or updates the two ElevenLabs agents and writes their ids to .env
  scripts/live_check.py   one real call per AI task (uses credits)
  tests/           pytest suite
frontend/src/
  App.jsx          session gate and app shell
  supabase.js      Supabase client built from /api/config
  api.js           fetch wrapper: bearer token, one refresh-and-retry on 401
  ui.jsx           shared pieces: menu, FamilyCard, ErrorRetry, Empty, date helpers
  VoiceAgent.jsx   one ElevenLabs call with the live transcript panel
  components/      DetailsForm, BackgroundInput (voice or paste), Jobs (picker and paste-a-job)
  pages/           Landing, Auth, Privacy, Onboarding, Home, Profile, Pathways, Resume,
                   Interview, Applications, Journal, Account
app.py             Vercel entry point: the API plus the built frontend
```

## 7. Data model

All tables are in the `public` schema. Every row has `user_id` referencing `auth.users` with `on delete cascade`, so deleting a login removes all of that person's data. Row-level security is on with no policies, and the browser-facing roles (`anon`, `authenticated`) have no privileges.

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
| `schema_migrations` | Which migration files have been applied |

Schema changes are numbered SQL files in `backend/migrations/`, applied with `python migrate.py`. Applied so far: `001_initial`, `002_journal_transcript`.

A reference from one row to another (for example an application's CV version) is stored only if the target belongs to the same user; otherwise it is saved as null.

## 8. API

`GET /api/config` is public and returns only values safe to expose. Every other route needs a valid token (401 without one) and touches only the caller's rows. Ids are UUIDs: a malformed id answers 422, an unknown or foreign one 404.

| Route | Purpose |
|---|---|
| `GET /api/state` | Everything the pages need for the signed-in user, plus stats, next steps, guidance content and today's usage |
| `PUT /api/profile` | Save "Your details" |
| `DELETE /api/account` | Delete the login and all data |
| `DELETE /api/achievements/{id}` | Remove an achievement |
| `POST /api/families/{id}/target` | Tick or untick a role family |
| `POST /api/jobs`, `DELETE /api/jobs/{id}` | Add a pasted job (with an AI summary), remove it |
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
| Cost abuse | Daily limits per user: `DAILY_AI_LIMIT` (40) and `DAILY_VOICE_LIMIT` (3), midnight to midnight UK time |
| Right to erasure | "Delete my account" removes the login; cascading deletes remove every row |
| Transparency | A privacy notice page lists what is collected, why, and who processes it. Sign-up requires agreeing to it |
| Data location | Database and login in London. The language model runs in the United States; ElevenLabs processes audio outside the UK. The privacy notice says so |

**Before any public launch:**

1. Have the privacy notice reviewed, and set `CONTACT_EMAIL`.
2. Turn email confirmation back on, with a proper email provider connected to Supabase.
3. Use a separate Supabase project for live data.
4. Rotate every key that has ever been shared outside `backend/.env`.
5. Add "not immigration advice" wording wherever visa rules appear (from step 2).

## 12. Running, testing and deploying

**Settings.** Copy `backend/.env.example` to `backend/.env` and fill it in. Each line has a comment saying where the value comes from. `DATABASE_URL` must be the Supabase **transaction pooler** string (port 6543); the direct database host is IPv6-only and will not resolve on most networks or on Vercel. A password containing `@`, `#` or `/` must be URL-encoded in that string.

**First-time setup.**

```
py -3.12 -m venv backend/.venv
backend\.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
cd backend
.venv\Scripts\python migrate.py          # create or update the tables
.venv\Scripts\python setup_agents.py     # create or update the voice agents
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

Database tests run against the real database inside transactions that are rolled back, so they leave nothing behind.

**Deploy to Vercel.** Not yet done for this version. Add every variable from `backend/.env` to the Vercel project (use `BEDROCK_REGION`, not `AWS_REGION`, which Vercel reserves), add the Vercel address to Supabase's Site URL and Redirect URLs, then deploy. `vercel.json` builds the frontend, runs `app.py` as one function in London (`lhr1`), and leaves tests and scripts out of the bundle.

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

- Jobs must be pasted; there are no job listings, sponsor checks or visa rules yet (step 2).
- The tailored CV is a profile paragraph, selected bullets and a cover letter, not a full downloadable CV (step 3).
- Achievements can be deleted but not edited (step 1).
- No streaks, milestones or weekly plan yet (step 4); the home page shows a getting-started checklist and tracker findings.
- Networking and Peers are removed until their steps make them real.
- The user's speech appears in the live transcript per finished sentence, not word by word.
- Reply rates count recent applications that may not have had time to get a reply.
- The frontend has no automated tests; it is verified by hand.
- The production JavaScript bundle is large (over 500 kB) because of the voice library.
