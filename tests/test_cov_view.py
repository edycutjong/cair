"""Line + branch coverage for cair/view.py: input validation, plan-card view model, stamps, /rules rows, /verify rows.
No network: neat.mcp is patched at the boundary."""
import json

import pytest

from cair import config, rules, view

UNCLEAR = rules.UNCLEAR


def _body(**kw):
    base = {"payer": "devpost", "country": "ID", "amount": "7000", "rails": ["payoneer"], "question": "q?"}
    base.update(kw)
    return base


def _code(body):
    with pytest.raises(view.InputError) as e:
        view.validate(body)
    return e.value.code


# ---------- form_options ----------

def test_form_options_adds_other_entries_and_prefill():
    opts = view.form_options({"x": 1})
    assert opts["countries"][view.OTHER].startswith("Somewhere else")
    assert opts["countries"]["ID"] == "Indonesia"
    assert opts["exchanges"]["other"] == "Self-custody / other"
    assert opts["usdc_payers"] == ["dorahacks_usdc", "superteam_usdc"]
    assert opts["prefill"] == {"x": 1}
    assert view.form_options()["prefill"] is None


def test_input_error_carries_code_and_every_code_has_a_message():
    e = view.InputError("payer")
    assert e.code == "payer" and str(e) == "payer"
    for code in ("payer", "country", "amount_format", "amount_range", "chain", "exchange", "rails_dup", "rails_none"):
        assert view.INPUT_MESSAGES[code]


# ---------- validate ----------

def test_validate_rail_payer_happy_path():
    out = view.validate(_body(amount="1,234.567", rails=["payoneer", "wise"], question="  hello  "))
    assert out == {"payer": "devpost", "country": "ID", "amount": "1234.57", "rails": ["payoneer", "wise"],
                   "exchange": None, "question": "hello"}


def test_validate_question_truncated_to_500():
    assert len(view.validate(_body(question="x" * 900))["question"]) == 500


@pytest.mark.parametrize("body,code", [
    ({"payer": "nope"}, "payer"),
    ({"payer": None}, "payer"),
    ({"country": "XX"}, "country"),
    ({"country": ""}, "country"),
    ({"amount": "abc"}, "amount_format"),
    ({"amount": ""}, "amount_format"),
    ({"amount": "NaN"}, "amount_range"),
    ({"amount": "Infinity"}, "amount_range"),
    ({"amount": "0.99"}, "amount_range"),
    ({"amount": "1000000.01"}, "amount_range"),
    ({"rails": ["payoneer", "payoneer"]}, "rails_dup"),
    ({"rails": ["payoneer", "bitcoin"]}, "rails_dup"),
    ({"rails": ["payoneer", 5]}, "rails_dup"),
    ({"rails": "payoneer"}, "rails_dup"),
    ({"rails": []}, "rails_none"),
])
def test_validate_rejects_with_code(body, code):
    assert _code(_body(**body)) == code


def test_validate_amount_boundaries_accepted():
    assert view.validate(_body(amount="1"))["amount"] == "1.00"
    assert view.validate(_body(amount="1000000"))["amount"] == "1000000.00"


def test_validate_missing_rails_key_is_rails_none():
    body = _body()
    del body["rails"]
    assert _code(body) == "rails_none"


def test_validate_other_country_allowed():
    assert view.validate(_body(country=view.OTHER))["country"] == view.OTHER


def test_validate_usdc_payer_builds_usdc_rail_and_ignores_form_rails():
    out = view.validate(_body(payer="dorahacks_usdc", chain="solana", exchange="indodax", rails=["wise"]))
    assert out["rails"] == ["usdc:solana"]
    assert out["exchange"] == "indodax"


def test_validate_usdc_payer_defaults_exchange_to_other():
    out = view.validate(_body(payer="superteam_usdc", chain="base"))
    assert out["exchange"] == "other" and out["rails"] == ["usdc:base"]


def test_validate_usdc_payer_bad_chain():
    assert _code(_body(payer="dorahacks_usdc", chain="dogechain")) == "chain"
    assert _code(_body(payer="dorahacks_usdc")) == "chain"


def test_validate_usdc_payer_bad_exchange():
    assert _code(_body(payer="dorahacks_usdc", chain="base", exchange="binance")) == "exchange"


def test_validate_default_question_rails():
    out = view.validate(_body(question="   ", rails=["payoneer", "paypal"], amount="7000"))
    assert out["question"] == ("I live in Indonesia. Devpost is paying me $7,000.00. "
                               "The form offers: Payoneer, PayPal. Which option should I pick, what goes on the "
                               "tax form, and how much lands?")


