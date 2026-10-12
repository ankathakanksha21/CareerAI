"""Per-user daily caps on AI actions and voice sessions, so one account cannot run up the bill.
A day runs midnight to midnight, Europe/London. The caps come from DAILY_AI_LIMIT and DAILY_VOICE_LIMIT."""
import repo
from config import daily_limit

KINDS = ("ai", "voice")


class LimitReached(Exception):
    def __init__(self, kind: str):
        super().__init__(f"daily {kind} limit reached")
        self.kind = kind


def allowed(conn, user_id, kind: str) -> bool:
    return repo.count_usage_today(conn, user_id, kind) < daily_limit(kind)


def check_and_record(conn, user_id, kind: str, action: str, *, retry_window_s: int = 0) -> None:
    """Count one use, or raise LimitReached. With retry_window_s, a repeat of the same action
    within that many seconds is the same attempt being retried and is not counted again."""
    if retry_window_s:
        since = repo.seconds_since_last_usage(conn, user_id, kind, action)
        if since is not None and since <= retry_window_s:
            return
    if not allowed(conn, user_id, kind):
        raise LimitReached(kind)
    repo.record_usage(conn, user_id, kind, action)


def usage(conn, user_id) -> dict:
    return {k: {"used": repo.count_usage_today(conn, user_id, k), "limit": daily_limit(k)} for k in KINDS}
