-- 005_profile_depth: the facts a full UK CV is built from, and where each achievement happened.
--
-- Work history and education are per-user tables like every other: deleted with the login,
-- row level security on with no policies, no privileges for the browser-facing roles.

create table work_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  employer text not null,
  job_title text not null default '',
  location text not null default '',
  country text not null default '',
  start_month date,                            -- first day of the month; null: not given
  end_month date,                              -- null: still there (is_current) or not given
  is_current boolean not null default false,
  employer_context text not null default '',   -- one line on what the employer does, for a UK reader
  source text not null default 'manual' check (source in ('manual', 'voice', 'paste', 'cv', 'github')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint work_history_end_after_start check (start_month is null or end_month is null or end_month >= start_month),
  constraint work_history_current_has_no_end check (not (is_current and end_month is not null))
);
create index work_history_user on work_history (user_id);

create table education (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  institution text not null,
  qualification text not null default '',
  subject text not null default '',
  start_month date,
  end_month date,
  grade text not null default '',
  country text not null default '',
  from_details boolean not null default false,  -- the current course typed in "Your details", kept in step with it
  source text not null default 'manual' check (source in ('manual', 'voice', 'paste', 'cv', 'github')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint education_end_after_start check (start_month is null or end_month is null or end_month >= start_month)
);
create index education_user on education (user_id);
create unique index education_one_from_details on education (user_id) where from_details;

alter table profiles
  add column skills text[] not null default '{}',
  add column languages jsonb not null default '[]',  -- [{"language": str, "level": str}]
  add column github_username text;

-- An achievement happened in one job or on one course, or neither
alter table achievements
  add column work_history_id uuid references work_history (id) on delete set null,
  add column education_id uuid references education (id) on delete set null,
  add column source_url text;  -- the repository of a GitHub project

alter table achievements drop constraint achievements_source_check;
alter table achievements add constraint achievements_source_check check (source in ('voice', 'paste', 'cv', 'github'));

-- A CV upload or GitHub import is logged with the text that was read
alter table journal_entries drop constraint journal_entries_type_check;
alter table journal_entries add constraint journal_entries_type_check check (type in ('coach', 'interview', 'import'));

alter table work_history enable row level security;
alter table education enable row level security;
revoke all on work_history, education from anon, authenticated;

-- The current course of everyone who has already filled in "Your details" becomes their first education entry
insert into education (user_id, institution, qualification, end_month, country, from_details)
select user_id, university, course, graduation_date, 'United Kingdom', true
from profiles
where coalesce(btrim(university), '') <> '' and coalesce(btrim(course), '') <> '';
