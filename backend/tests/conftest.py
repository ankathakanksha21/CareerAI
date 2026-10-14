import uuid

import pytest

import config


@pytest.fixture
def no_env_file(monkeypatch, tmp_path):
    """Hide backend/.env so a test sees only the variables it sets itself."""
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "none")


# ---------- the model ----------

@pytest.fixture(autouse=True)
def no_real_model(monkeypatch):
    """No test reaches the real model by accident: an AI task that was not replaced fails loudly."""
    import ai

    def refuse(*args, **kwargs):
        raise AssertionError("a test called the real model: replace the AI task it uses")
    monkeypatch.setattr(ai, "complete_json", refuse)


@pytest.fixture(autouse=True)
def no_real_research(monkeypatch):
    """No test reaches Companies House, an employer's website or the search service by accident, even
    with real keys in backend/.env: a test that needs one of them installs its own client."""
    import companies_house
    import fetcher
    import websearch

    def refuse(*args, **kwargs):
        raise AssertionError("a test reached a real outside service: replace the client it uses")
    for module in (companies_house, fetcher, websearch):
        monkeypatch.setattr(module, "_client", refuse)
    monkeypatch.setattr(fetcher, "_resolve", refuse)


@pytest.fixture
def stub(monkeypatch):
    """Replace one ai.<name> with a function returning `result` (or raising it). Returns the calls made."""
    import ai

    def install(name, result):
        calls = []

        def fake(*args, **kwargs):
            calls.append(args)
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(ai, name, fake)
        return calls
    return install


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
def own_transaction(conn, monkeypatch):
    """Make db.transaction() run inside this test's rolled-back transaction instead of committing."""
    from contextlib import contextmanager

    import db

    @contextmanager
    def in_test_transaction():
        with conn.transaction():  # a savepoint: a failing unit of work rolls back only itself
            yield conn

    # conn.transaction() is a savepoint only inside an open transaction; on an idle connection
    # it would begin one and COMMIT it. Open the test's transaction now so that can never happen.
    conn.execute("select 1")
    monkeypatch.setattr(db, "transaction", in_test_transaction)


@pytest.fixture
def client(conn, user_a, monkeypatch, own_transaction):
    """The API as user_a, with every route's database work running inside this test's
    rolled-back transaction instead of committing."""
    from fastapi.testclient import TestClient

    import main
    from auth import User, current_user

    monkeypatch.setenv("DAILY_AI_LIMIT", "40")
    monkeypatch.setenv("DAILY_VOICE_LIMIT", "3")
    monkeypatch.setenv("DAILY_RESEARCH_LIMIT", "5")
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
