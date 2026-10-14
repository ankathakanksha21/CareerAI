# UK Career Navigator: scope, architecture and handover

Last updated: 14 October 2026. This is the living document for the project. It is updated at the end of every build step.

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
| 1 | Deeper onboarding: CV upload, GitHub import, editing achievements, education and work history, story bank | 0 | Built and merged into `main`. The owner's hand checks with a real CV and account are left (section 18) | `careerai-step-1-deeper-onboarding` |
| 2 | Real jobs from Reed, fit scoring, sponsor register, visa salary facts | 0 | Built and merged into `main`. Some hand checks are left (section 16) | `careerai-step-2-real-jobs` |
| 3 | Full UK CV: all sections, editing in the app, Word and PDF | 1 | Built and merged into `main`. The owner's hand checks are left (section 20) | `careerai-step-3-full-uk-cv` |
| 4 | Tracker detail, follow-ups, a lesson from each rejection, weekly goals, streaks, weekly plan | 0 | Built on branch `step-4-tracker-and-habits`. The owner's hand checks are left (section 22) | `careerai-step-4-tracker-and-habits` |
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
 │                                 ├─ makes CV and cover letter files in memory   → Word and PDF, on download, never stored
 │                                 ├─ AWS Bedrock, Mantle endpoint                ← the language model
 │                                 ├─ ElevenLabs API                              ← mints voice session tokens
 │                                 ├─ Reed API                                    ← job adverts (titles and locations sent, nothing personal)
 │                                 ├─ GitHub API                                  ← public repositories and READMEs, by a username the user types
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
| Reading CV files | `pypdf` for PDF, the standard library for Word (.docx), both in memory | One small dependency. A Word file is a zip of XML, and reading it directly reaches the tables and text boxes CV templates are built from |
| Writing CV files | `python-docx` for Word and `fpdf2` for PDF, both in memory, drawn from one list of print blocks. The PDF embeds Liberation Sans (bundled in `backend/fonts`, SIL Open Font Licence 1.1) | Both are pure Python apart from two compiled packages that ship ready built. Liberation Sans has exactly Arial's letter widths, so Word (Arial) and the PDF break lines alike |
| GitHub projects | GitHub's public REST API, no login | Nothing to connect; public data only |
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
| An uploaded CV travels as the raw request body and is read in memory | The file is never written anywhere, which a form upload cannot promise (it spools to a temporary file) | A 4 MB limit, set by Vercel's 4.5 MB cap on a request | Files need to be bigger |
| One import is two model calls side by side: achievements, and CV facts | About 14 seconds instead of 30 | If only the facts call fails the achievements are kept and the page says so | The model gets fast enough for one call |
| Found jobs, courses, skills and languages are proposals, saved only when the user confirms them | Nothing the AI read is on a profile unchecked | Proposals live in the browser: leaving the page loses them, and the same CV must be uploaded again | Users lose proposals often |
| A found job or course that repeats a saved one fills in its blanks | The current course is in every CV; no duplicates, and its start month and grade arrive without typing | A wrong match would add a date to the wrong entry; the user sees what is added and can untick it | – |
| The current course is a real education row made from "Your details" | Step 3 reads one list | Its university, name and end month can only be changed in "Your details" | – |
| The quote on an achievement cannot be edited | "From your CV" is never shown beside words the CV did not have | A user who dislikes a quote must delete the achievement | – |
| Names the model returns are checked against the text; a rewrite may not carry a number that is in neither the achievement nor the user's note | Deterministic checks behind "never invent employers or numbers" | A name the model tidied heavily can be dropped; an unusual wording of a number can need a retry | Hand checks show either is too strict |
| GitHub projects are imported by username, with no login | Nothing to connect | Nothing proves the account is the user's own | Abuse is seen |
| A typed GitHub username travels in a request body, and `httpx` request logging is off | It never sits in an address or a server log | The listing is a POST | – |
| A CV's facts are copies of the stored records; the model writes wording only | Every employer, title, date, course, grade and contact detail on a CV is the user's own, whatever the model returned | A fact cannot be typed over on a CV: it is corrected on the Profile and brought in with "Update from profile" | Users want one CV to differ from their profile |
| A reworded bullet is kept only if it has every number of the stored bullet and no number the achievement does not hold | A figure on a CV is never altered or invented | A good rewording that drops a number is discarded and the stored bullet used | Real builds show too many bullets falling back |
| A tailored CV is two model calls side by side (the body; keywords, gaps and letter), one AI action | About half the wait of one call | The letter is written without seeing which bullets were picked. If either call fails nothing is saved | The model gets fast enough for one call |
| Keyword coverage is worked out in code, by exact wording, after every edit | "Covered" is always true of the CV as it will print, and matches how screening software reads | "Stakeholder management" is not covered by "managed stakeholders" | Users find it too literal |
| One list of print blocks, drawn by a Word writer and a PDF writer | The two files always say the same thing in the same order; a test compares them | The layout is limited to what both can draw: one column, no graphics | A second layout is wanted |
| The page count is the generated PDF's, stored with each version and recounted on every edit | A real count, not an estimate | Word lays the same text out itself and can differ by a line at a page boundary (section 19) | – |
| The PDF's font is bundled, and a character it cannot draw prints as "?" and is named on the page first | Accented Latin, Vietnamese, Greek and Cyrillic work, with Arial's widths | No rupee sign, Arabic, Hindi, Chinese, Japanese, Korean or Thai in the PDF; the Word file shows them | Users need another script in a PDF |
| A version an application points at never changes: an edit is saved as a new version | Reply rates by CV version stay true | Versions accumulate | – |
| Every edit to a CV is saved as it is made | Nothing is lost by leaving the page, and a download always matches the screen | One small request per edit, each recounting the pages | – |
| CV and letter files are made when downloaded and never stored | No personal files at rest; nothing to clean up | A file is made again each time (about 0.15 seconds) | – |
| A CV made before step 3 can be read, rebuilt or deleted, not edited or downloaded | A half CV with no education, dates or contact details is never sent out as a file | Its job must still be saved to rebuild it | – |
| Streaks, milestones reached, follow-ups due and the weekly plan are worked out on every read and never stored | They cannot drift from what the user did | A little work on every page load | A user has years of history |
| Only an application with a CV version recorded counts toward the weekly goal | Rewards the tailored application the product is built around | An application logged without its CV counts only once the CV is added | Users find it too strict |
| The first goal a user sets applies this week; any later change from the next Monday | A new user is not judged by defaults they never chose, and a week in progress can never be made easier | A user who lowers a goal waits until Monday | – |
| Where a rejection ended sets the stage (CV stage or phone screen: Rejected; interview or final: Rejected after interview), and a rejection after a phone screen counts as a reply | The stage list and the board stay as they were | One more rule in the reply count | – |
| A lesson is written when either the CV sent or the job description was recorded; with neither, no AI call | Applications tracked from Jobs often have the advert but no CV; one side is enough to say something useful | A lesson from one side is thinner, and about a CV it never saw it can only guess | Users find those lessons vague |
| A lesson must be worded as a possibility, may not claim feedback that was not entered, may quote only the inputs, and is written to "you"; checked in code | A guess is never presented as the reason someone was turned down | An honest but unusual wording costs a retry | – |
| A follow-up draft is written without the user's name; code adds "Dear ..." and "Kind regards" with their name | Nothing personal in the prompt beyond the contact's name | The model cannot choose another sign-off | – |
| Stage history starts with step 4 | Only real data | Older applications show no history | – |
| An application at No reply asks for no follow-up | The user has said they have stopped waiting | A reminder set on it is not listed on Home | Users ask for it |

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
- A job or course may have no dates: the AI leaves a date empty rather than guess a month, and the page then shows "Add dates".
- An achievement is linked to one job or one course, never both. Deleting the job or course keeps the achievement and clears the link.
- "Add a number" is shown when neither the bullet nor its result holds a digit.
- A repository already imported is skipped, and one with no README and no description is never sent to the model.
- The pitch is rewritten only by an import that saved new achievements.
- On a new CV education comes before work experience when the user is still studying, or graduated at most 24 months ago, and has worked for under 24 months. The user can reorder the sections.
- At most five bullets show under a job and four projects show on a new CV. Any more the model picked are kept, hidden, for the user to bring back.
- A job with no bullet picked still prints, with its title and dates, so the history shows no gap.
- An achievement linked to no job prints under Projects: GitHub projects with their repository address, course projects with their institution.
- The right-to-work line is off by default. Its suggested wording gives the visa held and the day it ends, and says nothing about what comes after.
- A cover letter is dated the day it is downloaded. To a named person it ends "Yours sincerely"; to "Hiring Manager", "Yours faithfully".
- File names are plain ASCII ("José Nuñez" gives `Jose-Nunez-CV-Acme.pdf`), because employers' upload forms often mishandle anything else.
- A CV version's number is never used twice, even after a version is deleted.
- The model is never sent the user's name, phone number, email, town or LinkedIn address when a CV is written.
- A new application gets a follow-up date a week after the date applied. Correcting the date applied moves it, until the user has followed up or chosen a date. "Mark as followed up" sets the next one a week after the day it is pressed.
- An application still at Applied with no stage change for 21 days is listed under Follow-ups due with "Move to No reply". Logging an application late is not a change: the days count from the date applied.
- Moving a card out of Rejected clears where it ended, the feedback and the lesson. Moving it between the two rejected stages keeps them.
- Three lessons that point to the same page become a finding under What to fix.
- All milestones not yet shown appear in one banner at the top of Home and are marked seen as it appears. Deleting an application can take away a milestone not yet shown; a milestone already shown never comes back.
- The weekly plan holds at most five tasks, never one for a page this build lacks: no jobs task without a Reed key, no task for a finding that links nowhere.

