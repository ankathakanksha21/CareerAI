-- Step 6: the hidden market. The people a user contacts and how far each has gone, every message
-- they marked as sent, the events they saved, a referral linked to an application, and an outreach
-- target beside applications and practice. All per user.

-- Events the user found on Meetup, Eventbrite, their university or a professional body and saved.
-- Nothing here is fetched: the user types it. `prep` holds the last preparation written for it.
create table networking_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  starts_at timestamptz not null,
  place text not null default '',
  online boolean not null default false,
  link text,
  type text not null check (type in ('meetup', 'careers_fair', 'webinar', 'society', 'employer_event')),
  status text not null default 'interested' check (status in ('interested', 'going', 'attended')),
  notes text not null default '',
  prep jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index networking_events_user on networking_events (user_id, starts_at);

-- Someone the user added. Other people's details: no email address or phone number is asked for.
-- `relationship` is how the user knows them, the only connection a draft may mention.
create table contacts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  role text not null default '',
  company text not null default '',
  relationship text not null check (relationship in ('alumni', 'tutor', 'supervisor', 'event', 'recruiter', 'introduced', 'none')),
  link text,
  status text not null default 'to_contact'
    check (status in ('to_contact', 'messaged', 'replied', 'chat_booked', 'chat_done', 'referral_offered')),
  notes text not null default '',
  event_id uuid references networking_events (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index contacts_user on contacts (user_id, created_at);

-- One row per step in a contact's pipeline: a message marked as sent (with its type), a reply, a
-- chat booked or held, a referral offered. A deleted contact's rows stay with contact_id cleared,
-- so a message still counts in the week it was sent. `on_day` is the London date, and the same
-- step for the same person on one day is recorded once, so marking a message sent twice counts once.
create table outreach_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  contact_id uuid references contacts (id) on delete set null,
  kind text not null check (kind in ('sent', 'replied', 'chat_booked', 'chat_done', 'referral_offered')),
  message_type text check (message_type in ('connection_note', 'chat_request', 'follow_up', 'thank_you', 'referral_ask',
                                            'recruiter_intro', 'reference_ask', 'own')),
  at timestamptz not null default now(),
  on_day date not null default (now() at time zone 'Europe/London')::date,
  check ((kind = 'sent') = (message_type is not null))
);
create unique index outreach_events_once_a_day on outreach_events (user_id, contact_id, kind, coalesce(message_type, ''), on_day);
create index outreach_events_user on outreach_events (user_id, at);

-- An application can name the saved contact behind it. Deleting the contact keeps the application.
alter table applications add column contact_id uuid references contacts (id) on delete set null;

-- Messages a week. Null on goals set before this step, which count as 0, so no past week changes.
alter table weekly_goals add column outreach int check (outreach between 0 and 20);

-- The user's university careers events page, pasted once.
alter table profiles add column university_events_url text;

-- The outreach target used until the user sets goals. Every account that exists now gets 0, with an
-- invitation to set one, so nobody's streak breaks without warning. Every account made later gets 2
alter table profiles add column outreach_default int not null default 0;
alter table profiles alter column outreach_default set default 2;

alter table networking_events enable row level security;
alter table contacts enable row level security;
alter table outreach_events enable row level security;
revoke all on networking_events, contacts, outreach_events from anon, authenticated;
