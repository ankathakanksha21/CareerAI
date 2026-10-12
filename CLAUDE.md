# UK Career Navigator

A career agent for international students (Student visa) and recent graduates (Graduate visa) already in the UK. One profile built from the user's own experience drives UK-standard CVs, interview practice and an application tracker that says what to fix.

**Read first:** `docs/ARCHITECTURE.md` (scope, stack, decisions, data model, API, how to run, what is verified). Section 2 is the roadmap and current status.

## How work is organised

The product is built in numbered steps, 0 to 7. Each step has its own document in `.claude/skills/careerai-step-N-*/SKILL.md` holding every decision already made for it. To build one, load that step's skill and follow `careerai-building-a-step`, which is the method every step uses.

**Agreed build order:** 0 (done), then 2, 1, 3, 4, 5, 6, 7. Step 3 needs step 1; steps 6 and 7 need step 4. One step per session.

## Rules that apply to every change

- **Only real data.** No seeded people, companies, jobs or history. No canned AI answers: an AI task returns the model's real result or an error with Retry.
- **Show the source.** Anything presented as the user's words ("You said") must be checked against what they actually said or wrote.
- **Every user's data is private.** Every database function takes `(conn, user_id, ...)` and filters by it. Every new table and route gets a test proving account B cannot read or change account A's rows.
- **FastAPI is the only gateway to data.** The browser uses Supabase for login only.
- **No database connection held open across an AI, voice or other outside call.**
- **Everything that costs money is limited per user per day** (`limits.py`).
- **The menu shows only features that genuinely work.** Every page has an empty state with one clear action.
- **Tests first.** Write the failing test, watch it fail, then write the code. Run the whole suite before every commit, and on its own: the tests use the real database.
- **Shared tables are real.** `job_listings`, `job_searches`, `sponsors` and `reference_meta` hold live public data with no `user_id`. A test must use names that cannot be real, must never count or clear a whole table, and must use the `own_transaction` fixture for any code that calls `db.transaction()`.
- **Ask before building.** The project owner wants open questions settled before code is written. Decisions recorded in a step document are settled; do not re-ask them.
- **British English** in all copy and prompts. No em dashes in UI copy or prompts.

## Secrets and accounts

- Keys live only in `backend/.env` (git-ignored). Never print, log, commit or paste them. `backend/.env.example` lists every setting with where to find it.
- When a new key is needed, ask the owner to add it to `backend/.env`; do not ask for it in chat.
- Never type a password into the app or create accounts for the owner. During browser checks the owner signs in, speaks in voice calls and confirms deletions.

## Git

- Commit as the repository's configured identity (`ankathakanksha21`). Small commits, each with the full test suite passing.
- One branch per step, named `step-N-<short-name>`, created from `main`. When a step is finished the owner merges it into `main` through a pull request. Never merge into `main` yourself.
- Push only when the owner asks, and to the remote named `ankathakanksha21` (their own repository). Never push to `origin`.

## Commands

```
cd backend && .venv\Scripts\python -m pytest tests          # all backend tests (uses the real database, rolled back)
cd backend && .venv\Scripts\python migrate.py               # apply new migrations
cd backend && .venv\Scripts\python scripts/live_check.py    # one real call per AI task (uses credits)
cd backend && .venv\Scripts\python scripts/refresh_sponsors.py   # reload the gov.uk sponsor register
cd backend && .venv\Scripts\python scripts/reed_check.py   # one real Reed search; prints the reply's shape
cd backend && .venv\Scripts\python -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev                                  # http://localhost:5173
cd frontend && npm run lint && npm run build
```

Needs Python 3.12 and Node 20.19 or newer.
