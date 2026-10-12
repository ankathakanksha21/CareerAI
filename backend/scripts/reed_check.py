"""One real search and one real advert from Reed, to confirm the reply is shaped the way reed.py
expects. Prints field names, value types and counts. Never prints the key.

Run from backend/ with the venv active:  python scripts/reed_check.py ["job title" [location]]"""
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reed  # noqa: E402
from config import jobs_configured  # noqa: E402


def shape(raw: dict) -> str:
    return ", ".join(f"{k}: {type(v).__name__}" for k, v in raw.items())


def main() -> int:
    if not jobs_configured():
        print("REED_API_KEY is not set in backend/.env")
        return 1
    keywords = sys.argv[1] if len(sys.argv) > 1 else "data analyst"
    location = sys.argv[2] if len(sys.argv) > 2 else "London"
    try:
        for posted_by in ("employer", "agency"):
            raw = reed._get(reed.SEARCH_URL, {"keywords": keywords, "locationName": location,
                                              reed.POSTED_BY[posted_by]: "true", "resultsToTake": reed.PAGE_SIZE})
            results = raw.get("results") or []
            parsed = [x for x in (reed.parse(r, posted_by) for r in results) if x]
            print(f"\n{posted_by}: {len(results)} results of {raw.get('totalResults')} in total; {len(parsed)} readable")
            if not results:
                continue
            print("  reply keys:", ", ".join(raw))
            print("  fields:", shape(results[0]))
            print("  raw posting date looks like:", repr(results[0].get("date") or results[0].get("datePosted")))
            ages = [(date.today() - x["posted_on"]).days for x in parsed]
            print("  days since posting, in the order returned:", ages[:25])
            print("  posted within 14 days:", sum(a <= 14 for a in ages), "| within 2 days:", sum(a <= 2 for a in ages))
            print("  description lengths:", sorted(Counter(len(x["description"]) // 100 * 100 for x in parsed).items()))
            print("  salaries: annual", sum(x["salary_annual"] for x in parsed), "| a rate",
                  sum(bool(x["salary_min"] or x["salary_max"]) and not x["salary_annual"] for x in parsed),
                  "| not stated", sum(not (x["salary_min"] or x["salary_max"]) for x in parsed))
            print("  links on reed.co.uk:", sum(x["url"] == str(r.get("jobUrl")) for x, r in zip(parsed, results)), "of", len(parsed))
        if parsed:
            one = reed._get(reed.JOB_URL.format(id=parsed[0]["source_id"]))
            print("\nadvert in full, fields:", shape(one))
            full = reed.details(parsed[0]["source_id"])
            print("  description length:", len(full["description"]), "| salary annual:", full["salary_annual"],
                  "| salary type:", repr(one.get("salaryType")), "| posted:", full.get("posted_on"))
    except reed.ReedError as e:
        print(f"Reed request failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
