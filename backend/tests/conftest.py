import os
import pytest

os.environ["MORNINGBRIEF_FAKE_KEYCHAIN"] = "1"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MORNINGBRIEF_HOME", str(tmp_path))
    from morningbrief.db.database import Database

    d = Database(tmp_path / "test.db")
    yield d
    d.close()


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("MORNINGBRIEF_HOME", str(tmp_path))
    from morningbrief.config import Config

    c = Config()
    c.llm_enabled = False
    return c
