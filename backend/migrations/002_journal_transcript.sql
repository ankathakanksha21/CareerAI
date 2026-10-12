-- 002_journal_transcript: keep what was said in a coach call or mock interview with its journal
-- entry, so the user can always see that their words were heard and what the results came from.
alter table journal_entries add column transcript text;
