---
name: careerai-step-2-real-jobs
description: Use when building, continuing or reviewing step 2 of the CareerAI roadmap - real job listings from Adzuna and Reed, matching jobs to the user's profile, the gov.uk sponsor register, and visa salary facts
---

# Step 2: real jobs

**Status:** Not started. Design approved by the owner, 12 October 2026. **Depends on:** step 0 (works better after step 1, which adds skills and work history, but does not require it). **Size:** large, about the same as step 0.
**REQUIRED:** follow `careerai-building-a-step`.

## Goal

The user sees real, current UK jobs for the roles they target, each judged against their own profile from its job description rather than its title, with plain facts about sponsorship and salary, and can act on any of them in one click.

Today a user must find jobs elsewhere and paste them in. That stays; this step adds the search.

## Decisions already made (do not re-ask)

| Decision | Detail | Decided by |
|---|---|---|
| Job sources | The official Adzuna and Reed APIs | Owner, 12 Oct 2026 |
| Graduate boards | Prospects, Bright Network, Handshake and similar are left out for now. No scraping | Owner, 12 Oct 2026 |
| Sponsor data | The gov.uk register of licensed sponsors (workers) | Owner, 12 Oct 2026 |
| Which jobs to show | All jobs, each labelled for sponsorship, with a "Sponsors only" filter | Owner, 12 Oct 2026 |
| New jobs | In the app only: refresh when the page is opened, a "New since your last visit" marker and a count on the menu. No email | Owner, 12 Oct 2026 |
| Visa wording | Facts with sources and the date checked, and "not immigration advice". No verdict labels | Owner, 12 Oct 2026 |
| Fit labels | Direct fit (80% or more of what the job asks for is evidenced), Near fit (60 to 79%), Stretch (40 to 59%). Below 40% is tucked away under "Not a match" | Recommended; approved 12 Oct 2026. From the owner's "direct, 70% overlap, stretch" |
| Where it lives | A new menu item, "Jobs", between Career pathways and Resume | Recommended; approved 12 Oct 2026 |
| Seniority | Titles containing senior, lead, principal, head, director or manager are left out unless the user turns on "Include senior roles" | Recommended; approved 12 Oct 2026 |
| Freshness | Jobs posted in the last 14 days. "Posted in the last 48 hours" is highlighted | Recommended; approved 12 Oct 2026. From the owner's "apply within 48 hours" |

## In scope

1. Fetch jobs from Adzuna and Reed for the user's targeted role families and preferred locations.
2. A shared cache of listings so many users do not repeat the same searches.
3. Fit scoring against the user's achievements and skills.
4. Sponsor register import and employer matching.
5. Visa salary facts, and the return of the "offer check" as a facts panel.
6. The Jobs page, and one-click Save, Tailor CV, Practise interview, Add to tracker, Not for me.
7. Real numbers on role family cards, and the "few sponsor-listed roles" tracker finding.

## Out of scope

Email alerts; scraping; graduate boards; applying on the user's behalf; salary negotiation advice; occupation-code going rates (the facts panel links to gov.uk for these).

## What the user sees

**Jobs page.** Filters: role family, location, "Sponsors only", "Include senior roles". Newest first. Each job shows:

| Element | Detail |
|---|---|
| Title, employer, location, source | With "View advert", which opens the original on Adzuna or Reed |
| Posted | Date, and a "Posted in the last 48 hours" marker |
| Salary | The advertised figure, or "Salary not stated". An Adzuna estimate is shown as "Estimated by Adzuna" and never used for the visa facts |
| Fit | The label, the percentage, up to three things the user already shows (each naming the achievement) and up to three gaps |
| Sponsorship | One of: "On the sponsor register as <name> (Skilled Worker)", "Possible match on the register: <name>. Check before applying", "Not found on the register. Employers sometimes appear under a different registered name", "Advertised by a recruitment agency; the employer is not named" |
| Salary fact | "Advertised salary £X. General Skilled Worker threshold £Y, new-entrant threshold £Z (gov.uk, checked on <date>). The rate for this occupation may be higher." |
| Actions | Save job, Tailor CV, Practise interview, Add to tracker, Not for me |

A line under the filters reads: "Sponsor register as of <date>. Visa rules checked on <date>. This is not immigration advice."

