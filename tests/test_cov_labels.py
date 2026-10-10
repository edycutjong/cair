"""Line + branch coverage for cair/labels.py, driven by small hand-built rule sheets (no CSV, no network)."""
import pytest

from cair import labels
from cair.rules import UNCLEAR, Fact, Sheet


def make_sheet(rows: dict[tuple[str, str, str, str], str]) -> Sheet:
    facts = {k: Fact(v, "s1", "http://x", "2026-10-10", "|".join(k[:3])) for k, v in rows.items()}
    return Sheet(facts=facts, quotes={"s1": {}}, version="t")


def test_rail_verdict_usdc_without_exchange_is_unclear():
    sheet = make_sheet({("*", "_exchange", "indodax:usdc:base", "deliverable"): "YES"})
    assert labels.rail_verdict(sheet, "ID", "dorahacks_usdc", "usdc:base", None) == UNCLEAR
    assert labels.rail_verdict(sheet, "ID", "dorahacks_usdc", "usdc:base", "") == UNCLEAR
    assert labels.rail_verdict(sheet, "ID", "dorahacks_usdc", "usdc:base", "other") == UNCLEAR


def test_rail_verdict_usdc_judged_by_exchange_page():
    sheet = make_sheet({("*", "_exchange", "indodax:usdc:base", "deliverable"): "YES",
                        ("*", "_exchange", "indodax:usdc:tron", "deliverable"): "NO"})
    assert labels.rail_verdict(sheet, "ID", "dorahacks_usdc", "usdc:base", "indodax") == "YES"
    assert labels.rail_verdict(sheet, "ID", "dorahacks_usdc", "usdc:tron", "indodax") == "NO"
    # chain the exchange page does not mention, and an exchange with no rows at all
    assert labels.rail_verdict(sheet, "ID", "dorahacks_usdc", "usdc:solana", "indodax") == UNCLEAR
    assert labels.rail_verdict(sheet, "ID", "dorahacks_usdc", "usdc:base", "pintu") == UNCLEAR


@pytest.mark.parametrize("cell,expected", [("YES", "YES"), ("NO", "NO"), (UNCLEAR, UNCLEAR), ("OFFERED", UNCLEAR)])
def test_rail_verdict_card_rail_collapses_non_tristate_values(cell, expected):
    sheet = make_sheet({("ID", "devpost", "wise", "deliverable"): cell})
    assert labels.rail_verdict(sheet, "ID", "devpost", "wise", None) == expected


def test_rail_verdict_missing_row_is_unclear():
    assert labels.rail_verdict(make_sheet({}), "ID", "devpost", "wise", None) == UNCLEAR


def full_sheet(over=None):
    rows = {
        ("ID", "devpost", "payoneer", "deliverable"): "YES",
        ("ID", "devpost", "wise", "deliverable"): "NO",
        ("ID", "devpost", "paypal", "deliverable"): "UNCLEAR",
        ("ID", "devpost", "_payer", "w8ben_applies"): "YES",
        ("ID", "*", "_treaty", "treaty_other_income_article"): "NONE",
        ("ID", "*", "_treaty", "withholding_default"): "0%",
        ("ID", "devpost", "payoneer", "receiving_fee_usd"): "1.5",
        ("ID", "devpost", "payoneer", "fx_margin_pct"): "2",
    }
    rows.update(over or {})
    return make_sheet(rows)


def test_expect_w8ben_applies_with_blank_line10_and_complete_landing():
    out = labels.expect(full_sheet(), "ID", "devpost", ["payoneer", "wise", "paypal"], None)
    assert out == {
        "forbidden_rails": ["wise"],
        "acceptable_rails": ["payoneer"],
        "w8ben": "APPLIES",
        "line10": "BLANK",
        "withholding": "0%",
        "unclear_fields": [],
        "sheet_rows": ["ID|devpost|_payer", "ID|devpost|payoneer", "ID|devpost|wise", "ID|devpost|paypal",
                       "ID|*|_treaty"],
    }


def test_expect_line10_article_number():
    out = labels.expect(full_sheet({("ID", "*", "_treaty", "treaty_other_income_article"): "21"}),
                        "ID", "devpost", ["payoneer"], None)
    assert out["line10"] == "ARTICLE 21"
    assert out["unclear_fields"] == []


@pytest.mark.parametrize("cell", [UNCLEAR, "abc"])
def test_expect_line10_unclear_when_article_not_usable(cell):
    out = labels.expect(full_sheet({("ID", "*", "_treaty", "treaty_other_income_article"): cell}),
                        "ID", "devpost", ["payoneer"], None)
    assert out["line10"] == UNCLEAR
    assert out["unclear_fields"] == ["line10"]


