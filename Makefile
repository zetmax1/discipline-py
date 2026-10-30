# `make check` runs everything the CI job ran: ruff, mypy, pytest against a throwaway
# Postgres (fails if any test was skipped), pip-audit, bandit (against .bandit-baseline.json)
# and gitleaks over the full history. Each step is also its own target.
# Needs requirements-dev.txt installed in venv/ (or PY=...) and Docker. The contract test
# reads ../discipline/contracts/analytics.schema.json unless ANALYTICS_CONTRACT is set.
# `make test-down` stops the test container.

SHELL := bash
.SHELLFLAGS := -eo pipefail -c

PY ?= venv/bin/python
BANDIT_TARGETS := app main.py scripts
GITLEAKS := ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f

COMPOSE := docker compose -f docker-compose.test.yml
# Always the throwaway container, never a URL from the environment.
export TEST_DATABASE_URL = postgres://postgres:test@127.0.0.1:55433/postgres?sslmode=disable

.PHONY: check lint types test audit bandit secrets test-up test-down

check: lint types test audit bandit secrets
	@echo "check: all passed"

lint:
	$(PY) -m ruff check .

types:
	$(PY) -m mypy

test: test-up
	@log=$$(mktemp); trap 'rm -f "$$log"' EXIT; \
	$(PY) -m pytest -q -rs > "$$log" 2>&1 || { cat "$$log"; exit 1; }; \
	tail -1 "$$log"; \
	if grep -qE '[0-9]+ skipped' "$$log"; then grep -E '^SKIPPED' "$$log"; echo "tests were skipped"; exit 1; fi

audit:
	$(PY) -m pip_audit -r requirements.txt --disable-pip --no-deps --progress-spinner off

bandit:
	$(PY) -m bandit -q -r $(BANDIT_TARGETS) -b .bandit-baseline.json

secrets:
	docker run --rm -u "$$(id -u):$$(id -g)" -v "$(CURDIR):/repo:ro" $(GITLEAKS) \
		git --no-banner --redact --exit-code 1 -c /repo/.gitleaks.toml /repo

test-up:
	$(COMPOSE) up -d --wait

test-down:
	$(COMPOSE) down
