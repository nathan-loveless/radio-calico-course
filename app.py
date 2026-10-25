import hashlib
import os
import re
import secrets
from datetime import timedelta

from flask import Flask, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import db
import scanner

DATA_DIR = db.DATA_DIR

app = Flask(__name__)


def load_secret_key():
    if os.environ.get("RADIOCALICO_SECRET_KEY"):
        return os.environ["RADIOCALICO_SECRET_KEY"]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "secret_key"
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
        g.db = db.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.get("/api/health")
def health():
    if db.BACKEND == "postgres":
        query = "select now()::text as time, version() as v"
    else:
        query = "select datetime('now') as time, sqlite_version() as v"
    row = get_db().execute(query).fetchone()
    return jsonify(ok=True, db=row["time"], backend=db.BACKEND, version=row["v"])


@app.get("/api/tracks")
def tracks():
    rows = get_db().execute(
        "select id, title, artist, album, duration, '/media/' || filename as url from tracks order by id"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/scan")
def rescan():
    with db.connect() as conn:
        found, removed = scanner.scan(conn)
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
    conn = get_db()
    row = conn.execute(
        "select count(*) filter (where value = 1) as up, count(*) filter (where value = -1) as down "
        "from ratings where song_key = ?", (key,)
    ).fetchone()
    mine = None
    if user:
        r = conn.execute(
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
    conn = get_db()
    try:
        cur = conn.execute(
            "insert into users (username, password_hash) values (?, ?) returning id",
            (username, generate_password_hash(password)),
        )
        uid = cur.fetchone()["id"]
        conn.commit()
    except db.IntegrityError:
        conn.rollback()
        return jsonify(error="That username is taken"), 409
    session.clear()
    session["uid"] = uid
    session.permanent = True
    return jsonify(user=user_json(current_user())), 201


@app.post("/api/login")
def login():
    username, password = credentials()
    row = get_db().execute(
        "select id, password_hash from users where lower(username) = lower(?)", (username,)
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
    conn = get_db()
    # One row per (song, user); rating again replaces the earlier value.
    conn.execute(
        "insert into ratings (song_key, voter, artist, title, value) values (?, ?, ?, ?, ?) "
        "on conflict (song_key, voter) do update set value = excluded.value, created_at = current_timestamp",
        (key, voter_id(user), song[0], song[1], value),
    )
    conn.commit()
    return jsonify(rating_summary(key, user))


@app.delete("/api/ratings")
def delete_rating():
    user = current_user()
    if not user:
        return jsonify(error="Log in to rate songs"), 401
    song = song_from(request.get_json(silent=True) or {})
    if not song:
        return jsonify(error="artist and title required"), 400
    key = song_key(*song)
    conn = get_db()
    conn.execute("delete from ratings where song_key = ? and voter = ?", (key, voter_id(user)))
    conn.commit()
    return jsonify(rating_summary(key, user))


db.init_db()
with db.connect() as _conn:
    scanner.scan(_conn)

if __name__ == "__main__":
    app.run(host=os.environ.get("RADIOCALICO_HOST", "127.0.0.1"), port=5000, debug=os.environ.get("RADIOCALICO_DEBUG", "1") == "1")
