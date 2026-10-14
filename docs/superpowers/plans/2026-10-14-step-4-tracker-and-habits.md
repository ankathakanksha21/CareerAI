# Step 4: Tracker and Habits Implementation Plan

> **For agentic workers:** follow `careerai-building-a-step` stage 4. Every task is test-first: write the tests, watch them fail for the right reason, write the code, watch them pass, run the whole suite on its own, commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status, 14 October 2026:** tasks 1 to 11 are built and committed, and task 12 is done except the owner's hand checks. A fresh review of the whole branch found no critical issues; its findings were fixed in one pass (see ARCHITECTURE section 22). Changes from this plan made while building, each for a stated reason: task 6 was built before task 5, so the milestones use the one rule for what counts as a reply; tasks 5, 7 and 8, and later the fixes with tasks 10 and 11, were committed separately after one shared run of the whole suite. The real model and the browser check found five things, each fixed test first: a follow-up's greeting on the same line as its body, and a sign-off after its last sentence; lessons about "the candidate"; an application logged late never counting as quiet; and "Move to No reply" leaving a follow-up due. A lesson with no CV recorded may still say what the CV may not have shown (the real model always did, and refusing it left those applications with no lesson).

**Goal:** Every application carries its whole record and stage history; follow-ups are suggested and drafted; each rejection asks where it ended and leaves one lesson; weekly goals, a weekly streak, milestones and a rule-built weekly plan appear on a rebuilt home page. All of it is worked out from what the user actually did.

**Architecture:** One new pure module, `habits.py`, works out weeks, goals, streaks, follow-ups due, milestones and the weekly plan from rows the state read already loads, plus three new reads (stage events, goal history, the London dates of mock interviews). Nothing about streaks or plans is stored. Two new AI tasks in `ai.py` (a rejection lesson, a follow-up draft) follow the existing pattern: the model's own result checked in code, or an error with Retry. All SQL stays in `repo.py`.

**Tech stack:** unchanged. No new package, no new outside service, no new setting.

**Step document:** `.claude/skills/careerai-step-4-tracker-and-habits/SKILL.md`. Where this plan adds to it, the addition is listed under "Decisions this plan adds" for the owner to approve.

## Global constraints

- Everything in `CLAUDE.md` applies. The points that bite hardest here:
- **Only real data.** A streak, a milestone and every plan task come from the user's own rows. No sample applications; test names cannot be real ("Zzqx Holdings Ltd").
- **Real result or an error.** A failed lesson keeps the rejection and its answers, and shows Retry. A failed draft shows Retry. Nothing is substituted.
- **No database connection across a model call.** Each AI route reads in one short transaction, calls the model, writes in a second.
- **Every new table and route** gets the standing tests: rows deleted with the account, RLS on, no browser privileges; 401 without a token, 422 for a malformed id, 404 for another user's id; the daily limit where it costs money.
- **Only the contact's name** may go to the model, never how to reach them. The user's own name never goes to the model.
- British English, no em dashes in UI copy or prompts.
- Commit after every task with the suite passing. Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push unless asked.

## What the checks before building found (14 October 2026)

| Checked | Result |
|---|---|
| Earlier steps | 1, 2 and 3 are merged into `main` (pull requests 7 and 8, and step 2 before them). So sponsor status on applications from Jobs, the "new matching jobs" task and lessons that read a full CV are all switched on. The "few sponsor-listed roles" finding already exists (step 2), so task 9 of the step document needs only the repeated-lessons finding |
| Baseline | Branch `step-4-tracker-and-habits` from `main` at `77b68f2`: 1,180 backend tests pass, the frontend lints and builds |
| Settings | None needed. `REED_API_KEY` is set, so the Jobs page exists in this build |
| Existing columns | `applications` already has `job_url`, `contact`, `notes`, `sponsor_licence`, `follow_up_on`. Stages are `applied`, `no_response`, `rejected` (shown as "Rejected at CV"), `screening`, `interview`, `rejected_after_interview`, `offer`. The board has one Rejected column holding both rejected stages |
| Practice | A finished mock interview is a `journal_entries` row of type `interview`, written by `POST /api/ai/interview-feedback` |
| Hard-coded goal | `Applications.jsx` has `WEEKLY_GOAL = 5` and counts every application. Replaced by the user's goal from the server |

