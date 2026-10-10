"""Line + branch coverage for cair/guardrail.py: the provenance checks that block an unsourced or over-promising explanation."""
from cair import guardrail

OUT = [{"gross": "7000.00", "withheld": "2100.00", "rate": "17881", "withholding_default": "30", "fx_margin_pct": "0.5",
        "article": 12}]


def card(rails=None, line10="ARTICLE 12", rate="30%", landed=None):
    return {"payer": "Acme", "country": "ID",
            "rails": rails if rails is not None else [{"rail": "payoneer", "verdict": "YES"},
                                                       {"rail": "wise", "verdict": "REFUSED"},
                                                       {"rail": "paypal", "verdict": "YES"}],
            "w8ben": {"line10": line10}, "withholding": {"rate": rate}, "landed": landed}


def test_clean_explanation_passes_with_full_score():
    v = guardrail.check("Use Payoneer. Wise is refused. The withholding rate is 30% of $7,000.00.", OUT, card())
    assert v["passed"] and v["score"] == 1.0 and v["figures"] == 2
    assert v["unsourced"] == [] and v["claims"] == [] and v["violation_classes"] == []


def test_no_figures_scores_one():
    v = guardrail.check("Use Payoneer.", OUT, card())
    assert v["passed"] and v["score"] == 1.0 and v["figures"] == 0


def test_share_of_a_sourced_amount_keeps_a_percentage_sourced():
    # no tax/rate word: the pct only counts because "of $7,000.00" carries a sourced money figure
    v = guardrail.check("That is 30% of $7,000.00.", OUT, card())
    assert v["passed"] and v["unsourced"] == []


def test_sourced_percentage_without_rate_context_is_unsourced():
    v = guardrail.check("Payoneer charges 30%.", OUT, card())
    assert not v["passed"] and v["unsourced"] == ["30%"]
    assert v["violation_classes"] == ["unsourced_figure"] and v["score"] == 0.0


def test_share_of_an_unsourced_amount_does_not_rescue_a_percentage():
    v = guardrail.check("That is 30% of $9,999.00.", OUT, card())
    assert sorted(v["unsourced"]) == ["$9,999.00", "30%"]


def test_unsourced_figure_echoed_from_question_is_reported_as_echo():
    v = guardrail.check("Your $5,000.00 is fine.", OUT, card(), question="I will get $5,000.00 from Acme")
    assert v["unsourced"] == ["$5,000.00"] and v["echoed_from_question"] == ["$5,000.00"]
    v = guardrail.check("Your $5,000.00 is fine.", OUT, card(), question="no amounts here")
    assert v["unsourced"] == ["$5,000.00"] and v["echoed_from_question"] == []


def test_neighbouring_article_numbers_are_allowed_when_a_sourced_article_exists():
    v = guardrail.check("The nearest articles are 12 and 15 for this case.", OUT, card(line10="ARTICLE 12"))
    assert v["unsourced"] == ["15"]  # 12 is the sourced article; 15 is not in the pool
    out = [{"article": 15}]
    ok = guardrail.check("Check the nearest articles (15, 16 and 17).", out, card())
    assert ok["unsourced"] == ["16", "17"]  # only the sourced article number is accepted in "articles" context
    ok2 = guardrail.check("See article 15 and also 15 here.", out, card())
    assert ok2["unsourced"] == []


def test_bare_number_in_article_context_matches_sourced_article():
    v = guardrail.check("The nearest articles cover 15 only.", [{"article": 15}], card())
    assert v["passed"] and v["unsourced"] == []
    v = guardrail.check("The nearest articles cover 15.5 only.", [{"article": 15}], card())
    assert v["unsourced"] == ["15.5"]  # non-integral value never rescued by the article pool


def test_endorsing_a_refused_rail_is_blocked_but_refusing_it_is_not():
    bad = guardrail.check("Go with Wise.", OUT, card())
    assert not bad["passed"] and bad["violation_classes"] == ["refused_rail"]
    assert bad["claims"][0].startswith("names refused wise without refusing it")
    assert guardrail.check("Wise is refused.", OUT, card())["passed"]


def test_follow_up_reference_to_a_refused_rail_is_blocked():
    v = guardrail.check("Wise is refused for this payer. Go with it anyway.", OUT, card(rails=[
        {"rail": "wise", "verdict": "REFUSED"}]))
    assert v["violation_classes"] == ["refused_rail"]
    assert any(c.startswith("endorses the refused rail by reference") for c in v["claims"])


def test_follow_up_naming_another_checked_rail_is_not_a_reference_to_the_refused_one():
    v = guardrail.check("Wise is refused. Use Payoneer instead of that.", OUT, card())
    assert v["passed"]