## 6. Code map

```
backend/
  main.py          routes only: who is calling, validate input, call modules, return JSON
  auth.py          access token → User. FastAPI dependency current_user
  db.py            connection helper for the pooled Postgres connection
  repo.py          ALL SQL. Every function takes (conn, user_id, ...), except those for the shared job and sponsor tables
  jobs.py          which searches to run, de-duplication, shortlist, fit maths, parallel calls to Reed and the model
  cvfile.py        a PDF or Word CV to plain text, in memory, with every refusal and its message
  cv.py            the CV document: section order, assembling from records, applying an edit, keyword coverage. Pure functions
  cvprint.py       a CV or cover letter as a list of print blocks; the layout both writers share; file names
  cvword.py        print blocks to a Word file, in memory
  cvpdf.py         print blocks to a PDF and its page count, in memory; which characters the font cannot draw
  cvbuild.py       one CV from start to finish: the model calls a build takes, an edit applied, the file a version downloads as
  fonts/           Liberation Sans Regular and Bold with their licence, embedded in every PDF
  github.py        GitHub client: a user's public repositories, one README. Everything GitHub-specific
  intake.py        one import: both extraction calls side by side, where each achievement happened, what to propose
  stories.py       the story bank: which achievements get a story, written in batches
  parallel.py      together(): several outside calls at once
  reed.py          Reed client: search, one advert in full, HTML to text. Everything Reed-specific
  sponsors.py      the gov.uk register: find, download, check, load; employer name matching
  visa.py          salary facts from data/visa_rules.json
  limits.py        per-user daily caps
  analytics.py     tracker stats, diagnosis rules, getting-started checklist. Pure functions
  habits.py        weeks, goals, the weekly streak, follow-ups due, milestones, the weekly plan. Pure functions
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
  scripts/cv_check.py     what one CV file reads as: size, whether it was cut, its first lines. Local only
  scripts/page_check.py   sample CVs of growing length: the PDF's page count beside Word's own. Windows with Word only
  tests/           pytest suite
frontend/src/
  App.jsx          session gate and app shell
  supabase.js      Supabase client built from /api/config
  api.js           fetch wrapper: bearer token, one refresh-and-retry on 401; download() for files that need the token
  cv.js            a CV document on screen: dates and contact line as the files word them, small edits to send back
  ui.jsx           shared pieces: menu, FamilyCard, ErrorRetry, Empty, date helpers
  VoiceAgent.jsx   one ElevenLabs call with the live transcript panel
  components/      DetailsForm, BackgroundInput (coach, CV file, pasted text or GitHub), GitHubImport,
                   FoundFacts ("We also found": tick and confirm), History (work history, education, skills),
                   AchievementCard (edit, link, improve), Jobs (picker and paste-a-job),
                   Visa (sponsor line, salary facts, sources line),
                   CvEditor (one CV: change, save in order), CvSheet (the CV as it prints: edit, reorder, hide, restore),
                   CvSide (pages, keywords, downloads, letter), OldCv (a version from before step 3), EditableText,
                   ContactForm (contact details; certifications, awards and volunteering),
                   ApplicationPanel (every field of an application, its history, follow-up and lesson),
                   RejectQuestions (where a rejection ended, feedback, the lesson), FollowUps, ThisWeek (goals, streak), Plan, Milestones
  tracker.js       the tracker's stage words and small rules, shared by Applications and Home
  pages/           Landing, Auth, Privacy, Onboarding, Home, Profile, Pathways, Jobs, Resume,
                   Interview, Applications, Journal, Account
app.py             Vercel entry point: the API plus the built frontend
```

## 7. Data model

All tables are in the `public` schema. Every row of a per-user table has `user_id` referencing `auth.users` with `on delete cascade`, so deleting a login removes all of that person's data. Five tables added in step 2 hold public data shared by everyone and have no `user_id`; they are marked below. Row-level security is on with no policies, and the browser-facing roles (`anon`, `authenticated`) have no privileges.

