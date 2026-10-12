from __future__ import annotations

import os

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App wired to temp SQLite files and the scripted FakeLlm."""
    monkeypatch.setenv("RETAIL_DB_PATH", str(tmp_path / "retail.db"))
    monkeypatch.setenv("SESSION_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    monkeypatch.setenv("LOG_JSON", "false")
    monkeypatch.setenv("APP_API_KEY", os.environ.get("TEST_APP_API_KEY", ""))

    from oldapp.core.config import get_settings

    get_settings.cache_clear()

    from oldapp.agents.model import set_model_override
    from tests.fake_llm import FakeLlm

    set_model_override(lambda role: FakeLlm())

    from fastapi.testclient import TestClient

    from oldapp.main import create_app

    with TestClient(create_app()) as c:
        yield c

    set_model_override(None)
    get_settings.cache_clear()
