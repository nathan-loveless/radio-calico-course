import hashlib
import re
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import scanner

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "radiocalico.db"

app = Flask(__name__)


def load_secret_key():
    path = BASE / "data" / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip()


app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)
USERNAME_RE = re.compile(r"[A-Za-z0-9_.-]{3,30}")
DUMMY_HASH = generate_password_hash("not-a-real-password")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("pragma foreign_keys = on")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript((BASE / "schema.sql").read_text())
        cols = {r[1] for r in db.execute("pragma table_info(tracks)")}
        for col, typ in (("album", "text"), ("duration", "real")):
            if col not in cols:
                db.execute(f"alter table tracks add column {col} {typ}")


@app.get("/api/health")
def health():
    row = get_db().execute("select datetime('now') as time, sqlite_version() as v").fetchone()
    return jsonify(ok=True, db=row["time"], sqlite=row["v"])


@app.get("/api/tracks")
def tracks():
    rows = get_db().execute(
        "select id, title, artist, album, duration, '/media/' || filename as url from tracks order by id"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/scan")
def rescan():
    with sqlite3.connect(DB_PATH) as db:
        found, removed = scanner.scan(db)
    return jsonify(found=found, removed=removed)


def song_key(artist, title):
    norm = "\0".join(" ".join(x.lower().split()) for x in (artist, title))
    return hashlib.sha256(norm.encode()).hexdigest()


def current_user():
    uid = session.get("uid")
    if uid is None:
        return None
    return get_db().execute("select id, username from users where id = ?", (uid,)).fetchone()


def voter_id(user):
    return f"u:{user['id']}" if user else None


def rating_summary(key, user):
    db = get_db()
    row = db.execute(
        "select coalesce(sum(value = 1), 0) as up, coalesce(sum(value = -1), 0) as down "
        "from ratings where song_key = ?", (key,)
    ).fetchone()
    mine = None
    if user:
        r = db.execute(
            "select value from ratings where song_key = ? and voter = ?", (key, voter_id(user))
        ).fetchone()
        mine = r["value"] if r else None
    return {"up": row["up"], "down": row["down"], "mine": mine}


def song_from(data):
    artist = str(data.get("artist") or "").strip()[:300]
    title = str(data.get("title") or "").strip()[:300]
    return (artist, title) if artist and title else None


def user_json(user):
    return {"username": user["username"]} if user else None


@app.before_request
def require_json_for_writes():
    # Non-simple content type forces a CORS preflight, which blocks cross-site form posts.
    if request.method in ("POST", "DELETE") and not request.is_json:
        return jsonify(error="JSON body required"), 415


def credentials():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    return username, password


@app.post("/api/register")
def register():
    username, password = credentials()
    if not USERNAME_RE.fullmatch(username):
        return jsonify(error="Username must be 3-30 letters, numbers, _ . or -"), 400
    if not (8 <= len(password) <= 200):
        return jsonify(error="Password must be at least 8 characters"), 400
    db = get_db()
    try:
        cur = db.execute(
            "insert into users (username, password_hash) values (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That username is taken"), 409
    session.clear()
    session["uid"] = cur.lastrowid
    session.permanent = True
    return jsonify(user=user_json(current_user())), 201


@app.post("/api/login")
def login():
    username, password = credentials()
    row = get_db().execute(
        "select id, password_hash from users where username = ?", (username,)
    ).fetchone()
    # Always run a hash check so response time doesn't reveal whether the username exists.
    ok = check_password_hash(row["password_hash"] if row else DUMMY_HASH, password)
    if not (row and ok):
        return jsonify(error="Incorrect username or password"), 401
    session.clear()
    session["uid"] = row["id"]
    session.permanent = True
    return jsonify(user=user_json(current_user()))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(user=None)


@app.get("/api/me")
def me():
    return jsonify(user=user_json(current_user()))


@app.get("/api/ratings")
def get_ratings():
    song = song_from(request.args)
    if not song:
        return jsonify(error="artist and title required"), 400
    return jsonify(rating_summary(song_key(*song), current_user()))


@app.post("/api/ratings")
def post_rating():
    user = current_user()
    if not user:
        return jsonify(error="Log in to rate songs"), 401
    data = request.get_json(silent=True) or {}
    song = song_from(data)
    value = data.get("value")
    if not song or value not in (1, -1) or isinstance(value, bool):
        return jsonify(error="artist, title and value (1 or -1) required"), 400
    key = song_key(*song)
    db = get_db()
    # One row per (song, user); rating again replaces the earlier value.
    db.execute(
        "insert into ratings (song_key, voter, artist, title, value) values (?, ?, ?, ?, ?) "
        "on conflict (song_key, voter) do update set value = excluded.value, created_at = datetime('now')",
        (key, voter_id(user), song[0], song[1], value),
    )
    db.commit()
    resp = jsonify(rating_summary(key, user))
    return resp


@app.delete("/api/ratings")
def delete_rating():
    user = current_user()
    if not user:
        return jsonify(error="Log in to rate songs"), 401
    song = song_from(request.get_json(silent=True) or {})
    if not song:
        return jsonify(error="artist and title required"), 400
    key = song_key(*song)
    db = get_db()
    db.execute("delete from ratings where song_key = ? and voter = ?", (key, voter_id(user)))
    db.commit()
    return jsonify(rating_summary(key, user))


init_db()
with sqlite3.connect(DB_PATH) as _db:
    scanner.scan(_db)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
