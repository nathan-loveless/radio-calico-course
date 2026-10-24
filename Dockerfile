# syntax=docker/dockerfile:1
# Targets: `dev` (source bind-mounted, Flask reloader) and `prod` (default; gunicorn, code baked in).
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --system --uid 1000 --home /app radiocalico && mkdir /data && chown radiocalico /data
ENV RADIOCALICO_DATA_DIR=/data RADIOCALICO_HOST=127.0.0.1 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8080
USER radiocalico
ENTRYPOINT ["/app/docker/entrypoint.sh"]

FROM base AS dev
ENV RADIOCALICO_ENV=dev
COPY --chown=radiocalico . .

FROM base AS prod
USER root
RUN pip install --no-cache-dir gunicorn==23.0.0
USER radiocalico
ENV RADIOCALICO_ENV=prod RADIOCALICO_DEBUG=0
COPY --chown=radiocalico app.py scanner.py schema.sql ./
COPY --chown=radiocalico docker ./docker
COPY --chown=radiocalico public ./public
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/api/health')"