def test_validate_default_question_unknown_country():
    out = view.validate(_body(country=view.OTHER, question=""))
    assert "I live in a country Cair has no sources for." in out["question"]


def test_validate_default_question_usdc_known_exchange():
    out = view.validate(_body(payer="dorahacks_usdc", chain="base", exchange="pintu", question=""))
    assert "DoraHacks (USDC) is paying me" in out["question"]
    assert "USDC on Base to Pintu" in out["question"]


def test_validate_default_question_usdc_self_custody():
    out = view.validate(_body(payer="superteam_usdc", chain="tron", question=""))
    assert "USDC on Tron (TRC-20) to my own wallet" in out["question"]


# ---------- _short ----------

def test_short():
    assert view._short(None) == ""
    assert view._short("") == ""
    assert view._short("https://a.io/x") == "a.io/x"
    assert view._short("no-scheme.io/x") == "no-scheme.io/x"
    long = "https://example.com/" + "a" * 100
    out = view._short(long)
    assert len(out) == 58 and out.endswith("…") and out.startswith("example.com/")
    exactly = "x" * 60
    assert view._short("https://" + exactly) == exactly


# ---------- card_view ----------

def _src(i, quote="q"):
    return {"source_id": i, "source_url": f"https://example.com/{i}", "accessed_at": "2026-10-10", "quote": quote,
            "page_date": "2026-01-01"}


def _card(**over):
    card = {
        "payer": "devpost", "country": "IN", "currency": "INR", "unit": "USD", "amount": "7000",
        "recommended": "payoneer",
        "rails": [{"rail": "payoneer", "name": "Payoneer", "source": _src("A")},
                  {"rail": "wise", "name": "Wise", "source": _src("A")},
                  {"rail": "paypal", "name": "PayPal", "source": None}],
        "w8ben": {"applies": "YES", "line10": "Article 21", "source": _src("W"), "article_source": _src("T")},
        "withholding": {"source": _src("H")},
        "landed": {"gross": "7000", "withheld": "700", "landed_usd": "6300", "upper_bound_usd": "6400",
                   "upper_bound_note": "n1", "landed_local": "609000", "upper_bound_local": "610000.5",
                   "upper_bound_local_note": "n2"},
        "fx": {"rate": "96.73", "as_of": "2026-10-09", "stale": False},
        "tool_calls": 7, "tools_used": ["a", "b"],
        "guardrail": [{"passed": False}, {"passed": True}],
        "recovery": [{"action": "x"}],
    }
    card.update(over)
    return card


def test_card_view_full_card():
    v = view.card_view(_card(), ["rail"], [])
    # footnotes are deduplicated: both rails share source A -> same number; paypal has no source -> None
    assert [r["fn"] for r in v["rails"]] == [1, 1, None]
    assert [r["recommended"] for r in v["rails"]] == [True, False, False]
    tools = [(n["tool"], n["id"]) for n in v["notes"]]
    assert tools == [("rail_eligibility", "A"), ("platform_rails", "W"), ("treaty_lookup", "T"),
                     ("treaty_lookup", "H"), ("your input", ""), ("fee_calc", ""), ("fx_quote", "")]
    assert v["w8_fn"] == 2 and v["l10_fn"] == 3 and v["wh_fn"] == 4
    assert v["landed"]["gross_fn"] == 5 and v["landed"]["calc_fn"] == 6 and v["landed"]["fx_fn"] == 7
    fx_note = v["notes"][6]
    assert fx_note["extra"] == "ECB reference rate via api.frankfurter.dev, as of 2026-10-09"
    assert "STALE" not in fx_note["extra"]
    assert v["notes"][0]["short"] == "example.com/A" and v["notes"][0]["page_date"] == "2026-01-01"
    ld = v["landed"]
    assert ld["gross"] == "$7,000.00" and ld["withheld"] == "$700.00" and ld["withheld_unclear"] is False
    assert ld["usd"] == "$6,300.00" and ld["usd_bound"] == "$6,400.00"
    assert ld["usd_bound_note"] == "n1" and ld["local_bound_note"] == "n2"
    assert ld["local"] == "INR 609,000.00" and ld["local_bound"] == "INR 610,000.50"
    assert v["usdc"] is False and v["gloss"] is False and v["networks"] == []
    assert v["confirmed"] == {"rail"} and v["confirmable"] == {"rail": "Payoneer", "line10": "Article 21"}
    assert v["rec_name"] == "Payoneer" and v["guard"] == {"passed": True} and v["guard_attempts"] == 2
    assert v["recovery"] == [{"action": "x"}] and v["tool_calls"] == 7 and v["tools_used"] == ["a", "b"]


