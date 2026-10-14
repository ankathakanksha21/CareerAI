---
name: careerai-step-5-interview-prep
description: Use when building, continuing or reviewing step 5 of the CareerAI roadmap - sourced company research, the interview prep pack, likely questions matched to the user's STAR stories, questions to ask the interviewer, and story coverage by competency
---

# Step 5: interview preparation

**Status:** Built on branch `step-5-interview-prep`, 14 October 2026; not yet merged. **Not finished:** the owner's hand checks. Design approved by the owner, 12 October 2026. **Depends on:** step 0. Better after step 1 (story bank) and step 4 (application stages). **Size:** medium to large, mostly because of the research.
**REQUIRED:** follow `careerai-building-a-step`.

## Where it stands (14 October 2026)

- Built and committed, tasks 1 to 13 of `docs/superpowers/plans/2026-10-14-step-5-interview-prep.md`. What it does and how is in `docs/ARCHITECTURE.md` section 23; what was verified and what was not is in section 24.
- Verified by the automated suite, by the real-model checks, by real research of one company through Tavily and its own website, and by running the Prep packs tab, story coverage and an application's Prepare button against the real backend and model as a temporary user whose data was never saved.
- A fresh review of the whole branch found nothing critical; every finding, the minor ones included, is fixed (ARCHITECTURE section 24).
- **Left for the owner:** the hand checks below with their own login, including printing a pack and a mock interview that uses one. The live Companies House key is now set.

## Changed at build time (14 October 2026)

Where what was built differs from the sections below, this table is what is true.

| Change | Why | Decided by |
|---|---|---|
| Research and the pack are two requests (`POST /api/companies/research`, then `POST /api/ai/prep`), not one `POST /api/ai/prep` | Each fits the 120-second limit; the page shows progress between them | Owner, with the plan |
| The company search is `POST /api/companies/search` with the name in the body | `CLAUDE.md`: what a user types never goes in an address | Owner, with the plan |
| Research is kept by Companies House number (or normalised name) together with the website's host | A wrong website typed by one user never changes another user's brief | Owner, with the plan |
| A pack keeps its own copy of the brief | Another user refreshing the company never changes it | Owner, with the plan |
| `DELETE /api/prep/{id}` added | A user can remove a pack | Owner, with the plan |
| Reading, editing and deleting a stored pack work without the research settings; only search, research, building and refresh need them | A user's own data never depends on an outside service being set up | Build-time ruling |
| The pitch is three paragraphs of 110 to 260 words (planned 150 to 260), and the page says "About a minute to 90 seconds spoken" | The real model writes about 120 to 140 words even when asked for 180 to 230 | Build-time ruling |
| A news or competitor result is used only if it names the company (the first word of its name) | The browser check showed results about another company reaching the brief | Build-time ruling |
| A story the model gives no competencies takes its one-word label when that is exactly one of the eight | The same rule the migration uses for existing stories; no extra call | Build-time ruling |
| The pitch may use figures from the company facts as well as the user's records and the advert | The real model's pitch quoted a company figure ("140 shops") and was refused | Build-time ruling |
| Every research counts against the daily limit, Refresh and a retry after a failure included (the plan let the same company again within 10 minutes go free) | The free window let repeated or parallel research run past the limit | Final review |
| Research is kept by the Companies House number together with the name searched for, and the website | A name typed with a real company number changed every user's research for that company | Final review |
| Research that missed a source for a passing reason is shared for an hour, not 14 days | One timeout for one user was everyone's brief for a fortnight | Final review |
| A pack is saved part by part, and a rebuild re-reads it under a lock; an emptied pitch is not the user's own | Edits were lost between two quick saves or during a rebuild | Final review |
| The right-to-work line is filled when the pack is read, while it is empty and the user has not written or cleared one | Visa details added after the pack was built did not show | Final review |
| Form controls, not forms, are left out of a page; a figure written in words for ten or more must be in its page | Older public-sector sites read as empty; "five thousand" was not checked | Final review |

## Goal

When a user has an interview, the app gives them one page to prepare from: who the company is, with a source for every statement; the questions they are likely to be asked, each matched to one of their own stories; good questions to ask back; and a mock interview that uses all of it.

Today the mock interview knows only the job title and summary, and there is no company research at all.

## Decisions already made (do not re-ask)

