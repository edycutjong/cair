"""Line + branch coverage for cair/rules.py: sheet loader validation, lookup precedence, source-quote parsing. No network."""
import re

import pytest

from cair import rules
from cair.rules import UNCLEAR, Fact, Sheet, SheetError

HEADER = ("country,payer,rail,deliverable,w8ben_applies,treaty_other_income_article,withholding_default,"
          "receiving_fee_usd,fx_margin_pct,source_id,source_url,accessed_at\n")
SOURCES = "### S1\nURL: https://example.test/s1 (updated 12 May 2026)\n> quote one\n> quote two\n"


def _load(tmp_path, rows, sources=SOURCES):
    csv_path = tmp_path / "sheet.csv"
    csv_path.write_text(HEADER + rows)
    src = tmp_path / "sources.md"
    src.write_text(sources)
    return rules.load(csv_path, src)


def _fact(value="X", row="a|b|c"):
    return Fact(value, "S1", "u", "2026-10-10", row)


def test_fact_as_dict_renames_row_key():
    assert _fact("YES").as_dict() == {"value": "YES", "source_id": "S1", "source_url": "u",
                                      "accessed_at": "2026-10-10", "row": "a|b|c"}


def test_get_prefers_most_specific_row():
    facts = {("ID", "devpost", "wise", "deliverable"): _fact("NO"),
             ("ID", "*", "wise", "deliverable"): _fact("YES"),
             ("*", "devpost", "wise", "deliverable"): _fact("UNCLEAR"),
             ("*", "*", "wise", "deliverable"): _fact("OFFERED")}
    sh = Sheet(facts=facts, quotes={}, version="v")
    assert sh.get("ID", "devpost", "wise", "deliverable").value == "NO"
    del facts[("ID", "devpost", "wise", "deliverable")]
    assert sh.get("ID", "devpost", "wise", "deliverable").value == "YES"
    del facts[("ID", "*", "wise", "deliverable")]
    assert sh.get("ID", "devpost", "wise", "deliverable").value == "UNCLEAR"
    del facts[("*", "devpost", "wise", "deliverable")]
    assert sh.get("ID", "devpost", "wise", "deliverable").value == "OFFERED"
    del facts[("*", "*", "wise", "deliverable")]
    assert sh.get("ID", "devpost", "wise", "deliverable") is None


def test_value_returns_unclear_when_no_row_fills_the_fact():
    sh = Sheet(facts={("*", "devpost", "wise", "deliverable"): _fact("NO")}, quotes={}, version="v")
    assert sh.value("ID", "devpost", "wise", "deliverable") == "NO"
    assert sh.value("ID", "devpost", "wise", "fx_margin_pct") == UNCLEAR
    assert sh.value("ID", "other", "wise", "deliverable") == UNCLEAR


def test_offered_rails_filters_by_payer_fact_and_value():
    facts = {("*", "devpost", "wise", "deliverable"): _fact("OFFERED"),
             ("*", "devpost", "payoneer", "deliverable"): _fact("OFFERED"),
             ("ID", "devpost", "paypal", "deliverable"): _fact("NO"),
             ("*", "devpost", "paypal", "fx_margin_pct"): _fact("OFFERED"),
             ("*", "other", "zzz", "deliverable"): _fact("OFFERED")}
    sh = Sheet(facts=facts, quotes={}, version="v")
    assert sh.offered_rails("devpost") == ["payoneer", "wise"]
    assert sh.offered_rails("nobody") == []


def test_exchange_rows_keyed_by_chain_suffix():
    facts = {("*", "_exchange", "indodax:usdc:ethereum", "deliverable"): _fact("YES"),
             ("*", "_exchange", "indodax:usdc:base:extra", "deliverable"): _fact("NO"),
             ("*", "_exchange", "pintu:usdc:solana", "deliverable"): _fact("YES"),
             ("*", "_exchange", "indodax:usdc:tron", "fx_margin_pct"): _fact("1"),
             ("*", "devpost", "indodax:usdc:bsc", "deliverable"): _fact("YES")}
    sh = Sheet(facts=facts, quotes={}, version="v")
    rows = sh.exchange_rows("indodax")
    assert set(rows) == {"ethereum", "base:extra"}
    assert rows["ethereum"].value == "YES"
    assert set(sh.exchange_rows("pintu")) == {"solana"}
    assert sh.exchange_rows("tokocrypto") == {}


def test_parse_quotes_extracts_url_quote_and_page_date():
    text = ("preamble ignored\n### A\nURL: https://a.test (dated 3 March 2026)\n> one\n> two\nnot a quote\n"
            "### B\nURL: https://b.test\n> only\n### C\nno url here\n")
    q = rules._parse_quotes(text)
    assert q["A"] == {"url": "https://a.test", "quote": "one two", "page_date": "dated 3 March 2026"}
    assert q["B"] == {"url": "https://b.test", "quote": "only", "page_date": ""}
    assert q["C"] == {"url": "", "quote": "", "page_date": ""}
    assert rules._parse_quotes("nothing here") == {}


