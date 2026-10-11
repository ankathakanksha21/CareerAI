-- 001_initial: the per-user tables for accounts and saved data.
--
-- Every row belongs to one Supabase login (auth.users) and is deleted with it.
-- The tables are private to the backend: row level security is on with no policies and the
-- browser-facing roles have no privileges, so Supabase's auto-generated API cannot read them.

create table profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  full_name text not null default '',
  university text,
  course text,
  graduation_date date,  -- first day of the chosen month
  visa_type text check (visa_type in ('student', 'graduate')),
  visa_end_date date,
  locations text[] not null default '{}',
  pitch text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table achievements (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null,
  raw text not null default '',  -- their own words
  uk_version text not null,      -- the UK CV bullet
  skills text[] not null default '{}',
  outcome text not null default '',
  scale text not null default '',
  context_note text not null default '',
  source text not null check (source in ('voice', 'paste')),
  created_at timestamptz not null default now()
);
create index achievements_user on achievements (user_id);

create table role_families (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  fit text not null check (fit in ('direct', 'near', 'stretch')),
  overlap int not null check (overlap between 0 and 100),  -- an AI estimate
  uk_titles text[] not null default '{}',
  why text not null default '',
  needs jsonb not null default '[]',  -- [{"need": str, "shown_by": achievement title or ""}]
  targeted boolean not null default false,
  created_at timestamptz not null default now()
);
create unique index role_families_user_name on role_families (user_id, lower(name));

create table saved_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null,
  company text not null,
  location text,
  url text,
  description text not null,
  summary text not null default '',
  keywords text[] not null default '{}',
  role_family_id uuid references role_families (id) on delete set null,
  source text not null default 'pasted',
  created_at timestamptz not null default now()
);
create index saved_jobs_user on saved_jobs (user_id);

create table cv_versions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  saved_job_id uuid references saved_jobs (id) on delete set null,
  role_family_id uuid references role_families (id) on delete set null,
  content jsonb not null,  -- profile, bullets, keywords, cover_letter, gaps
  created_at timestamptz not null default now()
);
create index cv_versions_user on cv_versions (user_id);

create table stories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  achievement_id uuid references achievements (id) on delete set null,
  title text not null,
  competency text not null default '',
  situation text not null default '',
  task text not null default '',
  action text not null default '',
  result text not null default '',
  strength text not null default '',
  tip text not null default '',
  created_at timestamptz not null default now()
);
create index stories_user on stories (user_id);

create table applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  company text not null,
  role text not null,
  role_family_id uuid references role_families (id) on delete set null,
  cv_version_id uuid references cv_versions (id) on delete set null,
  saved_job_id uuid references saved_jobs (id) on delete set null,
  source text not null,
  stage text not null default 'applied' check (stage in (
    'applied', 'no_response', 'rejected', 'screening', 'interview', 'rejected_after_interview', 'offer')),
  applied_on date not null default ((now() at time zone 'Europe/London')::date),
  posted_on date,
  job_url text,
  contact text,
  notes text,
  sponsor_licence boolean,
  follow_up_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint applications_posted_before_applied check (posted_on is null or posted_on <= applied_on)
);
create index applications_user on applications (user_id);

create table journal_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  type text not null check (type in ('coach', 'interview')),
  title text not null,
  with_whom text not null default '',
  summary text not null default '',
  points jsonb not null default '[]',
  actions jsonb not null default '[]',
  scores jsonb,
  created_at timestamptz not null default now()
);
create index journal_entries_user on journal_entries (user_id);

-- One row per AI action or voice session started: daily limits now, streaks later.
create table usage_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  kind text not null check (kind in ('ai', 'voice')),
  action text not null,
  created_at timestamptz not null default now()
);
create index usage_events_user_kind_time on usage_events (user_id, kind, created_at);

alter table profiles enable row level security;
alter table achievements enable row level security;
alter table role_families enable row level security;
alter table saved_jobs enable row level security;
alter table cv_versions enable row level security;
alter table stories enable row level security;
alter table applications enable row level security;
alter table journal_entries enable row level security;
alter table usage_events enable row level security;

revoke all on profiles, achievements, role_families, saved_jobs, cv_versions, stories,
  applications, journal_entries, usage_events from anon, authenticated;
