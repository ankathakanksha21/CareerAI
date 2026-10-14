---
name: careerai-step-4-tracker-and-habits
description: Use when building, continuing or reviewing step 4 of the CareerAI roadmap - the full application record and detail panel, follow-ups, a lesson from each rejection, weekly goals, streaks, milestones, and the weekly plan on the home page
---

# Step 4: tracker and habits

**Status:** Built and merged into `main` (pull request 9), 14 October 2026. **Not finished:** the owner's hand checks. Design approved by the owner, 12 October 2026. **Depends on:** step 0. Uses steps 2 and 3 where they exist (sponsor status, full CV versions) and must work without them. **Size:** medium.
**REQUIRED:** follow `careerai-building-a-step`.

## Where it stands (14 October 2026)

- Built and committed, tasks 1 to 11 of `docs/superpowers/plans/2026-10-14-step-4-tracker-and-habits.md`. What it does and how is in `docs/ARCHITECTURE.md` section 21; what was verified and what was not is in section 22.
- Verified by the automated suite, by the real-model checks (the four new ones read by eye as well), and by running Home and Applications against the real backend and model as a temporary user whose data was never saved.
- **Left for the owner:** the hand checks below with their own login, in particular a real rejection with their own CV, a second account, and dragging a card with a mouse.

## Changed at build time (14 October 2026)

Where what was built differs from the sections below, this table is what is true.

| Change | Why | Decided by |
|---|---|---|
| "Where it ended" sets the stage: CV stage or phone screen give `rejected`, interview or final interview give `rejected_after_interview`; the answer is kept in `rejected_at_stage`. A rejection after a phone screen counts as a reply | Keeps the stage list and board; a rejection after a screen was a reply | Owner, with the plan |
| A lesson is asked for when either the CV or the job description was recorded | This document refuses only when neither is | Owner, with the plan |
| A lesson must be a possibility, claim no feedback that was not entered, quote only the inputs, and be written to "you"; checked in code | The real model wrote "the candidate" | Owner, with the plan; the last rule found by the real-model check |
| A lesson with no CV recorded may still say what the CV may not have shown | The real model wrote about the CV every time; refusing it left those applications with no lesson | Found by the real-model check |
| The follow-up draft's greeting and sign-off are added in code, with the user's name; the model never sees it. Body at most 80 words, no invented number, no placeholder | Under 90 words, nothing personal in the prompt | Owner, with the plan |
| A new application gets a follow-up date a week after applying; the migration gave open applications one too | The suggestion exists for every open application | Owner, with the plan |
| "Mark as followed up" sets the next follow-up a week after today | A late follow-up should not be due again the next day | Owner, with the plan |
| "No change for 21 days" applies at Applied only and counts from the last stage change, or the date applied; logging an application late is not a change | Only an unanswered application can have no reply | Owner, with the plan; the last part found by the browser check |
| An application at No reply asks for no follow-up | The browser check showed "Move to No reply" leaving it on Follow-ups due | Found by the browser check |
| Stage history starts on 14 October 2026; older applications show no history | Only real data | Owner, with the plan |
| Goals: applications 1 to 30, practice 0 to 14 | A goal of nothing would build a streak from nothing | Owner, with the plan |
| Several new milestones show in one banner, all marked seen | Otherwise an existing user would see a banner on each of the next visits | Owner, with the plan |
| The getting-started checklist stays on Home until it is complete | A new user's plan would otherwise ask for applications before they have a profile | Owner, with the plan |
| A lesson keeps the date it was made (`made_on`) | "What you have learned" lists the newest first | Owner, with the plan |
| The "few sponsor-listed roles" finding was already built in step 2; the new finding is three lessons pointing to the same page | – | – |
| `GET /api/state` gives each application its `history` | The detail panel needs it | Owner, with the plan |
| The migration is `007_tracker_habits` | 006 was used by step 3 | – |

## Goal

The tracker becomes the reason to come back each day. Every application carries its full record, nothing is forgotten after it is sent, each rejection teaches one thing, and the home page shows a weekly plan and a streak built only from what the user actually did.

This is the product's main differentiator in the owner's words: tracking quality applications, seeing where each one ended, and improving after every rejection.

## Decisions already made (do not re-ask)

