# Step 0: Accounts and Saved Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-persona demo into a real multi-user app: Supabase login, per-user data in Postgres, and every existing live feature running on the signed-in person's own data with no seeded or canned content.

**Architecture:** The browser uses `supabase-js` only to log in and get an access token. Every `/api/*` call carries that token to FastAPI, which verifies it against Supabase's public keys and is the only thing that reads or writes Postgres (pooled connection, plain SQL in `repo.py`). LLM and voice calls stay server-mediated as today.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PyJWT, httpx, pytest · React 19, Vite 8, `@supabase/supabase-js`, `@elevenlabs/client` · Supabase Auth + Postgres · AWS Bedrock (Mantle) · ElevenLabs Agents · Vercel.

**Spec:** `docs/superpowers/specs/2026-10-11-step-0-accounts-and-persistence-design.md`

## Global Constraints

- Python **3.12** for `backend/.venv` (`py -3.12`), matching Vercel's default. Node **≥ 20.19 or ≥ 22.12** (Vite 8 refuses older; this machine has 20.11.0 and must be upgraded first).
- Every route except `GET /api/config` requires a valid token and answers 401 without one.
- Every `repo.py` function takes `(conn, user_id, ...)` and filters by `user_id`. No query touches user data without it.
- Never hold a database connection open across an LLM or ElevenLabs call: read and record usage in one short transaction, call out, write results in a second.
- `main.py` reaches the database only through `db.transaction()`, called via the module (`db.transaction()`), so tests can substitute it.
- `repo.py` returns plain dicts: UUIDs as `str`, dates as `datetime.date`, timestamps as `datetime`.
- No fictional person, company, job, date or canned AI answer in shipped code (`backend/*.py`, `backend/data/`, `frontend/src/`). Test fixtures under `backend/tests/` use obviously synthetic values such as "Company A".
- AI functions return the model's result or raise. No fallback content. Nothing is saved from a failed call.
- Daily limits default to `DAILY_AI_LIMIT=40`, `DAILY_VOICE_LIMIT=3`. A day is midnight to midnight Europe/London, computed in SQL.
- User-facing error strings are exactly those in spec section 13.
- British English in all copy and prompts. No em dashes in UI copy or prompts.
- Secrets live only in `backend/.env`. Never print, log or commit them.
- Claude never types a password into the app or creates accounts through Supabase. During browser verification the project owner performs sign-up, sign-in, voice calls and account deletion; Claude drives everything else.
- Commit locally after every task with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push.

## Review Focus

Inputs the spec implies but does not spell out, most likely first. Each has a test in the task named.

1. **Malformed or foreign ids.** A non-UUID id in a path or body answers 422, never 500. An id belonging to another user, or already deleted, answers 404 for that row, and is stored as null when it is only a reference on a new application or CV. (Tasks 8, 10)
2. **Odd model output.** Role families with duplicate names in different case, a `fit` outside the three values, `overlap` as `"85%"` or `150`, or zero usable achievements must be normalised or rejected with a clear message, never a database constraint error. (Tasks 4, 7, 11)
3. **Input size extremes.** A transcript under 20 characters (call ended at once) or over 30,000, or a job description under 30 or over 20,000, answers 422 with a plain message before any model call. (Task 11)
4. **Session expiry mid-use.** A 401 on an open page triggers one silent token refresh and retry; a second 401 returns the user to sign-in with no blank screen or loop. (Task 12)
5. **Dates that break arithmetic.** A visa end date in the past shows a message, not negative days. `posted_on` after `applied_on` answers 422. Applications with no posted date are left out of timing figures without dividing by zero. (Tasks 5, 10, 14)

## File Map

```
backend/
  config.py            modify   + supabase_url(), daily_limit()
  auth.py              create   token → User; FastAPI dependency
  db.py                create   connect(), transaction()
  repo.py              create   all SQL
  limits.py            create   daily caps
  content.py           create   loads data/content.json
  data/content.json    create   static guidance copy
  data/seed.json       delete
  store.py             delete
  llm.py               modify   fallback model, <think> stripping
  ai.py                modify   no fallbacks, retry, profile-based prompts
  analytics.py         modify   real-data stats, diagnosis, next steps
  voice.py             modify   transcript ownership check
  setup_agents.py      modify   coach prompt and variables
  main.py              rewrite  routes only
  migrate.py           create   migration runner
  migrations/001_initial.sql  create
  scripts/live_check.py       create   one real call per AI task
  pytest.ini, requirements.txt, requirements-dev.txt, .env.example
  tests/conftest.py, test_config.py, test_auth.py, test_llm.py, test_ai.py,
        test_analytics.py, test_migrate.py, test_repo_profile.py,
        test_repo_records.py, test_limits.py, test_routes_data.py, test_routes_ai.py
frontend/src/
  supabase.js          create   client from /api/config
  api.js               modify   bearer token, 401 refresh-and-retry
  App.jsx              rewrite  session gate and shell
  ui.jsx               modify   menu, helpers, ErrorRetry, Empty
  VoiceAgent.jsx       modify   userId, consent line
  components/DetailsForm.jsx, components/Jobs.jsx   create
  pages/Auth.jsx, pages/Privacy.jsx, pages/Account.jsx   create
  pages/Landing.jsx, Onboarding.jsx, Home.jsx, Profile.jsx, Pathways.jsx,
        Resume.jsx, Interview.jsx, Applications.jsx, Journal.jsx   modify
  pages/Networking.jsx, pages/Peers.jsx   delete
  index.css            modify
docs/ARCHITECTURE.md   create;  PLAN.md, docs/phases/Phase-1.md → docs/archive/
vercel.json, requirements.txt (root), .gitignore   modify
```

## Prerequisites (project owner, about 15 minutes)

These block the tasks marked **[needs Supabase]** or **[needs Node]**. Tasks 1 to 5 need neither.

1. Install Node 22 or 24 LTS from nodejs.org, then reopen the terminal. `node --version` must show ≥ 20.19 or ≥ 22.12.
2. Create a Supabase project in **London (`eu-west-2`)**.
3. Supabase → Authentication → Sign In / Providers → Email: turn **Confirm email** off.
4. Supabase → Authentication → URL Configuration: Site URL `http://localhost:5173`; add `http://localhost:5173/**` to Redirect URLs.
5. Copy `backend/.env.example` (rewritten in Task 1) to `backend/.env` and fill in every value. `DATABASE_URL` is the **Transaction pooler** string from the Connect dialog (port 6543) with the database password filled in.
6. Rotate the Bedrock key that was pasted into chat and put the new one in `backend/.env`.

---

### Task 1: Tooling, test harness and configuration helpers

**Files:**
- Create: `backend/pytest.ini`, `backend/requirements-dev.txt`, `backend/tests/test_config.py`
- Modify: `backend/requirements.txt`, `backend/.env.example`, `backend/config.py`, `.gitignore`

**Interfaces:**
- Produces: `config.supabase_url() -> str` (no trailing slash), `config.daily_limit(kind: str) -> int` for `kind` in `"ai"`, `"voice"`.

- [ ] **Step 1: Create the environment.** `py -3.12 -m venv backend/.venv`. Set `backend/requirements.txt` to `fastapi`, `uvicorn[standard]`, `anthropic[bedrock]`, `httpx`, `python-dotenv`, `psycopg[binary]`, `PyJWT[crypto]`. Set `backend/requirements-dev.txt` to `-r requirements.txt` and `pytest`. Install the dev file into the venv.
- [ ] **Step 2: `backend/pytest.ini`** with `pythonpath = .`, `testpaths = tests`, and a registered marker `db: needs DATABASE_URL`.
- [ ] **Step 3: Rewrite `backend/.env.example`** to the block in spec section 12, plus `CONTACT_EMAIL=` (optional, shown on the privacy page). Placeholders start with `your-` so `config.env` treats them as unset. Remove the passcode and Upstash lines.
- [ ] **Step 4: Harden `.gitignore`**: add `.env.*` and `!.env.example`.
- [ ] **Step 5: Write failing tests** in `tests/test_config.py` (set values with `monkeypatch.setenv`, and `monkeypatch.setattr(config, "ENV_PATH", tmp_path / "none")`):

```python
def test_supabase_url_strips_trailing_slash():   # SUPABASE_URL="https://x.supabase.co/" → "https://x.supabase.co"
def test_daily_limit_defaults():                 # unset → daily_limit("ai") == 40, daily_limit("voice") == 3
def test_daily_limit_reads_env():                # DAILY_AI_LIMIT="5" → 5
def test_daily_limit_bad_value_uses_default():   # DAILY_VOICE_LIMIT="abc" → 3
```

- [ ] **Step 6: Run** `.venv/Scripts/python -m pytest tests/test_config.py -v` from `backend/` (every later `pytest` command runs the same way). Expected: 4 failures (attribute missing).
- [ ] **Step 7: Implement** the two helpers in `config.py`.
- [ ] **Step 8: Run again.** Expected: 4 passed.
- [ ] **Step 9: Commit** `chore: test harness, dependencies and config helpers`.

---

### Task 2: Token verification (`auth.py`)

