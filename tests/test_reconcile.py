from decimal import Decimal

from cair import reconcile


def test_reconcile_full_reports_error_pct():
    r = reconcile.compare({"landed_usd": "4897.00", "gross": "7000.00"}, Decimal("4897.00"))
    assert r["mode"] == "full" and r["error_pct"] == "0.0000" and r["verdict"] == "within 1%"


def test_reconcile_partial_when_fee_unclear():
    r = reconcile.compare({"landed_usd": "UNCLEAR", "upper_bound_usd": "4900.00", "gross": "7000.00"}, Decimal("4897"))
    assert r["mode"] == "partial" and r["error_pct"] is None
    assert r["unexplained_usd"] == "3.00" and r["verdict"] == "within sourced bound"


def test_reconcile_partial_outside_bound():
    r = reconcile.compare({"landed_usd": "UNCLEAR", "upper_bound_usd": "4900.00", "gross": "7000.00"}, Decimal("5100"))
    assert r["verdict"] == "outside sourced bound"
