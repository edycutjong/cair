"""a2a round 04, local side: the r7 clause rule only split at ";" and "but", so a comma or "and" let a refusal in one
clause excuse a claim in the next, and "can't wait to tell you" read as a refusal (scripts/guardrail_probe_r8.py)."""
import pytest

from cair import guardrail, planner

SC = {
    "D": dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None),
    "N": dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None),
}
BLOCK = [
    ("D", "unclear_upgraded", "I can't say how long it takes, you will receive $4,900.00."),
    ("D", "unclear_upgraded", "I can't promise a date, and you will receive $4,900.00."),
    ("D", "withholding", "I cannot confirm the timing, nothing is withheld."),
    ("D", "unclear_upgraded", "I can't wait to tell you: you will receive $4,900.00."),
    ("D", "withholding", "I can't wait to tell you that nothing is withheld."),
    ("D", "unclear_upgraded", "Saya tidak bisa memastikan jadwalnya, Anda akan menerima $4.900,00."),
]
PASS = [
    ("D", "I can't promise a date, but at most $4,900.00 can land, before Payoneer's receiving fee."),
    ("D", "I won't put Articles 15, 16 or 17 on line 10, and line 10 stays blank."),  # a list is not a clause boundary
    ("D", "I can't confirm that rate, and the plan says 30%."),
    ("N", "The gross from Devpost is $2,000.00."),
]


@pytest.fixture
def cards(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return {k: planner.run(plan_id=f"r4l-{k}", question="", origin="eval", guardrail=False, **sc)["card"]
            for k, sc in SC.items()}


@pytest.mark.parametrize("key,cls,text", BLOCK)
def test_a_refusal_in_one_clause_does_not_excuse_the_next(cards, key, cls, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert not v["passed"] and cls in v["violation_classes"], v


@pytest.mark.parametrize("key,text", PASS)
def test_lists_and_honest_refusals_still_pass(cards, key, text):
    c = cards[key]
    assert guardrail.check(text, c["tool_outputs"], c)["passed"]
