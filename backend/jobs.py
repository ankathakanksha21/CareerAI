"""Finding and judging jobs: which searches to run for a user, which adverts to score first,
and how an advert's fit is worked out. Pure functions and outside calls; the SQL is in repo.py."""

FIT_BANDS = ((80, "direct"), (60, "near"), (40, "stretch"))  # below the last: not a match
SHOWN_ON_CARD = 3


# ---------- fit ----------

def fit_label(percent: int) -> str:
    return next((label for floor, label in FIT_BANDS if percent >= floor), "none")


def fit(requirements: list[dict], achievement_titles: list[str]) -> dict | None:
    """How much of what an advert asks for the user already shows: requirements evidenced, out of
    requirements listed. A requirement counts only if the model named an achievement the user
    really has. None when the advert listed nothing to judge."""
    mine = {t.strip().lower(): t for t in achievement_titles}
    shown, gaps = [], []
    for r in requirements:
        text = r["need"].strip()
        if not text:
            continue
        title = mine.get(r.get("shown_by", "").strip().lower())
        if title:
            shown.append({"need": text, "achievement": title})
        else:
            gaps.append(text)
    total = len(shown) + len(gaps)
    if not total:
        return None
    percent = round(100 * len(shown) / total)
    return {"percent": percent, "label": fit_label(percent), "shown": shown[:SHOWN_ON_CARD], "gaps": gaps[:SHOWN_ON_CARD]}
