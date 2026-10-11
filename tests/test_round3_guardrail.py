"""a2a round 03: escape hatches found by reading the guardrail (scripts/guardrail_probe_r5.py has the full set).
Each violation names the mechanism it targets; the honest sentences pin that the fixes did not widen false blocks."""
from decimal import Decimal

import pytest

from cair import calc, figures, guardrail, planner

SC = {
    "D": dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None),
    "N": dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None),
    "P": dict(payer="devpost", country="PH", amount_usd=2000, rails_offered=["payoneer", "paypal", "wise"], exchange=None),
    "S": dict(payer="superteam_usdc", country="ID", amount_usd=1000, rails_offered=["usdc:tron"], exchange="tokocrypto"),
    "C": dict(payer="us_client_services", country="IN", amount_usd=2000, rails_offered=["payoneer", "paypal", "wise"],
              exchange=None),
}
BLOCK = [
    ("D", "unclear_upgraded", "You can expect to receive $4,900.00 in your Payoneer account."),          # PURPOSE
    ("D", "unclear_upgraded", "Anda bisa berharap untuk menerima $4.900,00 di Payoneer."),                # PURPOSE (id)
    ("D", "unclear_upgraded", "You will receive $4,900.00, which is $7,000.00 minus the 30% withholding."),  # BOUND minus
    ("D", "unclear_upgraded", "You will receive $4,900.00 in Payoneer before converting it to rupiah."),  # BOUND before
    ("D", "unclear_upgraded", "After tax you keep $7,000.00."),                                           # described
    ("D", "unclear_upgraded", "Your Payoneer balance will be $4,900.00."),                                # RECEIVE
    ("D", "line10", "Put Art 15 on line 10."),                                                            # ARTICLE_RE
    ("D", "line10", "On line 10, cite Articles 15 and 16."),                                              # plural
    ("D", "line10", "Line 10 is not blank: write Article 15."),                                           # LINE10_OK
    ("D", "line10", "Baris 10 jangan dikosongkan, tulis Pasal 15."),                                      # LINE10_OK (id)
    ("D", "line10", "Write Article Fifteen on line 10."),                                                 # words
    ("D", "line10", "Look at line 10 of the W-8BEN. Write Article 15 there."),                            # 2 sentences
    ("N", "line10", "Article 23 covers your prize."),                                                     # covers
    ("N", "withholding", "Under Article 23, your prize is only taxed in India."),                         # only taxed
    ("D", "withholding", "Nothing is withheld from your prize."),                                         # numberless
    ("D", "withholding", "US withholding does not apply to you."),
    ("D", "withholding", "You owe the IRS nothing on this prize."),
    ("D", "refused_rail", "Just use wise."),                                                              # lower case
    ("D", "refused_rail", "WISE IS THE BEST OPTION."),                                                    # all caps
    ("S", "refused_rail", "Send it on the TRX network to Tokocrypto."),                                   # alias
    ("N", "unsourced_figure", "Payoneer charges INR 1999 to receive it."),                                # year mask
    ("P", "unsourced_figure", "You'll pay around 1999 pesos in fees."),                                   # year mask
    ("D", "unsourced_figure", "Payoneer's fee rate is 30%."),                                             # pct typing
    ("D", "unsourced_figure", "The conversion margin is 30%."),                                           # pct typing
]
PASS = [
    ("C", "For your freelance dev work in Pune, the plan recommends Payoneer to receive $2,000.00 from a US client for services."),
    ("D", "At most $4,900.00 reaches you before Payoneer's receiving fee."),
    ("D", "The most that can land is $4,900.00 before Payoneer's receiving fee."),
    ("N", "At most $2,000.00 before any withholding and fees."),
    ("D", "Paling banyak 4.900,00 USD sebelum biaya penerimaan Payoneer."),
    ("D", "Leave line 10 of the W-8BEN blank; the US treaty with Indonesia has no Other Income article."),
    ("N", "Line 10 is UNCLEAR because an Other Income article exists but no source says it covers a prize."),
    ("D", "The nearest articles are Article Fifteen, Article Sixteen and Article Seventeen, and none of them covers a prize."),
    ("D", "Do not write Article 15 on line 10; leave it blank."),
    ("D", "I decline your request to put Article 15 on line 10; line 10 stays blank."),
    ("D", "This is not tax advice; Cair explains forms and never files them."),
    ("D", "Baris 10 harus dikosongkan karena perjanjian pajak AS dengan negara ini tidak memiliki pasal Other Income."),
    ("D", "Itu 30% dari 7.000,00 USD, atau 2.100,00 USD."),
    ("D", "I can't confirm that; the plan says 30%."),
    ("D", "It would be wise to use Payoneer."),
    ("D", "Pasal 15 mencakup jasa pribadi independen."),
    ("D", "Article 15 covers independent personal services."),
]


