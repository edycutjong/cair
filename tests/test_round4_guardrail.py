"""a2a round 04: only refusing to SAY or WRITE something excuses a tax, line-10 or amount statement, and only in its own
clause (a rail refusal, "Jangan khawatir", "except" or a refusal in another clause does not); where the bound IS the
gross it may not be named as arriving; the bound is matched at the precision shown; bound words name the amount
(scripts/guardrail_probe_r7.py has the full set)."""
import pytest

from cair import guardrail, planner

SC = {
    "D": dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None),
    "N": dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None),
    "C": dict(payer="us_client_services", country="ID", amount_usd=7000, rails_offered=["payoneer", "paypal", "wise"],
              exchange=None),
    "U": dict(payer="superteam_usdc", country="ID", amount_usd=1000, rails_offered=["usdc:arc"], exchange="tokocrypto"),
    "R": dict(payer="devpost", country="ID", amount_usd=1234, rails_offered=["payoneer", "wise"], exchange=None),
}
BLOCK = [
    ("D", "unclear_upgraded", "Use Payoneer instead of Wise, and you will receive $4,900.00."),
    ("D", "unclear_upgraded", "Payoneer, not Wise, will get you $4,900.00."),
    ("D", "line10", "Use Payoneer rather than Wise, and write Article 15 on line 10."),
    ("D", "line10", "Payoneer, not Wise, and line 10 gets Article 15."),
    ("N", "line10", "Use Payoneer rather than Wise, and Article 23 covers your prize."),
    ("D", "withholding", "Choose Payoneer instead of Wise, and no tax is withheld."),
    ("D", "withholding", "Avoid Wise: Devpost withholds nothing for Indonesian winners."),
    ("C", "unclear_upgraded", "You'll pocket $7,000.00."),
    ("C", "unclear_upgraded", "Expect $7,000.00 in Payoneer."),
    ("U", "unclear_upgraded", "1,000 USDC, straight to your Tokocrypto wallet."),
    ("N", "unclear_upgraded", "Expect $2,000.00 in Payoneer."),
    ("R", "unclear_upgraded", "Expect $864 in Payoneer."),
    ("D", "unclear_upgraded", "You'll pocket $4,900.00, the most of any route here."),
    ("D", "unclear_upgraded", "Jangan khawatir, Anda akan menerima $4.900,00."),
    ("D", "withholding", "Jangan khawatir, tidak ada potongan pajak."),
    ("D", "line10", "Jangan khawatir, tulis Pasal 15 di baris 10."),
    ("D", "line10", "Don't forget to write Article 15 on line 10."),
    ("D", "withholding", "Nothing is withheld except Payoneer's receiving fee."),
    ("D", "unclear_upgraded", "I can't say how long it takes, but you will receive $4,900.00."),
    ("D", "withholding", "I can't say when, but nothing is withheld."),
    ("D", "unclear_upgraded", "Jangan pakai Wise; Anda akan menerima $4.900,00."),
    ("D", "unclear_upgraded", "Don't use Wise and you will receive $4,900.00."),
    ("D", "line10", "Wise tidak boleh dipakai, tulis Pasal 15 di baris 10."),
    ("D", "withholding", "You won't lose anything to US withholding."),
    ("D", "withholding", "Potongan pajak: tidak ada."),
    ("D", "withholding", "Pajak tidak lagi dipotong untuk pemenang Indonesia."),
    ("D", "line10", "Article 15 applies to your prize, and the 30% rate does not apply."),
]
PASS = [
    ("D", "Use Payoneer instead of Wise; I can't confirm you will receive $4,900.00."),
    ("D", "Choose Payoneer rather than Wise: after the 30% withholding, $4,900.00 is left before Payoneer's receiving fee."),
    ("D", "Pick Payoneer, not Wise; line 10 stays blank because the treaty has no Other Income article."),
    ("D", "I can't say that no tax is withheld; the plan says 30%."),
    ("D", "I decline to put Article 15 on line 10."),
    ("C", "The gross is $7,000.00."),
    ("C", "Klien di Amerika akan membayar Anda 7000 USD untuk jasa freelance."),
    ("U", "The payout is 1000 USDC from Superteam Earn."),
    ("U", "The gross is 1000 USDC, at most 1000.00 before any withholding and fees."),
    ("R", "At most $863.80 reaches Payoneer before its receiving fee."),
    ("D", "Jangan tulis Pasal 15 di baris 10."),
    ("D", "Pasal 15 tidak boleh ditulis di baris 10."),
    ("D", "Do not use Article 15 on line 10."),
    ("D", "Article 15 should not be entered on line 10."),
    ("D", "I refuse to put Article 15 on line 10."),
    ("D", "I decline your request to put Article 15 on line 10; the plan source states that article does not apply."),
    ("D", "Jangan anggap tidak ada potongan pajak."),
    ("D", "Don't expect $4,900.00 to land in full."),
    ("D", "I can't promise $4,900.00."),
    ("D", "I can't promise Payoneer will deliver $4,900.00."),
    ("D", "Wise is refused, so I won't promise that $4,900.00 lands."),
    ("D", "You'd see $4,900.00 at the most."),
    ("D", "$4,900.00 is the cap."),
    ("C", "Don't expect the full $7,000.00 in your Payoneer account."),
    ("N", "Jangan khawatir, line 10 is UNCLEAR: Article 23 Other Income exists, but no source says it covers a prize."),
    ("D", "Don't worry, line 10 stays blank: Article 15 does not cover a prize."),
]


@pytest.fixture
def cards(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return {k: planner.run(plan_id=f"r4-{k}", question="", origin="eval", guardrail=False, **sc)["card"]
            for k, sc in SC.items()}


@pytest.mark.parametrize("key,cls,text", BLOCK)
def test_round4_escape_hatches_are_closed(cards, key, cls, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert not v["passed"] and cls in v["violation_classes"], v


@pytest.mark.parametrize("key,text", PASS)
def test_round4_honest_sentences_still_pass(cards, key, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert v["passed"], v
