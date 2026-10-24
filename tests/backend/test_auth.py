import pytest

from conftest import PASSWORD


def test_register_logs_in(client):
    r = client.post("/api/register", json={"username": "carol", "password": PASSWORD})
    assert r.status_code == 201
    assert r.get_json() == {"user": {"username": "carol"}}
    assert client.get("/api/me").get_json() == {"user": {"username": "carol"}}


@pytest.mark.parametrize("name", ["ab", "x" * 31, "has space", "bad!", ""])
def test_register_rejects_bad_username(client, name):
    assert client.post("/api/register", json={"username": name, "password": PASSWORD}).status_code == 400


@pytest.mark.parametrize("password", ["short", "x" * 201, ""])
def test_register_rejects_bad_password(client, password):
    assert client.post("/api/register", json={"username": "carol", "password": password}).status_code == 400


def test_register_duplicate_username_is_case_insensitive(client, alice):
    r = client.post("/api/register", json={"username": "ALICE", "password": PASSWORD})
    assert r.status_code == 409


def test_login_success_and_me(client, alice):
    r = client.post("/api/login", json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 200
    assert client.get("/api/me").get_json() == {"user": {"username": "alice"}}


@pytest.mark.parametrize("creds", [
    {"username": "alice", "password": "wrong-password"},
    {"username": "nobody", "password": PASSWORD},
    {},
])
def test_login_failure_is_generic(client, alice, creds):
    r = client.post("/api/login", json=creds)
    assert r.status_code == 401
    assert r.get_json() == {"error": "Incorrect username or password"}


def test_logout_clears_session(alice):
    assert alice.post("/api/logout", json={}).get_json() == {"user": None}
    assert alice.get("/api/me").get_json() == {"user": None}


def test_me_anonymous(client):
    assert client.get("/api/me").get_json() == {"user": None}
