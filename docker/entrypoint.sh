#!/bin/bash
# Dev image only: runs Flask (reloader, SQLite) and nginx in one container.
# Exits (so Docker restarts it) if either dies.
set -e
mkdir -p /tmp/nginx "$RADIOCALICO_DATA_DIR"

RADIOCALICO_DEBUG=1 python app.py &
nginx -c /app/docker/nginx.conf &

wait -n
exit 1
