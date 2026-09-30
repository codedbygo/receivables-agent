# Collections Agent. Every command lives here; `make help` lists them.
# Backend in backend/ (uv), web console in web/ (npm), stack in compose.yaml.
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv
BE := backend
STATE := .bearing/state
SKIPPED := $(STATE)/.skipped
COMPOSE := docker compose
# Host-side URL for the compose Postgres (make up); CI and the sandbox override it.
DATABASE_URL ?= postgresql+psycopg://collections:collections@localhost:5432/collections
# The gates `make check` runs, in order (brief: lint + typecheck + test + eval-replay).
# eval joins GATES when the harness lands (HACK-001 P0 step 14); until then it fails loudly on its own.
GATES := format-check lint typecheck test

define skip
{ mkdir -p $(STATE); echo "$(1): SKIPPED ($(2) not installed)"; echo "$(1) $(2)" >> $(SKIPPED); exit 0; }
endef
define need_uv
command -v $(UV) >/dev/null || $(call skip,$(1),uv); [ -x $(BE)/.venv/bin/python ] || { echo "$(1): no $(BE)/.venv; run make setup" >&2; exit 1; }
endef
define not_built
@echo "$(1): not built yet ($(2)); see docs/design/collections-lld.md section 10" >&2; exit 1
endef

.PHONY: help setup up down logs migrate migrate-down test-integration seed reset-demo demo test lint typecheck format format-check fix eval check doctor clean

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install backend dependencies (uv.lock) and print the git hooks command
	cd $(BE) && $(UV) sync --locked --all-groups
	@echo "setup: hooks are not enabled automatically; run: bash .githooks/install.sh"

up: ## Start the stack (docker compose) and wait for health
	$(COMPOSE) up -d --wait

down: ## Stop the stack (data volume kept)
	$(COMPOSE) down

logs: ## Tail the stack logs
	$(COMPOSE) logs -f --tail=100

migrate: ## Apply database migrations (alembic upgrade head)
	cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run alembic upgrade head

migrate-down: ## Roll back one migration
	cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run alembic downgrade -1

test-integration: ## Postgres tests (needs make up; drops and recreates the public schema of DATABASE_URL)
	@n=$$(git ls-files -co --exclude-standard '$(BE)/tests/service/test_*.py' | wc -l | tr -d ' '); \
	[ "$$n" -gt 0 ] || { echo "test-integration: 0 test files, nothing checked" >&2; exit 1; }; \
	set -o pipefail; cd $(BE) && DATABASE_URL=$(DATABASE_URL) $(UV) run pytest -m integration 2>&1 | tail -5 && echo "test-integration: $$n test files checked"

seed: ## Load the deterministic demo seed
	$(call not_built,seed,P0 step 3)

reset-demo: ## Reset data to the start of the ABC story (keeps users, sessions, llm_calls)
	$(call not_built,reset-demo,P0 step 3)

demo: ## reset-demo, then print the demo script location
	$(call not_built,demo,P0 step 15)

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
	cd $(BE) && $(UV) run mypy | tail -1 && echo "typecheck: $$n files checked"

test: ## pytest (no network; Postgres tests are marked integration and need make up)
	@$(call need_uv,test); n=$$(git ls-files -co --exclude-standard '$(BE)/tests/*test_*.py' | wc -l | tr -d ' '); \
	[ "$$n" -gt 0 ] || { echo "test: 0 test files, nothing checked" >&2; exit 1; }; \
	set -o pipefail; cd $(BE) && $(UV) run pytest -m "not integration" 2>&1 | tail -5 && echo "test: $$n test files checked"

eval: ## Run the evaluation in replay mode and write docs/evals/report.md
	$(call not_built,eval,harness lands with P0 step 14)

fix: format ## Apply automatic fixes
	cd $(BE) && $(UV) run ruff check --fix .

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
