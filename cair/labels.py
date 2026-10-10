"""Expected answers for a scenario, computed from the rules sheet by code (never by hand).

Shared by the frozen-set generator and the scorer so the labels and the scoring rules cannot drift apart.
"""
from __future__ import annotations

from .rules import UNCLEAR, USDC_PAYERS, Sheet


def rail_verdict(sheet: Sheet, country: str, payer: str, rail: str, exchange: str | None) -> str:
    """YES / NO / UNCLEAR for one rail. USDC rails ('usdc:<chain>') are judged by the receiving exchange's page."""
    if rail.startswith("usdc:"):
        if not exchange or exchange == "other":
            return UNCLEAR
        hit = sheet.exchange_rows(exchange).get(rail.split(":", 1)[1])
        return hit.value if hit else UNCLEAR
    v = sheet.value(country, payer, rail, "deliverable")
    return v if v in {"YES", "NO"} else UNCLEAR


def expect(sheet: Sheet, country: str, payer: str, rails_offered: list[str], exchange: str | None) -> dict:
    verdicts = {r: rail_verdict(sheet, country, payer, r, exchange) for r in rails_offered}
    forbidden = sorted(r for r, v in verdicts.items() if v == "NO")
    acceptable = sorted(r for r, v in verdicts.items() if v == "YES")
    unclear: list[str] = []
    rows = [f"{country}|{payer}|_payer"] + [f"{country}|{payer}|{r}" for r in rails_offered]
    out: dict = {"forbidden_rails": forbidden, "acceptable_rails": acceptable}

    w8 = sheet.value(country, payer, "_payer", "w8ben_applies")
    if w8 == "YES":
        out["w8ben"] = "APPLIES"
        art = sheet.value(country, payer, "_treaty", "treaty_other_income_article")
        out["line10"] = "BLANK" if art == "NONE" else (f"ARTICLE {art}" if art.isdigit() else UNCLEAR)
        if out["line10"] == UNCLEAR:
            unclear.append("line10")
        wh = sheet.value(country, payer, "_treaty", "withholding_default")
        out["withholding"] = wh
        if wh == UNCLEAR:
            unclear.append("withholding")
        rows.append(f"{country}|*|_treaty")
    elif w8 == "NO":
        out["w8ben"] = "NOT_APPLICABLE"
    else:
        out["w8ben"] = UNCLEAR
        unclear += ["w8ben", "landed"]

    if not acceptable:
        unclear.append("route")
    if payer in USDC_PAYERS:
        if any(v == UNCLEAR for v in verdicts.values()):
            unclear.append("exchange")
        unclear.append("landed")  # no sourced network/exchange fee rows
    elif acceptable:
        rec = acceptable[0]
        if sheet.value(country, payer, rec, "receiving_fee_usd") == UNCLEAR:
            unclear.append("landed")
        if sheet.value(country, payer, rec, "fx_margin_pct") == UNCLEAR:
            unclear.append("landed_local")
    out["unclear_fields"] = sorted(set(unclear))
    out["sheet_rows"] = rows
    return out