**Short descriptions.** Adzuna supplies only a snippet. Those jobs are scored on the title and snippet and marked "Fit based on a short summary". Saving one invites the user to paste the full description before tailoring a CV.

**Refresh.** Opening the page fetches new jobs if the last fetch for that search is older than 6 hours. A "Check for new jobs" button does the same on demand.

**Elsewhere.**

- Home: "N new matching jobs posted in the last 48 hours" becomes the next best step when there are any.
- Career pathways: each role family card shows live matched jobs, the median advertised salary with the number of adverts it is based on, and the share from employers on the register.
- Applications: an application created from a listing is pre-filled with its link, posted date and sponsor status. The finding "few sponsor-listed roles in <family>" returns, stated as counts.
- Career pathways: the offer check returns as a facts panel (salary against the two thresholds, register lookup by employer name), with the same sources and wording.

## Data changes (migration `00N_jobs`)

Two kinds of table. Listings and the register are public data shared by all users and have no `user_id`; this is the one exception to the per-user rule and is deliberate. Matches are per user.

| Table | Per user? | Holds |
|---|---|---|
| `job_listings` | Shared | `source`, `source_id` (unique together), title, employer, location, `salary_min`, `salary_max`, `salary_stated`, description, `description_is_full`, url, `posted_at`, `fetched_at` |
| `job_searches` | Shared | The cache key: source, query, location, `fetched_at` |
| `sponsors` | Shared | Registered name, normalised name, town, county, route, rating |
| `reference_meta` | Shared | When the register was last loaded and its publication date |
| `job_matches` | Per user | `listing_id`, `fit_percent`, `fit_label`, `shown jsonb`, `gaps jsonb`, `sponsor_status`, `sponsor_name`, `status` (new, seen, saved, hidden), `first_seen_at`, `scored_at` |
| `saved_jobs` | Per user | Add `listing_id`, `posted_on`; `source` now also `adzuna` or `reed` |
| `profiles` | Per user | Add `include_senior boolean`, `jobs_last_seen_at` |

Listings older than 30 days are deleted. A saved job is a copy, so it survives.

Shared tables still have row-level security on and no browser privileges. They hold no personal data.

## API

| Route | Purpose |
|---|---|
| `GET /api/jobs` | The user's matches with filters; marks them seen |
| `POST /api/jobs/refresh` | Fetch (through the cache), match to the register, score the best unscored jobs. One AI action |
| `POST /api/jobs/{match_id}/save` | Copy into `saved_jobs` |
| `POST /api/jobs/{match_id}/hide` | "Not for me" |
| `GET /api/visa-facts?salary=&employer=` | The offer-check panel |
| `POST /api/internal/refresh-sponsors` | Reload the register. Called by a weekly scheduled job with a secret header; also runnable as `python scripts/refresh_sponsors.py` |

## How matching works

1. **Search.** For each targeted role family, its UK job titles are searched in each preferred location, on both sources, limited to 14 days. Reed is also searched with its graduate filter. "Remote" is searched as a keyword.
2. **Cache.** A search already run by anyone in the last 6 hours is read from the database instead of the API.
3. **De-duplicate.** The same title, employer and town from both sources is kept once.
4. **Shortlist without AI.** Listings are ranked by how many of the user's skills and achievement keywords appear in the title and description.
5. **Score with AI.** The top 15 unscored listings go to the model in one call. For each, it lists what the advert asks for and marks each requirement as shown by a named achievement or as a gap. The percentage is requirements shown divided by requirements listed.
6. **Sponsor match.** The employer name is normalised (case, punctuation, "Ltd", "Limited", "plc", "LLP", "Group", "UK", trading-as names) and compared with the register's Skilled Worker entries. Exact match after normalising is "on the register"; a close match is "possible match"; otherwise "not found".

A requirement can be marked "shown" only by an achievement that exists; the achievement title returned by the model is checked against the user's own.

## Outside services and settings

| Service | Settings | Notes |
|---|---|---|
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Free developer account. Returns description snippets only |
| Reed | `REED_API_KEY` | Free. Key sent as the Basic-auth username. Full description from the job details call, fetched only for shortlisted jobs |
| gov.uk register | none | A CSV linked from the publication page; the file address changes with each update, so the page is read to find it |
| Scheduled job | `CRON_SECRET` | Weekly register reload on Vercel. Locally, run the script |

