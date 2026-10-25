# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Radio Calico: a web radio player. A static frontend (`public/`, vanilla JS, no build step) is served by nginx, which proxies `/api/` to a small Flask backend. Production (Docker Compose) is three containers: nginx, Flask under gunicorn, and PostgreSQL. Development uses SQLite, either locally via `dev.sh` or in a single all-in-one dev container. Unit tests cover the ratings/auth system (see Testing); no linter is configured.

## File structure

```
radiocalico/
├── app.py                  # Flask API (auth, ratings, tracks); runs init_db + scan on import
├── scanner.py              # Indexes public/media/ audio tags into the tracks table
├── db.py                   # DB layer: SQLite, or PostgreSQL when DATABASE_URL is set
├── schema.sql              # SQLite schema, applied on every app start
├── schema_postgres.sql     # PostgreSQL schema, applied on every app start
├── Makefile                # prod/dev/test shortcuts
├── dev.sh                  # start|stop|status|scan|sql helper
├── nginx.conf              # Static serving + /api/ proxy for dev.sh (absolute paths)
├── requirements.txt        # Python deps (Flask, mutagen, psycopg)
├── Dockerfile              # dev / api / web targets
├── docker-compose.yml      # Production: db (postgres) + api (gunicorn) + web (nginx), :8080
├── docker-compose.dev.yml  # Development: one SQLite container, :8081
├── .env.example            # Secrets the prod compose file requires (copy to .env)
├── .dockerignore
├── docker/
│   ├── entrypoint.sh       # Dev image only: Flask + nginx in one container
│   ├── nginx.conf          # Dev image nginx (proxies to 127.0.0.1:5000)
│   └── nginx.web.conf      # Prod `web` image nginx (proxies to api:5000)
├── stream_URL.txt          # Reference copy of the HLS stream URL
├── public/                 # Static frontend served by nginx
│   ├── index.html          # Markup; loads hls.js from cdnjs, then player.js
│   ├── style.css           # All styling (numbered sections, CSS variable tokens)
│   ├── player.js           # HLS playback, now-playing metadata, ratings, auth UI
│   ├── logo.png            # Wordmark logo / cover placeholder
│   └── media/              # Local audio files (sample-a/b/c.wav) scanned into tracks
├── RadioCalico_Style_Guide.txt   # Brand palette, typography, components
├── RadioCalicoLayout.png         # Layout mockup
├── RadioCalicoLogoTM.png         # Original logo asset
├── RadioCalicoStyle.zip          # Style assets archive
├── data/                   # Git-ignored: radiocalico.db, secret_key
├── logs/                   # Git-ignored: access/error/app logs
├── run/                    # Git-ignored: pidfiles and nginx temp dirs
└── .venv/                  # Git-ignored: Python virtualenv
```

## Commands

`Makefile` wraps the common tasks (`make help` lists them): `prod`/`prod-down`/`prod-logs`, `dev`/`dev-down`, `local`/`local-stop`, `test`, `test-backend`, `test-postgres` (starts and removes its own postgres container), `test-frontend`, `setup`. `make prod` refuses to run without `.env`.

Docker: `docker compose up -d --build` (prod, :8080, needs `.env`) or `docker compose -f docker-compose.dev.yml up --build` (dev, :8081). Details under Docker.

Local, everything runs through `./dev.sh` (uses `.venv`, nginx must be installed):