def test_load_builds_facts_and_version(tmp_path):
    rows = ("*,devpost,wise,OFFERED,YES,,,,,S1,https://example.test/s1,2026-10-10\n"
            "ID,devpost,wise,,,NONE,10%,2.5,0.5,S1,https://example.test/s1,2026-10-10\n"
            "ID,devpost,paypal,,,UNCLEAR,,,,,,\n")
    sh = _load(tmp_path, rows)
    f = sh.get("ID", "devpost", "wise", "deliverable")
    assert f == Fact("OFFERED", "S1", "https://example.test/s1", "2026-10-10", "*|devpost|wise")
    assert sh.value("ID", "devpost", "wise", "withholding_default") == "10%"
    assert sh.value("ID", "devpost", "wise", "receiving_fee_usd") == "2.5"
    assert sh.value("ID", "devpost", "paypal", "treaty_other_income_article") == UNCLEAR
    assert sh.get("ID", "devpost", "paypal", "treaty_other_income_article").source_id == ""
    assert sh.quotes["S1"]["page_date"] == "updated 12 May 2026"
    assert len(sh.version) == 12
    assert _load(tmp_path, rows).version == sh.version
    assert _load(tmp_path, rows + "ID,devpost,payoneer,,,,,,3,S1,u,d\n").version != sh.version


def test_load_blank_cells_are_not_facts(tmp_path):
    sh = _load(tmp_path, "ID,devpost,wise,,,,,,,S1,u,d\n")
    assert sh.facts == {}


def test_load_defaults_to_packaged_data(monkeypatch, tmp_path):
    seen = {}
    real_read = rules.Path.read_bytes

    def spy(self):
        seen[self.name] = self
        return real_read(self)

    monkeypatch.setattr(rules.Path, "read_bytes", spy)
    sh = rules.load()
    assert seen["rules_sheet.csv"] == rules.DATA / "rules_sheet.csv"
    assert sh.facts and sh.quotes


def test_load_rejects_fact_filled_twice(tmp_path):
    rows = ("ID,devpost,wise,YES,,,,,,S1,u,d\n"
            "ID,devpost,wise,NO,,,,,,S1,u,d\n")
    with pytest.raises(SheetError, match=r"line 3: deliverable for ID\|devpost\|wise is filled twice"):
        _load(tmp_path, rows)


def test_load_rejects_value_without_source(tmp_path):
    with pytest.raises(SheetError, match=r"line 2: deliverable=YES for ID\|devpost\|wise has no source"):
        _load(tmp_path, "ID,devpost,wise,YES,,,,,,,u,d\n")


def test_load_rejects_source_missing_from_sources_md(tmp_path):
    with pytest.raises(SheetError, match="line 2: source NOPE is not in sources.md"):
        _load(tmp_path, "ID,devpost,wise,YES,,,,,,NOPE,u,d\n")
    with pytest.raises(SheetError, match="source NOPE is not in sources.md"):
        _load(tmp_path, "ID,devpost,wise,UNCLEAR,,,,,,NOPE,u,d\n")


def test_load_rejects_invalid_value(tmp_path):
    with pytest.raises(SheetError, match=r"line 2: withholding_default='30' is not a valid value"):
        _load(tmp_path, "ID,devpost,wise,,,,30,,,S1,u,d\n")


@pytest.mark.parametrize("fact,val", [
    ("deliverable", "YES"), ("deliverable", "NO"), ("deliverable", UNCLEAR), ("deliverable", "OFFERED"),
    ("w8ben_applies", "YES"), ("w8ben_applies", UNCLEAR),
    ("treaty_other_income_article", "NONE"), ("treaty_other_income_article", UNCLEAR),
    ("treaty_other_income_article", "21"),
    ("withholding_default", UNCLEAR), ("withholding_default", "30%"), ("withholding_default", "7.5%"),
    ("receiving_fee_usd", UNCLEAR), ("receiving_fee_usd", "0"), ("receiving_fee_usd", "1.25"),
    ("fx_margin_pct", UNCLEAR), ("fx_margin_pct", "0.5"),
])
def test_validate_accepts_valid_values(fact, val):
    assert rules._validate(fact, val, 2) is None


@pytest.mark.parametrize("fact,val", [
    ("deliverable", "MAYBE"), ("deliverable", "yes"),
    ("w8ben_applies", "OFFERED"),
    ("treaty_other_income_article", "21a"), ("treaty_other_income_article", "-1"),
    ("withholding_default", "30"), ("withholding_default", "%"), ("withholding_default", "3.%"),
    ("receiving_fee_usd", "$1"), ("receiving_fee_usd", "1."),
    ("fx_margin_pct", "0.5%"), ("fx_margin_pct", "NONE"),
])
def test_validate_rejects_invalid_values(fact, val):
    with pytest.raises(SheetError, match=re.escape(f"line 7: {fact}={val!r} is not a valid value")):
        rules._validate(fact, val, 7)


def test_sheet_is_cached_singleton(monkeypatch):
    rules.sheet.cache_clear()
    calls = []
    marker = Sheet(facts={}, quotes={}, version="m")
    monkeypatch.setattr(rules, "load", lambda: calls.append(1) or marker)
    try:
        assert rules.sheet() is marker
        assert rules.sheet() is marker
        assert calls == [1]
    finally:
        rules.sheet.cache_clear()


def test_constants_are_consistent():
    assert rules.USDC_PAYERS <= set(rules.PAYERS)
    assert set(rules.EXCHANGE_COUNTRY) == set(rules.EXCHANGES)
    assert set(rules.COUNTRIES) == set(rules.CURRENCY)
