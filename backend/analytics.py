"""Tracker analytics and the rule-based diagnosis that closes the loop.
Pure functions over the user's own rows. Each finding points back to the page that fixes it."""
from collections import defaultdict

STAGES = ("applied", "no_response", "rejected", "screening", "interview", "rejected_after_interview", "offer")
SOURCES = ("Company site", "Referral", "LinkedIn", "Indeed", "Reed", "Graduate job board",
           "University careers service", "Recruiter", "Other")
RESPONDED = {"screening", "interview", "rejected_after_interview", "offer"}
INTERVIEWED = {"interview", "rejected_after_interview", "offer"}
REJECTED = {"rejected", "rejected_after_interview"}
JOB_BOARDS = {"LinkedIn", "Indeed", "Reed", "Graduate job board"}

MIN_APPS_FOR_REPLY_RULE = 4
LOW_REPLY_RATE = 0.15
MIN_TIMED_APPS = 4
FAST_DAYS = 2  # applied within 48 hours of posting
MIN_NAMED_ADVERTS = 10    # adverts naming their employer needed before judging a role's sponsors
LOW_SPONSOR_SHARE = 0.2


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def responded(app) -> bool:
    """Whether the employer replied. A rejection after a phone screen was a reply, though its stage
    is the same as a rejection at the CV stage; where it ended says which."""
    return app["stage"] in RESPONDED or (app["stage"] == "rejected" and app.get("rejected_at_stage") == "screening")


def _row(label, apps):
    n = len(apps)
    responses = sum(responded(a) for a in apps)
    return {
        "label": label,
        "applied": n,
        "responses": responses,
        "interviews": sum(a["stage"] in INTERVIEWED for a in apps),
        "offers": sum(a["stage"] == "offer" for a in apps),
        "response_rate": round(responses / n, 2) if n else 0,
    }


def _key(value, known):
    """An id that is not one of the user's current rows counts as missing."""
    return value if value in known else None


def group(apps, key, labels=None, missing=None):
    """One row per distinct value of `key`. `labels` maps ids to names; `missing` names the rest."""
    buckets = defaultdict(list)
    for a in apps:
        buckets[a.get(key) if labels is None else _key(a.get(key), labels)].append(a)
    rows = [_row(k if labels is None else labels.get(k, missing), v) | {"key": k} for k, v in buckets.items()]
    return sorted(rows, key=lambda r: -r["applied"])


def _days_after_posting(a):
    return (a["applied_on"] - a["posted_on"]).days


def compute(applications, families, cv_versions, stories, market=None):
    """`market` is the live advert figures per targeted role family (see jobs.market), when there are any."""
    fam_names = {f["id"]: f["name"] for f in families}
    cv_names = {c["id"]: c["name"] for c in cv_versions}
    by_family = group(applications, "role_family_id", fam_names, "No role family")
    by_cv = group(applications, "cv_version_id", cv_names, "No CV recorded")
    by_source = group(applications, "source")
    timed = [a for a in applications if a.get("posted_on")]  # no posted date: speed is unknown, so left out
    fast = [a for a in timed if _days_after_posting(a) <= FAST_DAYS]
    slow = [a for a in timed if _days_after_posting(a) > FAST_DAYS]
    timing = {"fast": _row("Within 48 hours", fast), "slow": _row("After 48 hours", slow), "timed": len(timed),
              "avg_days": round(sum(_days_after_posting(a) for a in timed) / len(timed), 1) if timed else 0}
    return {
        "funnel": _row("All", applications),
        "by_family": by_family,
        "by_cv": by_cv,
        "by_source": by_source,
        "timing": timing,
        "findings": sorted(diagnose(applications, cv_versions, stories, by_family, by_source, timing, fam_names, cv_names)
                           + lesson_findings(applications), key=lambda f: -f["severity"])
                    + sponsor_findings(families, market or {}),
    }


