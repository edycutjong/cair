"""fee_calc: the only place money is computed. Decimal, banker's rounding, sheet cells in, strings out.

Three-state on w8ben_applies: YES withholds withholding_default; NO withholds nothing (the payer's page is the
source); UNCLEAR makes the landed amount UNCLEAR and reports an upper bound "before any withholding". An UNCLEAR
receiving fee makes landed USD UNCLEAR; an UNCLEAR margin or rate makes landed local UNCLEAR. Blank is never 0.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

UNCLEAR = "UNCLEAR"
MINOR = {"USD": Decimal("0.01"), "USDC": Decimal("0.01"), "IDR": Decimal("1"), "INR": Decimal("0.01"),
         "PHP": Decimal("0.01"), "VND": Decimal("1"), "NGN": Decimal("0.01")}


def q(x: Decimal, ccy: str) -> str:
    return str(x.quantize(MINOR.get(ccy, Decimal("0.01")), rounding=ROUND_HALF_EVEN))


def _num(cell: str | None) -> Decimal | None:
    if cell is None or cell == "" or cell == UNCLEAR:
        return None
    return Decimal(cell.rstrip("%"))


def fee_calc(gross_usd: str, unit: str, w8ben_applies: str, withholding_default: str | None,
             receiving_fee_usd: str | None, fx_margin_pct: str | None, fx_rate: str | None, local_ccy: str) -> dict:
    gross = Decimal(gross_usd)
    out: dict = {"gross": q(gross, unit), "unit": unit, "local_currency": local_ccy, "inputs": {
        "w8ben_applies": w8ben_applies, "withholding_default": withholding_default or UNCLEAR,
        "receiving_fee_usd": receiving_fee_usd or UNCLEAR, "fx_margin_pct": fx_margin_pct or UNCLEAR,
        "fx_rate": fx_rate or UNCLEAR}}

    rate_pct = _num(withholding_default)
    if w8ben_applies == "YES" and rate_pct is not None:
        withheld = gross * rate_pct / 100
        out["withheld"] = q(withheld, unit)
        after = gross - withheld
        out["after_withholding"] = q(after, unit)
    elif w8ben_applies == "NO":
        withheld, after = Decimal(0), gross
        out["withheld"] = "0.00"
        out["after_withholding"] = q(after, unit)
    else:
        withheld, after = None, None
        out["withheld"] = UNCLEAR

    fee = _num(receiving_fee_usd)
    if after is not None and fee is not None and after - fee >= 0:
        landed = after - fee
        out["landed_usd"] = q(landed, unit)
        bound = None
    elif after is not None and fee is not None:  # fees larger than what is left: nothing lands
        landed, bound = None, Decimal(0)
        out["landed_usd"] = UNCLEAR
        out["upper_bound_usd"] = "0.00"
        out["upper_bound_note"] = "fees exceed the amount left after withholding"
    else:
        landed = None
        out["landed_usd"] = UNCLEAR
        bound = after if after is not None else gross
        out["upper_bound_usd"] = q(bound, unit)
        out["upper_bound_note"] = ("before the receiving fee" if after is not None
                                   else "before any withholding and fees")

    rate = _num(fx_rate)
    margin = _num(fx_margin_pct)
    if landed is not None and rate is not None and margin is not None and unit == "USD":
        out["landed_local"] = q(landed * rate * (1 - margin / 100), local_ccy)
    else:
        out["landed_local"] = UNCLEAR
        if rate is not None and unit == "USD":
            base = landed if landed is not None else bound
            out["upper_bound_local"] = q(base * rate, local_ccy)
            out["upper_bound_local_note"] = "at the ECB reference rate, before the provider's conversion margin"
    return out
