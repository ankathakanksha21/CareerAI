---
name: careerai-step-7-peers
description: Use when building, continuing or reviewing step 7 of the CareerAI roadmap - opt-in buddy groups of two or three users, peer matching, shared weekly progress, nudges, weekly check-ins, contact links, and the reporting, blocking and privacy rules for anything one user can see about another
---

# Step 7: peers

**Status:** Built on branch `step-7-peers`, 15 October 2026 (see "Where it stands" at the end). Design approved by the owner, 12 October 2026. **Depends on:** step 4 (weekly goals and streak). **Size:** medium, with the highest privacy risk of any step.
**REQUIRED:** follow `careerai-building-a-step`.

## Goal

A user far from family and support has two or three people in the same position who can see whether they kept going this week, and can nudge them when they did not.

The owner's notes: isolation is a real barrier for international students; a small job-search buddy group of two or three gives accountability and morale.

**This is the only step in which one user sees anything about another.** Every rule below exists to keep that small, chosen and reversible.

## Decisions already made (do not re-ask)

| Decision | Detail | Decided by |
|---|---|---|
| Shape | Buddy groups of 2 or 3 people with similar targets. No directory, no browsing | Owner, 12 Oct 2026 |
| What peers see | First name, university, course, target roles, and this week's progress (targets met, streak). Nothing until the user switches Peers on | Owner, 12 Oct 2026 |
| Never shown | Surname, email, visa type or dates, applications, employers, CVs, achievements, journal, transcripts | Owner, 12 Oct 2026 |
| Talking | No chat. A one-tap nudge, one short check-in line a week, and an optional contact link shared inside the group | Owner, 12 Oct 2026 |
| Matching | Done by the app, not chosen from a list: same broad field first, then same city or university. Both people accept before a group forms | Recommended; approved 12 Oct 2026 |
| Visa status is not used for matching | Matching on it would reveal it | Recommended; approved 12 Oct 2026 |
| No fake peers | With too few users there may be no match. The app says "You are on the list" and waits. It never shows invented people | Recommended; approved 12 Oct 2026 |
| Build now | Only 3 accounts existed on 15 October 2026, so most people will wait. Built anyway: it is honest while nobody matches, and the three accounts are what the hand checks need | Owner, 15 Oct 2026 |
| A different field as a fallback | Same field first. When nobody in the same field is waiting, the best other match by city, university and time waited is proposed; the proposal shows their target roles, so either can decline. The waiting message says "when someone joins", not "with similar targets" | Owner, 15 Oct 2026 |
| Reviewing reports | `scripts/peer_reports.py` lists open reports with the reason and the reported line as it was when reported. Flags mark a report handled, or switch the reported user's Peers off and bar them from rejoining. The owner runs it about weekly | Owner, 15 Oct 2026 |
| Code of conduct | 1. Be kind. Encourage; never mock, insult or pressure anyone. 2. Keep it to the job search. No selling, no recruiting for money, no asking for money or favours. 3. Keep what you see in the group to yourself. Never share another member's details or check-ins elsewhere. 4. Never ask anyone for passwords, documents, bank details or anything about their visa. 5. If you ever meet in person, meet somewhere public. 6. Report anything that makes you uncomfortable. Every report is reviewed, and anyone who breaks these rules loses access to buddy groups | Owner, 15 Oct 2026 (drafted by Claude, approved) |
| Fields | Accounting and finance; Banking and investment; Consulting; Data and analytics; Software and IT; Engineering; Science and research; Healthcare and life sciences; Law; Marketing, advertising and PR; Sales and business development; Human resources; Operations, logistics and supply chain; Project and product management; Design, media and creative; Education; Public sector and policy; Charity and social care; Property, architecture and construction; Energy and sustainability; Hospitality, retail and tourism | Owner, 15 Oct 2026 (drafted by Claude, approved) |
| Terms of use | Not ready. The owner writes them before Peers is launched to real users; recorded as a launch blocker | Owner, 15 Oct 2026 |
| The final review's findings | All 16 fixed (5 important, 11 minor), test first. Plan task 10 | Owner, 24 Oct 2026 |
| Names written surname-first | Buddies see the first word of the full name. The consent screen and the group page show the user exactly how they appear, and say to put their given name first in Profile if it is wrong. No separate display name | Owner, 24 Oct 2026 (one of two options offered by the review) |
| New proposals a day | At most 3 a London day for each person; a newcomer proposed into their group counts too. After that they wait with "We will look again tomorrow", and nobody is proposed to them or their group until then. Stops "Not this time" being used to browse everyone | Owner, 24 Oct 2026 |
| Nudges have fixed wording | No free text, so nothing to moderate. At most one nudge to each member per day | Recommended; approved 12 Oct 2026 |
| Check-in line | Free text, 140 characters, one per week, with Report on every line | Recommended; approved 12 Oct 2026 |
| Contact link | One link per user, LinkedIn or WhatsApp only, visible only to current members of their group | Recommended; approved 12 Oct 2026 |
| Safety | Leave at any time; block a member; report; confirm being 18 or over and accept a short code of conduct when switching Peers on | Recommended; approved 12 Oct 2026 |
| Moderation | Reports are stored for the owner to review. There is no admin screen in this step; a script lists open reports | Recommended; approved 12 Oct 2026 |

