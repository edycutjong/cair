"""Line + branch coverage for cair/figures.py: number-word parsing, figure extraction and the sourced-value check."""
from decimal import Decimal

import pytest

from cair import figures
from cair.figures import _dec, extract, is_sourced, sourced_values, unsourced, words_to_number


@pytest.mark.parametrize("phrase,expected", [
    ("tiga puluh persen", 30),               # "puluh" multiplies the unit before it
    ("lima belas", 15),                       # "belas" adds ten
    ("sebelas", 11),
    ("seratus", 100),                         # "se-" prefix on a scale word contributes the implicit one
    ("seribu", 1000),
    ("sejuta", 1_000_000),
    ("dua juta", 2_000_000),
    ("two thousand one hundred USD", 2100),
    ("hundred", 100),
    ("twenty-five", 25),
    ("satu", 1),
    ("zero dollars", 0),
])
def test_words_to_number_reads_number_words(phrase, expected):
    assert words_to_number(phrase) == Decimal(expected)


@pytest.mark.parametrize("phrase", ["foo dollars", "five widgets", "dollars", "", "and USD percent"])
def test_words_to_number_rejects_non_numbers(phrase):
    # any unknown word, or nothing but currency/percent noise, is not a readable number
    assert words_to_number(phrase) is None


@pytest.mark.parametrize("raw,expected", [
    ("1.234.567,89", Decimal("1234567.89")),  # Indonesian grouping
    ("4,5", Decimal("4.5")),                  # decimal comma
    ("1,234.50", Decimal("1234.50")),         # US grouping
    ("1 234", Decimal("1234")),
    (" 62.82 ", Decimal("62.82")),
])
def test_dec_parses_locale_formats(raw, expected):
    assert _dec(raw) == expected


def test_dec_returns_none_for_unparseable():
    assert _dec("1.2.3") is None


def test_extract_masks_urls_and_allowlisted_text():
    text = ("See https://example.com/help/12345 and Form 8233, W-8BEN, line 14, due 2026-10-11, in 2025, "
            "within 30 days, the 3rd item, ERC-20, at 10:30.")
    assert extract(text) == []


def test_extract_money_with_symbol_code_and_multiplier():
    figs = extract("Fee is $5k, balance USD 1,234.50 and 2.500 rb IDR")
    assert [(f["kind"], f["value"]) for f in figs] == [
        ("money", Decimal("5000")), ("money", Decimal("1234.50")), ("money", Decimal("2500000"))]
    assert figs[0]["raw"] == "$5k"


def test_extract_money_with_trailing_currency():
    figs = extract("You pay 2.000 USD or 50 dollars")
    assert [(f["kind"], f["value"]) for f in figs] == [("money", Decimal("2000")), ("money", Decimal("50"))]


def test_extract_percent_and_article():
    figs = extract("Withholding is 30% under Article 12 and pasal 7")
    assert [(f["kind"], f["value"]) for f in figs] == [("article", 12), ("article", 7), ("pct", Decimal("30"))]


def test_extract_help_article_is_not_a_treaty_article():
    assert extract("see help article 12345 and support article 99") == []


def test_extract_percent_wins_over_overlapping_money():
    # "Rp 5%" is matched by both the percent and the money pattern; the percent is taken, the money is skipped
    figs = extract("Rp 5% off")
    assert [(f["kind"], f["value"], f["raw"]) for f in figs] == [("pct", Decimal("5"), "5%")]


def test_extract_unparseable_money_is_skipped():
    # the money pattern matches the digits but the number cannot be parsed -> no figure at all
    assert extract("$1.234,567.89") == []


def test_extract_words_in_money_and_pct():
    figs = extract("five million dollars, twenty percent and tiga puluh persen")
    assert [(f["kind"], f["value"], f["words"]) for f in figs] == [
        ("pct", Decimal("20"), True), ("pct", Decimal("30"), True), ("money", Decimal("5000000"), True)]


def test_extract_word_money_overlapping_a_digit_figure_is_not_double_counted():
    # "juta" is already consumed by "Rp 5 juta", so "juta rupiah" must not become a second figure
    figs = extract("Rp 5 juta rupiah")
    assert [(f["kind"], f["value"]) for f in figs] == [("money", Decimal("5000000"))]


