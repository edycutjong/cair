"""Mutation check for the exhaustive invariant test: does it catch a broken route rule?

Breaks one rule on purpose — the route becomes the first option offered on the form, whatever its verdict — and runs
all scenarios of tests/test_exhaustive.py through the real planner with the same stubs (fixed ECB rate, fixed wording
call; no network, no keys). Prints how many scenarios and invariant violations the unchanged test would report.

    .venv/bin/python scripts/mutation_route_rule.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import pytest  # noqa: E402
import test_exhaustive as t  # noqa: E402

from cair import fx, llm, planner  # noqa: E402


def main() -> None:
    mp = pytest.MonkeyPatch()
    mp.setattr(fx, "live", lambda quote, timeout=5.0: {
        "base": "USD", "quote": quote, "rate": {"IDR": "17881", "INR": "96.73", "PHP": "62.821"}[quote],
        "as_of": "2026-10-09", "source": "ECB reference rate (test)", "stale": False})
    mp.setattr(llm, "chat", lambda messages, temperature=0.0, max_tokens=700: "Ok.")
    real_build = planner.build_card

    def broken_build(plan_id, payer, country, amount_usd, exchange, rails, recommended, *rest):
        first = rails[0]["rail"] if rails else None   # the mutation: ignore the verdicts
        return real_build(plan_id, payer, country, amount_usd, exchange, rails, first, *rest)

    mp.setattr(planner, "build_card", broken_build)
    scenarios = failing = violations = 0
    try:
        for i, (payer, country, amount, rails, exchange) in enumerate(t.SCENARIOS):
            card = planner.run(plan_id=f"m-{i}", payer=payer, country=country, amount_usd=amount, rails_offered=rails,
                               exchange=exchange, question="Which one?", origin="eval")["card"]
            bad = t._violations(card, amount)
            scenarios += 1
            failing += bool(bad)
            violations += len(bad)
    finally:
        mp.undo()
    print(f"mutation 'route = first offered option': {scenarios} scenarios, {failing} failing, {violations} violations")


if __name__ == "__main__":
    main()
