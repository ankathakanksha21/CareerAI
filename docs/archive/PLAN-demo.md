> **Archived.** This describes the retired single-persona demo (October 2026), not the current app. See `docs/ARCHITECTURE.md`.

# UK Career Navigator: 3-hour demo build plan

A demo prototype of a career loop for international students in the UK. Eight features, one fictional user, fake data where it is not the point, live models where it is. The loop:

Profile -> Direction -> Preparation -> Action -> Tracking -> Diagnosis -> back to Profile.

Claude builds the code in phases (section 8). Dharan's hours go mostly into testing, filling keys and rehearsal.

## 1. The core approach

Build a story demo, not a product. The audience should believe the loop works after five minutes, so everything is arranged around one story.

- One persona: Aditi Rao, MSc Business Analytics at University of Exeter, 3 years as a data analyst at Infosys in Bengaluru, on a Student visa and moving to the Graduate Route.
- One seeded week of history, so every screen opens with something already in it.
- The loop visible on every screen: the sidebar is drawn as a route line (Evidence, Direction, Preparation, Reach, Run the search) with a dashed return track from diagnosis back to the top, and each layer keeps its line colour on tasks and findings.
- Fake everything that is not the point: job listings, tracker history, contacts, buddies, calendar.
- Make 6 "magic moments" live, because those are what convince the audience.
- The home screen is "This Week", not a feature menu. The design principle is "what should I do next, and why", and every screen should answer it.

The six moments, taken from the beats of the demo walkthrough (section 7). This is a working list, change it if you want a different six.

| # | Moment | Screen | Engine |
|---|--------|--------|--------|
| 1 | Talk to the onboarding coach, evidence cards appear | My Evidence | ElevenLabs agent, then Bedrock |
| 2 | CV bullets and cover letter tailored to one job | Get ready | Bedrock |
| 3 | Voice mock interview | Get ready | ElevenLabs agent |
| 4 | Interview feedback on structure, tone, clarity, UK tone | Get ready | Bedrock |
| 5 | Diagnosis finding from tracker stats, linked to its fix | Run the search | Rule-based on live tracker state |
| 6 | Outreach message draft for an alumni contact | Open doors | Bedrock |

The other live endpoints (role re-suggestion, STAR story, UK tone decoder, "explain with AI") are built too, but they are off-script.

## 2. Stack and why

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python FastAPI, single process, in-memory state loaded from `backend/data/seed.json` on start, plus a reset endpoint that reloads the seed | Nothing needs to persist past a demo, and a JSON seed is editable by hand. A database adds setup and nothing the audience sees |
| Frontend | React via Vite, no router, no UI library, one stylesheet, hand-drawn bar charts | Fewest moving parts, nothing to learn or debug beyond React itself |
| Dev wiring | Vite dev server proxies `/api` to FastAPI on port 8000 | No CORS setup |
| LLM | AWS Bedrock through the Mantle endpoint | One key, model chosen by `.env` |
| Voice | ElevenLabs Agents (Conversational AI), `@elevenlabs/client` over WebRTC | Real-time voice with a transcript stream, no audio plumbing to write |

LLM details.

- Client: `AnthropicBedrockMantle` from the `anthropic[bedrock]` package, authenticated with a Bedrock (Mantle) API key. Checked in the installed SDK: the constructor takes `api_key` and `aws_region`, and the default base URL is `https://bedrock-mantle.<region>.api.aws/anthropic`. Left alone, the SDK reads the key only from `AWS_BEARER_TOKEN_BEDROCK` or `ANTHROPIC_AWS_API_KEY`, so the code passes `BEDROCK_API_KEY` and `AWS_REGION` from `.env` explicitly.
- Model: the ID lives in `.env` as `BEDROCK_MODEL_ID`, and Dharan picks it from his Mantle console. Code dispatches by prefix. `anthropic.*` goes through the Messages API. Any other family goes through the OpenAI-compatible `/v1/chat/completions` surface on the same Mantle host (unverified, from the brief, not checked against AWS docs). Swapping models is an `.env` edit.
- Shape of every call: one prompt in, JSON out, parsed on the server. A parse failure or any error triggers the canned fallback.

Voice details.

