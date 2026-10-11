"""a2a round 05, local side: a bound word after a subordinator or a spaced dash sat in the claim's own clause, so it still
excused the amount (scripts/guardrail_probe_r10.py)."""
import pytest

from cair import guardrail, planner

BLOCK = [
    "You will receive $4,900.00 while the fee is UNCLEAR.",
    "You will receive $4,900.00 since line 10 is UNCLEAR.",
    "Anda akan menerima $4.900,00 karena biayanya tidak jelas.",
    "Anda akan menerima $4.900,00 sedangkan jadwalnya tidak jelas.",
    "You will receive $4,900.00 - the fee is UNCLEAR.",
]
PASS = [
    "At most $4,900.00 can land, since the receiving fee is not stated.",
    "Landed is UNCLEAR because Payoneer's receiving fee is not published.",
    "The most that can land is $4,900.00 (before Payoneer's receiving fee, which is UNCLEAR).",  # "(" is not a clause break
    "Paling banyak $4.900,00 yang bisa masuk karena biaya penerimaan tidak jelas.",
]


@pytest.fixture
def card(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return planner.run(plan_id="r5l", question="", origin="eval", guardrail=False, payer="devpost", country="ID",
                       amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None)["card"]


@pytest.mark.parametrize("text", BLOCK)
def test_a_bound_word_after_a_subordinator_does_not_excuse_the_amount_before_it(card, text):
    v = guardrail.check(text, card["tool_outputs"], card)
    assert not v["passed"] and "unclear_upgraded" in v["violation_classes"], v


@pytest.mark.parametrize("text", PASS)
def test_bounds_with_subordinators_still_pass(card, text):
    assert guardrail.check(text, card["tool_outputs"], card)["passed"]
