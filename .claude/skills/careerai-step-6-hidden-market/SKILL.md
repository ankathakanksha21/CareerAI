---
name: careerai-step-6-hidden-market
description: Use when building, continuing or reviewing step 6 of the CareerAI roadmap - networking contacts and their pipeline, AI-drafted outreach messages, saved networking events, search links for finding people and events, referrals, and the outreach weekly target
---

# Step 6: the hidden market

**Status:** Not started. Design approved by the owner, 12 October 2026. **Depends on:** step 4 (weekly goals and streak). **Size:** medium.
**REQUIRED:** follow `careerai-building-a-step`.

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