## Settled with the owner today

| Question | Answer |
|---|---|
| What counts toward the goal, rechecked | Still only an application with a CV version recorded |
| When a goal change applies | The first goal a user ever sets applies to this week too; every later change from the following Monday |
| Contact | Two fields, name and how to reach them. Only the name goes to the AI. `contact` becomes "how to reach them"; new column `contact_name` |
| Milestone banner | At the top of Home |

## Decisions this plan adds (for the owner to approve with the plan)

| # | Decision | Why | Cost if wrong |
|---|---|---|---|
| 1 | "Where it ended" sets the stage: at the CV stage or after a phone screen give `rejected`; after an interview or a final interview give `rejected_after_interview`. The answer itself is kept in `rejected_at_stage` (`cv`, `screening`, `interview`, `final`). A rejection after a phone screen counts as a reply in every reply rate | Keeps the existing stage list and board; without the last rule a rejection after a screen would read as "no reply" | One more rule in `analytics.py` |
| 2 | The question form preselects where it ended from the stage the card was in (Applied or No reply: CV stage; Phone screen: after a phone screen; Interview: after an interview) | One click in the usual case | None; it can be changed |
| 3 | Moving a card out of Rejected clears where it ended, the feedback and the lesson | They describe a rejection that the user has just undone | A user who drags out by mistake answers again |
| 4 | A lesson is asked for when either the CV sent or the job description was recorded (the step document refuses only when neither is). The job description is the application's saved job, or failing that the job the CV was built for. The model is told which of the two is missing and must not describe a missing advert | Follows "if neither was recorded"; most applications made from Jobs have both | A lesson from the CV alone is thinner |
| 5 | Checks in code on a lesson: the likely reason must be worded as a possibility (it contains "may", "might", "could", "possibly", "probably", "perhaps", "likely" or "seems"); with no feedback entered, the likely reason may not mention feedback and neither part may say "they said", "you were told" or similar; a quoted phrase must appear in the feedback, the CV or the advert; with no advert recorded, the likely reason may not mention the advert. One retry, then an error with Retry | "Never stated as fact" and "never invents feedback" checked, not just asked for | An unusual but honest wording costs a retry |
| 6 | The follow-up draft: the model writes a subject line and the body only. Code adds "Dear <contact name>," (or "Dear Hiring Manager,") and "Kind regards," with the user's full name, so the user's name is never sent. The body must be at most 80 words (under 90 in all), contain no number that is not in the date applied, the role or the company, and no placeholder in brackets | Under 90 words, no invented detail, nothing personal in the prompt | A good draft that names a number is retried once |
| 7 | A new application gets a follow-up date of applied + 7 days unless one is given. If the date applied is corrected before any follow-up, the suggested date moves with it. The migration gives open applications without one (Applied, Phone screen, Interview) applied + 7 | The suggestion exists for every open application, old ones included | The owner's older test applications show as due at once; each can be cleared |
| 8 | "Mark as followed up" sets the next follow-up 7 days after today, not after the old date | A late follow-up should not be due again tomorrow | None |
| 9 | "No change for 21 days" applies to applications still at Applied. The last change is the latest stage event, or the date applied for an application made before this step (whose history was not recorded). Such an application appears under Follow-ups due with "Move to No reply" | Only an application nobody answered can have "no reply" | None |
| 10 | Stage history starts now. Applications made before this step show "Stage changes are recorded from 14 October 2026" rather than an invented history | Only real data | Older cards have an empty history |
| 11 | Goals: applications 1 to 30 a week, practice 0 to 14. An application goal of 0 is refused | A goal of nothing would build a streak from nothing | None |
| 12 | Application-count milestones (1, 10, 25, 50) count every logged application; first reply, interview and offer count a card that is there now or ever passed through that stage (from the history) | A milestone celebrates logging and progress; the goal is where the CV rule bites | None |
| 13 | When several milestones are new at once, one banner lists them all and they are all marked seen when it appears | An existing user would otherwise see a banner on each of their next five visits | None |
| 14 | Weekly plan tasks, at most five, in the agreed order: one task for all follow-ups due; one per tracker finding that links to a page in this build; new jobs from the last 48 hours; applications still needed; practice still needed; stories still needed to reach six; achievements still missing a number. A finding with no page (the referral one) is not a task | "Each with a reason and a link"; "never a task whose page does not exist" | None |
| 15 | The getting-started checklist stays on Home, under the weekly plan, until all six are done | A new user's plan would otherwise say "send 5 applications" before they have a profile; the step document's home order does not mention it | One more card for new users |
| 16 | A lesson stores the date it was made (`made_on`) beside `likely_reason`, `one_change` and `page`, so "What you have learned" lists the latest first. Three lessons with the same page make a finding ("Three of your rejections point to your CV") | The step document's "point the same way", made exact | Two lessons on different pages that say the same thing do not combine |
| 17 | No route beyond the step document's six. `GET /api/state` also gives each application its `history` | The detail panel needs it | None |
| 18 | The migration is `007_tracker_habits` | 006 was used by step 3 | None |

