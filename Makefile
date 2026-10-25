# Radio Calico tasks. Run `make` (or `make help`) to list them.
COMPOSE      ?= docker compose
DEV_COMPOSE  := $(COMPOSE) -f docker-compose.dev.yml -p radiocalico-dev
PYTEST       := .venv/bin/pytest
PIP_AUDIT    ?= .venv/bin/pip-audit
TRIVY_IMAGE  := aquasec/trivy:0.76.1
# The three images compose runs in production.
SCAN_IMAGES  := radiocalico-api radiocalico-web radiocalico-db
# The official postgres image bundles a gosu binary built with an old Go toolchain. It only drops
# privileges at container start and we cannot rebuild it, so it is excluded from the scan.
TRIVY_SKIP   := /usr/local/bin/gosu
PG_NAME      := radiocalico-test-pg
PG_PORT      ?= 55432

.DEFAULT_GOAL := help
.PHONY: help prod prod-down prod-logs prod-ps dev dev-down dev-logs local local-stop \
        test test-backend test-postgres test-frontend security security-npm security-python security-images setup

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- production: nginx + Flask + PostgreSQL (http://localhost:8080) ----------------------------

.env:
	@echo "Missing .env. Create it with:" >&2
	@echo "  cp .env.example .env   # then set both values; generate each with: openssl rand -hex 32" >&2
	@exit 1

prod: .env ## Build and start production (db + api + web) on :8080
	$(COMPOSE) up -d --build
	@echo "http://localhost:8080"

prod-down: ## Stop production (data kept; `docker compose down -v` also deletes the database)
	$(COMPOSE) down

prod-logs: ## Follow production logs
	$(COMPOSE) logs -f

prod-ps: ## Show production container status
	$(COMPOSE) ps

# ---- development: one container, SQLite, live reload (http://localhost:8081) ------------------

dev: ## Build and start the dev container on :8081 (foreground; Ctrl-C to stop)
	UID=$$(id -u) GID=$$(id -g) $(DEV_COMPOSE) up --build

dev-down: ## Stop the dev container
	$(DEV_COMPOSE) down

dev-logs: ## Follow dev logs
	$(DEV_COMPOSE) logs -f

local: ## Run without Docker via dev.sh (needs .venv and nginx) on :8080
	./dev.sh start

local-stop: ## Stop the dev.sh processes
	./dev.sh stop

# ---- tests -------------------------------------------------------------------------------------

setup: ## Install Python and Node test dependencies
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	npm install

test: test-backend test-postgres test-frontend ## Run everything: backend (SQLite + PostgreSQL) and frontend

test-backend: ## Backend tests on SQLite
	$(PYTEST) -q

test-postgres: ## Backend tests on PostgreSQL (starts and removes a throwaway postgres container)
	@docker rm -f $(PG_NAME) >/dev/null 2>&1 || true
	docker run -d --name $(PG_NAME) -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=rc -p 127.0.0.1:$(PG_PORT):5432 postgres:16-alpine >/dev/null
	@trap 'docker rm -f $(PG_NAME) >/dev/null' EXIT; \
	until docker exec $(PG_NAME) pg_isready -U postgres -d rc >/dev/null 2>&1; do sleep 1; done; sleep 2; \
	DATABASE_URL=postgresql://postgres:pw@127.0.0.1:$(PG_PORT)/rc $(PYTEST) -q

test-frontend: ## Frontend tests (Vitest + jsdom)
	npm test

# ---- security ----------------------------------------------------------------------------------

security: security-npm security-python security-images ## Run all security scans (npm audit, pip-audit, Trivy image scan)
	@echo "security: all scans passed"

security-npm: ## Scan npm dependencies (npm audit; fails on moderate or higher)
	npm audit --audit-level=moderate

security-python: ## Scan Python dependencies (pip-audit against pinned requirements.txt)
	$(PIP_AUDIT) --no-deps --disable-pip -r requirements.txt

security-images: ## Build the prod images and scan them with Trivy (fails on fixable HIGH/CRITICAL)
	docker build --target api -t radiocalico-api .
	docker build --target web -t radiocalico-web .
	docker build --target db -t radiocalico-db .
	@for img in $(SCAN_IMAGES); do \
	  echo "== trivy: scanning $$img (first run downloads the vulnerability database)"; \
	  if docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v radiocalico-trivy-cache:/root/.cache \
	    $(TRIVY_IMAGE) image --quiet --severity HIGH,CRITICAL --ignore-unfixed --skip-files $(TRIVY_SKIP) --exit-code 1 $$img; \
	  then echo "   ok: no fixable HIGH/CRITICAL findings in $$img"; \
	  else echo "   FAILED: $$img has fixable HIGH/CRITICAL findings (listed above)"; fail=1; fi; \
	done; exit $${fail:-0}
