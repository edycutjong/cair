"""Line + branch coverage for cair/reconcile.py: MCP read-back retries, quote comparison, EVALUATOR write-back. No network."""
import json
from decimal import Decimal

import pytest

from cair import reconcile


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(reconcile.time, "sleep", calls.append)
    return calls


@pytest.fixture
def mcp(monkeypatch):
    """Script neat.mcp: each call pops the next scripted reply (a value, or an Exception to raise)."""
    script, calls = [], []

    def fake(batch):
        calls.append(batch)
        nxt = script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return [nxt]

    monkeypatch.setattr(reconcile.neat, "mcp", fake)
    fake.script, fake.calls = script, calls
    return fake


@pytest.fixture
def posted(monkeypatch):
    sent = []

    def post_trace(trace):
        sent.append(trace)
        return {"trace_id": "eval-1"}

    monkeypatch.setattr(reconcile.neat, "post_trace", post_trace)
    return sent


def _ctx(fee_output="X", with_fee=True):
    spans = [{"name": "other"}]
    if with_fee:
        spans.append({"name": "fee_calc", "output_value": fee_output})
    return {"spans": spans}


HIT = {"results": [{"trace_id": "t-other", "root_span_name": "x"},
                   {"trace_id": "t-plan", "root_span_name": "payout-plan"}]}


# ---------- read_back ----------

def test_read_back_finds_trace_and_decodes_fee_calc(mcp, sleeps):
    quote = {"landed_usd": "4897.00"}
    mcp.script += [HIT, _ctx(json.dumps(quote))]
    out = reconcile.read_back("plan-1", None)
    assert out["trace_id"] == "t-plan" and out["fee_calc"] == quote
    assert out["source"] == "neatlogs MCP read-back"
    assert out["steps"] == [{"tool": "search_traces", "query": "plan-1", "trace_id": "t-plan"},
                            {"tool": "get_trace_context", "trace_id": "t-plan", "spans": 2, "fee_calc_found": True}]
    assert mcp.calls[0] == [("search_traces", {"query": "plan-1", "limit": 5})]
    assert mcp.calls[1] == [("get_trace_context", {"trace_id": "t-plan"})]
    assert sleeps == []


def test_read_back_falls_back_to_known_trace_id(mcp, sleeps):
    mcp.script += [{"results": []}, _ctx(json.dumps({"landed_usd": "1"}))]
    out = reconcile.read_back("plan-1", "t-known")
    assert out["trace_id"] == "t-known" and out["fee_calc"] == {"landed_usd": "1"}
    assert out["steps"][0]["trace_id"] is None
    assert mcp.calls[1] == [("get_trace_context", {"trace_id": "t-known"})]


def test_read_back_no_trace_anywhere_retries_then_gives_up(mcp, sleeps):
    mcp.script += ["not-a-dict"] * 2
    out = reconcile.read_back("plan-1", None, tries=2)
    assert out["fee_calc"] is None and out["trace_id"] is None
    assert out["error"] == "fee_calc span not found"
    assert [s["tool"] for s in out["steps"]] == ["search_traces", "search_traces"]
    assert sleeps == [2, 4]  # back-off grows with the attempt


def test_read_back_retries_when_fee_calc_span_missing_or_empty(mcp, sleeps):
    # attempt 0: no fee_calc span; attempt 1: span present but empty output; attempt 2: finalised
    mcp.script += [HIT, _ctx(with_fee=False), HIT, _ctx(fee_output=""), HIT, _ctx(json.dumps({"gross": "9"}))]
    out = reconcile.read_back("plan-1", None)
    assert out["fee_calc"] == {"gross": "9"}
    assert sleeps == [2, 4]
    flags = [s["fee_calc_found"] for s in out["steps"] if s["tool"] == "get_trace_context"]
    assert flags == [False, True, True]


def test_read_back_non_dict_context_counts_zero_spans(mcp, sleeps):
    mcp.script += [HIT, "garbage"]
    out = reconcile.read_back("plan-1", None, tries=1)
    assert out["steps"][1] == {"tool": "get_trace_context", "trace_id": "t-plan", "spans": 0,
                               "fee_calc_found": False}
    assert out["fee_calc"] is None


def test_read_back_records_mcp_errors_and_recovers(mcp, sleeps):
    mcp.script += [RuntimeError("mcp down"), HIT, _ctx(json.dumps({"landed_usd": "2"}))]
    out = reconcile.read_back("plan-1", None)
    assert out["fee_calc"] == {"landed_usd": "2"}
    assert out["steps"][0] == {"tool": "mcp", "error": "RuntimeError: mcp down"}
    assert sleeps == [2]


def test_read_back_reports_last_error_and_truncates(mcp, sleeps):
    mcp.script += [ValueError("a"), KeyError("b" * 500)]
    out = reconcile.read_back("plan-1", "t-known", tries=2)
    assert out["fee_calc"] is None and out["trace_id"] == "t-known"
    assert out["error"].startswith("KeyError: ") and len(out["error"]) == 200
    assert sleeps == [2, 4]


# ---------- compare ----------

def test_compare_full_off_by_more_than_one_percent():
    r = reconcile.compare({"landed_usd": "100"}, Decimal("95"))
    assert r["mode"] == "full" and r["error_pct"] == "-5.0000" and r["verdict"] == "off by more than 1%"
    assert r["quoted"] == "100" and r["landed"] == "95"


