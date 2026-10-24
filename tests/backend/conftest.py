import os
import sys
import tempfile
from pathlib import Path

# app.py runs init_db() and a media scan on import, so point it at a throwaway data dir first.
_DATA_DIR = tempfile.TemporaryDirectory()
os.environ["RADIOCALICO_DATA_DIR"] = _DATA_DIR.name
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

import app as app_module

JSON = {"content_type": "application/json"}
PASSWORD = "correct-horse"


@pytest.fixture(autouse=True)
def clean_db():
    import sqlite3

    with sqlite3.connect(app_module.DB_PATH) as db:
        db.execute("delete from ratings")
        db.execute("delete from users")


@pytest.fixture
def client():
    return app_module.app.test_client()


@pytest.fixture
def make_user(client):
    """Return a client logged in as a newly registered user (separate cookie jar per call)."""

    def make(name="alice"):
        c = app_module.app.test_client()
        r = c.post("/api/register", json={"username": name, "password": PASSWORD})
        assert r.status_code == 201
        return c

    return make


@pytest.fixture
def alice(make_user):
    return make_user("alice")


@pytest.fixture
def bob(make_user):
    return make_user("bob")