**Files:**
- Create: `backend/auth.py`, `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `config.supabase_url()`, `config.env("SUPABASE_PUBLISHABLE_KEY")`.
- Produces:
  - `@dataclass(frozen=True) class User: id: str; email: str; name: str`
  - `class AuthError(Exception)`
  - `verify_token(token: str) -> User` (raises `AuthError`)
  - `current_user(authorization: str | None = Header(None)) -> User`, a FastAPI dependency that raises `HTTPException(401, "Sign in to continue.")`
  - Test seam: `auth._signing_key(token: str)` returns the public key for an asymmetric token; `auth._user_from_supabase(token: str) -> dict` handles HS256.

- [ ] **Step 1: Write failing tests.** A fixture generates an EC P-256 key pair with `cryptography`, monkeypatches `auth._signing_key` to return the public key, sets `SUPABASE_URL=https://proj.supabase.co`, and provides `make_token(**overrides)` signing ES256 with defaults `sub="11111111-1111-1111-1111-111111111111"`, `email="a@example.test"`, `role="authenticated"`, `aud="authenticated"`, `iss="https://proj.supabase.co/auth/v1"`, `exp=now+3600`, `user_metadata={"full_name": "Test User"}`.

```python
def test_valid_token_returns_user():        # User(id=sub, email="a@example.test", name="Test User")
def test_missing_name_gives_empty_string(): # user_metadata={} → name == ""
def test_expired_token_rejected():          # exp=now-10 → AuthError
def test_wrong_issuer_rejected():           # iss="https://evil.example/auth/v1" → AuthError
def test_non_authenticated_role_rejected(): # role="anon" → AuthError
def test_forged_signature_rejected():       # signed with a second key → AuthError
def test_garbage_token_rejected():          # "not-a-jwt" → AuthError
def test_hs256_token_uses_supabase_check(): # HS256 token; _user_from_supabase patched to return
                                            # {"id": "...", "email": "b@example.test", "user_metadata": {"full_name": "B"}} → that User
def test_hs256_rejected_when_supabase_says_no():  # patched to raise AuthError → AuthError
def test_dependency_401_without_header():   # current_user(None) → HTTPException 401
def test_dependency_401_bad_scheme():       # current_user("Token abc") → 401
```

- [ ] **Step 2: Run.** Expected: collection error, module missing.
- [ ] **Step 3: Implement.**
  - Read the unverified header. `alg` in `{"ES256", "RS256"}`: `jwt.decode(token, _signing_key(token), algorithms=["ES256", "RS256"], audience="authenticated", issuer=f"{supabase_url()}/auth/v1")`, then require `role == "authenticated"`.
  - `_signing_key` uses a module-level `jwt.PyJWKClient(f"{supabase_url()}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=600)`, built lazily.
  - `alg == "HS256"`: `_user_from_supabase` does `GET {supabase_url()}/auth/v1/user` with headers `apikey: <publishable key>` and `Authorization: Bearer <token>`, timeout 10 s. Non-200 raises `AuthError`. Cache the result in a dict keyed by `sha256(token)` until the token's unverified `exp`.
  - Any other `alg`, any `jwt` exception or any network error becomes `AuthError`.
- [ ] **Step 4: Run.** Expected: 11 passed.
- [ ] **Step 5: Commit** `feat: verify Supabase access tokens`.

---

### Task 3: LLM call path (`llm.py`)

**Files:**
- Modify: `backend/llm.py`
- Create: `backend/tests/test_llm.py`

**Interfaces:**
- Produces:
  - `class LLMNotConfigured(Exception)` (unchanged)
  - `complete(system: str, user: str, max_tokens: int = 1500) -> str`
  - `complete_json(system: str, user: str, max_tokens: int = 1500) -> dict | list` (raises `ValueError` when no JSON is found)
  - `strip_reasoning(text: str) -> str`
  - Test seam: `llm._call(model: str, system: str, user: str, max_tokens: int) -> str` does one request to one model.

- [ ] **Step 1: Write failing tests** (patch `llm._call`; set `BEDROCK_REGION`, `BEDROCK_MODEL_ID=primary.model`, `BEDROCK_API_KEY`):

