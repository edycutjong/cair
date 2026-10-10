"""The reconciler end to end through the API: quote read back from the trace, compared with what landed."""
import json
from datetime import date, timedelta

import pytest

from cair import db, neat, reconcile


@pytest.fixture
def planned(client):
    r = client.post("/api/plan", json={"payer": "devpost", "amount": "7000", "country": "ID", "rails": ["payoneer", "wise"]})
    return r.json()["plan_id"], db.get_plan(r.json()["plan_id"])


def _read_back_returning(monkeypatch, card_json):
    fee = json.loads(card_json)["landed"]
    spans = [{"name": "fee_calc", "output_value": json.dumps(fee)}]

    def fake(calls, timeout=30.0):
        name = calls[0][0]
        if name == "search_traces":
            return [{"results": [{"trace_id": "a" * 32, "root_span_name": "payout-plan"}]}]
        return [{"spans": spans}]

    monkeypatch.setattr(neat, "mcp", fake)


def test_receipt_reads_the_quote_back_from_the_trace_and_stamps_it(client, planned, monkeypatch):
    pid, row = planned
    _read_back_returning(monkeypatch, row["card_json"])
    r = client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "4897.00", "currency": "USD",
                                          "landed_on": date.today().isoformat()})
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["quote_source"] == "neatlogs MCP read-back" and res["mode"] == "partial"
    assert res["verdict"] == "within sourced bound" and res["unexplained_usd"] == "3.00"
    assert db.receipts(pid)[0]["evaluator_trace_id"] == "f" * 32


def test_receipt_falls_back_to_the_stored_quote_when_the_neatlogs_read_back_is_down(client, planned, monkeypatch):
    pid, _ = planned

    def down(calls, timeout=30.0):
        raise ConnectionError("neatlogs MCP unreachable")

    monkeypatch.setattr(neat, "mcp", down)
    monkeypatch.setattr(reconcile.time, "sleep", lambda s: None)
    r = client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "4897.00", "currency": "USD",
                                          "landed_on": date.today().isoformat()})
    res = r.json()["result"]
    assert res["quote_source"].startswith("DB copy") and res["verdict"] == "within sourced bound"


def test_a_receipt_dated_before_the_plan_is_a_replay_not_a_prediction(client, planned, monkeypatch):
    pid, row = planned
    _read_back_returning(monkeypatch, row["card_json"])
    r = client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "4897.00", "currency": "USD",
                                          "landed_on": (date.today() - timedelta(days=30)).isoformat()})
    assert r.json()["result"]["label"] == "REPLAY — known outcome"


def test_a_receipt_in_another_currency_is_not_compared_with_a_usd_quote(client, planned, monkeypatch):
    pid, _ = planned
    monkeypatch.setattr(neat, "mcp", lambda calls, timeout=30.0: pytest.fail("no read-back for a non-USD receipt"))
    r = client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "80000000", "currency": "IDR",
                                          "landed_on": date.today().isoformat()})
    assert r.json()["result"]["mode"] == "not compared"


def test_idr_receipt_in_the_tens_of_millions_is_accepted(client, planned, monkeypatch):
    """Defect: the 10,000,000 cap applied to every currency, so IDR 87,616,900 (a normal $4,900 payout) was refused."""
    pid, _ = planned
    monkeypatch.setattr(neat, "mcp", lambda calls, timeout=30.0: pytest.fail("no read-back for a non-USD receipt"))
    r = client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "87,616,900", "currency": "IDR",
                                          "landed_on": date.today().isoformat()})
    assert r.status_code == 200 and r.json()["result"]["mode"] == "not compared"


def test_an_impossible_receipt_amount_is_rejected(client, planned):
    pid, _ = planned
    for amount in ("0", "-5", "abc", "99999999999999"):
        r = client.post("/api/receipt", json={"plan_id": pid, "landed_amount": amount, "currency": "USD"})
        assert r.status_code == 400, amount
    assert client.post("/api/receipt", json={"plan_id": pid, "landed_amount": "10", "currency": "XYZ"}).status_code == 400
