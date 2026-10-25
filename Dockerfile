# syntax=docker/dockerfile:1
# Targets:
#   dev  all-in-one (nginx + Flask reloader + SQLite), repo bind-mounted. See docker-compose.yml `app-dev`.
#   api  production Flask app under gunicorn, talks to PostgreSQL via DATABASE_URL.
#   web  production nginx serving public/ and proxying /api/ to the api service.
#   db   production PostgreSQL: the official image plus OS package updates.
FROM python:3.12-slim AS pybase
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 1000 --home /app radiocalico
ENV PYTHONUNBUFFERED=1

FROM pybase AS dev
RUN apt-get update && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /data && chown radiocalico /data
ENV RADIOCALICO_ENV=dev RADIOCALICO_DATA_DIR=/data RADIOCALICO_HOST=127.0.0.1
VOLUME /data
EXPOSE 8080
USER radiocalico
COPY --chown=radiocalico . .
ENTRYPOINT ["/app/docker/entrypoint.sh"]

FROM pybase AS api
RUN pip install --no-cache-dir gunicorn==23.0.0
USER radiocalico
ENV RADIOCALICO_DEBUG=0
COPY app.py db.py scanner.py schema.sql schema_postgres.sql ./
COPY public/media ./public/media
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/api/health')"
# --preload runs init_db + the media scan once in the master, not in every worker.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--preload", "--workers", "2", "--threads", "4", "--access-logfile", "-", "app:app"]

FROM nginxinc/nginx-unprivileged:1.30-alpine AS web
USER root
RUN apk upgrade --no-cache
USER nginx
COPY docker/nginx.web.conf /etc/nginx/nginx.conf
COPY public /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1

FROM postgres:16-alpine3.22 AS db
RUN apk upgrade --no-cache