Visa thresholds live in `backend/data/visa_rules.json` with the source address and the date they were checked. They are never hard-coded elsewhere.

## Behaviours that must have tests

In addition to the standing list in `careerai-building-a-step`:

- A search inside the cache window makes no API call; outside it, exactly one per source.
- An API error, timeout or rate-limit answer from one source still returns the other source's jobs, with a notice naming the source that failed.
- Both sources failing shows "We could not reach the job sites. Try again shortly." and keeps the jobs already stored.
- The same job from both sources appears once.
- Senior titles are excluded by default and included when the setting is on.
- Fit: requirements marked "shown" by an achievement the user does not have are counted as gaps; zero requirements returns no score rather than dividing by zero; the label boundaries at 40, 60 and 80.
- A listing with no stated salary, or an Adzuna estimate, produces no salary comparison.
- Employer normalising: "Acme Ltd", "ACME LIMITED" and "Acme" match the same register entry; "Acme Recruitment" does not match "Acme".
- Only Skilled Worker route entries count as a match.
- An empty or unreadable register file leaves the existing register in place and reports failure.
- The internal refresh route answers 401 without the secret.
- User A's matches, saved and hidden jobs are invisible to user B, while both read the same shared listing.
- Hiding a job keeps it hidden after the next refresh.
- An application created from a listing carries its link, posted date and sponsor status.
- The visa facts response always includes the source address and the checked-on date.

## Check by hand

1. With real keys, refresh: real jobs appear for the user's targets and locations, newest first.
2. Open three adverts through "View advert": they are the same jobs.
3. Pick an employer known to be on the register and one known not to be: the labels are right.
4. Save a job, tailor a CV for it, add it to the tracker: the link, posted date and sponsor status carry through.
5. "Not for me" hides a job; refresh; it stays hidden.
6. Role family cards show job counts, median salary and sponsor share that match the list.
7. Compare the two thresholds on screen with gov.uk on the day.
8. A second account with different targets sees different matches and none of the first account's saved jobs.

## Task outline

1. Verify the three outside sources and the visa figures (see below); agree anything that differs.
2. Migration and database functions for listings, searches, sponsors, matches.
3. Adzuna and Reed clients with the shared cache, error handling and de-duplication.
4. Register download, load and employer matching; the refresh script and internal route.
5. Shortlisting and the AI fit-scoring task.
6. Routes: list, refresh, save, hide, visa facts.
7. The Jobs page and its filters.
8. Home, Career pathways, Applications and offer-check changes.
9. Privacy page update (job searches are sent to Adzuna and Reed without personal details).
10. Live checks, hand checks, documentation.

## Done when

A new user who has picked target roles sees real matched jobs within a minute of opening the Jobs page, each with a fit label they can trace to their own achievements and sponsorship facts they can verify, and can take any job through to a tailored CV and a tracked application without retyping anything.

## Verify at build time

These were true or believed true on 12 October 2026 and must be rechecked before coding.

- **Adzuna:** search is `https://api.adzuna.com/v1/api/jobs/gb/search/{page}` with `app_id` and `app_key`; results carry `title`, `description` (a snippet), `company.display_name`, `location`, `salary_min`, `salary_max`, `salary_is_predicted`, `created`, `redirect_url`. Check the free-tier call limits (believed to be a few hundred calls a day) and the terms on attribution and storing results. If the limits are too low for the cache design, tell the owner.
- **Reed:** `https://www.reed.co.uk/api/1.0/search` with `keywords`, `locationName`, `distanceFromLocation`, `graduate`, `resultsToTake` (maximum 100), `resultsToSkip`; details at `/api/1.0/jobs/{id}`. Check which fields the search returns (posting date and job address were not confirmed), whether its description is cut short, and the terms of use.
- **Register:** published at `https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers`, updated most working days. Check the file format and column names, and that reuse is allowed under the Open Government Licence.
- **Visa rules:** read the current Skilled Worker salary thresholds, the new-entrant rules and who qualifies, on gov.uk. Do not reuse the old demo's figures. Agree the exact on-screen wording with the owner, including whether to mention work limits on a Student visa.
- **Vercel:** whether scheduled jobs are available on the owner's plan and how the secret is passed.
