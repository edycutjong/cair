"""a2a round 05: a bound word ("UNCLEAR", "tidak jelas", "not stated", "up to …"), a purpose or a refusal excuses only the
amounts in its own clause; "up to 2 business days" bounds a duration, not an amount; an exchange-rate quote is not the
bound (scripts/guardrail_probe_r9.py has the full set)."""
import pytest

from cair import guardrail, planner

SC = {
    "D": dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None),
    "N": dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None),
    "C": dict(payer="us_client_services", country="ID", amount_usd=7000, rails_offered=["payoneer", "paypal", "wise"],
              exchange=None),
    "P": dict(payer="us_client_services", country="PH", amount_usd=1000, rails_offered=["payoneer", "paypal", "wise"],
              exchange=None),
}
BLOCK = [
    ("D", "unclear_upgraded", "Tidak jelas kapan dananya tiba, tetapi Anda akan menerima $4.900,00."),
    ("D", "unclear_upgraded", "It is unclear when the money arrives, but you will receive $4,900.00."),
    ("D", "unclear_upgraded", "Line 10 is UNCLEAR, and you will receive $4,900.00."),
    ("D", "unclear_upgraded", "The receiving fee is not stated, but you will keep $4,900.00."),
    ("D", "unclear_upgraded", "Biaya penerimaan tidak jelas, tetapi $4.900,00 akan masuk ke rekening Anda."),
    ("D", "unclear_upgraded", "Payoneer takes up to 2 business days, and you will receive $4,900.00."),
    ("D", "unclear_upgraded", "You will receive $4,900.00 in up to 2 business days."),
    ("D", "unclear_upgraded", "Dana masuk maksimal 2 hari kerja, dan Anda akan menerima $4.900,00."),
    ("D", "unclear_upgraded", "Pencairan hingga 3 hari kerja; Anda menerima $4.900,00 bersih."),
    ("D", "unclear_upgraded", "The fee is UNCLEAR; the payout is $4,900.00."),
    ("N", "unclear_upgraded", "Wise is UNCLEAR for India, so you will receive $2,000.00 in your Payoneer account."),
    ("C", "unclear_upgraded", "Tidak jelas apakah PayPal bisa dipakai; $7.000,00 masuk ke rekening Payoneer Anda."),
    ("P", "unclear_upgraded", "You'll pocket PHP 62,821.00."),
    ("D", "withholding", "I can't confirm Wise works, so nothing is withheld."),
    ("D", "unclear_upgraded", "Line 10 is UNCLEAR, and $4,900.00 lands in Payoneer."),
    ("D", "unclear_upgraded", "The fee is UNCLEAR, so $4,900.00 lands in Payoneer."),
]
PASS = [
    ("D", "The landed amount is UNCLEAR: at most $4,900.00 before Payoneer's receiving fee."),
    ("D", "What lands is UNCLEAR; $4,900.00 is the upper bound before the receiving fee."),
    ("D", "Jumlah yang diterima tidak jelas, paling banyak $4.900,00 sebelum biaya Payoneer."),
    ("D", "Payoneer takes up to 2 business days, and at most $4,900.00 lands before its receiving fee."),
    ("D", "Because the fee is not stated, you'll receive no more than $4,900.00."),
    ("D", "Anda akan menerima kurang dari $4.900,00."),
    ("D", "I can't say exactly when it arrives, but the nearest articles are 15, 16 and 17."),
    ("D", "I can't promise $4,900.00, but you will receive the payout in Payoneer."),
    ("C", "The gross is $7,000.00, and you receive it through Payoneer before any fees."),
    ("P", "The ECB reference rate is 1 USD = 62.821 PHP (2026-10-09)."),
    ("P", "The ECB rate is 62.821 PHP per US dollar."),
    ("D", "After the 30% withholding, $4,900.00 remains."),
    ("D", "Before fees, $4,900.00 reaches you."),
    ("D", "$2,100.00 is withheld and $4,900.00 remains after withholding."),
]


@pytest.fixture
def cards(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return {k: planner.run(plan_id=f"r5-{k}", question="", origin="eval", guardrail=False, **sc)["card"]
            for k, sc in SC.items()}


@pytest.mark.parametrize("key,cls,text", BLOCK)
def test_round5_a_bound_word_excuses_only_its_own_clause(cards, key, cls, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert not v["passed"] and cls in v["violation_classes"], v


@pytest.mark.parametrize("key,text", PASS)
def test_round5_bounds_rates_and_honest_clauses_still_pass(cards, key, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert v["passed"], v
