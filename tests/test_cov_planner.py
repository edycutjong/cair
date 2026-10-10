"""Line + branch coverage for cair/planner.py: recovery paths, guardrail failure modes and card rendering. No network."""
import copy

import pytest

from cair import llm, planner, rules, tools

HERO = dict(plan_id="t-cov", payer="devpost", country="ID", amount_usd=7000,
            rails_offered=["payoneer", "paypal", "wise"], exchange=None, question="Which one?", origin="eval")
OK_TEXT = "Use Payoneer. Wise is refused because Indonesian addresses can no longer hold money. Line 10 stays blank."
USDC = dict(HERO, payer="dorahacks_usdc", rails_offered=["usdc:ethereum"], exchange="indodax", amount_usd=1000)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(planner.time, "sleep", lambda s: None)


def run(**kw):
    return planner.run(**{**HERO, **kw})


@pytest.fixture
def hero_card(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    return run()["card"]


# ---------- Attempts ----------

def test_attempts_retries_once_then_succeeds():
    att = planner.Attempts()
    seen = []

    def flaky(x):
        seen.append(x)
        if len(seen) == 1:
            raise ValueError("boom")
        return x * 2

    assert att.call("t", flaky, 21) == 42
    assert att.calls == ["t", "t"]
    assert att.log == [{"tool": "t", "attempt": 1, "error": "ValueError: boom"}]


def test_attempts_failing_twice_without_fallback_logs_unclear():
    att = planner.Attempts()

    def bad():
        raise RuntimeError("x" * 500)

    assert att.call("t", bad) is None
    assert [e.get("attempt") for e in att.log] == [1, 2, None]
    assert len(att.log[0]["error"]) == 300
    assert att.log[-1] == {"tool": "t", "action": "UNCLEAR"}


def test_attempts_failing_twice_uses_fallback_with_last_error():
    att = planner.Attempts()

    def bad():
        raise KeyError("k")

    assert att.call("t", bad, fallback=lambda err: ("fb", err)) == ("fb", "KeyError: 'k'")
    assert att.log[-1] == {"tool": "t", "action": "fallback"}


# ---------- tool failures inside the planner ----------

def test_platform_rails_down_makes_w8ben_unclear(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = run(fail="platform_rails")["card"]
    assert card["w8ben"]["applies"] == rules.UNCLEAR and card["w8ben"]["source"] is None
    assert "w8ben" in card["unclear"]
    assert {"tool": "platform_rails", "action": "UNCLEAR"} in card["recovery"]
    assert "platform_rails" in card["tools_used"]
    assert not any(o.get("w8ben_source") for o in card["tool_outputs"])
    assert "no primary source says whether this payer needs a W-8BEN" in card["text"]


def test_treaty_lookup_down_leaves_line10_unclear(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = run(fail="treaty_lookup")["card"]
    assert card["w8ben"]["applies"] == "YES" and card["w8ben"]["line10"] == rules.UNCLEAR
    assert card["w8ben"]["line10_why"] == "the treaty lookup failed twice"
    assert card["w8ben"]["nearest_articles"] == [] and card["w8ben"]["article_source"] is None
    assert card["withholding"]["rate"] == rules.UNCLEAR and card["withholding"]["source"] is None
    assert {"tool": "treaty_lookup", "action": "UNCLEAR"} in card["recovery"]
    assert not any("nearest" in o for o in card["tool_outputs"])


def test_rail_eligibility_down_leaves_rails_unclear(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = run(fail="rail_eligibility")["card"]
    assert [r["verdict"] for r in card["rails"]] == [rules.UNCLEAR] * 3
    assert all(r["source"] is None and r["note"] == "eligibility check failed twice" for r in card["rails"])
    assert card["recommended"] is None and "route" in card["unclear"]
    assert "RECOMMENDED RAIL: UNCLEAR" in card["text"]
    assert not any(o.get("rail") for o in card["tool_outputs"])


def test_exchange_networks_down_leaves_usdc_rail_unclear(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = planner.run(**{**USDC, "fail": "exchange_networks"})["card"]
    (rail,) = card["rails"]
    assert rail["verdict"] == rules.UNCLEAR and rail["source"] is None
    assert rail["note"] == "network check failed twice" and rail["sourced_yes_networks"] == []
    assert card["recommended"] is None
    assert {"tool": "exchange_networks", "action": "UNCLEAR"} in card["recovery"]
    assert not any("sourced_yes_networks" in o for o in card["tool_outputs"])


def test_fee_calc_down_leaves_landed_unclear(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = run(fail="fee_calc")["card"]
    assert card["landed"] == {"landed_usd": rules.UNCLEAR, "landed_local": rules.UNCLEAR, "withheld": rules.UNCLEAR}
    assert {"landed", "landed_local"} <= set(card["unclear"])
    assert not any(o.get("tool") == "fee_calc" for o in card["tool_outputs"])
    assert "LANDED (USD): UNCLEAR" in card["text"]


def test_fx_fallback_returning_nothing_adds_no_output(fixed_fx, llm_says, monkeypatch):
    llm_says(OK_TEXT)
    monkeypatch.setattr(tools, "fx_quote_fallback", lambda ccy, err: None)
    card = run(fail="fx_quote")["card"]
    assert card["fx"] is None
    assert "FX:" not in card["text"]
    assert {"tool": "fx_quote", "action": "fallback"} in card["recovery"]
    assert not any(o.get("quote") == "IDR" for o in card["tool_outputs"])


def test_fx_fallback_serves_stale_cached_rate(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    run()  # a live fetch seeds the snapshot
    card = run(fail="fx_quote")["card"]
    assert card["fx"]["stale"] is True and card["fx"]["rate"] == "17881"
    assert "STALE" in card["text"]


# ---------- explain(): guardrail switch and failing checker ----------

def test_guardrail_disabled_returns_unchecked_text(fixed_fx, llm_says):
    llm_says("Anything goes: you will receive $1.")
    card = run(guardrail=False)["card"]
    assert card["explanation"] == "Anything goes: you will receive $1."
    assert card["explanation_source"] == "llm (guardrail disabled: ablation)"
    assert card["guardrail"] == []


def test_guardrail_exception_blocks_and_falls_back_to_template(fixed_fx, llm_says, monkeypatch):
    llm_says(OK_TEXT)

    def boom(*a, **k):
        raise TimeoutError("checker down")

    monkeypatch.setattr(planner, "guardrail_run", boom)
    card = run()["card"]
    assert card["explanation_source"] == "template"
    assert [v["attempt"] for v in card["guardrail"]] == [1, 2]
    for v in card["guardrail"]:
        assert v["passed"] is False and v["score"] == 0.0
        assert v["claims"] == ["guardrail error: TimeoutError"]
        assert v["violation_classes"] == ["guardrail_error"]
    assert {"tool": "llm_explain", "action": "template explanation from tool outputs"} in card["recovery"]
    assert card["explanation"] == planner.template_explanation(card)


def test_blocked_text_is_retried_with_problems_and_echoed_figure(fixed_fx, monkeypatch):
    seen = []
    texts = iter(["bad one", OK_TEXT])

    def chat(messages, temperature=0.0, max_tokens=700):
        seen.append(copy.deepcopy(messages))
        return next(texts)

    verdicts = iter([
        {"passed": False, "score": 0.1, "unsourced": ["$9"], "claims": ["no"], "violation_classes": ["x"],
         "echoed_from_question": ["$9", "40%"], "attempt": 1},
        {"passed": True, "score": 1.0, "unsourced": [], "claims": [], "violation_classes": [], "attempt": 2}])
    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(planner, "guardrail_run", lambda *a, **k: next(verdicts))
    card = run()["card"]
    assert card["explanation"] == OK_TEXT and card["explanation_source"] == "llm"
    retry_msgs = seen[1]
    assert retry_msgs[-2] == {"role": "assistant", "content": "bad one"}
    retry = retry_msgs[-1]["content"]
    assert "blocked by the provenance check: $9; no" in retry
    assert "$9, 40% came from the user's question" in retry
    assert len(seen[0]) == 2  # first call: system + user only


def test_blocked_without_echo_omits_echo_sentence(fixed_fx, monkeypatch):
    seen = []

    def chat(messages, temperature=0.0, max_tokens=700):
        seen.append(copy.deepcopy(messages))
        return "text"

    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(planner, "guardrail_run", lambda *a, **k: {
        "passed": False, "score": 0.0, "unsourced": [], "claims": ["c"], "violation_classes": [], "attempt": 1})
    card = run()["card"]
    assert card["explanation_source"] == "template" and len(seen) == 2
    assert "came from the user's question" not in seen[1][-1]["content"]


def test_llm_error_goes_straight_to_template(fixed_fx, llm_says):
    llm_says(raises=ConnectionError("down"))
    card = run()["card"]
    assert card["explanation_source"] == "template"
    assert card["guardrail"] == []
    err = [e for e in card["recovery"] if e.get("tool") == "llm_explain" and "error" in e]
    assert err == [{"tool": "llm_explain", "attempt": 1, "error": "ConnectionError: down"}]


def test_unknown_country_skips_llm(fixed_fx, monkeypatch):
    def chat(*a, **k):
        raise AssertionError("LLM must not be called")

    monkeypatch.setattr(llm, "chat", chat)
    card = run(country="ZZ")["card"]
    assert card["explanation_source"] == "template"
    assert card["guardrail"][0]["reason"] == "no_source"
    assert card["country_name"] == "a country not in the rules sheet"


# ---------- build_card branches ----------

def _tr(**kw):
    return {"other_income_article": "NONE", "withholding_default": "30%", "treaty_text_indexed": True,
            "has_article_titled_other_income": False, "article_source": None, "withholding_source": None,
            "nearest": [], **kw}


def build(w8, tr=None, fc=None, recommended="payoneer", payer="devpost", country="ID"):
    rails = [{"rail": "payoneer", "name": "Payoneer", "verdict": "DELIVERS", "source": None, "note": None}]
    return planner.build_card("p", payer, country, "7000", None, rails, recommended, {"w8ben_source": {"u": 1}},
                              tr, None, fc, w8)


def test_build_card_article_number_goes_on_line10():
    card = build("YES", _tr(other_income_article="21"))
    assert card["w8ben"]["line10"] == "ARTICLE 21"
    assert card["w8ben"]["line10_why"] == "a sourced article covers this income"
    assert card["withholding"]["rate"] == "30%" and card["unclear"] == ["landed", "landed_local"]  # no fee_calc passed


def test_build_card_blank_line10_reasons():
    assert "no Other Income article" in build("YES", _tr())["w8ben"]["line10_why"]
    off = build("YES", _tr(treaty_text_indexed=False))["w8ben"]["line10_why"]
    assert off == "this country is not on the IRS list of US income tax treaties"


def test_build_card_unclear_article_reasons():
    failed = build("YES", None)
    assert failed["w8ben"]["line10_why"] == "the treaty lookup failed twice"
    assert failed["withholding"]["rate"] == rules.UNCLEAR and {"line10", "withholding"} <= set(failed["unclear"])
    titled = build("YES", _tr(other_income_article=rules.UNCLEAR, has_article_titled_other_income=True))
    assert "exists but no source says it covers a prize" in titled["w8ben"]["line10_why"]
    nodata = build("YES", _tr(other_income_article=rules.UNCLEAR))
    assert nodata["w8ben"]["line10_why"] == "Cair has no sourced treaty data for this country"


def test_build_card_w8ben_not_needed():
    card = build("NO", _tr(), fc={"landed_usd": "1", "landed_local": "2", "withheld": "0"})
    assert card["w8ben"]["line10"] == "NOT NEEDED"
    assert card["withholding"]["rate"] == "NONE"
    assert card["withholding"]["source"] is None
    assert card["unclear"] == []


def test_build_card_w8ben_unclear():
    card = build(rules.UNCLEAR, _tr())
    assert card["w8ben"]["line10"] == rules.UNCLEAR and "w8ben" in card["unclear"]


def test_build_card_known_landed_figures_are_not_unclear():
    fc = {"landed_usd": "4900.00", "landed_local": "87616900", "withheld": "2100.00"}
    card = build("YES", _tr(), fc=fc)
    assert card["landed"] == fc and card["withholding"]["amount"] == "2100.00"
    assert "landed" not in card["unclear"] and "landed_local" not in card["unclear"]


def test_build_card_usdc_never_flags_landed_local():
    fc = {"landed_usd": "10", "landed_local": rules.UNCLEAR, "withheld": "0"}
    card = build("NO", None, fc=fc, payer="dorahacks_usdc")
    assert card["unit"] == "USDC" and "landed_local" not in card["unclear"]


def test_build_card_without_route_flags_route():
    assert "route" in build("NO", None, recommended=None)["unclear"]


# ---------- template_explanation ----------

def test_template_with_nothing_unclear_has_no_unclear_sentence():
    card = build("YES", _tr(other_income_article="21"), fc={"landed_usd": "1", "landed_local": "2", "withheld": "0"})
    text = planner.template_explanation(card)
    assert text.startswith("Payoneer is the offered route with a sourced DELIVERS for Indonesia.")
    assert "UNCLEAR" not in text.split("W-8BEN line 10:")[0] and "no primary source states them" not in text
    assert "W-8BEN line 10: ARTICLE 21 (a sourced article covers this income)." in text


def test_template_lists_refused_rails_and_unclear_labels():
    card = build("YES", None, recommended=None)
    card["rails"].append({"rail": "wise", "name": "Wise", "verdict": "REFUSED", "source": None, "note": None})
    text = planner.template_explanation(card)
    assert "None of the offered routes has a sourced DELIVERS, so Cair does not pick one." in text
    assert "Wise is refused: its own page rules it out." in text
    assert text.endswith("UNCLEAR: what lands in USD, what lands in local currency, W-8BEN line 10, "
                         "which option to pick, the withholding rate — no primary source states them.")
    card["unclear"] = ["mystery"]
    assert "UNCLEAR: mystery" in planner.template_explanation(card)


# ---------- render_text ----------

def test_render_text_without_explanation_omits_it(hero_card):
    card = copy.deepcopy(hero_card)
    card["explanation"] = ""
    text = planner.render_text(card)
    assert OK_TEXT not in text and "\n\n\nRECOMMENDED" not in text
    assert "\n\nRECOMMENDED RAIL: Payoneer\n" in text
    assert OK_TEXT in planner.render_text(hero_card)


def test_render_text_shows_known_landed_amounts(hero_card):
    card = copy.deepcopy(hero_card)
    card["landed"] = {"landed_usd": "4900", "landed_local": "87616900", "withheld": "2100"}
    card["withholding"]["amount"] = "2100"
    lines = planner.render_text(card).splitlines()
    assert "LANDED (USD): $4,900.00" in lines
    assert "LANDED (LOCAL): IDR 87,616,900" in lines
    assert "WITHHOLDING: 30% ($2,100.00)" in lines


def test_render_text_upper_bounds_when_landed_unclear(hero_card):
    card = copy.deepcopy(hero_card)
    card["landed"] = {"landed_usd": rules.UNCLEAR, "landed_local": rules.UNCLEAR, "upper_bound_usd": "4900",
                      "upper_bound_note": "(before fees)", "upper_bound_local": "87616900",
                      "upper_bound_local_note": "(before FX margin)"}
    lines = planner.render_text(card).splitlines()
    assert "LANDED (USD): UNCLEAR — at most $4,900.00 (before fees)" in lines
    assert "LANDED (LOCAL): UNCLEAR — at most IDR 87,616,900 (before FX margin)" in lines


def test_render_text_unclear_line10_and_no_networks_for_usdc(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = planner.run(**USDC)["card"]
    text = card["text"]
    assert "Send a small test transaction first" in text
    assert "- Networks this exchange's own pages confirm for USDC: BNB Smart Chain (BEP-20), Base, Ethereum (ERC-20)" in text
    assert "W-8BEN LINE 10: UNCLEAR (no primary source says whether this payer needs a W-8BEN)" in text
    assert card["unit"] == "USDC" and "1000 USDC from DoraHacks (USDC)" in text


def test_render_text_usdc_confirmed_networks_listed(hero_card):
    card = copy.deepcopy(hero_card)
    card["payer"] = "dorahacks_usdc"
    card["rails"] = [{"rail": "usdc:base", "name": "x", "verdict": "DELIVERS", "source": None,
                      "sourced_yes_networks": ["base", "unknown-net"]}]
    text = planner.render_text(card)
    assert "Networks this exchange's own pages confirm for USDC: Base, unknown-net." in text


def test_render_text_line10_variants():
    base = {"plan_id": "p", "exchange": None}
    for line10, expected in [("BLANK", "W-8BEN LINE 10: BLANK (why)"), ("NOT NEEDED", "W-8BEN LINE 10: NOT NEEDED"),
                             ("ARTICLE 7", "W-8BEN LINE 10: ARTICLE 7"), (rules.UNCLEAR, "W-8BEN LINE 10: UNCLEAR (why)")]:
        card = build("YES", _tr(other_income_article="7"), fc={"landed_usd": "1", "landed_local": "1", "withheld": "0"})
        card.update(base, explanation="", text="")
        card["w8ben"].update(line10=line10, line10_why="why")
        assert expected in planner.render_text(card).splitlines()


def test_render_text_no_rails_and_no_source_marker():
    card = build("NO", None, recommended=None)
    card["rails"] = []
    card["explanation"] = ""
    text = planner.render_text(card)
    assert "RECOMMENDED RAIL: NONE" in text
    card["rails"] = [{"rail": "payoneer", "name": "Payoneer", "verdict": "DELIVERS", "source": None}]
    assert "- Payoneer: DELIVERS [no primary source]" in planner.render_text(card)


# ---------- helpers ----------

def test_money_formats_by_unit():
    assert planner._money(None, "USD") == rules.UNCLEAR
    assert planner._money(rules.UNCLEAR, "IDR") == rules.UNCLEAR
    assert planner._money("1234.5", "USD") == "$1,234.50"
    assert planner._money("1234.567", "IDR") == "IDR 1,235"
    assert planner._money("1234.567", "PHP") == "PHP 1,234.57"


def test_strip_summary_drops_label_lines():
    label = next(iter(planner.FIELDS.values()))
    text = f"Keep this.\n**{label.upper()}**: x\n- {label}: y\nAnd this."
    assert planner.strip_summary(text) == "Keep this.\nAnd this."


def test_language_empty_question_is_english():
    assert planner.language("") == "English"
    assert planner.language("1234 $$") == "English"


def test_facts_for_llm_formats_amounts_and_usdc_networks(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    card = run()["card"]
    facts = planner._facts_for_llm(card)
    assert facts["fx"]["rate"] == "1 USD = 17,881 IDR"
    assert facts["recommended"] == "Payoneer" and facts["amount"] == "7000 USD"
    usdc = planner.run(**USDC)["card"]
    facts = planner._facts_for_llm(usdc)
    assert facts["always"].startswith("Send a small test transaction")
    assert "networks_this_exchange_accepts_sourced" in facts
    card["fx"] = {"rate": rules.UNCLEAR, "as_of": None, "stale": True, "quote": "IDR"}
    assert planner._facts_for_llm(card)["fx"]["rate"] == rules.UNCLEAR


def test_run_returns_trace_usage_and_origin(fixed_fx, llm_says):
    llm_says(OK_TEXT)
    out = run(session_id="s1", end_user_id="u1")
    assert set(out) == {"text", "tool_outputs", "trace_id", "guardrail", "recovery", "llm_usage", "card"}
    assert out["card"]["origin"] == "eval" and out["text"] == out["card"]["text"]
    assert out["llm_usage"]["calls"] == 0  # llm.chat is stubbed, so nothing records usage
    assert tools.FORCE_FAIL.get() is None and llm.USAGE.get() is not out["llm_usage"]
