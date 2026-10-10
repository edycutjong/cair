"""Line + branch coverage for cair/tools.py: clip, forced-failure injection, source attachment, every tool's output
shape and its UNCLEAR / not-found paths. The rules sheet is real data or a hand-built Sheet; FX is patched; no network."""
import json

import pytest

from cair import calc, fx, rules, tools, treaty
from cair.rules import UNCLEAR, Fact, Sheet


def _sheet(facts=None, quotes=None):
    return Sheet(facts=facts or {}, quotes=quotes or {}, version="v")


def _fact(value="YES", sid="S1"):
    return Fact(value, sid, "https://example.test/s1", "2026-10-10", "row")


@pytest.fixture
def use_sheet(monkeypatch):
    def setter(sheet):
        monkeypatch.setattr(rules, "sheet", lambda: sheet)
        return sheet
    return setter


# ---- clip ----

def test_clip_short_text_is_untouched():
    assert tools.clip("abc def", 7) == "abc def"


def test_clip_cuts_at_word_boundary_and_marks_the_cut():
    assert tools.clip("alpha beta gamma delta", 14) == "alpha beta …"


def test_clip_strips_trailing_punctuation_before_the_marker():
    assert tools.clip("one two, three four", 9) == "one two …"


# ---- forced failure ----

def test_maybe_fail_is_silent_by_default():
    assert tools.FORCE_FAIL.get() is None
    tools._maybe_fail("fx_quote")


def test_maybe_fail_raises_only_for_the_named_tool():
    token = tools.FORCE_FAIL.set("fx_quote")
    try:
        tools._maybe_fail("rail_eligibility")
        with pytest.raises(tools.ToolFailure, match="fx_quote unavailable"):
            tools._maybe_fail("fx_quote")
    finally:
        tools.FORCE_FAIL.reset(token)


@pytest.mark.parametrize("name,call", [
    ("platform_rails", lambda: tools.platform_rails("devpost")),
    ("rail_eligibility", lambda: tools.rail_eligibility("ID", "devpost", "wise")),
    ("treaty_lookup", lambda: tools.treaty_lookup("ID")),
    ("fx_quote", lambda: tools.fx_quote("IDR")),
    ("exchange_networks", lambda: tools.exchange_networks("indodax", "base")),
    ("fee_calc", lambda: tools.fee_calc("100", "USD", "YES", "30%", None, None, None, "IDR")),
])
def test_every_tool_honours_forced_failure(name, call):
    token = tools.FORCE_FAIL.set(name)
    try:
        with pytest.raises(tools.ToolFailure, match=name):
            call()
    finally:
        tools.FORCE_FAIL.reset(token)


# ---- _src ----

def test_src_none_fact_gives_none():
    assert tools._src(None, _sheet()) is None


def test_src_without_matching_quote_returns_bare_fact_dict():
    out = tools._src(_fact(), _sheet(quotes={"OTHER": {"quote": "q"}}))
    assert out == _fact().as_dict()
    assert "quote" not in out and "page_date" not in out


def test_src_attaches_quote_and_page_date():
    sh = _sheet(quotes={"S1": {"quote": "the quote", "page_date": "12 May 2026"}})
    out = tools._src(_fact(), sh)
    assert out["quote"] == "the quote" and out["page_date"] == "12 May 2026"
    assert out["source_id"] == "S1"


def test_src_defaults_missing_page_date_and_clips_long_quote():
    long_quote = "word " * 200
    out = tools._src(_fact(), _sheet(quotes={"S1": {"quote": long_quote}}))
    assert out["page_date"] == ""
    assert out["quote"].endswith(" …") and len(out["quote"]) <= 402


# ---- platform_rails ----

def test_platform_rails_known_payer(use_sheet):
    use_sheet(_sheet({("*", "devpost", "_payer", "w8ben_applies"): _fact("YES"),
                      ("*", "devpost", "wise", "deliverable"): _fact("OFFERED"),
                      ("*", "devpost", "paypal", "deliverable"): _fact("OFFERED")},
                     {"S1": {"quote": "q", "page_date": "d"}}))
    out = tools.platform_rails("devpost")
    assert out["payer"] == "devpost" and out["known_payer"] is True
    assert out["offered_rails"] == ["paypal", "wise"]
    assert out["w8ben_applies"] == "YES"
    assert out["w8ben_source"]["quote"] == "q"


def test_platform_rails_unknown_payer_is_unclear_and_unsourced(use_sheet):
    use_sheet(_sheet())
    assert tools.platform_rails("nobody") == {"payer": "nobody", "known_payer": False, "offered_rails": [],
                                              "w8ben_applies": UNCLEAR, "w8ben_source": None}


