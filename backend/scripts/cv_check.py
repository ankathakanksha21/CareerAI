"""What one real CV file reads as: how much text, whether it was cut, and its first lines in the
order the AI will receive them. For looking into a layout that reads badly. Everything stays on
this machine: nothing is sent anywhere and nothing is saved.

Run from backend/ with the venv active:  python scripts/cv_check.py path/to/cv.pdf"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cvfile  # noqa: E402

SHOWN = 20


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = Path(sys.argv[1])
    try:
        text, cut = cvfile.text(path.read_bytes())
    except OSError as e:
        print(f"Could not open {path.name}: {type(e).__name__}")
        return 1
    except cvfile.Unreadable as e:
        print(f"Refused, with the message the user would see: {e}")
        return 1
    lines = text.splitlines()
    print(f"{path.name}: {len(text):,} characters in {len(lines)} lines{', cut for length' if cut else ''}")
    print(f"First {min(SHOWN, len(lines))} lines:")
    for line in lines[:SHOWN]:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
