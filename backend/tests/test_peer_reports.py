"""The owner's report script, run inside the test's rolled-back transaction. It is read by id,
never by counting the real table."""
import importlib.util
import uuid
from pathlib import Path

import pytest

import peerdb

pytestmark = pytest.mark.db


def script():
    spec = importlib.util.spec_from_file_location("peer_reports", Path(__file__).resolve().parent.parent / "scripts" / "peer_reports.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def new_user(conn) -> str:
    user_id = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, email) values (%s, %s)", (user_id, f"test-{user_id}@example.test"))
    return user_id


@pytest.fixture
def reported(conn, own_transaction):
    """A report by one test user about another's check-in, in a group of two."""
    a, b = new_user(conn), new_user(conn)
    group = conn.execute("insert into peer_groups (status, active_since) values ('active', current_date) returning id").fetchone()["id"]
    for slot, user in enumerate((a, b), start=1):
        conn.execute("insert into peer_profiles (user_id, enabled, consented_at, over_18, field) values (%s, true, now(), true, 'data')", (user,))
        conn.execute("insert into peer_group_members (group_id, user_id, slot, status, yes_from, joined_at) values (%s, %s, %s, 'accepted', %s, now())",
                     (group, user, slot, [a, b]))
    line = conn.execute("insert into peer_checkins (group_id, user_id, week_start, text) values (%s, %s, current_date, 'Zzqx rude line') returning id",
                        (group, a)).fetchone()["id"]
    report = conn.execute("insert into peer_reports (reporter, about_user, group_id, checkin_id, checkin_text, reason, details) "
                          "values (%s, %s, %s, %s, 'Zzqx rude line', 'unkind', 'Zzqx details') returning id", (b, a, group, line)).fetchone()["id"]
    return {"a": a, "b": b, "group": str(group), "report": str(report)}


def test_lists_open_reports_with_the_line_and_no_names(reported, capsys):
    assert script().main([]) == 0
    out = capsys.readouterr().out
    assert f"Report {reported['report']}" in out
    assert "Unkind, harassing or threatening" in out and "Zzqx rude line" in out and "Zzqx details" in out
    assert reported["a"] in out and "example.test" not in out


def test_marks_one_handled(reported, capsys):
    run = script()
    assert run.main(["--handled", reported["report"]]) == 0
    assert "Marked handled." in capsys.readouterr().out
    run.main([])
    assert reported["report"] not in capsys.readouterr().out
    assert run.main(["--handled", reported["report"]]) == 1


def test_bars_a_user(conn, reported, capsys):
    assert script().main(["--bar", reported["a"]]) == 0
    me = peerdb.get_profile(conn, reported["a"])
    assert me["enabled"] is False and me["barred_at"] is not None
    with pytest.raises(peerdb.Barred):
        peerdb.switch_on(conn, reported["a"], field="data")


def test_refuses_an_id_that_is_not_one(capsys):
    with pytest.raises(SystemExit):
        script().main(["--handled", "not-an-id"])
