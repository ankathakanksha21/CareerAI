---
name: careerai-step-6-hidden-market
description: Use when building, continuing or reviewing step 6 of the CareerAI roadmap - networking contacts and their pipeline, AI-drafted outreach messages, saved networking events, search links for finding people and events, referrals, and the outreach weekly target
---

# Step 6: the hidden market

**Status:** Built on branch `step-6-hidden-market`, 15 October 2026 (plan `docs/superpowers/plans/2026-10-14-step-6-hidden-market.md`). **Not finished:** the owner's hand checks. **Depends on:** step 4 (weekly goals and streak). **Size:** medium.
**REQUIRED:** follow `careerai-building-a-step`.

## Where it stands

- Built test-first, as the plan's ten tasks: migration `009_networking` (applied), the pipeline rules (`networking.py`), search links and professional bodies (`links.py`), the third weekly target, database functions, the two AI tasks, the routes, the guide and privacy notice, and the Networking page. What it does is ARCHITECTURE section 25; what was verified and what was not, section 26.
- The real model was tried on every kind of draft; five problems it showed were fixed, each with a test that failed first (the table below).
- The pages were checked against the real backend and model through a temporary check page as a throwaway user, not through the owner's sign-in.

## Changed at build time (15 October 2026)

Where what was built differs from the sections below, this table is what is true.

| Change | Why | Decided by |
|---|---|---|
| The model is never sent a contact's name or notes, nor the user's name; code adds the greeting and sign-off. The privacy notice says role, company and how you know them are sent | Less personal data to the model (the design assumed names were sent) | Plan, approved 14 Oct 2026 |
| Chat preparation is three fixed questions written by code; event preparation is saved on the event (`networking_events.prep`) | Free to read again | Plan, approved 14 Oct 2026 |
| The same step with the same person on one London day is recorded once (`outreach_events.on_day`); a deleted contact's steps stay with the contact cleared | "Marking the same message sent twice does not count twice"; the owner's answer on deleting | Plan; owner, 14 Oct 2026 |
| A reference is asked only of a tutor, lecturer or supervisor; a referral only for a saved job whose employer matches the contact's company by the register's name rules | Neither request should embarrass the user | Plan, approved 14 Oct 2026 |
| `profiles.outreach_default`: 0 for accounts that existed at the migration, 2 after; goals saved before step 6 count no messages; the target is 0 to 20 | The rule for existing users without changing any past week | Plan, approved 14 Oct 2026 |
| Limits the design left open: follow-up two sentences and 60 words, thank-you 100, referral ask 130, recruiter introduction 120, reference 120, event introduction 30 to 90 words | A number the model can be held to | Plan, approved 14 Oct 2026 |
| No draft may mention visas or sponsorship, a month or figure not given, a web address or a placeholder; em dashes and spaced en dashes become commas | Visa facts are never sent, so anything said would be invented | Plan; build-time ruling for en dashes |
| A connection note is told its room in words as well as characters | The real model wrote about 290 characters when asked for 179 | Build-time ruling |
| A follow-up must say it is following up | The real model's follow-up read as a first message | Build-time ruling |
| A referral ask may not say the user already works in the role or at the company; the prompt says the job is not theirs yet | The real model wrote "currently working on a Junior Data Analyst role" | Build-time ruling |
| A reference request is given the user's target roles and may not name the referee's organisation as where the user applies, or ask to join their team | The real model did both | Build-time ruling |
| Meetup gets no link for a remote location; only Eventbrite's online search was checked | Only checked patterns are used | Build-time ruling |
| The weekly plan's outreach task is "Message <name>" or, with nobody at To contact, "Find someone to message"; a contact follow-up comes straight after application follow-ups | The plan should say how to meet each target | Plan, approved 14 Oct 2026 |

## Goal

A user with no UK network builds one on purpose: they know where to look for people and events, keep track of everyone they contact, send short messages that ask for advice rather than a job, follow up, and turn conversations into referrals that show up in the tracker.

The owner's notes: many UK roles are filled through referrals or never advertised; international students arrive with no network; relationships are built slowly through alumni, tutors, meetups, societies and recruiters.

## Decisions already made (do not re-ask)

| Decision | Detail | Decided by |
|---|---|---|
| Events | The app builds search links that open on Meetup, Eventbrite, the user's university and professional bodies. The user saves the events they find. Nothing is scraped or invented | Owner, 12 Oct 2026 |
| Outreach target | A third weekly target beside applications and practice. The user can set it to zero | Owner, 12 Oct 2026 |
| Contacts | Added by the user. The app never looks people up or imports them | Recommended; approved 12 Oct 2026 (LinkedIn offers no API for this) |
| Messages | The AI drafts; the user copies and sends them wherever they like. The app never sends anything | Recommended; approved 12 Oct 2026 |
| No invented connection | A draft may mention only the link the user entered ("how you know them"). It must not claim a shared history, mutual contact or meeting that was not entered | Recommended; approved 12 Oct 2026 |
| Existing users | The outreach target starts at 0 for accounts created before this step, with an invitation to set one, so nobody's streak breaks without warning. New accounts start at 2 | Recommended; approved 12 Oct 2026 |
| What counts | Each message the user marks as sent, of any type, counts once toward the week | Recommended; approved 12 Oct 2026 |
| Start date in a recruiter introduction | An optional "When can you start?" box, used as typed. Left empty, the draft says only when the course ends, from the profile. Nothing about visas | Owner, 14 Oct 2026 |
| Deleting a contact | Their name, role, company, link and notes are deleted; each message marked as sent still counts in its week, so a past week or a streak never changes | Owner, 14 Oct 2026 |
| Connection note limit | 200 characters, the limit LinkedIn's help page gives, which fits every account | Owner, 14 Oct 2026 |