def test_card_view_usdc_payer_networks_and_exchange_footnote_tool():
    card = _card(payer="dorahacks_usdc", country="ID", currency="IDR",
                 rails=[{"rail": "usdc:base", "name": "USDC on Base", "source": _src("E"),
                         "sourced_yes_networks": ["base", "mystery"]},
                        {"rail": "usdc:solana", "name": "USDC on Solana", "source": _src("F"),
                         "sourced_yes_networks": ["solana", "base"]}],
                 recommended="usdc:base")
    v = view.card_view(card, [], [])
    assert v["usdc"] is True and v["gloss"] is True
    assert v["notes"][0]["tool"] == "exchange_networks" and v["notes"][1]["tool"] == "exchange_networks"
    assert v["networks"] == sorted(["Base", "Solana", "mystery"])  # unknown network falls back to its raw key


def test_card_view_missing_optional_sections():
    card = _card(w8ben={"applies": "NO", "line10": UNCLEAR}, withholding={}, fx=None, guardrail=None,
                 recovery=None, tools_used=None, currency=None,
                 landed={"gross": None, "withheld": UNCLEAR}, recommended="nonexistent")
    v = view.card_view(card, [], [])
    assert v["w8_fn"] is None and v["l10_fn"] is None and v["wh_fn"] is None
    assert v["landed"]["fx_fn"] is None
    assert [n["tool"] for n in v["notes"]] == ["rail_eligibility", "your input", "fee_calc"]
    assert v["landed"]["gross"] == "7000 USD"  # no gross figure -> falls back to the raw amount
    assert v["landed"]["withheld"] is None and v["landed"]["withheld_unclear"] is True
    assert v["landed"]["usd"] is None and v["landed"]["local"] is None
    assert v["guard"] is None and v["guard_attempts"] == 0
    assert v["recovery"] == [] and v["tools_used"] == []
    assert v["rec_name"] is None and v["confirmable"] == {}
    assert v["fx"] == {}


def test_card_view_fx_unclear_or_missing_rate_has_no_footnote():
    for rate in (None, UNCLEAR):
        v = view.card_view(_card(fx={"rate": rate}), [], [])
        assert v["landed"]["fx_fn"] is None
        assert all(not n["tool"].startswith("fx_quote") for n in v["notes"])
    v = view.card_view(_card(fx={}), [], [])
    assert v["landed"]["fx_fn"] is None


def test_card_view_stale_fx_footnote():
    v = view.card_view(_card(fx={"rate": "96", "stale": True, "as_of": "2026-09-01"}), [], [])
    n = v["notes"][v["landed"]["fx_fn"] - 1]
    assert n["tool"] == "fx_quote_fallback"
    assert n["extra"].startswith("ECB reference rate via api.frankfurter.dev, as of 2026-09-01")
    assert "STALE" in n["extra"]


def test_card_view_money_formatting_by_unit():
    for unit, expect_gross in (("IDR", "IDR 7,000"), ("VND", "VND 7,000"), ("PHP", "PHP 7,000.00")):
        card = _card(unit=unit, landed={"gross": "7000"})
        assert view.card_view(card, [], [])["landed"]["gross"] == expect_gross


def test_card_view_empty_string_money_is_none():
    v = view.card_view(_card(landed={"gross": "", "landed_usd": ""}), [], [])
    assert v["landed"]["gross"] == "7000 USD" and v["landed"]["usd"] is None


def test_card_view_dedup_distinguishes_extra_and_tool():
    card = _card(rails=[{"rail": "payoneer", "name": "Payoneer", "source": _src("A")}],
                 w8ben={"applies": "YES", "line10": "BLANK", "source": _src("A"), "article_source": _src("A")},
                 withholding={"source": _src("A")})
    v = view.card_view(card, [], [])
    # same source id under different tools are distinct footnotes; same tool+id collapses
    assert [(n["tool"], n["id"]) for n in v["notes"][:3]] == [
        ("rail_eligibility", "A"), ("platform_rails", "A"), ("treaty_lookup", "A")]
    assert v["l10_fn"] == v["wh_fn"] == 3
    assert v["confirmable"]["line10"] == "leave blank"


def test_card_view_note_with_extra_only():
    # src=None but extra given -> entry built from empty defaults
    card = _card()
    v = view.card_view(card, [], [])
    note = next(n for n in v["notes"] if n["tool"] == "your input")
    assert note == {"tool": "your input", "id": "", "url": "", "short": "", "accessed": "", "quote": "",
                    "extra": "the amount you entered", "page_date": ""}