def test_unclear_rail_recommendation_is_blocked_and_flagged_as_unclear():
    c = card(rails=[{"rail": "payoneer", "verdict": "UNCLEAR"}, {"rail": "wise", "verdict": "REFUSED"}])
    v = guardrail.check("Use Payoneer.", OUT, c)
    assert v["violation_classes"] == ["unclear_rail"]
    assert v["claims"] == ["recommends payoneer, whose deliverability is UNCLEAR: Use Payoneer."]
    assert guardrail.check("Payoneer is UNCLEAR for this payer.", OUT, c)["passed"]


def test_rail_the_plan_never_checked_cannot_be_recommended():
    v = guardrail.check("Try Skrill instead.", OUT, card())
    assert v["violation_classes"] == ["unclear_rail"]
    assert v["claims"] == ["recommends skrill, which this plan did not check: Try Skrill instead."]
    # a chain USDC network the tools did not confirm is also unchecked ...
    v = guardrail.check("Send it on Tron.", OUT, card())
    assert v["violation_classes"] == ["unclear_rail"] and "usdc:tron" in v["claims"][0]
    # ... unless a tool confirmed it
    c = card(rails=[{"rail": "payoneer", "verdict": "YES", "sourced_yes_networks": ["tron"]}])
    assert guardrail.check("Send it on Tron.", OUT, c)["passed"]


def test_article_on_line_10_while_tools_say_blank_is_blocked():
    c = card(line10="BLANK")
    v = guardrail.check("Put Article 12 on line 10.", [{"article": 12}], c)
    assert v["violation_classes"] == ["line10"]
    assert v["claims"][0].startswith("article on line 10 while the tools say BLANK")
    assert guardrail.check("Line 10 stays blank, no article applies.", OUT, c)["passed"]
    assert guardrail.check("I won't put Article 12 on line 10.", OUT, c)["passed"]


def test_treaty_article_presented_as_applying_while_line_10_is_blank():
    c = card(line10="UNCLEAR")
    v = guardrail.check("Claim Article 12 on your form.", [{"article": 12}], c)
    assert v["violation_classes"] == ["line10"]
    assert v["claims"] == ["treaty article presented as applying while the tools say UNCLEAR: "
                           "Claim Article 12 on your form."]
    assert guardrail.check("The nearest article is Article 12.", [{"article": 12}], c)["passed"]
    # with a sourced line-10 article, claiming it is fine
    assert guardrail.check("Claim Article 12 on your form.", [{"article": 12}], card(line10="ARTICLE 12"))["passed"]


def test_withholding_rate_must_match_the_tools():
    v = guardrail.check("The withholding is 15%.", [{"withholding_default": "15"}], card(rate="30%"))
    assert v["violation_classes"] == ["withholding"]
    assert v["claims"][0].startswith("withholding 15% while the tools say 30%")
    assert guardrail.check("The withholding is 30%.", OUT, card(rate="30%"))["passed"]


def test_withholding_rate_with_margin_word_is_not_a_withholding_claim():
    v = guardrail.check("The conversion margin is 0.5% on the tax estimate.", OUT, card(rate="30%"))
    assert v["claims"] == []


def test_withholding_while_tax_position_is_unclear_may_only_say_unclear():
    c = card(rate="UNCLEAR")
    ok = guardrail.check("The withholding is UNCLEAR, not 30%.", OUT, c)
    assert ok["passed"] and ok["claims"] == []  # saying UNCLEAR is the only allowed statement
    bad = guardrail.check("The withholding is 30%.", OUT, c)
    assert bad["violation_classes"] == ["withholding"]
    assert bad["claims"][0].startswith("withholding 30% while the tools say UNCLEAR")


def test_tax_position_the_tools_did_not_produce_is_blocked():
    v = guardrail.check("No withholding applies.", OUT, card())
    assert v["violation_classes"] == ["withholding"]
    assert v["claims"] == ["tax position the tools did not produce (they say 30%): No withholding applies."]
    assert guardrail.check("It is tax-free, which the tools cannot say.", OUT, card())["passed"]
    assert guardrail.check("Whether you are tax-free is UNCLEAR.", OUT, card())["passed"]


def test_unclear_landed_amount_cannot_be_presented_as_what_lands():
    c = card(landed={"landed_usd": "UNCLEAR", "gross": "7000.00", "withheld": "2100.00"})
    v = guardrail.check("You will receive $4,900.00 in your bank.", [{"gross": "7000.00", "after_withholding": "4900.00"}], c)
    assert v["violation_classes"] == ["unclear_upgraded"]
    assert v["claims"][0].startswith("$4,900.00 stated as what lands while it is UNCLEAR")
    # the gross, named as such, and bounded/purpose sentences are not promises
    assert guardrail.check("You get gross $7,000.00 before tax.", OUT, c)["passed"]
    assert guardrail.check("You receive at most $4,900.00.", [{"gross": "4900.00"}], c)["passed"]
    assert guardrail.check("To receive $7,000.00, use Payoneer.", OUT, c)["passed"]
    assert guardrail.check("You can receive funds on Payoneer.", OUT, c)["passed"]  # no money figure at all