## Verified at build time (14 October 2026)

- **LinkedIn.** The help page "Personalize invitations to connect" gives 200 characters for a note, and a free account can add one to about three invitations a month. People search: `https://www.linkedin.com/search/results/people/?keywords=<terms>`. Signed out, LinkedIn shows its sign-in page and returns to the search afterwards; the terms are shown beside the link too.
- **Meetup.** `https://www.meetup.com/find/?keywords=<field>&location=gb--<City>&source=EVENTS` lands on "<Field> events near <City>, GB" (checked for London and Milton Keynes).
- **Eventbrite.** `https://www.eventbrite.co.uk/d/united-kingdom--<city-slug>/<keyword-slug>/` and `https://www.eventbrite.co.uk/d/online/<keyword-slug>/` land on the matching search (checked for Manchester, Milton Keynes and online).
- **Professional bodies**, each events page opened: BCS, Royal Statistical Society, CIPD (its branch network; branches are open to non-members and students), CIM, ICAEW, APM, CIPS, IET, IMechE, ICE.
- **Guide sources.** gov.uk's volunteering page (it lists NCVO, Reach Volunteering, NHS Volunteering and others); Reach Volunteering (skills-based, asks for three years' professional experience); Prospects' work experience and internships hub; UKCISA's student work page (volunteering is different from "voluntary work", which is unpaid employment and counts toward the weekly hours); gov.uk "Your rights as an agency worker: fees" (agencies cannot charge for finding you work). **Do-it.org now redirects to an unrelated domain and is left out.**
- **Step 4's streak** takes a third target without changing past weeks: goals set before this step count as an outreach target of 0.

## In scope

1. Contacts and their pipeline.
2. AI drafts for seven kinds of message.
3. Preparing for and recording an informational chat.
4. Saved events, with preparation before and follow-up after.
5. Search links for finding people and events.
6. Linking a contact to an application as a referral.
7. The third weekly target, new milestones, new findings.
8. The guide: how networking works in the UK.

## Out of scope

Automatic event listings; scraping or any LinkedIn automation; sending messages or connection requests; calendar sync; email reminders; matching users to each other (step 7).

## What the user sees

**Networking returns to the menu**, with three tabs.

### People

Each contact holds: name, role, company, how you know them (alumnus of my university, tutor or lecturer, supervisor, met at an event, recruiter, introduced by someone, no connection yet), a profile link, and notes.

The pipeline: To contact → Messaged → Replied → Chat booked → Chat done → Referral offered. Each contact shows what to do next and when ("Follow up: 14 days since your message").

**Draft a message** offers:

| Type | Shape |
|---|---|
| LinkedIn connection note | Within LinkedIn's character limit. Who I am, the link between us, no ask |
| Request for a chat | Under 80 words. One clear ask: 15 minutes for advice, not a job |
| Follow-up | Two sentences, two weeks after no reply |
| Thank-you | Within 24 hours of a chat. Mentions one thing learned, which the user types in |
| Referral ask | Only when a job at their company is saved. The job link and two lines on fit |
| Recruiter introduction | What I do, what I am looking for, when I can start |
| Asking for a reference | To a tutor or supervisor |

Each draft has Copy and "Mark as sent".

**Chat booked** opens a short preparation: three questions to ask (what the team works on, what good looks like in the first six months, what they wish they had known), adjusted to the contact's role. **Chat done** opens a notes box, a reminder to ask who else to talk to, and the thank-you draft.

**Find people** gives search links that open on LinkedIn: alumni of the user's university, narrowed by a target company or job title.

### Events

**Where to look:** search links for the user's field and city on Meetup and Eventbrite, a link to their university's careers events page (they paste it once), and professional bodies for their field.

**My events:** the user saves an event with its name, date and time, place or "online", link and type (meetup, careers fair, webinar, society, employer event). Status: Interested → Going → Attended.

- **Before:** "Prepare" gives a 30-second introduction built from their pitch, three ways to start a conversation at that kind of event, and a small goal.
- **After:** "Who did you meet?" adds contacts linked to the event and suggests a message within 48 hours.

Upcoming events appear on Home under "Coming up".

### Guide

Static, checked content: from stranger to referral in six steps; working with recruiters; getting one UK project, internship or volunteer role and why a UK referee matters; who can give a reference. Search links to real volunteering and university sites, no listings.