## In scope

1. Switching Peers on, with a consent screen showing exactly what others will see.
2. Matching into groups of 2 or 3.
3. The group page: members, shared weekly progress, group streak.
4. Nudges and weekly check-ins.
5. Contact links.
6. Leave, block, report.
7. Peers returning to the menu and to Home.

## Out of scope

In-app chat or direct messages; a member directory; peer CV reviews or shared documents; mock interviews between peers; session notes; email or push notifications; an admin screen.

## What the user sees

**Peers page, switched off (the default).** An explanation of buddy groups and a button, "Join a buddy group". The consent screen lists, in two columns, what group members will see and what they will never see, with two ticks: "I am 18 or over" and "I agree to the code of conduct". The user also confirms their field from a short fixed list (the app suggests one from their target roles).

**Waiting.** "You are on the list. We will match you when someone with similar targets joins." Shown honestly for as long as it takes.

**A proposed group.** "We found a buddy for you": first name, university, course, target roles. Accept or Not this time. Nothing further is shown, and no contact link, until everyone has accepted. A declined pairing is not proposed again.

**The group page.**

| Element | Detail |
|---|---|
| Members | First name, university, course, target roles |
| This week | For each member: how many of their weekly targets are met, and their streak in weeks. No counts of applications, no employer names |
| Group streak | Weeks in which every member met their targets |
| Check-in | "What is your focus this week?" One line each, editable until the week ends. Report beside each line |
| Nudge | "Send a nudge" beside each member. Fixed wording, shown on their Home page |
| Contact link | "Share a contact link" (LinkedIn or WhatsApp). Shown to the group as a button |
| Controls | Leave group; Block and leave; Report; Find a new group (when a member has been inactive for three weeks) |

**Home.** A small group card: members' first names with a tick or a dot for this week, and any nudge received.

**Switching Peers off** removes the user from their group and from matching at once. Their check-ins and nudges disappear for the others.

## Data changes (migration `00N_peers`)

| Table | Holds |
|---|---|
| `peer_profiles` | One per user: `enabled`, `consented_at`, `over_18`, `field`, `contact_link`, `waiting_since` |
| `peer_groups` | `status` (proposed, active, closed), `created_at` |
| `peer_group_members` | `group_id`, `user_id`, `status` (proposed, accepted, declined, left), `joined_at` |
| `peer_checkins` | `group_id`, `user_id`, `week_start`, `text` |
| `peer_nudges` | `group_id`, `from_user`, `to_user`, `at` |
| `peer_blocks` | `blocker`, `blocked` |
| `peer_reports` | `reporter`, `about_user`, `group_id`, `checkin_id` (nullable), `reason`, `at`, `handled` |

All rows are deleted with the account. A group left with fewer than two accepted members closes.

## The one exception to the privacy rule, kept narrow

Everywhere else, a database function returns only the caller's rows. Here, exactly one function, `peer_view(conn, viewer_id, member_id)`, returns another user's information, and:

- it returns only the fields in "What peers see", built from an explicit list in code, never from `select *`;
- it returns nothing unless both users are accepted members of the same active group, neither has blocked the other, and the member has Peers switched on;
- a proposed member's view is the same minus the weekly progress and contact link.

No other code path may read another user's rows. Reviewers must check this.

## API

| Route | Purpose |
|---|---|
| `GET /api/peers` | The caller's peer status: off, waiting, proposed or in a group, with the permitted views |
| `POST /api/peers/join`, `POST /api/peers/leave-all` | Switch Peers on (with the two confirmations and field) or off |
| `POST /api/peers/groups/{id}/accept`, `/decline`, `/leave` | Respond to a proposal; leave a group |
| `PUT /api/peers/groups/{id}/checkin` | This week's line |
| `POST /api/peers/groups/{id}/nudge` | `{to}` |
| `PUT /api/peers/contact-link` | Set or clear the link |
| `POST /api/peers/block`, `POST /api/peers/report` | Safety actions |

## How matching works

Run when a user joins the list or asks for a new group. No scheduled job.

1. Candidates are users who are waiting, have Peers on, are not the caller, are not blocked in either direction, and have not already declined each other.
2. Prefer the same field. Among those, prefer the same city, then the same university, then whoever has waited longest.
3. A group of two that is active and has room may take a third in the same field.
4. A proposal expires after 7 days without a reply, and both return to the list.

The field comes from a fixed list of about twenty broad areas (for example data and analytics, software, finance, marketing, engineering). The app suggests one from the user's target roles; the user confirms it.

## AI tasks

One: suggest a field from the user's target role names, chosen from the fixed list. An answer outside the list is ignored and the user picks by hand.

## Outside services and settings

None.

## Behaviours that must have tests

In addition to the standing list in `careerai-building-a-step`:

