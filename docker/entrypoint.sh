#!/bin/bash
# Runs Flask and nginx in one container; exits (so Docker restarts it) if either dies.
set -e
mkdir -p /tmp/nginx "$RADIOCALICO_DATA_DIR"

if [ "$RADIOCALICO_ENV" = "prod" ]; then
  # One worker: app.py runs init_db + a media scan on import and SQLite is single-writer.
  gunicorn --bind 127.0.0.1:5000 --workers 1 --threads 4 --access-logfile - app:app &
else
  RADIOCALICO_DEBUG=1 python app.py &
fi
nginx -c /app/docker/nginx.conf &

wait -n
exit 1