| Table | Holds |
|---|---|
| `profiles` | One row per user: name, university, course, graduation month, visa type, visa end date, preferred locations, pitch, skills, spoken languages with a level, GitHub username, and for the CV a phone number, town or city, LinkedIn address and lines of certifications, awards and volunteering, and which milestones have been shown |
| `achievements` | Their own words (`raw`), the UK CV bullet (`uk_version`), skills, outcome, scale, context note, source (voice, paste, cv or github), the job or course it happened in, and for a GitHub project its repository link |
| `work_history` | Jobs, internships and placements: employer, job title, location, country, start and end month, whether it is current, one line on what the employer does, where the entry came from |
| `education` | Courses: institution, qualification, subject, start and end month, grade, country. The current course is made from "Your details" and marked `from_details` |
| `role_families` | AI-suggested families: fit, estimated overlap, UK titles, requirements shown or missing, targeted or not. Unique per user by name, ignoring case |
| `saved_jobs` | Jobs the user pasted: title, company, description, AI summary, keywords, matched role family |
| `cv_versions` | Each CV in full as one document, named "<title>, <company> vN" or "Base CV vN": whether it is a base or a tailored CV, its page count, when it was last edited, who its letter is to. A version made before step 3 is marked format 1 and holds only a paragraph, bullets and a letter |
| `stories` | STAR stories, linked to their achievement |
| `applications` | Tracker rows: company, role, family, CV version, source, stage, applied and posted dates, link, the contact's name and how to reach them, notes, sponsor licence, the next follow-up date and when the user last followed up, and for a rejection where it ended, any feedback and the lesson |
| `application_events` | One row per stage change of an application, with when; the first records its creation. Deleted with the application |
| `weekly_goals` | The user's weekly goals (applications with a CV, mock interviews), each applying from a Monday. No row means the defaults, 5 and 2 |
| `journal_entries` | Coach calls, mock interviews and imports (a CV upload, a GitHub import): summary, points, actions, scores, and the transcript or the text that was read |
| `usage_events` | One row per AI action or voice session: daily limits now, streaks later |
| `job_listings` (shared) | One row per advert: source and its id, title, employer, who really posted it (employer, agency, or training for an advert that sells a course), location, salary and whether it is annual, description and whether it is the full text, link, posting date, and what the register says about the employer |
| `job_searches`, `job_search_results` (shared) | The search cache: each search anyone has run, when, and the adverts it last found |
| `sponsors` (shared) | The register's Skilled Worker entries: registered name, normalised name, town, county, rating. A trading name gets its own row |
| `reference_meta` (shared) | When the register was last loaded and the date gov.uk published that file |
| `job_matches` | One user's view of one advert: role family, fit percentage and label, what they show and lack, new, seen, saved or hidden |
| `schema_migrations` | Which migration files have been applied |