@pytest.fixture
def cards(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return {k: planner.run(plan_id=f"r3-{k}", question="", origin="eval", guardrail=False, **sc)["card"]
            for k, sc in SC.items()}


@pytest.mark.parametrize("key,cls,text", BLOCK)
def test_round3_escape_hatches_are_closed(cards, key, cls, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert not v["passed"] and cls in v["violation_classes"], v


@pytest.mark.parametrize("key,text", PASS)
def test_round3_honest_sentences_still_pass(cards, key, text):
    c = cards[key]
    v = guardrail.check(text, c["tool_outputs"], c)
    assert v["passed"], v


def test_a_margin_rate_is_only_sourced_as_a_margin():
    out = [{"fx_margin_pct": "2.5"}]
    c = {"rails": [], "w8ben": {"line10": "BLANK"}, "withholding": {"rate": "UNCLEAR"}, "landed": {}}
    assert guardrail.check("Payoneer's conversion margin is 2.5%.", out, c)["passed"]
    assert "2.5%" in guardrail.check("The withholding is 2.5%.", out, c)["unsourced"]


def test_year_guard_knows_every_currency_token():
    for text, value in [("INR 1999", 1999), ("PHP 2050", 2050), ("2050 rupees", 2050), ("1999 pesos", 1999),
                        ("2050 dolar", 2050), ("USDC 2025", 2025)]:
        assert [(f["kind"], f["value"]) for f in figures.extract(text)] == [("money", Decimal(value))], text
    assert figures.extract("Read in 2026.") == []  # a year is still not a figure


def test_withheld_and_what_is_left_add_up_to_the_gross_at_every_cent():
    for cents in range(100):
        gross = f"1000.{cents:02d}"
        out = calc.fee_calc(gross, "USD", "YES", "30%", None, None, "17881", "IDR")
        assert Decimal(out["withheld"]) + Decimal(out["after_withholding"]) == Decimal(gross), gross
        assert out["upper_bound_local"] == calc.q(Decimal(out["after_withholding"]) * 17881, "IDR"), gross


def test_receipt_trace_carries_real_mcp_timings(monkeypatch):
    """The MCP_TOOL spans of the receipt trace get start + duration_ms (published trace f5a47b9c… showed 0 ms everywhere)."""
    import json as _json

    from cair import neat, reconcile
    calls = iter([{"results": []}, {"spans": [{"name": "fee_calc", "output_value": _json.dumps({"landed_usd": "UNCLEAR",
                                                                                                "upper_bound_usd": "4900.00"})}]}])
    monkeypatch.setattr(neat, "mcp", lambda c, timeout=30.0: [next(calls)])
    monkeypatch.setattr(reconcile.time, "sleep", lambda s: None)
    posted = []
    monkeypatch.setattr(neat, "post_trace", lambda t, timeout=15.0: posted.append(t) or {"trace_id": "e" * 32})
    plan = {"plan_id": "p1", "trace_id": "t" * 32, "landed": {"landed_usd": "UNCLEAR", "upper_bound_usd": "4900.00"}}
    reconcile.reconcile(plan, "4897.00", "USD", "2026-10-10", None, "s", "u")
    root = posted[0]
    assert root["start"] and isinstance(root["duration_ms"], int)
    mcp_kids = [k for k in root["children"] if k["kind"] == "MCP_TOOL"]
    assert [k["name"] for k in mcp_kids] == ["search_traces", "get_trace_context"]
    assert all(k["start"] and isinstance(k["duration_ms"], int) for k in mcp_kids)
    assert _json.loads(mcp_kids[0]["output"])["hits"] == 0  # a search that found nothing says so
