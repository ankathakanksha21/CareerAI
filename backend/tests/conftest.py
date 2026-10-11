import pytest

import config


@pytest.fixture
def no_env_file(monkeypatch, tmp_path):
    """Hide backend/.env so a test sees only the variables it sets itself."""
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "none")