Schema changes are numbered SQL files in `backend/migrations/`, applied with `python migrate.py`. Applied so far: `001_initial`, `002_journal_transcript`, `003_jobs` (which also adds `listing_id` and `posted_on` to `saved_jobs`, and `include_senior` to `profiles`), `004_training_adverts`, `005_profile_depth` (which also copies each existing user's current course into `education`), `006_full_cv`, `007_tracker_habits` (which also gives each open application without one a follow-up date a week after it was sent).

Adverts older than 30 days are deleted on each refresh. A saved job is a copy, so it stays.

A reference from one row to another (for example an application's CV version) is stored only if the target belongs to the same user; otherwise it is saved as null.

**A CV document** (`cv_versions.content`, format 2) holds a copy of the contact line, the job's title and company, the profile paragraph, the order of the five sections, and then each section: courses and jobs as the id of the stored record plus a copy of its facts made when the CV was built, bullets as wording with the id of the achievement it came from and whether it is hidden, projects, skills in three groups, additional lines, the right-to-work line and whether it is shown, the three paragraphs of the cover letter, the job's keywords in their three groups, and the gaps. Because the facts are copies, a later change to the profile never alters a CV that was sent.

## 8. API

`GET /api/config` is public and returns only values safe to expose. Every other route needs a valid token (401 without one) and touches only the caller's rows; the one exception is the register reload, which needs the scheduler's secret instead. Ids are UUIDs: a malformed id answers 422, an unknown or foreign one 404.

| Route | Purpose |
|---|---|
| `GET /api/state` | Everything the pages need for the signed-in user, plus stats, next steps, guidance content and today's usage; each application's stage history; `habits` (this week against its goals, the streak and best streak, milestones reached and not yet shown), `plan` (this week's tasks) and `follow_ups_due` |
| `PUT /api/profile` | Save "Your details" |
| `DELETE /api/account` | Delete the login and all data |
| `PATCH`, `DELETE /api/achievements/{id}` | Edit any field but the quote, including the job or course it happened in; remove an achievement |
| `POST`, `PATCH`, `DELETE /api/work-history[/{id}]`, `/api/education[/{id}]` | Jobs and courses |
| `PUT /api/profile/skills` | Replace skills and spoken languages |
| `PUT /api/profile/contact` | Phone, town or city and LinkedIn address for the CV. A LinkedIn address must be on linkedin.com |
| `PUT /api/profile/additional` | Up to 12 lines of certifications, awards and volunteering |
| `PATCH /api/cv-versions/{id}` | Save an edit: wording, order and what is hidden, never a fact. With `refresh_facts`, copy the facts from the profile again. A version sent with an application is left alone and the edit saved as a new one |
| `DELETE /api/cv-versions/{id}` | Remove a version; 409 while an application points at it |
| `GET /api/cv-versions/{id}/download?format=docx\|pdf&part=cv\|letter` | The CV or its letter as a file, made now and not kept |
| `POST /api/profile/facts` | Save the jobs, courses, skills and languages the user ticked after an import, all or nothing, and link the new achievements |
| `PATCH`, `DELETE /api/stories/{id}` | Edit or remove a STAR story |
| `POST /api/github/repos` | A GitHub user's own public repositories, each marked if already imported. The username travels in the body |
| `POST /api/families/{id}/target` | Tick or untick a role family |
| `POST /api/jobs`, `DELETE /api/jobs/{id}` | Add a pasted job (with an AI summary), remove a saved job |
| `GET /api/jobs` | The user's matched adverts, whether a search is due, the register's date and the visa figures. Changes nothing |
| `POST /api/jobs/refresh` | Run the searches that are due, match the adverts, score up to 15. One AI action when anything is scored |
| `POST /api/jobs/seen` | Mark new matches as seen |
| `PUT /api/jobs/preferences` | "Include senior roles" |
| `POST /api/jobs/{match_id}/save`, `/hide`, `/track` | Copy the advert into saved jobs; dismiss it; save it and log an application with its link, posting date and sponsor status |
| `POST /api/visa-facts` | The offer check: a salary beside the published figures, and a register lookup |
| `GET /api/internal/refresh-sponsors` | Reload the register. Not for users: needs `Authorization: Bearer <CRON_SECRET>` |
| `POST`, `PATCH`, `DELETE /api/applications[/{id}]` | Tracker. A change of stage is added to the application's history |
| `POST /api/applications/{id}/reject` | Where it ended and any feedback; sets the stage and returns one lesson, or a notice when neither a CV nor a job description was recorded. The rejection is saved before the model is called. One AI action when there is something to compare |
| `POST /api/ai/applications/{id}/follow-up` | A follow-up message to copy. One AI action. 400 once the application has ended |
| `POST /api/applications/{id}/followed-up` | Followed up today: the next follow-up is due in a week |
| `PUT /api/profile/goals` | Weekly goals: 1 to 30 applications, 0 to 14 mock interviews. The first applies this week, later ones from next Monday |
| `POST /api/milestones/seen` | Milestones the banner has shown |
| `GET /api/journal/{id}/transcript` | What was said in that session |
| `POST /api/ai/achievements` | Transcript or pasted text → achievements and pitch, plus proposed jobs, courses, skills and languages |
| `POST /api/ai/achievements/upload` | A PDF or Word CV as the raw body → the same. The file is read and dropped |
| `POST /api/ai/achievements/github` | Up to 5 repositories → project achievements, each with its link |
| `POST /api/ai/achievements/{id}/improve` | A one-line note → the bullet, result and scale rewritten and saved; the answer carries what they replaced |
| `POST /api/ai/stories/bank` | STAR stories for the strongest achievements without one, up to 8 stories in all |
| `POST /api/ai/families` | Achievements → role families |
| `POST /api/ai/cv` | A saved job → a full CV and cover letter; no job → a base CV. Saved as a new version. One AI action |
| `POST /api/ai/star` | Achievement → STAR story |
| `POST /api/ai/interview-feedback` | Mock interview transcript → scores and feedback |
| `POST /api/ai/tone` | Decode a British phrase, or rewrite a sentence in UK tone |
| `POST /api/ai/diagnosis` | Weekly review from tracker stats |
| `GET /api/voice/token` | Start a voice session (counts against the daily limit) |
| `GET /api/voice/transcript/{conversation_id}` | Fallback transcript, only for the session's owner |

Error responses always carry a plain `detail` message the UI shows as-is: 409 a CV that is attached to an application, 413 a file over 4 MB, 422 invalid input or a file that cannot be read, 429 daily limit ("You've reached today's limit. It resets at midnight."), 502 AI or voice failure, 503 service not configured or database unreachable.

## 9. AI layer

- **One prompt in, JSON out.** `ai.py` has one function per task. Replies are coerced to the expected shape, and values are normalised (fit labels, overlap clamped to 0–100, scores to 0–5).
- **Real result or an error.** A task returns the model's own output or raises. One automatic retry on malformed output or a network error. Nothing is saved from a failed call.
- **Fallback model.** If the main model is refused (403 or 404) and `BEDROCK_FALLBACK_MODEL_ID` is set, the request is tried once there.
- **Reasoning text.** The current model can emit a `<think>` block; it is removed before parsing.
- **Stray characters.** The model sometimes adds an extra bracket or quote after a complete answer (3 of 12 real calls on 12 October 2026). The parser reads the first complete JSON value and ignores what follows.
- **Job fit.** The model lists what each advert asks for and names the achievement that shows each requirement. A requirement counts only if that achievement is really one of the user's. Only achievements are sent, nothing else about the person.
- **No invention.** The base prompt forbids inventing employers, numbers or achievements. On top of that, every quote shown as "You said" is checked against the user's own lines of the transcript (`ai.verbatim`): kept if they said exactly that, replaced by their closest sentence if the model paraphrased, dropped otherwise.
- **Quotes by source.** A quote is checked against the text it claims to come from: the user's own lines of a call, the whole of a CV (where a line beginning "Coach:" is still theirs, and a sentence wrapped across PDF lines is read as one), or that repository's own README and description. The label says which: "You said", "You wrote", "From your CV", "From your repository".
- **Checks in code behind the prompt.** An employer, institution, skill or language is kept only if the text names it. A date is kept only if it is a real month. A rewritten bullet may not carry a number that is in neither the achievement nor the user's note. The same achievement is not saved twice.
- **Several calls for one action.** An import asks for achievements and for CV facts at the same time; the story bank writes in batches of four. Each counts as one AI action.
- **A CV: wording only.** `build_cv` returns a profile paragraph, bullets each naming one of the user's achievements, and the user's own skills in two groups. `job_letter` returns the advert's main terms, gaps and the three paragraphs of a letter. Neither is asked for, or trusted with, a fact: employers, dates, courses and grades are copied from the records in code. A bullet for an id that is not the user's is dropped; a reworded bullet that lost, changed or gained a number is replaced by the stored one; a skill that is not the user's is dropped; a keyword that is not in the advert is dropped; a paragraph or letter with a number found nowhere in the candidate's facts is refused and asked for once more.
- **A lesson and a follow-up.** `rejection_lesson` is given the CV as sent (without its contact line), the job description, where the process ended and any feedback, and says which of them were not recorded. Its reason must be worded as a possibility, it may not claim feedback the user did not enter, a quoted phrase must be in the inputs, and it is written to "you". `follow_up` is given only the role, the company, the date applied and the contact's name; it writes a subject and a body of at most 80 words with no number that is not in those details, and code adds the greeting and the user's own sign-off.
- **Privacy in logs.** Failures log the task name and the error type only, never prompts or replies. `httpx` request lines are off, because an address can hold what a user typed.
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
| Uploaded files | Read as the raw request body, in memory, at most 4 MB, and dropped. Never written to disk or the database: only the text read from them is kept. The type is decided from the file's first bytes, never its name. Password-protected, damaged and oversized-when-unpacked files are refused before anything reaches the model |
| Contact details | Phone number, town and LinkedIn address are stored for the CV's contact line and printed there. They, the user's name and their email are never sent to the model |
| People at employers | An application can hold a contact's name and how to reach them. Only the name is sent to the model, for a follow-up draft. Nothing is ever sent to an employer for the user |
| Generated files | A CV or cover letter is made in memory for one download, sent with `Cache-Control: no-store`, and not kept anywhere. Its file name is plain ASCII built from the user's name and the company |
| What GitHub is told | A username the user typed, to list its public repositories and read the READMEs they pick. Usernames and repository names are checked against GitHub's own naming rules before they are put in an address. A repository link is stored only if it is on github.com |
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
.venv\Scripts\python scripts/cv_check.py path\to\cv.pdf   # optional: see what a CV file reads as
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
| `test_cvfile` | Real PDFs and Word files built in memory: text in order, tables, headers, text boxes, the page and length limits, every refusal with its message, nothing written to disk |
| `test_github` | Request shape, forks left out, each failure and its message, names GitHub would never allow, the token in no error or log |
| `test_intake`, `test_stories` | Both extraction calls run and one may fail; linking achievements to jobs and courses; what is proposed and what is left out; story batches |
| `test_repo_history`, `test_routes_profile` | Work history, education, skills, found facts, editing achievements and stories; one user never reading or changing another's |
| `test_routes_imports` | Upload, GitHub import, improve and the story bank end to end with the model and GitHub replaced: limits, refusals, nothing saved on failure, no username in the log |
| `test_cv` | The CV document: which section comes first at its boundaries, facts copied whatever the model wrote, bullets under their own job, the caps, every rule of an edit, keyword coverage word for word |
| `test_cvprint` | What prints and in what order: hidden parts and empty sections left out, dates, the letter's greeting and sign-off, file names |
| `test_cvpdf`, `test_cvword` | Real files read back: the same text in the same order in both, real text in an embedded font, no tables or headers, heading and list styles, accents and other alphabets, what the PDF cannot draw, page counts, nothing written to disk |
| `test_repo_cv`, `test_routes_cv` | Building, editing, downloading and deleting a CV with the model replaced: every fact equal to the record, limits, nothing saved on failure, a sent version never changed, one user never reaching another's CV, contact details |
| `test_habits` | Weeks across Sunday and Monday and the clock changes, goals by the week they applied, the streak in every case the step names, follow-ups due and quiet applications, milestones, the weekly plan's order, cap and pages |
| `test_repo_habits`, `test_repo_records` | Stage history written once per change and deleted with the application, rejections, lessons, follow-up dates, goals, mock interviews by their London date, milestones seen; one user never reading or changing another's |
| `test_routes_tracker` | Rejecting with and without anything to compare, a failed or limited lesson keeping the rejection, follow-up drafts sending only what they should, goals, milestones shown once, the state for a new user, and another user reaching none of it |

No test can reach the real model: an AI task that a test did not replace fails loudly. Database tests run against the real database inside transactions that are rolled back, so they leave nothing behind. Because the real register and real adverts are in that database, tests use names that cannot occur in real data and never count whole tables. Run the suite on its own: a second database-heavy job at the same time has caused dropped connections.

**Deploy to Vercel.** Not yet done for this version. `vercel.json` schedules the register reload for 05:00 UTC every Monday; it works only if `CRON_SECRET` is set in the Vercel project. The function may run for 120 seconds, to leave room for an import and one retry. A Python function may be 500 MB unpacked (Vercel's limit, read on 13 October 2026); with the Word and PDF packages the app is about 190 MB. `backend/fonts` must be in the bundle. Set `GITHUB_TOKEN` there: Vercel shares server addresses, and without a token GitHub allows only 60 requests an hour for each address. Add every variable from `backend/.env` to the Vercel project (use `BEDROCK_REGION`, not `AWS_REGION`, which Vercel reserves), add the Vercel address to Supabase's Site URL and Redirect URLs, then deploy. `vercel.json` builds the frontend, runs `app.py` as one function in London (`lhr1`), and leaves tests and scripts out of the bundle.

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

- One CV layout: a single column in Arial. No second design, no photo or graphics, by choice.
- A PDF cannot show the rupee sign or Arabic, Hindi, Chinese, Japanese, Korean or Thai letters, or any right-to-left text: they print as "?" and the page says which. The Word file shows them.
- The page count is the PDF's. Word lays the same text out itself; on 60 test CVs a line or two apart it agreed on 59 and said one page fewer on the other.
- Facts cannot be typed over on a CV. A wrong employer name is fixed on the Profile, then "Update from profile".
- A keyword counts as covered only when the CV has the same words. A rephrasing shows as "in your profile" or as a gap.
- The cover letter has no postal address for the employer and no reference line; the user adds them in the Word file if a job asks for them.
- A Word file edited outside the app cannot be brought back in.
- A CV made before step 3 cannot be edited or downloaded, only read, rebuilt or deleted.
- Certifications, awards and volunteering are free lines of text, not records with dates.
- A scanned or image-only CV cannot be read; the user is asked to paste the text. Only the first 20 pages and 30,000 characters of a file are read.
- Jobs, courses and skills an import found are lost if the user leaves the page before confirming them. Uploading the same CV again brings them back without repeating achievements.
- Nothing checks that a GitHub account is the user's own. Looking up repositories is not limited per user, so heavy use by one person could use up the server's GitHub allowance.
- An achievement at an employer where the user held two roles is linked to the more recent one; the user can change it.
- At most 8 achievements come from one CV. A longer CV needs a second upload to pick up the rest.
- Practice counts only a mock interview finished in the app. Practice anywhere else does not count toward the weekly goal.
- An application counts in the week of its date applied, which the user sets. Weeks before the account existed never count.
- Stage history starts on 14 October 2026; older applications have none.
- Follow-up reminders are in the app only: no email or push notification.
- A lesson is a guess from the CV and the advert. It cannot know why someone was turned down, and says so in its wording.
- A milestone banner shows once, on Home, and goes when the page's data is next refreshed. If marking it as seen fails, it shows again next time.
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
| A signed-in run by the project owner, read from the database afterwards | 26 searches; 687 adverts stored (606 from recruiters, 56 from named employers of which 29 are on the register, 7 possible and 20 not found, 25 training programmes); 30 jobs scored over two refreshes, from 0% to 83%; 2 jobs saved with their full adverts; 1 CV tailored from a listing; 1 application tracked with its link, posting date and role family; 1 job dismissed | 12 Oct 2026 |

**Not yet verified:**

- **What the owner made of the pages.** The owner has run the Jobs page signed in, and the database shows it worked end to end. Whether anything on screen looked wrong, whether the fit labels feel right on a real profile, and whether the large "Not checked yet" group is a problem have not been recorded.
- **The rest of the eight hand checks in the step document**, including a second account.
- **The weekly reload on Vercel.** Nothing is deployed. The route is tested; the schedule and the 60-second limit there are not.
- **Reed's terms of use and call limits.** Not published on its developer page.

## 17. Building a profile (step 1)

**Four ways in.** A voice call with the coach, a CV file, pasted text, or GitHub projects, in onboarding and on the Profile page, in any order and more than once.

**What one import does** (`POST /api/ai/achievements` or `/upload`):

1. A file is read into text (`cvfile.py`) and dropped. A file that cannot be read is refused here, before anything is counted or sent to the model.
2. One AI action is counted. The user's saved achievements, jobs and courses are read.
3. Two model calls run at the same time (`intake.read`). One returns achievements that are not already saved, each with the place it happened as the text names it. The other returns the jobs, courses, skills and languages the text states.
4. Each achievement is tied to where it happened (`intake.place`): to a saved job or course at once, or to a job or course that was only just found, to be linked when the user confirms it.
5. Achievements are saved. Everything else comes back as a proposal (`intake.proposals`): a new job or course whole, or, where it repeats one already saved, only the fields it would fill in.
6. The page shows "We also found" with everything ticked. `POST /api/profile/facts` saves what is left ticked, all or nothing, and links the achievements. Confirming twice changes nothing.

**Reading files.** Checked on 13 October 2026 against sample CVs made for the purpose: Word single-column and two-column table layouts, each also exported to PDF by Word itself, and two designed two-column PDFs. `pypdf`'s default mode returned every sentence whole and in order; its "layout" mode broke sentences in two-column files and is not used. A two-column PDF can still mix a side column's lines among the main column's, and the model is told so; on the real model it read such text correctly.

| File | Answer |
|---|---|
| Empty | "That file is empty." |
| Over 4 MB | "That file is over 4 MB. Upload a smaller one, or paste the text instead." |
| Neither a PDF nor a Word file, whatever its name | "Upload a PDF or a Word (.docx) file." |
| Password-protected PDF | "This PDF is password-protected. Remove the password, or paste the text instead." |
| Damaged, or unpacks to more than 20 MB | "We could not open that file. Save it again as PDF or .docx, or paste the text instead." |
| A scan with no text | "We could not read any text in this file. Paste the text instead." |

**GitHub.** The user types a username and sees that account's public repositories that are not forks. Up to five are read (description and the first 6,000 characters of the README) and each becomes a project achievement linked to its repository. Without `GITHUB_TOKEN`, GitHub allows 60 requests an hour for each server address; one import uses about seven.

**Editing.** Every field of an achievement but its quote can be edited, and it can be linked to a job or course. "Improve with AI" rewrites the bullet from the achievement's own facts and a one-line note, saves it and offers Undo. Stories can be edited and deleted; "Build my story bank" writes stories for the strongest achievements that have none, never taking the total past eight.

**Timings on the real model, 13 October 2026.** A CV import, both calls: 11 to 14 seconds in the check script, 22 seconds through the browser with the file reading and saving. Two GitHub projects: 9 seconds, 16 through the browser. Improve: 4 to 5 seconds. Eight stories: 17 seconds.

## 18. Verification record for step 1

| Check | Result | Date |
|---|---|---|
| Automated backend suite | 907 passed, 0 skipped, against the real database | 13 Oct 2026 |
| Frontend | Lints with no errors; builds | 13 Oct 2026 |
| Real model, one call per AI task (`live_check.py`) | 21 of 21 passed: the 13 from before and 8 new (CV achievements, CV facts, both at once, the same CV again adding nothing, GitHub projects, improve with and without a number, a story bank of four) | 13 Oct 2026 |
| File reading on sample CVs | Six made-up CVs in real layouts, two of them exported to PDF by Word: every sentence whole and in order; a scanned PDF refused with its message | 13 Oct 2026 |
| GitHub, real API | Repository list, README, "no such user" and the allowance of 60 an hour confirmed | 13 Oct 2026 |
| The pages against the real backend, as a temporary user whose data was never saved | Onboarding with a two-column PDF (7 achievements, each with a "From your CV" quote; 2 jobs, 2 courses, 8 skills and 3 languages offered; unticked items not saved; achievements linked). A Word upload. A scanned PDF refused. The current course filled in, not duplicated. Edit, link, improve and undo. Add, edit and delete a job; the current course locked. Skills and languages. GitHub list and import on a real account. Story bank, story edit and delete. Imports in the journal with the text read. No JavaScript errors | 13 Oct 2026 |
| The database afterwards | No trace of the temporary user | 13 Oct 2026 |

**Not yet verified:**

- **A real CV.** Every file so far was made for the test. The owner's own CV, as PDF and as Word, has not been uploaded (hand check 1).
- **The owner's own GitHub account** (hand check 3), and **a signed-in session**: the pages were driven without the login screen, through a temporary check page that was then removed.
- **How the pages look.** They were checked by their text and behaviour, not by eye: the browser pane was not on screen, so no screenshot was taken.
- **A second account in the browser seeing none of it** (hand check 7). Proved by automated tests only.
- **A voice call after this change.** The coach's own prompt is unchanged, but what follows the call now also proposes jobs and courses; tested with the model replaced, not with a real call.
- **Anything on Vercel**: the 4.5 MB cap, the 120-second limit and GitHub's allowance from shared addresses.

## 19. The full CV (step 3)

**Two kinds of CV.** A base CV from the whole profile, for no particular job, and a tailored CV for one saved job, which also carries a cover letter, the advert's main terms and the gaps to be ready for. Both are built by `POST /api/ai/cv`, one AI action.

**What one build does** (`cvbuild.build`):

1. The route reads the user's profile, education, work history and achievements, and the date in London. With no achievements it stops there.
2. One AI action is counted. With no database connection open, the model is asked for the wording: `build_cv` returns a profile paragraph, bullets each naming one of the user's achievements, and the user's own skills in two groups. For a job, `job_letter` runs beside it and returns the advert's main terms, the gaps and the three paragraphs of a letter.
3. What comes back is checked in code before anything is used (the table below).
4. `cv.assemble` puts the CV together. Every fact is copied from the records. A bullet goes under the job its achievement is linked to, in the model's order; an achievement linked to no job becomes a project.
5. The CV is drawn as a PDF to count its pages, and saved as a new version with that count.

**What the model may decide, and the check behind each rule.** The model is never sent the user's name, phone number, email, town or LinkedIn address.

| Rule | Check in code | When it fails |
|---|---|---|
| Facts are never the model's | Employers, titles, dates, courses, grades and contact details are copied from the records; anything of the kind in the reply is ignored | Nothing: it cannot happen |
| A bullet is one of the user's achievements | Its id must be one of theirs, and is used once | The bullet is dropped |
| Numbers stay as stored | The rewording must hold every number of the stored bullet and none the achievement does not | The stored bullet is used |
| A figure stays hedged | If the stored bullet says "about", "roughly" or "up to", the rewording must still hedge | The stored bullet is used |
| No skill is added | A skill is kept only if it is the user's own, in their spelling | The skill is dropped |
| Keywords are the advert's | A term must be in the advert, at most three words, and not a filler word such as "experience" | The term is dropped |
| The paragraph and letter invent no number | A number must be in the candidate's facts (for the letter, or in the job's title) | Asked once more, then the build fails with Retry |
| A tailored CV does not claim what the profile does not show | A term the advert asks for that is nowhere in the profile may not appear in the paragraph (the job's own title aside) | The paragraph is written once more, told what not to claim. Any sentence that still names such a term is then taken out, and the build fails only if no paragraph is left. A bullet that brings such a term in goes back to the stored wording |

The hedge rule, the keyword rules and the last rule were added after the first real-model runs, which showed a paragraph claiming "dashboards" for a candidate with none, "about 8%" turned into "8%", and "experience" and "desirable" returned as keywords. The last rule only catches a claim made in the advert's own words: a paragraph that says the same thing differently is not caught, which is why the paragraph is the first thing the page invites the user to read and edit.

**Section order.** Education first for someone still studying or graduated at most 24 months ago who has worked for under 24 months; otherwise work experience first. Months of work are counted once where jobs overlap.

**Editing** (`PATCH /api/cv-versions/{id}`, `cv.merge`). The page sends the whole CV as edited. Wording, order and what is hidden are taken from it; every fact is taken from the stored copy, or from the user's own record when an entry is new to this CV. A bullet or entry naming a row that is not the user's is dropped. `refresh_facts` copies the facts and contact details from the profile again and adds any job or course added since. The pages are recounted and the keywords regrouped on every save. If an application points at the version, the edit is saved as a new version and the sent one is left exactly as it was; the check is made at the moment of saving.

**Keyword coverage.** Each of the advert's terms is in one of three groups: covered (its words are in the CV as it will print), in the profile but not in this CV (with the unused achievements that show it), or not in the profile (a gap, never added). A term is found only as the same words in the same order, give or take a plural; "C" is not found in "C++".

**The files** (`cvprint`, `cvword`, `cvpdf`). A CV or letter is first turned into a list of print blocks: name, contact line, headings, entries with their dates, bullets. Both writers draw that one list. A4, one column, Arial 10.5 pt in Word and Liberation Sans in the PDF, which has Arial's letter widths. Word's own heading and list styles; dates against a right-hand tab stop; no tables, text boxes, images, headers or footers. A section with nothing to show prints nothing. A heading is never left alone at the foot of a page, and a paragraph of up to three lines is never split across pages, which is how Word breaks pages too.

| Download | File name |
|---|---|
| Tailored CV | `Firstname-Lastname-CV-Company.docx` or `.pdf` |
| Base CV | `Firstname-Lastname-CV.docx` or `.pdf` |
| Cover letter | `Firstname-Lastname-Cover-Letter-Company.docx` or `.pdf` |

**Page count against Word** (`scripts/page_check.py`, 14 October 2026). Sixty sample CVs from under one page to four, a line or two apart, each saved as a Word file and opened by Word itself: the PDF's count was Word's on 59, and one page more on the other. It never said fewer.

**The right-to-work line.** Off by default. Switched on, it offers "Right to work in the UK: Graduate visa, valid until 14 March 2028." or "Visa status: Student visa, valid until 30 January 2027." from the user's own visa type and end date, and the user can retype it. It prints last, under "Additional information".

**Timings on the real model, 14 October 2026.** The CV body: 4 to 6 seconds. Keywords, gaps and letter: 5 to 6 seconds. A whole tailored build with both calls side by side: 5 to 6 seconds, or 10 to 12 when the paragraph had to be written a second time. Through the browser, with reading and saving: 7 to 17 seconds for a tailored CV, 10 for a base one. A file download: about 0.1 seconds.

## 20. Verification record for step 3

| Check | Result | Date |
|---|---|---|
| Automated backend suite | 1,180 passed, 0 skipped, against the real database | 14 Oct 2026 |
| Frontend | Lints with no errors; builds | 14 Oct 2026 |
| Real model, one call per AI task (`live_check.py`) | 24 of 24 passed: the 20 from before and 4 new (the CV body for a job and for none; keywords, gaps and letter; a whole build), 3 to 5 seconds each | 14 Oct 2026 |
| The four new real-model checks, repeated | 12 of 12 over three runs after the fixes above. One earlier run of the base CV body had failed its check before them | 14 Oct 2026 |
| Real output read by eye | Tailored and base CV bodies, four runs each: 15 of 16 bullets kept the model's rewording with every number and hedge intact; the one that turned "about 8%" into "8%" fell back to the stored bullet. Keywords after the fix: "SQL", "dashboards", "Python", "stakeholder communication" | 14 Oct 2026 |
| PDF and Word files in tests | Read back with `pypdf` and `python-docx`: the same text in the same order in both, real text in an embedded font, no tables or headers, accents, Greek, Cyrillic and a pound sign intact | 14 Oct 2026 |
| Page count against Word itself | 59 of 60 sample CVs the same, 1 one page over, 0 under | 14 Oct 2026 |
| The pages against the real backend and model, as a temporary user whose data was never saved | Contact details asked for before the first CV, a wrong LinkedIn address refused. A tailored CV built with every fact from the records. Reword the paragraph, a bullet and the skills; hide, move and restore a bullet; add two achievements from the profile (the GitHub one arrived with its repository address); add a line; switch on the right-to-work line; address the letter to a name. A job renamed on the profile offered "Update from profile" and it took. Content pushed to three pages showed the warning and what to trim, and hiding six lines brought it back to two. Logged an application with the CV, edited again: a new version, the sent one unchanged, and deleting the sent one refused with its message. A base CV built with no letter. A CV from before this step opened read-only and was rebuilt as a full one. Bullets and jobs reordered by simulated drag, and a drop into another list refused. Contact details and certifications saved on the Profile. No JavaScript errors | 14 Oct 2026 |
| The files that run produced | Three CVs and a letter, as Word and PDF: identical text in each pair; opened by Word itself they were 1, 1, 2 and 1 pages, the app's own counts, in Arial on A4 with real bullets and heading styles and no tables | 14 Oct 2026 |
| The database afterwards | No trace of the temporary user | 14 Oct 2026 |

**Not yet verified:**

- **A real profile.** Every CV so far was built from a made-up candidate. The owner's own base and tailored CV, read for accuracy, are hand check 1.
- **The files opened by a person.** Word reported the page counts, fonts and styles, and the text was compared by program. Nobody has yet looked at a downloaded file in Word, Google Docs or a PDF reader, or selected and copied its text (hand checks 2 and 3).
- **A signed-in session.** The pages were driven without the login screen, through a temporary check page that was then removed. Saving a file through the browser's own download prompt was not seen: the check confirmed the page hands the browser a file with the right name.
- **Dragging to reorder with a real mouse.** The up and down buttons were used, and the drag handlers were driven with simulated drag events. Nobody has yet dragged a bullet by hand.
- **How the pages look**, beyond two screenshots of the Resume page at one width.
- **An applicant-tracking system.** No file has been put through a real parser (hand check 7, the owner's choice).
- **The owner's own earlier CVs.** A made-up one from before this step opened and rebuilt correctly; the owner's real ones have not been opened.
- **A second account in the browser.** Proved by automated tests only.
- **Anything on Vercel**: the size of the bundle with the two new packages, and whether the font files are in it.

## 21. The tracker and habits (step 4)

**Every application's whole record.** Clicking a card opens a panel with every field: company, role, the stage with its dated history, the dates applied and posted, the CV version sent (which opens it on Resume), where it was sent, the link, sponsor licence, the follow-up date, the contact's name and how to reach them, notes, and for a rejection the lesson. Each field is saved as it is changed. Every stage change, whether by dragging, by the menu on the card or by a rejection, adds one dated line to `application_events`.

**A lesson from each rejection.** Moving a card to Rejected opens two questions first: where it ended (at the CV stage, after a phone screen, after an interview, after a final interview) and any feedback, in the user's own words. Cancelling leaves the card where it was. `POST /api/applications/{id}/reject` saves the answers and the stage, then, in a separate step with no database connection open, asks the model for one lesson: what may have happened, one change for next time, and which page fixes it (Resume, Interview coach or Profile). The CV is the version recorded with the application; the job description is the application's saved job, or else the job that CV was built for. With neither, no AI call is made and the page says so. If the model fails or the daily limit is reached, the rejection and the answers stay saved and the lesson can be asked for again from the panel.

| Rule for a lesson | Check in code | When it fails |
|---|---|---|
| A guess, never a verdict | The likely reason must contain "may", "might", "could", "possibly", "probably", "perhaps", "likely", "seems" or "suggests" | Asked once more, then an error with Retry |
| No invented feedback | With no feedback entered, the reason may not mention feedback, and neither part may say "they said", "you were told" or similar. Suggesting the user ask for feedback is allowed | The same |
| Quotes are real | A phrase in quotation marks must appear in the feedback, the CV or the advert | The same |
| No advert, no description of it | With no job description recorded, the reason may not mention the advert | The same |
| Written to the user | "The candidate" is refused | The same |
| A page that exists | Anything but resume, interview or profile becomes resume for a CV-stage rejection, interview for the rest | Normalised |

The last three rules came from the real model on 14 October 2026, which wrote "The candidate may have lacked..." and, with no CV recorded, still wrote about "your CV". That second case is allowed: refusing it would leave every application tracked without a CV with no lesson, and the reason is still a possibility.

**Follow-ups.** A new application is given a follow-up date a week after the date applied. Home and Applications list those whose date has come, and those still at Applied after 21 days with no stage change, with "Move to No reply". "Draft a follow-up" asks the model for a subject and a short body from the role, company, date applied and contact's name only; code adds "Dear <name>," (or "Dear Hiring Manager,") and "Kind regards," with the user's own name, after removing any greeting or sign-off the model wrote itself. The real model put "Dear Priya," on the same line as the body and ended with "Best wishes" after the last sentence; both are handled. Nothing is sent for the user: the message is copied.

**Goals and the streak.** A week runs Monday to Sunday in London. It is met when applications with a CV version recorded reach that week's application goal and finished mock interviews reach its practice goal. The streak is the run of met weeks ending last week, plus this week once it is met; a week in progress never breaks it, and weeks before the account existed do not count. Goals live in `weekly_goals`, each from a Monday: the first a user sets applies to this week, later changes from the next Monday, so a past or current week is always judged by the goal it started with. A mock interview's week is decided by its London date, so one at 00:30 on a Monday in summer (23:30 UTC on Sunday) belongs to the new week.

**Milestones.** First application; 10, 25 and 50 applications; first reply, interview and offer (a card counts if it is at that stage now or passed through it); first mock interview; six STAR stories; four and eight weeks in a row. Worked out from the data each time; `profiles.milestones_seen` records which have been shown.

**The weekly plan.** At most five tasks, built by rules in this order: follow-ups due; each tracker finding that links to a page; new matching jobs from the last 48 hours; applications still needed for the goal; mock interviews still needed; stories still needed to reach six; achievements without a number. A task that is done is simply not built again. Nothing in the plan comes from the model.

**The home page**, top to bottom: the milestone banner when there is one, the next best step, this week against the goals with the streak and Edit goals, the weekly plan, follow-ups due, getting started while it is unfinished, and beside them the visa countdown and the search totals.

**What you have learned.** Applications lists the latest lessons, newest first. Three lessons pointing to the same page make a finding under What to fix.

## 22. Verification record for step 4

| Check | Result | Date |
|---|---|---|
| Automated backend suite | 1,331 passed, 0 skipped, against the real database | 14 Oct 2026 |
| Frontend | Lints with no errors and no new warnings; builds | 14 Oct 2026 |
| Migration `007_tracker_habits` | Applied to the real database; open applications without a follow-up date were given one | 14 Oct 2026 |
| Real model, one call per AI task (`live_check.py`) | 28 of 28 passed: the 24 from before and 4 new (a lesson with feedback, without feedback, without an advert; a follow-up draft), 1 to 3 seconds each | 14 Oct 2026 |
| Real output read by eye | Seven lessons: each hedged, specific to the CV and advert, and using the feedback only when it was given; the first ones spoke of "the candidate", fixed. Seven drafts: 50 to 65 words, one ask, the right date and contact; the first ones lost their body to a greeting on the same line or kept a second sign-off, fixed | 14 Oct 2026 |
| Home and Applications against the real backend and model, as a temporary user whose data was never saved | The panel showed every field; notes, date posted and link saved and were still there after a reload. A card moved Applied, Phone screen, Interview, Offer showed each change with its date, and Offer showed nothing to follow up. Dropping a card on Rejected asked the two questions without moving it, and Cancel left it at Applied; answered "after an interview" with feedback, it gave a lesson about this job's CV and the feedback, which also appeared under What you have learned and in the panel. A card with no CV or advert gave the fixed message and made no AI call. A real follow-up draft was addressed to the contact, dated right and signed with the user's name; Mark as followed up moved the date a week on and took it off Follow-ups due. Setting goals of 1 and 0 made the week met and the streak 1, and took the goal tasks off the plan. Three milestones showed in one banner and not again after a reload; two more reached later showed once each. Open CV opened the version that was sent. Move to No reply worked from Home. At phone width the panel filled the screen with no sideways scroll | 14 Oct 2026 |
| Defects that check found, each fixed test first | An application logged late never counted as quiet; Move to No reply left a follow-up due; "1 of 1 applications" | 14 Oct 2026 |
| The database afterwards | No trace of the temporary user | 14 Oct 2026 |

**Not yet verified:**

- **A signed-in session.** The pages were driven without the login screen, through a temporary check page that was then removed.
- **The owner's own applications.** The migration gave the open ones a follow-up date a week after they were sent, so they will show as due at once; they have not been looked at.
- **Dragging a card with a real mouse.** Drops were driven with simulated drag events and the stage menu.
- **A second account in the browser** starting at zero (hand check 7). Proved by automated tests only.
- **Real weeks passing.** Streaks across weeks, the weeks the clocks change, milestones at 10, 25 and 50 applications and streaks of 4 and 8 weeks are proved by tests with set dates, not by living through them.
- **How the pages look**, beyond the panel at phone width.
- **Anything on Vercel.**
