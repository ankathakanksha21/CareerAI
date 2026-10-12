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


# ---------- API fixtures ----------

@pytest.fixture
def client(conn, user_a, monkeypatch):
    """The API as user_a, with every route's database work running inside this test's
    rolled-back transaction instead of committing."""
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    import db
    import main
    from auth import User, current_user

    @contextmanager
    def in_test_transaction():
        with conn.transaction():  # a savepoint: a failing route rolls back only its own work
            yield conn

    monkeypatch.setattr(db, "transaction", in_test_transaction)
    monkeypatch.setenv("DAILY_AI_LIMIT", "40")
    monkeypatch.setenv("DAILY_VOICE_LIMIT", "3")
    main.app.dependency_overrides[current_user] = lambda: User(user_a, "a@example.test", "Test Person")
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()


@pytest.fixture
def as_user():
    """Switch which user the API sees: as_user(user_b)."""
    import main
    from auth import User, current_user

    def switch(user_id, name="Other Person"):
        main.app.dependency_overrides[current_user] = lambda: User(user_id, "other@example.test", name)
    return switch
