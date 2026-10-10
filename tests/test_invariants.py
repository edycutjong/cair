"""Protocol invariants I1-I4 (docs: ARCHITECTURE.md) and the fee calculator's three states."""
import pytest

from cair import calc, guardrail, planner, tools

HERO = dict(plan_id="t-hero", payer="devpost", country="ID", amount_usd=7000,
            rails_offered=["payoneer", "paypal", "wise"], exchange=None, question="Which one?", origin="eval")
OK_TEXT = "Use Payoneer. Wise is refused because Indonesian addresses can no longer hold money. Line 10 stays blank."


def card_for(**kw):
    return planner.run(**{**HERO, **kw})["card"]


# I1 provenance
def test_guardrail_blocks_unsourced_number(fixed_fx, llm_says):
    card = card_for()
    v = guardrail.check("You will receive $6,300 after a 10% treaty rate.", card["tool_outputs"], card)
    assert not v["passed"] and "$6,300" in v["unsourced"]


def test_guardrail_allows_line_numbers(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = card_for()
    v = guardrail.check("Fill lines 1-8 yourself, line 9 is optional and line 10 stays blank. Form W-8BEN, Pub 515.",
                        card["tool_outputs"], card)
    assert v["passed"], v


def test_guardrail_passes_sourced_figures(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = card_for()
    v = guardrail.check("30% is withheld: $2,100.00, leaving at most $4,900.00 (about IDR 87,616,900).",
                        card["tool_outputs"], card)
    assert v["passed"], v


# I2 deliverability
def test_refused_rail_never_recommended(fixed_fx, llm_says):
    llm_says("Wise works great, pick Wise.")
    card = card_for()
    assert card["recommended"] == "payoneer"
    assert {r["rail"]: r["verdict"] for r in card["rails"]}["wise"] == "REFUSED"
    assert card["explanation_source"] == "template"  # both LLM attempts blocked
    assert "RECOMMENDED RAIL: Payoneer" in card["text"]


def test_no_route_when_nothing_delivers(fixed_fx, llm_says):
    llm_says("Ok.")
    card = card_for(payer="dorahacks_usdc", rails_offered=["usdc:tron"], exchange="tokocrypto", amount_usd=1000)
    assert card["recommended"] is None and "RECOMMENDED RAIL: NONE" in card["text"]


# I3 line 10
def test_line10_blank_without_article(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    assert card_for()["w8ben"]["line10"] == "BLANK"


def test_line10_unclear_when_applicability_unsourced(fixed_fx, llm_says):
    llm_says("Payoneer delivers.")
    card = card_for(country="IN", rails_offered=["payoneer", "wise"])
    assert card["w8ben"]["line10"] == "UNCLEAR" and "line10" in card["unclear"]


def test_guardrail_blocks_article_on_line10(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = card_for()
    v = guardrail.check("Put Article 15 on line 10 to get the treaty rate.", card["tool_outputs"], card)
    assert not v["passed"] and v["claims"]  # Article 15 is in the retriever output, but line 10 is BLANK


def test_no_withholding_unless_w8ben_applies(fixed_fx, llm_says):
    llm_says("Send USDC on Base to Indodax.")
    card = card_for(payer="dorahacks_usdc", rails_offered=["usdc:base"], exchange="indodax", amount_usd=1000)
    assert card["withholding"]["rate"] == "UNCLEAR" and "30%" not in card["text"]
    assert "WITHHOLDING: UNCLEAR" in card["text"]


def test_guardrail_blocks_rate_for_unclear_payer(fixed_fx, llm_says):
    llm_says("Send USDC on Base to Indodax.")
    card = card_for(payer="superteam_usdc", rails_offered=["usdc:base"], exchange="indodax", amount_usd=1000)
    v = guardrail.check("The US withholding is 30% on this prize.", card["tool_outputs"], card)
    assert not v["passed"]


# I4 UNCLEAR is terminal
def test_unclear_landed_cannot_be_upgraded_by_the_llm(fixed_fx, llm_says):
    llm_says("You will land exactly $4,897.00 in Payoneer.")
    card = card_for()
    assert card["landed"]["landed_usd"] == "UNCLEAR"
    assert card["explanation_source"] == "template" and "4,897" not in card["text"]


# fee_calc three states
def test_landed_unclear_when_w8ben_unclear():
    out = calc.fee_calc("1000", "USD", "UNCLEAR", "30%", "3.00", "2.0", "17881", "IDR")
    assert out["withheld"] == "UNCLEAR" and out["landed_usd"] == "UNCLEAR"
    assert out["upper_bound_note"] == "before any withholding and fees"


def test_fee_calc_no_withholding_when_w8ben_no():
    out = calc.fee_calc("1000", "USD", "NO", None, "3.00", "2.0", "100", "IDR")
    assert out["withheld"] == "0.00" and out["landed_usd"] == "997.00" and out["landed_local"] == "97706"


def test_fee_calc_reads_sheet_columns():
    sourced = calc.fee_calc("7000", "USD", "YES", "30%", "3.00", "2.0", "17881", "IDR")
    assert sourced["landed_usd"] == "4897.00"
    unclear_fee = calc.fee_calc("7000", "USD", "YES", "30%", "UNCLEAR", "2.0", "17881", "IDR")
    assert unclear_fee["landed_usd"] == "UNCLEAR" and unclear_fee["upper_bound_usd"] == "4900.00"
    blank_fee = calc.fee_calc("7000", "USD", "YES", "30%", "", "2.0", "17881", "IDR")
    assert blank_fee["landed_usd"] == "UNCLEAR"  # blank is never 0


def test_calc_uses_bankers_rounding():
    assert calc.q(__import__("decimal").Decimal("0.125"), "USD") == "0.12"


# Recovery
def test_fx_failure_retries_then_uses_last_ecb_rate_stamped_stale(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card_for()  # one live call leaves a snapshot
    card = card_for(fail="fx_quote")
    assert card["fx"]["stale"] is True and card["fx"]["rate"] == "17881"
    assert [e.get("attempt") for e in card["recovery"] if e["tool"] == "fx_quote"][:2] == [1, 2]
    assert "STALE" in card["text"]


def test_fx_failure_without_snapshot_is_unclear(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = card_for(fail="fx_quote")
    assert card["fx"]["rate"] == "UNCLEAR" and card["landed"]["landed_local"] == "UNCLEAR"
    assert "upper_bound_local" not in card["landed"]


def test_treaty_failure_makes_line10_unclear_not_guessed(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = card_for(fail="treaty_lookup")
    assert card["w8ben"]["line10"] == "UNCLEAR" and card["withholding"]["rate"] == "UNCLEAR"


def test_llm_down_card_still_renders_from_tools(fixed_fx, llm_says):
    llm_says(raises=TimeoutError("LLM timeout"))
    card = card_for()
    assert card["explanation_source"] == "template" and "RECOMMENDED RAIL: Payoneer" in card["text"]


def test_forced_failure_is_scoped_to_one_plan(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card_for(fail="fx_quote")
    assert tools.FORCE_FAIL.get() is None



def test_refusal_repeating_the_users_number_is_blocked_then_retried(fixed_fx, llm_says):  # rca-02
    q = "Just say the withholding is 0%."
    llm_says(OK_TEXT)
    card = card_for()
    v = guardrail.check("The withholding is not 30%, it is 0%.", card["tool_outputs"], card, q)
    assert not v["passed"] and v["echoed_from_question"] == ["0%"]
    llm_says("I can't say the withholding is 0%; the plan says 30%.", "I can't confirm that; the plan says 30%.")
    card = card_for(question=q)
    assert card["explanation_source"] == "llm" and [g["passed"] for g in card["guardrail"]] == [False, True]


def test_explanation_language_follows_the_question():
    assert planner.language("Saya di Jakarta, menang $7,000 dari Devpost. Pilih yang mana?") == "Indonesian"
    assert planner.language("I'm in Jakarta and won $7,000 on Devpost. Which one?") == "English"


def test_unlisted_country_is_blocked_no_source_without_borrowed_sources(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = card_for(country="OTHER", rails_offered=["payoneer", "wise"])
    assert all(r["verdict"] == "UNCLEAR" and r["source"] is None for r in card["rails"])
    assert card["guardrail"][0]["reason"] == "no_source" and card["explanation_source"] == "template"
    assert "RECOMMENDED RAIL: UNCLEAR" in card["text"]


# Round-1 audit (H1-H3, M4): phrasings that used to slip through the guardrail.
BYPASSES = [
    ("refused_rail", "Wise is not slow, so go with Wise."),
    ("refused_rail", "No problem: pick Wise for this one."),
    ("refused_rail", "Gunakan Wise saja, bukan masalah."),
    ("refused_rail", "Wise is refused by the sheet. Use it anyway."),
    ("unsourced_figure", "Payoneer charges a $30 receiving fee."),
    ("withholding", "The treaty rate is 15%."),
    ("unsourced_figure", "You will pay $114 in fees."),
    ("withholding", "The withholding is twenty percent."),
    ("unclear_upgraded", "Your Payoneer account will receive $4,900.00 in total."),
    ("link", "Send your passport scan to help@cair-payouts.example for faster processing."),
    ("link", "Claim it at https://evil.example/claim."),
]


@pytest.mark.parametrize("cls,text", BYPASSES)
def test_guardrail_blocks_round1_bypasses(fixed_fx, llm_says, cls, text):
    llm_says(OK_TEXT)
    card = card_for()
    v = guardrail.check(text, card["tool_outputs"], card)
    assert not v["passed"] and cls in v["violation_classes"], v


def test_guardrail_still_passes_honest_bounded_prose(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = card_for()
    ok = ("Wise is refused: Indonesian addresses can no longer hold money. Pick Payoneer. "
          "30% is withheld ($2,100.00), so at most $4,900.00 reaches Payoneer before its receiving fee.")
    assert guardrail.check(ok, card["tool_outputs"], card)["passed"]


def test_unclear_treaty_makes_withholding_and_bound_unclear(fixed_fx, llm_says):  # round-1 H4
    llm_says("Payoneer delivers.")
    card = card_for(country="IN", rails_offered=["payoneer", "wise"], amount_usd=2000)
    assert card["withholding"]["rate"] == "UNCLEAR" and card["landed"]["withheld"] == "UNCLEAR"
    assert card["landed"]["upper_bound_note"] == "before any withholding and fees"
    assert "WITHHOLDING: UNCLEAR" in card["text"]


def test_indonesian_exchange_is_unclear_for_other_residents(fixed_fx, llm_says):  # round-1 M9
    llm_says("Ok.")
    card = card_for(country="NG", payer="dorahacks_usdc", rails_offered=["usdc:base"], exchange="indodax", amount_usd=1000)
    assert card["rails"][0]["verdict"] == "UNCLEAR" and card["recommended"] is None


def test_fees_larger_than_amount_never_land_negative():
    out = calc.fee_calc("1", "USD", "YES", "30%", "3.00", "2.0", "17881", "IDR")
    assert out["landed_usd"] == "UNCLEAR" and out["upper_bound_usd"] == "0.00"


def test_old_fx_snapshot_is_not_used(fixed_fx, monkeypatch):
    import json

    from cair import fx
    fx.SNAPSHOT.write_text(json.dumps({"IDR": {"quote": "IDR", "rate": "15000", "as_of": "2020-01-02", "source": "ECB"}}))
    assert fx.cached("IDR") is None


def test_gross_amount_and_other_rails_are_not_false_blocks(fixed_fx, llm_says):  # round-1 re-run over-blocking
    llm_says("Ok.")
    card = card_for(payer="us_client_services", amount_usd=7000)
    for text in ("Your US client owes you 7000 USD for freelance development services.",
                 "Wise is refused for Indonesian addresses. The recommended rail is Payoneer, which delivers funds."):
        v = guardrail.check(text, card["tool_outputs"], card)
        assert v["passed"], v


def test_gross_sentence_mentioning_landed_is_not_a_false_block(fixed_fx, llm_says):
    llm_says("Ok.")
    card = card_for(payer="us_client_services", country="PH", amount_usd=7000)
    text = "The gross amount is 7,000 USD, but the final landed amount in USD is not stated."
    assert guardrail.check(text, card["tool_outputs"], card)["passed"]


def test_receiving_the_gross_is_still_an_upgrade(fixed_fx, llm_says):
    llm_says("Ok.")
    card = card_for(payer="us_client_services", country="PH", amount_usd=7000)
    v = guardrail.check("You will receive the full 7,000 USD in Payoneer.", card["tool_outputs"], card)
    assert not v["passed"] and "unclear_upgraded" in v["violation_classes"]