def diagnose(apps, cv_versions, stories, by_family, by_source, timing, fam_names, cv_names):
    findings = []

    # 1. Low reply rate for a role family: CV or tailoring problem
    for row in by_family:
        if row["applied"] < MIN_APPS_FOR_REPLY_RULE or row["response_rate"] >= LOW_REPLY_RATE:
            continue
        fam = row["key"]  # None for the applications that have no role family
        used = {_key(a.get("cv_version_id"), cv_names) for a in apps if _key(a.get("role_family_id"), fam_names) == fam}
        own_cv = fam is not None and any(cv["id"] in used and cv.get("role_family_id") == fam for cv in cv_versions)
        if own_cv:
            detail = ""
        elif used <= {None}:
            detail = " None of them used a tailored CV."
        elif fam is None:
            detail = ""
        else:
            names = ", ".join(sorted(cv_names[c] for c in used if c))
            detail = f" They used a CV written for another role ({names})."
        subject = f"{row['label']} applications" if fam else "Applications without a role family"
        findings.append({
            "id": f"cv-{fam or 'none'}", "type": "cv", "severity": 3,
            "title": f"{subject} are not getting replies",
            "evidence": f"{plural(row['responses'], 'response')} from {plural(row['applied'], 'application')}.{detail}",
            "action": (f"Tailor a {row['label']} CV from your profile, then send the next batch with it." if fam
                       else "Tailor a CV to each job from your profile, then send the next batch with it."),
            "link": {"page": "resume", "label": "Tailor a CV"},
        })

    # 2. Interviews but no offers: storytelling or communication problem
    funnel = _row("All", apps)
    if funnel["interviews"] >= 3 and funnel["offers"] == 0:
        weak = sum(s.get("strength") != "strong" for s in stories)
        if not stories:
            note = "You have no STAR stories saved yet."
        elif weak:
            note = f"{weak} of your {len(stories)} STAR stories still need a number or detail."
        else:
            note = "Your STAR stories are complete, so practise saying them out loud."
        findings.append({
            "id": "story", "type": "story", "severity": 3,
            "title": "You reach interviews but they are not turning into offers",
            "evidence": f"{plural(funnel['interviews'], 'interview')}, 0 offers. {note}",
            "action": "Run a mock interview and strengthen your STAR stories before the next one.",
            "link": {"page": "interview", "label": "Practise an interview"},
        })

    # 3. Referrals work but are rarely used: network problem
    ref = next((r for r in by_source if r["key"] == "Referral"), None)
    board_row = _row("Job boards", [a for a in apps if a["source"] in JOB_BOARDS])
    if (ref and board_row["applied"] and ref["response_rate"] > board_row["response_rate"]
            and ref["applied"] / len(apps) < 0.2):
        findings.append({
            "id": "network", "type": "network", "severity": 2,
            "title": "Referrals work for you, but you rarely use them",
            "evidence": f"Referrals got replies {ref['responses']} of {ref['applied']} times. Job boards: {board_row['responses']} of {board_row['applied']}.",
            "action": "Ask people you know inside companies that are hiring for a referral before you apply.",
            "link": {"page": "networking", "label": "Find people"},
        })

    # 4. Slow applications: timing problem
    if (timing["timed"] >= MIN_TIMED_APPS and timing["avg_days"] > 3
            and timing["fast"]["response_rate"] > timing["slow"]["response_rate"]):
        findings.append({
            "id": "timing", "type": "timing", "severity": 2,
            "title": "You apply too long after roles are posted",
            "evidence": f"Average {timing['avg_days']} days after posting. Within 48 hours: {timing['fast']['responses']} of {timing['fast']['applied']} replied. Later: {timing['slow']['responses']} of {timing['slow']['applied']}.",
            "action": "Check new roles daily and apply within 48 hours of posting.",
            "link": {"page": "jobs", "label": "See new jobs"},
        })

    return sorted(findings, key=lambda f: -f["severity"])


MIN_LESSONS = 3  # lessons from rejections that point to the same page before they make a finding
LESSON_PAGES = {
    "resume": ("your CV", "Open Resume"),
    "interview": ("your interview answers", "Practise an interview"),
    "profile": ("the evidence on your profile", "Open your profile"),
}


def _names(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def lesson_findings(apps):
    """6. Three or more rejections whose lessons point to the same page: a pattern, not bad luck."""
    by_page = defaultdict(list)
    for a in apps:
        lesson = a.get("lesson") or {}
        if a["stage"] in REJECTED and lesson.get("page") in LESSON_PAGES:
            by_page[lesson["page"]].append(a)
    findings = []
    for page, rejected in by_page.items():
        if len(rejected) < MIN_LESSONS:
            continue
        rejected.sort(key=lambda a: a["lesson"].get("made_on") or "")
        what, label = LESSON_PAGES[page]
        findings.append({
            "id": f"lessons-{page}", "type": "lessons", "severity": 3,
            "title": f"{len(rejected)} of your rejections point to {what}",
            "evidence": f"The lessons from {_names([a['company'] for a in rejected])} each suggest a change to {what}.",
            "action": rejected[-1]["lesson"]["one_change"],
            "link": {"page": page, "label": label},
        })
    return findings


def sponsor_findings(families, market):
    """5. A target role where few advertising employers hold a sponsor licence: a direction problem.
    Counts only adverts that name their employer; an agency advert says nothing either way."""
    findings = []
    for family in families:
        figures = market.get(family["id"])
        if not family.get("targeted") or not figures or figures["named"] < MIN_NAMED_ADVERTS:
            continue
        if figures["listed"] / figures["named"] >= LOW_SPONSOR_SHARE:
            continue
        findings.append({
            "id": f"sponsor-{family['id']}", "type": "sponsor", "severity": 2,
            "title": f"Few {family['name']} roles come from licensed sponsors",
            "evidence": f"{figures['listed']} of {figures['named']} current adverts that name their employer are from employers on the sponsor register.",
            "action": "Turn on Sponsors only in Jobs, or look at a neighbouring role where more employers sponsor.",
            "link": {"page": "jobs", "label": "Open Jobs"},
        })
    return findings


NEXT_STEPS = (
    ("profile", "Build your profile", "Your CVs, stories and interview practice are all built from it.", "profile"),
    ("roles", "Pick your target roles", "Your targets decide what the app prepares you for.", "pathways"),
    ("job", "Save a job you want", "Pick one from Jobs, or paste an advert, so your CV and practice fit a real role.", "jobs"),
    ("cv", "Tailor a CV for it", "UK employers shortlist on evidence that matches the job description.", "resume"),
    ("interview", "Practise an interview", "Most UK interviews expect STAR answers, said out loud.", "interview"),
    ("application", "Log your first application", "The tracker can only tell you what to fix once it has your applications.", "applications"),
)


def next_steps(state):
    """The getting-started checklist, ticked from what the user has actually done."""
    done = {
        "profile": bool(state["achievements"]),
        "roles": any(f.get("targeted") for f in state["role_families"]),
        "job": bool(state["saved_jobs"]),
        "cv": bool(state["cv_versions"]),
        "interview": any(j.get("type") == "interview" for j in state["journal"]),
        "application": bool(state["applications"]),
    }
    return [{"id": i, "text": text, "why": why, "page": page, "done": done[i]} for i, text, why, page in NEXT_STEPS]
