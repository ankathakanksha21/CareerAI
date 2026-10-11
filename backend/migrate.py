"""Apply the SQL files in migrations/ that this database has not seen yet, in filename order.

Run from backend/ with the venv active:  python migrate.py
Each applied file is recorded in schema_migrations, so running it again is harmless."""
from pathlib import Path

import db

MIGRATIONS = Path(__file__).parent / "migrations"


def _ensure_table(conn) -> None:
    conn.execute("create table if not exists schema_migrations "
                 "(version text primary key, applied_at timestamptz not null default now())")
    conn.execute("alter table schema_migrations enable row level security")
    conn.execute("revoke all on schema_migrations from anon, authenticated")


def pending(conn) -> list[str]:
    _ensure_table(conn)
    applied = {r["version"] for r in conn.execute("select version from schema_migrations").fetchall()}
    return sorted(p.stem for p in MIGRATIONS.glob("*.sql") if p.stem not in applied)


def apply_all(conn) -> list[str]:
    """Apply every pending migration on this connection. The caller commits."""
    versions = pending(conn)
    for version in versions:
        conn.execute((MIGRATIONS / f"{version}.sql").read_text(encoding="utf-8"))
        conn.execute("insert into schema_migrations (version) values (%s)", (version,))
    return versions


if __name__ == "__main__":
    with db.transaction() as connection:
        done = apply_all(connection)
    print("\n".join(f"applied {v}" for v in done) or "nothing to apply")
