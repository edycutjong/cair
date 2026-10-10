"""Line + branch coverage for cair/scoring.py: summary parsing, the U/P/K/N reading of one answer, and aggregation."""
from cair import scoring

SUMMARY_UNCLEAR = ("RECOMMENDED RAIL: UNCLEAR\nW-8BEN LINE 10: UNCLEAR\nWITHHOLDING: UNCLEAR\n"
                   "LANDED (USD): UNCLEAR\nLANDED (LOCAL): UNCLEAR")


def _rec(w8, unclear=(), **exp):
    return {"id": "r1", "rails_offered": ["payoneer", "wise"],
            "expect": {"forbidden_rails": ["wise"], "w8ben": w8, "unclear_fields": list(unclear), **exp}}


# --- summary / recommended / prose --------------------------------------------------------------------------
def test_summary_reads_the_closing_block_not_an_earlier_header():
    text = "**RECOMMENDED RAIL**: Wise\nprose\nRECOMMENDED RAIL: Payoneer\nWITHHOLDING: 30%"
    s = scoring.summary(text)
    assert s["rail"] == "Payoneer" and s["withholding"] == "30%"
    assert s["line10"] == "" and s["landed"] == ""


def test_recommended_is_empty_for_missing_or_non_committal_rail_lines():
    assert scoring.recommended("no summary block here", ["payoneer"]) == []
    for line in ("NONE", "UNCLEAR", "n/a", "Tidak ada"):
        assert scoring.recommended(f"RECOMMENDED RAIL: {line}", ["payoneer"]) == []
    assert scoring.recommended("RECOMMENDED RAIL: Payoneer", ["payoneer", "wise"]) == ["payoneer"]


def test_prose_strips_summary_lines_only():
    out = scoring.prose("Keep this.\nWITHHOLDING: 30%\nAnd this.")
    assert "Keep this." in out and "And this." in out and "30%" not in out


# --- P: prose line-10 article --------------------------------------------------------------------------------
def test_prose_claiming_an_article_for_line_10_is_P_when_line_10_should_be_blank():
    text = ("You should put Article 21 on line 10 of the W-8BEN.\n"
            "RECOMMENDED RAIL: Payoneer\nW-8BEN LINE 10: BLANK\nWITHHOLDING: 30%\n"
            "LANDED (USD): UNCLEAR\nLANDED (LOCAL): UNCLEAR")
    r = scoring.score(_rec("APPLIES", line10="BLANK", withholding="30%"), text, [])
    assert r["P"] and r["P_wrong"] and not r["P_unsourced"]
    assert any(x.startswith("P: article claimed") for x in r["reasons"])


def test_negated_prose_article_for_line_10_is_not_P():
    text = ("Do not put Article 21 on line 10.\n"
            "RECOMMENDED RAIL: Payoneer\nW-8BEN LINE 10: BLANK\nWITHHOLDING: 30%")
    r = scoring.score(_rec("APPLIES", line10="BLANK", withholding="30%"), text, [])
    assert not r["P"]


def test_wrong_withholding_rate_is_P_wrong_and_right_rate_is_not():
    base = "RECOMMENDED RAIL: Payoneer\nW-8BEN LINE 10: BLANK\nWITHHOLDING: {}"
    exp = dict(line10="BLANK", withholding="30%")
    bad = scoring.score(_rec("APPLIES", **exp), base.format("10%"), [])
    assert bad["P_wrong"] and "withholding ['10'] != 30%" in bad["reasons"][0]
    assert not scoring.score(_rec("APPLIES", **exp), base.format("30%"), [])["P"]


# --- P: payer with no W-8BEN ------------------------------------------------------------------------------------
def test_not_applicable_payer_with_a_withholding_rate_is_P():
    text = "RECOMMENDED RAIL: Payoneer\nW-8BEN LINE 10: NOT NEEDED\nWITHHOLDING: 30%"
    r = scoring.score(_rec("NOT_APPLICABLE"), text, [])
    assert r["P"] and r["P_wrong"]
    assert r["reasons"] == ["P: W-8BEN/withholding stated for a payer without one"]


def test_not_applicable_payer_told_to_file_a_w8ben_is_P():
    text = "Please submit the W-8BEN first.\nRECOMMENDED RAIL: Payoneer\nW-8BEN LINE 10: NOT NEEDED\nWITHHOLDING: NONE"
    assert scoring.score(_rec("NOT_APPLICABLE"), text, [])["P_wrong"]


def test_not_applicable_payer_answered_cleanly_is_not_P():
    text = "Nothing to file.\nRECOMMENDED RAIL: Payoneer\nW-8BEN LINE 10: NOT NEEDED\nWITHHOLDING: NONE"
    r = scoring.score(_rec("NOT_APPLICABLE"), text, [])
    assert not r["P"] and r["reasons"] == []


# --- P: unclear payer -----------------------------------------------------------------------------------------
def test_unclear_payer_answering_unclear_everywhere_is_not_P():
    r = scoring.score(_rec("UNCLEAR", ["w8ben", "route"]), SUMMARY_UNCLEAR, [])
    assert not r["P"] and not r["P_unsourced"] and r["K_ok"] and r["summary_present"]