| Decision | Detail | Decided by |
|---|---|---|
| Research sources | The employer's own website, the official Companies House record, and a web search service for recent news and competitors | Owner, 12 Oct 2026 |
| Daily drill | Not included. Voice practice stays as full mock interviews | Owner, 12 Oct 2026 |
| Nothing from the model's memory | Every statement in a company brief must come from text the app fetched, and shows its source. A statement with no source is dropped | Recommended; approved 12 Oct 2026 |
| The user confirms the company | Companies House often returns several similar names. The user picks the right one, or says none match | Recommended; approved 12 Oct 2026 |
| Research is shared, advice is personal | Facts about a company are stored once and reused for every user for 14 days. "Why this company, for you" and the question-to-story matching are per user | Recommended; approved 12 Oct 2026 |
| Research limit | 5 companies per user per day (`DAILY_RESEARCH_LIMIT`), separate from the AI limit, because searches cost money | Recommended; approved 12 Oct 2026 |
| Right-to-work answer | The pack helps the user phrase a one-line answer from their own visa type and end date. It states facts only and carries "not immigration advice" | Recommended; approved 12 Oct 2026 |
| Export | The pack prints from the browser. No Word or PDF export | Recommended; approved 12 Oct 2026 |
| Search service | Tavily: 1,000 free credits a month with no card, 2 credits per newly researched company (news and competitors), then $0.008 a credit. News search with publish dates. Its terms do not forbid keeping results, so the 14-day shared cache works. Brave was ruled out because its terms forbid storing results beyond transient use; Serper because its terms are vague and its dates less reliable. Expected monthly cost now: nothing | Recommended; approved 14 Oct 2026 |
| Right-to-work wording | One spoken line from the visa type and end date. Graduate: "I have the right to work in the UK on a Graduate visa until 30 January 2027." Student: "I am in the UK on a Student visa until 30 January 2027." Under it: "Employers often ask next whether you will need sponsorship. That answer is yours to add. This is not immigration advice." Editable, saved with the pack | Recommended; approved 14 Oct 2026 |
| How stories get competencies | New stories are tagged in the same call that writes them, at no extra cost. Existing stories get a "Tag my stories" button on the coverage grid (one AI action). The user can tick or untick competencies when editing a story | Recommended; approved 14 Oct 2026 |
| Where packs live | A fourth tab, "Prep packs", in Interview coach. It lists the user's packs; "Prepare" (on Interview coach and on applications at phone screen or interview) opens the company step there | Recommended; approved 14 Oct 2026 |

## In scope

1. Company lookup and confirmation.
2. Fetching the employer's site safely, the Companies House record, and news and competitor search results.
3. A sourced company brief.
4. The prep pack for a saved job or an application.
5. Likely questions matched to the user's stories; questions to ask.
6. Story coverage by competency.
7. The mock interviewer using the pack.

## Out of scope

A daily drill; longer or multi-interviewer mock interviews; salary negotiation; assessment-centre or psychometric test practice; any research from the AI's own knowledge.

## What the user sees

**Where it starts.** A "Prepare" button on Interview coach next to the job picker, and on any application at the phone screen or interview stage.

**Step 1: confirm the company.** The app shows up to five Companies House matches for the employer name (name, registered town, status, year incorporated) and a box for the website address. Choices: "This one", "None of these", and "It is not a UK company". The pack still works without a Companies House record and says so.

**Step 2: the prep pack**, one page:

| Section | Content |
|---|---|
| Company brief | What they do; size and age; values in their own words (quoted); products or projects; news from the last 12 months, each with its date; competitors, each attributed ("according to <source>"). Every line ends with a source link. A line at the top: "Researched on <date>" and a Refresh button |
| Why this company, for you | Three talking points, each joining a fact from the brief to one of the user's achievements |
| Tell me about yourself | A 90-second answer drafted from the profile and this job. Editable |
| Likely questions | Eight, for this role: from what the advert asks for, plus standard UK competency questions. Each shows "Use your story: <title>" or "No story yet" with a button to write one |
| Questions to ask them | Five suggestions drawn from the brief. The user ticks two or three. None that the company's own site already answers |
| Your right-to-work answer | One editable line from the user's own visa facts, for the HR screen |
| On the day | The UK norms already in the app, plus a short checklist for the interview type |

**Story coverage** (Interview coach → STAR stories): a grid of the common UK competencies (teamwork, leadership, problem solving, communication, handling a setback, initiative, influencing, working to deadlines) against the user's stories, with "No story yet" where there is a gap.

**Mock interview.** When a pack exists for the chosen job, the interviewer is given the company summary and asks from the pack's likely questions. Feedback works as now.

## Data changes (migration `00N_interview_prep`)

| Table | Per user? | Holds |
|---|---|---|
| `companies` | Shared | Name, Companies House number, website, `facts jsonb` (each with source address and date), `researched_at` |
| `prep_packs` | Per user | `saved_job_id` or `application_id`, `company_id`, `content jsonb` (talking points, pitch, likely questions with story ids, questions to ask with ticks, right-to-work line), `updated_at` |
| `stories` | Per user | Add `competencies text[]` so one story can cover more than one |
| `usage_events` | Per user | Allow `kind` value `research` |

`companies` is public data with no `user_id`, like the job listings in step 2. It still has row-level security on and no browser privileges.

## API

