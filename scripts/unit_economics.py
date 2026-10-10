"""Unit economics for docs/BUSINESS-PLAN.md, from measured token counts and published prices.

    python scripts/unit_economics.py evidence/bench-<utc>.json

Prices (read 2026-10-10):
- qwen3.8-max, International: $2 input / $6 output per 1M tokens
  https://www.alibabacloud.com/help/en/model-studio/model-pricing (page updated 2026-10-09)
- EC2 t3.small on-demand: $0.0209 per hour  https://aws.amazon.com/ec2/instance-types/t3/
Everything else in the output is an ASSUMPTION and is labelled as one.
"""
from __future__ import annotations

import json
import sys
from decimal import ROUND_HALF_UP, Decimal as D

IN_PER_M, OUT_PER_M = D("2"), D("6")
EC2_HOUR, HOURS_PER_MONTH = D("0.0209"), D("730")

# Assumptions (not measured): pricing and usage of the paid tiers.
PRO_PRICE = D("4")            # Freelancer Pro, USD/month
PRO_PLANS_PER_MONTH = D("4")  # a freelancer paid weekly re-plans each payout
DESK_PRICE_PER_WINNER = D("2")  # Payout Desk for hackathon organisers, USD per winner
SCENARIOS = {"base": {"free_plans": 1_000, "pro": 25, "desk_winners": 0},
             "growth": {"free_plans": 5_000, "pro": 150, "desk_winners": 200}}


def money(x: D) -> str:
    return str(x.quantize(D("0.0001") if x < 1 else D("0.01"), rounding=ROUND_HALF_UP))


def main() -> None:
    bench = json.loads(open(sys.argv[1]).read())
    s, n = bench["summary"], D(bench["summary"]["plans"])
    per_plan = (D(s["prompt_tokens_total"]) / n * IN_PER_M + D(s["completion_tokens_total"]) / n * OUT_PER_M) / D(1_000_000)
    worst = per_plan * D("2.2")  # a retry repeats the call with the first answer + findings added: about 2.2x
    fixed = EC2_HOUR * HOURS_PER_MONTH
    out = {"inference_usd_per_plan_measured": money(per_plan), "inference_usd_per_plan_with_one_retry_estimate": money(worst),
           "ec2_usd_per_month": money(fixed), "break_even_pro_subscribers": None, "scenarios": {}}
    contrib = PRO_PRICE - PRO_PLANS_PER_MONTH * per_plan
    out["break_even_pro_subscribers"] = int((fixed / contrib).to_integral_value(rounding="ROUND_CEILING"))
    for name, sc in SCENARIOS.items():
        plans = sc["free_plans"] + sc["pro"] * PRO_PLANS_PER_MONTH + sc["desk_winners"]
        cost = fixed + plans * per_plan
        revenue = sc["pro"] * PRO_PRICE + sc["desk_winners"] * DESK_PRICE_PER_WINNER
        out["scenarios"][name] = {**sc, "plans_per_month": int(plans), "cost_usd": money(cost),
                                  "revenue_usd": money(revenue), "gross_profit_usd": money(revenue - cost),
                                  "gross_margin_pct": money((revenue - cost) / revenue * 100) if revenue else None}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