- Two agents. An onboarding coach interviews the user about their background. A mock interviewer interviews for a chosen role and company, passed in as dynamic variables.
- The browser asks the backend (`/api/voice/token`) for a short-lived conversation token. The backend holds the ElevenLabs key and mints the token, so the key never reaches the browser.
- The browser then calls `Conversation.startSession` with that token over WebRTC. Checked in the installed SDK types: `conversationToken` with `connectionType: "webrtc"` and `dynamicVariables` are supported options.
- The live transcript streams into the UI through the SDK's `onMessage` callback. When the call ends, the transcript goes to Bedrock (Evidence Bank extraction for the coach, STAR feedback for the interviewer).
- `backend/setup_agents.py` creates both agents through the ElevenLabs API, using prompts kept in the repo, and writes the agent IDs into `.env`.

Why not no-code or an agent framework.

- Agent frameworks (LangGraph, CrewAI): each AI step here is one prompt in, JSON out. A framework adds latency and debugging surface without changing what the audience sees.
- No-code (Lovable, Bubble): the custom loop logic (diagnosis rules, tracker analytics) and the ElevenLabs plus Bedrock wiring get harder, not easier.

## 3. Architecture

```
Browser (React, :5173)
  |  /api/*  (Vite proxy)                    ^  WebRTC audio (direct)
  v                                          v
FastAPI (:8000)                        ElevenLabs Agents
  /api/state                             (coach, interviewer)
  /api/ai/*
  /api/voice/token
  |                |
  v                v
Bedrock Mantle   ElevenLabs API
(LLM calls)      (mints the token)
```

The browser talks to FastAPI for state and AI, and talks to ElevenLabs Agents directly for audio. FastAPI is the only thing that holds keys.

## 4. Live vs fake

Six product layers plus the home screen. Feature numbers are the eight features of the brief.

