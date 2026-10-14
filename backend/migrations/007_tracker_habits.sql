-- 007_tracker_habits: the history of each application's stage, weekly goals, and what a rejection taught.
-- Streaks, milestones and the weekly plan are worked out from these rows each time and never stored.

-- `contact` (from step 0) now holds how to reach the contact; their name is a column of its own, the only
-- part that is ever sent to the AI. A rejection keeps where it ended and any feedback the user was given.
alter table applications
  add column contact_name text,
  add column rejected_at_stage text check (rejected_at_stage in ('cv', 'screening', 'interview', 'final')),
  add column feedback_received text,
  add column lesson jsonb,
  add column last_followed_up_on date;

-- One row per stage change. The first row of an application records its creation (from_stage is null).
-- Applications made before this migration have no rows: their history was not recorded.
create table application_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  application_id uuid not null references applications (id) on delete cascade,
  from_stage text,
  to_stage text not null,
  at timestamptz not null default now()
);
create index application_events_application on application_events (application_id, at, id);
create index application_events_user on application_events (user_id);

-- A goal applies from its Monday until the next row's Monday, so a past week is always judged by the
-- goal that applied then. No row at all means the defaults (5 applications, 2 practice sessions).
create table weekly_goals (
  user_id uuid not null references auth.users (id) on delete cascade,
  effective_from date not null check (extract(isodow from effective_from) = 1),
  applications int not null check (applications between 1 and 30),
  practice int not null check (practice between 0 and 14),
  created_at timestamptz not null default now(),
  primary key (user_id, effective_from)
);

-- Milestones already announced, so each banner is shown once.
alter table profiles add column milestones_seen jsonb not null default '[]';

-- A follow-up is suggested 7 days after applying. Open applications made before this step get one too.
update applications set follow_up_on = applied_on + 7
 where follow_up_on is null and stage in ('applied', 'screening', 'interview');

alter table application_events enable row level security;
alter table weekly_goals enable row level security;
revoke all on application_events, weekly_goals from anon, authenticated;
