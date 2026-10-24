from app import song_key


def test_normalizes_case_and_whitespace():
    assert song_key("The  Band", " Hello World ") == song_key("the band", "hello   world")


def test_different_songs_differ():
    assert song_key("A", "B") != song_key("A", "C")
    assert song_key("A", "B") != song_key("C", "B")


def test_artist_and_title_are_not_interchangeable():
    assert song_key("A", "B") != song_key("B", "A")


def test_separator_prevents_concatenation_collisions():
    assert song_key("ab", "c") != song_key("a", "bc")
