"""Run a planner over the frozen set, score every answer, write evidence/eval-<run>-<utc>.json.

    python scripts/eval.py --planner v1                  # baseline: one tool-less LLM call (lives only here)
    python scripts/eval.py --planner v2                  # evidence plan + provenance guardrail
    python scripts/eval.py --planner v2 --no-guardrail   # ablation
    python scripts/eval.py --planner v2 --fail fx_quote  # forced tool failure (recovery)

Every run calls the real LLM and the real FX source and is traced to neatlogs, tagged eval + the run name +
frozen-set-v1, so the before/after traces can be filtered in the dashboard. Scoring: cair/scoring.py, docs/METRICS.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import neatlogs  # noqa: E402

from cair import config, llm, rules, scoring  # noqa: E402
from cair.tracing import current_trace_id  # noqa: E402

SET = ROOT / "data" / "frozen_set.jsonl"
TEMPERATURE = 0.0

V1_SYSTEM = """You help people outside the US receive prize money and client payments paid in USD or USDC.
Answer the user's question directly and concretely: which payout option to pick from the ones their form offers,
what to write on the W-8BEN tax form (if any), how much US tax is withheld, and how much lands in their account.
If you are not sure about something, say UNCLEAR rather than guessing.

End your answer with exactly these five lines:
RECOMMENDED RAIL: <one option from the form, or NONE, or UNCLEAR>
W-8BEN LINE 10: <BLANK, or the treaty article and rate, or NOT NEEDED, or UNCLEAR>
WITHHOLDING: <percentage, or NONE, or UNCLEAR>
LANDED (USD): <amount, or UNCLEAR>
LANDED (LOCAL): <amount in local currency, or UNCLEAR>"""


def v1_user(rec: dict) -> str:
    parts = [rec["question"], "", f"Payer: {rules.PAYERS[rec['payer']]}", f"Amount: ${rec['amount_usd']:,}",
             f"Country of residence: {rules.COUNTRIES[rec['country']]}",
             "Options on the form: " + ", ".join(rules.RAILS.get(r, r) for r in rec["rails_offered"])]
    if rec.get("exchange"):
        parts.append(f"Receiving exchange: {rules.EXCHANGES.get(rec['exchange'], rec['exchange'])}")
    return "\n".join(parts)


@neatlogs.span(kind="AGENT", name="baseline", capture_input=False)
def _v1_agent(user: str) -> str:
    # Baseline by design: no tools, no rules sheet, no guardrail — what one chatbot call does.
    return llm.chat([{"role": "system", "content": V1_SYSTEM}, {"role": "user", "content": user}], TEMPERATURE)


@neatlogs.span(kind="WORKFLOW", name="payout-plan")
def v1_plan(plan_id: str, payer: str, country: str, amount_usd: int, rails_offered: list, exchange: str | None,
            question: str) -> dict:
    rec = {"payer": payer, "country": country, "amount_usd": amount_usd, "rails_offered": rails_offered,
           "exchange": exchange, "question": question}
    text = _v1_agent(v1_user(rec))
    return {"text": text, "tool_outputs": None, "trace_id": current_trace_id()}


def run_one(rec: dict, args) -> dict:
    t0 = time.perf_counter()
    plan_id = f"eval-{args.run}-{rec['id']}"
    try:
        if args.planner == "v1":
            out = v1_plan(plan_id, rec["payer"], rec["country"], rec["amount_usd"], rec["rails_offered"],
                          rec.get("exchange"), rec["question"])
        else:
            from cair import planner
            out = planner.run(plan_id=plan_id, payer=rec["payer"], country=rec["country"],
                              amount_usd=rec["amount_usd"], rails_offered=rec["rails_offered"],
                              exchange=rec.get("exchange"), question=rec["question"], origin="eval",
                              guardrail=not args.no_guardrail, fail=args.fail)
        err = None
    except Exception as e:  # a crashed plan is scored as an empty answer and reported
        out, err = {"text": "", "tool_outputs": [] if args.planner != "v1" else None, "trace_id": None}, repr(e)
    row = scoring.score(rec, out["text"], out["tool_outputs"])
    row.update({"trace_id": out.get("trace_id"), "latency_s": round(time.perf_counter() - t0, 2), "error": err,
                "text": out["text"], "tool_outputs": out["tool_outputs"], "guardrail": out.get("guardrail"),
                "recovery": out.get("recovery")})
    return row


def rescore(path: Path) -> int:
    doc = json.loads(path.read_text())
    recs = {json.loads(ln)["id"]: json.loads(ln) for ln in SET.read_text().splitlines()}
    for row in doc["scenarios"]:
        fresh = scoring.score(recs[row["id"]], row["text"], row.get("tool_outputs") if doc["meta"]["planner"] != "v1" else None)
        row.update(fresh)
    doc["aggregate"] = scoring.aggregate(doc["scenarios"])
    doc["meta"]["rescored_with_git_sha"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                                          capture_output=True, text=True).stdout.strip()
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(doc["aggregate"], indent=1))
    return 0


def check_set() -> str:
    digest = hashlib.sha256(SET.read_bytes()).hexdigest()
    try:
        tagged = subprocess.run(["git", "show", "frozen-set-v1:data/frozen_set.sha256"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.split()[0]
    except Exception:
        tagged = "unavailable"
    if tagged not in {digest, "unavailable"}:
        raise SystemExit(f"frozen set changed since tag frozen-set-v1: {digest} != {tagged}")
    return digest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", choices=["v1", "v2"])
    ap.add_argument("--no-guardrail", action="store_true")
    ap.add_argument("--fail", help="force this tool to fail on every call (recovery run)")
    ap.add_argument("--only", help="comma-separated scenario ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default="", help="suffix for the evidence file name, e.g. r1")
    ap.add_argument("--rescore", help="re-score the stored answers in an evidence file (no LLM calls), in place")
    args = ap.parse_args()
    if args.rescore:
        return rescore(Path(args.rescore))
    if not args.planner:
        ap.error("--planner is required")
    args.run = "v1" if args.planner == "v1" else ("ablation" if args.no_guardrail else "v2")
    if args.fail:
        args.run = f"fail-{args.fail}"

    digest = check_set()
    recs = [json.loads(ln) for ln in SET.read_text().splitlines()]
    if args.only:
        keep = set(args.only.split(","))
        recs = [r for r in recs if r["id"] in keep]
    if args.limit:
        recs = recs[: args.limit]

    neatlogs.init(api_key=config.NEATLOGS_API_KEY, endpoint=config.NEATLOGS_ENDPOINT, workflow_name="payout-plan",
                  tags=["eval", args.run, "frozen-set-v1"])
    started = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda r: run_one(r, args), recs))
    neatlogs.flush()
    neatlogs.shutdown()

    agg = scoring.aggregate(rows)
    git_sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    meta = {"run": args.run, "planner": args.planner, "guardrail": args.planner == "v2" and not args.no_guardrail,
            "forced_failure": args.fail, "model": config.LLM_MODEL, "temperature": TEMPERATURE, "extra_body": llm.EXTRA_BODY,
            "llm_endpoint": "Qwen Cloud (OpenAI-compatible)", "sheet_version": rules.sheet().version,
            "frozen_set_sha256": digest, "git_sha": git_sha, "started_utc": started.isoformat(timespec="seconds"),
            "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "errors": sum(1 for r in rows if r["error"])}
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"eval-{args.run}{('-' + args.tag) if args.tag else ''}-{stamp}.json"
    out.write_text(json.dumps({"meta": meta, "aggregate": agg, "scenarios": rows}, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **agg, "errors": meta["errors"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
