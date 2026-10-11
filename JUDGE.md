## The claim

**Cair is an agent that plans how a prize or client payment reaches your bank account — it refuses routes that can't
deliver, fills W-8BEN line 10 only when a treaty article really applies, computes the most that can land, and shows the source of
every figure. Every plan is a neatlogs trace.** *The payout route a chatbot can't get wrong.*

## The 30-second path

No account, no key, no clone.

1. Open the [live app](https://app.cair.edycu.dev). Choose **Devpost · 7000 · Indonesia**, tick **Payoneer** and
   **Wise**, press *Plan my payout* (about 5–10 seconds).
2. Read the card: **Wise REFUSED** with Wise's own sentence, **Payoneer** recommended, W-8BEN **line 10 blank**,
   30% withholding = $2,100.00, and *at most* $4,900.00 stamped **UNCLEAR** because Payoneer does not publish its
   receiving fee.
3. Press **Confirm** on line 10 — the server writes a confirm span into the same neatlogs session.
4. Open [/verify](https://app.cair.edycu.dev/verify): the last plans read back from neatlogs over MCP, redacted.
5. Open [/rules](https://app.cair.edycu.dev/rules): every fact the agent may state, with its primary source and the
   date it was read ([CSV](https://app.cair.edycu.dev/rules.csv)).

## The receipts

All numbers come from stored runs in [`evidence/`](https://github.com/edycutjong/cair/tree/main/evidence); each
scenario in them carries its neatlogs trace id. Definitions: [`docs/METRICS.md`](https://github.com/edycutjong/cair/blob/main/docs/METRICS.md).

| What | v1: one LLM call | **v2: Cair** |
|---|---|---|
| Recommends a route its own provider rules out | 18 / 48 (every run) | **0 / 48** |
| Contradicts a sourced tax fact | 8 / 48 (every run) | **0 / 48** |
| Says UNCLEAR where no primary source exists | 11–23 / 143 fields | **143 / 143** |
| Figures traceable to a tool output | n/a (no tools) | **359 / 359** |

| What | Result |
|---|---|
| Forced failure of the FX tool (`--fail fx_quote`) | all 48 plans completed after retry and fallback; 350 / 350 figures sourced |
| Provenance guardrail on sentences it was not tuned on (measured before the misses were fixed; that set is now in-sample) | blocks 62 / 66 violations; blocks 3 / 66 honest sentences |
| Cost and speed per plan (bench on the builder's laptop at commit `0a8fc06`; later commits changed guardrail and claims sentence splitting; re-run on `42cda1c`: U/P/K unchanged, see [`evidence/rerun-at-head-2026-10-11.md`](evidence/rerun-at-head-2026-10-11.md)) | p50 5.50 s · p95 10.31 s · $0.0033 of LLM at list price |
| Tests | 631 passing (100% line+branch coverage), no network or keys; many are named for the defect they pin (e.g. `test_amount_in_2000s_is_not_masked_as_a_year`) |
| Exhaustive verification | 2,448 scenarios (every payer × country × option set × amount) run through the real planner against the protocol invariants: 0 violations |
| cfo.ai business plan | entered and shared (5 pages): base scenario cost $18.887 / month, operating profit $81.113 on assumed revenue of $100, $25 AWS credit = 1.35 months before revenue ([cfo.ai/s/PQ2HUGmiJl3P0RQB](https://cfo.ai/s/PQ2HUGmiJl3P0RQB)) |
| Permission boundary | tests prove no public route returns a key or token, `/verify` shows no raw amount, and the builder-only origin cannot be forged |

## Reproduce it (the real path)

The eval, ablation, forced-failure and latency numbers above are produced with the real model, the real ECB rate and
the real neatlogs project — there is no offline or mock mode for the product. (The held-out guardrail test feeds fixed
sentences to the guardrail with the model call stubbed.) [`DEMO.md` §3](https://github.com/edycutjong/cair/blob/main/DEMO.md) has the
commands (`scripts/eval.py --planner v2`, `--fail fx_quote`, `scripts/bench.py`). Separate and clearly **not** the
product: `pytest` runs the deterministic core without network or keys, and the CI pipeline runs no real-model path.

## Honest limitations

- Three countries are fully sourced (Indonesia, India, the Philippines); anything else is UNCLEAR by design.
- The evaluation measures fidelity to the sourced rules sheet, not tax correctness; the labels and the agent read the
  same sheet (three cells were re-checked by hand against the live pages).
- Payoneer's receiving fee and conversion margin are unpublished, so "what lands" is an upper bound. Receipts so far
  are the builder's own: one replay of a known outcome (n = 1) plus one QA test receipt (/verify counts 2,
  [`evidence/receipts-live-2026-10-10.md`](https://github.com/edycutjong/cair/blob/main/evidence/receipts-live-2026-10-10.md)); forward
  receipts from real users: n = 0.
- The guardrail is rule-based. Held-out sentences slip through at roughly the held-out rate. Sentences written by someone
  reading its code did far better: 0 / 40 blocked on `75ba335`, 37 / 40 after the fixes, and a second such probe 24 / 25
  (`evidence/guardrail-probe-r5-…`, `-r6-…`). That is why the route, line 10 and every amount are decided by code, not by the model's prose.

## Links

[Demo video (2:57)](https://youtu.be/UC7pSo3hUlk) · [Live app](https://app.cair.edycu.dev) · [Verify](https://app.cair.edycu.dev/verify) ·
[Rules sheet](https://app.cair.edycu.dev/rules) · [Website](https://cair.edycu.dev) ·
[Pitch deck](https://cair.edycu.dev/pitch/) · [cfo.ai model](https://cfo.ai/s/PQ2HUGmiJl3P0RQB) · [Repository](https://github.com/edycutjong/cair) ·
[README](https://github.com/edycutjong/cair#readme)
