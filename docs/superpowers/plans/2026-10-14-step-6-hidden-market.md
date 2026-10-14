# Step 6: The Hidden Market Implementation Plan

> **For agentic workers:** follow `careerai-building-a-step` stage 4. Every task is test-first: write the tests, watch them fail for the right reason, write the code, watch them pass, run the whole suite on its own, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user with no UK network builds one on purpose. They keep the people they contact in a pipeline (To contact → Messaged → Replied → Chat booked → Chat done → Referral offered), draft seven kinds of short message that claim no connection they did not enter, prepare for chats and events, find people and events through search links, record a referral against an application, and count messages sent toward a third weekly target.

**Architecture:** Two new pure modules, unit-tested: `networking.py` (the pipeline, each contact's next step, what is coming up, the outreach finding, chat questions) and `links.py` (search links and professional bodies, built only from fixed hosts). `habits.py` takes a third target. `ai.py` gains two tasks, `outreach_draft` and `event_prep`, each the model's own words checked in code, or an error with Retry. All SQL stays in `repo.py`; routes stay thin in `main.py`. A new Networking page with three tabs (People, Events, Guide), and small changes to Home, This week, the application panel and the findings.

**Tech stack:** unchanged. No new packages, outside services or settings. Every link opens on the other site; the app fetches nothing.

**Step document:** `.claude/skills/careerai-step-6-hidden-market/SKILL.md`, including the owner's answers and the build-time checks of 14 October 2026.

## Global constraints

- Everything in `CLAUDE.md` applies. The points that bite hardest here:
- **Only real data.** No sample contacts or events. Every tab has an empty state with one action. A draft is the model's own words or an error with Retry.
- **No invented connection.** A draft may claim only the link the user entered as "how you know them". Checked in code, not only asked for.
- **Other people's details.** A contact holds a name, role, company, how you know them, a profile link and notes. No email address or phone number is asked for. A contact's name and notes, and the user's own name, are never sent to the model.
- **The app sends nothing.** No message, connection request or email leaves the app. The user copies a draft.
- **No database connection held across a model call.** Count usage and read in one transaction, call the model, save in a second.
- **What a user types never goes in our addresses.** Search links are built on the server from the profile; the page receives finished addresses.
- **Search links** use `https` and only `www.linkedin.com`, `www.meetup.com`, `www.eventbrite.co.uk`, the listed professional bodies, and the user's own university events page (http or https only).
- **Every new table and route** gets the standing tests: rows deleted with the account, RLS on, no browser privileges; 401 without a token, 422 for a malformed id, 404 for another user's id; the daily AI limit on drafts and event preparation.
- British English, no em dashes in UI copy or prompts.
- Commit after every task with the suite passing, as `ankathakanksha21`. Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push unless asked.

## What the checks before building found (14 October 2026)

| Checked | Result |
|---|---|
| Earlier steps | 0 to 5 merged into `main` (step 5 as pull request 10, `95682e8`). Step 4's goals, streak, milestones and weekly plan exist |
| Baseline | Branch `step-6-hidden-market` from `main` at `95682e8`: 1,679 backend tests pass; the frontend lints with no errors and builds |
| Settings | None needed |
| Verify-at-build-time list | Recorded in the step document: LinkedIn note 200 characters; LinkedIn, Meetup and Eventbrite address patterns opened; ten professional bodies opened; guide sources checked, Do-it.org left out |
| Streak | `habits.goal_for` and `_met` take a third target; goals set before this step count as an outreach target of 0, so no past week changes |

## Settled with the owner today

| Question | Answer |
|---|---|
| Start date in a recruiter introduction | Optional "When can you start?" box, used as typed; empty, the draft says only when the course ends |
| Deleting a contact | Their details go; their messages still count in their weeks |
| Connection note limit | 200 characters |

## Decisions this plan adds (for the owner to approve with the plan)

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| 1 | The model is never sent a contact's name or notes, nor the user's name. Code adds "Hi Priya," (or "Dear Dr Shah," for a reference) and the sign-off with the user's name | Less personal data to the model; a greeting is never misspelt | The model cannot vary the greeting |
| 2 | Chat preparation is three fixed questions written by code with the contact's role and company. No AI action | The step document names the three questions; code can fill them reliably and for free | Less variety |
| 3 | Event preparation is saved on the event (`networking_events.prep`), so reopening it is free; "Prepare again" writes a new one | One AI action, not one per visit | One more column |
| 4 | A contact's messages keep their week when the contact is deleted: `outreach_events.contact_id` is set to null | The owner's answer above | None |
| 5 | Marking the same kind of message sent to the same person twice on one London day counts once. Every other pipeline event is likewise recorded once per person per day | "Marking the same message sent twice does not count twice" | Two genuinely different messages of one type to one person on one day count once |
| 6 | Recording an event only moves a contact forward (a thank-you sent after a chat does not move them back to Messaged). The user can still set the status by hand to correct a mistake | The pipeline reflects the furthest point reached | – |
| 7 | A reference request is offered only for a tutor, lecturer or supervisor (422 otherwise). A referral ask needs a saved job whose employer matches the contact's company by the register's name rules ("Acme Ltd" = "ACME LIMITED"); otherwise 422 "Save the job you want a referral for first." | A reference from a stranger, or a referral to the wrong company, would embarrass the user | A contact at a differently named parent company cannot be asked |
| 8 | The outreach target is 0 to 20 a week. `profiles.outreach_default` is 0 for accounts that exist when the migration runs and 2 for every later one; it applies until the user saves goals. Goals saved before this step count 0. While the target is 0 and the user has never chosen one, This week invites them to set it | The step document's rule for existing users, without breaking any streak | One more profile column |
| 9 | Weekly plan: "Follow up with <name>" (14 days after the last message, no reply) right after application follow-ups; "Message <name>" (the longest waiting at To contact), or "Find someone to message" when nobody is, while the outreach target is not met | The plan should say how to meet each of the three targets | The plan's five places fill faster |
| 10 | "Coming up" on Home: the next three saved events at Interested or Going whose London date is today or later | The step document's rule, with a small cap | A fourth event is only on Networking |
| 11 | Networking sits in the menu after Applications, before Journal | Where the old page sat relative to the others | – |
| 12 | The finding "5 or more messages and no replies": at least five messages marked sent and no contact has replied, booked or held a chat, or offered a referral. It links to the Guide tab | The step document's rule | – |
| 13 | Limits the step document leaves open: a follow-up at most two sentences and 60 words; a thank-you 100 words; a referral ask 130; a recruiter introduction 120; a reference request 120; an event introduction 30 to 90 words | Short messages get replies; a number the model can be held to | A retry when the model runs long |
| 14 | No draft may mention visas, sponsorship or the right to work, a month or a figure that is not in what was sent, a web address (code adds the job link), or a placeholder in brackets. Em dashes are replaced with commas | The visa facts are not sent, so anything said would be invented | An honest but unusual wording costs a retry |
| 15 | Linking a saved contact to an application also copies their name into the application's contact name, which the follow-up draft uses | One name per application | The name typed before is replaced |
| 16 | New milestones: first message sent, first reply from a contact, first chat (Chat done), first referral offered | The step document's list, named apart from the employer "first reply" | – |

## Review focus

1. Odd characters in a company, field, city or university ("AT&T", "C# / .NET", "Saint-Étienne", "../?x=1#y") must stay inside the query or path segment of a link to the expected host.
2. A contact set back by hand, then an event recorded: the status moves only forward from where it now is.
3. Events near midnight and across the clock change: "Coming up" by the London date, not UTC.
4. A draft that mixes an allowed connection with a forbidden one (an alumnus "we met at the fair"), and a thank-you after a chat (allowed to say it was good to talk).
5. Deleting a networking event that contacts point to, and a contact that an application points to.

---

### Task 1: Migration `009_networking`

**Files:** Create `backend/migrations/009_networking.sql`. Test: `backend/tests/test_migrate.py` (add the three tables to `TABLES`).

**Produces:** tables `contacts` (`id`, `user_id`, `name`, `role`, `company`, `relationship` checked in `alumni, tutor, supervisor, event, recruiter, introduced, none`, `link`, `status` checked in `to_contact, messaged, replied, chat_booked, chat_done, referral_offered` default `to_contact`, `notes`, `event_id` → `networking_events` on delete set null, timestamps); `outreach_events` (`id`, `user_id`, `contact_id` → `contacts` on delete set null, `kind` checked in `sent, replied, chat_booked, chat_done, referral_offered`, `message_type` checked in `connection_note, chat_request, follow_up, thank_you, referral_ask, recruiter_intro, reference_ask, own`, `at`, `on_day date` default London today; unique `(user_id, contact_id, kind, coalesce(message_type, ''), on_day)`); `networking_events` (`id`, `user_id`, `name`, `starts_at timestamptz`, `place`, `online bool`, `link`, `type` checked in `meetup, careers_fair, webinar, society, employer_event`, `status` checked in `interested, going, attended` default `interested`, `notes`, `prep jsonb`, timestamps); `applications.contact_id` → `contacts` on delete set null; `weekly_goals.outreach int` nullable, `0..20`; `profiles.university_events_url text`; `profiles.outreach_default int not null` added with default 0, then default set to 2. RLS on and privileges revoked for the three tables.

- [ ] Tests: the three tables have RLS and no browser privileges (via `TABLES`); all three are deleted with the user; deleting a contact keeps the application (link null) and keeps its outreach events (contact null); deleting a networking event keeps its contacts (link null); checks refuse an unknown relationship, status, kind, message type, event type and an outreach target of 21; the same `sent` row twice on one day raises `UniqueViolation`; a new profile's `outreach_default` is 2; the migration's two statements on `outreach_default`, run against a temporary table with one row in it, give that row 0 and the next row 2; `university_events_url` and `applications.contact_id` start null.
- [ ] Run `pytest tests/test_migrate.py`: FAIL (no tables). Write the migration, apply with `python migrate.py`, run again: PASS. Whole suite. Commit `feat: networking tables: contacts, their pipeline events, saved events, an outreach target`.

### Task 2: `networking.py`, the pipeline rules (pure)

**Files:** Create `backend/networking.py`. Test: `backend/tests/test_networking.py`.

**Produces:**
- `RELATIONSHIPS: dict[str, str]` (key → label: "Alumnus of my university", "Tutor or lecturer", "Supervisor", "Met at an event", "Recruiter", "Introduced by someone", "No connection yet"); `STATUSES`, `KINDS` (kind → the status it implies), `MESSAGE_TYPES` (key → label), `EVENT_TYPES`, `EVENT_STATUSES`; `FOLLOW_UP_DAYS = 14`, `AFTER_EVENT_DAYS = 2`, `COMING_UP = 3`, `NO_REPLY_MESSAGES = 5`.
- `advanced(status: str, kind: str) -> str`: the further of the two.
- `next_step(contact: dict, history: list[dict], today: date, met_on: date | None) -> dict` → `{"text", "due_on", "late"}`. To contact: "Send a first message" (met at an event: due two days after it, "Message within 48 hours of meeting"); Messaged: "Follow up: 14 days since your message" once 14 days have passed since the last `sent`, else "Waiting for a reply (sent N days ago)"; Replied: "Book a chat"; Chat booked: "Prepare for your chat"; Chat done: "Send a thank-you" until one is marked sent after the chat, then "Ask who else to talk to"; Referral offered: "Link them to your application".
- `follow_ups_due(contacts, outreach, today) -> list[dict]`: contacts at Messaged whose last message is 14 or more days old.
- `coming_up(events: list[dict], today: date) -> list[dict]`: Interested or Going, London date ≥ today, soonest first, at most three. Events arrive with `on_day` (their London date).
- `outreach_days(outreach) -> list[date]`: the day of each `sent` row.
- `findings(outreach, contacts) -> list[dict]`: the "no replies" finding (decision 12), id `outreach-no-replies`, type `network`, link `{"page": "networking", "label": "Read the guide", "tab": "guide"}`.
- `chat_questions(contact) -> list[str]`: the three questions with the role and company filled in, worded sensibly when either is blank.

- [ ] Tests (`test_networking.py`): `advanced` never moves back; each status's next step, including 13 against 14 days, an event-met contact due two days after the event, and a thank-you sent before the chat not counting; `follow_ups_due` ignores a contact who replied; `coming_up` keeps an event at 23:30 today, drops one yesterday, drops Attended, caps at three, orders by time; the finding needs five sends and disappears with one reply, booked chat or referral (by event or by status); `chat_questions` with and without role or company; British spelling, no em dash in any text.
- [ ] Run: FAIL (no module). Write, PASS. Whole suite. Commit `feat: the networking pipeline's rules: next steps, follow-ups, what is coming up`.

### Task 3: `links.py`, search links and professional bodies (pure)

**Files:** Create `backend/links.py`, `backend/data/professional_bodies.json` (name, events page, the keywords that select it, `checked_on: "2026-10-14"`). Test: `backend/tests/test_links.py`.

**Produces:** `search_links(*, university: str, locations: list[str], fields: list[str], titles: list[str], companies: list[str], events_url: str | None) -> dict` → `{"people": [...], "meetup": [...], "eventbrite": [...], "university": {...} | None, "bodies": [...]}`; each link `{"label", "url", "terms"}`. LinkedIn: `https://www.linkedin.com/search/results/people/?keywords=` + quoted "<university> <company or title>" (up to five companies from saved jobs, three titles from targeted families; the university alone when there are neither). Meetup: `https://www.meetup.com/find/?keywords=<field>&location=gb--<City>&source=EVENTS`. Eventbrite: `https://www.eventbrite.co.uk/d/united-kingdom--<city-slug>/<field-slug>/`, or `/d/online/<field-slug>/` for a "Remote" location. Fields are the targeted families' names (at most three), cities the preferred locations (at most three). `bodies_for(texts: list[str]) -> list[dict]`. `safe_url(value: str) -> str | None`: an http or https address with a dotted host and no spaces, else None (used for profile links and the university events page).

- [ ] Tests: each pattern exactly as verified; `&`, `#`, `?`, `/`, `..`, quotes and accents stay inside the query value or the slug (parse every URL back: scheme https, host in the allowed set, path and query as expected); an empty slug (field "C#" → "c") never yields `//`; duplicates removed; caps respected; no university → no LinkedIn links; "Data Analyst" selects BCS and the Royal Statistical Society, "HR Advisor" CIPD, "Marketing Executive" CIM, a field with no body gives none; `safe_url` refuses `javascript:alert(1)`, `ftp://x.y`, `http://localhost`, `https://a b.com`, accepts `careers.leeds.ac.uk/events` as `https://careers.leeds.ac.uk/events`; every body in the JSON has an https events page and a checked date.
- [ ] Run: FAIL. Write, PASS. Whole suite. Commit `feat: search links for people and events, and professional bodies by field`.

### Task 4: The third weekly target, milestones, plan and findings

**Files:** Modify `backend/habits.py`, `backend/analytics.py`. Tests: `backend/tests/test_habits.py`, `backend/tests/test_analytics.py`.

**Consumes:** `networking.outreach_days`, `networking.follow_ups_due`.
**Produces:** `DEFAULT_GOAL` gains `outreach: 2`; `goal_for(week, goals, default_outreach=2)` returns `outreach` (a goal row's `None` counts 0); `week_counts(..., outreach_days=())`, `this_week(..., outreach_days=(), default_outreach=2)` add `outreach` and `outreach_chosen`; `streaks(..., outreach_days=(), default_outreach=2)`; `_met` needs all three; `milestones(..., outreach=(), contacts=())` adds `first-message-sent`, `first-contact-reply`, `first-chat`, `first-referral` (by event or current status); `weekly_plan(..., contact_follow_ups=(), to_message=None, outreach_needed=0)` adds the tasks of decision 9; the referral finding links to `{"page": "networking", "label": "Find people"}`.

- [ ] Tests: a target of 0 is always met; 2 messages meet a target of 2 and 1 does not; a goal row from before this step (outreach `None`) leaves a past met week met; `default_outreach=0` with no rows gives 0 and an existing three-week streak stands; `outreach_chosen` false until a row has a value; a sent message's week is its London day; the four milestones each appear once, from events or status; plan tasks: "Follow up with Priya" after application follow-ups, "Message Sam" when the target is unmet, "Find someone to message" when nobody is at To contact, none once met, never more than five; the referral finding's link. Update the existing assertions that compare a goal dict to include `outreach`.
- [ ] Run: FAIL. Write, PASS. Whole suite. Commit `feat: an outreach target beside applications and practice; networking milestones and plan tasks`.

### Task 5: Database functions

**Files:** Modify `backend/repo.py`. Test: create `backend/tests/test_repo_networking.py`.

**Produces:** `list_contacts`, `get_contact`, `add_contact(conn, user_id, fields)`, `update_contact(conn, user_id, contact_id, fields)` (the event link checked as the user's own), `delete_contact`; `record_outreach(conn, user_id, contact_id, kind, message_type=None) -> dict | None` (one row per decision 5, `on conflict do nothing`; status moved forward under `for update`; returns the contact); `list_outreach(conn, user_id)` (with `on_day`); `list_networking_events` (with `on_day`), `get_networking_event`, `add_networking_event` (a naive `starts_at` read as London time), `update_networking_event`, `delete_networking_event`, `set_event_prep`; `set_university_events_url`; `set_goal(..., outreach)` and `list_goals` with `outreach`; `APPLICATION_FIELDS` and `_REFERENCES` gain `contact_id`, and setting it copies the contact's name and, at Referral offered, sets the source to `Referral` (decision 15 and the step document); `load_state` gains `contacts`, `networking_events`, `outreach`.

- [ ] Tests: user B gets nothing from and changes nothing of user A's contacts, events, outreach, event prep and university link; an event link or contact link to B's row is saved as null; `record_outreach` twice the same day gives one row and returns the contact; it never moves a status back; `starts_at` "2026-10-20T18:30" is 17:30 UTC in October and 18:30 UTC in December; linking a Referral-offered contact sets the source and the contact name, another contact only the name; deleting a contact or event as in task 1.
- [ ] Run: FAIL. Write, PASS. Whole suite. Commit `feat: contacts, their pipeline, saved events and the referral link to applications in the database`.

### Task 6: Two AI tasks: outreach drafts and event preparation

**Files:** Modify `backend/ai.py`. Test: create `backend/tests/test_ai_networking.py` (the model replaced through `llm.complete_json`, as the existing AI tests do).

**Produces:**
- `NOTE_CHARS = 200`; `DRAFT_LIMITS` per type (the spec's and decision 13's).
- `outreach_draft(*, kind: str, contact: dict, sender: str, about_me: str, university: str = "", event_name: str = "", job: dict | None = None, achievements: list = (), learned: str = "", start: str = "", course_ends: str = "", looking_for: list[str] = ()) -> dict` → `{"message": str, "words": int, "characters": int}`. `contact` carries `role`, `company`, `relationship` and `name` (the name used only by code for the greeting). The model writes the body only; code strips any greeting or sign-off it wrote (`_message_body`), replaces em dashes, adds the greeting, the job line for a referral ask (title, and the address when the saved job has one) and the sign-off, then checks the whole message.
- `event_prep(*, event: dict, about_me: str) -> dict` → `{"introduction": str, "openers": [str, str, str], "goal": str}`.
- Checks, each a failed attempt that is asked for once more, then `AIError`: over the limit (a connection note by characters of the whole note, the rest by words of the body); a claim of a connection not entered (alumni, tutor, supervisor or shared employer, met at an event, introduced) unless the relationship is that one, and the event's name only for "met at an event"; a connection note with an ask; a chat request without "15 minutes" or asking for a job or referral; a follow-up over two sentences; a thank-you that does not use what was learned; a recruiter introduction whose start differs from what the user typed; any mention of visas or sponsorship, a month or figure not in the inputs, a web address, a placeholder.

- [ ] Tests (one per check, and): a connection note over 200 characters is asked for again and then refused, never cut; a chat request of 80 words is refused, 79 accepted; "no connection yet" refuses "we both studied", "we met", "a mutual friend", "when we worked together", accepts the same draft without them; an alumnus may say "fellow Leeds graduate" but not "we met at the fair"; a thank-you may say it was good to talk; a supervisor may mention working together; the prompt never contains the contact's name, their notes or the user's name (captured from the fake); the greeting uses the first name after a title ("Dr Priya Shah" → "Hi Priya,", reference → "Dear Dr Shah,"); the referral job line is added by code; the event introduction outside 30 to 90 words, or with a figure not in the pitch, is refused; exactly three openers.
- [ ] Run: FAIL. Write, PASS. Whole suite. Commit `feat: outreach drafts that claim no connection the user did not enter, and event preparation`.

### Task 7: Routes and the state read

**Files:** Modify `backend/main.py`. Test: create `backend/tests/test_routes_networking.py`; extend `backend/tests/test_routes_tracker.py` for goals and the application link.

**Produces:** `GET`, `POST`, `PATCH`, `DELETE /api/contacts[/{id}]`; `POST /api/contacts/{id}/events` `{kind, message_type?}`; `POST /api/ai/outreach` `{contact_id, type, learned?, job_id?, start?}` (one AI action; 422 for a thank-you with nothing learned, a referral ask without a matching saved job "Save the job you want a referral for first.", a reference request to someone who is not a tutor or supervisor); `GET`, `POST`, `PATCH`, `DELETE /api/networking-events[/{id}]`; `POST /api/ai/networking-events/{id}/prepare` (one AI action; saved on the event); `GET /api/networking/links`; `PUT /api/profile/events-url` `{url}` (422 for an address `safe_url` refuses; empty clears it); `PUT /api/profile/goals` takes `outreach` 0 to 20 (left out: the target in force); `PATCH /api/applications/{id}` takes `contact_id`. `GET /api/state` gains `contacts` (each with `next`, `history`, `event_name`), `networking_events`, `coming_up`, the outreach count and `outreach_chosen` in `habits.this_week`, the new findings, milestones and plan tasks, and `options` for relationships, statuses, message types, event types and statuses. `_pages()` gains `networking`.

- [ ] Tests: each route 401 without a token, 422 for a malformed id, 404 for user B's id (and B cannot draft for, prepare, record against or link A's rows); a profile link `javascript:...` is 422; drafts and preparation count one AI action and answer 429 at the limit with nothing saved; a failed draft (the fake raises) is 502 and records nothing; marking sent twice counts once in `habits.this_week.outreach`; a thank-you with an empty `learned` makes no model call; a referral ask with a saved job at "ACME LIMITED" for a contact at "Acme Ltd" works, at another company is 422; an account whose profile has `outreach_default` 0 shows a target of 0 and the invitation flag, a new account 2; goals saved with `outreach` 3 apply from the right Monday; linking a Referral-offered contact sets the source to Referral; the state carries the new keys and `coming_up` drops an event from yesterday.
- [ ] Run: FAIL. Write, PASS. Whole suite. Commit `feat: networking routes: contacts, drafts, saved events, search links, the outreach target`.

### Task 8: The guide and the privacy page

**Files:** Modify `backend/data/content.json` (`networking_guide`: "From stranger to referral in six steps", "Working with recruiters", "One UK project, internship or volunteering role", "Who can give a reference"; each with sources), `backend/tests/test_content.py`, `frontend/src/pages/Privacy.jsx`.

- [ ] Tests: the four sections exist; every link is https on gov.uk, ukcisa.org.uk, reachvolunteering.org.uk, prospects.ac.uk or ncvo.org.uk; no em dash; nothing names Do-it. The guide says agencies cannot charge for finding work (gov.uk), that "voluntary work" on a Student visa counts toward the weekly hours while volunteering need not (UKCISA), that free LinkedIn accounts can add a note to only a few invitations a month, and carries "This is not immigration advice." where visas are mentioned.
- [ ] Privacy: the people you add (name, role, company, how you know them, profile link, notes), which never leave the app except role, company and how you know them, sent to the AI for a draft; saved events; search links show the other site your search words. Commit `feat: the networking guide and what the privacy notice says about contacts`.

### Task 9: The pages

**Files:** Create `frontend/src/pages/Networking.jsx`, `frontend/src/networking.js` (labels and small rules), `frontend/src/components/ContactCard.jsx` (next step, status, history, chat preparation and notes), `DraftMessage.jsx` (type, extra boxes, Copy, Mark as sent), `ContactForm` as `PersonForm.jsx`, `FindPeople.jsx`, `NetworkingEvents.jsx` (where to look, my events, Prepare, who did you meet), `NetworkingGuide.jsx`, `ComingUp.jsx`. Modify `App.jsx`, `ui.jsx` (menu), `pages/Home.jsx` (Coming up), `components/ThisWeek.jsx` (three targets, invitation, outreach in the form), `components/ApplicationPanel.jsx` (link a saved contact), `pages/Applications.jsx` and `components/Plan.jsx` (a link's `tab`), `index.css`.

- [ ] `npm run lint` with no new warnings and `npm run build`. Checked in the browser as in task 10. Commit `feat: the Networking page: people, events and the guide; three targets on This week; coming up on Home`.

### Task 10: Live checks, hand checks, documentation

**Files:** Modify `backend/scripts/live_check.py` (one draft of each of the seven types for a made-up contact, and one event preparation), `docs/ARCHITECTURE.md` (roadmap, decisions, code map, data model, API, AI layer, security, limitations, section 25 "Networking", section 26 its verification record), the step document (status, "Changed at build time"), this plan's status line.

- [ ] Run `live_check.py`: every check passes; read each draft by eye for honesty, length and tone; tighten a prompt for anything that fails, with a test for the rule it broke.
- [ ] Hand checks through the temporary signed-in page (memory note "Checking signed-in pages without a login"), against the real backend and model: the seven step-document checks, at desktop and phone width. The owner's own sign-in, LinkedIn's results behind its sign-in page, and Meetup and Eventbrite at a later date are listed as not verified.
- [ ] Final whole-branch review by a fresh reviewer on the most capable model; fix what it finds test-first; whole suite; documentation updated; commit.
