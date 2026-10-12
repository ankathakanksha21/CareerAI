"""The test fixtures themselves. The tests share the real database, so a fixture that commits
would leave test rows behind, or wipe a shared table."""
import pytest

pytestmark = pytest.mark.db

MARKER = "zzqx-fixture-check"


def test_db_transaction_in_tests_never_commits(conn, own_transaction):
    import db
    with db.transaction() as c:  # the first work on this connection, as in a test that starts by calling the code
        c.execute("insert into reference_meta (key) values (%s)", (MARKER,))
    other = db.connect()
    try:
        committed = other.execute("select count(*) as n from reference_meta where key = %s", (MARKER,)).fetchone()["n"]
        if committed:  # do not leave it behind for the next run
            conn.rollback()
            other.execute("delete from reference_meta where key = %s", (MARKER,))
            other.commit()
        assert committed == 0, "db.transaction() committed during a test"
    finally:
        other.close()
