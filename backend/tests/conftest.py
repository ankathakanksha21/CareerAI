import uuid

import pytest

import config


@pytest.fixture
def no_env_file(monkeypatch, tmp_path):
    """Hide backend/.env so a test sees only the variables it sets itself."""
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "none")


# ---------- database fixtures (tests marked "db") ----------

@pytest.fixture
def conn():
    """One connection per test. Everything the test writes is rolled back at the end."""
    if not config.env("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    import db
    connection = db.connect()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _throwaway_user(conn) -> str:
    """A login that exists only inside this test's transaction."""
    user_id = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, email) values (%s, %s)", (user_id, f"test-{user_id}@example.test"))
    return user_id


@pytest.fixture
def user_a(conn) -> str:
    return _throwaway_user(conn)


@pytest.fixture
def user_b(conn) -> str:
    return _throwaway_user(conn)
