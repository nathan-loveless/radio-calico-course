"""Build the tracks table from the audio files in public/media/, using their tags."""
import sqlite3
from pathlib import Path

import mutagen

MEDIA_DIR = Path(__file__).parent / "public" / "media"
EXTENSIONS = {".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wav"}


def read_tags(path):
    """Return (title, artist, album, duration); missing tags fall back to defaults."""
    try:
        audio = mutagen.File(path, easy=True)
    except mutagen.MutagenError:
        audio = None
    tags = audio.tags if audio is not None and audio.tags else {}

    # Easy tags use names like "title"; WAV (and some others) expose raw ID3 frames instead.
    raw_frames = {"title": "TIT2", "artist": "TPE1", "album": "TALB"}

    def first(key):
        values = tags.get(key) or tags.get(raw_frames[key])
        if not values:
            return None
        value = values[0] if isinstance(values, list) else values.text[0]
        return str(value).strip() or None

    title = first("title") or path.stem.replace("_", " ").replace("-", " ").title()
    artist = first("artist") or "Unknown Artist"
    duration = audio.info.length if audio is not None else None
    return title, artist, first("album"), duration


def scan(db):
    """Upsert every audio file and drop rows whose file is gone. Returns (added_or_updated, removed)."""
    files = sorted(p for p in MEDIA_DIR.iterdir() if p.suffix.lower() in EXTENSIONS)
    for p in files:
        title, artist, album, duration = read_tags(p)
        db.execute(
            """insert into tracks (title, artist, album, duration, filename) values (?, ?, ?, ?, ?)
               on conflict(filename) do update set
                 title = excluded.title, artist = excluded.artist,
                 album = excluded.album, duration = excluded.duration""",
            (title, artist, album, duration, p.name),
        )
    names = [p.name for p in files]
    if names:
        marks = ",".join("?" * len(names))
        removed = db.execute(f"delete from tracks where filename not in ({marks})", names).rowcount
    else:  # `not in ()` is a syntax error on PostgreSQL
        removed = db.execute("delete from tracks").rowcount
    return len(files), removed


if __name__ == "__main__":
    with sqlite3.connect(Path(__file__).parent / "data" / "radiocalico.db") as conn:
        print("scanned %d files, removed %d rows" % scan(conn))