- `peer_view` returns exactly the permitted fields and no others, for a user who has a surname, visa details, applications and achievements.
- It returns nothing for: a stranger; a member of a different group; a former member; a blocked or blocking user; a member who has switched Peers off; a closed group.
- A proposed member sees no weekly progress and no contact link.
- Switching Peers off removes the user from every other member's view in the same request.
- Deleting an account removes that user from every view and closes a group left with one member.
- Matching never pairs a user with themselves, with someone they blocked or who blocked them, or with someone they have declined.
- A group never exceeds three accepted members, including when two people accept at the same moment.
- The same field is preferred over a different one; with nobody suitable the user stays waiting and no group is created.
- A nudge to the same member twice in one day is refused; a nudge to someone outside the group is refused.
- A check-in over 140 characters is refused; a second check-in in the same week replaces the first; other groups cannot read it.
- A contact link to any host other than LinkedIn or WhatsApp is refused, as is anything that is not `https`.
- A report hides that check-in from the reporter at once and is stored for review.
- Weekly progress shows targets met and streak only: the response contains no application counts, company names or dates.
- Joining without both confirmations is refused.
- Every peers route answers 401 without a token, and 404 for a group the caller is not in.

## Check by hand

Needs three real accounts.

1. Account A joins: sees "You are on the list". No invented peers anywhere.
2. Account B joins in the same field: both see a proposal with only the permitted details. Both accept.
3. On the group page, compare what B sees of A with A's own profile: no surname, visa, applications or employers.
4. A sends a nudge: it appears on B's Home. A second nudge the same day is refused.
5. Both write a check-in; B reports A's line: it disappears for B.
6. A shares a LinkedIn link; B sees it. A leaves: B no longer sees A or the link.
7. Account C joins and is added as a third. A fourth account is not added to that group.
8. B blocks C: they are separated and never matched again.
9. Delete account A: nothing of A remains visible to anyone.

## Task outline

1. Agree the code of conduct, the field list and how reports will be reviewed with the owner.
2. Migration; peer profiles and consent.
3. `peer_view` and its tests, before anything that uses it.
4. Matching, proposals, accept and decline.
5. The group page: members, weekly progress, group streak.
6. Nudges and check-ins.
7. Contact links.
8. Leave, block, report; the report-listing script.
9. Peers on Home and in the menu; the consent screen.
10. Privacy page update (what group members see); live checks, three-account hand checks, documentation.

## Done when

Three real accounts can form a group, see only the agreed details about each other, nudge and check in, and leave, block or delete without leaving anything behind, and a user with nobody to match sees an honest waiting message.

## Verify at build time

- How many real users exist. With very few, most people will wait; tell the owner before building, since it affects whether this step is worth doing yet.
- The owner's plan for reviewing reports, and whether a code of conduct and terms of use are ready. Do not launch user-to-user features without them.
- That step 4's weekly targets and streak exist, including the third target from step 6 if it has shipped.
- WhatsApp and LinkedIn link formats to accept.

## Verified at build time (15 October 2026)

- **Users:** 3 accounts, probably all the owner's. Built anyway (owner's choice).
- **Step 4's targets:** `habits.this_week` and `habits.streaks` take three targets, step 6's outreach included.
- **LinkedIn link:** LinkedIn's help page: the custom part of a profile address is 3 to 100 letters or numbers; default ones add hyphens and digits. Accepted: `https://(www.|xx.)linkedin.com/in/<handle>`, stored as `https://www.linkedin.com/in/<handle>`.
- **WhatsApp link:** `https://wa.me/<number>`, the full international number in digits. WhatsApp's own help page did not load; two guides citing it agree. Other WhatsApp forms (QR links, `api.whatsapp.com`) are left out rather than guessed.
- **Reports and code of conduct:** agreed with the owner (table above). Terms of use: not ready; a launch blocker.

## Changed at build time

| What | Why |
|---|---|
| A third member needs the yes of the newcomer and of every current member | "Both people accept before a group forms": nobody shares their week with someone they did not accept |
| Pairings declined, left unanswered for 7 days, or left are never proposed again | Re-proposing the same silent person, or someone just left, helps nobody |
| Leaving (and "Find a new group") puts the user back on the list; switching Peers off is how to stop | One way out of a group, one way to stop |
| Blocking a proposed newcomer turns them away and the blocker stays | Leaving one's own group because of a newcomer would punish the wrong person |
| Matching also runs when a waiting user opens Home or Peers | A match missed when two people join at the same moment heals on the next visit, still with no scheduled job |
| "Same city" is a shared preferred location, not the CV town | Every user has preferred locations |
| Pages name a member by their membership id, never a user id | Nothing that identifies an account reaches the browser |

## Where it stands

Built, tested and checked in a browser with three temporary users (never saved). The final review's 16 findings were fixed on 24 October 2026 (plan task 10), with 3 new proposals a day as the cap and "Your group will see you as" for surname-first names. The owner's three-account hand checks, the terms of use, and a signed-in session are left. See ARCHITECTURE sections 27 and 28.