| Decision | Detail | Decided by |
|---|---|---|
| Streak | Counts weeks in which the user met their own weekly goal. A missed day does not break it | Owner, 12 Oct 2026 |
| Rejections | The tracker asks where it ended and whether feedback was given, then suggests one specific change. One AI action each | Owner, 12 Oct 2026 |
| Tracker view | The drag-and-drop board, plus a detail panel with every field when a card is clicked. No table view | Owner, 12 Oct 2026 |
| Weekly goal | Set by the user. Defaults: 5 applications and 2 practice sessions a week | Recommended; approved 12 Oct 2026 |
| What counts as an application for the goal | One with a CV version recorded. Others are still logged, and shown as "no CV recorded", but do not count. This rewards the tailored application the product is built around | Recommended; approved 12 Oct 2026 |
| What counts as practice | A finished mock interview. There is no daily drill (owner's decision for step 5) | Recommended; approved 12 Oct 2026 |
| Week | Monday to Sunday, UK time | Recommended; approved 12 Oct 2026 |
| Follow-ups | In the app only. Suggested 7 days after applying. Nothing is ever sent for the user | Recommended; approved 12 Oct 2026 |
| Weekly plan | Built by rules from the user's real state, not by AI, and ticked automatically when the thing is done. No manual tick boxes | Recommended; approved 12 Oct 2026 |
| Milestones | Worked out from real data, shown once each as a small banner | Recommended; approved 12 Oct 2026 |
| What counts as an application, rechecked | Still only one with a CV version recorded | Owner, 14 Oct 2026 |
| When a goal change applies | The first goal a user ever sets applies to the current week as well, so a new user is not judged by defaults they never chose. Every later change applies from the following Monday | Owner, 14 Oct 2026 |
| Contact on an application | Two fields: the contact's name, and how to reach them. Only the name is ever sent to the AI (for a follow-up draft). The existing `contact` column becomes "how to reach them"; one new column, `contact_name` | Owner, 14 Oct 2026 |
| Milestone banner | At the top of Home, above "Your next best step", because it is shown once and marked seen as soon as it appears | Owner, 14 Oct 2026 |

## In scope

1. The detail panel with all eleven fields and a stage history.
2. Follow-up dates, a "Follow-ups due" list, and an AI-drafted follow-up message to copy.
3. The rejection question and lesson, and a "What you have learned" list.
4. Weekly goals, weekly streak, best streak.
5. Milestones.
6. The weekly plan and a rebuilt home page.
7. New tracker findings that use the richer data.

## Out of scope

A table view or CSV export; email or push reminders; sending messages for the user; calendar sync; daily streaks.

## What the user sees

**Application detail panel** (opens from a card):

| Field | Notes |
|---|---|
| Company, role | Editable |
| Status | The stage, with the date of each change underneath as a short history |
| Date applied, date posted | Editable |
| CV version | Chosen from saved versions, opens the CV |
| Source, link | Link opens the advert |
| Sponsor licence | Yes, No or Not known. Filled automatically for jobs from step 2; otherwise set by hand |
| Follow-up date | Suggested as 7 days after applying; "Mark as followed up" moves it on a week; can be cleared |
| Contact | Name and how to reach them |
| Notes | Free text |
| Lesson | Shown once the application is rejected (below) |

**Follow-ups.** Cards with a follow-up due show a marker. Home and Applications list "Follow-ups due". "Draft a follow-up" writes a short, polite UK-tone message from the role, company and date applied, for the user to copy. An application with no change for 21 days gets a suggestion to move it to "No reply".

**Rejections.** Moving a card to a rejected column opens two questions: where it ended (at the CV stage, after a phone screen, after an interview, after a final interview) and whether they gave feedback (optional text). The app then shows one lesson:

- "What probably happened", worded as a possibility, never a certainty.
- "One change for next time", specific and tied to this application.
- A button to the page that fixes it (Resume, Interview coach or Profile).

The lesson compares the CV that was sent with the job description. If neither was recorded, no AI call is made and the app says: "No CV or job description was recorded for this application, so there is nothing to compare. Attach both next time."

**What you have learned.** The Applications page lists the latest lessons. When three lessons point the same way, it becomes a finding.

**Home page**, top to bottom:

1. Your next best step (as now).
2. This week: progress against the two goals, the streak in weeks, the best streak, and an "Edit goals" link.
3. Weekly plan: up to five tasks, each with a reason and a link, ticked automatically.
4. Follow-ups due.
5. Visa countdown and search totals (as now).
6. A new milestone, when one has just been reached.

**Weekly plan tasks** are drawn, in this order of priority, from: follow-ups due; tracker findings; new matching jobs posted in the last 48 hours (if step 2 exists); applications still needed for the weekly goal; practice sessions still needed; story bank below six stories; achievements missing a number.

**Milestones:** first application; 10, 25 and 50 applications; first reply; first interview; first offer; first mock interview; story bank of six; streaks of 4 and 8 weeks.

## Data changes (migration `00N_tracker_habits`)

| Change | Detail |
|---|---|
| `applications` | Add `rejected_at_stage text`, `feedback_received text`, `lesson jsonb` (`{likely_reason, one_change, page}`), `last_followed_up_on date`. The columns `job_url`, `contact`, `notes`, `sponsor_licence`, `follow_up_on` already exist from step 0 |
| New table `application_events` | `application_id`, `from_stage`, `to_stage`, `at`. One row per stage change; the first row records the creation |
| New table `weekly_goals` | `effective_from date` (a Monday), `applications int`, `practice int`. A change of goal applies from the following Monday, so past weeks are always judged by the goal that applied then |
| `profiles` | Add `milestones_seen jsonb` |

## API

| Route | Purpose |
|---|---|
| `PATCH /api/applications/{id}` | Already exists; now records a stage change in `application_events` |
| `POST /api/applications/{id}/reject` | `{stage, feedback}` → sets the stage, stores the answers, returns the lesson. One AI action when there is something to compare |
| `POST /api/ai/applications/{id}/follow-up` | A follow-up message draft. One AI action |
| `POST /api/applications/{id}/followed-up` | Marks it and moves the follow-up date on 7 days |
| `PUT /api/profile/goals` | Set the weekly goals (from next Monday) |
| `POST /api/milestones/seen` | Marks milestones as shown |

`GET /api/state` gains `habits` (this week's counts and goals, streak, best streak, milestones reached, milestones not yet shown), `plan` (the weekly tasks) and `follow_ups_due`.

## How the streak is worked out

A pure function over the user's applications, journal entries and goal history:

1. A week runs Monday to Sunday, UK time.
2. A week is met when qualifying applications reach that week's application goal and practice sessions reach its practice goal.
3. The streak is the number of consecutive met weeks ending with last week, plus the current week if it is already met.
4. The current week never breaks a streak while it is still in progress.
5. Weeks before the account existed do not count for or against.

Nothing is stored about streaks; they are always recomputed, so they cannot drift from the data.

## AI tasks

| Task | Notes |
|---|---|
| Rejection lesson | Input: the job description, the CV content sent, the stage it ended, any feedback. Output: a hedged likely reason, one change, which page fixes it. Must not state a reason as fact, and must not invent feedback |
| Follow-up draft | Under 90 words, UK tone, one clear ask, no pressure. Uses only the role, company, date applied and contact name |

## Outside services and settings

None.

## Behaviours that must have tests

In addition to the standing list in `careerai-building-a-step`:

- Streak: no activity gives 0; three met weeks then a missed week gives 0; a met current week extends it; an unmet current week in progress does not break it; a week exactly at the goal is met; the Sunday-to-Monday boundary in UK time, including the weeks the clocks change.
- A goal change applies from the next Monday and does not alter earlier weeks.
- An application without a CV version is logged but does not count toward the goal.
- Lowering the goal today cannot create a streak in past weeks.
- Milestones are derived from data, each shown once, and a deleted application can remove an unreached one but never re-announce a seen one.
- Every stage change writes one event; the history lists them in order; deleting the application deletes its events.
- Rejecting with no CV and no job description makes no AI call and returns the fixed message.
- A failed lesson call still records the rejection and the answers, with a Retry for the lesson.
- The lesson never repeats feedback the user did not enter.
- The follow-up suggestion is 7 days after applying; marking followed-up moves it 7 days; an application at offer or rejected has no follow-up due.
- The weekly plan never contains more than five tasks, never a task whose page does not exist in this build (for example jobs before step 2), and a completed task disappears on the next load.
- User B cannot read or reject user A's application, or see their events, goals, lessons or milestones.

## Check by hand

1. Open a card: all eleven fields are there, editable, and persist after a reload.
2. Move a card through three stages: the history shows each with its date.
3. Reject an application that has a CV and job description: the two questions appear, then a lesson that refers to this job. Reject one that has neither: the fixed message appears.
4. Set a follow-up for today: it appears on Home and Applications; "Draft a follow-up" gives a usable message; "Mark as followed up" moves it on.
5. Set goals to 1 application and 0 practice; log one application with a CV: the week shows as met and the streak moves.
6. Reach a milestone: the banner appears once and not again after a reload.
7. A second account starts at zero for everything.

## Task outline

1. Migration; events written on every stage change, including through the existing drag and drop.
2. The detail panel and its fields.
3. Follow-ups: suggestion, list, mark, draft.
4. The rejection flow and lesson task; the "What you have learned" list.
5. Goal history, the streak function and its tests.
6. Milestones.
7. Weekly plan rules.
8. The rebuilt home page.
9. New findings: repeated lessons; few sponsor-listed roles in a family (only if step 2 exists).
10. Live checks, hand checks, documentation.

## Done when

A user can open the app on any day and see what is due, what to do this week and how the week is going, every application shows its whole story, and each rejection leaves behind one concrete thing to change.

## Verify at build time

- Which earlier steps have shipped, and switch the dependent parts on or off accordingly: sponsor status and "new jobs" tasks need step 2; lessons are richer with step 3's full CV content.
- That the weekly-goal definition ("an application counts when a CV version is recorded") still matches what the owner wants once they have used the tracker for real.
