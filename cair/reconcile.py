"""Receipt reconciler: what Cair quoted vs what actually landed, read back from neatlogs and written back as an
EVALUATOR span.

1. MCP search_traces(plan id) -> the plan's trace id      (falls back to the id stored with the plan)
2. MCP get_trace_context(trace id) -> the fee_calc span's output, i.e. the quote exactly as it was traced
3. compare with the landed amount:
   - full: the quote had a landed figure -> error_pct
   - partial: the quote was UNCLEAR (e.g. receiving fee unsourced) -> check the landed amount sits inside the sourced
     upper bound and report the unexplained remainder; error_pct stays empty
4. POST /v1/trace: the read-back steps as MCP_TOOL spans + one EVALUATOR span, in the plan's session.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from . import neat

UNCLEAR = "UNCLEAR"


def read_back(plan_id: str, known_trace_id: str | None, tries: int = 4) -> dict:
    """Find the plan's trace and its fee_calc output over MCP. Traces finalize a few seconds after a plan."""
    steps: list[dict] = []
    timing: list[dict] = []  # when each step started and how long it took: the MCP_TOOL spans' real timeline

    def clock() -> tuple[float, str]:
        return time.perf_counter(), datetime.now(UTC).isoformat(timespec="milliseconds")

    def took(t0: float, at: str, **extra) -> None:
        timing.append({"start": at, "duration_ms": round((time.perf_counter() - t0) * 1000), **extra})

    last_err = None
    for i in range(tries):
        t0, at = clock()
        try:
            found, ctx = None, None
            res = neat.mcp([("search_traces", {"query": plan_id, "limit": 5})])[0]
            hits = res.get("results", []) if isinstance(res, dict) else []
            found = next((h["trace_id"] for h in hits if h.get("root_span_name") == "payout-plan"), None)
            steps.append({"tool": "search_traces", "query": plan_id, "trace_id": found})
            took(t0, at, hits=len(hits))
            tid = found or known_trace_id
            if tid:
                t0, at = clock()
                ctx = neat.mcp([("get_trace_context", {"trace_id": tid})])[0]
                spans = ctx.get("spans", []) if isinstance(ctx, dict) else []
                fee = next((s for s in spans if s.get("name") == "fee_calc"), None)
                steps.append({"tool": "get_trace_context", "trace_id": tid, "spans": len(spans),
                              "fee_calc_found": bool(fee)})
                took(t0, at)
                if fee and fee.get("output_value"):
                    return {"trace_id": tid, "fee_calc": json.loads(fee["output_value"]), "steps": steps,
                            "timing": timing, "source": "neatlogs MCP read-back"}
        except Exception as e:  # MCP unavailable or trace not finalized yet: back off and retry
            last_err = f"{type(e).__name__}: {e}"[:200]
            steps.append({"tool": "mcp", "error": last_err})
            took(t0, at)
        time.sleep(2 + 2 * i)
    return {"trace_id": known_trace_id, "fee_calc": None, "steps": steps, "timing": timing,
            "error": last_err or "fee_calc span not found"}


def compare(fee_calc: dict, landed: Decimal) -> dict:
    if fee_calc.get("landed_usd") not in (None, UNCLEAR):
        quoted = Decimal(fee_calc["landed_usd"])
        err = (landed - quoted) / quoted * 100 if quoted else None
        return {"mode": "full", "quoted": str(quoted), "landed": str(landed),
                "error_pct": str(err.quantize(Decimal("0.0001"))) if err is not None else None,
                "verdict": "within 1%" if err is not None and abs(err) <= 1 else "off by more than 1%"}
    raw_upper = fee_calc.get("upper_bound_usd") or fee_calc.get("gross")
    if not raw_upper or raw_upper == UNCLEAR:
        return {"mode": "not compared", "verdict": "the quote has no sourced amount to compare with", "landed": str(landed),
                "error_pct": None}
    upper = Decimal(raw_upper)
    unexplained = upper - landed
    return {"mode": "partial", "quoted_upper": str(upper), "landed": str(landed), "error_pct": None,
            "unexplained_usd": str(unexplained),
            "verdict": "within sourced bound" if landed <= upper else "outside sourced bound",
            "note": "the quote's landed amount was UNCLEAR, so only its sourced components are compared; "
                    "the remainder is not explained by the sourced rules"}


def reconcile(plan: dict, landed_amount: str, landed_currency: str, landed_on: str, label: str | None,
              session_id: str, end_user_hash: str) -> dict:
    result: dict[str, Any]
    rb: dict[str, Any]
    t_start, started = time.perf_counter(), datetime.now(UTC).isoformat(timespec="milliseconds")
    if landed_currency != "USD":
        result = {"mode": "not compared", "verdict": "only USD receipts are compared with the quote so far",
                  "landed": landed_amount}
        rb = {"trace_id": plan.get("trace_id"), "steps": [], "fee_calc": None}
    else:
        rb = read_back(plan["plan_id"], plan.get("trace_id"))
        fee = rb["fee_calc"]
        source = rb.get("source")
        if fee is None:  # recovery: compare against our own stored copy, and say so
            fee = plan["landed"]
            source = "DB copy (neatlogs read-back unavailable)"
        result = compare(fee, Decimal(landed_amount))
        result["quote_source"] = source
    result.update({"plan_id": plan["plan_id"], "landed_on": landed_on, "currency": landed_currency,
                   "label": label, "plan_trace_id": rb.get("trace_id")})
    timing = rb.get("timing") or []

    def meta(i: int) -> dict:  # /v1/trace: a child without start/duration_ms renders at 0 ms on its parent's start
        return timing[i] if i < len(timing) else {}

    trace = {
        "name": "receipt-reconcile",
        "start": started,
        "duration_ms": round((time.perf_counter() - t_start) * 1000),
        "input": json.dumps({"plan_id": plan["plan_id"], "landed": landed_amount, "currency": landed_currency,
                             "landed_on": landed_on, "label": label}),
        "output": json.dumps(result),
        "attributes": {"neatlogs.session.id": session_id, "neatlogs.end_user.id": end_user_hash},
        "children": [
            *({"name": s["tool"], "kind": "MCP_TOOL", "tool_name": s["tool"], "input": json.dumps(
                {k: v for k, v in s.items() if k in {"query", "trace_id"}}),
               "output": json.dumps({**s, **{k: v for k, v in meta(i).items() if k == "hits"}}),
               **{k: v for k, v in meta(i).items() if k in ("start", "duration_ms")},
               **({"status": "ERROR", "error": s["error"]} if "error" in s else {})}
              for i, s in enumerate(rb["steps"])),
            {"name": "reconcile", "kind": "EVALUATOR", "input": json.dumps({"quote": rb.get("fee_calc") or "DB copy",
             "landed": landed_amount}), "output": json.dumps(result)},
        ],
    }
    try:
        posted = neat.post_trace(trace)
        result["evaluator_trace_id"] = posted.get("trace_id")
    except Exception as e:
        result["evaluator_trace_id"] = None
        result["evaluator_error"] = f"{type(e).__name__}: {e}"[:200]
    return result
