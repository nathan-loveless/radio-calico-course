# Radio Calico

A web radio player. It streams a live HLS station, shows the current song, and lets signed-in listeners rate what's playing.

- **Frontend:** static HTML/CSS and vanilla JavaScript in `public/` (no build step), using [hls.js](https://github.com/video-dev/hls.js) for playback.
- **Backend:** a small Flask + SQLite API for accounts, ratings and a local track library.
- **Serving:** nginx serves `public/` and proxies `/api/` to Flask.
- **Packaging:** a single Docker image (nginx + Flask) with `dev` and `prod` targets, or run it locally with `dev.sh`.

## Features

- Live HLS stream playback with now-playing artist and title
- User registration and login (session cookie)
- Song ratings, one per user per song, that apply to live-stream songs as well as local tracks
- Local media library indexed from audio tags in `public/media/`
- Branded styling following `RadioCalico_Style_Guide.txt`

## Requirements

- **Docker:** Docker with the Compose plugin, nothing else.
- **Local (no Docker):** Python 3 with `venv`, nginx and Bash.

## Getting started

### Docker (recommended)

One image, two build targets. nginx and Flask run together in one container on port 8080; the SQLite database and `secret_key` live in the `/data` volume.

```bash
# prod: code baked in, gunicorn, healthcheck, restarts automatically
docker compose up -d --build                      # http://localhost:8080

# dev: repo bind-mounted, Flask reloader, edits to public/ show immediately
docker compose --profile dev up --build app-dev   # http://localhost:8081
```

| | `prod` (default target) | `dev` |
| --- | --- | --- |
| Server | gunicorn (1 worker, 4 threads) | `python app.py`, debug and reloader on |
| Code | copied into the image (app, `public/`, `docker/` only) | bind-mounted from the repo |
| Data volume | `radiocalico-data` | `radiocalico-dev-data` (separate) |
| Port | 8080 | 8081 |
| Extras | healthcheck, `restart: unless-stopped` | runs as your `UID`/`GID` |

Without compose: `docker build --target prod -t radiocalico:prod .` then `docker run -p 8080:8080 -v radiocalico-data:/data radiocalico:prod`.

Configuration is by environment variable: `RADIOCALICO_DATA_DIR` (default `/data` in the image), `RADIOCALICO_HOST` (Flask bind address) and `RADIOCALICO_DEBUG` (`1` or `0`). There is no TLS in the container; terminate HTTPS in a reverse proxy in front of it. Deleting the data volume deletes all users and ratings.

If your user id is not 1000, start dev with `UID=$(id -u) GID=$(id -g) docker compose --profile dev up`.

### Local (without Docker)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

./dev.sh start     # Flask on 127.0.0.1:5000, nginx on http://localhost:8080
./dev.sh status
./dev.sh stop
```

Then open <http://localhost:8080>.

`nginx.conf` uses absolute paths under `/home/nathansl2003/radiocalico`. If you clone the repo elsewhere, update those paths before starting.

### Helper commands

| Command | Description |
| --- | --- |
| `./dev.sh start` / `stop` / `status` | Run, stop or inspect Flask and nginx (pidfiles in `run/`, logs in `logs/`) |
| `./dev.sh scan` | Re-index `public/media/` audio files into the `tracks` table |
| `./dev.sh sql '<query>'` | Run a SQL query against `data/radiocalico.db` |

Flask runs with `debug=True` and reloads on edit. nginx must be restarted after changing `nginx.conf`. The container uses its own `docker/nginx.conf`, so changes to the root `nginx.conf` only affect `dev.sh`.

## Project structure

```
radiocalico/
├── app.py            # Flask API (auth, ratings, tracks)
├── scanner.py        # Indexes audio tags from public/media/ into SQLite
├── schema.sql        # SQLite schema, applied on every start
├── dev.sh            # start|stop|status|scan|sql helper
├── nginx.conf        # Static serving + /api/ proxy for dev.sh (absolute paths)
├── requirements.txt  # Flask, mutagen
├── Dockerfile        # base / dev / prod targets
├── docker-compose.yml  # prod service, plus app-dev under the dev profile
├── .dockerignore
├── docker/
│   ├── entrypoint.sh # Runs Flask (gunicorn in prod) and nginx; exits if either dies
│   └── nginx.conf    # Container nginx config (container paths, logs to stdout)
├── stream_URL.txt    # Reference copy of the HLS stream URL
├── public/           # Static frontend
│   ├── index.html
│   ├── style.css
│   ├── player.js
│   └── media/        # Local audio files
├── data/             # Git-ignored: database and secret_key
├── logs/             # Git-ignored
└── run/              # Git-ignored
```

## How it works

- **Playback:** `public/player.js` plays the HLS stream from CloudFront. The stream URL and the now-playing metadata URL (`metadatav2.json`) are constants in that file.
- **Ratings:** keyed by a hash of the normalized artist and title, not by track id, so they work for any song on the live stream.
- **Auth:** a session cookie, with the secret key generated into `data/secret_key`. Login performs a dummy hash check to avoid username enumeration.
- **CSRF defense:** POST and DELETE requests must use a JSON content type, which forces a CORS preflight. Any new write endpoint must accept JSON.
- **Container state:** `app.py` reads `RADIOCALICO_DATA_DIR` for the database and `secret_key`, so mounting a volume there is all persistence needs.
- **Schema changes:** put them in `schema.sql` using `create table if not exists`, and add a migration step for existing databases.

## Design

Palette: forest green `#1F4E23`, teal `#38A29D`, mint `#D8F2D5`, calico orange `#EFA63C`, cream `#F5EADA`, charcoal `#231F20`. Headings use Montserrat and body text uses Open Sans. See `RadioCalico_Style_Guide.txt` and `RadioCalicoLayout.png`.

## Testing

Ratings and auth are covered by unit tests on both sides. There is no linter configured.

```bash
# Backend (pytest; uses a temp data dir via RADIOCALICO_DATA_DIR, never touches data/)
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

# Frontend (Vitest + jsdom; loads public/index.html and player.js unmodified)
npm install
npm test
```

Both run in GitHub Actions on every push to `main` and on pull requests (`.github/workflows/test.yml`).

