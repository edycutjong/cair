# Cair — business plan

> **Status:** the measured costs below come from this repository (`scripts/bench.py`, `scripts/unit_economics.py`).
> The cfo.ai model built from these inputs is **pending** — it is added here (export + screenshot) once it has been
> entered in cfo.ai. Nothing on this page was produced by cfo.ai yet.

## What is sold

| Tier | Who | Price | What they get |
|---|---|---|---|
| Free planner | any prize winner or freelancer | $0, rate-limited | the plan card, confirm, one receipt check |
| Freelancer Pro *(planned, not built)* | freelancers paid by US clients every month | **$4 / month** *(assumption)* | saved payer profiles, a receipt check after every payout, a log of quoted vs landed over time |
| Payout Desk *(planned, not built)* | hackathon organisers and platforms (the link in the winner email) | **$2 per winner** *(assumption)* | one plan per winner prefilled with the event's payer and network, and a list of which winners' payouts reconciled |

Why organisers (a hypothesis, not yet validated): winners are likely to ask them "which option do I pick?", and an
undeliverable payout becomes their problem too. Devpost's own help page says that if a prize is undeliverable the winner "may incur
fees … or be delaying or forfeiting receipt of the prize".

## Costs (measured)

| Cost | Value | Source |
|---|---|---|
| LLM per plan | **$0.0033** (942 prompt + 244 completion tokens on average, 1.19 calls — guardrail retries included) | `evidence/bench-20261010T085809Z.json` × qwen3.8-max International $2 / $6 per 1M tokens (Alibaba Cloud Model Studio pricing page, updated 2026-10-09) |
| Hosting | **$15.26 / month** (t3.small on-demand, Linux, US East (N. Virginia), $0.0209/h × 730 h) | aws.amazon.com/ec2/instance-types/t3 |
| Tracing | neatlogs free tier (MCP `whoami` reports `"tier": "free"`) | `evidence/mcp-whoami.json` |
| FX rates, rules data | $0 (ECB via Frankfurter; primary pages read by hand) | — |
| Not modelled | payment-processor fees, the builder's time, a second region | — |

Latency (same bench, commit `0a8fc06`, run on the builder's laptop in Jakarta): p50 **5.50 s**, p95 **10.31 s** per
plan, live LLM and live ECB rate, one plan at a time. The p95 is a plan whose explanation was blocked and rewritten.

## Revenue scenarios (monthly, assumptions labelled)

Assumptions: Pro at $4/month, 4 plans per Pro subscriber per month, Payout Desk at $2 per winner. These are
inputs to `scripts/unit_economics.py`, not measurements.

From `python scripts/unit_economics.py evidence/bench-20261010T085809Z.json`:

| Scenario | Free plans | Pro subscribers | Desk winners | Plans | Cost | Revenue | Gross profit | Gross margin |
|---|---|---|---|---|---|---|---|---|
| Base *(assumption)* | 1,000 | 25 | 0 | 1,100 | $18.94 | $100.00 | $81.06 | 81.06% |
| Growth *(assumption)* | 5,000 | 150 | 200 | 5,800 | $34.69 | $1,000.00 | $965.31 | 96.53% |

**Break-even: 4 Pro subscribers** cover the server and their own inference.

## Runway

- Cash raised: $0. The AWS credits our team received for neatHack ($25 by the builder's record; the event page gives
  no amount) pay for about 1.6 months of the t3.small.
- Monthly burn with no revenue at 1,000 free plans: **$18.61** ($15.26 hosting + 1,000 × $0.0033). After the allowance it is self-funded
  by the builder; the burn is small enough that runway is set by the builder's time, not cash.
- The cost that would grow first is not inference (a plan costs about a third of a cent) but the rules sheet: every new
  country or payer is hours of reading primary sources. That is the moat and the main cost.

## Risks

- A provider changes its policy and the sheet is stale → every cell shows the date it was read; UNCLEAR is allowed.
- Tax-advice exposure → Cair explains forms, never files them, shows sources, and says UNCLEAR where no primary source
  exists.
- Organisers may not pay per winner → Freelancer Pro alone breaks even at 4 subscribers.
