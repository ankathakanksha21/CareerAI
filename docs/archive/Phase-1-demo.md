> **Archived.** This describes the retired single-persona demo (October 2026), not the current app. See `docs/ARCHITECTURE.md`.

# Phase 1: clickable app on seeded data, fallbacks wired, agent setup script written

Scope from PLAN.md: the full app on seeded data, every live endpoint wired with a demo-safe fallback, the agent setup script written, verified in fallback mode without keys. No keys are needed to run or test this phase.

## What was built

Backend, in `backend/` (FastAPI):

- `main.py`: all routes. State is in memory, loaded from `data/seed.json`; `POST /api/reset` restores it.
- `config.py`: reads `backend/.env` on every call, so edits apply without a restart. A value starting with `your-` counts as unset.
- `llm.py`: Bedrock through Mantle. `anthropic.*` model IDs go through `AnthropicBedrockMantle` (Messages API). Any other prefix goes through the OpenAI-compatible `/v1/chat/completions` on `bedrock-mantle.<region>.api.aws`, with the Mantle key as bearer. JSON is extracted from the reply.
- `ai.py`: 8 live tasks, each one prompt to JSON with a canned fallback: evidence extraction plus two-line pitch, role family suggestions, CV and cover letter tailoring, evidence to STAR story, interview feedback scores, UK tone decode or rewrite, outreach message draft, weekly diagnosis review.
- `analytics.py`: funnel and response rates by role family, CV version, source and timing; a visa-fit label per job; rule-based diagnosis with 5 rules (CV/tailoring, storytelling, network, direction, timing), each linking to the page that fixes it.
- `voice.py`: mints an ElevenLabs conversation token for WebRTC and fetches a transcript server-side.
- `setup_agents.py`: creates or updates the onboarding coach and mock interviewer agents through the ElevenLabs API and writes `ELEVENLABS_ONBOARDING_AGENT_ID` and `ELEVENLABS_INTERVIEWER_AGENT_ID` into `backend/.env`. If the full config gets a 422, it retries with a minimal config.
- `data/seed.json`: persona Aditi Rao, 6 evidence items, 5 role families, 11 fictional jobs, 24 applications, 6 STAR stories, 6 contacts, a buddy group of 3, calendar, UK game tips, tone phrases, a weekly plan of 8 tasks.
- `.env.example`, `requirements.txt`.

Frontend, in `frontend/` (Vite, React 19, no router, no UI library, one stylesheet `src/index.css`, font Hanken Grotesk):

- `App.jsx`: sidebar drawn as a route line with one colour per product layer, a dashed return track for the loop, a status footer (AI live or demo mode, voice agents ready or not set up) and the Reset demo data button.
- `VoiceAgent.jsx`: `@elevenlabs/client` Conversation over WebRTC with a backend-minted token, live transcript, and a fallback that fetches the transcript server-side.
- `ui.jsx`: shared pieces, including the "Live AI" or "Demo fallback" badge and the fallback note.
- `pages/Home.jsx`: This Week plan, next best step from the top diagnosis finding, visa countdown, funnel, streak, milestones, upcoming dates, buddy mini view.
- `pages/Evidence.jsx`: voice coach, paste or sample transcript, Evidence Bank cards ("you said" vs UK version, context note), two-line pitch, Make a STAR story.
- `pages/Direction.jsx`: role families with a Targeting toggle, AI re-check of fit, matched jobs filtered by the selected families with visa-fit badges, Tailor CV and Log application, offer visa check, timeline, UK game tips, job sources.
- `pages/Prep.jsx`: tabs for CV and cover letter tailoring per job (CV version saved), STAR stories, mock interview (voice, or sample-transcript scoring), UK tone decoder.
- `pages/Reach.jsx`: contacts with status, AI outreach draft with copy and mark-as-sent, 6-step hidden market playbook, UK project nudge.
- `pages/Tracker.jsx`: diagnosis findings with fix links, AI weekly review, funnel, response-rate bars by family, CV version, source and timing, add-application form, a stage dropdown per application that updates the diagnosis live.
- `pages/Buddies.jsx`: members with streaks, goals and progress, nudge, group feed.

Other: `.claude/launch.json` has a `backend` config (uvicorn on 8000 with reload) and a `frontend` config (Vite on 5173). Vite proxies `/api` to `127.0.0.1:8000`. `PLAN.md` holds the approach, stack reasoning and demo script.

## How to run it

Dependencies are already installed in `backend/.venv` and `frontend/node_modules`. Two PowerShell terminals, both starting from the repo root.

Terminal 1, backend:

```
cd backend
.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

Terminal 2, frontend:

```
cd frontend
npm run dev
```

Open http://localhost:5173. Optionally open http://localhost:8000/docs to see the API.

Starting Phase 2 (going live), after this phase is tested: copy `backend/.env.example` to `backend/.env`, then fill `AWS_REGION`, `BEDROCK_API_KEY` (the Mantle API key), `BEDROCK_MODEL_ID` (the exact provider-prefixed ID from the Mantle console) and `ELEVENLABS_API_KEY`. Then, from `backend/` with the venv active:

```
python setup_agents.py
```

No server restart is needed. The sidebar footer turns green when AI and voice are configured.

## What to verify

With no `.env`, the sidebar footer should read "AI in demo mode (no Bedrock key)" and "Voice agents not set up". Every AI result should carry the "Demo fallback" badge, with the note "Set AWS_REGION and BEDROCK_MODEL_ID in backend/.env". Press Reset demo data before each pass.

1. Each of the 7 sidebar pages loads with no error banner: This week, My evidence, Where to aim, Get ready, Open doors, Run the search, Buddies.
2. This week: the "Your next best step" button (label "Tailor a CV" on the seed) jumps to the CV and cover letter tab in Get ready.
3. This week: tick a task and the "N of 8 done" count updates. The visa countdown shows 115 days (from the fixed demo date 2026-10-08 to the seeded visa end 2027-01-31, computed from the code, not observed).
4. My evidence: "Use sample transcript" then "Build my Evidence Bank" adds 3 new cards and the two-line pitch, with the Demo fallback badge. "Make a STAR story" on a card adds a story under Get ready, STAR stories.
5. Where to aim: untick Targeting on a role family and the matched jobs list changes. "Log application" on a job adds a row in Run the search under Applications.
6. Where to aim, Offer check: it defaults to 36,000 with Licensed sponsor and New entrant ticked, which reads as visa-viable (threshold 33,400). Set the salary below 33,400, or untick New entrant (threshold 41,700), and the verdict turns to the "below the threshold" message. Untick Licensed sponsor for the Graduate Route message.
7. Get ready: "Tailor CV and cover letter" for a job returns a CV, cover letter and CV version name, and the version appears in the tracker's CV version choices. "Score a sample interview" returns scores. The tone decoder returns for both buttons.
8. Open doors: "Draft a message" on a contact, then "Copy message" and "Mark as sent" (status becomes messaged).
9. Run the search: the seed diagnosis should show these findings, in this order of severity (CV and story first):
   - Product Analyst: 0 responses from 7 applications, all on the Data Analyst v2 CV.
   - Interviews to offers: 4 interviews, 0 offers.
   - Referrals: 2 of 2 replied, job boards 0 of 15.
   - Timing: average 4.4 days after posting, 5 of 6 fast applications replied vs 0 of 18 slow.
   - Few visa-ready BI Analyst roles.
   The funnel should read 24 applied, 5 replies (21%), 4 interviews, 0 offers, and the sidebar badge on Run the search should show 5.
10. Run the search: set a Product Analyst application to Interview with the stage dropdown. The funnel and findings update immediately. From the rule in `analytics.py` (a family is flagged at 4 or more applications and a response rate under 0.15), the first change gives 1 of 7 (0.14) so the finding stays with new numbers, and a second one gives 2 of 7 (0.29) so the finding disappears. This is derived from the code, not run.
11. Run the search: "Weekly review with AI" returns a fallback review with the badge.
12. Buddies: "Send a nudge" disables the button and adds a line to the group feed.
13. Reset demo data restores everything from steps 3 to 12.
14. My evidence or Get ready, "Start talking" without keys: shows the setup message instead of starting a call. Check the browser console is clean throughout.

Verified in Phase 1 without keys (real results):

- Every API endpoint was exercised with FastAPI TestClient in fallback mode: state, reset, task toggle, family select, add and update application, contact status, nudge. All 8 AI endpoints returned fallback data with `live=false` and the note above. The voice token endpoint returned 503 with a setup message when keys are missing.
- All 7 screens rendered in the browser at 1440 px and 375 px wide with no horizontal overflow and no console errors.
- Clicked through: sample transcript to Evidence Bank (3 new cards and pitch, Demo fallback badge), Tailor CV for Lumen Health, Weekly review with AI, Score a sample interview, Draft a message, Start talking without keys.

## Known limitations

Not verified yet (needs keys, Phase 2):

- Live Bedrock calls through Mantle, on both the `anthropic.*` path and the non-Claude chat/completions path.
- `setup_agents.py` against the real ElevenLabs API: the payload fields `dynamic_variables.dynamic_variable_placeholders` and `platform_settings.auth.enable_auth`, the voice IDs for Alice (`Xb7hH8MSUJpSbSDYk0k2`) and George (`JBFqnCBsd6RMkjVDRZzb`), and the agent LLM `gemini-2.5-flash`.
- The conversation token endpoint, the WebRTC session and transcript capture.
- Latency of each live call.

Known limits of the build:

- State is in memory and resets on backend restart, including the auto-reload when backend code changes.
- Visa salary thresholds (£41,700 general, £33,400 new entrant) are illustrative July 2025 figures, with an on-screen note to check gov.uk.
- All job companies and contacts are fictional.
- The visa countdown uses a fixed demo date of 8 October 2026 so the seeded week stays consistent.
- The AI role-family re-check is shown beside the seeded families and does not replace them.
- Response rates count recent "applied" rows that may not have had time to reply.
- The production JS bundle is 845 kB (fine for a local demo).
- Voice needs a microphone and network. The sample-transcript buttons are the fallback.
