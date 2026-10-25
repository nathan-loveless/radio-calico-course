# Radio Calico

A web radio player. It streams a live HLS station, shows the current song, and lets signed-in listeners rate what's playing.

- **Frontend:** static HTML/CSS and vanilla JavaScript in `public/` (no build step), using [hls.js](https://github.com/video-dev/hls.js) for playback.
- **Backend:** a small Flask API for accounts, ratings and a local track library. It uses PostgreSQL in the production deployment and SQLite for local development and tests.
- **Serving:** nginx serves `public/` and proxies `/api/` to Flask.
- **Packaging:** Docker Compose. Production is three containers (nginx, Flask under gunicorn, PostgreSQL); development is one all-in-one container with SQLite. You can also run locally with `dev.sh`.

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

`make` lists the shortcuts used below: `make prod`, `make dev`, `make test`, and more (`make help`).

### Docker production (nginx + Flask + PostgreSQL)

```bash
cp .env.example .env     # then fill in both values; generate each with: openssl rand -hex 32
docker compose up -d --build                      # http://localhost:8080
```

Three services: `web` (nginx serving `public/` and proxying `/api/`; the only published port, 8080), `api` (Flask under gunicorn, reachable only from `web`) and `db` (PostgreSQL 16 with data in the `pgdata` volume). `api` waits for `db` to be healthy and `web` waits for `api`.

Compose refuses to start unless `.env` sets:

- `POSTGRES_PASSWORD`: the database password. Use hex, because it is embedded in a URL.
- `RADIOCALICO_SECRET_KEY`: signs session cookies. Changing it logs everyone out.

The tables are created on first start. Deleting the `pgdata` volume deletes all users and ratings. There is no TLS in the stack; terminate HTTPS in a reverse proxy in front of `web`.

### Docker development (SQLite, live reload)

```bash
docker compose -f docker-compose.dev.yml up --build     # http://localhost:8081
```

One container runs nginx and the Flask reloader against SQLite, with the repo bind-mounted so edits show immediately. No secrets are needed. If your user id is not 1000, run it with `UID=$(id -u) GID=$(id -g)` set. The data lives in the `radiocalico-dev-data` volume.

### Choosing the database

`app.py` uses PostgreSQL when `DATABASE_URL` is set (for example `postgresql://user:pass@host:5432/dbname`) and SQLite otherwise, in `$RADIOCALICO_DATA_DIR` (default `data/`). `RADIOCALICO_SECRET_KEY` overrides the generated `secret_key` file. `RADIOCALICO_DEBUG` (`1` or `0`) controls Flask debug mode when run directly.

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

Flask runs with `debug=True` and reloads on edit. nginx must be restarted after changing `nginx.conf`. The containers use their own configs (`docker/nginx.conf` for dev, `docker/nginx.web.conf` for production), so changes to the root `nginx.conf` only affect `dev.sh`.

## Project structure

```
radiocalico/
├── app.py            # Flask API (auth, ratings, tracks)
├── scanner.py        # Indexes audio tags from public/media/ into the tracks table
├── db.py             # Connection layer: SQLite, or PostgreSQL when DATABASE_URL is set
├── schema.sql        # SQLite schema, applied on every start
├── schema_postgres.sql  # PostgreSQL schema, applied on every start
├── dev.sh            # start|stop|status|scan|sql helper
├── nginx.conf        # Static serving + /api/ proxy for dev.sh (absolute paths)
├── requirements.txt  # Flask, mutagen, psycopg
├── Makefile          # prod / dev / test shortcuts (run `make help`)
├── Dockerfile        # dev / api / web targets
├── docker-compose.yml  # Production: db + api + web
├── docker-compose.dev.yml  # Development: one container, SQLite
├── .env.example      # Secrets the production compose file requires
├── .dockerignore
├── docker/
│   ├── entrypoint.sh # Dev image: runs Flask and nginx; exits if either dies
│   ├── nginx.conf    # Dev image nginx config (all-in-one, proxies to localhost)
│   └── nginx.web.conf  # Production `web` image nginx config (proxies to the `api` service)
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

`make test` runs everything (backend on SQLite and on a throwaway PostgreSQL container, then frontend); `make test-backend`, `make test-postgres` and `make test-frontend` run one part, and `make setup` installs the dependencies. The commands they wrap:

Ratings and auth are covered by unit tests on both sides. There is no linter configured.

```bash
# Backend (pytest; uses a temp data dir via RADIOCALICO_DATA_DIR, never touches data/)
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest

# Same suite against PostgreSQL (needs a reachable, disposable database; the tests delete users and ratings)
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname .venv/bin/pytest

# Frontend (Vitest + jsdom; loads public/index.html and player.js unmodified)
npm install
npm test
```

The backend suite runs on both SQLite and PostgreSQL, and the frontend suite alongside it, in GitHub Actions on every push to `main` and on pull requests (`.github/workflows/test.yml`).

