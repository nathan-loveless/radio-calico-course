import pytest

SONG = {"artist": "A", "title": "T"}


@pytest.mark.parametrize("method,path", [
    ("post", "/api/ratings"),
    ("delete", "/api/ratings"),
    ("post", "/api/login"),
    ("post", "/api/register"),
    ("post", "/api/logout"),
])
def test_writes_without_json_content_type_are_rejected(alice, method, path):
    r = getattr(alice, method)(path, data="artist=A&title=T&value=1",
                               content_type="application/x-www-form-urlencoded")
    assert r.status_code == 415


def test_form_post_does_not_create_rating(alice):
    alice.post("/api/ratings", data="artist=A&title=T&value=1",
               content_type="application/x-www-form-urlencoded")
    assert alice.get("/api/ratings", query_string=SONG).get_json()["up"] == 0


def test_get_needs_no_content_type(client):
    assert client.get("/api/ratings", query_string=SONG).status_code == 200
