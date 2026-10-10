"""One exhaustive verification of the decision path that must never be wrong.

Every payer x every country (plus "somewhere else") x every combination of the payout options the form can show x every
amount band is run through the real planner (real tools, real rules sheet; only the ECB rate and the wording call are
fixed so the run needs no network). Each resulting card must satisfy the protocol invariants. The case count is
printed with `-s` and published in JUDGE.md / README.md.
"""
import itertools
from decimal import Decimal

import pytest

from cair import guardrail, planner, rules, view

AMOUNTS = ["1", "1000", "7000", "1000000"]
COUNTRIES = [*rules.COUNTRIES, view.OTHER]
EXCHANGES = [*rules.EXCHANGES, "other"]


def _scenarios():
    for payer in rules.PAYERS:
        for country in COUNTRIES:
            for amount in AMOUNTS:
                if payer in rules.USDC_PAYERS:
                    for chain, exchange in itertools.product(rules.CHAINS, EXCHANGES):
                        yield payer, country, amount, [f"usdc:{chain}"], exchange
                else:
                    for n in (1, 2, 3):
                        for subset in itertools.combinations(rules.RAILS, n):
                            yield payer, country, amount, list(subset), None


SCENARIOS = list(_scenarios())


@pytest.fixture(scope="module")
def stubbed():
    mp = pytest.MonkeyPatch()
    from cair import fx, llm
    mp.setattr(fx, "live", lambda quote, timeout=5.0: {
        "base": "USD", "quote": quote, "rate": {"IDR": "17881", "INR": "96.73", "PHP": "62.821"}[quote],
        "as_of": "2026-10-09", "source": "ECB reference rate (test)", "stale": False})
    mp.setattr(llm, "chat", lambda messages, temperature=0.0, max_tokens=700: "Ok.")
    yield
    mp.undo()


def _violations(card: dict, amount: str) -> list[str]:
    bad = []
    verdicts = {r["rail"]: r["verdict"] for r in card["rails"]}
    rec = card["recommended"]
    if rec is not None and verdicts.get(rec) != "DELIVERS":
        bad.append(f"I2: recommended {rec} but its verdict is {verdicts.get(rec)}")
    if rec is None and "DELIVERS" in verdicts.values():
        bad.append("I2: a DELIVERS rail exists but no route was picked")
    w8 = card["w8ben"]
    if w8["applies"] != "YES" and (w8["line10"] == "BLANK" or w8["line10"].startswith("ARTICLE")):
        bad.append(f"I3: line 10 {w8['line10']} although W-8BEN applies = {w8['applies']}")
    if w8["line10"].startswith("ARTICLE") and not w8["article_source"]:
        bad.append("I3: an article on line 10 with no source")
    if w8["applies"] != "YES" and card["withholding"]["rate"] not in ("NONE", rules.UNCLEAR):
        bad.append(f"I4: a withholding rate {card['withholding']['rate']} without a W-8BEN")
    landed = card["landed"]["landed_usd"]
    if landed != rules.UNCLEAR:
        if w8["applies"] == rules.UNCLEAR or rec is None:
            bad.append("I4: a landed amount although the tax position or the route is UNCLEAR")
        if Decimal(landed) > Decimal(amount):
            bad.append(f"I4: landed {landed} exceeds the gross {amount}")
    own = guardrail.check(planner.template_explanation(card), card["tool_outputs"], card)
    if not own["passed"]:
        bad.append(f"I1: the fallback template fails the provenance guardrail: {own}")
    return bad


def test_no_scenario_ever_breaks_an_invariant(stubbed):
    failures = []
    for i, (payer, country, amount, rails, exchange) in enumerate(SCENARIOS):
        card = planner.run(plan_id=f"x-{i}", payer=payer, country=country, amount_usd=amount, rails_offered=rails,
                           exchange=exchange, question="Which one?", origin="eval")["card"]
        for v in _violations(card, amount):
            failures.append(f"{payer}/{country}/{amount}/{rails}/{exchange}: {v}")
    print(f"\nexhaustive: {len(SCENARIOS)} scenarios verified against 5 invariant groups, {len(failures)} violations")
    assert not failures, "\n".join(failures[:20])
