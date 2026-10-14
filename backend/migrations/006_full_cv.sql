-- 006_full_cv: what a full UK CV needs beyond the profile, and what kind of CV a saved version is.
--
-- No new table: every column sits on a per-user table that already has row level security on
-- and no privileges for the browser-facing roles.

-- The contact line of a CV, and the lines of its "Additional information" section
alter table profiles
  add column phone text not null default '',
  add column city text not null default '',
  add column linkedin_url text not null default '',  -- stored without "https://": "linkedin.com/in/name"
  add column additional text[] not null default '{}';  -- certifications, awards, volunteering: one line each

-- A version made before this step holds a profile paragraph, bullets and a letter (format 1).
-- From now on a version holds the whole document (format 2): see cv.py.
alter table cv_versions
  add column kind text not null default 'tailored' check (kind in ('base', 'tailored')),
  add column format_version int not null default 1 check (format_version in (1, 2)),
  add column edited_at timestamptz,                  -- when the user last changed it; null: as built
  add column contact_name text not null default '',  -- who the cover letter is addressed to, if the user knows
  add column pages int;                              -- pages of the PDF made from it; null for format 1