def test_platform_rails_real_sheet_devpost_requires_w8ben():
    out = tools.platform_rails("devpost")
    assert out["known_payer"] and out["w8ben_applies"] == "YES"
    assert {"payoneer", "paypal", "wise"} <= set(out["offered_rails"])


# ---- rail_eligibility ----

def test_rail_eligibility_sourced_no(use_sheet):
    use_sheet(_sheet({("ID", "*", "wise", "deliverable"): _fact("NO")}, {"S1": {"quote": "banned"}}))
    out = tools.rail_eligibility("ID", "devpost", "wise")
    assert out["deliverable"] == "NO" and out["country"] == "ID" and out["rail"] == "wise"
    assert out["source"]["quote"] == "banned"


def test_rail_eligibility_offered_says_nothing_about_country(use_sheet):
    use_sheet(_sheet({("*", "devpost", "wise", "deliverable"): _fact("OFFERED")}))
    out = tools.rail_eligibility("ID", "devpost", "wise")
    assert out["deliverable"] == UNCLEAR and out["source"] is None


def test_rail_eligibility_no_row_is_unclear(use_sheet):
    use_sheet(_sheet())
    assert tools.rail_eligibility("ID", "devpost", "payoneer") == {
        "country": "ID", "rail": "payoneer", "deliverable": UNCLEAR, "source": None}


def test_rail_eligibility_fact_without_source_id_has_no_source(use_sheet):
    use_sheet(_sheet({("ID", "*", "payoneer", "deliverable"): _fact("YES", sid="")}))
    out = tools.rail_eligibility("ID", "devpost", "payoneer")
    assert out["deliverable"] == "YES" and out["source"] is None


def test_rail_eligibility_real_sheet_wise_not_deliverable_in_indonesia():
    out = tools.rail_eligibility("ID", "devpost", "wise")
    assert out["deliverable"] == "NO"
    assert out["source"]["source_id"] == "WISE-ID" and out["source"]["quote"]


# ---- treaty_lookup ----

def test_treaty_lookup_with_sheet_rows_and_index(use_sheet, monkeypatch):
    use_sheet(_sheet({("ID", "*", "_treaty", "treaty_other_income_article"): _fact("NONE"),
                      ("ID", "*", "_treaty", "withholding_default"): _fact("30%")},
                     {"S1": {"quote": "q"}}))
    seen = {}

    def nearest(country, query):
        seen["args"] = (country, query)
        return {"treaty_text_indexed": True, "nearest": [{"article": 15, "title": "T", "score": 1.0}]}

    monkeypatch.setattr(treaty, "nearest", nearest)
    out = tools.treaty_lookup("ID", "custom query")
    assert seen["args"] == ("ID", "custom query")
    assert out["other_income_article"] == "NONE" and out["withholding_default"] == "30%"
    assert out["article_source"]["quote"] == "q" and out["withholding_source"]["quote"] == "q"
    assert out["nearest"][0]["article"] == 15
    json.dumps(out)


def test_treaty_lookup_unknown_country_is_unclear(use_sheet, monkeypatch):
    use_sheet(_sheet())
    monkeypatch.setattr(treaty, "nearest", lambda c, q: {"country": c, "treaty_text_indexed": False})
    out = tools.treaty_lookup("ZZ")
    assert out["other_income_article"] == UNCLEAR and out["withholding_default"] == UNCLEAR
    assert out["article_source"] is None and out["withholding_source"] is None
    assert out["treaty_text_indexed"] is False


def test_treaty_lookup_default_query_and_missing_nearest_key(use_sheet, monkeypatch):
    use_sheet(_sheet())
    queries = []

    def nearest(country, query):
        queries.append(query)
        return {"treaty_text_indexed": False}  # no "nearest" key -> documents attr falls back to []

    monkeypatch.setattr(treaty, "nearest", nearest)
    tools.treaty_lookup("ZZ")
    assert queries == [treaty.QUERY]


def test_treaty_lookup_real_data_indonesia():
    out = tools.treaty_lookup("ID")
    assert out["treaty_text_indexed"] is True
    assert out["other_income_article"] == "NONE" and out["withholding_default"] == "30%"
    assert len(out["nearest"]) == 3


def test_treaty_lookup_real_data_unindexed_country():
    out = tools.treaty_lookup("ZZ")
    assert out["nearest"] == [] and out["other_income_article"] == UNCLEAR


# ---- fx_quote / fx_quote_fallback ----

def test_fx_quote_delegates_to_live(monkeypatch):
    seen = []
    monkeypatch.setattr(fx, "live", lambda q: seen.append(q) or {"quote": q, "rate": "1", "stale": False})
    assert tools.fx_quote("IDR") == {"quote": "IDR", "rate": "1", "stale": False}
    assert seen == ["IDR"]