def test_expect_line10_unclear_when_treaty_row_missing():
    sheet = full_sheet()
    del sheet.facts[("ID", "*", "_treaty", "treaty_other_income_article")]
    out = labels.expect(sheet, "ID", "devpost", ["payoneer"], None)
    assert out["line10"] == UNCLEAR and "line10" in out["unclear_fields"]


def test_expect_withholding_unclear():
    sheet = full_sheet()
    del sheet.facts[("ID", "*", "_treaty", "withholding_default")]
    out = labels.expect(sheet, "ID", "devpost", ["payoneer"], None)
    assert out["withholding"] == UNCLEAR
    assert out["unclear_fields"] == ["withholding"]


def test_expect_w8ben_not_applicable_skips_treaty_fields():
    out = labels.expect(full_sheet({("ID", "devpost", "_payer", "w8ben_applies"): "NO"}),
                        "ID", "devpost", ["payoneer"], None)
    assert out["w8ben"] == "NOT_APPLICABLE"
    assert "line10" not in out and "withholding" not in out
    assert out["sheet_rows"] == ["ID|devpost|_payer", "ID|devpost|payoneer"]
    assert out["unclear_fields"] == []


def test_expect_w8ben_unclear_flags_landed():
    sheet = full_sheet()
    del sheet.facts[("ID", "devpost", "_payer", "w8ben_applies")]
    out = labels.expect(sheet, "ID", "devpost", ["payoneer"], None)
    assert out["w8ben"] == UNCLEAR
    assert out["unclear_fields"] == ["landed", "w8ben"]


def test_expect_no_acceptable_rail_means_unclear_route_and_no_landing_check():
    out = labels.expect(full_sheet(), "ID", "devpost", ["wise", "paypal"], None)
    assert out["acceptable_rails"] == []
    assert out["forbidden_rails"] == ["wise"]
    assert out["unclear_fields"] == ["route"]


def test_expect_unclear_receiving_fee_flags_landed_only():
    sheet = full_sheet()
    del sheet.facts[("ID", "devpost", "payoneer", "receiving_fee_usd")]
    out = labels.expect(sheet, "ID", "devpost", ["payoneer"], None)
    assert out["unclear_fields"] == ["landed"]


def test_expect_unclear_fx_margin_flags_landed_local_only():
    sheet = full_sheet()
    del sheet.facts[("ID", "devpost", "payoneer", "fx_margin_pct")]
    out = labels.expect(sheet, "ID", "devpost", ["payoneer"], None)
    assert out["unclear_fields"] == ["landed_local"]


def test_expect_recommends_first_sorted_acceptable_rail_for_fees():
    # both rails are YES; payoneer sorts first and has fee data, paypal has none, so landed stays resolved
    sheet = full_sheet({("ID", "devpost", "paypal", "deliverable"): "YES"})
    out = labels.expect(sheet, "ID", "devpost", ["paypal", "payoneer"], None)
    assert out["acceptable_rails"] == ["payoneer", "paypal"]
    assert out["unclear_fields"] == []


def usdc_sheet(over=None):
    rows = {
        ("ID", "dorahacks_usdc", "_payer", "w8ben_applies"): "NO",
        ("*", "_exchange", "indodax:usdc:base", "deliverable"): "YES",
        ("*", "_exchange", "indodax:usdc:tron", "deliverable"): "NO",
    }
    rows.update(over or {})
    return make_sheet(rows)


def test_expect_usdc_payer_resolved_exchange_still_flags_landed():
    out = labels.expect(usdc_sheet(), "ID", "dorahacks_usdc", ["usdc:base", "usdc:tron"], "indodax")
    assert out["acceptable_rails"] == ["usdc:base"]
    assert out["forbidden_rails"] == ["usdc:tron"]
    assert out["w8ben"] == "NOT_APPLICABLE"
    assert out["unclear_fields"] == ["landed"]


def test_expect_usdc_payer_unknown_exchange_flags_exchange_and_route():
    out = labels.expect(usdc_sheet(), "ID", "dorahacks_usdc", ["usdc:base"], None)
    assert out["acceptable_rails"] == []
    assert out["unclear_fields"] == ["exchange", "landed", "route"]


def test_expect_usdc_payer_unlisted_chain_flags_exchange():
    out = labels.expect(usdc_sheet(), "ID", "dorahacks_usdc", ["usdc:base", "usdc:solana"], "indodax")
    assert out["acceptable_rails"] == ["usdc:base"]
    assert out["unclear_fields"] == ["exchange", "landed"]