def test_card_view_stamps_receipts_without_mutating_input():
    r = {"mode": "full", "quoted": "6300", "landed": "6290", "error_pct": "0.2", "verdict": "OK", "label": "L"}
    v = view.card_view(_card(), [], [r])
    assert v["receipts"][0]["title"].startswith("LANDED · quoted 6300")
    assert r == {"mode": "full", "quoted": "6300", "landed": "6290", "error_pct": "0.2", "verdict": "OK", "label": "L"}


# ---------- confirmable ----------

def test_confirmable_cases():
    assert view.confirmable(_card()) == {"rail": "Payoneer", "line10": "Article 21"}
    assert view.confirmable(_card(recommended="none")) == {"line10": "Article 21"}
    unclear = _card(w8ben={"applies": "YES", "line10": UNCLEAR})
    assert view.confirmable(unclear) == {"rail": "Payoneer"}
    no = _card(w8ben={"applies": "NO", "line10": "BLANK"})
    assert view.confirmable(no) == {"rail": "Payoneer"}
    blank = _card(w8ben={"applies": "YES", "line10": "BLANK"})
    assert view.confirmable(blank)["line10"] == "leave blank"


# ---------- stamp_view ----------

def test_stamp_full():
    s = view.stamp_view({"mode": "full", "quoted": "100", "landed": "99", "error_pct": "1", "verdict": "OK",
                         "label": "lab", "evaluator_trace_id": "tid", "quote_source": "src"})
    assert s == {"title": "LANDED · quoted 100 · received 99 · Δ 1%", "verdict": "OK", "mode": "full", "label": "lab",
                 "partial": False, "trace": "tid", "source": "src"}


def test_stamp_full_falls_back_to_landed_amount_and_defaults():
    s = view.stamp_view({"mode": "full", "quoted": "100", "landed_amount": "98", "error_pct": "2"})
    assert s["title"] == "LANDED · quoted 100 · received 98 · Δ 2%"
    assert s["source"] == "" and s["trace"] is None and s["verdict"] is None


def test_stamp_partial_prefers_quoted_upper_and_unexplained_usd():
    s = view.stamp_view({"mode": "partial", "quoted_upper": "110", "quoted": "100", "landed": "90",
                         "unexplained_usd": "5", "unexplained": "9"})
    assert s["partial"] is True
    assert s["title"] == ("LANDED · at most 110 quoted · received 90 · 5 not explained by the sourced rules")


def test_stamp_partial_fallbacks():
    s = view.stamp_view({"mode": "partial", "quoted": "100", "landed_amount": "90", "unexplained": "9"})
    assert s["title"] == "LANDED · at most 100 quoted · received 90 · 9 not explained by the sourced rules"


def test_stamp_received_not_compared():
    s = view.stamp_view({"mode": "received", "landed": "50", "currency": "IDR"})
    assert s["title"] == "RECEIVED · 50 IDR · not compared" and s["partial"] is False
    s = view.stamp_view({"landed_amount": "50", "landed_currency": "PHP"})
    assert s["title"] == "RECEIVED · 50 PHP · not compared" and s["mode"] is None


# ---------- rules_rows / band ----------

def test_rules_rows_join_quotes_and_truncate(monkeypatch, tmp_path):
    csv_path = tmp_path / "rules_sheet.csv"
    csv_path.write_text("country,source_id,source_url\nID,S1,https://example.com/a\nIN,S2,https://example.com/b\n")
    monkeypatch.setattr(config, "DATA", tmp_path)
    sheet = rules.Sheet(facts={}, quotes={"S1": {"quote": "z" * 400}}, version="t")
    rows = view.rules_rows(sheet)
    assert [r["source_id"] for r in rows] == ["S1", "S2"]
    assert rows[0]["quote"] == "z" * 300 and rows[0]["short"] == "example.com/a"
    assert rows[1]["quote"] == ""  # no matching quote -> empty, not an error
    assert rows[0]["country"] == "ID"


def test_rules_rows_real_sheet_has_a_row_per_csv_line():
    rows = view.rules_rows(rules.load())
    assert rows and all("short" in r and "quote" in r for r in rows)


@pytest.mark.parametrize("amount,expected", [
    ("0", "< $1k"), ("999.99", "< $1k"), ("1000", "$1k–5k"), ("5000", "$1k–5k"), ("5000.01", "> $5k"),
])
def test_band(amount, expected):
    assert view.band(amount) == expected


# ---------- verify_rows ----------

