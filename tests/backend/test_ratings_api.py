import sqlite3

import pytest

import app as app_module

SONG = {"artist": "Artist", "title": "Title"}


def rate(c, value, **song):
    return c.post("/api/ratings", json={**(song or SONG), "value": value})


def rows():
    with sqlite3.connect(app_module.DB_PATH) as db:
        return db.execute("select song_key, voter, artist, title, value from ratings").fetchall()


# --- GET ---------------------------------------------------------------

@pytest.mark.parametrize("params", [{}, {"artist": "A"}, {"title": "T"}, {"artist": " ", "title": "T"}])
def test_get_requires_artist_and_title(client, params):
    assert client.get("/api/ratings", query_string=params).status_code == 400


def test_get_unknown_song_is_empty(client):
    r = client.get("/api/ratings", query_string=SONG)
    assert r.status_code == 200
    assert r.get_json() == {"up": 0, "down": 0, "mine": None}


def test_get_anonymous_mine_is_null_even_with_votes(client, alice):
    rate(alice, 1)
    assert client.get("/api/ratings", query_string=SONG).get_json() == {"up": 1, "down": 0, "mine": None}


# --- POST --------------------------------------------------------------

def test_post_requires_login(client):
    assert rate(client, 1).status_code == 401
    assert rows() == []


@pytest.mark.parametrize("value", [0, 2, -2, "1", None, True, False, 1.5])
def test_post_rejects_invalid_value(alice, value):
    assert rate(alice, value).status_code == 400
    assert rows() == []


def test_post_requires_song(alice):
    assert alice.post("/api/ratings", json={"value": 1}).status_code == 400
    assert alice.post("/api/ratings", json={"artist": "A", "value": 1}).status_code == 400


def test_post_counts_and_mine(alice):
    assert rate(alice, 1).get_json() == {"up": 1, "down": 0, "mine": 1}
    assert alice.get("/api/ratings", query_string=SONG).get_json()["mine"] == 1


def test_rerating_replaces_previous_value(alice):
    rate(alice, 1)
    assert rate(alice, -1).get_json() == {"up": 0, "down": 1, "mine": -1}
    assert len(rows()) == 1


def test_rating_same_value_twice_does_not_double_count(alice):
    rate(alice, 1)
    assert rate(alice, 1).get_json() == {"up": 1, "down": 0, "mine": 1}
    assert len(rows()) == 1


def test_votes_aggregate_across_users_and_mine_is_per_caller(alice, bob):
    rate(alice, 1)
    assert rate(bob, -1).get_json() == {"up": 1, "down": 1, "mine": -1}
    assert alice.get("/api/ratings", query_string=SONG).get_json() == {"up": 1, "down": 1, "mine": 1}


def test_ratings_are_per_song(alice):
    rate(alice, 1)
    other = alice.get("/api/ratings", query_string={"artist": "Artist", "title": "Other"})
    assert other.get_json() == {"up": 0, "down": 0, "mine": None}


def test_song_matching_ignores_case_and_spacing(alice, bob):
    rate(alice, 1, artist="The Band", title="Hello World")
    r = rate(bob, 1, artist="  the   band ", title="HELLO world")
    assert r.get_json()["up"] == 2


def test_song_fields_are_trimmed_and_truncated(alice):
    rate(alice, 1, artist="  " + "x" * 400 + "  ", title="T")
    (row,) = rows()
    assert row[2] == "x" * 300


# --- DELETE ------------------------------------------------------------

def test_delete_requires_login(client):
    assert client.delete("/api/ratings", json=SONG).status_code == 401


def test_delete_requires_song(alice):
    assert alice.delete("/api/ratings", json={}).status_code == 400


def test_delete_removes_only_own_rating(alice, bob):
    rate(alice, 1)
    rate(bob, 1)
    assert alice.delete("/api/ratings", json=SONG).get_json() == {"up": 1, "down": 0, "mine": None}
    assert bob.get("/api/ratings", query_string=SONG).get_json()["mine"] == 1


def test_delete_without_rating_is_a_noop(alice):
    r = alice.delete("/api/ratings", json=SONG)
    assert r.status_code == 200
    assert r.get_json() == {"up": 0, "down": 0, "mine": None}


def test_can_rate_again_after_delete(alice):
    rate(alice, 1)
    alice.delete("/api/ratings", json=SONG)
    assert rate(alice, -1).get_json() == {"up": 0, "down": 1, "mine": -1}