def test_extract_bare_numbers_keep_large_drop_small():
    figs = extract("about 500 units, 3 items, 9 tabs and 1.234.567 total")
    assert [(f["kind"], f["value"]) for f in figs] == [("number", Decimal("500")), ("number", Decimal("1234567"))]


def test_extract_bare_number_inside_money_is_not_repeated():
    figs = extract("$4,900 only")
    assert [(f["kind"], f["value"]) for f in figs] == [("money", Decimal("4900"))]


def test_sourced_values_collects_only_named_fields():
    pools = sourced_values([
        {"gross": 2000, "withheld": "600.00", "withholding_rate": "30%", "article": 12, "bm25": 7.77,
         "nested": [{"fx_rate": 17881.5, "fx_margin_pct": 1.5, "other_income_article": 21.0}]},
        {"amount": True, "landed_usd": None, "rate": "n/a", "treaty_other_income_article": 12.5},
    ])
    assert pools.money == {Decimal("2000"), Decimal("600.00"), Decimal("17881.5")}
    assert pools.pct == {Decimal("30"), Decimal("1.5")}
    assert pools.arts == {12, 21}  # 12.5 is not an integral article number


def test_is_sourced_word_kind_is_never_sourced():
    assert is_sourced({"kind": "word", "value": "gibberish", "raw": "gibberish", "words": True}, figures.Pools()) is False


def test_is_sourced_words_must_match_exactly():
    pools = figures.Pools()
    pools.money.add(Decimal("2100"))
    pools.pct.add(Decimal("30"))
    assert is_sourced({"kind": "money", "value": Decimal("2100"), "raw": "x", "words": True}, pools)
    assert not is_sourced({"kind": "money", "value": Decimal("2101"), "raw": "x", "words": True}, pools)
    assert is_sourced({"kind": "pct", "value": Decimal("30"), "raw": "x", "words": True}, pools)
    assert not is_sourced({"kind": "pct", "value": Decimal("2100"), "raw": "x", "words": True}, pools)


def test_is_sourced_article():
    pools = figures.Pools()
    pools.arts.add(12)
    assert is_sourced({"kind": "article", "value": 12, "raw": "Article 12"}, pools)
    assert not is_sourced({"kind": "article", "value": 13, "raw": "Article 13"}, pools)


def test_is_sourced_matches_at_displayed_precision_only():
    pools = figures.Pools()
    pools.money.add(Decimal("62.821"))
    assert is_sourced({"kind": "money", "value": Decimal("62.82"), "raw": "62.82"}, pools)
    assert not is_sourced({"kind": "money", "value": Decimal("62.83"), "raw": "62.83"}, pools)
    assert not is_sourced({"kind": "money", "value": Decimal("62"), "raw": "62"}, pools)


def test_is_sourced_exact_pool_hit_and_pct_pool():
    pools = figures.Pools()
    pools.money.add(Decimal("4900"))
    pools.pct.add(Decimal("30"))
    assert is_sourced({"kind": "money", "value": Decimal("4900"), "raw": "$4,900"}, pools)
    assert is_sourced({"kind": "pct", "value": Decimal("30"), "raw": "30%"}, pools)
    assert not is_sourced({"kind": "pct", "value": Decimal("4900"), "raw": "4900%"}, pools)


def test_is_sourced_absurd_number_is_unsourced_not_a_crash():
    pools = figures.Pools()
    pools.money.add(Decimal("1"))
    huge = Decimal("1E+999999")  # quantizing to 2 places overflows the context precision -> InvalidOperation
    assert is_sourced({"kind": "money", "value": huge, "raw": "1.00"}, pools) is False


def test_unsourced_lists_only_figures_missing_from_tool_outputs():
    outputs = [{"gross": 2000, "withheld": 600, "withholding_rate": 30, "article": 12}]
    text = "On 2000 USD, 30% is withheld (600 USD) under Article 12; you also owe $75 and 15%."
    assert unsourced(text, outputs) == ["15%", "$75"]  # percentages are extracted before money


def test_unsourced_flags_unreadable_and_words_figures():
    assert unsourced("a fee of five hundred dollars", [{"amount": 500}]) == []
    assert unsourced("a fee of five hundred dollars", [{"amount": 400}]) == ["five hundred dollars"]