def test_compare_full_zero_quote_has_no_error_pct():
    r = reconcile.compare({"landed_usd": "0"}, Decimal("5"))
    assert r["error_pct"] is None and r["verdict"] == "off by more than 1%"


def test_compare_partial_uses_gross_when_no_upper_bound():
    r = reconcile.compare({"landed_usd": "UNCLEAR", "gross": "7000.00"}, Decimal("4897"))
    assert r["mode"] == "partial" and r["quoted_upper"] == "7000.00" and r["unexplained_usd"] == "2103.00"


def test_compare_partial_when_landed_missing_entirely():
    r = reconcile.compare({"upper_bound_usd": "50"}, Decimal("50"))
    assert r["mode"] == "partial" and r["verdict"] == "within sourced bound" and r["unexplained_usd"] == "0"


@pytest.mark.parametrize("fee", [{"landed_usd": "UNCLEAR"}, {"landed_usd": None, "upper_bound_usd": reconcile.UNCLEAR},
                                 {"upper_bound_usd": "", "gross": None}])
def test_compare_not_compared_without_sourced_amount(fee):
    r = reconcile.compare(fee, Decimal("10"))
    assert r == {"mode": "not compared", "verdict": "the quote has no sourced amount to compare with",
                 "landed": "10", "error_pct": None}


# ---------- reconcile ----------

def _plan():
    return {"plan_id": "plan-1", "trace_id": "t-known", "landed": {"landed_usd": "100"}}


def test_reconcile_non_usd_skips_read_back(mcp, posted):
    out = reconcile.reconcile(_plan(), "1500", "IDR", "2026-10-09", None, "sess", "hash")
    assert mcp.calls == []
    assert out["mode"] == "not compared" and out["landed"] == "1500" and out["currency"] == "IDR"
    assert out["plan_trace_id"] == "t-known" and out["label"] is None and out["evaluator_trace_id"] == "eval-1"
    trace = posted[0]
    assert [c["name"] for c in trace["children"]] == ["reconcile"]
    assert trace["children"][0]["kind"] == "EVALUATOR"
    assert json.loads(trace["children"][0]["input"]) == {"quote": "DB copy", "landed": "1500"}
    assert trace["attributes"] == {"neatlogs.session.id": "sess", "neatlogs.end_user.id": "hash"}
    assert json.loads(trace["output"])["plan_id"] == "plan-1"


def test_reconcile_usd_uses_neatlogs_readback(mcp, sleeps, posted):
    mcp.script += [HIT, _ctx(json.dumps({"landed_usd": "100"}))]
    out = reconcile.reconcile(_plan(), "100", "USD", "2026-10-09", "wise", "sess", "hash")
    assert out["mode"] == "full" and out["verdict"] == "within 1%"
    assert out["quote_source"] == "neatlogs MCP read-back" and out["plan_trace_id"] == "t-plan"
    assert out["label"] == "wise" and out["evaluator_trace_id"] == "eval-1"
    kids = posted[0]["children"]
    assert [k["name"] for k in kids] == ["search_traces", "get_trace_context", "reconcile"]
    assert [k["kind"] for k in kids] == ["MCP_TOOL", "MCP_TOOL", "EVALUATOR"]
    assert json.loads(kids[0]["input"]) == {"query": "plan-1", "trace_id": "t-plan"}
    assert json.loads(kids[1]["input"]) == {"trace_id": "t-plan"}
    assert "status" not in kids[0]
    assert json.loads(kids[2]["input"])["quote"] == {"landed_usd": "100"}
    assert json.loads(posted[0]["input"])["label"] == "wise"


def test_reconcile_falls_back_to_db_copy_and_traces_mcp_errors(mcp, sleeps, posted, monkeypatch):
    monkeypatch.setattr(reconcile, "read_back", lambda pid, tid: {
        "trace_id": tid, "fee_calc": None, "steps": [{"tool": "mcp", "error": "boom"}], "error": "boom"})
    out = reconcile.reconcile(_plan(), "90", "USD", "2026-10-09", None, "sess", "hash")
    assert out["quote_source"] == "DB copy (neatlogs read-back unavailable)"
    assert out["mode"] == "full" and out["error_pct"] == "-10.0000" and out["plan_trace_id"] == "t-known"
    err_span = posted[0]["children"][0]
    assert err_span["status"] == "ERROR" and err_span["error"] == "boom" and err_span["kind"] == "MCP_TOOL"
    assert json.loads(posted[0]["children"][-1]["input"])["quote"] == "DB copy"


def test_reconcile_survives_post_trace_failure(mcp, sleeps, monkeypatch):
    mcp.script += [HIT, _ctx(json.dumps({"landed_usd": "100"}))]

    def boom(trace):
        raise ConnectionError("x" * 500)

    monkeypatch.setattr(reconcile.neat, "post_trace", boom)
    out = reconcile.reconcile(_plan(), "100", "USD", "2026-10-09", None, "sess", "hash")
    assert out["mode"] == "full" and out["evaluator_trace_id"] is None
    assert out["evaluator_error"].startswith("ConnectionError: ") and len(out["evaluator_error"]) == 200
