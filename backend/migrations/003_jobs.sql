-- 003_jobs: real job listings, the sponsor register, and each user's matches.
--
-- Listings, searches and the register are public data shared by every user, so they have no
-- user_id. This is the one deliberate exception to the per-user rule; they hold nothing personal.
-- A user's view of a listing (fit, saved, hidden) is a private row in job_matches.
-- Like every other table, all of these are closed to the browser-facing roles.

create table job_listings (
  id uuid primary key default gen_random_uuid(),
  source text not null,     -- the job site, e.g. 'reed'
  source_id text not null,  -- the advert's id on that site
  title text not null,
  employer text not null,
  employer_key text not null default '',  -- the employer's name normalised for the register lookup
  posted_by text not null check (posted_by in ('employer', 'agency')),
  location text not null default '',
  salary_min numeric,
  salary_max numeric,
  salary_annual boolean not null default false,        -- false: a day or hourly rate, or no salary stated
  description text not null default '',
  description_is_full boolean not null default false,  -- false: the short text that search results carry
  url text not null,
  posted_on date not null,
  sponsor_status text not null default 'not_found' check (sponsor_status in ('listed', 'possible', 'not_found', 'agency')),
  sponsor_name text,        -- the registered name the employer matched
  fetched_at timestamptz not null default now(),
  unique (source, source_id)
);
create index job_listings_posted_on on job_listings (posted_on);

-- One row per search already run, by anyone: the shared cache
create table job_searches (
  id uuid primary key default gen_random_uuid(),
  source text not null,
  query text not null,
  location text not null,
  fetched_at timestamptz not null default now(),
  unique (source, query, location)
);

create table job_search_results (
  search_id uuid not null references job_searches (id) on delete cascade,
  listing_id uuid not null references job_listings (id) on delete cascade,
  primary key (search_id, listing_id)
);
create index job_search_results_listing on job_search_results (listing_id);

-- The gov.uk register of licensed sponsors. An employer with a trading name has one row per name.
create table sponsors (
  id bigint generated always as identity primary key,
  name text not null,      -- as registered
  name_key text not null,  -- normalised: see sponsors.normalise
  town text not null default '',
  county text not null default '',
  route text not null,
  rating text not null default ''
);
create index sponsors_name_key on sponsors (name_key text_pattern_ops);

-- When each shared reference set was last loaded, and how current its source is
create table reference_meta (
  key text primary key,
  loaded_at timestamptz not null default now(),
  published_on date,
  source_url text,
  row_count int
);

create table job_matches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  listing_id uuid not null references job_listings (id) on delete cascade,
  role_family_id uuid references role_families (id) on delete set null,
  search_location text not null default '',  -- which of the user's locations found it
  fit_percent int check (fit_percent between 0 and 100),
  fit_label text check (fit_label in ('direct', 'near', 'stretch', 'none')),
  shown jsonb not null default '[]',  -- [{"need": str, "achievement": the user's achievement title}]
  gaps jsonb not null default '[]',   -- [str]
  fit_from_summary boolean not null default false,  -- scored on the short text, not the full advert
  status text not null default 'new' check (status in ('new', 'seen', 'saved', 'hidden')),
  first_seen_at timestamptz not null default now(),
  scored_at timestamptz,
  unique (user_id, listing_id)
);
create index job_matches_listing on job_matches (listing_id);

alter table saved_jobs add column listing_id uuid references job_listings (id) on delete set null;
alter table saved_jobs add column posted_on date;
alter table profiles add column include_senior boolean not null default false;

alter table job_listings enable row level security;
alter table job_searches enable row level security;
alter table job_search_results enable row level security;
alter table sponsors enable row level security;
alter table reference_meta enable row level security;
alter table job_matches enable row level security;

revoke all on job_listings, job_searches, job_search_results, sponsors, reference_meta, job_matches
  from anon, authenticated;
