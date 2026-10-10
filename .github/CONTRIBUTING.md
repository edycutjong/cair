# Contributing

Thanks for your interest in improving Cair! 🎉

## Getting Started
1. Fork the repo and branch from `main`: `git checkout -b feat/your-feature`
2. Install (Python 3.12): `make install`
3. Copy the env template: `cp .env.example .env` (the tests need no keys; the live app and the eval do)
4. Run the app: `make run`

## Before You Open a PR
- `make ci` passes (ruff, mypy, pytest with coverage, pip-audit, gitleaks).
- `make e2e` passes (Playwright, boots the app itself).
- Add or update tests for any behavior change. A regression test is named after the defect it pins.
- A new fact in `data/rules_sheet.csv` needs a primary source and a read date in `data/sources.md`; a fact without
  one stays UNCLEAR.
- Keep commits conventional (`feat:`, `fix:`, `docs:`, `chore:`); releases are cut from them.

## Reporting Bugs / Requesting Features
Open an issue using the provided templates. Include repro steps, expected vs. actual behavior, and environment
details. For a wrong payout rule, link the primary source that contradicts the sheet.
