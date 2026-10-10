"""Line + branch coverage for cair/calc.py: the three-state withholding, fee/bound outcomes and the local-currency leg."""
from decimal import Decimal

import pytest

from cair.calc import MINOR, UNCLEAR, _num, fee_calc, q


def calc(gross="100.00", unit="USD", w8="YES", wh="30%", fee="2.00", margin="1.5%", rate="16000", ccy="IDR"):
    return fee_calc(gross, unit, w8, wh, fee, margin, rate, ccy)


# --- q / _num -------------------------------------------------------------------------------------------------
def test_q_uses_minor_unit_of_the_currency_and_bankers_rounding():
    assert q(Decimal("2.5"), "IDR") == "2"        # half-even, zero decimals
    assert q(Decimal("3.5"), "VND") == "4"
    assert q(Decimal("0.125"), "USD") == "0.12"
    assert q(Decimal("0.135"), "USDC") == "0.14"
    assert q(Decimal("1.005"), "INR") == "1.00"
    assert q(Decimal("1"), "XYZ") == "1.00"       # unknown currency falls back to two decimals
    assert set(MINOR) >= {"USD", "IDR", "VND"}


@pytest.mark.parametrize("cell", [None, "", UNCLEAR])
def test_num_treats_blank_and_unclear_as_unknown_never_zero(cell):
    assert _num(cell) is None


def test_num_strips_percent_and_parses_decimal():
    assert _num("30%") == Decimal("30")
    assert _num("1.5") == Decimal("1.5")
    assert _num("0") == Decimal(0)


# --- withholding ------------------------------------------------------------------------------------------------
def test_yes_with_rate_withholds_and_lands_everything():
    out = calc()
    assert out["gross"] == "100.00" and out["unit"] == "USD" and out["local_currency"] == "IDR"
    assert out["withheld"] == "30.00"
    assert out["after_withholding"] == "70.00"
    assert out["landed_usd"] == "68.00"
    assert out["landed_local"] == "1071680"  # 68 * 16000 * (1 - 1.5%)
    assert "upper_bound_usd" not in out and "upper_bound_note" not in out and "upper_bound_local" not in out
    assert out["inputs"] == {"w8ben_applies": "YES", "withholding_default": "30%", "receiving_fee_usd": "2.00",
                             "fx_margin_pct": "1.5%", "fx_rate": "16000"}


def test_landed_local_applies_margin_to_rate():
    out = calc(gross="100", w8="NO", wh=None, fee="0", margin="2", rate="10")
    assert out["landed_usd"] == "100.00"
    assert out["landed_local"] == "980"  # 100 * 10 * 0.98


def test_no_withholds_nothing_even_with_a_rate_present():
    out = calc(w8="NO", wh="30%")
    assert out["withheld"] == "0.00"
    assert out["after_withholding"] == "100.00"
    assert out["landed_usd"] == "98.00"


@pytest.mark.parametrize("w8,wh", [("UNCLEAR", "30%"), ("UNCLEAR", None), ("YES", None), ("YES", UNCLEAR),
                                   ("YES", ""), ("MAYBE", "30%")])
def test_unclear_withholding_makes_landed_unclear_with_upper_bound_before_any_withholding(w8, wh):
    out = calc(w8=w8, wh=wh)
    assert out["withheld"] == UNCLEAR
    assert "after_withholding" not in out
    assert out["landed_usd"] == UNCLEAR
    assert out["upper_bound_usd"] == "100.00"
    assert out["upper_bound_note"] == "before any withholding and fees"
    assert out["landed_local"] == UNCLEAR
    # bound (gross) converted at the reference rate, no margin
    assert out["upper_bound_local"] == "1600000"
    assert "ECB reference rate" in out["upper_bound_local_note"]


def test_blank_inputs_are_echoed_as_unclear():
    out = fee_calc("10", "USD", "UNCLEAR", None, None, None, None, "IDR")
    assert out["inputs"] == {"w8ben_applies": "UNCLEAR", "withholding_default": UNCLEAR,
                             "receiving_fee_usd": UNCLEAR, "fx_margin_pct": UNCLEAR, "fx_rate": UNCLEAR}
    assert out["landed_usd"] == UNCLEAR and out["landed_local"] == UNCLEAR
    assert out["upper_bound_usd"] == "10.00"
    assert "upper_bound_local" not in out  # no rate, so nothing to convert


# --- receiving fee -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("fee", [None, "", UNCLEAR])
def test_unclear_fee_makes_landed_usd_unclear_bound_is_after_withholding(fee):
    out = calc(fee=fee)
    assert out["after_withholding"] == "70.00"
    assert out["landed_usd"] == UNCLEAR
    assert out["upper_bound_usd"] == "70.00"
    assert out["upper_bound_note"] == "before the receiving fee"
    assert out["landed_local"] == UNCLEAR
    assert out["upper_bound_local"] == "1120000"  # 70 * 16000


def test_fee_equal_to_remainder_lands_zero():
    out = calc(fee="70")
    assert out["landed_usd"] == "0.00"
    assert "upper_bound_usd" not in out
    assert out["landed_local"] == "0"


def test_fee_larger_than_remainder_means_nothing_lands():
    out = calc(fee="70.01")
    assert out["landed_usd"] == UNCLEAR
    assert out["upper_bound_usd"] == "0.00"
    assert out["upper_bound_note"] == "fees exceed the amount left after withholding"
    assert out["landed_local"] == UNCLEAR
    assert out["upper_bound_local"] == "0"
    assert "ECB" in out["upper_bound_local_note"]


# --- local leg -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("margin", [None, "", UNCLEAR])
def test_unclear_margin_keeps_usd_but_local_is_unclear_with_bound_at_reference_rate(margin):
    out = calc(margin=margin)
    assert out["landed_usd"] == "68.00"
    assert out["landed_local"] == UNCLEAR
    assert out["upper_bound_local"] == "1088000"  # 68 * 16000, no margin applied
    assert out["upper_bound_local_note"].endswith("before the provider's conversion margin")


@pytest.mark.parametrize("rate", [None, "", UNCLEAR])
def test_unclear_rate_gives_no_local_figures(rate):
    out = calc(rate=rate)
    assert out["landed_usd"] == "68.00"
    assert out["landed_local"] == UNCLEAR
    assert "upper_bound_local" not in out and "upper_bound_local_note" not in out


def test_non_usd_unit_never_converts():
    out = calc(unit="USDC")
    assert out["unit"] == "USDC"
    assert out["landed_usd"] == "68.00"
    assert out["landed_local"] == UNCLEAR
    assert "upper_bound_local" not in out


def test_non_usd_unit_with_unclear_fee_has_bound_but_no_local():
    out = calc(unit="USDC", fee=None)
    assert out["upper_bound_usd"] == "70.00"
    assert out["landed_local"] == UNCLEAR and "upper_bound_local" not in out


def test_local_amount_rounds_to_currency_minor_unit():
    out = calc(gross="10", w8="NO", wh=None, fee="0", margin="0", rate="0.0123", ccy="INR")
    assert out["landed_local"] == "0.12"
    out = calc(gross="10", w8="NO", wh=None, fee="0", margin="0", rate="0.0123", ccy="VND")
    assert out["landed_local"] == "0"


def test_gross_is_quantized_in_the_requested_unit():
    assert fee_calc("100.005", "USD", "NO", None, "0", "0", "1", "USD")["gross"] == "100.00"
    assert fee_calc("100.015", "USD", "NO", None, "0", "0", "1", "USD")["gross"] == "100.02"