def _plan(i, trace="t" * 32, guard=None, **card_extra):
    card = {"guardrail": guard if guard is not None else [], "tool_calls": 4, "recommended": "payoneer",
            "unclear": ["a", "b"], "recovery": [{"action": "retry"}, {"note": "x"}]}
    card.update(card_extra)
    return {"id": f"plan-{i:08d}", "created_at": "2026-10-10", "payer": "devpost", "country": "ID",
            "amount_usd": "7000", "end_user_hash": "abcdef0123456789", "origin": "web", "trace_id": trace,
            "card_json": json.dumps(card)}


def test_verify_rows_readback_success(monkeypatch):
    calls = []

    def mcp(cs, timeout):
        calls.append((cs, timeout))
        return [{"span_count": 3, "spans": [{"name": "plan", "type": "agent", "status": "ok", "duration_ms": 12.6},
                                            {"name": "tool", "type": "tool", "status": None, "duration_ms": None}]}]

    monkeypatch.setattr(view.neat, "mcp", mcp)
    rows, source = view.verify_rows([_plan(1, guard=[{"passed": False}, {"passed": True}])])
    assert calls == [([("get_trace_context", {"trace_id": "t" * 32})], 45)]
    assert source == "Read back from neatlogs (MCP get_trace_context)"
    r = rows[0]
    assert r["plan"] == "00000001" and r["user"] == "abcdef01" and r["band"] == "> $5k"
    assert r["guardrail"] == "PASSED" and r["attempts"] == 2
    assert r["spans"] == [{"name": "plan", "kind": "agent", "status": "ok", "ms": 13},
                          {"name": "tool", "kind": "tool", "status": None, "ms": 0}]
    assert r["readback"] is True and r["span_count"] == 3
    assert r["db_tool_calls"] == 4 and r["db_route"] == "payoneer" and r["db_unclear"] == 2 and r["recoveries"] == 1
    assert "amount" not in r and "card_json" not in r  # redacted projection


def test_verify_rows_blocked_guardrail_and_no_guardrail(monkeypatch):
    monkeypatch.setattr(view.neat, "mcp", lambda cs, timeout: [{"spans": []}, {"spans": []}])
    rows, _ = view.verify_rows([_plan(1, trace="a" * 32, guard=[{"passed": False}]),
                                _plan(2, trace="b" * 32, guard=None)])
    assert rows[0]["guardrail"] == "BLOCKED" and rows[1]["guardrail"] == "—"
    assert rows[1]["attempts"] == 0


def test_verify_rows_no_trace_ids_skips_mcp(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("mcp must not be called")

    monkeypatch.setattr(view.neat, "mcp", boom)
    rows, source = view.verify_rows([_plan(1, trace=None, recommended=None, unclear=None)])
    assert source == "Read back from neatlogs (MCP get_trace_context)"
    r = rows[0]
    assert r["readback"] is False and r["span_count"] is None and r["spans"] == [] and r["trace"] is None
    assert r["db_route"] == "none" and r["db_unclear"] == 0 and r["recoveries"] == 1


def test_verify_rows_empty_plans(monkeypatch):
    monkeypatch.setattr(view.neat, "mcp", lambda *a, **k: pytest.fail("no call expected"))
    assert view.verify_rows([]) == ([], "Read back from neatlogs (MCP get_trace_context)")


def test_verify_rows_mcp_failure_falls_back_to_db_copy(monkeypatch):
    def mcp(cs, timeout):
        raise TimeoutError("slow")

    monkeypatch.setattr(view.neat, "mcp", mcp)
    rows, source = view.verify_rows([_plan(1)])
    assert source == "DB copy — neatlogs read-back unavailable right now"
    assert rows[0]["readback"] is False and rows[0]["spans"] == [] and rows[0]["db_tool_calls"] == 4


def test_verify_rows_ignores_non_dict_results_and_partial_results(monkeypatch):
    # second call errored (string result); third has no result at all (zip(strict=False) truncates)
    monkeypatch.setattr(view.neat, "mcp", lambda cs, timeout: [{"spans": [{"name": "s"}], "span_count": 1}, "error"])
    rows, source = view.verify_rows([_plan(1, trace="a" * 32), _plan(2, trace="b" * 32), _plan(3, trace="c" * 32)])
    assert source.startswith("Read back")
    assert [r["readback"] for r in rows] == [True, False, False]
    assert rows[0]["spans"] == [{"name": "s", "kind": None, "status": None, "ms": 0}]


def test_verify_rows_empty_ctx_dict_is_not_readback(monkeypatch):
    monkeypatch.setattr(view.neat, "mcp", lambda cs, timeout: [{}])
    rows, _ = view.verify_rows([_plan(1)])
    assert rows[0]["readback"] is False and rows[0]["span_count"] is None
