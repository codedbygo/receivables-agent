# Collections Agent. Every command lives here; `make help` lists them.
# Backend in backend/ (uv), web console in frontend/ (npm), stack in compose.yaml.
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv
BE := backend
STATE := .bearing/state
SKIPPED := $(STATE)/.skipped
COMPOSE := docker compose
# Host-side URL for the compose Postgres (make up); CI and the sandbox override it.
POSTGRES_PORT ?= 5434
export POSTGRES_PORT
DATABASE_URL ?= postgresql+psycopg://collections:collections@localhost:$(POSTGRES_PORT)/collections
# The gates `make check` runs, in order (brief: lint + typecheck + test + eval-replay).
# eval-replay is the offline half of the evaluation; the scenario half (make eval) needs Postgres and runs in CI's integration job.
GATES := format-check lint typecheck test eval-replay web-check

define skip
{ mkdir -p $(STATE); echo "$(1): SKIPPED ($(2) not installed)"; echo "$(1) $(2)" >> $(SKIPPED); exit 0; }
endef
define need_uv
command -v $(UV) >/dev/null || $(call skip,$(1),uv); [ -x $(BE)/.venv/bin/python ] || { echo "$(1): no $(BE)/.venv; run make setup" >&2; exit 1; }
endef
define not_built
@echo "$(1): not built yet ($(2)); see docs/design/collections-lld.md section 10" >&2; exit 1
endef

.PHONY: help setup up down logs migrate migrate-down test-integration seed reset-demo demo test lint typecheck format format-check fix eval eval-replay web-setup web-build web-check e2e check audit coverage smoke db-backup db-restore doctor clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install backend dependencies (uv.lock) and print the git hooks command
	cd $(BE) && $(UV) sync --locked --all-groups
	@echo "setup: hooks are not enabled automatically; run: bash .githooks/install.sh"

up: ## Start the stack (docker compose) and wait for health; build the console first (make web-build)
	@[ -f frontend/dist/index.html ] || { echo "up: frontend/dist missing; run make web-setup web-build first" >&2; exit 1; }
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack (data volume kept)
	$(COMPOSE) down

logs: ## Tail the stack logs
	$(COMPOSE) logs -f --tail=100

migrate: ## Apply database migrations (alembic upgrade head)
	cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run alembic upgrade head

migrate-down: ## Roll back one migration
	cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run alembic downgrade -1

test-integration: ## Postgres tests (needs make up; drops and recreates the public schema of DATABASE_URL)
	@n=$$(git ls-files -co --exclude-standard '$(BE)/tests/service/test_*.py' '$(BE)/tests/tool/test_*.py' | wc -l | tr -d ' '); \
	[ "$$n" -gt 0 ] || { echo "test-integration: 0 test files, nothing checked" >&2; exit 1; }; \
	set -o pipefail; cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run pytest -m integration 2>&1 | tail -5 && echo "test-integration: $$n test files checked"

coverage: ## Whole suite with line coverage (needs Postgres): fails under 100% line coverage, overall and on guardrails, services, tools, mcp
	@$(call need_uv,coverage); set -o pipefail; cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run pytest --cov --cov-report=term-missing:skip-covered --cov-fail-under=100 2>&1 | tail -25 \
	&& $(UV) run coverage report --include='app/guardrails/*,app/services/*,app/tools/*,app/mcp/*' --fail-under=100 | tail -1 \
	&& echo "coverage: gates met (100% overall and core)"

smoke: ## Post-deploy checks against a running stack; resets the demo data first and last (SMOKE_BASE_URL, ADMIN_TOKEN, MCP_URL, MCP_TOKEN, MAILPIT_URL, MAILPIT_UI_AUTH)
	@$(call need_uv,smoke); cd $(BE) && $(UV) run python -m app.smoke

db-backup: ## pg_dump the stack's database to backups/<UTC timestamp>.sql (COMPOSE="docker compose -f compose.yaml -f compose.prod.yaml" for the hosted demo)
	@mkdir -p backups; f=backups/$$(date -u +%Y%m%dT%H%M%SZ).sql; \
	$(COMPOSE) exec -T postgres pg_dump -U collections --clean --if-exists collections > $$f && echo "db-backup: $$f"

db-restore: ## Restore a backup into the stack's database: make db-restore FILE=backups/<file>.sql
	@[ -f "$(FILE)" ] || { echo "db-restore: FILE=backups/<file>.sql is required" >&2; exit 1; }
	$(COMPOSE) exec -T postgres psql -v ON_ERROR_STOP=1 -U collections collections < $(FILE)

seed: ## Load the deterministic demo seed into an empty database
	cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run python -m app.seed

reset-demo: ## Reset data to the start of the ABC story (keeps users, sessions, llm_calls)
	cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run python -m app.seed --reset

demo: ## Reset the running stack to the start of the ABC story (needs make up), then print where to go
	$(COMPOSE) exec -T api python -m app.seed --reset
	@echo "demo: console http://localhost:8080  inbox http://localhost:8025  script: README.md, How to demo"

web-setup: ## Install the web console's dependencies (pnpm-lock.yaml)
	cd frontend && pnpm install --frozen-lockfile

web-build: ## Build the web console into frontend/dist (served by the web service)
	cd frontend && pnpm exec tsc --noEmit && pnpm exec vite build

e2e: ## The demo story in a browser against the running stack (make up; E2E_BASE_URL to point elsewhere)
	cd frontend && pnpm exec playwright test