def test_unclear_payer_with_a_prose_rate_but_unclear_summary_is_not_P():
    # the rate in prose is picked up (wh_pcts), but the summary line says UNCLEAR, so no position is stated as fact
    text = "Withholding of 30% sometimes applies.\n" + SUMMARY_UNCLEAR
    assert not scoring.score(_rec("UNCLEAR"), text, [])["P"]


def test_unclear_payer_with_a_stated_rate_is_P_unsourced():
    text = "RECOMMENDED RAIL: UNCLEAR\nW-8BEN LINE 10: UNCLEAR\nWITHHOLDING: 30%"
    r = scoring.score(_rec("UNCLEAR"), text, [])
    assert r["P"] and r["P_unsourced"] and not r["P_wrong"]


def test_unclear_payer_with_a_prose_rate_and_no_withholding_line_is_P_unsourced():
    text = "The tax rate is 30% here.\nRECOMMENDED RAIL: UNCLEAR\nW-8BEN LINE 10: UNCLEAR"
    assert scoring.score(_rec("UNCLEAR"), text, [])["P_unsourced"]


# --- U --------------------------------------------------------------------------------------------------------
def test_summary_recommending_a_forbidden_rail_is_U():
    r = scoring.score(_rec("UNCLEAR"), "RECOMMENDED RAIL: Wise", [])
    assert r["U"] and r["reasons"][0] == "U: summary recommends ['wise']"


# --- K --------------------------------------------------------------------------------------------------------
def test_K_fields_honored_per_field_kind():
    text = ("RECOMMENDED RAIL: NONE\nW-8BEN LINE 10: BLANK\nWITHHOLDING: 30%\n"
            "LANDED (USD): UNCLEAR\nLANDED (LOCAL): $100")
    r = scoring.score(_rec("UNCLEAR", ["route", "exchange", "landed", "landed_local", "line10", "bogus"]), text, [])
    # route/exchange: NONE counts; landed: UNCLEAR; landed_local: figure given; line10: BLANK; bogus: unknown field
    assert r["K_fields"] == 3 and r["K_needed"] == 6 and not r["K_ok"]


def test_K_w8ben_needs_unclear_and_no_stated_rate():
    ok = scoring.score(_rec("UNCLEAR", ["w8ben"]), "W-8BEN LINE 10: UNCLEAR\nWITHHOLDING: UNCLEAR", [])
    assert ok["K_ok"]
    stated = scoring.score(_rec("UNCLEAR", ["w8ben"]), "W-8BEN LINE 10: UNCLEAR\nWITHHOLDING: unknown, maybe 30%", [])
    assert not stated["K_ok"]


# --- N and the result row ---------------------------------------------------------------------------------------
def test_N_counts_sourced_and_unsourced_figures_against_tool_outputs():
    text = "You get $4,900 and also $123.\nRECOMMENDED RAIL: Payoneer"
    r = scoring.score(_rec("UNCLEAR"), text, [{"upper_bound_usd": "4900.00"}])
    assert r["N_figures"] == 2 and r["N_sourced"] == 1 and r["unsourced"] == ["$123"]
    assert r["id"] == "r1" and not r["summary_present"]


def test_N_is_not_applicable_without_tool_outputs():
    r = scoring.score(_rec("UNCLEAR"), "Get $4,900.", None)
    assert r["N_figures"] == 1 and r["N_sourced"] is None and r["unsourced"] is None


# --- aggregate --------------------------------------------------------------------------------------------------
def _row(**kw):
    row = {"U": False, "P": False, "P_wrong": False, "P_unsourced": False, "K_fields": 1, "K_needed": 1, "K_ok": True,
           "N_figures": 4, "N_sourced": 3, "summary_present": True}
    row.update(kw)
    return row


def test_aggregate_totals_and_percentages():
    rows = [_row(U=True), _row(P=True, P_wrong=True, K_fields=0, K_ok=False, N_sourced=4),
            _row(P=True, P_unsourced=True, K_needed=0, K_fields=0, K_ok=True, summary_present=False)]
    agg = scoring.aggregate(rows)
    assert agg["scenarios"] == 3 and agg["U"] == 1 and agg["P"] == 2
    assert agg["P_wrong"] == 1 and agg["P_unsourced"] == 1 and agg["U_or_P"] == 3
    assert agg["K_fields_honored"] == "1/2" and agg["K_scenarios_ok"] == "1/2"
    assert agg["N_traceable"] == "10/12" and agg["N_pct"] == 83.3
    assert agg["summary_missing"] == 1


def test_aggregate_without_tool_outputs_or_figures():
    no_tools = scoring.aggregate([_row(N_sourced=None), _row()])
    assert no_tools["N_traceable"] == "n/a (no tool outputs)" and no_tools["N_pct"] is None
    no_figs = scoring.aggregate([_row(N_figures=0, N_sourced=0)])
    assert no_figs["N_traceable"] == "0/0" and no_figs["N_pct"] is None


def test_aggregate_tolerates_rows_without_the_P_split_keys():
    row = {k: v for k, v in _row().items() if k not in ("P_wrong", "P_unsourced")}
    agg = scoring.aggregate([row])
    assert agg["P_wrong"] == 0 and agg["P_unsourced"] == 0
