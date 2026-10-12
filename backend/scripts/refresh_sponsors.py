"""Load today's gov.uk register of licensed sponsors into the database, replacing the stored copy.
On Vercel a weekly scheduled job does the same through /api/internal/refresh-sponsors.

Run from backend/ with the venv active:  python scripts/refresh_sponsors.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sponsors  # noqa: E402


def main() -> int:
    started = time.time()
    try:
        done = sponsors.refresh()
    except sponsors.RegisterError as e:
        print(f"Not loaded; the stored register is unchanged. {e}")
        return 1
    print(f"Loaded {done['rows']} Skilled Worker sponsors, published {done['published_on']}, in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
