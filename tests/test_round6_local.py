"""a2a round 06, local side: WRITE_REFUSED was still read on the whole sentence, so a refused write of something else
("Don't put Wise on the form") excused an instruction to write a treaty article in the same sentence."""
import pytest

from cair import guardrail, planner

BLOCK = [
    "Don't put Wise on the form, and write Article 15 in the treaty box.",
    "Never enter your Wise details; cite Article 15 in the treaty section.",
    "Jangan tulis Wise di formulir, tetapi tulis Pasal 15 di bagian perjanjian.",
    "Don't write the gross twice; claim Article 15 on the W-8BEN.",
]
PASS = [
    "Do not write Article 15 on the W-8BEN; leave line 10 blank.",
    "Don't cite Article 15; no source says it covers a prize.",
    "Jangan tulis Pasal 15 di formulir.",
]


@pytest.fixture
def card(fixed_fx, llm_says):
    llm_says("Plan explained.")
    return planner.run(plan_id="r6l", question="", origin="eval", guardrail=False, payer="devpost", country="ID",
                       amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None)["card"]


@pytest.mark.parametrize("text", BLOCK)
def test_a_refused_write_of_something_else_does_not_excuse_writing_an_article(card, text):
    v = guardrail.check(text, card["tool_outputs"], card)
    assert not v["passed"] and "line10" in v["violation_classes"], v


@pytest.mark.parametrize("text", PASS)
def test_a_refused_write_of_the_article_still_passes(card, text):
    assert guardrail.check(text, card["tool_outputs"], card)["passed"]