- `./dev.sh start` / `stop` / `status`: run Flask (127.0.0.1:5000, logs in `logs/app.log`) and nginx (http://localhost:8080). Pidfiles in `run/`.
- `./dev.sh scan`: re-index `public/media/` audio files into the `tracks` table.
- `./dev.sh sql '<query>'`: run a query against `data/radiocalico.db`.
- Dependencies: `.venv/bin/pip install -r requirements.txt` (Flask, mutagen, psycopg).

Flask is started with `python app.py` (debug=True, so it reloads on edit); nginx must be restarted for `nginx.conf` changes. `.gitignore` excludes `.venv`, `run`, `logs`, `data` (DB and `secret_key` are local state).

## Architecture

- **nginx.conf**: used only by `dev.sh`. All paths are absolute to `/home/nathansl2003/radiocalico`; update them if the repo moves. Serves `public/` statically and proxies `/api/` to Flask. Adds MIME types for wav/flac/aac so local media plays.
- **app.py**: single-file Flask API (health, tracks, scan, register/login/logout/me, ratings). On import it runs `db.init_db()` and a media scan.
- **db.py**: the only place that knows the backend. `DATABASE_URL` set means PostgreSQL (psycopg 3, dict rows), otherwise SQLite in `RADIOCALICO_DATA_DIR`. `connect()` returns a wrapper whose `execute` rewrites `?` to `%s` for PostgreSQL, and which works as a context manager (commit/rollback, then close). Write SQL once with `?` placeholders and keep it portable: use `count(*) filter (where ...)` not boolean `sum`, `returning id` not `lastrowid`, `current_timestamp` not `datetime('now')`, `lower(col) = lower(?)` for usernames, and `db.IntegrityError` not `sqlite3.IntegrityError`. After a failed statement call `rollback()` (PostgreSQL aborts the transaction).
  - **Schemas:** two files that must stay in sync, `schema.sql` (SQLite) and `schema_postgres.sql` (PostgreSQL, with a case-insensitive unique index on `lower(username)`). Both use `create table if not exists` and run on every start, so changing an existing table needs a migration step (SQLite's lives in `db.init_db()`; PostgreSQL has none yet).
  - Auth: session cookie (`uid`); the secret key is `RADIOCALICO_SECRET_KEY` if set, else generated into `data/secret_key`. Login does a dummy hash check to avoid username enumeration.
  - CSRF defense: `before_request` rejects POST/DELETE without a JSON content type (forces CORS preflight). New write endpoints must take JSON.
  - Ratings are keyed by `song_key` = sha256 of normalized (artist, title), not by track id, so they apply to songs from the live stream as well as local tracks. One rating per user per song (upsert); voter is `u:<user id>`.
- **scanner.py**: reads tags with mutagen from `public/media/` and upserts into `tracks` by `filename`; removes rows for deleted files. Used by `app.py` at startup, `POST /api/scan`, and `dev.sh scan`.
- **public/player.js**: plays an HLS live stream (hls.js from cdnjs) from CloudFront; stream and now-playing metadata (`metadatav2.json`) URLs are hard-coded constants at the top and in the metadata section (`stream_URL.txt` is a reference copy). Current song's artist/title from that metadata is what the ratings API is called with. The local `/api/tracks` library is separate from the live stream.

## Docker

- **Targets** (`Dockerfile`): `dev` (python + nginx, SQLite, repo bind-mounted, Flask reloader), `api` (gunicorn only; copies `app.py`, `db.py`, `scanner.py`, both schemas and `public/media`) and `web` (`nginxinc/nginx-unprivileged` with `public/` baked in). All run as non-root.
- **Production** (`docker-compose.yml`): `db` (postgres:16-alpine, `pgdata` volume, healthcheck) then `api` then `web`, each waiting on the previous one's health. Only `web` publishes a port (8080). `api` runs `gunicorn --preload --workers 2 --threads 4`; `--preload` makes `init_db()` and the scan run once in the master. `init_db()` also takes a Postgres advisory lock so concurrent starts are safe.
- **Secrets:** compose requires `POSTGRES_PASSWORD` and `RADIOCALICO_SECRET_KEY` from `.env` (git-ignored; template in `.env.example`) and fails with a clear message if they're missing. The DB password is used inside `DATABASE_URL`, so it must be URL-safe (hex).
- **Dev** (`docker-compose.dev.yml`, separate so it needs no secrets): `docker/entrypoint.sh` runs `python app.py` (debug) and nginx with `docker/nginx.conf`; data in the `radiocalico-dev-data` volume; runs as `${UID:-1000}:${GID:-1000}` so bind-mounted files stay owned by the host user. `RADIOCALICO_HOST` only applies when `app.py` is run directly.
- **nginx configs:** three of them (`nginx.conf` for `dev.sh`, `docker/nginx.conf` for the dev container, `docker/nginx.web.conf` for prod). Routing changes (MIME types, `/api/` proxy) must be made in each. The prod one proxies via `resolver 127.0.0.11` and a variable so nginx re-resolves `api` after it restarts.
- **Health:** `/api/health` returns `{ok, db, backend, version}`; `backend` is `sqlite` or `postgres`.
- **Not in the images:** tests, `dev.sh`, CI config and style assets (see `.dockerignore`). No TLS; terminate HTTPS in a proxy in front of `web`.

## Testing

- Backend: `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest` (`tests/backend/`). `tests/backend/conftest.py` sets `RADIOCALICO_DATA_DIR` to a temp dir before importing `app`, because `app.py` runs `init_db()` and a scan on import; `app.py` honors that env var for the DB and `secret_key`. With `DATABASE_URL` set to a disposable PostgreSQL the same suite runs against Postgres (CI runs both); the tests delete all users and ratings.
- Frontend: `npm install && npm test` (`tests/frontend/`, Vitest + jsdom). `helpers.js` loads `public/index.html` and `player.js` unmodified into jsdom with a stubbed `fetch` route table; `player.js` has no exports, so tests drive it through the DOM.
- CI: `.github/workflows/test.yml` runs backend (SQLite), backend (PostgreSQL service container) and frontend on push to main and PRs.

## Design

`RadioCalico_Style_Guide.txt` defines the brand (palette: forest green #1F4E23, teal #38A29D, mint #D8F2D5, calico orange #EFA63C, cream #F5EADA, charcoal #231F20; Montserrat headings, Open Sans body). `RadioCalicoLayout.png` is the layout mockup. Follow these in `public/style.css`.