### Elsewhere

- **Applications:** the detail panel's Contact field can link to a saved contact. Linking one with "Referral offered" sets the source to Referral. The finding "Referrals work for you, but you rarely use them" regains its button.
- **Home:** the weekly progress shows three targets. The weekly plan can include "Message <name>" and "Follow up with <name>".
- **Milestones:** first message sent, first reply, first chat, first referral.
- **Findings:** "5 or more messages and no replies" points to the message drafts and the guide.

## Data changes (migration `00N_networking`)

| Table | Holds |
|---|---|
| `contacts` | Name, role, company, `relationship`, link, `status`, notes, `event_id` (nullable) |
| `outreach_events` | `contact_id`, `kind` (sent, replied, chat_booked, chat_done, referral_offered), `message_type`, `at` |
| `networking_events` | Name, `starts_at`, place, `online`, link, type, status, notes |
| `applications` | Add `contact_id` (nullable, set null on delete) |
| `weekly_goals` | Add `outreach int` |
| `profiles` | Add `university_events_url` |

All per user, with the standing rules.

Contacts are other people's details. Only what is listed above is stored; no email addresses or phone numbers are asked for.

## API

| Route | Purpose |
|---|---|
| `GET`, `POST`, `PATCH`, `DELETE /api/contacts[/{id}]` | Contacts |
| `POST /api/contacts/{id}/events` | Record sent, replied, chat booked, chat done, referral offered |
| `POST /api/ai/outreach` | `{contact_id, type, learned?, job_id?}` → a draft. One AI action |
| `GET`, `POST`, `PATCH`, `DELETE /api/networking-events[/{id}]` | Saved events |
| `POST /api/ai/networking-events/{id}/prepare` | Introduction, openers and a goal. One AI action |
| `GET /api/networking/links` | Search links built from the profile |

## AI tasks

| Task | Notes |
|---|---|
| Outreach draft | Input: the user's pitch, the contact's fields, the message type, and a saved job where relevant. Length limits enforced after the model replies; one retry if over, then an error. The only connection it may mention is the `relationship` value |
| Event preparation | From the pitch, the event type and name |

## Outside services and settings

None. Every link opens on the other site in a new tab; the app fetches nothing.

## Behaviours that must have tests

In addition to the standing list in `careerai-building-a-step`:

- A connection note over the limit is retried once and then refused; it is never cut mid-sentence.
- A chat request over 80 words is retried, then refused.
- A draft for a contact with "no connection yet" contains no claim of a shared university, employer, event or acquaintance.
- A referral ask with no saved job at that company answers 422 "Save the job you want a referral for first."
- A thank-you with nothing entered under "what you learned" is refused rather than inventing something.
- Search links: the field, city, company and university are URL-encoded; only the expected sites can appear; odd characters in a company name cannot break or redirect the link.
- An event in the past leaves "Coming up"; an event today stays until midnight UK time.
- Each "sent" counts once toward the week; marking the same message sent twice does not count twice.
- An account created before this step has an outreach target of 0; a new account has 2; a target of 0 is always met.
- Deleting a contact keeps the application and clears its link; deleting an event keeps its contacts.
- Linking a referral contact sets the application's source to Referral.
- User B cannot read, draft for or change user A's contacts or events.

## Check by hand

1. Add a real contact and draft each of the seven message types: each reads naturally, fits its limit, and claims nothing untrue.
2. Open each "Find people" and "Where to look" link: it lands on a sensible search on the right site.
3. Save an event for next week: it appears on Home; "Prepare" is usable.
4. Mark it attended, add someone you met: the contact is linked and a follow-up is suggested.
5. Move a contact through to "Referral offered", link them to an application: the source becomes Referral.
6. Mark two messages as sent: the weekly outreach target moves.
7. A second account sees no contacts or events.

## Task outline

1. Verify the link patterns and the guide content (below).
2. Migration; contacts and the pipeline.
3. The outreach draft task with its limits and honesty checks.
4. Chat preparation and notes.
5. Saved events, preparation, "who did you meet".
6. The search-link builder.
7. Referral link to applications; the third weekly target and its rule for existing users.
8. Milestones, findings, weekly plan tasks, "Coming up" on Home.
9. The guide content; privacy page update (people you add; their names and roles are sent to the AI for drafts).
10. Live checks, hand checks, documentation.

## Done when

A user can go from "I know nobody here" to a tracked list of people, a sent message they are comfortable with, a booked chat they are prepared for, and a referral recorded against an application, with every step counted toward their week.

## Verify at build time

- LinkedIn's current character limit for a connection note, and the address patterns for alumni and people search. If LinkedIn blocks deep links, link to the search page with the terms shown for the user to paste.
- Meetup and Eventbrite search address patterns for a keyword and a UK city.
- The list of professional bodies by field, each checked against its real website. Keep it short; leave a field out rather than guess.
- The volunteering and university sites named in the guide exist and say what the guide claims.
- That step 4's streak function accepts a third target without changing past weeks.
