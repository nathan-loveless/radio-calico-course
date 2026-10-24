# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Radio Calico: a web radio player. A static frontend (`public/`, vanilla JS, no build step) is served by nginx, which proxies `/api/` to a small Flask + SQLite backend. It runs either locally via `dev.sh` or as a single Docker image (nginx + Flask) with `dev` and `prod` targets. Unit tests cover the ratings/auth system (see Testing); no linter is configured.

## File structure

```
radiocalico/
├── app.py                  # Flask API (auth, ratings, tracks); runs init_db + scan on import
├── scanner.py              # Indexes public/media/ audio tags into the tracks table
├── schema.sql              # SQLite schema, applied on every app start
├── dev.sh                  # start|stop|status|scan|sql helper
├── nginx.conf              # Static serving + /api/ proxy for dev.sh (absolute paths)
├── requirements.txt        # Python deps (Flask, mutagen)
├── Dockerfile              # base / dev / prod targets (prod adds gunicorn)
├── docker-compose.yml      # `app` (prod, :8080) and `app-dev` (dev profile, :8081)
├── .dockerignore
├── docker/
│   ├── entrypoint.sh       # Starts Flask + nginx in one container; exits if either dies
│   └── nginx.conf          # Container nginx config (/app paths, logs to stdout)
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

Docker: `docker compose up -d --build` (prod, :8080) or `docker compose --profile dev up --build app-dev` (dev, :8081). Details under Docker.

Local, everything runs through `./dev.sh` (uses `.venv`, nginx must be installed):

- `./dev.sh start` / `stop` / `status`: run Flask (127.0.0.1:5000, logs in `logs/app.log`) and nginx (http://localhost:8080). Pidfiles in `run/`.
- `./dev.sh scan`: re-index `public/media/` audio files into the `tracks` table.
- `./dev.sh sql '<query>'`: run a query against `data/radiocalico.db`.
- Dependencies: `.venv/bin/pip install -r requirements.txt` (Flask, mutagen).

Flask is started with `python app.py` (debug=True, so it reloads on edit); nginx must be restarted for `nginx.conf` changes. `.gitignore` excludes `.venv`, `run`, `logs`, `data` (DB and `secret_key` are local state).

## Architecture

- **nginx.conf**: used only by `dev.sh`. All paths are absolute to `/home/nathansl2003/radiocalico`; update them if the repo moves. Serves `public/` statically and proxies `/api/` to Flask. Adds MIME types for wav/flac/aac so local media plays.
- **app.py**: single-file Flask API (health, tracks, scan, register/login/logout/me, ratings). On import it runs `init_db()` (executes `schema.sql`, plus ad-hoc `alter table` migrations for older DBs) and a media scan, so schema changes go in `schema.sql` using `create table if not exists` and need a migration step for existing tables.
  - Auth: session cookie (`uid`), secret key generated into `data/secret_key`. Login does a dummy hash check to avoid username enumeration.
  - CSRF defense: `before_request` rejects POST/DELETE without a JSON content type (forces CORS preflight). New write endpoints must take JSON.
  - Ratings are keyed by `song_key` = sha256 of normalized (artist, title), not by track id, so they apply to songs from the live stream as well as local tracks. One rating per user per song (upsert); voter is `u:<user id>`.
- **scanner.py**: reads tags with mutagen from `public/media/` and upserts into `tracks` by `filename`; removes rows for deleted files. Used by `app.py` at startup, `POST /api/scan`, and `dev.sh scan`.
- **public/player.js**: plays an HLS live stream (hls.js from cdnjs) from CloudFront; stream and now-playing metadata (`metadatav2.json`) URLs are hard-coded constants at the top and in the metadata section (`stream_URL.txt` is a reference copy). Current song's artist/title from that metadata is what the ratings API is called with. The local `/api/tracks` library is separate from the live stream.

## Docker

- **Image:** `Dockerfile` has a shared `base` (python:3.12-slim + nginx, non-root user `radiocalico`, `/data` volume, port 8080) and two targets. `prod` (the default) copies in only `app.py`, `scanner.py`, `schema.sql`, `docker/` and `public/`, and adds pinned gunicorn. `dev` copies the whole repo but is meant to be run with the repo bind-mounted over `/app`.
- **Process model:** `docker/entrypoint.sh` (bash, needs `wait -n`) starts Flask in the background (`gunicorn --workers 1 --threads 4` when `RADIOCALICO_ENV=prod`, otherwise `python app.py`) plus nginx, and exits if either dies. Keep gunicorn at one worker: `app.py` runs `init_db()` and a scan on import and SQLite is single-writer.
- **nginx:** the container uses `docker/nginx.conf` (root `/app/public`, proxy to 127.0.0.1:5000, temp files in `/tmp/nginx`, logs to stdout/stderr), not the root `nginx.conf`. Routing changes must be made in both files.
- **State:** `RADIOCALICO_DATA_DIR=/data` holds `radiocalico.db` and `secret_key`; prod and dev use separate named volumes in `docker-compose.yml`.
- **Env vars:** `RADIOCALICO_HOST` (Flask bind address, default `127.0.0.1`; `app.py` only reads it when run directly, not under gunicorn), `RADIOCALICO_DEBUG` (`1` default, `0` in prod), `RADIOCALICO_ENV` (`dev`/`prod`, set by the image target).
- **Healthcheck:** prod polls `/api/health` through nginx.
- **Compose dev:** runs as `${UID:-1000}:${GID:-1000}` so bind-mounted files stay owned by the host user.
- **Not in the image:** tests, `dev.sh`, CI config and the style assets are excluded by `.dockerignore` and the prod `COPY` list. No TLS; terminate HTTPS in a proxy in front.

## Testing

- Backend: `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest` (`tests/backend/`). `tests/backend/conftest.py` sets `RADIOCALICO_DATA_DIR` to a temp dir before importing `app`, because `app.py` runs `init_db()` and a scan on import; `app.py` honors that env var for the DB and `secret_key`.
- Frontend: `npm install && npm test` (`tests/frontend/`, Vitest + jsdom). `helpers.js` loads `public/index.html` and `player.js` unmodified into jsdom with a stubbed `fetch` route table; `player.js` has no exports, so tests drive it through the DOM.
- CI: `.github/workflows/test.yml` runs both on push to main and PRs.

## Design

`RadioCalico_Style_Guide.txt` defines the brand (palette: forest green #1F4E23, teal #38A29D, mint #D8F2D5, calico orange #EFA63C, cream #F5EADA, charcoal #231F20; Montserrat headings, Open Sans body). `RadioCalicoLayout.png` is the layout mockup. Follow these in `public/style.css`.
