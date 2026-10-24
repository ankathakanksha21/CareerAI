# UK Career Navigator: scope, architecture and handover

Last updated: 15 October 2026. This is the living document for the project. It is updated at the end of every build step.

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
| 4 | Tracker detail, follow-ups, a lesson from each rejection, weekly goals, streaks, weekly plan | 0 | Built and merged into `main`. The owner's hand checks are left (section 22) | `careerai-step-4-tracker-and-habits` |
| 5 | Interview prep: sourced company research, prep pack, questions matched to stories | 0 | Built and merged into `main`. The owner's hand checks are left (section 24) | `careerai-step-5-interview-prep` |
| 6 | Hidden market: contacts, outreach drafts, saved events, referrals | 4 | Built and merged into `main`. The owner's hand checks are left (section 26) | `careerai-step-6-hidden-market` |
| 7 | Peers: opt-in buddy groups of two or three | 4 | Built on branch `step-7-peers`. The owner's three-account hand checks and terms of use are left (section 28) | `careerai-step-7-peers` |

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
 │                                 ├─ Companies House API                         ← a company's official record (a company name, nothing personal)
 │                                 ├─ Tavily                                      ← a company's news and competitors (its name only)
 │                                 ├─ employers' websites                         ← up to six public pages, read safely, robots.txt respected
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
| Company research | Companies House's public data API; Tavily for news and competitors; the employer's own site read by `fetcher.py` | The register is official and free. Tavily has 1,000 free credits a month, dated news, and terms that allow keeping results (Brave's forbid storing them, which the shared cache needs) |
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
| Every line of a company brief cites a passage the app fetched, and code checks it against that passage | Nothing about a company comes from the model's memory | An honest line worded with a figure the page writes differently is dropped | – |
| Company research is shared by everyone for 14 days, kept by the Companies House number with the name searched for, and the website | One search per company, not per user; a wrong name or website typed by one user never changes another's brief | The same company can be researched twice under two spellings or websites | – |
| Research that missed a source for a passing reason (a timeout, Companies House or the search service down) is shared for an hour, not 14 days | One bad moment for one user is not everyone's brief for a fortnight | A failing source is tried again by the next user after an hour | – |
| A pack keeps its own copy of the brief | Another user refreshing the company never changes it; talking points always point at facts the pack shows | A pack shows its own research date until Refresh | – |
| Research and the pack are two requests | Each fits the 120-second limit, and the page shows progress between them | One more route | – |
| Companies House lines are written by code | Exact register facts need no model | None | – |
| A news or competitor result must name the company (the first word of its name) | A result about another company never reaches the brief | Two companies sharing a first word are not told apart | Users report a wrong line |
| The pitch is accepted at 110 to 260 words | The real model writes about 120 to 140 words even when asked for more | Pitches run about a minute rather than a full 90 seconds | The model changes |
| Research is limited to 5 a day, separately from the AI limit. Every research counts, Refresh and a retry after a failure included; a shared, fresh company is free | Searches cost money, and nothing can run past the limit | A failed research uses one of the day's five | Users hit the limit because of failures |
| Edits to a pack are saved part by part, and a rebuild re-reads the pack under a lock | Two saves a moment apart, or an edit made while the pack is rewritten, are never lost | – | – |
| An outreach draft is the model's own words checked in code: within its limit or asked for once more and then refused, never cut; no connection claimed but the one the user entered; no visa talk, month, figure or web address that was not given | A draft can be sent as it is without claiming a shared past that never happened | An honest draft can cost a retry; a small embellishment code cannot see ("yesterday", a project described more grandly) still gets through, so the page asks the user to read it first | Users report claims they did not make |
| The model is never sent a contact's name or notes, nor the user's name; code adds "Hi Priya," ("Dear Dr Shah," for a reference) and the sign-off | Less personal data leaves the app; a name is never misspelt | The model cannot vary the greeting | – |
| A message marked as sent stays counted when its contact is deleted (the row loses the contact) | A past week or a streak never changes because someone was tidied away | Rows with no contact stay in the table | – |
| The same step with the same person on one London day is recorded once | Marking a message sent twice counts once | Two different messages of one kind to one person on one day count once | – |
| Accounts that existed when step 6 arrived start with an outreach target of 0 and an invitation to set one; later accounts start at 2; goals saved before step 6 ask for no messages | Nobody's streak breaks without warning, and no past week changes | One more profile column (`outreach_default`) | – |
| Search links for people and events are built on the server from the profile and open on the other site; the app fetches nothing from LinkedIn, Meetup, Eventbrite or the professional bodies | No scraping and no terms to break | LinkedIn's search opens only for someone signed in there; what the links find is whatever those sites show | A site changes its addresses |
| A reference is asked only of a tutor, lecturer or supervisor; a referral only for a saved job whose employer matches the contact's company by the register's name rules | The app never drafts a request that would embarrass the user | A contact at a parent company with another name cannot be asked for a referral | Users ask for it |
| Chat questions are written by code from the contact's role and company; event preparation is saved on the event | Both are free to read again | Less variety in the chat questions | – |
| One function, `peerdb.peer_view`, returns anything about another user, from an explicit field list; all peers SQL lives in `peerdb.py`, apart from `repo.py` | The one exception to "every user's data is private" is small enough to review in one place | Matching also reads other users' field, places, university and time waited (to choose, never returned) | A second feature needs to show one user to another |
| Pages name a member by their membership row's id, never a user id | Nothing that identifies an account across groups reaches the browser | – | – |
| A group never holds more than three live members: each holds one of three places, with a unique index; one live group per user, also by index | Two people accepting at the same moment cannot make four | A place freed by someone leaving is reused | – |
| Everyone says yes before anyone sees progress or a link, including the current members when a third is proposed | Nobody shares their week with someone they did not accept | A third joins a little more slowly | – |
| A different field is proposed only when nobody in the same field is waiting (owner's choice) | With few users, people are matched at all | A pairing across fields may suit less well; either can say not this time | Enough users to wait for the same field |
| Declined, unanswered for 7 days, or left: that pairing is never proposed again; blocks hide both people from each other everywhere | Nobody is offered the same silent or unwanted person twice | Two people who would now get on are never paired again | – |
| Matching runs on joining, on going back on the list, and when a waiting user opens Home or Peers; no scheduled job | No extra service; a missed match heals on the next visit | A few queries on every page load for someone waiting | Users wait long for a match that exists |
| Switching Peers off deletes the user's check-ins and the nudges they sent and received, and clears their link; blocks, passes and reports stay | Others stop seeing them at once | – | – |
| A report copies the line it reports | Editing or deleting the line later keeps the evidence | The copy goes when either account is deleted, as every row does | – |

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
- Moving a card out of Rejected clears where it ended, the feedback and the lesson. Moving it into Rejected, or from one rejected stage to the other, always asks where it ended first, so the answer and the stage agree. The question starts on an answer that fits: a card already at "Rejected after interview" starts on "after an interview".
- A lesson is saved only onto the rejection it was written for: if the card was moved out of Rejected or answered again while the model was writing, the lesson is dropped and the page says so.
- Three lessons that point to the same page become a finding under What to fix.
- All milestones not yet shown appear in one banner at the top of Home and are marked seen as it appears. Deleting an application can take away a milestone not yet shown; a milestone already shown never comes back.
- The weekly plan holds at most five tasks, never one for a page this build lacks: no jobs task without a Reed key, no task for a finding that links nowhere.
- Prep packs appear only when the Companies House key, `SEARCH_PROVIDER=tavily`, the search key and the model are all set. A pack already made can always be read, edited and deleted.
- "Prepare" opens the pack that already exists for a job or application. An application with a saved job shares that job's pack.
- Refresh researches again and rewrites the pack; a pitch or right-to-work line the user edited is kept, and the ticks on questions to ask are cleared because the questions change.
- A likely question is matched only to one of the user's own stories; anything else shows "No story yet" with a link to write one.
- The user ticks at most three questions to ask. Printing a pack prints only the ticked ones, when any are ticked, and every source as its address.
- A story written by the app is tagged with up to three of eight competencies in the same call; "Tag my stories" tags older ones in one AI action; the user can tick them by hand. A story the model gave none takes its one-word label when it is exactly one of the eight.
- The mock interviewer is told a company summary (what they do, products, news) whenever the chosen job has a pack, and the pack's likely questions in the job-specific and behavioural sessions.
- Networking is always in the menu; drafts and event preparation need the model, and the rest works without it.
- Recording a step moves a contact forward and never back, so a thank-you sent after a chat leaves them at Chat done. The user can set the status by hand to correct a mistake.
- Linking a saved contact to an application copies their name into the contact name the follow-up draft uses; one who offered a referral makes the source Referral. Unlinking changes neither.
- "Coming up" on Home lists the next three saved events the user is interested in or going to, from today on, by the London date: an event tonight stays until midnight.
- The weekly plan adds "Follow up with <name>" once a message has had no reply for 14 days, and "Message <name>" (the person waiting longest at To contact) or "Find someone to message" while the outreach target is not met.
- Five messages marked as sent with no reply, chat or referral from anyone become a finding that points to the guide.
- Peers is always in the menu; only the field suggestion needs the model, and the user can pick a field by hand.
- "Not this time" and leaving put the user straight back on the list, and matching runs for them at once (after the people left behind), up to 3 new proposals a London day each; after that they wait until tomorrow. Switching Peers off is how to stop.
- Blocking a proposed newcomer turns them away and the blocker stays; blocking a member already in means the blocker leaves.
- "Same city" means a shared preferred location, ignoring "Remote" and case. The CV's town is not used.
- A member counts as inactive after 21 days with no application with a CV, mock interview, message marked as sent or check-in, once they have been in the group that long; the others are then offered "Find a new group", which is the same as leaving.

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
  companies_house.py  Companies House client: search by name, one company's profile, SIC descriptions
  fetcher.py       an employer's website, read safely: public addresses only (checked at connection), robots.txt, size, time and page limits
  textify.py       HTML to plain text, shared by Reed adverts and websites
  websearch.py     Tavily client: a company's news from the last year and its competitors
  research.py      one company's research: the four sources side by side, numbered passages, the cited brief, the cache key
  prep.py          a prep pack's own rules: right-to-work line, edits, rebuilds, what the interviewer is told. Pure functions
  networking.py    the networking pipeline: how a contact moves on, the next step and when, follow-ups due, coming up, the no-replies finding, chat questions. Pure functions
  links.py         search links for people and events from fixed sites, professional bodies by field, safe addresses typed by the user. Pure functions
  peers.py         buddy groups' rules: the 21 fields, the code of conduct, report reasons, the nudge's wording, contact links, ranking, progress, group streak, inactivity. Pure functions
  peerdb.py        every peers query. peer_view is the ONLY function in the app that returns another user's information; matching, proposals, expiry, leaving, check-ins, nudges, blocks, reports, and the owner's report tools
  ai.py            one function per AI task: prompt, output shaping, quote checking
  llm.py           one call path to Bedrock, fallback model, JSON parsing
  voice.py         ElevenLabs token minting and transcript fetch (owner only)
  content.py       loads data/content.json, the static guidance copy
  data/visa_rules.json   the visa figures, their gov.uk sources and the date checked. The only place they are written
  data/sic_codes.json    SIC 2007 code descriptions from gov.uk's condensed list (Open Government Licence)
  data/professional_bodies.json   ten professional bodies, each with its events page, the words that pick it and the date it was checked
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
                   RejectQuestions (where a rejection ended, feedback, the lesson), FollowUps, ThisWeek (goals, streak), Plan, Milestones,
                   PrepPacks (the tab), CompanyConfirm (pick the company, research, build), PrepPack (the pack, printable), StoryCoverage,
                   ContactCard (one person: next step, steps so far, chat help), DraftMessage, PersonForm, FindPeople,
                   NetworkingEvents (where to look, saved events, preparation, who did you meet), NetworkingGuide, ComingUp,
                   PeerConsent (what the group sees and never sees, the code of conduct, the field), PeerGroup (members, check-ins, nudges, link, report, block, leave), PeerCard (Home)
  tracker.js       the tracker's stage words and small rules, shared by Applications and Home
  prep.js          prep pack words and which pack belongs to a job or application
  networking.js    networking's labels and small rules: which drafts a contact can be sent, event times in London
  pages/           Landing, Auth, Privacy, Contact, Onboarding, Home, Profile, Pathways, Jobs, Resume,
                   Interview, Applications, Networking, Peers, Journal, Account
app.py             Vercel entry point: the API plus the built frontend
```

## 7. Data model

All tables are in the `public` schema. Every row of a per-user table has `user_id` referencing `auth.users` with `on delete cascade`, so deleting a login removes all of that person's data. Five tables added in step 2 and one in step 5 hold public data shared by everyone and have no `user_id`; they are marked below. Row-level security is on with no policies, and the browser-facing roles (`anon`, `authenticated`) have no privileges.

| Table | Holds |
|---|---|
| `profiles` | One row per user: name, university, course, graduation month, visa type, visa end date, preferred locations, pitch, skills, spoken languages with a level, GitHub username, and for the CV a phone number, town or city, LinkedIn address and lines of certifications, awards and volunteering, which milestones have been shown, their university's careers events page, and the outreach target used until they set goals (0 for accounts from before step 6, 2 after) |
| `achievements` | Their own words (`raw`), the UK CV bullet (`uk_version`), skills, outcome, scale, context note, source (voice, paste, cv or github), the job or course it happened in, and for a GitHub project its repository link |
| `work_history` | Jobs, internships and placements: employer, job title, location, country, start and end month, whether it is current, one line on what the employer does, where the entry came from |
| `education` | Courses: institution, qualification, subject, start and end month, grade, country. The current course is made from "Your details" and marked `from_details` |
| `role_families` | AI-suggested families: fit, estimated overlap, UK titles, requirements shown or missing, targeted or not. Unique per user by name, ignoring case |
| `saved_jobs` | Jobs the user pasted: title, company, description, AI summary, keywords, matched role family |
| `cv_versions` | Each CV in full as one document, named "<title>, <company> vN" or "Base CV vN": whether it is a base or a tailored CV, its page count, when it was last edited, who its letter is to. A version made before step 3 is marked format 1 and holds only a paragraph, bullets and a letter |
| `stories` | STAR stories, linked to their achievement, with up to three of eight competencies |
| `applications` | Tracker rows: company, role, family, CV version, source, stage, applied and posted dates, link, the contact's name and how to reach them, the saved contact behind it, notes, sponsor licence, the next follow-up date and when the user last followed up, and for a rejection where it ended, any feedback and the lesson |
| `application_events` | One row per stage change of an application, with when; the first records its creation. Deleted with the application |
| `weekly_goals` | The user's weekly goals (applications with a CV, mock interviews, messages to contacts), each applying from a Monday. No row means the defaults: 5, 2 and the profile's own outreach default. A goal saved before step 6 has no messages target and asks for none |
| `contacts` | People the user added: name, role, company, how they know them (alumnus, tutor or lecturer, supervisor, met at an event, recruiter, introduced, no connection yet), profile link, notes, where they are in the pipeline, the saved event where they met. No email address or phone number |
| `outreach_events` | One row per step with a contact: a message marked as sent with its kind, a reply, a chat booked or held, a referral offered, with its London day. Recorded once per person, step and day. A deleted contact's rows stay with the contact cleared |
| `networking_events` | Events the user saved: name, start (London time), place or online, link, kind, Interested, Going or Attended, notes, and the last preparation written for it |
| `peer_profiles` | One per user who has ever switched Peers on: on or off, when they consented (18 or over, the code of conduct), their field, their contact link, since when they are on the list (kept through a proposal, so someone turned down keeps their place; cleared once they are in an active group), and whether the owner barred them |
| `peer_groups` | A buddy group: proposed, active or closed, and the London day it first had two members |
| `peer_group_members` | One row per person per group: their place (1 to 3), proposed, accepted, declined or left, and who has said yes to them. Its id is how pages name a member |
| `peer_passes` | Pairings never proposed again: declined, left unanswered for 7 days, or left |
| `peer_checkins` | One line (140 characters) per member per group per London week |
| `peer_nudges` | Who nudged whom, in which group, on which London day. One a day from one person to another |
| `peer_blocks` | Who blocked whom |
| `peer_reports` | Reports for the owner to review: who, about whom, the reason, details, a copy of the reported line, handled or not. Deleted with either account |
| `journal_entries` | Coach calls, mock interviews and imports (a CV upload, a GitHub import): summary, points, actions, scores, and the transcript or the text that was read |
| `usage_events` | One row per AI action, voice session or newly researched company: the daily limits |
| `prep_packs` | One per saved job (or per application without one): the role and company, a copy of the brief it was built from, talking points, the pitch, likely questions with the story for each, questions to ask and which are ticked, the right-to-work line, the interview type, and whether the user edited the pitch or the line |
| `job_listings` (shared) | One row per advert: source and its id, title, employer, who really posted it (employer, agency, or training for an advert that sells a course), location, salary and whether it is annual, description and whether it is the full text, link, posting date, and what the register says about the employer |
| `job_searches`, `job_search_results` (shared) | The search cache: each search anyone has run, when, and the adverts it last found |
| `sponsors` (shared) | The register's Skilled Worker entries: registered name, normalised name, town, county, rating. A trading name gets its own row |
| `reference_meta` (shared) | When the register was last loaded and the date gov.uk published that file |
| `companies` (shared) | One company's research: the key it is kept under, its name, Companies House number and website, the register entry, the brief's lines each with its source address, title and date, which sources could not be read, and when |
| `job_matches` | One user's view of one advert: role family, fit percentage and label, what they show and lack, new, seen, saved or hidden |
| `schema_migrations` | Which migration files have been applied |

Schema changes are numbered SQL files in `backend/migrations/`, applied with `python migrate.py`. Applied so far: `001_initial`, `002_journal_transcript`, `003_jobs` (which also adds `listing_id` and `posted_on` to `saved_jobs`, and `include_senior` to `profiles`), `004_training_adverts`, `005_profile_depth` (which also copies each existing user's current course into `education`), `006_full_cv`, `007_tracker_habits` (which also gives each open application without one a follow-up date a week after it was sent), `008_interview_prep` (which also tags existing stories whose one-word competency is exactly one of the eight), `009_networking` (which gives every account that existed then an outreach target of 0), `010_peers`.

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
| `PATCH`, `DELETE /api/stories/{id}` | Edit or remove a STAR story, including its competencies (at most three) |
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
| `PUT /api/profile/goals` | Weekly goals: 1 to 30 applications, 0 to 14 mock interviews, 0 to 20 messages (left out: the target in force is kept). The first applies this week, later ones from next Monday |
| `POST /api/milestones/seen` | Milestones the banner has shown |
| `POST /api/companies/search` | Up to five Companies House matches for a name. The name travels in the body |
| `POST /api/companies/research` | A confirmed company's brief: shared research from the last 14 days, or researched now (one research use) |
| `POST /api/ai/prep` | The pack for a saved job or an application, from a company's research. One AI action. A rebuild keeps the user's edits |
| `GET`, `PATCH`, `DELETE /api/prep/{id}` | A pack with what the interviewer is told from it; the user's pitch, right-to-work line, ticks (at most three) and interview type |
| `POST /api/prep/{id}/refresh` | Research the pack's company again now; the page then rebuilds the pack |
| `POST /api/ai/stories/tag` | Competencies for the user's stories that have none. One AI action |
| `GET`, `POST`, `PATCH`, `DELETE /api/contacts[/{id}]` | People the user contacts, each with the next step and the steps so far. A profile link must be a public http or https address |
| `POST /api/contacts/{id}/events` | Record a message sent (with its kind; "own" when there was no draft), a reply, a chat booked or held, a referral offered. Once per person, step and day |
| `POST /api/ai/outreach` | A draft of one of seven kinds for one contact. One AI action. 422 for a thank-you with nothing learned, a reference from someone who is not a tutor or supervisor, or a referral ask without a saved job at their company |
| `GET`, `POST`, `PATCH`, `DELETE /api/networking-events[/{id}]` | Saved events. A time without a zone is London time |
| `POST /api/ai/networking-events/{id}/prepare` | An introduction, three openers and a goal, saved on the event. One AI action |
| `GET /api/networking/links` | Search links for people and events and professional bodies, built from the profile, target roles and saved jobs |
| `PUT /api/profile/events-url` | The university's careers events page; empty clears it |
| `GET /api/peers` | Where the caller stands in Peers (off, waiting, proposed, in a group) with what they may see of the others; `appears_as`, the caller's own name, university, course and target roles exactly as their group sees them; `again_tomorrow` when they have had 3 proposals today. Also in `/api/state` as `peers` |
| `POST /api/peers/join` | Switch Peers on: `{over_18: true, conduct: true, field}`. 409 without university and course, or when already on; 403 when barred. Matching runs |
| `POST /api/peers/leave-all` | Switch Peers off: out of any group, check-ins and nudges deleted, link cleared |
| `POST /api/peers/groups/{id}/accept`, `/decline`, `/leave` | Yes or not this time to a proposal (or a newcomer); leave a group. 404 for a group the caller is not live in |
| `PUT /api/peers/groups/{id}/checkin` | This week's line, 1 to 140 characters |
| `POST /api/peers/groups/{id}/nudge` | `{to: member}`. 409 for a second nudge the same London day |
| `PUT /api/peers/contact-link` | A LinkedIn (`linkedin.com/in/...`) or WhatsApp (`wa.me/<international number>`, not starting with 0) link over https, or empty to clear. 422 for anything else; checked again in `peerdb.set_contact_link` |
| `POST /api/peers/block`, `POST /api/peers/report` | `{member}`; a report adds `{reason, details?, checkin_id?}`. 404 for someone the caller cannot see |
| `POST /api/ai/peers/field` | A field from the caller's target role names, or null. One AI action; none without target roles |
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
- **A company brief.** `company_brief` is given only numbered passages the app fetched and must cite one for each statement. A statement is kept only if its number was sent, its section is one of six, every figure and every quoted phrase in it is in that passage, a value carries words found exactly in its page, and a news line cites a news result from the last 12 months (its date is the result's, not the model's). Register lines are written by code. With nothing fetched at all, the model is not asked.
- **A prep pack.** `prep_pack` gets the brief, the advert (or a note that none was recorded), the user's course, achievements and stories, with short ids mapped back in code. A talking point must name a real fact and achievement and use only their figures; the pitch, in three paragraphs, 110 to 260 words with no figure from outside the input; a likely question keeps a story only if it is the user's. No name, contact details or visa are sent.
- **Story competencies.** Each story is tagged with up to three of eight competencies; anything else the model names is dropped.
- **Outreach drafts.** `outreach_draft` is given the user's pitch (or their course), the contact's role and company, how the user knows them and, by kind, what they learned, when they can start, their target roles, or the saved job and their achievements. The model writes the body only; code removes any greeting or sign-off it wrote, adds its own, adds the job's line to a referral ask, and checks the result (section 25).
- **Event preparation.** `event_prep` is given the pitch and the event's name and kind: an introduction of 30 to 90 words with no figure that is not in the pitch, three openers, one goal.
- **Privacy in logs.** Failures log the task name and the error type only, never prompts or replies. `httpx` request lines are off, because an address can hold what a user typed.
- **No database connection is held during a model call.** Each AI route reads and counts usage in one short transaction, calls the model, then writes in a second.

To check the prompts against the real model: `python scripts/live_check.py` from `backend/` (uses credits).

## 10. Voice

- Two private ElevenLabs agents, created and updated by `setup_agents.py`: an onboarding coach and a mock interviewer. Their prompts live in that file. Run it again after editing a prompt.
- The backend mints a short-lived token; the ElevenLabs key never reaches the browser.
- The coach is told the user's first name, course, university and visa type, so it spends the call on experience.
- The interviewer is told the job (or "general practice"), the session type and a summary of the user's achievements, and, when the job has a prep pack, a company summary and the pack's likely questions to ask from.
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
| Cost abuse | Daily limits per user: `DAILY_AI_LIMIT` (40), `DAILY_VOICE_LIMIT` (3) and `DAILY_RESEARCH_LIMIT` (5 newly researched companies), midnight to midnight UK time. A jobs refresh that scores anything is one AI action; Reed calls are free and bounded by the shared cache and 20 searches per refresh |
| Shared tables | Hold only public adverts and the public register. A user's fit, saved and dismissed jobs live in `job_matches`, filtered by user id like everything else |
| What Reed is told | Job titles and locations from the user's target roles. Never a name, an email or anything from their profile |
| Uploaded files | Read as the raw request body, in memory, at most 4 MB, and dropped. Never written to disk or the database: only the text read from them is kept. The type is decided from the file's first bytes, never its name. Password-protected, damaged and oversized-when-unpacked files are refused before anything reaches the model |
| Contact details | Phone number, town and LinkedIn address are stored for the CV's contact line and printed there. They, the user's name and their email are never sent to the model |
| People at employers | An application can hold a contact's name and how to reach them. Only the name is sent to the model, for a follow-up draft. Nothing is ever sent to an employer for the user |
| Generated files | A CV or cover letter is made in memory for one download, sent with `Cache-Control: no-store`, and not kept anywhere. Its file name is plain ASCII built from the user's name and the company |
| What GitHub is told | A username the user typed, to list its public repositories and read the READMEs they pick. Usernames and repository names are checked against GitHub's own naming rules before they are put in an address. A repository link is stored only if it is on github.com |
| The scheduled reload | Refused unless the request carries the secret; refused always when no secret is set. Compared in constant time |
| Links from outside | An advert's link is used only if it is on reed.co.uk over https; anything else is replaced by Reed's standard address |
| Reading employers' websites | Only http and https on the standard ports, only a typed host name (never an IP address, user name or port). The server resolves every address itself and refuses unless all of them are public, then connects to the address it checked, so a redirect or a second lookup cannot reach a private network. Redirects are followed by hand and checked the same way. robots.txt is respected for "UKCareerNavigator". Pages are asked for uncompressed. At most 1 MB of text and 8 seconds a page, the clock read after every piece that arrives, six pages, HTML only; all four sources together get 30 seconds. IPv6 forms that carry an IPv4 address (mapped, NAT64, 6to4, IPv4-compatible) are judged by that address or refused. Tested against private, loopback, link-local and each of those forms |
| What Companies House, Tavily and employers' sites are told | A company name and its website. Nothing about the user. A Companies House number is checked as eight letters or digits before it is put in an address |
| Shared research | `companies` holds public facts about companies only. A user's pack, ticks and edits are in `prep_packs`, filtered by user id |
| People the user adds | Name, role, company, how they know them, a profile link and notes; no email address or phone number is asked for. Only the role, company and how they know them go to the model for a draft. Nothing is sent to them: the user copies a draft |
| Search links and typed addresses | Built on the server from fixed addresses on linkedin.com, meetup.com, eventbrite.co.uk and the listed professional bodies, with what the user typed escaped inside one query value or path segment; tested against `&`, `#`, `?`, `/`, `..` and accents. A profile link or events page must be http or https on a named public host with no user name, password or port; `javascript:` and the like are refused |
| What one user sees of another (Peers) | Only through `peerdb.peer_view`: first name, university, course and target roles; once both have said yes, targets met this week (never counts), streak, contact link, this week's line and whether they have been inactive. Nothing unless both are live in the same open group, neither blocked the other, and the member is switched on and not barred. Tested for a member with a surname, visa, applications and achievements. Matching never uses visa status |
| Moderation | Fixed-wording nudges; a 140-character weekly line with Report beside it; reports reviewed by the owner with `scripts/peer_reports.py` (ids, reasons, the reported line; no names or emails), which can bar a user |
| Right to erasure | "Delete my account" switches Peers off first (closing a group left with one member), then removes the login; cascading deletes remove every row |
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
8. Write terms of use before Peers is open to real users, and decide how often reports are reviewed (`python scripts/peer_reports.py`).

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
| `test_companies_house`, `test_websearch` | Request shape, parsing, every failure as one error type, the key in no error or log, a bad company number never in an address |
| `test_fetcher` | Typed addresses, private and mapped addresses refused before and after redirects, the connection made to the checked address, size, time, redirects, robots.txt, non-HTML pages, text from a page |
| `test_research`, `test_repo_prep` | The four sources and each failing, register lines, numbered passages, results about other companies left out, the shared cache's 14 days |
| `test_prep` | The right-to-work line, edits, ticks, rebuilds keeping the user's words, what the interviewer is told |
| `test_routes_prep` | Search, research and packs end to end with every outside service replaced: the shared cache and the research limit, failures, no sources, not a UK company, a dissolved one, packs for jobs and applications, edits, refresh, isolation between users, no key in any response, no connection held during an outside call |
| `test_routes_tracker` | Rejecting with and without anything to compare, a failed or limited lesson keeping the rejection, follow-up drafts sending only what they should, goals, milestones shown once, the state for a new user, and another user reaching none of it |

No test can reach the real model, Companies House, a website or Tavily: an AI task or outside client that a test did not replace fails loudly. Database tests run against the real database inside transactions that are rolled back, so they leave nothing behind. Because the real register and real adverts are in that database, tests use names that cannot occur in real data and never count whole tables. Run the suite on its own: a second database-heavy job at the same time has caused dropped connections.

**Deploy to Vercel.** Not yet done for this version. `vercel.json` schedules the register reload for 05:00 UTC every Monday; it works only if `CRON_SECRET` is set in the Vercel project. The function may run for 120 seconds, to leave room for an import and one retry. A Python function may be 500 MB unpacked (Vercel's limit, read on 13 October 2026); with the Word and PDF packages the app is about 190 MB. `backend/fonts` must be in the bundle. Set `COMPANIES_HOUSE_API_KEY`, `SEARCH_PROVIDER` and `SEARCH_API_KEY` there for prep packs. Set `GITHUB_TOKEN` there: Vercel shares server addresses, and without a token GitHub allows only 60 requests an hour for each address. Add every variable from `backend/.env` to the Vercel project (use `BEDROCK_REGION`, not `AWS_REGION`, which Vercel reserves), add the Vercel address to Supabase's Site URL and Redirect URLs, then deploy. `vercel.json` builds the frontend, runs `app.py` as one function in London (`lhr1`), and leaves tests and scripts out of the bundle.

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
- Peers is removed until its step makes it real.
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
- A company brief is only as good as what was found: a small company with a thin website gets a short brief. Tavily's date for a news result is its estimate of when the page was published or last updated.
- A search result is kept only if it names the company's first word, so two companies that share a first word are not told apart.
- "None that the company's own site already answers" is asked of the model for questions to ask; code cannot check it.
- A site that blocks automated readers in robots.txt, or that builds its pages with JavaScript, gives no website lines.
- A figure in a brief statement, in digits or in words for ten or more, must be in its page; "5,000" and "five thousand" are not taken as the same, so an honest line worded differently from its page is dropped.
- Looking up Companies House is not limited per user; heavy use by one person could use up the app's allowance of 600 requests in 5 minutes.
- A pack does not change when the user's stories or achievements change; Refresh rebuilds it.
- A draft can still embellish what code cannot check, such as "yesterday" or a course project described more grandly. The page asks the user to read and change it before sending.
- LinkedIn's people search opens only for someone signed in to LinkedIn, and a free account can add a note to only about three invitations a month.
- Meetup gets no link for a remote location; only Eventbrite's online search was checked.
- Events are typed in by the user. Nothing is listed for them, and there are no email reminders.
- A professional body is suggested only when a target role's name contains one of its words; a field with no match gets none.
- With only a few users, most people who switch Peers on wait; a match needs someone else on the list.
- A proposal lapses after 7 days only when someone in it next opens the app; until then it stays open.
- There is no admin screen: reports are read and acted on with the script, and a report about someone goes when either account is deleted.
- A WhatsApp link shows the user's phone number to their group; the consent screen and the link box say so.
- The field suggestion is asked for each time the consent screen opens (once per AI action).

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
| `agency` | Reed says agency, or the name contains recruit, career, staffing, resourcing or RPO | "Recruiter or job board advert; employer not named." Scored and shown as a job |
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
| Quotes are real | A phrase in quotation marks in the reason, double or single, straight or curly, must appear in the feedback, the CV or the advert; in the suggested change, a phrase in double quotes must. Single quotes in the change are how the model suggests new wording ("such as 'Presented findings to senior managers'") and are allowed. An apostrophe ("you're", "employer's") is not a quotation mark | The same |
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
| Automated backend suite | 1,341 passed, 0 skipped, against the real database | 14 Oct 2026 |
| Frontend | Lints with no errors and no new warnings; builds | 14 Oct 2026 |
| Migration `007_tracker_habits` | Applied to the real database; open applications without a follow-up date were given one | 14 Oct 2026 |
| Real model, one call per AI task (`live_check.py`) | 28 of 28 passed: the 24 from before and 4 new (a lesson with feedback, without feedback, without an advert; a follow-up draft), 1 to 3 seconds each. After the review fixes the three lesson checks passed twice more, 6 of 6 with no retry | 14 Oct 2026 |
| Real output read by eye | Eight lessons: each hedged, specific to the CV and advert, and using the feedback only when it was given; the first ones spoke of "the candidate", fixed. Seven drafts: about 50 to 65 words, one ask, the right date and contact; the first ones lost their body to a greeting on the same line or kept a second sign-off, fixed | 14 Oct 2026 |
| Home and Applications against the real backend and model, as a temporary user whose data was never saved | The panel showed every field; notes, date posted and link saved and were still there after a reload. A card moved Applied, Phone screen, Interview, Offer showed each change with its date, and Offer showed nothing to follow up. Dropping a card on Rejected asked the two questions without moving it, and Cancel left it at Applied; answered "after an interview" with feedback, it gave a lesson about this job's CV and the feedback, which also appeared under What you have learned and in the panel. A card with no CV or advert gave the fixed message and made no AI call. A real follow-up draft was addressed to the contact, dated right and signed with the user's name; Mark as followed up moved the date a week on and took it off Follow-ups due. Setting goals of 1 and 0 made the week met and the streak 1, and took the goal tasks off the plan. Three milestones showed in one banner and not again after a reload; two more reached later showed once each. Open CV opened the version that was sent. Move to No reply worked from Home. At phone width the panel filled the screen with no sideways scroll | 14 Oct 2026 |
| Defects that check found, each fixed test first | An application logged late never counted as quiet; Move to No reply left a follow-up due; "1 of 1 applications" | 14 Oct 2026 |
| A fresh review of the whole branch (a separate reviewer on the most capable model) | Ready to merge with fixes; no critical findings. Fixed, each with a test or a browser check that failed first: a quote in single quotes escaped the quote check; the question form started a card already at "Rejected after interview" on "at the CV stage", and could undo a rejected stage picked from the menu; Cancel did nothing once Save was pressed, and a lesson could land on a card moved out of Rejected meanwhile; a greeting such as "Hello!" took the first clause of a draft with it, and a closing "Many thanks for..." sentence was cut; Escape lost an edit not yet saved, and one refused edit reset every field; "Ended at the cv stage"; the "Also worth fixing" card, dropped from Home without a recorded reason, is back. The same checks were then repeated on the pages as a temporary user | 14 Oct 2026 |
| The database afterwards | No trace of the temporary user | 14 Oct 2026 |

**Not yet verified:**

- **A signed-in session.** The pages were driven without the login screen, through a temporary check page that was then removed.
- **The owner's own applications.** The migration gave the open ones a follow-up date a week after they were sent, so they will show as due at once; they have not been looked at.
- **Dragging a card with a real mouse.** Drops were driven with simulated drag events and the stage menu.
- **A second account in the browser** starting at zero (hand check 7). Proved by automated tests only.
- **Real weeks passing.** Streaks across weeks, the weeks the clocks change, milestones at 10, 25 and 50 applications and streaks of 4 and 8 weeks are proved by tests with set dates, not by living through them.
- **How the pages look**, beyond the panel at phone width.
- **Anything on Vercel.**

## 23. Interview preparation (step 5)

**Where it starts.** "Prepare" beside the job picker on Interview coach, and "Prepare for this interview" on any application at Phone screen or Interview. Both open the Prep packs tab, which also lists the user's packs. If the job or application already has a pack, it opens.

**Confirming the company.** The employer's name (editable) is looked up on Companies House and up to five matches are shown with their town, status and year. The user picks one, "None of these" or "Not a UK company", and may type the website. Without a register entry the pack still builds and says so.

**Research** (`POST /api/companies/research`, `research.py`). Companies House's profile, the employer's home page and up to five useful pages of the same site (about, careers, values, news and the like), a news search for the last year and a competitor search all run side by side. Any of them may fail; the brief then says what is missing ("Not included: the news search"). The register's lines are written by code. Everything else goes to the model as numbered passages: the website's text split between lines (each page in turn, at most 18 passages), then each news and competitor result that names the company. The model returns statements, each citing one passage, and code keeps a statement only if:

| Rule | Check in code |
|---|---|
| It came from something the app fetched | Its passage number is one that was sent ("3", "[3]" and 3 are read alike) |
| It is in one of the six sections | What they do, size and age, values, products and projects, news, competitors |
| No figure was invented | Every number in it is in its passage ("1,200" and "1200" alike) |
| No words were put in the company's mouth | A phrase in double quotes is in its passage; a value carries a quote found there word for word (case, spacing and curly quotes aside), shown in the page's own wording |
| News is news, and recent | It cites a news result; the date shown is the result's; a result older than 12 months is left out; one with no date is shown as "Undated" |
| Competitors are attributed | Shown as "According to <source>" |

If statements came back but none survived, the model is asked once more, then the page shows Retry; nothing is kept from a failed attempt. If nothing was fetched at all, the model is not asked and the brief says nothing was found. The result is stored in `companies` and reused by anyone who prepares for the same company, under the same name and website, within 14 days, or within an hour if a source was missing for a passing reason. Form controls are left out of a page's text, not whole forms, so older sites built inside one form are read; a page with no text counts as unread. On 14 October 2026, for Monzo with the register left out (see section 24), the sources took 2.3 seconds and the brief 30: four pages, eight news results from the last three weeks, five competitor pages, nineteen lines.

**The pack** (`POST /api/ai/prep`), one AI action, built from the research, the advert (or a note that none was recorded), the user's course, achievements and stories:

| Part | What it is, and what code checks |
|---|---|
| Company brief | The research, copied into the pack, with "Researched on" and Refresh. Every line links to its page |
| Why this company, for you | Up to three talking points, each joining one fact to one achievement, both real and shown beneath it, using only their figures |
| Tell me about yourself | Three short paragraphs, 110 to 260 words, no figure from outside the input. Editable; the user's version survives Refresh |
| Likely questions | Five to eight, each with the competency it tests, why it is likely, and "Use your story: <title>" or "No story yet" with a link to write one. A story id that is not the user's becomes "No story yet" |
| Questions to ask them | Five, each linked to the fact it came from where there is one. The user ticks at most three |
| Your right-to-work answer | Written by the app from the visa type and end date (the owner's wording), editable, with "That answer is yours to add. This is not immigration advice." |
| On the day | Phone, video or in person (starting at Phone for a phone screen), with a checklist for each and the UK norms already in the app |

The pack prints from the browser: the menu, buttons and boxes are left out, the user's own text is printed, only the ticked questions are printed when any are ticked, and every source prints its address.

**Story coverage.** STAR stories shows the eight competencies (teamwork, leadership, problem solving, communication, handling a setback, initiative, influencing, working to deadlines) with the stories that show each, or "No story yet". Stories are tagged when written; "Tag my stories" tags older ones; the edit form has eight tick boxes, at most three.

**The mock interviewer.** When the job picked on Practice sessions has a pack, the interviewer is told a company summary of at most 600 characters (what they do, products, news) and, in the job-specific and behavioural sessions, the pack's likely questions (at most 1,200 characters), and asks its three questions from them. The page says "Using your prep pack".

## 24. Verification record for step 5

| Check | Result | Date |
|---|---|---|
| Automated backend suite | 1,679 passed, 0 skipped, against the real database | 14 Oct 2026 |
| Frontend | Lints with no errors and no new warnings; builds | 14 Oct 2026 |
| Migration `008_interview_prep` | Applied to the real database | 14 Oct 2026 |
| Real model, one call per AI task (`live_check.py`) | 33 of 33 passed: the 28 from before and 5 new (a cited company brief, real research of one company, a prep pack, tagging stories, a story's competencies). After the review fixes the six step 5 checks passed again | 14 Oct 2026 |
| Real research | Monzo through the live Companies House register, its own website (4 pages), Tavily (8 news results from the last three weeks, 5 competitor pages) and the model: a 28-line brief in 14.5 seconds, nothing missing (21 lines in 10 seconds after figures in words were checked too). Every line cited its page and every value was quoted word for word | 14 Oct 2026 |
| Companies House key | The first key given was for Companies House's test environment: it worked on their sandbox and was refused by the live service. The Live key added afterwards works | 14 Oct 2026 |
| What the real model showed, each fixed test first | It wrote the pitch at about 120 to 140 words even when asked for more (now three paragraphs, 110 to 260 words, and the page says "About a minute to 90 seconds"); a pitch quoting a company figure was refused (figures from the company facts are now allowed); it sometimes named the wrong achievement for a talking point (that point is dropped by the figure check; the prompt now asks for the achievement the point describes) | 14 Oct 2026 |
| Interview coach against the real backend and model, as a temporary user whose data was never saved, with Companies House, the website and the search replaced by made-up company pages | Prep packs tab with its empty state; Prepare from a saved job: two register matches with town, status and year, a website typed, the pack built in about 20 seconds with every section; source links open the page in a new tab; three questions ticked and the other two refused; an edited pitch and the interview type kept on the server; Refresh kept the edited pitch and the type and cleared the ticks; Prepare from an application at Phone screen with no saved job and "It is not a UK company": a second pack, starting at Phone; STAR stories: the coverage grid, "Tag my stories" with the real model, three tick boxes at most when editing; Practice sessions with a packed job says "Using your prep pack" | 14 Oct 2026 |
| Defects that check found, each fixed | Search results about another company reached the brief (a news or competitor result must now name the company); a value's quote was shown twice; the reasons for likely questions spoke of "the candidate" and started in lower case | 14 Oct 2026 |
| Voice agents | The mock interviewer's prompt updated on ElevenLabs with `setup_agents.py` (both agents updated in place) | 14 Oct 2026 |
| A fresh review of the whole branch (a separate reviewer on the most capable model) | Ready with fixes; nothing critical. All findings fixed, each with a test that failed first: refreshing or repeating research within 10 minutes cost nothing against the daily limit (every research now counts, and a failed rewrite after a refresh does not research again); a different typed name with a real company number changed every user's research for that company (the name is now part of the key); an edit could be lost while the pack was rewritten or between two quick saves; a slowly sent page was not cut off; a passing failure was shared for 14 days; pages built inside one form read as empty; figures in words were not checked; the right-to-work line did not appear after visa details were added. The smaller points were fixed too, at the owner's request: a page cut through a character or with one stray byte read as mojibake; a compressed page could expand in memory; IPv6 forms of private IPv4 addresses passed; a malformed link could stop a site being read; an emptied pitch was kept as the user's own; linking an application to a job after its pack was made gave two packs and a 500 when the job was deleted; a call could restart as the pack loaded | 14 Oct 2026 |
| The fixes against the real model, as a temporary user (direct requests to a scratch server, canned company pages) | Research 3.7 seconds, a pack 14.9 seconds with every part; two saves made from the same old copy both kept; Refresh counted against the limit, kept the edited pitch and cleared the ticks; an emptied pitch was no longer marked as the user's own | 14 Oct 2026 |
| The owner's missing transcript | The owner's mock interview on 14 October 2026 was heard by ElevenLabs (one answer of 20 words) and scored, but the page kept only the interviewer's line: pressing End before the last sentence's text arrived lost it, and the stored copy was read only when nothing at all had arrived. The page now reads ElevenLabs' stored copy whenever the user's own words are missing | 14 Oct 2026 |
| The database afterwards | No temporary user and no test company left | 14 Oct 2026 |

**Not yet verified:**

- **The transcript fix in a real call.** It reads ElevenLabs' stored copy when the user's words are missing; a call ended straight after speaking has not been tried since.
- **A signed-in session.** The pages were driven without the login screen, through a temporary check page (removed afterwards); the review fixes were checked by direct requests, not on the pages.
- **Printing a pack**, and **a voice call that uses a pack** (the interviewer's questions were not heard).
- **The owner's hand checks** in the step document: a well-known employer with five sources followed, a small company, an employer not on Companies House, news dates, story matching, a mock interview with a pack, printing.
- **A second account in the browser.** Proved by automated tests only.
- **Anything on Vercel**, including the new settings.

## 25. Networking (step 6)

**Where it is.** Networking sits in the menu between Applications and Journal, with three tabs: People, Events and Guide. Nothing on it is ever sent for the user: drafts are copied, and every link opens on the other site.

**People.** The user adds someone with their name, role, company, how they know them (alumnus of my university, tutor or lecturer, supervisor, met at an event, recruiter, introduced by someone, no connection yet), a profile link and notes. Each person shows where they are in the pipeline (To contact, Messaged, Replied, Chat booked, Chat done, Referral offered), what to do next and by when, and the steps so far. "Write a message" offers the drafts that fit them; "I sent my own message" counts a message the user wrote themselves; buttons record a reply, a chat booked or held, and a referral offered. At Chat booked three questions for the chat are shown, written by code with their role and company; at Chat done a notes box, the reminder to ask who else to talk to, and the thank-you draft. "Find people" gives LinkedIn searches for alumni of the user's university at the companies they saved jobs from and in their target roles, with the search words shown in case LinkedIn asks them to sign in first.

**Drafts** (`POST /api/ai/outreach`, `ai.outreach_draft`), one AI action each. The model writes the body only; code adds the greeting and sign-off with the user's name, and for a referral ask the job's title and address. Then:

| Kind | Shape, checked in code |
|---|---|
| LinkedIn connection note | At most 200 characters for the whole note, LinkedIn's limit; no request of any kind, not even a question |
| Request for a chat | Under 80 words; asks for 15 minutes; never for a job or a referral |
| Follow-up | At most two sentences and 60 words; says it is following up |
| Thank-you | At most 100 words; uses what the user typed under "one thing you learned", which must be given |
| Referral ask | At most 130 words; only for a saved job whose employer is the contact's company by the register's name rules; never says the user already works there |
| Recruiter introduction | At most 120 words; a start date the user typed appears as typed, otherwise only the course end month is given |
| Asking for a reference | At most 120 words; only to a tutor, lecturer or supervisor; names the user's target roles, never the referee's own organisation or team |

Every draft is also refused if it claims a connection the user did not enter (a shared university, a teacher, working together, meeting at an event, an introduction; a thank-you may say it was good to meet), names an event other than where they met, mentions visas or sponsorship, gives a figure or month that was not in what was sent, holds a web address or a placeholder in brackets. A refused draft is asked for once more, then the page shows Retry; nothing is ever cut to fit. Em dashes, and en dashes used as one, become commas.

**Events.** "Where to look" lists Meetup and Eventbrite searches for each target role and preferred location (Eventbrite's online search for "Remote"), the user's university careers events page once they paste it, and the professional bodies whose words appear in their target roles (BCS, Royal Statistical Society, CIPD, CIM, ICAEW, APM, CIPS, IET, IMechE, ICE, each checked on 14 October 2026). The user saves an event with its name, date and time (London), place or online, link and kind, as Interested, Going or Attended. "Prepare" writes a 30-second introduction from their pitch, three ways to start a conversation at that kind of event and one small goal, saved on the event. Once Attended, "Who did you meet?" adds people linked to the event, and each is told to message within 48 hours.

**The week.** Each message marked as sent counts once toward a third weekly target, beside applications and mock interviews, in the week of its London day. The target can be 0 to 20, and 0 is always met. Accounts that existed when step 6 arrived start at 0 with an invitation on This week to set one; new accounts start at 2. Goals saved before step 6 ask for no messages, so no past week or streak changes. Home lists the next three events under "Coming up". New milestones: first message sent, first reply from a contact, first chat, first referral offered.

**Referrals.** On an application, "Saved contact" links one of the user's contacts: their name becomes the application's contact name, and someone who offered a referral makes the source Referral, which the tracker's referral finding uses. That finding now links to Networking.

**Guide.** Fixed text with its sources: from stranger to referral in six steps; working with recruiters (agencies cannot charge for finding you work, GOV.UK); one UK project, internship or volunteering role (volunteering against voluntary work on a Student visa, UKCISA; GOV.UK's volunteering page, Reach Volunteering, Prospects); who can give a reference. Do-it.org was left out: on 14 October 2026 it redirected to an unrelated site.

## 26. Verification record for step 6

| Check | Result | Date |
|---|---|---|
| Automated backend suite | 1,951 passed, 0 skipped, against the real database | 15 Oct 2026 |
| Frontend | Lints with no errors and no warnings in the new or changed files; builds | 15 Oct 2026 |
| Migration `009_networking` | Applied to the real database | 15 Oct 2026 |
| Address patterns and sources (before building) | LinkedIn's help page gives 200 characters for a note; LinkedIn's people search sends a signed-out visitor to sign in and back; Meetup's and Eventbrite's searches open on the right city and topic (London, Manchester, Milton Keynes, online); ten professional bodies' events pages opened; GOV.UK, UKCISA, Reach Volunteering and Prospects say what the guide says; Do-it.org redirects to an unrelated site and is left out | 14 Oct 2026 |
| Real model (`live_check.py`, the step 6 checks) | 9 of 9 passed: a draft of each of the seven kinds and event preparation, read by eye | 15 Oct 2026 |
| What the real model showed, each fixed test first | Connection notes ran to about 290 characters (the room is now given in words too); a follow-up read as a first message; a referral ask said the user was "currently working on" the role; a reference request named the referee's organisation as where the user applies and offered to join their team; a spaced en dash | 15 Oct 2026 |
| Networking, Home and Applications against the real backend and model, as a temporary user whose data was never saved | Add a contact; a real chat request drafted, Mark as sent counted 1 of 2 messages; They replied, Chat booked (three questions), Chat done (notes, thank-you); Referral offered, then Saved contact on an application set the source to Referral and the contact name; an event saved and prepared by the real model; marked Attended, "Who did you meet?" added someone with "Message within 48 hours of meeting"; Coming up and three targets on Home; the Guide; the events page refused `javascript:` and saved a real address; an older account saw the invitation and set a target; a message 15 days old put "Follow up with ..." first on the plan; no sideways scroll at phone width | 15 Oct 2026 |
| Defect that check found, fixed | An open draft kept its old kind after the contact moved on | 15 Oct 2026 |
| A fresh review of the whole branch (a separate reviewer, Opus) | Ready with fixes; nothing critical. Fixed, each with a test that failed first: honest drafts were refused ("introduce myself", "not asking for a job", "lovely to meet", "valued my placement in your team", "working with you and your team"); a start date or lesson typed with a visa word, a web address or a dash could never pass and cost an AI action (now 422 before any action, and dashes match); after one follow-up the nudge never stopped (now "move on to someone else"); "Mark as sent" lost a first message's draft; "no connection" claims that slipped through ("both went to", "classmates", "pointed me", a thank-you naming an event); "Dr Shah" greeted "Hi Shah"; a company named like a web address failed every draft; a referral offered after linking left the source unchanged; the People filter could stick on an empty status; the plan's "Read the guide" opened People; the recruiters guide lacked "This is not immigration advice."; the privacy notice understated what drafts send | 15 Oct 2026 |
| The database afterwards | No temporary user and no test contact left | 15 Oct 2026 |

**Left from the review, for the owner to decide:** a double click on Save event saves it twice; the careers events page box hides while the search links fail to load; a contact with no company gets "Save the job you want a referral for first."; the edit form sends back the status it opened with; an older account that accepts the invitation mid-week gets the target this week (the form says the first goals apply this week).

**Not yet verified:**

- **The review's two page fixes in a browser** ("Mark as sent" keeping the draft, the People filter): changed after the browser check, proved by build and reading only.
- **A signed-in session.** The pages were driven without the login screen, through a temporary check page (removed afterwards).
- **LinkedIn's results** behind its sign-in page, and Meetup and Eventbrite results on another day.
- **The owner's hand checks** in the step document, including drafting all seven kinds for a real contact and a second account in the browser.
- **Real weeks passing** for the outreach target and streak, beyond tests with set dates.
- **Anything on Vercel.**

## 27. Peers (step 7)

**The one exception to "every user's data is private".** This is the only part of the app in which one user sees anything about another. All of it goes through one function, `peerdb.peer_view(conn, viewer_id, member_id)`, which returns an explicit list of fields and nothing unless both people are live members of the same open group, neither has blocked the other, and the member has Peers switched on and is not barred. Members of a proposal (or a newcomer to a group) see only first name, university, course and target roles; members of an active group who have both said yes also see how many of the three weekly targets were met this week (`2 of 3`, never the counts), the streak in weeks, the contact link, this week's check-in line, and whether the member has done nothing that counts for three weeks. Pages name a member by the id of their membership row, never by user id. Matching (`peerdb._candidates`) also reads other users' field, preferred locations, university and time waited, and returns only the group it made. The owner's report tools (`open_reports`, `mark_handled`, `bar`) are called only from `scripts/peer_reports.py`. All peers SQL lives in `peerdb.py`, apart from `repo.py`, whose rule (every function touches only the caller's rows) stays true.

**Switching on.** Peers is off by default. "Join a buddy group" shows, in two columns, what the group will see and never see, the code of conduct (approved by the owner on 15 October 2026), two ticks (18 or over; the code of conduct) and a field from a fixed list of 21. The field is suggested once from the user's target role names by the model (`ai.suggest_field`, one AI action; none without target roles; an answer off the list is ignored). Joining needs the profile's details complete. A barred user cannot join. The screen also shows "Your group will see you as": the user's own first name, university, course and target roles exactly as buddies see them (`peerdb.appears_as`, the same `_shown` read `peer_view` uses). The first name is the first word of the full name, so a name typed surname-first shows the surname; the user is told to put their given name first in Profile. The group page's own card repeats it (owner's choice, 24 October 2026, over a separate display name).

**Matching** runs when someone joins, goes back on the list, or opens Home or Peers while waiting; there is no scheduled job. Same field first; within it a shared preferred location (not "Remote"), then the same university, then a waiting person before a pair with room, then whoever has waited longest. A pair takes a third only in the field of both members. A different field is the last resort (owner's choice). Visa status is never used. Never proposed together: the same person, anyone blocked either way, and pairings "passed": declined, left unanswered for 7 days, or left. With nobody suitable the user waits: "You are on the list". **At most 3 new proposals per person per London day** (`peers.PROPOSALS_A_DAY`, owner, 24 October 2026). Each proposal of theirs counts, and so does each newcomer proposed into a group they are already in. After that they wait with "We will look again tomorrow", and neither they nor their group is anyone's candidate until then, so "Not this time" cannot be used to page through everyone. **A fair queue:** a person keeps their place on the list (`waiting_since`) through a proposal; whoever is turned down, turned away as a newcomer or left behind keeps it, while whoever said no, left or let a proposal lapse goes to the back; after a lapse those who said yes are matched first.

**Proposals.** Two people both say yes before a group forms. A third needs the yes of the newcomer and of each current member; until then each side sees only the other's first name, university, course and target roles. "Not this time" puts both back on the list, and matching runs again at once. A proposal unanswered for 7 days lapses on the next visit of anyone in it. A group never holds more than three live members: each holds one of three places, enforced by a unique index, so two people accepting at the same moment cannot make four.

**The group page.** Each member's card: who they are, targets met this week, streak, this week's line with Report, the contact link as a button, Send a nudge (one a day to each member, fixed wording: "<name> nudged you: one step today keeps your week on track."), Report and Block and leave. The group streak counts the weeks in a row, ending last week, in which every current member met all their targets, plus this week once all have, only since the group became active. The user's own card: their targets, streak, "What is your focus this week?" (140 characters, one per London week, editable that week) and an optional LinkedIn (`linkedin.com/in/...`) or WhatsApp (`wa.me/<number>`) link, refused for any other host or for anything but https. Home shows a small card with each member's first name and a tick for all targets met, and this week's nudges.

**Ways out.** Leave group (back on the list for a new one; "Find a new group" is the same, shown when a member has been inactive for three weeks); Block and leave (the blocker leaves, the other two stay; never matched again; a blocked newcomer is turned away instead); Report (four fixed reasons and optional details; the reported line disappears for the reporter at once and is copied into the report); Switch Peers off (out of any group at once, contact link cleared, the user's check-ins and the nudges they sent and received deleted). A group left with one member closes and that member goes back on the list. Deleting the account switches Peers off first. Switching off re-reads the membership once its group is locked and repeats until the user is in no group, so a proposal made while it waited for the lock cannot keep them; as a second guard, a group holding someone switched off or barred closes on the next visit of anyone in it, and a proposal in which nobody can be seen reads as waiting. When something on an open page has gone (404), the page refreshes itself.

**Reports** are reviewed by the owner with `scripts/peer_reports.py`: it lists open reports (ids, reasons, details, the reported line; no names or emails), marks one handled, or bars a user (Peers off, cannot be switched on again). What users wrote is printed with control characters escaped, so a line cannot rewrite the listing; barring an id nobody has says so.

**State reads.** Home and Peers call `status()` on every load. It reads London's today and Monday once, locks the group only when something in it may change, and for a member of a three-person group runs at most 30 statements (52 before 24 October 2026; a test holds the limit).

## 28. Verification record for step 7

| Check | Result | Date |
|---|---|---|
| Before building | 3 accounts in the database (the owner chose to build anyway); step 4's goals and streak take step 6's third target; LinkedIn's help page on profile addresses; WhatsApp's `wa.me` form from two guides citing its help page (the page itself did not load) | 15 Oct 2026 |
| Migration `010_peers` | Applied to the real database | 15 Oct 2026 |
| Tasks 1 to 3 | Whole backend suite: 2,030 passed, 0 failed, 0 errors | 15 Oct 2026 |
| Tasks 4 to 9 | Each task's tests seen failing first, then passing; whole-suite result recorded with the commit | 15 Oct 2026 |
| Real model (`live_check.py peers`) | 2 of 2: data roles gave "Data and analytics", solicitor roles gave "Law" | 15 Oct 2026 |
| Peers, Home and the privacy notice against the real backend and model, as three temporary users whose data was never saved | Consent screen with both columns, the code of conduct and a suggested field; on the list; a proposal showing only first name, university, course and target roles; both accept; check-in; a lookalike LinkedIn address refused and a real one shown as a button; a nudge on Peers and on Home; a reported line hidden from the reporter; a third person proposed into the pair and accepted by all three; leaving; blocking (all three back on the list, none rematched with someone they left or blocked); switching off; no sideways scroll at phone width | 15 Oct 2026 |
| Defects that check found, fixed | The link button read "Remove link" with nothing saved; a reported line read as if none had been written | 15 Oct 2026 |
| A fresh review of the whole step (a separate reviewer, Opus) | Nothing leaks: every detail about another user goes through `peer_view`, and the database enforces the three-member limit. Ready with fixes. **Not yet fixed:** the consent wording overstates privacy before everyone says yes and omits the inactivity flag; a name typed surname-first shows the surname as the first name; a stale page answers 404 without refreshing; a rare race can leave someone who switched off in another's proposal; "Not this time" can be used to see many people in a row (a daily cap is for the owner to decide); and 11 smaller points | 15 Oct 2026 |
| The database afterwards | No temporary user left; no peers rows from the checks | 15 Oct 2026 |
| The review's findings, all 16 fixed (plan task 10), each backend fix with a test seen failing first | Consent wording and the inactivity line; "Your group will see you as"; a page refreshes on 404; the switch-off race; 3 proposals a day; `peerdb.Gone` instead of any `LookupError`; report-script escaping and an unknown `--bar` id; the link checked in `set_contact_link`; no WhatsApp number starting with 0; no date in nudges; a fair queue; Home and proposal wording; nudge keys; 52 to at most 30 statements per state read, no group lock when nothing changes; `switch_on` refuses an unlisted field; tests read only their own report | 24 Oct 2026 |
| Whole backend suite after the fixes, and again after the second review's fixes | 2,168 passed, then 2,170 passed, 0 skipped both times; frontend lints with no errors and builds | 24 Oct 2026 |
| Peers and Home after the fixes, against a scratch backend (port 8001) with three made-up users in a transaction never committed, matching limited to them | Consent screen: accurate wording, the inactivity line, "Your group will see you as Zzqxzhang"; a proposal's wording; "You said yes. Waiting for Zzqxben to answer"; Home "Waiting for an answer"; the group page's "Your group sees you as"; Home's newcomer line and one nudge; a newcomer's "once both have said yes"; a stale page's nudge answered "That item no longer exists" and the page refreshed itself into the next proposal; after 3 proposals, "We will look again tomorrow"; no sideways scroll at phone width; no server errors | 24 Oct 2026 |
| The database afterwards | No `check-%@example.test` user left | 24 Oct 2026 |
| A fresh review of the fixes (three reviewers on privacy, matching and the rest; each serious finding sent to a separate skeptic) | No leak: everything about another user still comes only from `peer_view`. Confirmed and fixed test first: the daily cap did not cover people already in a pair, who could turn newcomers away all day (a newcomer now counts for the group's members, and a group whose member is at the cap takes nobody). Also fixed: "never your surname" was unconditional; "You have been shown 3" could be untrue for someone away; "an application" counts only with its CV; three tests that could pass with the bug present | 24 Oct 2026 |

**Not yet verified:**

- **The owner's three-account hand checks** in the step document, signed in for real.
- **A signed-in session.** The pages were driven without the login screen, through a temporary check page (removed afterwards).
- **Real weeks passing** for check-ins, nudge days, the group streak and the 7-day expiry, beyond tests with set dates.
- **Anything on Vercel.**

## 29. Calmer screens (24 October 2026)

**What changed.** Every screen was audited for text that repeats the screen, restates a heading or explains what a control already shows. 447 cuts were proposed, each checked by a second reviewer so that no information, source label, honesty line or behaviour was lost, and approved one by one by the owner. About 38% of the fixed copy is gone (the privacy notice keeps every word). Nothing a button, form, route or AI action does has changed.

**Shared pieces in `ui.jsx`**, so screens tuck text away the same way: `InfoTip` (an (i) that opens a short note on click, tap or Enter), `ShowMore` (a "Show more" or titled toggle for longer blocks), `Chips` (short facts as chips), `Spinner`, an optional `info` on `PageHead` and an optional `icon` on `Empty`. Every toggle is a button with `aria-expanded`; every icon-only button has an `aria-label` and a `title`.

**Decisions worth knowing.**
- Sidebar names: Pathways, CV and Interview (were Career pathways, Resume and Interview coach); routes are unchanged.
- On a phone the avatar button now shows in the top bar and opens Account, which holds Sign out; before, a phone had no way to reach Account.
- The privacy notice is in seven sections you open, with jump links; every section prints open.
- Printed prep packs still show every question, its reason, each fact and the UK norms, whatever is open on screen.
- Journal: a coach entry's text link reads "Full text", because a pasted background is filed as a coach entry too.
- Not done, for the owner to decide: the privacy notice's "Who processes it" as a table, since blank cells in a legal notice could read as "nothing".

**Verified, 24 October 2026.** Whole backend suite: 2,174 passed, 0 skipped. Frontend lints with no errors and builds. In a browser, signed out: Landing (212 words), sign-in and the privacy notice (all 7 sections open; about 1,370 words with all open, as before). Signed in, through a scratch backend with one made-up user in a transaction never committed: all 11 signed-in pages render with no crash and no sideways scroll at desktop width and at 375px, and every toggle opens to show its text (Pathways 155 words closed, 369 open). No `check-%@example.test` user left.

**Not verified:** the sidebar and the phone avatar button (the check page has no app frame), anything signed in for real, print output on paper, and the screens with an AI result on them (the model was not called).

## 30. The new look (24 October 2026)

**What changed.** A design board of 24 decisions, drawn from Mobbin's own stylesheet (neutral base, see-through greys, pill buttons, fast ease-out motion) and approved by the owner, then two changes the owner asked for after seeing it: no serif anywhere, and cards that rise slightly as they scroll into view. Only `index.html` (fonts), `index.css`, `ui.jsx` (`ShowMore`, `InfoTip`) and `App.jsx` (one wrapper) changed; no screen was rewritten and no behaviour changed.

**Tokens** (the top of `index.css`; every colour, font, size, corner, shadow and timing comes from them):
- Colour: page `#f6f7f6`, white cards, text `#0c0f0d`, greys made from that text at 66%, 48%, 4 to 9% and 8 to 14%; green `#24562c` is the only accent; red and amber only for status.
- Type: Geist for everything, with titles and the big numbers (visa days left, streaks, counts) bold (650) and tight (-0.035em to -0.045em), close to Mobbin's paid Saans; Geist Mono for small uppercase labels such as "Next step". Instrument Serif was tried on the board and dropped by the owner.
- Shape: cards 18px corners, inputs 10px and 44px tall with a soft fill, buttons and chips pills; hairline borders and a whisper of shadow; more room (card padding 24px, 32px between sections, 48px page margins on a laptop).
- Motion: one ease-out curve; 150ms for hover and press, 220ms for toggles and notes, 420ms for arrivals.

**Motion.** Buttons lift 1px on hover and settle on press; clickable cards lift 2px. Show more and (i) notes fade in and out (the closing animation plays before the content hides; the toggle reports itself closed at once). A page's cards fade up in sequence when it opens, at most 8, and the animation leaves no transform behind, so a fixed panel inside a page is never trapped. Progress bars fill from empty. Loading placeholders shimmer, the save toast slides up, a new milestone pops in. Anyone who asks their device for less motion gets none (a spinner still turns slowly).

**Scroll and hover (owner, 25 October 2026).** Cards, stat tiles and the landing sections that are out of view when they first appear wait faded and lowered, then rise into place once, a few at a time with a 70ms stagger, as they scroll into view (`ui.jsx` `useScrollReveal`, an IntersectionObserver in every browser; it marks them with a `data-reveal` attribute, so React re-rendering a class never traps one hidden). The observer's first report decides, after layout, so anything on screen then is never hidden; printing and reduced motion always show everything. On hover: every card deepens its border and gains a soft shadow, links draw their underline in from the left, menu icons nudge right, the brand mark tilts, button arrows slide forward and a plus turns, stat tiles and date boxes lift 1px, icon buttons grow a touch and press in, a landing feature's icon fills green, and the line under the open tab slides in (another tab hints at it on hover).

**Verified, 24 October 2026.** Frontend lints with no errors and builds; the whole backend suite passed (2,174, 0 skipped; the backend is unchanged). In a browser: Landing at desktop and 375px (fonts loaded, no sideways scroll, the brand name on two lines on a phone). The real app, sidebar included, against a scratch backend with one made-up user in a transaction never committed and a stand-in session (both removed afterwards): every page opened from the sidebar with no crash, no sideways scroll and no console error; on a phone the avatar shows in the top bar and opens Account; Show more and an (i) note open and close with their state right, including Escape and a click elsewhere. No `check-%@example.test` user left.

The scroll reveal and hover rules, 25 October 2026: lint and build clean; in the real app with the stand-in session, cards below the fold waited at load (none on screen hidden) and rose as the page scrolled, at desktop and 375px, with no sideways scroll; every hover rule present in the loaded stylesheet. Hover itself could not be seen: a simulated pointer does not hover in the check browser.

**Not verified:** a real sign-in, the hover effects under a real pointer, Safari and Firefox, and printing.

## 31. Contact us (25 October 2026)

**What it is.** A Contact us page (`pages/Contact.jsx`, address `#contact`) with one card for each of the two people who build the app, Akanksha Ankath first, then Dharan Teja Vipparla: name, email (opens the mail app) and a LinkedIn button (new tab). Their phone numbers were given but are left off on purpose, at the owners' choice. Like the privacy notice it opens signed in or out, and Back returns to the dashboard or the landing page. It is linked from the landing page's footer, beside Privacy, and from the bottom of the signed-in menu, just above the account row (on a phone, at the end of the scrolling menu row). The details live in the page itself, not the database: they are the owners' own, not user data. No backend change.

**Verified, 25 October 2026.** Frontend lints with no errors and builds; the whole backend suite passed (2,174, 0 skipped; the backend is unchanged). In a browser, signed out: the page at desktop width and 375px (no sideways scroll, no phone number anywhere on it, both mail and LinkedIn addresses right, LinkedIn opening in a new tab) and the footer link. Signed in, through the scratch backend and stand-in session (both removed afterwards, no `check-%@example.test` user left): the menu link sits above the account row, opens the page, and Back returns to the dashboard; on a phone it shows at the end of the menu row with no sideways scroll.

**Not verified:** a real sign-in, and that each email and LinkedIn address reaches its owner (they are as the owners gave them).
