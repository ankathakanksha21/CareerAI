"""Reports about buddy groups (step 7), for the app's owner to review. There is no admin screen:
run this about once a week, from backend/ with the venv active.

  python scripts/peer_reports.py                     list open reports, oldest first
  python scripts/peer_reports.py --handled REPORT_ID mark one report handled
  python scripts/peer_reports.py --bar USER_ID       switch that user's Peers off and stop them switching it on again

It prints ids, reasons and the reported line, never names or email addresses: find an account by
its id in the Supabase dashboard (Authentication, Users)."""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import peerdb  # noqa: E402


def _id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise argparse.ArgumentTypeError("not an id") from None


def _text(value: str) -> str:
    """What a user wrote, with anything that is not printable shown as an escape (\\x1b, \\r), so a
    line cannot move the cursor and rewrite or erase itself or the lines around it."""
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode("ascii") for c in value)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Review reports about buddy groups.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--handled", type=_id, metavar="REPORT_ID", help="mark one report handled")
    action.add_argument("--bar", type=_id, metavar="USER_ID", help="switch a user's Peers off for good")
    args = parser.parse_args(argv)
    with db.transaction() as conn:
        if args.handled:
            done = peerdb.mark_handled(conn, args.handled)
            print("Marked handled." if done else "No open report has that id.")
            return 0 if done else 1
        if args.bar:
            if not peerdb.bar(conn, args.bar):
                print("No user has that id.")
                return 1
            print("Barred: Peers is off for that user, and they cannot switch it on again.")
            return 0
        reports = peerdb.open_reports(conn)
    if not reports:
        print("No open reports.")
        return 0
    for r in reports:
        print(f"Report {r['id']}  {r['at']:%d %b %Y %H:%M}")
        print(f"  About user {r['about_user']} ({r['about_them']} open about them), from user {r['reporter']}")
        print(f"  Reason: {r['reason']}")
        if r["details"]:
            print(f"  Details: {_text(r['details'])}")
        if r["checkin_text"]:
            print(f"  The line reported: {_text(r['checkin_text'])}")
    print(f"{len(reports)} open. Mark one handled with --handled REPORT_ID, or bar a user with --bar USER_ID.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
