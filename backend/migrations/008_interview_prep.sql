-- Step 5: interview preparation. Company research shared by every user, one prep pack per job
-- or application, competencies on stories, and a daily limit on research.

-- Public facts about a company, researched once and reused by everyone for 14 days. No user_id:
-- like the job listings, this is public data. Found by the Companies House number (or the
-- normalised name) together with the website's host, so a wrong website typed by one user never
-- changes what another user is shown.
create table companies (
  id uuid primary key default gen_random_uuid(),
  lookup_key text not null unique,
  name text not null,
  company_number text,
  website text,
  registry jsonb,
  facts jsonb not null default '[]',
  missing jsonb not null default '[]',
  researched_at timestamptz not null default now()
);

-- One user's pack for one saved job, or for an application with no saved job. It keeps a copy of
-- the brief it was built from, so another user refreshing the company never changes it.
create table prep_packs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  saved_job_id uuid references saved_jobs (id) on delete set null,
  application_id uuid references applications (id) on delete set null,
  company_id uuid references companies (id) on delete set null,
  role text not null,
  company text not null,
  content jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index prep_packs_user on prep_packs (user_id);
create unique index prep_packs_one_per_job on prep_packs (user_id, saved_job_id) where saved_job_id is not null;
create unique index prep_packs_one_per_application on prep_packs (user_id, application_id)
  where application_id is not null and saved_job_id is null;

-- The eight UK competencies a story can show, at most three per story (checked in code).
alter table stories add column competencies text[] not null default '{}'
  check (competencies <@ array['teamwork', 'leadership', 'problem_solving', 'communication',
                               'setback', 'initiative', 'influencing', 'deadlines']);

-- A story whose one-word competency is exactly one of the eight labels is tagged with it now.
-- The rest wait for "Tag my stories".
update stories s set competencies = array[m.key]
  from (values ('teamwork', 'teamwork'), ('leadership', 'leadership'), ('problem solving', 'problem_solving'),
               ('communication', 'communication'), ('handling a setback', 'setback'), ('initiative', 'initiative'),
               ('influencing', 'influencing'), ('working to deadlines', 'deadlines')) as m (label, key)
 where lower(trim(s.competency)) = m.label and s.competencies = '{}';

-- Researching a company costs search credits, so it has its own daily limit.
alter table usage_events drop constraint usage_events_kind_check;
alter table usage_events add constraint usage_events_kind_check check (kind in ('ai', 'voice', 'research'));

alter table companies enable row level security;
alter table prep_packs enable row level security;
revoke all on companies, prep_packs from anon, authenticated;
