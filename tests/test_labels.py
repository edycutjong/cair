import json

from cair import labels, rules
from cair.config import DATA


def test_sheet_loads_and_every_fact_is_sourced_or_unclear():
    sheet = rules.load()
    for fact in sheet.facts.values():
        assert fact.value == rules.UNCLEAR or fact.source_id in sheet.quotes


def test_sheet_refuses_a_fact_filled_twice(tmp_path):
    csv = (DATA / "rules_sheet.csv").read_text().splitlines()
    dup = [ln for ln in csv if ln.startswith("ID,*,wise,")][0]
    bad = tmp_path / "sheet.csv"
    bad.write_text("\n".join(csv + [dup]) + "\n")
    try:
        rules.load(bad)
    except rules.SheetError as e:
        assert "filled twice" in str(e)
    else:
        raise AssertionError("duplicate fact accepted")


def test_sheet_refuses_an_unsourced_fact(tmp_path):
    csv = (DATA / "rules_sheet.csv").read_text().splitlines()
    bad = tmp_path / "sheet.csv"
    bad.write_text("\n".join(csv + ["VN,*,payoneer,YES,,,,,,,,2026-10-10"]) + "\n")
    try:
        rules.load(bad)
    except rules.SheetError as e:
        assert "no source" in str(e)
    else:
        raise AssertionError("unsourced fact accepted")


def test_hero_labels_from_sheet():
    exp = labels.expect(rules.load(), "ID", "devpost", ["payoneer", "paypal", "wise"], None)
    assert exp["forbidden_rails"] == ["wise"]
    assert exp["acceptable_rails"] == ["payoneer"]
    assert exp["w8ben"] == "APPLIES" and exp["line10"] == "BLANK" and exp["withholding"] == "30%"
    assert exp["unclear_fields"] == ["landed", "landed_local"]  # Payoneer fee and margin are not on its pricing page


def test_india_line10_unclear_because_other_income_applicability_unsourced():
    exp = labels.expect(rules.load(), "IN", "devpost", ["payoneer", "wise"], None)
    assert exp["line10"] == rules.UNCLEAR and "line10" in exp["unclear_fields"]


def test_usdc_labels_follow_the_exchange_page():
    s = rules.load()
    assert labels.expect(s, "ID", "dorahacks_usdc", ["usdc:tron"], "tokocrypto")["forbidden_rails"] == ["usdc:tron"]
    ok = labels.expect(s, "ID", "dorahacks_usdc", ["usdc:base"], "indodax")
    assert ok["acceptable_rails"] == ["usdc:base"] and "exchange" not in ok["unclear_fields"]
    assert "exchange" in labels.expect(s, "ID", "dorahacks_usdc", ["usdc:base"], "pintu")["unclear_fields"]
    assert "w8ben" in ok["unclear_fields"] and "landed" in ok["unclear_fields"]


def test_frozen_set_labels_match_sheet():
    sheet = rules.load()
    for line in (DATA / "frozen_set.jsonl").read_text().splitlines():
        rec = json.loads(line)
        assert rec["expect"] == labels.expect(sheet, rec["country"], rec["payer"], rec["rails_offered"], rec.get("exchange"))