def test_fx_quote_fallback_without_snapshot_is_unclear_and_stale(monkeypatch):
    monkeypatch.setattr(fx, "cached", lambda q: None)
    out = tools.fx_quote_fallback("IDR", "timeout")
    assert out == {"quote": "IDR", "rate": UNCLEAR, "as_of": None, "stale": True,
                   "reason": "live ECB rate failed (timeout) and no earlier snapshot exists"}


def test_fx_quote_fallback_with_snapshot_keeps_rate_and_explains(monkeypatch):
    hit = {"base": "USD", "quote": "IDR", "rate": "17000", "as_of": "2026-10-01", "stale": True}
    monkeypatch.setattr(fx, "cached", lambda q: dict(hit))
    out = tools.fx_quote_fallback("IDR", "HTTP 500")
    assert out["rate"] == "17000" and out["as_of"] == "2026-10-01" and out["stale"] is True
    assert out["reason"] == "live ECB rate failed (HTTP 500); using the last fetched ECB rate"


# ---- exchange_networks ----

EX = {("*", "_exchange", "indodax:usdc:base", "deliverable"): _fact("YES"),
      ("*", "_exchange", "indodax:usdc:tron", "deliverable"): _fact("NO"),
      ("*", "_exchange", "indodax:usdc:solana", "deliverable"): _fact("YES")}


def test_exchange_networks_yes_for_indonesia(use_sheet):
    use_sheet(_sheet(dict(EX), {"S1": {"quote": "q"}}))
    out = tools.exchange_networks("indodax", "base")
    assert out["deliverable"] == "YES" and out["note"] is None
    assert out["source"]["quote"] == "q"
    assert out["sourced_yes_networks"] == ["base", "solana"]
    assert "test transaction" in out["always"]


def test_exchange_networks_sourced_no_passes_through(use_sheet):
    use_sheet(_sheet(dict(EX)))
    out = tools.exchange_networks("indodax", "tron", "ID")
    assert out["deliverable"] == "NO" and out["note"] is None


def test_exchange_networks_unsourced_chain_is_unclear(use_sheet):
    use_sheet(_sheet(dict(EX)))
    out = tools.exchange_networks("indodax", "arc")
    assert out["deliverable"] == UNCLEAR and out["source"] is None and out["note"] is None


def test_exchange_networks_foreign_resident_is_unclear_with_note(use_sheet):
    use_sheet(_sheet(dict(EX)))
    out = tools.exchange_networks("indodax", "base", "US")
    assert out["deliverable"] == UNCLEAR
    assert out["note"] == "Indodax is an Indonesian exchange; no source says it serves residents of this country"
    assert out["source"]["value"] == "YES"  # the sourced row is still shown for transparency


def test_exchange_networks_unknown_exchange_has_no_rows(use_sheet):
    use_sheet(_sheet(dict(EX)))
    out = tools.exchange_networks("binance", "base")
    assert out["deliverable"] == UNCLEAR and out["source"] is None and out["sourced_yes_networks"] == []


def test_exchange_networks_known_exchange_missing_from_country_map(use_sheet, monkeypatch):
    monkeypatch.setitem(rules.EXCHANGES, "newx", "NewX")
    use_sheet(_sheet({("*", "_exchange", "newx:usdc:base", "deliverable"): _fact("YES")}))
    out = tools.exchange_networks("newx", "base")
    assert out["deliverable"] == UNCLEAR and "NewX is an Indonesian exchange" in out["note"]


def test_exchange_networks_real_sheet_indodax_ethereum():
    out = tools.exchange_networks("indodax", "ethereum")
    assert out["deliverable"] == "YES" and "ethereum" in out["sourced_yes_networks"]


# ---- fee_calc ----

def test_fee_calc_forwards_every_argument(monkeypatch):
    seen = {}

    def fake(*args):
        seen["args"] = args
        return {"ok": True}

    monkeypatch.setattr(calc, "fee_calc", fake)
    out = tools.fee_calc("500", "USD", "YES", "30%", "1.5", "2", "17000", "IDR")
    assert out == {"ok": True}
    assert seen["args"] == ("500", "USD", "YES", "30%", "1.5", "2", "17000", "IDR")


def test_fee_calc_real_arithmetic_withholds_thirty_percent():
    out = tools.fee_calc("100", "USD", "YES", "30%", None, None, None, "IDR")
    assert out["withheld"] == "30.00" and out["after_withholding"] == "70.00"
    assert out["landed_usd"] == UNCLEAR  # no receiving fee given -> never guessed
