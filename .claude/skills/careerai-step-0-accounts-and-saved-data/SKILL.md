---
name: careerai-step-0-accounts-and-saved-data
description: Use when a question or task concerns step 0 of the CareerAI roadmap (sign-up and login, per-user saved data, daily limits, removal of the demo persona, the live voice transcript), or when finishing its remaining hand checks
---

# Step 0: accounts and saved data

**Status:** Built, 12 October 2026. Three hand checks remain (below).
**Record of the work:** spec `docs/superpowers/specs/2026-10-11-step-0-accounts-and-persistence-design.md`, plan `docs/superpowers/plans/2026-10-11-step-0-accounts-and-persistence.md`, and `docs/ARCHITECTURE.md`.

## What it delivered

- Supabase login (email and password): sign up, sign in, password reset, delete account.
- Postgres tables for every user's data, with versioned migrations. FastAPI is the only gateway; every query is filtered by the caller's user id.
- Onboarding for a real person: details form, then voice or pasted text, then profile, then AI-suggested role families.
- Paste-a-job, tailored CV and cover letter saved as versions, mock interviews, STAR stories, application tracker with diagnosis, journal.
- Per-user daily limits on AI actions (40) and voice sessions (3).
- All demo data and canned AI answers removed. Networking and Peers hidden until their steps.
- Added on the owner's request: a live transcript during voice calls, transcripts saved with journal entries, and "You said" quotes checked against the transcript.

## Decisions that later steps inherit

| Decision | Detail |
|---|---|
| Audience | International students on a Student visa and recent graduates on the Graduate visa, already in the UK |
| Stack | React (Vite) + Python FastAPI on Vercel; Supabase for login and Postgres; Bedrock for the model; ElevenLabs for voice |
| Data access | Tables behind FastAPI; plain SQL in `repo.py`; deny-all row-level security |
| No fake content | An AI task returns the real result or an error with Retry |
| Unbuilt features | Hidden from the menu until their step makes them real |
| Job input for now | The user pastes a job's title, company and description |
| Costs | Every paid action is limited per user per day |
| Git | Small local commits on a feature branch; push only when asked, to the owner's own repository |

## Remaining hand checks

1. Profile → "Edit details" shows month and year lists for graduation and saves.
2. A second account sees none of the first account's data on any page.
3. Deleting that second account from Account → "Delete my account" works, and signing in with it then fails.

Also not yet verified by hand: the password-reset email flow, and a Vercel deployment of this version.

## Before any public launch

Listed in `docs/ARCHITECTURE.md` section 11: review the privacy notice and set `CONTACT_EMAIL`, turn email confirmation back on with an email provider, use a separate Supabase project for live data, rotate every key that has been shared.
