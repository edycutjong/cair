"""a2a round 03, local side: the r5 fixes closed 40 sentences; these pin the design-level fix that followed — when landed is
UNCLEAR the bound amount is only ever stated as a bound, whatever the verb (scripts/guardrail_probe_r6.py has the full set)."""
import pytest

from cair import claims, guardrail, planner

SC = {
    "D": dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None),
    "N": dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None),
}
BLOCK = [
    ("D", "unclear_upgraded", "You'll pocket $4,900.00."),
    ("D", "unclear_upgraded", "$4,900.00 will hit your Payoneer account."),
    ("D", "unclear_upgraded", "Expect $4,900.00 in Payoneer."),
    ("D", "unclear_upgraded", "In rupiah that is IDR 87,616,900 for you."),
    ("D", "withholding", "Withholding: none."),
    ("D", "withholding", "The IRS takes nothing from your prize."),
    ("D", "withholding", "Withholding is waived for you."),
    ("D", "line10", "W-8BEN line ten: Article 15."),
    ("D", "refused_rail", "Send it via TransferWise."),
]
PASS = [
    ("D", "$4,900.00 is the most you could see, not a promise."),
    ("D", "At the ECB rate, IDR 87,616,900 is a ceiling, not a promise."),
    ("D", "After the 30% withholding, $4,900.00 remains; Payoneer's receiving fee is not stated."),
    ("D", "Gross prize: $7,000.00."),
    ("N", "Your gross prize is $2,000.00."),  # the bound equals the gross here: the gross is not a bound
]


@pytest.fixture
def cards(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return {k: planner.run(plan_id=f"r3l-{k}", question="", origin="eval", guardrail=False, **sc)["card"]
            for k, sc in SC.items()}


@pytest.mark.parametrize("key,cls,text", BLOCK)
def test_bound_amount_and_vocabulary_gaps_are_closed(cards, key, cls, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert not v["passed"] and cls in v["violation_classes"], v


@pytest.mark.parametrize("key,text", PASS)
def test_bounds_said_in_other_words_still_pass(cards, key, text):
    c = cards[key]
    assert guardrail.check(text, c["tool_outputs"], c)["passed"]


def test_transferwise_is_a_name_for_wise():
    assert claims.rail_names("wise") == ["Wise", "TransferWise"]