```python
def test_strip_reasoning_removes_think_block():     # "<think>{not json}</think>{\"a\":1}" → "{\"a\":1}"
def test_strip_reasoning_unterminated_block():      # "<think>abc" → ""
def test_complete_json_ignores_braces_in_think():   # _call returns "<think>{x}</think>\n```json\n{\"a\": 1}\n```" → {"a": 1}
def test_complete_json_no_json_raises_value_error():
def test_fallback_used_on_403_and_404():            # _call raises httpx.HTTPStatusError(403) for primary; with
                                                    # BEDROCK_FALLBACK_MODEL_ID=fallback.model the second call gets "fallback.model"
def test_no_fallback_on_500():                      # HTTPStatusError(500) propagates; _call called once
def test_no_fallback_when_unset():                  # 403 propagates when the fallback id is empty
def test_not_configured_without_model():            # BEDROCK_MODEL_ID unset → LLMNotConfigured
```

- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement.** Move the existing per-prefix dispatch into `_call`. `complete` calls `_call` with the primary model; on `httpx.HTTPStatusError` or `anthropic.APIStatusError` with status 403 or 404, and a non-empty fallback id different from the primary, it calls `_call` once with the fallback. `complete_json` applies `strip_reasoning` before fence stripping and JSON extraction. Fix the `LLMNotConfigured` message to "Set BEDROCK_REGION and BEDROCK_MODEL_ID in backend/.env".
- [ ] **Step 4: Run.** Expected: 8 passed.
- [ ] **Step 5: Commit** `feat: fallback model and reasoning-safe JSON parsing`.

---

### Task 4: AI tasks without fallbacks (`ai.py`)

**Files:**
- Modify: `backend/ai.py`
- Create: `backend/tests/test_ai.py`

**Interfaces:**
- Consumes: `llm.complete_json`, `llm.LLMNotConfigured`.
- Produces (each returns the shaped dict or raises `ai.AIError`; `LLMNotConfigured` passes through):
  - `class AIError(Exception)`
  - `extract_achievements(transcript: str, profile: dict) -> dict` → `{"items": [{"title","raw","uk_version","skills": [str],"outcome","scale","context_note"}], "pitch": str}`
  - `suggest_families(achievements: list[dict], profile: dict) -> dict` → `{"families": [{"name","fit","overlap": int,"uk_titles": [str],"why","needs": [{"need","shown_by"}]}]}`
  - `summarise_job(title: str, company: str, description: str, family_names: list[str]) -> dict` → `{"summary": str, "keywords": [str], "family": str}` (`family` is one of `family_names` or `""`)
  - `tailor(job: dict, achievements: list[dict], profile: dict) -> dict` → `{"profile","bullets": [{"text","achievement_id"}],"keywords": [str],"cover_letter": {"why_them","why_you","what_you_deliver"},"gaps": [str]}`
  - `star(achievement: dict) -> dict` → `{"title","competency","situation","task","action","result","strength","tip"}`
  - `interview_feedback(transcript: str, job: dict | None, profile: dict, interview_type: str) -> dict` (shape unchanged from today's `data`)
  - `tone(text: str, mode: str) -> dict`, `explain_diagnosis(findings: list, stats: dict, profile: dict) -> dict` (shapes unchanged)
- `profile` keys the prompts may use: `full_name`, `course`, `university`, `visa_type`, `visa_end_date`.

- [ ] **Step 1: Write failing tests** (patch `ai.complete_json` with a list of scripted returns or exceptions):

```python
def test_run_retries_once_on_malformed_json():   # 1st raises ValueError, 2nd returns valid → result returned, 2 calls
def test_run_retries_once_on_missing_required(): # tailor: 1st returns {"bullets": []}, 2nd valid → 2 calls
def test_run_raises_ai_error_after_two_failures():  # both raise ValueError → AIError, exactly 2 calls
def test_not_configured_is_not_retried():        # LLMNotConfigured propagates after 1 call
def test_extract_drops_items_without_text():     # item with empty uk_version, raw and title is removed
def test_extract_fills_uk_version_from_raw():    # uk_version "" and raw "x" → uk_version "x"
def test_extract_zero_usable_items_returns_empty():  # only empty items → {"items": [], ...} after ONE call, no AIError
def test_families_normalised():                  # input: fit "Direct Fit" → "direct"; fit "unknown" → "near";
                                                 # overlap "85%" → 85; overlap 150 → 100; overlap -5 → 0
def test_families_deduplicated_case_insensitively():  # "Data Analyst" and "data analyst " → one, first kept
def test_families_needs_are_objects():           # needs ["SQL"] → [{"need": "SQL", "shown_by": ""}]
def test_summarise_job_family_must_be_known():   # model returns family "Astronaut", names ["Data Analyst"] → family == ""
def test_tailor_requires_bullets_and_letter():   # missing cover_letter on both attempts → AIError
def test_no_demo_content_in_module():            # source of ai.py contains none of: "Aditi", "Infosys", "Exeter", "Lumen", "fallback"
```

- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement.**
  - Replace every canned fallback dict with an empty **shape template** used only by `_conform` for keys and types.
  - `_run(task, system, user, template, max_tokens, required) -> dict`: up to 2 attempts; `ValueError`, `json.JSONDecodeError`, `httpx.HTTPError` and a missing required field count as failures; after the second, raise `AIError(task)`. Log failures with `log.warning`, never the prompt or the reply.
  - Add `needs` to the families prompt: "For each family list 4 to 6 things UK employers expect, and for each name the candidate's achievement title that shows it, or an empty string if it is a gap." Remove the salary and sponsorship instructions.
  - `extract_achievements` has no required fields: a transcript with nothing usable is a valid empty result, which the route turns into a 422. `tailor` requires `bullets` and `cover_letter`; `suggest_families` requires `families`; `star` requires `situation` and `action`.
  - Remove `cv_version_name`, `targets` and `visa` from prompts and shapes. Rename `evidence_id` to `achievement_id` in the tailor prompt.
  - `tailor` builds its job text from `job["title"]`, `job["company"]`, `job["description"]` (first 6,000 characters) and `job["keywords"]`.
  - `interview_feedback` with `job=None` uses the line "Role: general practice, no specific job".
  - Delete `outreach` and `peer_notes`.
- [ ] **Step 4: Run.** Expected: 13 passed.
- [ ] **Step 5: Commit** `feat: AI tasks return real results or fail, with one retry`.

---

### Task 5: Tracker analytics on real data (`analytics.py`)

**Files:**
- Modify: `backend/analytics.py`
- Create: `backend/tests/test_analytics.py`

**Interfaces:**
- Produces:
  - `STAGES = ("applied","no_response","rejected","screening","interview","rejected_after_interview","offer")`
  - `SOURCES = ("Company site","Referral","LinkedIn","Indeed","Graduate job board","University careers service","Recruiter","Other")`
  - `compute(applications: list[dict], families: list[dict], cv_versions: list[dict], stories: list[dict]) -> dict` → `{"funnel","by_family","by_cv","by_source","timing","findings"}`
  - `next_steps(state: dict) -> list[dict]`, each `{"id","text","why","page","done"}`
- Application keys read: `role_family_id`, `cv_version_id`, `source`, `stage`, `applied_on` (date), `posted_on` (date or None).
- Finding shape: `{"id","type","severity","title","evidence","action","link": {"page","label"} | None}`.

- [ ] **Step 1: Write failing tests.** A helper `app(**kw)` builds an application with defaults `stage="applied"`, `source="Company site"`, `applied_on=date(2026, 10, 1)`, others `None`.

```python
def test_empty_tracker_has_no_findings_and_zero_rates():
    # compute([], [], [], []) → findings == [], funnel["applied"] == 0, funnel["response_rate"] == 0, timing["avg_days"] == 0
def test_by_family_labels_unknown_as_no_role_family():   # role_family_id None → label "No role family"
def test_by_cv_labels_missing_as_no_cv_recorded():       # cv_version_id None → label "No CV recorded"
def test_low_reply_rule_fires_at_four_apps_under_15_percent():
    # 4 apps in family F, 0 responses → one finding id "cv-<F>", link == {"page": "resume", "label": "Tailor a CV"}
def test_low_reply_rule_silent_at_three_apps():
def test_low_reply_detail_when_no_tailored_cv():         # all cv_version_id None → evidence ends "None of them used a tailored CV."
def test_low_reply_detail_when_other_family_cv():        # cv belongs to family G → evidence contains "a CV written for another role"
def test_story_rule_needs_three_interviews_no_offers():  # link == {"page": "interview", "label": "Practise an interview"}
def test_story_rule_wording_without_stories():           # evidence contains "You have no STAR stories saved yet."
def test_network_rule_has_no_link():                     # referrals 2/2 replied, 10 job-board apps 0 replies → finding "network", link is None
def test_timing_excludes_apps_without_posted_date():     # 2 apps with posted_on, 3 without → timing fast+slow applied == 2
def test_timing_rule_needs_four_timed_apps():            # 3 timed apps, avg 5 days → no "timing" finding
def test_no_direction_rule():                            # no finding has type "direction"
def test_next_steps_empty_state():                       # 6 steps in order profile, roles, job, cv, interview, application; all done False
def test_next_steps_progress():                          # state with 1 achievement and 1 targeted family → first two done, rest not
def test_next_steps_interview_needs_interview_journal_entry():  # a "coach" journal entry does not tick "interview"
```

- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement.**
  - `JOB_BOARDS = {"LinkedIn", "Indeed", "Graduate job board"}`. Remove `visa_fit` and the direction rule.
  - Timing uses `(applied_on - posted_on).days` over applications that have `posted_on`; fast means ≤ 2. The timing rule requires at least 4 timed applications, an average over 3 days and a higher fast reply rate; its link is `{"page": "pathways", "label": "Where to look"}`.
  - Story rule action: "Run a mock interview and strengthen your STAR stories before the next one."
  - Network rule action: "Ask people you know inside companies that are hiring for a referral before you apply."
  - `next_steps` copy, in order:

    | id | text | why | page | done when |
    |---|---|---|---|---|
    | profile | Build your profile | Your CVs, stories and interview practice are all built from it. | profile | ≥ 1 achievement |
    | roles | Pick your target roles | Your targets decide what the app prepares you for. | pathways | ≥ 1 targeted family |
    | job | Add a job you want | Paste a job description so your CV and practice fit a real role. | resume | ≥ 1 saved job |
    | cv | Tailor a CV for it | UK employers shortlist on evidence that matches the job description. | resume | ≥ 1 CV version |
    | interview | Practise an interview | Most UK interviews expect STAR answers, said out loud. | interview | ≥ 1 journal entry of type `interview` |
    | application | Log your first application | The tracker can only tell you what to fix once it has your applications. | applications | ≥ 1 application |

- [ ] **Step 4: Run.** Expected: 16 passed.
- [ ] **Step 5: Commit** `feat: tracker analytics and next steps on real data`.

---

### Task 6: Schema, connection helper and migration runner **[needs Supabase]**

**Files:**
- Create: `backend/db.py`, `backend/migrate.py`, `backend/migrations/001_initial.sql`, `backend/tests/conftest.py`, `backend/tests/test_migrate.py`

**Interfaces:**
- Produces:
  - `db.connect() -> psycopg.Connection`: `psycopg.connect(env("DATABASE_URL"), row_factory=dict_row, prepare_threshold=None, connect_timeout=10, sslmode="require")`
  - `db.transaction()`: context manager yielding a connection; commits on success, rolls back on error, always closes.
  - `migrate.pending(conn) -> list[str]`, `migrate.apply_all(conn) -> list[str]` (versions applied, in order). `apply_all` does not commit; `python migrate.py` applies, commits once and prints them.
  - Fixtures in `conftest.py`:
    - `conn`: one connection per test, rolled back at the end. Skips with "DATABASE_URL not set" when it is empty.
    - `user_a`, `user_b`: ids of two rows inserted into `auth.users` inside that transaction with `insert into auth.users (id, email) values (%s, %s)` and emails `a@example.test`, `b@example.test`.
  - If Supabase refuses the insert into `auth.users`, change the two fixtures to create users once per session with `POST {SUPABASE_URL}/auth/v1/admin/users` (`{"email": ..., "email_confirm": true}`, headers `apikey` and `Authorization: Bearer` both the secret key) and delete them in teardown. Record which path was used in the commit message.

- [ ] **Step 1: Write `001_initial.sql`.** Tables and columns exactly as spec section 6, with these pinned details:
  - Every `user_id` is `uuid not null references auth.users(id) on delete cascade`; `profiles.user_id` is also the primary key and `profiles.full_name` is `text not null default ''`.
  - Text columns the UI always renders are `not null default ''`; arrays are `text[] not null default '{}'`; `needs`, `points`, `actions` are `jsonb not null default '[]'`; `cv_versions.content` is `jsonb not null`.
  - Checks: `visa_type in ('student','graduate')`, `fit in ('direct','near','stretch')`, `overlap between 0 and 100`, `achievements.source in ('voice','paste')`, `applications.stage in (<the seven STAGES>)`, `journal_entries.type in ('coach','interview')`, `usage_events.kind in ('ai','voice')`, and `applications: posted_on is null or posted_on <= applied_on`.
  - `applications.applied_on date not null default ((now() at time zone 'Europe/London')::date)`.
  - Cross-table references (`role_family_id`, `saved_job_id`, `cv_version_id`, `achievement_id`) are nullable with `on delete set null`.
  - `create unique index role_families_user_name on role_families (user_id, lower(name))`.
  - `create index` on `user_id` for every table, and `usage_events (user_id, kind, created_at)`.
  - `alter table <t> enable row level security` for all nine tables. No policies.
- [ ] **Step 2: Write failing tests** in `test_migrate.py` (marked `db`):

```python
def test_apply_all_is_idempotent(conn):        # after apply_all, pending(conn) == [] and a second apply_all returns []
def test_all_tables_exist_with_rls(conn):
    # for each of the 9 tables + schema_migrations: pg_class.relrowsecurity is true
def test_no_policies_exist(conn):              # select count(*) from pg_policies where schemaname = 'public' → 0
def test_cascade_on_user_delete(conn, user_a): # insert a profile and an achievement for user_a, delete the auth.users row → both gone
def test_posted_after_applied_rejected(conn, user_a):  # insert application posted_on > applied_on → psycopg.errors.CheckViolation
```

- [ ] **Step 3: Run** `pytest tests/test_migrate.py -v`. Expected: failures (modules missing).
- [ ] **Step 4: Implement `db.py` and `migrate.py`.** The runner creates `schema_migrations (version text primary key, applied_at timestamptz not null default now())` with RLS enabled if absent, then applies each `migrations/*.sql` not yet recorded, in filename order, recording the filename stem.
- [ ] **Step 5: Apply for real:** `python migrate.py` from `backend/`. Expected output: `applied 001_initial`.
- [ ] **Step 6: Run the tests.** Expected: 5 passed, 0 skipped.
- [ ] **Step 7: Commit** `feat: database schema, connection helper and migration runner`.

---

### Task 7: Repository for profile, achievements and role families **[needs Supabase]**

**Files:**
- Create: `backend/repo.py`, `backend/tests/test_repo_profile.py`

**Interfaces:**
- Produces:
  - `get_or_create_profile(conn, user_id, full_name: str) -> dict` (adds `first_name`, the first word of `full_name`)
  - `update_profile(conn, user_id, *, full_name, university, course, graduation_date, visa_type, visa_end_date, locations) -> dict` (stores `graduation_date` as the first of its month; creates the row if absent)
  - `set_pitch(conn, user_id, pitch: str) -> None`
  - `details_complete(profile: dict) -> bool` (pure)
  - `list_achievements(conn, user_id) -> list[dict]` (newest first)
  - `add_achievements(conn, user_id, items: list[dict], source: str) -> list[dict]`
  - `get_achievement(conn, user_id, achievement_id) -> dict | None`
  - `delete_achievement(conn, user_id, achievement_id) -> bool`
  - `list_families(conn, user_id) -> list[dict]` (direct, near, stretch; then overlap descending)
  - `sync_families(conn, user_id, families: list[dict]) -> list[dict]`
  - `set_family_targeted(conn, user_id, family_id, targeted: bool) -> dict | None`

- [ ] **Step 1: Write failing tests** (marked `db`):

```python
def test_profile_created_once(conn, user_a):           # two calls → same row; full_name from the first call
def test_first_name_derived(conn, user_a):             # full_name "Test Person" → first_name "Test"
def test_update_profile_normalises_graduation(conn, user_a):  # date(2026, 9, 17) → date(2026, 9, 1)
def test_details_complete():                           # False when any of university, course, graduation_date,
                                                       # visa_type, visa_end_date is None or locations == []; True otherwise
def test_achievements_round_trip_newest_first(conn, user_a):
def test_delete_achievement_returns_false_for_other_user(conn, user_a, user_b):   # row still exists for user_a
def test_get_achievement_none_for_other_user(conn, user_a, user_b):
def test_list_achievements_empty_for_other_user(conn, user_a, user_b):
def test_sync_inserts_new_families(conn, user_a):
def test_sync_updates_in_place_keeping_id_and_targeted(conn, user_a):
    # sync "Data Analyst"; target it; sync "data analyst" with overlap 60 → same id, targeted True, overlap 60
def test_sync_removes_untargeted_unreferenced(conn, user_a):    # second sync omits an untargeted family → gone
def test_sync_keeps_targeted_even_if_omitted(conn, user_a):
def test_sync_keeps_referenced_even_if_omitted(conn, user_a):   # an application row (inserted with plain SQL) points at it → kept
def test_sync_does_not_touch_other_users_families(conn, user_a, user_b):
def test_set_family_targeted_none_for_other_user(conn, user_a, user_b):
```

- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement.** A private `_row(d)` converts UUID values to `str`. `sync_families` matches on `lower(trim(name))`; "referenced" means any `applications`, `cv_versions` or `saved_jobs` row with that `role_family_id`. Wrap jsonb parameters with `psycopg.types.json.Jsonb`.
- [ ] **Step 4: Run.** Expected: 15 passed.
- [ ] **Step 5: Commit** `feat: repository for profile, achievements and role families`.

---

### Task 8: Repository for jobs, CVs, stories, applications and journal **[needs Supabase]**

**Files:**
- Modify: `backend/repo.py`
- Create: `backend/tests/test_repo_records.py`

**Interfaces:**
- Produces:
  - `list_jobs(conn, user_id)`, `get_job(conn, user_id, job_id) -> dict | None`, `delete_job(conn, user_id, job_id) -> bool`
  - `add_job(conn, user_id, *, title, company, location, url, description, summary, keywords, role_family_id) -> dict`
  - `list_cv_versions(conn, user_id)`, `add_cv_version(conn, user_id, *, saved_job_id, role_family_id, base_name: str, content: dict) -> dict` (name is `f"{base_name} v{n}"`, `n` = 1 + the user's existing versions for that `saved_job_id`)
  - `list_stories(conn, user_id)`, `add_story(conn, user_id, achievement_id, story: dict) -> dict`
  - `list_applications(conn, user_id)` (by `applied_on` then `created_at`, newest first)
  - `add_application(conn, user_id, fields: dict) -> dict`, `update_application(conn, user_id, app_id, fields: dict) -> dict | None`, `delete_application(conn, user_id, app_id) -> bool`
  - `list_journal(conn, user_id)`, `add_journal_entry(conn, user_id, *, type, title, with_whom, summary, points, actions, scores=None) -> dict`
  - `load_state(conn, user_id) -> dict` with keys `achievements`, `role_families`, `saved_jobs`, `cv_versions`, `stories`, `applications`, `journal`
- `fields` for applications may contain only: `company, role, role_family_id, cv_version_id, saved_job_id, source, stage, applied_on, posted_on, job_url, contact, notes, sponsor_licence, follow_up_on`. Any other key raises `ValueError`.
- **Reference ownership:** when inserting or updating, a `role_family_id`, `cv_version_id`, `saved_job_id` or `achievement_id` that is not the caller's own row is stored as null (select it with `where id = %s and user_id = %s`).

- [ ] **Step 1: Write failing tests** (marked `db`):

```python
def test_job_round_trip_and_delete(conn, user_a):
def test_get_job_none_for_other_user(conn, user_a, user_b):
def test_delete_job_false_for_other_user(conn, user_a, user_b):
def test_cv_version_names_increment_per_job(conn, user_a):     # base "Role A, Company A" twice → "... v1", "... v2"
def test_cv_version_content_round_trips_as_dict(conn, user_a):
def test_story_keeps_when_achievement_deleted(conn, user_a):   # achievement_id becomes None
def test_application_defaults(conn, user_a):                   # stage "applied", applied_on == London today
def test_application_update_only_named_fields(conn, user_a):   # update {"stage": "interview"} leaves notes unchanged; updated_at moves
def test_application_unknown_field_raises(conn, user_a):       # {"user_id": ...} → ValueError
def test_update_application_none_for_other_user(conn, user_a, user_b):   # row unchanged
def test_delete_application_false_for_other_user(conn, user_a, user_b):
def test_foreign_reference_stored_as_null(conn, user_a, user_b):
    # user_b creates an application naming user_a's role_family_id, cv_version_id and saved_job_id → all three None
def test_deleted_reference_stored_as_null(conn, user_a):       # a random uuid as role_family_id → None, no error
def test_journal_round_trip_newest_first(conn, user_a):
def test_load_state_only_own_rows(conn, user_a, user_b):       # user_a has one row in every table; load_state(user_b) → every list empty
```

- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the whole repo suite: `pytest tests/test_repo_profile.py tests/test_repo_records.py -v`. Expected: 30 passed.
- [ ] **Step 5: Commit** `feat: repository for jobs, CVs, stories, applications and journal`.

---

### Task 9: Daily limits (`limits.py`) **[needs Supabase]**

**Files:**
- Create: `backend/limits.py`, `backend/tests/test_limits.py`
- Modify: `backend/repo.py`

**Interfaces:**
- Produces:
  - `repo.count_usage_today(conn, user_id, kind: str) -> int`
  - `repo.record_usage(conn, user_id, kind: str, action: str) -> None`
  - `repo.seconds_since_last_usage(conn, user_id, kind: str, action: str) -> float | None`
  - `class limits.LimitReached(Exception)` with attribute `kind`
  - `limits.check_and_record(conn, user_id, kind: str, action: str, *, retry_window_s: int = 0) -> None`
  - `limits.allowed(conn, user_id, kind: str) -> bool` (no recording)
  - `limits.usage(conn, user_id) -> dict` → `{"ai": {"used": int, "limit": int}, "voice": {...}}`
- "Today" in SQL: `created_at >= (date_trunc('day', now() at time zone 'Europe/London') at time zone 'Europe/London')`.

- [ ] **Step 1: Write failing tests** (marked `db`; set limits with `monkeypatch.setenv`):

```python
def test_under_limit_records(conn, user_a):                 # DAILY_AI_LIMIT=2; one call → usage ai.used == 1
def test_at_limit_raises_and_does_not_record(conn, user_a): # two calls pass, third raises LimitReached(kind="ai"); used stays 2
def test_kinds_are_separate(conn, user_a):                  # ai at its limit; a voice call still passes
def test_users_are_separate(conn, user_a, user_b):          # user_a at limit; user_b passes
def test_yesterdays_usage_does_not_count(conn, user_a):
    # insert an event with created_at = London midnight - 1 minute and one at London midnight → count_usage_today == 1
def test_retry_window_is_free(conn, user_a):
    # record voice/"onboarding"; check_and_record(..., "voice", "onboarding", retry_window_s=120) → used still 1
def test_retry_window_only_for_same_action(conn, user_a):   # previous event was "interviewer" → the onboarding call is counted
def test_allowed_does_not_record(conn, user_a):
```

- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: 8 passed.
- [ ] **Step 5: Commit** `feat: per-user daily limits`.

---

### Task 10: API for state, profile, account and tracker (`main.py`) **[needs Supabase]**

**Files:**
- Rewrite: `backend/main.py`
- Create: `backend/content.py`, `backend/data/content.json`, `backend/tests/test_routes_data.py`
- Modify: `backend/tests/conftest.py`
- Delete: `backend/store.py`, `backend/data/seed.json`

**Interfaces:**
- Consumes: `auth.current_user`, `auth.User`, `db.transaction`, every `repo` function, `limits.usage`, `analytics.compute`, `analytics.next_steps`, `analytics.STAGES`, `analytics.SOURCES`.
- Produces:
  - `content.load() -> dict` with keys `uk_market`, `where_to_look`, `tone_phrases`, `tone_norms`, `cv_rules`
  - Fixture `client(conn, user_a)`: a `TestClient` where `current_user` is overridden to `User(user_a, "a@example.test", "Test Person")` and `db.transaction` is patched to yield `conn` inside `conn.transaction()` (a savepoint) without committing or closing. A helper `as_user(client, user_id)` switches the override.
  - Routes:

    | Route | Body | Answer |
    |---|---|---|
    | `GET /api/config` | – | `{"supabase_url", "supabase_publishable_key", "contact_email"}` |
    | `GET /api/state` | – | spec 7.1, plus `"options": {"sources": [...], "stages": [...]}`; `profile` includes `first_name` and `email` |
    | `PUT /api/profile` | `full_name` 1–120, `university` 1–160, `course` 1–160, `graduation_date` date, `visa_type` `student`/`graduate`, `visa_end_date` date, `locations` 1–5 strings of 1–60 | the profile |
    | `DELETE /api/account` | – | 204 |
    | `DELETE /api/achievements/{id}` | – | 204 or 404 |
    | `POST /api/families/{id}/target` | `{"targeted": bool}` | the family or 404 |
    | `DELETE /api/jobs/{id}` | – | 204 or 404 |
    | `POST /api/applications` | `company` 1–160, `role` 1–160, `source` in SOURCES, optional `stage` in STAGES, `applied_on`, `posted_on`, `role_family_id`, `cv_version_id`, `saved_job_id`, `job_url` ≤ 500, `contact` ≤ 200, `notes` ≤ 4000, `follow_up_on` | the application, 201 |
    | `PATCH /api/applications/{id}` | any subset of the above | the application or 404 |
    | `DELETE /api/applications/{id}` | – | 204 or 404 |

  - All ids in paths and bodies are typed `uuid.UUID`. 404 detail: "That item no longer exists".
  - Exception handlers: `limits.LimitReached` → 429 "You've reached today's limit. It resets at midnight."; `ai.AIError` → 502 "The AI did not respond properly. Try again."; `llm.LLMNotConfigured` → 503 "AI is not set up on the server."; `psycopg.OperationalError` → 503 "We can't reach the server. Try again in a minute."

- [ ] **Step 1: Write `data/content.json`** with exactly this copy:

```json
{
  "uk_market": [
    {"title": "Graduate schemes recruit a year ahead", "body": "Applications usually open between September and December for a start the following autumn. Direct-entry roles are advertised all year and often close within two to three weeks."},
    {"title": "Know the entry routes", "body": "A spring week is a short insight programme, mostly for first and second-year undergraduates. Summer internships and placements often lead to graduate offers. Your university careers service can tell you which ones you are eligible for."},
    {"title": "Check the sponsor register before you apply", "body": "Only employers on the gov.uk register of licensed sponsors can sponsor a Skilled Worker visa. Some employers will hire you on a Graduate visa but cannot sponsor you afterwards."},
    {"title": "UK CVs are two pages", "body": "No photo, date of birth or marital status. Start each bullet with an action and include a number. A cover letter answers why this company before why you."},
    {"title": "Referrals and conversations matter", "body": "Many UK roles are filled through referrals or are never advertised. A 15-minute chat with someone inside a company often does more than several online applications."}
  ],
  "where_to_look": [
    {"name": "Graduate and early-career boards", "tip": "Prospects, Bright Network and Handshake list graduate schemes, internships and entry-level roles with fixed deadlines."},
    {"name": "Your university careers service", "tip": "Employers who post here already want graduates from your university, and advisers explain how UK recruitment works."},
    {"name": "LinkedIn and Indeed", "tip": "Set daily alerts for your target titles and apply within 48 hours of posting."},
    {"name": "Company career pages", "tip": "Roles often appear here first. Check the employers you want every week."},
    {"name": "Register of licensed sponsors (gov.uk)", "tip": "Check an employer before you spend time on a tailored application."}
  ],
  "tone_phrases": [
    {"phrase": "Not bad at all.", "meaning": "Genuinely good. British praise is understated."},
    {"phrase": "I'll bear that in mind.", "meaning": "Probably will not act on it."},
    {"phrase": "With respect...", "meaning": "I disagree with you."},
    {"phrase": "We'd love to keep in touch.", "meaning": "Usually a polite no. Thank them and do not wait on it."},
    {"phrase": "That's quite interesting.", "meaning": "Often polite and lukewarm, not real enthusiasm."},
    {"phrase": "We'll be in touch.", "meaning": "Neutral. If no date was given, follow up after a week."},
    {"phrase": "Do you have any questions for us?", "meaning": "You are expected to ask two or three thoughtful ones. Saying no reads as low interest."},
    {"phrase": "Tell me about yourself.", "meaning": "A 90-second pitch: what you do now, what you did before, why this role."}
  ],
  "tone_norms": [
    "Say 'I led' or 'I built', not 'I single-handedly'. Confident but understated works best.",
    "Use 'we' for team results and 'I' for your part. UK interviewers listen for your exact contribution.",
    "A little small talk at the start is normal. Ask how their week is going.",
    "Feedback is often softened and indirect. If you are unsure where you stand, ask one specific follow-up question.",
    "Address people by first name unless told otherwise. 'Sir' and 'Madam' sound overly formal."
  ],
  "cv_rules": [
    "Two pages. No photo, date of birth or marital status.",
    "Each bullet starts with an action and carries a number.",
    "Overseas employers get one line of context.",
    "The cover letter answers why them before why you."
  ]
}
```

- [ ] **Step 2: Write failing tests** (marked `db`):

```python
def test_every_route_but_config_needs_a_token():
    # plain TestClient, no overrides: for each /api route and method except GET /api/config,
    # with a valid uuid in path params → 401
def test_config_is_public_and_has_no_secret(monkeypatch):   # body has the publishable key; SUPABASE_SECRET_KEY value appears nowhere
def test_state_for_new_user(client):
    # 200; details_complete False; every list empty; next_steps has 6 items all not done;
    # usage == {"ai": {"used": 0, "limit": 40}, "voice": {"used": 0, "limit": 3}}; profile.full_name == "Test Person"
def test_put_profile_completes_details(client):             # then GET state → details_complete True
def test_put_profile_validation(client):                    # visa_type "tourist" → 422; locations [] → 422; 6 locations → 422
def test_application_crud(client):                          # POST 201, PATCH stage "interview", DELETE 204, second DELETE 404
def test_application_bad_source_422(client):
def test_posted_after_applied_422(client):                  # posted_on 2026-10-10, applied_on 2026-10-01 → 422, not 500
def test_malformed_id_422(client):                          # PATCH /api/applications/not-a-uuid → 422
def test_unknown_id_404(client):                            # PATCH with a random uuid → 404 "That item no longer exists"
def test_user_b_cannot_see_or_change_user_a(client, user_b):
    # user_a posts an application; as user_b: GET state has none, PATCH → 404, DELETE → 404; as user_a it is unchanged
def test_target_family(client):                             # seed a family through repo; POST target → targeted True in state
def test_delete_achievement_and_job(client):
def test_account_delete_calls_supabase(client, monkeypatch, user_a):
    # patch main._delete_auth_user to record its argument and return → 204 and called with user_a
def test_account_delete_failure_is_502(client, monkeypatch):  # patched to raise httpx.HTTPError → 502 "Could not delete the account. Try again."
def test_content_in_state(client):                          # state.content.uk_market has 5 items; tone_phrases has 8
```

- [ ] **Step 3: Run.** Expected: failures.
- [ ] **Step 4: Implement.** `GET /api/state` runs in one transaction: `get_or_create_profile`, `load_state`, `limits.usage`, then `analytics.compute` and `analytics.next_steps` outside it. `main._delete_auth_user(user_id)` sends `DELETE {supabase_url}/auth/v1/admin/users/{user_id}` with headers `apikey` and `Authorization: Bearer`, both the secret key, timeout 15 s, and raises on a non-2xx answer. The posted-after-applied check is a Pydantic model validator for POST; for PATCH, catch `psycopg.errors.CheckViolation` and answer 422 "The posting date cannot be after the application date."
- [ ] **Step 5: Delete** `store.py` and `data/seed.json`. `grep -ri "aditi\|seed.json\|DEMO_\|passcode\|upstash" backend --include=*.py` must return nothing.
- [ ] **Step 6: Run** `pytest -v`. Expected: all tests so far pass, 0 skipped.
- [ ] **Step 7: Commit** `feat: authenticated API for state, profile, account and tracker`.

---

### Task 11: AI and voice routes **[needs Supabase]**

**Files:**
- Modify: `backend/main.py`, `backend/voice.py`, `backend/setup_agents.py`
- Create: `backend/tests/test_routes_ai.py`, `backend/tests/test_voice.py`

**Interfaces:**
- Consumes: Task 4's `ai.*`, Task 9's `limits.*`, Task 8's `repo.*`.
- Produces:

  | Route | Body | Answer |
  |---|---|---|
  | `POST /api/ai/achievements` | `transcript` 20–30,000 chars, `source` `voice`/`paste` | `{"items": [saved rows], "pitch": str}` |
  | `POST /api/ai/families` | – | `{"families": [rows]}`; 400 "Build your profile first." with no achievements |
  | `POST /api/jobs` | `title` 1–160, `company` 1–160, `description` 30–20,000, optional `url` ≤ 500, `location` ≤ 120 | the job, 201 |
  | `POST /api/ai/tailor` | `job_id` | the CV version row; 400 "Build your profile first." with no achievements |
  | `POST /api/ai/star` | `achievement_id` | the story row |
  | `POST /api/ai/interview-feedback` | `transcript` 20–30,000, optional `job_id`, `interview_type` 1–80 | the feedback dict |
  | `POST /api/ai/tone` | `text` 1–1000, `mode` `decode`/`rewrite` | the tone dict |
  | `POST /api/ai/diagnosis` | – | the review dict; 400 "Log some applications first." with none |
  | `GET /api/voice/token` | query `agent` `onboarding`/`interviewer`, `transport` `webrtc`/`websocket` | `{"token"}` or `{"signed_url"}` |
  | `GET /api/voice/transcript/{conversation_id}` | – | `{"turns": [...]}` or 404 |

  - `voice.fetch_transcript(conversation_id: str, user_id: str) -> list[dict]` raises `PermissionError` unless `user_id` equals the conversation's top-level `user_id`, or `conversation_initiation_client_data.user_id`, or `conversation_initiation_client_data.dynamic_variables.user_id`.
  - 422 messages: short transcript "Say or paste a bit more first."; short job description "Paste the full job description."
  - Zero usable achievements: 422 "We could not find any achievements in that. Add more detail and try again."

- [ ] **Step 1: Write failing tests** (marked `db`; every `ai.*` function is monkeypatched):

```python
def test_achievements_saved_and_journalled(client):
    # ai returns 2 items + pitch → 200; state has 2 achievements with source "paste", profile.pitch set,
    # one journal entry of type "coach"; usage ai.used == 1
def test_achievements_none_found_422(client):
    # ai returns {"items": [], "pitch": ""} → 422 "We could not find any achievements in that. Add more detail and try again."; no rows, no journal entry
def test_achievements_short_transcript_422(client):         # 19 chars → 422 and ai not called
def test_achievements_oversize_422(client):                 # 30,001 chars → 422 and ai not called
def test_ai_error_saves_nothing_and_is_502(client):         # ai raises AIError → 502 "The AI did not respond properly. Try again."; no rows
def test_ai_limit_429(client, monkeypatch):                 # DAILY_AI_LIMIT=1 → second call 429 with the exact message; ai called once
def test_families_need_achievements(client):                # 400 "Build your profile first."
def test_families_synced(client):                           # ai returns 3 families → state.role_families has 3
def test_add_job_summarised_and_matched(client):            # ai returns family "Data Analyst" which exists → role_family_id set, summary saved
def test_add_job_survives_ai_failure(client):               # ai raises AIError → 201; summary == first 300 chars of description; role_family_id None
def test_add_job_skips_ai_when_limit_reached(client, monkeypatch):   # DAILY_AI_LIMIT=0 → 201, ai not called
def test_add_job_short_description_422(client):
def test_tailor_creates_named_version(client):              # job "Role A" at "Company A" → name "Role A, Company A v1"; second call "... v2"
def test_tailor_other_users_job_404(client, user_b):
def test_star_other_users_achievement_404(client, user_b):
def test_interview_feedback_without_job(client):            # no job_id → 200; journal title "HR screening call: general practice"
def test_interview_feedback_journal_has_scores(client):
def test_diagnosis_needs_applications(client):              # 400 "Log some applications first."
def test_voice_token_counts_and_limits(client, monkeypatch):
    # voice.conversation_token patched → 200 {"token": "t"}; DAILY_VOICE_LIMIT=1 → second webrtc call 429
def test_voice_websocket_retry_is_free(client, monkeypatch): # webrtc then websocket within the window → both 200, voice.used == 1
def test_voice_unconfigured_503(client, monkeypatch):       # no ELEVENLABS_API_KEY → 503 "Voice is unavailable right now."
def test_voice_bad_agent_422(client):
def test_transcript_owner_only(client, monkeypatch):        # voice.fetch_transcript raises PermissionError → 404
def test_no_connection_held_during_ai(client, monkeypatch):
    # the patched ai function asserts a module flag set by the patched db.transaction is "closed" while it runs
```

- [ ] **Step 2: Run.** Expected: failures.
- [ ] **Step 3: Implement the routes.** Each AI route follows one pattern: transaction 1 reads what it needs and calls `limits.check_and_record(conn, user.id, "ai", <action>)`; the model call happens with no transaction open; transaction 2 writes. `POST /api/jobs` uses `limits.allowed` then `record_usage` and never fails because of the AI. The voice token route uses `retry_window_s=120` when `transport == "websocket"`. Journal titles: coach entries "Background call with your careers coach" (voice) or "Profile built from your pasted background" (paste); interview entries `f"{interview_type}: {title}, {company}"` or `f"{interview_type}: general practice"`.
- [ ] **Step 4: Update `voice.py`** as in Interfaces, test-first in `tests/test_voice.py` with `httpx.get` patched (no database needed):

```python
def test_transcript_owner_top_level():        # conversation user_id == caller → turns returned, empty messages dropped
def test_transcript_owner_dynamic_variable(): # only dynamic_variables.user_id matches → turns returned
def test_transcript_mismatch_raises():        # no location matches → PermissionError
```
- [ ] **Step 5: Update `setup_agents.py`.** Add `user_id`, `course`, `university` and `visa_type` to the coach's placeholders (defaults `""`, `"your course"`, `"your university"`, `"Student"`) and `user_id` to the interviewer's. Coach prompt:

```
You are a warm, efficient UK careers coach onboarding an international student or recent graduate into a career navigator app. Your goal, in about three minutes, is to collect raw material for their profile: skills, outcomes and scale.

You already know they study or studied {{course}} at {{university}} and hold a {{visa_type}} visa. Do not ask about these.

Cover these, one short question at a time:
1. Previous work in any country: employer, role, what they did, and for one or two pieces of work the result with a number and the scale (users, records, money, time saved).
2. Projects, dissertation, internships, volunteering or part-time work, especially anything done in the UK.
3. The tools and skills they used most.
4. The roles they want next.

Rules:
- Ask one question at a time and keep your turns under 25 words.
- If they give an achievement without a number, ask once for a rough number.
- If they mention an overseas employer, briefly ask what the company does so a UK employer would understand it.
- Do not give long advice. You are collecting, not coaching.
- When the list is covered, or after about 8 exchanges, say: "That's plenty to work with. Press End and I'll build your profile." Then stop asking questions.
- Use British English.
```

  First message: `Hi {{candidate_name}}, I'm your UK careers coach. In a few minutes I'll help you turn your background into evidence UK employers understand. To start, what work or projects have you done so far?`

- [ ] **Step 6: Run** `pytest -v`. Expected: everything passes, 0 skipped.
- [ ] **Step 7: Commit** `feat: AI and voice routes with limits and ownership checks`.

---

### Task 12: Signed-out experience and session handling **[needs Node, Supabase]**

**Files:**
- Create: `frontend/src/supabase.js`, `frontend/src/pages/Auth.jsx`, `frontend/src/pages/Privacy.jsx`
- Modify: `frontend/package.json`, `frontend/src/api.js`, `frontend/src/App.jsx`, `frontend/src/pages/Landing.jsx`, `frontend/src/ui.jsx`, `frontend/src/index.css`

**Interfaces:**
- Consumes: `GET /api/config`, `GET /api/state`.
- Produces:
  - `supabase.js`: `getSupabase(): Promise<SupabaseClient>` (one cached client, options `{auth: {flowType: 'pkce', detectSessionInUrl: true, persistSession: true, autoRefreshToken: true}}`), `getConfig(): Promise<{supabase_url, supabase_publishable_key, contact_email}>`, `accessToken(): Promise<string | null>`
  - `api.js`: `api(path, {method, body})`, `post`, `patch`, plus `put`, `del`, and `onSignedOut(fn)`. Errors carry `.status`. On 401 it calls `supabase.auth.refreshSession()` once and retries; a second 401 calls the `onSignedOut` handler.
  - `ui.jsx`: `today()` returning a `Date` at local midnight (replaces `TODAY`); `ErrorRetry({error, onRetry})`; `Empty({title, body, action, onAction})`. `AiBadge`, `FallbackNote`, `coverage` and the alias table in `resolvePage` are removed.
  - `App.jsx` props to pages: `{s, refresh, go, tab, focus, notify, session}`.
  - Routes by hash: signed out `#landing` (default), `#auth/signin`, `#auth/signup`, `#auth/forgot`, `#privacy`; any other hash shows landing. Signed in: `#privacy`, `#account`, `#onboarding` and the app pages; details incomplete forces onboarding step 1. `?reset=1` in the query string with a session shows the new-password form.

- [ ] **Step 1: Install.** `npm ci` then `npm install @supabase/supabase-js` in `frontend/`. Read the installed `@elevenlabs/client` type definitions and confirm `startSession` accepts `userId`; note the result for Task 15.
- [ ] **Step 2: Build `supabase.js` and `api.js`** as in Interfaces.
- [ ] **Step 3: Build `Auth.jsx`.**

  | Mode | Fields and action | Result |
  |---|---|---|
  | signup | Full name, Email, Password (min 8), tick "I agree to the privacy notice" (link to `#privacy`). `signUp({email, password, options: {data: {full_name}}})` | Session → app. No session → "Check your email to confirm your account, then sign in." |
  | signin | Email, Password. `signInWithPassword` | "Invalid login credentials" is shown as "Email or password is incorrect." |
  | forgot | Email. `resetPasswordForEmail(email, {redirectTo: `${location.origin}/?reset=1`})` | Always "If an account exists for that email, a reset link is on its way." |
  | newpassword | New password (min 8). `updateUser({password})` | Remove `reset` from the URL, go to the dashboard |

  Submit buttons are disabled while a request runs. Client-side validation messages appear beside the field.
- [ ] **Step 4: Build `Privacy.jsx`.** Plain sections: what we collect (email, name, university, course, graduation date, visa type and end date, preferred locations, what you tell the coach or paste, job descriptions you add, your applications, AI-written content, daily usage counts); why (to build your profile, CVs and practice, and to show what is and is not working); who processes it (Supabase for login and database, in London; Amazon Web Services Bedrock for AI text, in the United States; ElevenLabs for voice calls and transcription); how long (until you delete your account); your choices (delete your account and all data from the Account page); contact (shown only when `contact_email` is set). No legal claims beyond these facts.
- [ ] **Step 5: Rewrite `Landing.jsx`.** Headline "A clear plan for your UK job search." Lede "For international students and recent graduates in the UK. Turn your experience into UK-standard applications, practise interviews out loud, and see why applications are or are not working." Four feature cards only: UK-standard CV and cover letter; Interview practice; Application tracker; Career pathways. The preview panel shows the six getting-started steps from Task 5 with the first two ticked, labelled "Example". Buttons: "Get started" → `#auth/signup`, "Sign in" → `#auth/signin`; when signed in, one button "Open dashboard". Footer link "Privacy". Remove the fictional-data footer line and every fictional name.
- [ ] **Step 6: Rewrite the gate in `App.jsx`** as in Interfaces. Subscribe to `onAuthStateChange`; on sign-out clear state and go to landing. Wrap `<Page>` in an error boundary that renders `ErrorRetry`, so a page that throws never blanks the app. Pages still reading the old state shape are fixed in Tasks 13 to 15.
- [ ] **Step 7: CSS.** Style `input[type=email]`, `input[type=date]`, `input[type=month]` like the existing text inputs; add `.auth-card` (max-width 420px, centred) and `.empty` (centred, muted, 32px padding).
- [ ] **Step 8: Verify.** `npm run lint` and `npm run build` succeed. In the browser preview, signed out:
  - Landing shows four cards and no fictional names; "Get started" opens sign-up.
  - Sign-up with a 5-character password shows the validation message and sends no request (check the network log).
  - Sign-up without the privacy tick is blocked.
  - `#applications` while signed out shows landing.
  - `#privacy` renders.
  - **Project owner:** sign up one account. Expected: the app moves past the auth screens (onboarding arrives in Task 13; an empty shell is acceptable here).
  - Session expiry: in the console, overwrite the stored access token with `x`, then trigger `/api/state`. Expected: one refresh and a successful retry. Then delete the stored session from `localStorage` entirely and trigger a call: the sign-in screen appears, with no blank page and no request loop (the network log shows at most two `/api/state` requests).
- [ ] **Step 9: Commit** `feat: sign-up, sign-in, password reset and session gate`.

---

### Task 13: Onboarding for a real person **[needs Node, Supabase]**

**Files:**
- Create: `frontend/src/components/DetailsForm.jsx`
- Modify: `frontend/src/pages/Onboarding.jsx`, `frontend/src/VoiceAgent.jsx`, `frontend/src/index.css`

**Interfaces:**
- Consumes: `PUT /api/profile`, `POST /api/ai/achievements`, `POST /api/ai/families`, `POST /api/families/{id}/target`, `GET /api/voice/token`.
- Produces:
  - `DetailsForm({profile, onSaved, submitLabel})`: the seven fields of spec 4.1, month input for graduation, a tag input for locations (Enter or comma adds, × removes, maximum 5). Calls `PUT /api/profile`, then `onSaved(profile)`.
  - `VoiceAgent` gains a required `userId` prop, passed to `startSession` as `userId` and as `dynamicVariables.user_id`. Its idle sub-line becomes "Uses your microphone. Your voice is processed by ElevenLabs to run and transcribe this call."

- [ ] **Step 1: Build `DetailsForm`.** Required-field messages beside each field. Visa type is two radio buttons, "Student visa" and "Graduate visa".
- [ ] **Step 2: Rebuild `Onboarding.jsx`** with steps "Your details", "Your background", "Your profile", "Target roles":
  1. `DetailsForm`, button "Continue".
  2. Voice or paste. Coach variables: `candidate_name` (first name), `course`, `university`, `visa_type` ("Student" or "Graduate"). Paste needs 20 characters. Link "I'll do this later" goes to the dashboard. The transcript or pasted text is kept in component state; on failure show `ErrorRetry` whose Retry re-sends the same text. A 429 shows the limit message without Retry.
  3. The saved achievements and pitch. "Continue" calls `POST /api/ai/families` (label "Finding roles that fit") then moves on. Failure shows `ErrorRetry`.
  4. One card per family: fit label, name, "{overlap}% overlap (AI estimate)", why, UK titles, then each need with a tick and "Shown by: {shown_by}" or "Gap". A "Targeting" tick calls the target route. Helper text "Pick 3 to 5." "Go to my dashboard" is enabled once one family is targeted.
  Remove the talking points, the sample button and the "Skip to dashboard" link. Signed-in users with complete details can revisit steps 2 to 4 from `#onboarding`.
- [ ] **Step 3: Verify.** Lint and build succeed. In the browser (signed in as the account from Task 12):
  - Reloading any hash while details are incomplete returns to step 1.
  - Submitting step 1 empty shows seven field messages and sends no request.
  - A sixth location cannot be added.
  - After saving, a reload lands on the dashboard route, and `#onboarding` reopens at step 2.
  - Paste path: Claude pastes a short synthetic background of its own writing; step 3 lists the returned achievements; step 4 lists families with needs; targeting one enables the dashboard button and survives a reload.
  - **Project owner:** run the voice path once and confirm the coach uses your first name and does not ask for course, university or visa.
- [ ] **Step 4: Commit** `feat: onboarding with details form, voice or paste, and AI role families`.

---

### Task 14: App shell, This week, Profile and Account **[needs Node, Supabase]**

**Files:**
- Create: `frontend/src/pages/Account.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/ui.jsx`, `frontend/src/pages/Home.jsx`, `frontend/src/pages/Profile.jsx`, `frontend/src/pages/Journal.jsx`, `frontend/src/index.css`
- Delete: `frontend/src/pages/Networking.jsx`, `frontend/src/pages/Peers.jsx`

**Interfaces:**
- Consumes: state keys `profile`, `achievements`, `stats`, `next_steps`, `journal`, `usage`; `DELETE /api/achievements/{id}`, `POST /api/ai/star`, `POST /api/ai/achievements`, `DELETE /api/account`.

- [ ] **Step 1: Shell.** `NAV` is one group: This week, Profile, Career pathways, Resume, Interview coach, Applications, Journal. Sidebar foot: avatar and name (opens `#account`) and a "Sign out" button. Remove the status pips and the reset button.
- [ ] **Step 2: `Home.jsx`.**
  - Title "This week, {first_name}".
  - "Your next best step": the first tracker finding if any, otherwise the first step in `next_steps` not done (text, why, a button to its page). Hidden when there is neither.
  - "Getting started" card: `{done} of 6` and the six steps with ticks and an "Open" button; hidden once all six are done.
  - Visa card from `visa_end_date` and `today()`: more than 0 days "{n} days until your {Student|Graduate} visa ends" with the date underneath; 0 "Your visa ends today"; under 0 "Your visa end date has passed. Update it in your profile if it has changed."
  - "Your search so far": applied, replies, interviews, offers.
  - Remove the weekly plan checkboxes, streak, milestones, "Coming up" and the buddy group.
- [ ] **Step 3: `Profile.jsx`.** Details card with "Edit details" opening `DetailsForm` in place. Pitch. "Add to your profile" by voice or paste (same retry behaviour as onboarding). Achievement cards with "Make a STAR story" and "Delete" (asks "Delete this achievement?" first). Empty state: "No achievements yet. Talk to the coach or paste your CV to build your profile."
- [ ] **Step 4: `Account.jsx`.** Name and email; "AI actions today: {used} of {limit}"; "Voice sessions today: {used} of {limit}"; "Sign out"; link to the privacy notice; "Delete my account" in a bordered danger section that requires typing `DELETE`, calls `DELETE /api/account`, signs out locally and returns to landing.
- [ ] **Step 5: `Journal.jsx`.** Use `created_at` for the date; filters All, Mock interviews, Coach calls; drop the "New" chip and the peer type. Empty state "No sessions yet." with a button to Interview coach.
- [ ] **Step 6: Verify.** Lint and build succeed; `grep -ri "networking\|peers\|buddy\|reset demo\|demo fallback" frontend/src` returns nothing. In the browser:
  - The menu has seven items and none leads to an error.
  - Home shows "Getting started" with the right ticks for the account's data.
  - Temporarily set the visa end date to yesterday via "Edit details": Home shows the "has passed" message, not a negative number. Restore it.
  - Deleting an achievement asks first and removes the card.
  - Account shows today's usage figures matching `usage` in `/api/state`.
- [ ] **Step 7: Commit** `feat: app shell, home, profile and account on real data`.

---

### Task 15: Career pathways, Resume, Interview coach and Applications **[needs Node, Supabase]**

**Files:**
- Create: `frontend/src/components/Jobs.jsx`
- Modify: `frontend/src/pages/Pathways.jsx`, `frontend/src/pages/Resume.jsx`, `frontend/src/pages/Interview.jsx`, `frontend/src/pages/Applications.jsx`, `frontend/src/index.css`

**Interfaces:**
- Consumes: state keys `role_families`, `saved_jobs`, `cv_versions`, `stories`, `applications`, `stats`, `content`, `options`; the routes of Tasks 10 and 11.
- Produces: `Jobs.jsx` exports `JobPicker({jobs, value, onChange, allowNone})` (with `allowNone`, a first option "General practice" whose value is `''`) and `AddJob({onAdded, onCancel})` (Title, Company, Job description, optional Link and Location; "Save job"; the description needs 30 characters).

- [ ] **Step 1: `Pathways.jsx`.** Family cards as in onboarding step 4, with the "Targeting" tick. Header button "Re-check fit from my profile". Empty states: no achievements → `Empty` "Build your profile first" → Profile; achievements but no families → `Empty` with "Find roles that fit my profile". "Your dates" card: graduation month and visa end date. "How the UK market works" from `content.uk_market`; "Where to look" from `content.where_to_look`. Remove matched jobs, the offer check, the AI comparison table, salary and sponsor rows.
- [ ] **Step 2: `Resume.jsx`.** No saved jobs → `Empty` "Add a job you want to apply for" opening `AddJob`. Otherwise: `JobPicker`, "Add a job", "Remove" (asks first), and "Tailor CV and cover letter". The sheet shows the selected CV version: after tailoring, the new one; clicking a chip under "Your CV versions" opens that one. Beside the letter: "Add to Applications with this CV" with a Source select (from `options.sources`, default "Company site") and an optional "Date posted"; it posts `company`, `role`, `saved_job_id`, `cv_version_id`, `role_family_id`, `source`, `posted_on`. "UK CV rules" comes from `content.cv_rules`. Failures use `ErrorRetry`.
- [ ] **Step 3: `Interview.jsx`.** `JobPicker` with `allowNone` plus "Add a job". For "General practice" the interviewer variables are `role` = first targeted family name or "graduate role", `company` = "a UK employer", `job_summary` = "General practice, no specific job." `cv_summary` joins the first five achievements' `uk_version`, cut to 900 characters. Pass `userId`. The transcript stays in state so `ErrorRetry` can re-score it. Remove the sample interview and the "No microphone?" card. STAR stories and the tone decoder read `stories`, `content.tone_phrases` and `content.tone_norms`. Stories empty state: "No stories yet. Write one from an achievement above."
- [ ] **Step 4: `Applications.jsx`.** Add-form fields: Company, Role, Role family (optional, "None"), CV version (optional, "None"), Source, Date applied (default today), Date posted (optional). Cards show company, role, family chip when set, CV name when set, source, date, the stage select and a "Delete" control (asks first). Weekly progress uses `today()` and shows only the count this week, "within 48 hours" and the bars. Findings render their button only when `link` is set. "Weekly review with AI" is disabled with no applications. Empty state: "Log your first application" opening the form. Insight bars are hidden until there is at least one application.
- [ ] **Step 5: Verify.** Lint and build succeed. In the browser:
  - Resume with no jobs shows the empty state; adding a job with a 10-character description is refused with the message beside the field.
  - Add a real-looking job Claude writes itself (generic title, "Company A", a 60-word description). Tailor: a CV and letter appear, named "{title}, Company A v1". Tailor again: "v2". Clicking the "v1" chip reopens it.
  - "Add to Applications with this CV" creates a card that shows the CV name.
  - Applications: drag the card to "Interview"; reload; it stays there. Delete asks first.
  - Add four applications in one family with no replies: "What to fix" shows the low-reply finding with a "Tailor a CV" button that opens Resume.
  - A date posted after the date applied shows "The posting date cannot be after the application date."
  - Interview coach, "General practice": the session card renders with no job selected. Tone decoder returns a result.
  - **Project owner:** run one voice mock interview and confirm feedback appears and a Journal entry is added.
- [ ] **Step 6: Commit** `feat: pathways, resume, interview coach and tracker on real data`.

---

### Task 16: Live checks, deployment configuration and documentation **[needs Node, Supabase]**

**Files:**
- Create: `backend/scripts/live_check.py`, `docs/ARCHITECTURE.md`
- Modify: `vercel.json`, `requirements.txt` (root), `.vercelignore`
- Move: `PLAN.md` → `docs/archive/PLAN-demo.md`, `docs/phases/Phase-1.md` → `docs/archive/Phase-1-demo.md`

- [ ] **Step 1: `live_check.py`.** Calls each of the eight `ai.*` functions once with short synthetic inputs written in the script, and prints one line per task: name, PASS or FAIL, seconds, and on failure the exception type. Exit code 1 if any fail. It prints no prompt, reply or key.
- [ ] **Step 2: Run it** from `backend/`. Expected: 8 PASS. If a task fails on the configured model, fix the prompt or parsing in `ai.py`/`llm.py`, add a unit test reproducing the reply shape, and rerun.
- [ ] **Step 3: Run `python setup_agents.py`.** Expected: both agents created or updated, ids written to `backend/.env`.
- [ ] **Step 4: Deployment files.** Root `requirements.txt`: add `psycopg[binary]` and `PyJWT[crypto]` pinned to the versions installed in the venv. `vercel.json`: add `"regions": ["lhr1"]` and exclude `backend/tests/**` and `backend/scripts/**` from the function. Do not deploy.
- [ ] **Step 5: Full automated run.** `pytest -v` from `backend/`: all pass, 0 skipped. `npm run lint` and `npm run build`: clean.
- [ ] **Step 6: End-to-end walkthrough** with the project owner, following spec section 14: sign up → details → onboarding → target roles → add a job → tailor a CV → mock interview feedback → log an application → sign out → sign in and see the same data → restart the backend and see the same data → sign up a second account and confirm every page is empty → delete the first account and confirm sign-in with it fails. Record each step as pass or fail.
- [ ] **Step 7: Write `docs/ARCHITECTURE.md`** with these sections: Purpose and audience; Roadmap and status (steps 0 to 7); System diagram; Tech stack with the reason for each choice; Decisions and trade-offs (spec section 16, plus any made during the build); Data model; API reference; AI layer (tasks, retry, fallback model, limits); Voice; Security and privacy, including the pre-launch list (review the privacy notice, add a contact email, turn email confirmation on with an email provider, split development and live databases, rotate keys); How to run locally; How to deploy to Vercel (variables to set, redirect URLs to add); Testing (commands, what each suite proves); Verification record (live check output summary and the walkthrough results with the date); Known limitations.
- [ ] **Step 8: Move the two demo documents** to `docs/archive/` with a first line stating they describe the retired demo.
- [ ] **Step 9: Commit** `docs: architecture and knowledge-transfer document; deployment config; live checks`.

---

## Self-Review Notes

- **Spec coverage.** Sections 3 (scope items 1–14) map to Tasks 12 (1, 13), 6 (2), 10–11 (3), 13 (4, 5, 6), 15 (7, 8), 5 and 14 (9), 9 (10), 4, 10 and 12–15 (11), 3 (12), 16 (14). Sections 7.4 and 7.5 are Task 5; section 8 is Tasks 3 and 4; section 9 is Tasks 11 and 13; section 10 is Task 9; section 11 is Tasks 2, 6, 8, 10 and 12; section 13's messages are pinned in Tasks 10 and 11; section 14's test list is spread across Tasks 2–11 and 16; section 17 is Task 16.
- **Additions beyond the spec**, each small and recorded in `docs/ARCHITECTURE.md`: a minimum of four timed applications before the timing rule fires; findings may have no link; `CONTACT_EMAIL`; `options.sources` and `options.stages` in the state; the job summary is skipped rather than refused when the daily limit is reached.