web-check: ## Typecheck and unit-test the web console
	@command -v pnpm >/dev/null || $(call skip,web-check,pnpm); [ -d frontend/node_modules ] || { echo "web-check: no frontend/node_modules; run make web-setup" >&2; exit 1; }; \
	cd frontend && pnpm exec tsc --noEmit && pnpm exec vitest run 2>&1 | tail -4 && echo "web-check: typecheck and tests passed"

format: ## Format Python
	cd $(BE) && $(UV) run ruff format .

format-check: ## Fail if any Python file is unformatted
	@$(call need_uv,format-check); n=$$(git ls-files -co --exclude-standard '$(BE)/*.py' | wc -l | tr -d ' '); \
	[ "$$n" -gt 0 ] || { echo "format-check: 0 python files, nothing checked" >&2; exit 1; }; \
	cd $(BE) && $(UV) run ruff format --check . >/dev/null || { echo "format-check: run make format" >&2; exit 1; }; \
	echo "format-check: $$n files checked"

lint: ## ruff check
	@$(call need_uv,lint); n=$$(git ls-files -co --exclude-standard '$(BE)/*.py' | wc -l | tr -d ' '); \
	[ "$$n" -gt 0 ] || { echo "lint: 0 python files, nothing checked" >&2; exit 1; }; \
	cd $(BE) && $(UV) run ruff check . && echo "lint: $$n files checked"

typecheck: ## mypy strict over app/
	@$(call need_uv,typecheck); n=$$(git ls-files -co --exclude-standard '$(BE)/app/*.py' | wc -l | tr -d ' '); \
	[ "$$n" -gt 0 ] || { echo "typecheck: 0 python files, nothing checked" >&2; exit 1; }; \
	set -o pipefail; cd $(BE) && $(UV) run mypy | tail -1 && echo "typecheck: $$n files checked"

test: ## pytest (no network; Postgres tests are marked integration and need make up)
	@$(call need_uv,test); n=$$(git ls-files -co --exclude-standard '$(BE)/tests/*test_*.py' | wc -l | tr -d ' '); \
	[ "$$n" -gt 0 ] || { echo "test: 0 test files, nothing checked" >&2; exit 1; }; \
	set -o pipefail; cd $(BE) && $(UV) run pytest -m "not integration" 2>&1 | tail -5 && echo "test: $$n test files checked"

eval: ## Full evaluation (needs make up): replies, guardrails, 12 scenarios; writes docs/evals/report.md, resets demo data
	cd $(BE) && DATABASE_URL=$(DATABASE_URL) LLM_MODE=replay $(UV) run python -m app.evaluation

eval-replay: ## Offline evaluation gate: 40 replies, red team, golden (no database, no network)
	@$(call need_uv,eval-replay); cd $(BE) && LLM_MODE=replay $(UV) run python -m app.evaluation --offline

fix: format ## Apply automatic fixes
	cd $(BE) && $(UV) run ruff check --fix .

audit: ## Known-vulnerability scan of the locked Python and web dependencies (needs network; CI security job)
	@$(call need_uv,audit); cd $(BE) && $(UV) export --frozen --no-hashes --no-emit-project -o .audit-requirements.txt >/dev/null \
	&& $(UV) run pip-audit -r .audit-requirements.txt --no-deps --disable-pip --progress-spinner off; s=$$?; rm -f .audit-requirements.txt; [ $$s -eq 0 ]
	@command -v pnpm >/dev/null || $(call skip,audit,pnpm); cd frontend && pnpm audit --prod
	@echo "audit: python and web dependencies have no known vulnerabilities"

check: ## The gate: every gate in GATES, then the tally. CI runs exactly this.
	@mkdir -p $(STATE); rm -f $(SKIPPED)
	@for g in $(GATES); do $(MAKE) --no-print-directory $$g || { echo "check: $$g failed" >&2; exit 1; }; done
	@s=$$(cut -d' ' -f1 $(SKIPPED) 2>/dev/null | sort -u | wc -l | tr -d ' '); r=$$(( $(words $(GATES)) - s )); \
	echo "check: $$r gates run, $$s skipped"; \
	if [ "$$s" -eq 0 ]; then echo "check: passed"; \
	elif [ "$${BEARING_ALLOW_SKIP:-0}" = "1" ] && [ -z "$$CI" ]; then echo "check: passed with skips (local only)"; \
	else sed 's/^/  skipped: /' $(SKIPPED); echo "check: FAILED, $$s gate(s) skipped" >&2; exit 1; fi

doctor: ## Environment diagnostics
	@echo "uv:        $$(command -v $(UV) >/dev/null && $(UV) --version || echo missing)"
	@echo "docker:    $$(command -v docker >/dev/null && docker --version || echo missing)"
	@echo "venv:      $$([ -x $(BE)/.venv/bin/python ] && $(BE)/.venv/bin/python --version || echo 'missing (make setup)')"
	@echo "lock:      $$([ -f $(BE)/uv.lock ] && echo present || echo MISSING)"
	@echo "hooksPath: $$(git config core.hooksPath || echo 'NOT SET (bash .githooks/install.sh)')"

clean: ## Remove caches
	rm -rf $(BE)/.ruff_cache $(BE)/.mypy_cache $(BE)/.pytest_cache $(SKIPPED)
	find $(BE) -name __pycache__ -type d -prune -exec rm -rf {} +