| Route | Purpose |
|---|---|
| `GET /api/companies/search?name=` | Companies House matches |
| `POST /api/ai/prep` | `{job_id or application_id, company_number?, website?}` → the pack. One research use (unless the company is cached) and one AI action |
| `GET /api/prep/{id}`, `PATCH /api/prep/{id}` | Read; save edits to the pitch, the ticked questions, the right-to-work line |
| `POST /api/prep/{id}/refresh` | Research again |

## How the research works

1. **Companies House:** search by name; after the user confirms, read the company profile.
2. **Website:** fetch the home page and up to five pages whose links look like about, careers, values, news or press. Text only.
3. **Search:** two queries, one for news in the last 12 months and one for competitors. Keep the title, snippet, address and date of each result.
4. **Number the sources.** Every fetched passage gets a number.
5. **Write the brief.** The model receives only the numbered passages and must attach a source number to every statement. Statements with no valid number are dropped. Quoted values are checked word for word against the page text.
6. **Store** the facts on the shared company record with their source addresses and dates.

**Fetching safely.** The server fetches addresses that come from users and search results, so:

- Only `http` and `https`, only public hosts. Private, loopback and link-local addresses are refused, including after redirects.
- The site's `robots.txt` is respected.
- A size limit, a time limit and a page limit per company.
- An honest user-agent string naming the app.

## Outside services and settings

| Service | Settings | Notes |
|---|---|---|
| Companies House API | `COMPANIES_HOUSE_API_KEY` | Free, official |
| Web search | `SEARCH_PROVIDER` (`tavily`), `SEARCH_API_KEY` | Tavily, chosen 14 Oct 2026. `POST https://api.tavily.com/search`, key as a Bearer token; `topic=news` returns `published_date` |
| Limit | `DAILY_RESEARCH_LIMIT` (default 5) | |

## AI tasks

| Task | Notes |
|---|---|
| Company brief | Numbered sources in, cited statements out |
| Prep pack | From the brief, the job description, the user's achievements and stories: talking points, the pitch, likely questions with a story id each, questions to ask. A story id that is not the user's is treated as "no story yet" |
| Story competencies | Tags each story with one or more of the eight competencies |

## Behaviours that must have tests

In addition to the standing list in `careerai-building-a-step`:

- A statement with no source number, or a number that does not exist, never reaches the brief.
- A quoted value that is not in the fetched page is dropped.
- News older than 12 months is left out; a result with no date is shown as undated, not as recent.
- Addresses that resolve to private, loopback or link-local ranges are refused, including when a public address redirects to one.
- A page over the size limit, a slow site, a site that forbids fetching in `robots.txt`, and a non-HTML response are each handled without failing the whole pack.
- No Companies House match, "not a UK company", a dissolved company, and several identical names all produce a usable flow.
- The search service failing produces a brief from the remaining sources with a notice saying what is missing.
- With no sources at all, the brief says nothing could be found. It is never filled from the model.
- A second user researching the same company within 14 days makes no new search or fetch, but gets their own talking points.
- A likely question is matched only to a story the user owns.
- The research limit counts once per newly researched company and not for a cached one.
- No API key appears in a response, a stored record or a log line.
- User B cannot read or change user A's pack.

## Check by hand

1. Prepare for a well-known UK employer: follow five source links and confirm each supports its statement.
2. Prepare for a small company with a thin website: the brief is short and honest.
3. Prepare for an employer that is not on Companies House (a university or NHS trust): the pack still builds.
4. Check the news dates are real and within the year.
5. Likely questions point to the right stories; a competency with no story shows the gap.
6. Run a mock interview with a pack: the interviewer asks company-specific questions.
7. Print the pack.

## Task outline

1. Choose the search service with the owner; confirm all three sources' terms and limits.
2. Migration; the research limit.
3. Companies House client and the confirm-company flow.
4. The safe fetcher with its tests.
5. The search client.
6. Numbered-source brief with citation checks; the shared company cache.
7. The prep pack task and routes.
8. The pack page and the Prepare entry points.
9. Story competencies and the coverage grid.
10. Passing the pack to the mock interviewer; live checks, hand checks, documentation; privacy page update (company names are sent to the search service).

## Done when

For a real upcoming interview, a user can produce a pack in under two minutes in which every company statement can be clicked through to its source, every likely question points to one of their own stories or a named gap, and the mock interview reflects it.

## Verify at build time

- **Search service:** compare current options on price, free allowance, freshness of news, and terms on storing snippets. Agree the choice and expected monthly cost with the owner before writing code.
- **Companies House API:** authentication, endpoints for search and company profile, and rate limits.
- **Time limit:** research may not fit in one 60-second request on Vercel. If not, split it into steps the page calls in turn, with visible progress.
- **Mock interviewer:** how much text the ElevenLabs dynamic variables can carry, and re-run `setup_agents.py` after changing the prompt.
- **Right-to-work wording:** agree it with the owner.
