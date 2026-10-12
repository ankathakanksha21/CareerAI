---
name: careerai-building-a-step
description: Use when starting, continuing or finishing any numbered step (0 to 7) of the UK Career Navigator roadmap in this repository, or when the owner says "build step N", "continue step N" or "what is left on step N"
---

# Building a CareerAI step

The method every step follows. The step's own skill (`careerai-step-N-*`) says WHAT to build and which decisions are settled. This says HOW.

**Core principle:** the owner has been burned by features that looked finished but ran on fake data. A step is done only when it works on real data, is proven by tests and by hand, and is written down.

## The six stages, in order

Each stage ends with something the owner can see. Do not start a stage before the previous one is finished.

### 1. Orient (no code)

- Read `CLAUDE.md`, `docs/ARCHITECTURE.md` and the step's skill.
- Check earlier steps are marked done in ARCHITECTURE section 2. If one is not, stop and tell the owner.
- Run the full backend suite and `npm run build`. Both must pass before you change anything. If they do not, fix that first and say so.
- Check every setting the step needs is in `backend/.env` (names only, never values). If a key is missing, give the owner the exact steps to get it and wait.

### 2. Settle what is open

- Decisions in the step's skill under "Decisions already made" are settled. Do not re-ask them.
- Everything under "Verify at build time" must be checked now against the live source (API docs, gov.uk). If reality differs from the document, tell the owner what changed and agree the new approach before continuing.
- Ask the owner any remaining question with a recommended option. Record each answer in the step's skill.

### 3. Plan

- Write a task-by-task plan against the code as it is today: files, function signatures, the tests for each task. Save it to `docs/superpowers/plans/YYYY-MM-DD-step-N-<name>.md`.
- Each task must be small enough to test on its own.
- The owner approves the plan before any product code is written.

### 4. Build, test first

For every task: write the test, run it and watch it fail for the right reason, write the code, run it and watch it pass, run the whole suite, commit.

Every step must include these tests, whatever else it adds:

| For each new... | Test that... |
|---|---|
| Table | Rows are deleted with the account; RLS is on; browser roles have no privileges |
| Database function | Another user gets nothing and changes nothing |
| Route | 401 without a token; 422 for a malformed id; 404 for another user's id; the daily limit applies if it costs money |
| AI task | Odd model output is normalised or rejected; nothing is saved when it fails; quotes shown as the user's words are checked |
| Outside service | Failure and timeout show a clear message; no key appears in any response or log |

### 5. Verify

- Whole suite passes with 0 skipped. Frontend lints and builds.
- One real call per new AI task (`scripts/live_check.py`, extended for the step).
- Every item in the step's "Check by hand" list is done in a browser. The owner does sign-in, voice and deletions.
- Anything you could not verify goes in the report as **not verified**. Never describe it as working.

### 6. Document and report

- Update `docs/ARCHITECTURE.md`: roadmap status, new decisions and trade-offs, data model, API, the verification record with dates, known limitations.
- Update the step's skill: status, and any decision that changed.
- Update the privacy page if the step collects or sends new personal data.
- Final message to the owner: what was built, what was verified and how, what was **not** verified, every judgement call you made and what it costs if wrong, and what they need to do.

## When to stop and ask the owner

- A settled decision turns out to be impossible or clearly wrong.
- A needed key or account is missing.
- Something would cost money beyond the daily limits, delete data, or be visible outside this repository (a push, a deploy, an email).
- You are unsure what the owner meant. Ask what the goal was; do not guess.

## Red flags

| Thought | Reality |
|---|---|
| "I'll add sample data so the page isn't empty" | No. Write an empty state. |
| "The AI call failed, I'll return something plausible" | No. Return the error; the page shows Retry. |
| "This decision is in the step document but I'd do it differently" | It is settled. Raise it with the owner or follow it. |
| "The tests pass, so it works" | Tests do not replace the hand checks. Do both. |
| "I'll write the tests after" | The test comes first and must be seen failing. |
| "The owner can verify that later, I'll call it done" | Report it as not verified. |
| "I need the key to continue, I'll ask for it in chat" | Ask them to put it in `backend/.env`. |
| "This is nearly done, I'll push it" | Push only when asked, and only to the `ankathakanksha21` remote. |

## If other process skills are installed

If `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:executing-plans` and `superpowers:test-driven-development` are available, use them for stages 2, 3 and 4. The decisions in the step's skill count as the brainstorming already done; start from "Verify at build time" and any open questions. If they are not installed, the stages above are complete on their own.
