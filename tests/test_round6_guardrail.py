"""a2a round 06: the describing words of the tax and line-10 checks ("UNCLEAR", "tidak jelas", "blank", "no source",
"nearest", and "margin" for a rate) excuse only the clause they are in, like refusals and bound words
(scripts/guardrail_probe_r11.py)."""
import pytest

from cair import guardrail, planner

SC = {
    "D": dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None),
    "N": dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None),
}
BLOCK = [
    ("D", "withholding", "Nothing is withheld from your prize, but Payoneer's receiving fee is UNCLEAR."),
    ("D", "withholding", "No US tax is withheld, though the receiving fee is UNCLEAR."),
    ("D", "withholding", "Pajak tidak dipotong, tetapi biaya Payoneer tidak jelas."),
    ("D", "withholding", "Your prize is tax-free, while the conversion margin is UNCLEAR."),
    ("N", "withholding", "The withholding is 30%, but the receiving fee is UNCLEAR."),
    ("N", "withholding", "Withholding is 30%; the conversion margin is UNCLEAR."),
    ("D", "line10", "Write Article 15 on line 10; Payoneer's receiving fee is UNCLEAR."),
    ("D", "line10", "Tulis Pasal 15 di baris 10, karena biaya Payoneer tidak jelas."),
    ("N", "line10", "Article 23 covers your prize, although the fee is UNCLEAR."),
    ("D", "line10", "Under Article 15 you can claim an exemption, but the receiving fee is UNCLEAR."),
]
PASS = [
    ("D", "I decline your request to put Article 15 on line 10; line 10 stays blank."),
    ("D", "Line 10 stays blank: no Article covers a prize."),
    ("N", "Line 10 is UNCLEAR: Article 23 exists, but no source says it covers a prize."),
    ("D", "Article 15 is the nearest match, but it covers employment, not prizes."),
    ("D", "Line 10 stays blank because no article covers a prize, so do not write Article 15."),
    ("D", "30% ($2,100.00) is withheld; the receiving fee is UNCLEAR."),
    ("N", "The withholding rate is UNCLEAR, not 30%."),
    ("D", "After the 30% withholding, the provider's conversion margin still applies."),
]


@pytest.fixture
def cards(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return {k: planner.run(plan_id=f"r6-{k}", question="", origin="eval", guardrail=False, **sc)["card"]
            for k, sc in SC.items()}


@pytest.mark.parametrize("key,cls,text", BLOCK)
def test_round6_unclear_in_another_clause_does_not_excuse_a_tax_or_line10_claim(cards, key, cls, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert not v["passed"] and cls in v["violation_classes"], v


@pytest.mark.parametrize("key,text", PASS)
def test_round6_describing_in_the_same_clause_still_passes(cards, key, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert v["passed"], v
