-- 010_peers: buddy groups of two or three (step 7). The only step in which one user sees anything
-- about another, and then only through peerdb.peer_view. Every row is deleted with either account
-- it names.

-- Each user's own switch. Off until they consent: 18 or over, the code of conduct, and a field
create table peer_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  enabled boolean not null default false,
  consented_at timestamptz,
  over_18 boolean not null default false,
  field text,                    -- a key of peers.FIELDS
  contact_link text,             -- a LinkedIn or WhatsApp address, shown only to their current group
  waiting_since timestamptz,     -- on the list since; null when proposed, in a group or off
  barred_at timestamptz,         -- set from the owner's report script: cannot switch Peers on again
  created_at timestamptz not null default now(),
  check (not enabled or (over_18 and consented_at is not null and field is not null))
);
create index peer_profiles_waiting on peer_profiles (waiting_since) where waiting_since is not null;

-- A group is proposed until two people have both said yes, then active, then closed when fewer than
-- two remain
create table peer_groups (
  id uuid primary key default gen_random_uuid(),
  status text not null default 'proposed' check (status in ('proposed', 'active', 'closed')),
  created_at timestamptz not null default now(),
  active_since date,             -- the London day it first had two accepted members
  closed_at timestamptz
);

-- One row per person per group. Pages call a member by this row's id, never by their user id.
-- A live member (proposed or accepted) holds one of three places, so a group can never hold a
-- fourth, even when two people accept at the same moment; and a person is live in one group only
create table peer_group_members (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references peer_groups (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  slot smallint not null check (slot between 1 and 3),
  status text not null default 'proposed' check (status in ('proposed', 'accepted', 'declined', 'left')),
  yes_from uuid[] not null default '{}',  -- who has agreed to this member being in the group, themselves included
  proposed_at timestamptz not null default now(),
  joined_at timestamptz,
  unique (group_id, user_id)
);
create unique index peer_members_slot on peer_group_members (group_id, slot) where status in ('proposed', 'accepted');
create unique index peer_members_one_group on peer_group_members (user_id) where status in ('proposed', 'accepted');
create index peer_members_group on peer_group_members (group_id);

-- Pairings never proposed again: one declined, let a proposal expire, or left a group with the other
create table peer_passes (
  user_id uuid not null references auth.users (id) on delete cascade,
  other_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, other_id)
);
create index peer_passes_other on peer_passes (other_id);

-- One line a week from each member: "What is your focus this week?"
create table peer_checkins (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references peer_groups (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  week_start date not null,      -- the London Monday
  text text not null check (char_length(text) between 1 and 140),
  updated_at timestamptz not null default now(),
  unique (group_id, user_id, week_start)
);

-- A nudge has fixed wording, so only who, to whom and when are kept. One a day from one person to another
create table peer_nudges (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references peer_groups (id) on delete cascade,
  from_user uuid not null references auth.users (id) on delete cascade,
  to_user uuid not null references auth.users (id) on delete cascade,
  at timestamptz not null default now(),
  on_day date not null,          -- the London day
  unique (from_user, to_user, on_day)
);
create index peer_nudges_to on peer_nudges (to_user, on_day);

create table peer_blocks (
  blocker uuid not null references auth.users (id) on delete cascade,
  blocked uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker, blocked)
);
create index peer_blocks_blocked on peer_blocks (blocked);

-- Kept for the owner to review with scripts/peer_reports.py. The reported line is copied, so
-- editing or deleting it later does not remove the evidence
create table peer_reports (
  id uuid primary key default gen_random_uuid(),
  reporter uuid not null references auth.users (id) on delete cascade,
  about_user uuid not null references auth.users (id) on delete cascade,
  group_id uuid references peer_groups (id) on delete set null,
  checkin_id uuid references peer_checkins (id) on delete set null,
  checkin_text text,
  reason text not null check (reason in ('unkind', 'spam', 'personal', 'other')),
  details text not null default '' check (char_length(details) <= 500),
  at timestamptz not null default now(),
  handled boolean not null default false
);
create index peer_reports_reporter on peer_reports (reporter);
create index peer_reports_open on peer_reports (at) where not handled;

alter table peer_profiles enable row level security;
alter table peer_groups enable row level security;
alter table peer_group_members enable row level security;
alter table peer_passes enable row level security;
alter table peer_checkins enable row level security;
alter table peer_nudges enable row level security;
alter table peer_blocks enable row level security;
alter table peer_reports enable row level security;
revoke all on peer_profiles, peer_groups, peer_group_members, peer_passes, peer_checkins, peer_nudges, peer_blocks, peer_reports
  from anon, authenticated;
