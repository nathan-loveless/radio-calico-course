#!/usr/bin/env bash
cd "$(dirname "$0")"
mkdir -p run logs
running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
case "$1" in
  start)
    running run/app.pid || { nohup .venv/bin/python app.py >logs/app.log 2>&1 & echo $! > run/app.pid; }
    running run/nginx.pid || nginx -c "$PWD/nginx.conf" -p "$PWD"
    echo "http://localhost:8080" ;;
  stop)
    running run/app.pid && pkill -P "$(cat run/app.pid)"; running run/app.pid && kill "$(cat run/app.pid)"
    rm -f run/app.pid
    running run/nginx.pid && nginx -c "$PWD/nginx.conf" -p "$PWD" -s stop ;;
  status)
    running run/app.pid && echo "app running" || echo "app stopped"
    running run/nginx.pid && echo "nginx running" || echo "nginx stopped" ;;
  scan) .venv/bin/python -I scanner.py ;;
  sql) shift; exec .venv/bin/python -I -c "import sqlite3,sys;print(sqlite3.connect('data/radiocalico.db').execute(sys.argv[1]).fetchall())" "$@" ;;
  *) echo "usage: $0 start|stop|status|scan|sql '<query>'"; exit 1 ;;
esac
