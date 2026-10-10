"""Latency and token benchmark of the v2 planner over the frozen set — live LLM, live ECB rate, one plan at a time.

    python scripts/bench.py            # writes evidence/bench-<utc>.json

The first plan is a warm-up and is discarded. Reports p50/p95 wall-clock per plan, LLM calls and tokens per plan.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import neatlogs  # noqa: E402

from cair import config, planner  # noqa: E402


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main() -> int:
    recs = [json.loads(ln) for ln in (ROOT / "data" / "frozen_set.jsonl").read_text().splitlines()]
    neatlogs.init(api_key=config.NEATLOGS_API_KEY, endpoint=config.NEATLOGS_ENDPOINT, workflow_name="payout-plan",
                  tags=["eval", "bench", "frozen-set-v1"])
    started = datetime.now(timezone.utc)
    rows = []
    for i, rec in enumerate([recs[0]] + recs):
        t0 = time.perf_counter()
        out = planner.run(plan_id=f"bench-{i}-{rec['id']}", payer=rec["payer"], country=rec["country"],
                          amount_usd=rec["amount_usd"], rails_offered=rec["rails_offered"], exchange=rec.get("exchange"),
                          question=rec["question"], origin="eval", session_id="bench", end_user_id="eval")
        dt = time.perf_counter() - t0
        if i == 0:
            continue  # warm-up
        rows.append({"id": rec["id"], "seconds": round(dt, 3), **out["llm_usage"],
                     "guardrail_attempts": len(out["guardrail"] or []), "trace_id": out["trace_id"]})
    neatlogs.flush()
    neatlogs.shutdown()
    secs = [r["seconds"] for r in rows]
    toks = [r["prompt_tokens"] + r["completion_tokens"] for r in rows]
    summary = {"plans": len(rows), "p50_s": round(pct(secs, .5), 2), "p95_s": round(pct(secs, .95), 2),
               "mean_s": round(statistics.mean(secs), 2), "max_s": round(max(secs), 2),
               "llm_calls_per_plan_mean": round(statistics.mean(r["calls"] for r in rows), 2),
               "tokens_per_plan_mean": round(statistics.mean(toks)), "tokens_per_plan_p95": round(pct(toks, .95)),
               "prompt_tokens_total": sum(r["prompt_tokens"] for r in rows),
               "completion_tokens_total": sum(r["completion_tokens"] for r in rows)}
    meta = {"model": config.LLM_MODEL, "host": "builder laptop (Jakarta) -> Qwen Cloud intl + Frankfurter",
            "git_sha": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                      text=True).stdout.strip(),
            "started_utc": started.isoformat(timespec="seconds"), "warmup_discarded": 1, "concurrency": 1}
    out = ROOT / "evidence" / f"bench-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps({"meta": meta, "summary": summary, "plans": rows}, indent=1) + "\n")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **summary}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
