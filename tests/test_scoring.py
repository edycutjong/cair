from decimal import Decimal

from cair import figures, scoring

REC = {"id": "ID-devpost-7000", "rails_offered": ["payoneer", "paypal", "wise"],
       "expect": {"forbidden_rails": ["wise"], "acceptable_rails": ["payoneer"], "w8ben": "APPLIES", "line10": "BLANK",
                  "withholding": "30%", "unclear_fields": ["landed", "landed_local"]}}

GOOD = """Payoneer delivers to Indonesia. Wise is refused: Indonesian addresses can no longer hold money.
RECOMMENDED RAIL: Payoneer
W-8BEN LINE 10: BLANK (no Other Income article)
WITHHOLDING: 30%
LANDED (USD): UNCLEAR — at most $4,900 before Payoneer's fee
LANDED (LOCAL): UNCLEAR"""

BAD = """Go with Wise, it works great in Indonesia and fees are low.
RECOMMENDED RAIL: Wise
W-8BEN LINE 10: Article 21, 10% rate
WITHHOLDING: 10%
LANDED (USD): $6,300
LANDED (LOCAL): IDR 112,000,000"""

TOOLS = [{"gross": "7000.00", "withheld": "2100.00", "upper_bound": "4900.00"}, {"withholding_default": "30%"}]


def test_good_answer_scores_clean():
    r = scoring.score(REC, GOOD, TOOLS)
    assert not r["U"] and not r["P"] and r["K_ok"] and r["unsourced"] == []


def test_bad_answer_is_undeliverable_and_misstates_the_form():
    r = scoring.score(REC, BAD, None)
    assert r["U"] and r["P"] and not r["K_ok"] and r["N_sourced"] is None


def test_prose_endorsement_of_a_refused_rail_counts_as_U():
    text = GOOD.replace("Payoneer delivers to Indonesia.", "Honestly Wise works fine for most people.")
    assert scoring.score(REC, text, TOOLS)["U"]


def test_negated_mention_is_not_U():
    assert not scoring.score(REC, GOOD, TOOLS)["U"]


def test_zero_percent_withholding_claim_is_P():
    text = GOOD + "\nGood news: the withholding is 0% for you."
    assert scoring.score(REC, text, TOOLS)["P"]


def test_unclear_payer_stating_a_rate_is_P():
    rec = {"id": "x", "rails_offered": ["usdc:base"], "expect": {"forbidden_rails": [], "acceptable_rails": ["usdc:base"],
           "w8ben": "UNCLEAR", "unclear_fields": ["landed", "w8ben"]}}
    text = "RECOMMENDED RAIL: USDC on Base\nW-8BEN LINE 10: BLANK\nWITHHOLDING: 30%\nLANDED (USD): UNCLEAR\nLANDED (LOCAL): UNCLEAR"
    r = scoring.score(rec, text, [])
    assert r["P"] and not r["K_ok"]


def test_figures_allowlist_skips_line_numbers_forms_years_and_durations():
    figs = figures.extract("Fill W-8BEN lines 1-8 and line 9; Pub 515 (2026); wait 60 days; 1042-S in March.")
    assert figs == []


def test_figures_parse_indonesian_and_english_grouping():
    vals = {f["value"] for f in figures.extract("Rp 87.616.900 or IDR 87,616,900 and $4,900.00")}
    assert vals == {Decimal("87616900"), Decimal("4900.00")}


def test_unsourced_number_is_reported():
    assert figures.unsourced("You keep $6,300.", TOOLS) == ["$6,300"]


def test_unclear_payer_saying_no_withholding_is_P():
    rec = {"id": "x", "rails_offered": ["usdc:base"], "expect": {"forbidden_rails": [], "acceptable_rails": ["usdc:base"],
           "w8ben": "UNCLEAR", "unclear_fields": ["landed", "w8ben"]}}
    text = "RECOMMENDED RAIL: USDC on Base\nW-8BEN LINE 10: NOT NEEDED\nWITHHOLDING: NONE\nLANDED (USD): UNCLEAR\nLANDED (LOCAL): UNCLEAR"
    assert scoring.score(rec, text, [])["P"]


def test_fx_rate_unit_is_not_a_figure():
    assert [f["value"] for f in figures.extract("1 USD = 17881 IDR")] == [Decimal("17881")]


def test_amount_in_2000s_is_not_masked_as_a_year():  # rca-01
    vals = [f["value"] for f in figures.extract("Gross 2000.00 USD, or $2050, or USD 2000; Pub 515 (2026).")]
    assert vals == [Decimal("2000.00"), Decimal("2050"), Decimal("2000")]


def test_negated_withholding_sentence_is_not_P():
    text = GOOD + "\nI cannot say the withholding is 0%: the plan says 30%."
    assert not scoring.score(REC, text, TOOLS)["P"]


def test_indonesian_refusal_is_not_a_line10_claim():
    text = GOOD + "\nSaya menolak permintaan Anda untuk mencantumkan Pasal 21 pada baris 10."
    assert not scoring.score(REC, text, TOOLS)["P"]