| Layer | Screen | Seeded | Live |
|-------|--------|--------|------|
| Home | This Week | Weekly plan with tasks pulled from each layer, streak, milestones, top diagnosis banner | Banner and tasks follow the current tracker state |
| Foundation (feature 1) | My Evidence | Evidence items | Voice onboarding with the ElevenLabs coach, transcript to Bedrock, structured evidence cards in UK CV language with a context note for foreign employers. Also a paste-text path |
| Direction (feature 2) | Where to aim | Role families (direct, near, stretch with overlap %, UK titles, salary range, sponsorship likelihood), UK recruitment calendar, job sources, matched jobs with visa-fit badges, offer visa check (salary vs threshold, sponsor licence) | Re-suggest role families from the current Evidence Bank |
| Preparation (feature 4) | Get ready | STAR story bank | CV bullets and cover letter (why them, why you, what you'll deliver) tailored to a chosen job from the Evidence Bank. "Turn this evidence into a STAR story". Voice mock interview with the ElevenLabs interviewer, then Bedrock feedback on structure, tone, clarity and UK tone. UK tone decoder (decode a British phrase, or rewrite your sentence in UK tone) |
| Reach (features 3 and 7) | Open doors | Hidden-market playbook, outreach tracker with fictional alumni contacts, nudge toward one UK project or volunteer role | Outreach message draft per contact |
| Execution (features 5 and 6) | Run the search | Tracker of about 24 applications (role family, CV version, source, stage) | Add or update applications. Funnel and response-rate charts by role family, CV version and source. Rule-based diagnosis. "Explain with AI" coaching note from the stats |
| Support (feature 8) | Not alone | Buddy group of 3 with shared streak view and nudge button | Nothing, fully seeded |

Diagnosis rules. Each finding links back to the module that fixes it. Thresholds are set in Phase 1 and tuned so the seeded tracker produces the Product Analyst finding used in the demo.

| Pattern in the tracker | Finding | Fix lives in |
|------------------------|---------|--------------|
| Low response rate | CV or tailoring | Get ready (CV tailoring) |
| Interviews but no offers | Storytelling | Get ready (STAR stories, mock interview) |
| Few relevant roles | Direction | Where to aim |
| No outreach replies | Network | Open doors |

## 5. Demo-safe design

- Every live endpoint has a canned fallback, returned on timeout, error or unparseable output.
- Every live result shows a small badge, "Live AI" or "Demo fallback", so Dharan always knows what happened.
- A "Reset demo" button calls the reset endpoint and restores the seed. Press it before every run.
- The voice call itself needs the network. Its Bedrock steps (evidence extraction, STAR feedback) have fallbacks, and Evidence also has the paste-text path if the mic is unavailable.
- Rehearse once with wifi off to see every fallback fire and check that the badges read correctly.

## 6. Build order and time budget

The time budget is the order of work. Because Claude writes the code, the phase boundaries in section 8 decide when your keys are needed: Phase 1 runs with no keys, Phase 2 is where the key steps below happen.

1. 0:00-0:15, accounts and keys. Copy `.env.example` to `.env` and fill `AWS_REGION`, `BEDROCK_API_KEY`, `BEDROCK_MODEL_ID`, `ELEVENLABS_API_KEY`. The venv and the Vite scaffold already exist. Run `setup_agents.py` once the keys are in (command in section 10).
2. 0:15-0:45, seed and state. Write `backend/data/seed.json` for Aditi (evidence, role families, jobs, about 24 applications, contacts, buddies, calendar, STAR stories, weekly plan). FastAPI loads it on start and serves `/api/state`, the tracker add and update endpoints, and the reset endpoint. Quick check: open `http://localhost:8000/docs`.
3. 0:45-1:30, React screens in loop order: This Week, My Evidence, Where to aim, Get ready, Open doors, Run the search, Buddies. Build the sidebar loop line and the badge component first, then each screen against seeded data, hand-drawn charts last. Add the `/api` proxy to `vite.config.js`.
4. 1:30-2:15, live endpoints. One `/api/ai/*` endpoint per live feature, each a single prompt returning JSON. Then the two voice flows: the token endpoint, `startSession` in the browser, the live transcript, and transcript to Bedrock on call end.
5. 2:15-2:40, close the loop. Wire the four diagnosis rules to the tracker with links to their fix screens. Add the fallbacks, the badges and the Reset demo button.
6. 2:40-3:00, rehearse the demo walkthrough (section 7) twice, pressing Reset demo between runs. Do one of the two with wifi off.

## 7. Demo walkthrough

The main path takes about 11 minutes at the times below. It follows the app as it is now: a landing page, a three-step onboarding, then the app with a left sidebar. The sidebar has two groups, "Your search" (This week, Profile, Career pathways, Resume, Interview coach, Applications) and "Community" (Networking, Peers, Journal). Dharan plays Aditi Rao (MSc Business Analytics at Exeter, 3 years as a data analyst at Infosys, Student visa ends January 2027) in the voice parts. Names in quotes after "Click" are the exact labels on screen. "Say" lines are written to be spoken aloud.

### Before you start

- [ ] Backend and frontend are running (commands in section 10).
- [ ] Open http://localhost:5173 in a Chrome guest window, or a Chrome profile with no extensions. An extension blocked the WebRTC voice host once. The app now falls back to a WebSocket by itself, but a clean profile is the safest.
- [ ] Click "Open dashboard" on the landing page and check that the sidebar footer shows "AI live" and "Voice ready".
- [ ] Warm up the AI a few minutes ahead: "Interview coach", tab "UK tone decoder", "Rewrite in UK tone". Wait for the "Live AI" badge, so the first call in front of the audience is not the slow one.
- [ ] Allow the microphone once: "Interview coach", tab "Practice sessions", "Start talking", allow, then "End". Wait about 10 seconds, because ending a call with a transcript starts an AI scoring call.
- [ ] Click "Reset demo data" in the sidebar footer (a toast says "Demo data restored"). Do this last, after the warm-up calls finish, so a late result cannot land after the reset.
- [ ] Click "UK Career Navigator" at the top of the sidebar to go back to the landing page. Set browser zoom to 110 to 125 percent and go full screen.
- [ ] Do not edit code or restart the backend during the demo. A restart wipes the demo state.

### 0. Open (20 s, no clicking)

- Say: "International students do not know how UK hiring works, so they apply blindly and cannot tell why it is not working. This gives them a plan for this week and tells them what to fix."
- Say, once, then move on: "The AI and the voice are live. The people, companies and six weeks of history are sample data, so you can see the product in the middle of a search."

### 1. Landing page (30 s)

- Show: the headline, the example weekly plan on the right, then the six cards under "What you can do": "Resume optimisation (UK standard)", "Interview prep", "Application tracker", "Networking events near you", "Career pathways", "Find your peers". Point at them, because clicking a card jumps straight into that screen.
- Say: "Six tools, and they share one profile, so each one knows what the others found."
- Click: "Get started".

### 2. Onboarding step 1, "Your background" (about 2 min)

- Show: two options, "Talk to our careers coach" (selected by default) and "Paste your CV or notes".
- Say: "I'll play Aditi, a typical user."
- Click: "Start talking" and allow the microphone if asked. The coach greets her with "Hi Aditi". Click "Show talking points for the demo" and use its five lines as your script (course, Infosys, the Power BI churn dashboard with 40 managers and closures down 6%, the Python Monday reports saving about 12 hours a week, target roles and visa). Answer in short sentences for 60 to 90 seconds, then click "End". Do not mention A/B tests or experiments, because the Product Analyst gap in step 4 depends on it.
- Say while it builds (about 7 s, "Building your profile" on screen): "The transcript is being turned into achievements written for UK employers."
- If voice fails: click "Paste your CV or notes", then "Use a sample background", then "Build my profile".

### 3. Onboarding step 2, "Your profile" (30 s)

- Show: the two-line pitch in the first person, then the "achievements captured" heading. Each achievement is rewritten as a UK CV bullet that starts with an action and carries a number.
- Say: "What I said out loud is now a CV bullet a UK recruiter can scan, with the action first and a number. It translates overseas experience into UK language."
- Click: "Continue".

### 4. Onboarding step 3, "What UK employers actually look for" (30 s)

- Show: one card each for Data Analyst, Business Intelligence Analyst and Product Analyst. Every requirement is ticked with the achievement that proves it ("Shown by: ..."), or marked as a gap. "A clear answer on right to work" is flagged with "!" as something to prepare. On the Product Analyst card, point at the gap "A/B testing and experiment design".
- Say: "For each role I can see what I already show and what is missing. For Product Analyst it is A/B testing. Right to work is something to prepare."
- Click: "Go to my dashboard".

### 5. This week (40 s)

- Show: the "Your next best step" banner at the top, with its reason underneath ("Why: 0 responses from 7 applications..."). Then the "Weekly plan", where every task has a "why" line, and the card "115 days until your Student visa ends".
- Say: "The home page is this week's plan. The top step comes from what the tracker found, and every task says why."
- Optional, 20 s: click "Profile". Each achievement shows "You said:" next to its UK version, plus a note for UK recruiters. The seeded card "Churn dashboard for a UK retail bank client" explains that Infosys is one of India's largest IT services firms with major UK banking clients. Say: "A recruiter who has never heard of Infosys still understands what that job was."
- Click: "Applications".

### 6. Applications (about 90 s)

- Show: "Weekly progress" at the top (0 of 5 applications this week, with bars per week), then the board with the columns Applied, No reply, Phone screen, Interview, Offer and Rejected.
- Say: "Aditi has sent 7 Product Analyst applications and heard nothing back."
- Do: scroll to "What to fix" and read the top finding, "0 responses from 7 applications". Scroll back up and drag the Product Analyst card "Bramble Home" from "No reply" to "Phone screen". If the drag does not take, use the stage dropdown on the card and pick "Phone screen". Scroll down and the finding now reads "1 response from 7 applications".
- Say: "I moved one card and the diagnosis recalculated."
- Show: the findings in "What to fix". Each names a problem type (CV and tailoring, Storytelling, Network, Timing, Direction) and has a button to the screen that fixes it. Optional, 10 s: "Weekly review with AI" (a few seconds, "Live AI" badge).
- Say: "Job boards do not do this part. The tracker tells me why it is not working. All 7 Product Analyst applications went out with the same Data Analyst v2 CV."
- Optional line while scrolling: "Referrals got replies 2 of 2 times, job boards 0 of 15. Applications sent within 48 hours of posting got 5 replies from 6, later ones 0 from 18."
- Click: "Tailor a CV" on the Product Analyst finding.

### 7. Resume (about 60 s)

- Show: the job picker already reads "Product Analyst, Lumen Health".
- Click: "Tailor CV and cover letter" (about 6 s).
- Show: the CV version name in the chip above the CV, the bullets picked from the profile under "Experience, selected for this role", "Keywords covered", the cover letter in three parts ("Why Lumen Health", "Why me", "What I will deliver"), and "Be ready to talk about" for the gaps.
- Say: "It picks the most relevant achievements from my profile and rewrites them in this job's language. The cover letter follows the UK shape, why them, why me, what I will deliver."
- Click: "Add to Applications with this CV".
- Say: "The tracker can now compare this CV against the old one, which closes the loop."
- Optional, 10 s: click "Applications" to show the new card in the Applied column and "1 of 5" this week. "Reply rate by CV version" under Insights now lists the new CV.

### 8. Interview coach (about 90 s)

- Click: "Interview coach". Four session cards show: "CV walkthrough", "Job-specific interview", "HR screening call", "Behavioural round".
- Click: "HR screening call". "Practising for" already reads "Insight Analyst, Northwind Retail Group".
- Say: "I'll take the HR screening call, because it asks about right to work and sponsorship. That question matters most to international students."
- Click: "Start talking", answer one or two questions, then click "End". Scoring takes a few seconds ("Scoring your answers").
- Show: scores out of 5 for Structure, Clarity, Evidence and UK tone, then "What worked", "Change next time", "A stronger answer", the "UK tone" notes and "Saved to your Journal."
- Say: "I get scored on four things and shown a stronger version of my own answer."
- If voice fails: click "Score a sample interview".
- Optional, 15 s: tab "UK tone decoder", then "Rewrite in UK tone" on the prefilled sentence "I am the best candidate for this role and I can do everything you need."

### 9. Career pathways (40 s)

- Click: "Career pathways".
- Show: the role family cards, each marked "Direct fit", "Near fit" or "Stretch", with % overlap, salary and sponsorship likelihood. Under "Matched jobs this week" every job carries a visa badge. Point at "Data Analyst, Halden Building Society" (£32,000) with the badge "Check salary".
- Show: the "Offer check" box. Type 32000 in "Salary (£)" and it reads that £32,000 is £1,400 below the £33,400 threshold. The small print under it says the figures are illustrative (July 2025 rules) and to check gov.uk.
- Say: "Every job is checked for visa fit before I spend time on it. This one pays £32,000, which is below the £33,400 new-entrant threshold."
- Say: "The thresholds are illustrative July 2025 figures, and the screen tells you to check gov.uk."

### 10. Networking (40 s)

- Click: "Networking".
- Show: "Events near you" (Exeter and the South West, plus online). Click "RSVP" on "Exeter Data and Analytics Meetup" and it turns into "Going".
- Say: "In the full product this sends my RSVP. Here it records it."
- Click: "Draft a message" for James Okafor under "Alumni outreach" (Product Analyst at Lumen Health, Exeter alumnus, BSc 2021). It takes a few seconds.
- Show: the subject, a message under 80 words with one clear ask for advice, the follow-up in two weeks, and the buttons "Copy message" and "Mark as sent".
- Say: "James is an Exeter alumnus at Lumen Health, the company Aditi just tailored a CV for. The draft asks him for advice and stays under 80 words."

### 11. Peers and Journal (about 60 s)

- Click: "Peers".
- Show: "Matched with you", a card per peer with a match percentage and chips for what you share. Point at Arjun Iyer, 92% match (MSc Data Science at Bristol, 2 years at TCS in Chennai; shared: Indian IT services background, BI and data analyst roles, Graduate Route from 2027).
- Say: "Arjun is a 92% match on course, past work, target roles and visa route."
- Click: scroll to "Session notes", then "Use sample notes" (it picks Arjun and fills in rough notes), then "Generate session notes" (a few seconds).
- Show: the clean note ("Aditi Rao met Arjun Iyer") with what was done, what was discussed and the actions, then the new entry at the top of "Who met who".
- Say: "I typed rough notes after a chat. It turns them into who met who, what we did and the action items."
- Click: "Journal". The coach call, the mock interview and the peer chat from this demo sit at the top with a "New" chip. Older seeded entries with similar titles (22 and 26 September) sit below, so point at the ones marked "New". Click "Session notes" on one entry to open it.
- Say: "I did not log any of these. They landed here on their own."
- Optional, 10 s: on Peers, Chen Wei's card (88% match, same course) reads "Strong on A/B testing, your Product Analyst gap", which answers the gap from step 4.

### 12. Close (20 s)

- Click: "This week".
- Show: the numbers moved with what you did (25 applied and 6 replies, if you did the drag and the CV step). The banner still says to tailor a Product Analyst CV, because the rule keeps firing until the Product Analyst reply rate reaches 15 percent. If asked, say the new CV needs replies first.
- Say: "Every screen answers the same question, what should I do next, and why."
- Then stop talking and take questions.

### A 5-minute version

1. Landing page (20 s): "Get started".
2. Onboarding (60 s): skip voice. "Paste your CV or notes", "Use a sample background", "Build my profile", then "Continue" and "Go to my dashboard".
3. This week (20 s): point at the sidebar and name the three skipped screens in one sentence each. Say: "Career pathways checks every job for visa fit." "Networking has events nearby and alumni messages I can draft." "Peers matches me with students who have a similar background."
4. Applications (60 s): drag "Bramble Home" to "Phone screen", show "What to fix", click "Tailor a CV".
5. Resume (45 s): "Tailor CV and cover letter", then "Add to Applications with this CV".
6. Interview coach (45 s): "HR screening call", then "Score a sample interview".
7. Journal (15 s): the new entry from the interview.
8. Close (15 s): back to "This week", with the closing line from step 12.

### Real vs demo

| Kind | What |
|------|------|
| Live AI | Profile building and pitch, CV and cover letter tailoring, STAR stories, interview feedback, UK tone decoder, outreach drafts, weekly AI review, role-fit re-check ("Re-check fit from my profile"), peer session notes |
| Live voice | The onboarding coach and the mock interviewer (4 session types) |
| Live logic computed from the data | Diagnosis findings, reply rates and charts, weekly progress, visa-fit labels, the offer check, the ticks on "What UK employers actually look for", board stage changes |
| Demo data (fictional) | Aditi's six-week history, the 24 applications, all jobs and companies, contacts, events, peers, match percentages, the buddy group, the first four Journal entries |
| Recorded only, nothing is sent | RSVP, "Request a chat", "Nudge", "Mark as sent" ("Copy message" does copy to the clipboard) |
| Not built | Accounts and login, real job feeds, saving data between restarts |

### How to talk about the demo parts

- Say it once, up front, in one sentence (step 0), then move on. The landing page footer also reads "Demo prototype. All people, companies and jobs shown are fictional."
- On a recorded-only button, say what the full product would do in a few words, for example "In the full product this sends the request. Here it records it."
- Call it sample data. Avoid the word fake, and do not apologise.
- If a "Demo fallback" badge shows, say "That's the offline fallback. Live, it does the same with your data." Then carry on. Hovering over the badge shows the reason.
- If voice fails, use the paste or sample buttons. Every voice step has one.

### If something goes wrong

| What you see | What to do |
|--------------|------------|
| Voice will not connect | Use the sample buttons: "Use a sample background" then "Build my profile" in onboarding, "Score a sample interview" in the Interview coach. |
| An AI call is slow | Keep talking about what it is doing. Calls take 2 to 7 seconds, and profile building and CV tailoring take the longest (6 to 7 s). Stay on the page, because leaving it drops the result. The backend waits up to 60 seconds for the model before it falls back. |
| "Demo fallback" badge | Say the fallback line above and keep going. |
| The page looks stale | Refresh the browser. The state is kept on the backend. On the onboarding screens a refresh returns you to step 1, so use "Skip to dashboard" if the profile is already built. |

### Likely questions

- Where would real jobs come from? In a real version, job board APIs plus the public gov.uk register of licensed sponsors. The prototype uses sample data.
- Is the match score real? The matching is designed around course, past work, target roles and visa route. In the prototype the scores are preset.
- What is live? Point at the "Live AI" badge. The AI calls and the voice calls are real.
- What happens to my data? In the prototype nothing is saved after a restart.

## 8. Phases

One phase doc each, in `docs/phases/` (`Phase-1.md`, `Phase-2.md`, `Phase-3.md`). Claude stops after each phase and waits for Dharan's testing.

- Phase 1: the full clickable app on seeded data, all live endpoints wired with fallbacks, and the agent setup script written. Verified in fallback mode without keys (every badge reads "Demo fallback"). Stop for testing and for you to fill `.env`.
- Phase 2: go live. Dharan fills `.env` and runs `setup_agents.py`. Verify each live feature end to end with real keys (badge reads "Live AI"), then tune prompts and latency. Stop for testing.
- Phase 3, if time: demo rehearsal polish, the reset flow, any visual fixes.

## 9. What Dharan must provide

- The AWS region where the Bedrock (Mantle) key works (`AWS_REGION`).
- The Bedrock (Mantle) API key (`BEDROCK_API_KEY`).
- The model ID from the Mantle console (`BEDROCK_MODEL_ID`).
- An ElevenLabs API key with Agents access (`ELEVENLABS_API_KEY`).

Secrets go only in `.env`, never in chat. Claude creates `.env.example` with these four placeholder names, and you fill `.env` yourself. `.env` sits in `backend/` next to `main.py`.

## 10. How to run

All paths are relative to the repo root (`CareerAI Agent`). Two terminals, backend and frontend.

Create the agents, once, after `.env` is filled (this writes the agent IDs into `.env`):

```
cd backend
.venv\Scripts\activate
python setup_agents.py
```

Backend:

```
cd backend
.venv\Scripts\activate
uvicorn main:app --reload --port 8000
```

Frontend, in a second terminal:

```
cd frontend
npm run dev
```

Open http://localhost:5173. Allow the microphone when the browser asks.

In PowerShell, if `.venv\Scripts\activate` does not activate the venv, use `.venv\Scripts\Activate.ps1` (the file exists in the venv).