## Review focus

Inputs most likely to break this, each with a test in the task named.

1. **Clock edges.** An application on a Sunday and one on the Monday after; a mock interview at 23:30 UTC on the Sunday the clocks go forward (Monday 00:30 in London) and on the Sunday they go back; "today" at London midnight. (Tasks 3, 4)
2. **Undo and repeat.** Dragging a card out of Rejected and back; rejecting the same application twice; retrying a failed lesson must not write a second stage event or a second usage beyond the one retry. (Tasks 2, 8)
3. **Missing references.** The CV version or saved job deleted after the application was sent; an old-format CV; an application made before this step with no history. (Tasks 2, 5, 8)
4. **Odd model output.** A lesson stated as fact, feedback invented, a quote found nowhere, a page that is not one of the three, an empty change; a draft over 80 words, with "[Your name]", with its own greeting and sign-off, or with an invented date. (Task 7)
5. **Goal edits.** Setting goals twice in one week; setting the same goal again; lowering it on a Sunday; a first goal set this week, then changed. (Tasks 3, 4, 8)

## File map

| File | What changes |
|---|---|
| `backend/migrations/007_tracker_habits.sql` | New |
| `backend/repo.py` | Applications: contact name, follow-up default, events, rejection, lesson, followed up. Goals, practice days, account start, milestones seen |
| `backend/habits.py` | New, pure: weeks, goals, streaks, this week, follow-ups due, milestones, the weekly plan |
| `backend/analytics.py` | A rejection after a phone screen counts as a reply; the repeated-lessons finding |
| `backend/ai.py` | `rejection_lesson`, `follow_up` |
| `backend/main.py` | State gains `habits`, `plan`, `follow_ups_due`, and `history` on each application. Five new routes |
| `backend/scripts/live_check.py` | Two more real calls |
| `backend/tests/` | `test_migrate`, `test_repo_records`, new `test_repo_habits`, new `test_habits`, `test_analytics`, `test_ai`, new `test_routes_tracker`, `test_routes_data` |
| `frontend/src/tracker.js` | New: stage and "where it ended" labels, small helpers |
| `frontend/src/components/` | New: `ApplicationPanel`, `RejectQuestions`, `FollowUps`, `ThisWeek` (goals and streak), `Plan`, `Milestones` |
| `frontend/src/pages/` | `Applications` (panel, questions, follow-ups, what you have learned, the user's goal), `Home` (rebuilt), `Resume` (opens a given version), `Privacy` |
| `frontend/src/index.css` | The panel, the follow-up marker, the banner |

---

### Task 1: Schema (`007_tracker_habits.sql`)

```sql
applications + contact_name text, rejected_at_stage text check (in 'cv','screening','interview','final'),
               feedback_received text, lesson jsonb, last_followed_up_on date
application_events (id bigint identity pk, user_id → auth.users cascade, application_id → applications cascade,
                    from_stage text, to_stage text not null, at timestamptz not null default now())
                    index (application_id, at, id), index (user_id)
weekly_goals (user_id → auth.users cascade, effective_from date check isodow = 1,
              applications int check 1..30, practice int check 0..14, created_at, primary key (user_id, effective_from))
profiles     + milestones_seen jsonb not null default '[]'
```

Both new tables: RLS on, `revoke all ... from anon, authenticated`. Backfill: `follow_up_on = applied_on + 7` where it is null and the stage is `applied`, `screening` or `interview`.

- [ ] **Step 1: tests** in `test_migrate.py`: add both tables to `TABLES` (RLS and privilege tests then cover them); `test_new_tables_cascade_on_user_delete`; `test_events_deleted_with_their_application`; `test_goal_must_start_on_a_monday` and `test_goal_bounds` (`CheckViolation` for a Tuesday, 0 applications, 15 practice); `test_rejected_at_stage_checked`; `test_milestones_seen_defaults_to_empty`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** write the migration; `python migrate.py`.
- [ ] **Step 4:** run the suite; commit `feat: schema for stage history, weekly goals and rejection lessons`.

### Task 2: Applications in `repo.py`

**Produces:**

```python
APPLICATION_FIELDS += ("contact_name",)
CLOSED = ("offer", "rejected", "rejected_after_interview")
FOLLOW_UP_DAYS = 7
ENDED_AT = {"cv": "rejected", "screening": "rejected", "interview": "rejected_after_interview", "final": "rejected_after_interview"}

add_application(conn, user_id, fields) -> dict            # + creation event (from_stage None); follow_up_on = applied_on + 7 when not given and open
update_application(conn, user_id, app_id, fields) -> dict | None
    # a stage change writes one event; leaving a rejected stage clears rejected_at_stage, feedback_received, lesson;
    # a new applied_on moves follow_up_on with it while follow_up_on == old applied_on + 7 and last_followed_up_on is null
get_application(conn, user_id, app_id) -> dict | None
list_application_events(conn, user_id) -> list[dict]     # {application_id, from_stage, to_stage, at, day (London date)}, by application, at, id
reject_application(conn, user_id, app_id, *, ended_at: str, feedback: str) -> dict | None   # stage from ENDED_AT, answers stored, lesson cleared, event if the stage changed
set_lesson(conn, user_id, app_id, lesson: dict) -> dict | None
mark_followed_up(conn, user_id, app_id, today: date) -> dict | None   # last_followed_up_on = today, follow_up_on = today + 7
```

The old stage is read with `select ... for update` in the same transaction as the update, so two quick drags cannot both see the same old stage.

- [ ] **Step 1: tests** in `test_repo_records.py`: `test_new_application_records_its_creation`; `test_follow_up_suggested_seven_days_after_applying`; `test_given_follow_up_kept`; `test_closed_application_gets_no_follow_up`; `test_stage_change_writes_one_event`, `test_same_stage_writes_no_event`, `test_other_field_change_writes_no_event`; `test_history_in_order` (three moves with the same `now()` keep their order through `id`); `test_events_gone_with_the_application`; `test_new_applied_on_moves_the_suggested_follow_up` and `test_followed_up_date_not_moved`; `test_reject_sets_stage_from_where_it_ended` (parametrised over the four answers); `test_reject_twice_writes_one_event`; `test_leaving_rejected_clears_answers_and_lesson`; `test_mark_followed_up_moves_seven_days_from_today`; isolation: `test_user_b_cannot_read_events_reject_set_lesson_or_mark` (each returns None or nothing and A's row is unchanged); `test_contact_name_saved`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: stage history, rejection answers and follow-up dates on applications`.

### Task 3: Goals, practice and milestones in `repo.py`

**Produces:**

```python
list_goals(conn, user_id) -> list[dict]                     # {effective_from, applications, practice}, oldest first
set_goal(conn, user_id, *, effective_from: date, applications: int, practice: int) -> dict   # upsert on (user_id, effective_from)
practice_days(conn, user_id) -> list[date]                  # London date of each mock interview (journal type 'interview')
account_started(conn, user_id) -> date | None               # London date the profile was created
mark_milestones_seen(conn, user_id, ids: list[str]) -> list[str]   # union with those already seen, order kept
```

- [ ] **Step 1: tests** in new `test_repo_habits.py`: `test_set_goal_twice_for_the_same_monday_keeps_one_row`; `test_goals_oldest_first`; `test_practice_day_is_the_london_date` (23:30 UTC on Sunday 29 March 2026 is Monday 30 March; 23:30 UTC on Sunday 25 October 2026 is still Sunday 25 October); `test_coach_calls_and_imports_are_not_practice`; `test_milestones_seen_is_a_union`; isolation: user B sees none of A's goals, practice days or milestones, and B's writes leave A's alone.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: weekly goal history, practice days and milestones seen`.

### Task 4: Weeks, goals and streaks (`habits.py`)

**Produces:**

```python
DEFAULT_GOAL = {"applications": 5, "practice": 2}

monday(day: date) -> date
goal_for(week: date, goals: list[dict]) -> dict              # latest goal with effective_from <= week, else DEFAULT_GOAL
goal_starts(today: date, goals: list[dict]) -> date          # this Monday if no goal was ever set, else next Monday
week_counts(week: date, applications: list, practice_days: list[date]) -> dict   # {applications (with a CV only), practice, without_cv}
streaks(*, applications, practice_days, goals, started: date | None, today: date) -> dict    # {current, best}
this_week(*, applications, practice_days, goals, today) -> dict
    # {week_of, applications, practice, without_cv, goal, met, next_goal (from next Monday, when it differs) | None}
```

A week is met when both counts reach that week's goal. The streak is the run of met weeks ending last week, plus this week if it is already met. An unmet week in progress breaks nothing. Weeks before the week of `started` are not counted (`started` None: no weeks, streak 0).

- [ ] **Step 1: tests** in new `test_habits.py`: `test_no_activity_is_zero`; `test_three_met_weeks_then_a_missed_week_is_zero`; `test_met_current_week_extends`; `test_unmet_current_week_in_progress_does_not_break`; `test_exactly_at_goal_is_met`; `test_sunday_counts_in_its_own_week_and_monday_in_the_next`; `test_weeks_when_the_clocks_change_are_ordinary_weeks` (weeks of 23 and 30 March and of 19 and 26 October 2026); `test_application_without_cv_does_not_count` (but is in `without_cv`); `test_goal_change_applies_from_next_monday_and_leaves_earlier_weeks`; `test_first_goal_applies_this_week`; `test_lowering_the_goal_today_cannot_make_past_weeks_met`; `test_weeks_before_the_account_do_not_count`; `test_best_streak_survives_a_break`; `test_next_goal_shown_only_when_it_differs`.
- [ ] **Step 2:** run, see them fail (no module).
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: weekly goals and the weekly streak`.

### Task 5: Follow-ups, milestones and the weekly plan (`habits.py`)

**Produces:**

```python
STALE_DAYS, STORY_TARGET, MAX_TASKS = 21, 6, 5
MILESTONES = {"applications-1": "...", "applications-10": ..., "applications-25", "applications-50", "first-reply",
              "first-interview", "first-offer", "first-mock-interview", "story-bank-6", "streak-4", "streak-8"}   # id: banner text

follow_ups_due(applications: list, events: list, today: date) -> list[dict]
    # open applications that are due (follow_up_on <= today) or stale (at Applied, no change for 21 days);
    # {id, company, role, follow_up_on, due: bool, quiet_days: int | None}, oldest date first
milestones(*, applications, events, practice_count: int, story_count: int, best_streak: int) -> list[str]   # reached, in MILESTONES order
weekly_plan(*, follow_ups, findings, fresh_jobs: int, week: dict, story_count: int, missing_numbers: int, pages: set[str]) -> list[dict]
    # [{id, text, why, page, tab | None, label}], at most MAX_TASKS, in the order of decision 14
```

Copy for each plan task is fixed in `habits.py`, for example `"Send 3 more applications with a tailored CV"`, why `"Your goal is 5 this week and 2 have a CV recorded."`, page `jobs` when it exists, else `resume`.

- [ ] **Step 1: tests** in `test_habits.py`: `test_follow_up_due_on_the_day`; `test_offer_and_rejected_have_no_follow_up_due`; `test_quiet_for_21_days_at_applied` (20 days: not listed; 21: listed with `quiet_days`); `test_quiet_counts_from_the_last_stage_change`; `test_old_application_without_history_counts_from_date_applied`; `test_milestones_from_data` (each id at its threshold); `test_reply_reached_through_history_counts` (a card now at Rejected that passed through Interview reached first interview); `test_rejection_after_a_phone_screen_is_a_reply`; `test_plan_at_most_five`; `test_plan_order`; `test_no_jobs_task_without_the_jobs_page`; `test_finding_without_a_page_is_not_a_task`; `test_met_goal_gives_no_goal_task` (a done task disappears); `test_six_stories_gives_no_story_task`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: follow-ups due, milestones and the weekly plan`.

### Task 6: Findings (`analytics.py`)

**Produces:** `responded(app) -> bool` (a stage in `RESPONDED`, or `rejected` with `rejected_at_stage == "screening"`), used by `_row`; `lesson_findings(applications) -> list[dict]` added to `compute`'s findings: three or more lessons with the same `page` give `{"id": f"lessons-{page}", "type": "lessons", "severity": 3, ...}` naming the companies, with the latest lesson's change as the action and a link to that page.

- [ ] **Step 1: tests** in `test_analytics.py`: `test_rejection_after_screen_counts_as_reply`; `test_rejection_at_cv_is_not_a_reply`; `test_three_lessons_on_one_page_make_a_finding`; `test_two_lessons_make_no_finding`; `test_lessons_on_different_pages_do_not_combine`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: replies after a phone screen, and a finding from repeated lessons`.

### Task 7: The two AI tasks (`ai.py`)

**Produces:**

```python
ENDED_LABEL = {"cv": "at the CV stage", "screening": "after a phone screen", "interview": "after an interview", "final": "after a final interview"}
LESSON_PAGES = ("resume", "interview", "profile")

rejection_lesson(*, job: dict | None, cv_text: str, ended_at: str, feedback: str) -> dict
    # {likely_reason, one_change, page}; page outside LESSON_PAGES becomes "resume" for cv, else "interview"
follow_up(*, role: str, company: str, applied_on: date, contact_name: str, sender: str) -> dict
    # {subject, message}; message = greeting + body + "Kind regards," + sender. Only role, company, date and contact name are sent
```

The checks are decisions 5 and 6. `cv_text` comes from `cv.text(content)` for a format 2 CV (no contact line) or the paragraph and bullets of a format 1 CV.

- [ ] **Step 1: tests** in `test_ai.py` with the model replaced: lesson: `test_lesson_stated_as_fact_is_retried_then_refused`; `test_lesson_mentioning_feedback_when_none_given_is_refused`; `test_lesson_may_suggest_asking_for_feedback` (in `one_change`); `test_lesson_quote_must_be_in_the_inputs`; `test_lesson_page_normalised`; `test_lesson_without_advert_may_not_describe_it`; `test_lesson_prompt_says_what_is_missing`. Draft: `test_draft_wrapped_with_greeting_and_name` (contact name, and "Hiring Manager" when blank); `test_users_name_never_sent`; `test_draft_over_80_words_retried`; `test_draft_with_placeholder_retried`; `test_draft_with_invented_number_retried` (the day and year applied are allowed); `test_draft_own_greeting_and_sign_off_removed`.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: rejection lesson and follow-up draft AI tasks`.

### Task 8: Routes (`main.py`)

**Produces:**

| Route | Body | Answer |
|---|---|---|
| `POST`, `PATCH /api/applications[/{id}]` | + `contact_name` (≤120) | as now |
| `POST /api/applications/{id}/reject` | `{ended_at: cv\|screening\|interview\|final, feedback: str ≤2000 = ""}` | `{application, lesson \| None, notice \| None}`. Neither CV nor advert: no AI call, notice "No CV or job description was recorded for this application, so there is nothing to compare. Attach both next time." The rejection is saved before the model is called, so 429 and 502 keep it |
| `POST /api/ai/applications/{id}/follow-up` | none | `{subject, message}`. One AI action. 400 for an application at Offer or Rejected |
| `POST /api/applications/{id}/followed-up` | none | the application |
| `PUT /api/profile/goals` | `{applications: 1..30, practice: 0..14}` | `{goal, starts_on}` |
| `POST /api/milestones/seen` | `{ids: [known ids]}` | 204 |

`GET /api/state` adds `habits` (`this_week`, `streak`, `best_streak`, `milestones`, `new_milestones` as `[{id, text}]`), `plan`, `follow_ups_due`, and `history` on each application.

- [ ] **Step 1: tests** in new `test_routes_tracker.py`: for every new route, 401 without a token, 422 for a malformed id, 404 for user B's application; reject with neither recorded makes no model call and returns the notice; reject with a CV returns a lesson and stores it; failed lesson (502) keeps the stage and answers, and a second post with the same answers retries without a second event; limit reached (429) keeps the rejection; the draft counts one AI action and refuses a closed application; followed up moves the date; goals: first set applies this week, the next from Monday, 0 applications and 15 practice give 422; milestones seen with an unknown id gives 422; a seen milestone is not announced again after its application is deleted and logged again, and an unseen one disappears with its application; state for a new user has streak 0, no milestones and a plan; user B's state shows none of A's events, goals, lessons or milestones. In `test_routes_data.py`: `contact_name` round trip.
- [ ] **Step 2:** run, see them fail.
- [ ] **Step 3:** implement.
- [ ] **Step 4:** run the suite; commit `feat: routes for rejections, follow-ups, goals and milestones; habits in the state`.

### Task 9: Real-model check (`scripts/live_check.py`)

- [ ] Add "rejection lesson" (a made-up advert and CV text, ended after an interview, with feedback; and once with no feedback) and "follow-up draft"; each prints pass or fail against the same checks as the code. Run it; fix anything the real model shows, test first. Commit `test: live checks for the lesson and the follow-up draft`.

### Task 10: Applications page

- [ ] `tracker.js`, `ApplicationPanel` (every field editable and saved as it changes; history with dates; follow-up date, Mark as followed up, Clear, Draft a follow-up with Copy; the lesson, or Retry, or the fixed message; CV version opens it on Resume), `RejectQuestions` (opened by a drop on Rejected or by choosing a rejected stage; nothing changes if cancelled), `FollowUps`, "What you have learned", the user's goal in Weekly progress, a follow-up marker on cards. Lint and build. Checked by hand with the temporary-user harness. Commit `feat: application detail panel, rejection lessons and follow-ups`.

### Task 11: Home, Resume and Privacy

- [ ] `Home` in the agreed order: milestone banner (marks seen when shown), next best step, This week with Edit goals, the weekly plan, follow-ups due, getting started (while unfinished), visa countdown and totals, other findings. `Resume` opens `focus.cvId`. `Privacy`: what a lesson and a draft send to the model. Lint and build; checked by hand. Commit `feat: the home page with this week, the weekly plan and milestones`.

### Task 12: Verify and document

- [ ] Suite with 0 skipped; lint and build; `live_check.py`; the step's hand checks with the harness, then listed for the owner (sign-in, second account). Update `docs/ARCHITECTURE.md` (roadmap, decisions, data model, API, sections 21 and 22: how the tracker works and its verification record, limitations), the step document's status, `CLAUDE.md` if a rule changed, this plan's status. Commit `docs: step 4 built; what is verified and what the owner still has to check`.

## Order and what blocks what

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12. Tasks 4 to 7 are pure and could go in any order after 3; routes (8) need all of them; the pages need the routes.