def test_unclear_landed_with_a_non_gross_amount_in_a_gross_sentence_is_still_blocked():
    c = card(landed={"landed_usd": "UNCLEAR", "gross": "7000.00", "withheld": None})
    v = guardrail.check("You get $7,000.00 gross and $1,234.00 net.", [{"gross": "7000.00", "amount": "1234.00"}], c)
    assert v["violation_classes"] == ["unclear_upgraded"]


def test_resolved_landed_amount_may_be_stated():
    c = card(landed={"landed_usd": "4900.00", "gross": "7000.00", "withheld": "2100.00"})
    assert guardrail.check("You will receive $4,900.00.", [{"landed_usd": "4900.00"}], c)["passed"]


def test_links_must_come_from_a_tool_output():
    v = guardrail.check("See https://example.com/page for details.", OUT, card())
    assert v["violation_classes"] == ["link"]
    assert v["claims"] == ["link or address not in any tool output: https://example.com/page"]
    out = OUT + [{"source": {"url": "https://example.com/page"}, "notes": ["mail help@example.com"]}]
    assert guardrail.check("See https://example.com/page.", out, card())["passed"]
    assert guardrail.check("Write to help@example.com.", out, card())["passed"]


def test_over_length_explanation_is_blocked():
    text = "word " * 400
    v = guardrail.check(text, OUT, card())
    assert v["violation_classes"] == ["length"]
    assert v["claims"] == [f"explanation is {len(text)} characters (max {guardrail.MAX_CHARS})"]
    assert guardrail.check("word " * 300, OUT, card())["passed"]


def test_strings_flattens_nested_containers_and_ignores_non_strings():
    assert guardrail._strings({"a": ["x", ("y", 3)], "b": {"c": "z", "d": None}, "e": 1.5}) == ["x", "y", "z"]
    assert guardrail._strings("solo") == ["solo"]
    assert guardrail._strings(7) == []


class FakeSpan:
    def __init__(self):
        self.attrs = {}

    def set_attribute(self, key, value):
        self.attrs[key] = value


def patch_neatlogs(monkeypatch):
    spans, logs = [], []

    class Trace:
        def __init__(self, name, kind):
            self.name, self.kind, self.span = name, kind, FakeSpan()
            spans.append(self)

        def __enter__(self):
            return self.span

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(guardrail.neatlogs, "trace", lambda name, kind: Trace(name, kind))
    monkeypatch.setattr(guardrail.neatlogs, "log", lambda msg, **kw: logs.append((msg, kw)))
    return spans, logs


def test_run_records_a_passing_guardrail_span(monkeypatch):
    spans, logs = patch_neatlogs(monkeypatch)
    v = guardrail.run("Use Payoneer.", OUT, card(), attempt=2)
    assert v["passed"] and v["attempt"] == 2
    (span,) = spans
    assert (span.name, span.kind) == ("provenance_guardrail", "GUARDRAIL")
    assert span.span.attrs["neatlogs.guardrail.passed"] is True
    assert span.span.attrs["neatlogs.guardrail.score"] == 1.0
    assert span.span.attrs["neatlogs.guardrail.input"] == "Use Payoneer."
    assert '"verdict": "PASSED"' in span.span.attrs["neatlogs.guardrail.output"]
    assert logs == []


def test_run_records_a_blocked_verdict_and_logs_each_violation_class(monkeypatch):
    spans, logs = patch_neatlogs(monkeypatch)
    v = guardrail.run("Go with Wise. It costs $1.99.", OUT, card(), attempt=0, question="q")
    assert not v["passed"] and v["violation_classes"] == ["refused_rail", "unsourced_figure"]
    attrs = spans[0].span.attrs
    assert attrs["neatlogs.guardrail.passed"] is False and attrs["neatlogs.guardrail.score"] == 0.0
    assert '"verdict": "BLOCKED"' in attrs["neatlogs.guardrail.output"]
    assert logs == [("violation {cls}", {"cls": "refused_rail"}), ("violation {cls}", {"cls": "unsourced_figure"})]


def test_no_source_is_a_deterministic_block(monkeypatch):
    spans, _ = patch_neatlogs(monkeypatch)
    v = guardrail.no_source({"payer": "Acme", "country": "Narnia"})
    assert v == {"passed": False, "score": 0.0, "reason": "no_source", "figures": 0, "unsourced": [], "claims": [],
                 "detail": "no sourced rule for Acme in Narnia", "attempt": 0}
    attrs = spans[0].span.attrs
    assert attrs["neatlogs.guardrail.passed"] is False and attrs["neatlogs.guardrail.score"] == 0.0
    assert '"verdict": "BLOCKED"' in attrs["neatlogs.guardrail.output"] and "no_source" in attrs["neatlogs.guardrail.output"]
