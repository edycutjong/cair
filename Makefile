# Cair — developer targets. Python 3.12; `make install` creates .venv.
PY ?= .venv/bin/python

.PHONY: help install run lint lint-fix typecheck test test-coverage e2e lighthouse audit security-scan ci ci-full

help:
	@echo "install        create .venv and install runtime + dev dependencies"
	@echo "run            serve the app on http://localhost:8000 (needs the keys in .env.example)"
	@echo "lint           ruff check"
	@echo "lint-fix       ruff check --fix"
	@echo "typecheck      mypy on the cair package"
	@echo "test           pytest (deterministic core, no network or keys)"
	@echo "test-coverage  pytest with coverage report"
	@echo "e2e            Playwright browser tests against a locally booted app"
	@echo "lighthouse     Lighthouse CI audit (needs node)"
	@echo "audit          pip-audit + gitleaks"
	@echo "ci             lint + typecheck + test-coverage + audit"
	@echo "ci-full        ci + e2e"

install:
	python3.12 -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt
	.venv/bin/playwright install chromium

run:
	CAIR_SECURE_COOKIES=0 $(PY) -m uvicorn cair.app:app --port 8000

# ── Code quality ────────────────────────────────────────────
lint:
	@echo "🔍 ruff..."
	$(PY) -m ruff check .

lint-fix:
	$(PY) -m ruff check --fix .

typecheck:
	@echo "🔍 mypy..."
	$(PY) -m mypy cair

test:
	$(PY) -m pytest -q

test-coverage:
	$(PY) -m pytest -q --cov --cov-report=term-missing --cov-report=xml

# ── Browser tests and performance ───────────────────────────
e2e:
	@echo "🎭 Playwright E2E (boots the app with no keys)..."
	$(PY) -m pytest e2e -q

lighthouse:
	@echo "🔦 Lighthouse CI..."
	npx --yes @lhci/cli@0.14 autorun

# ── Security ────────────────────────────────────────────────
audit:
	@echo "=== pip-audit (dependency CVEs) ==="
	$(PY) -m pip_audit -r requirements.txt
	@echo "=== gitleaks (secrets in history) ==="
	gitleaks detect --no-banner --redact

security-scan: audit

ci: lint typecheck test-coverage audit

ci-full: ci e2e
