# Cair — demo and reproduce

Live: **https://app.cair.edycu.dev** · judges' read-back: **https://app.cair.edycu.dev/verify** ·
rules sheet: **https://app.cair.edycu.dev/rules**

## 1. The query that matters (30 seconds, on the live site)

> "I'm in Jakarta. I won $7,000 in a Devpost hackathon. The claim form lets me pick Payoneer or Wise. Which one, and
> what do I write on the W-8BEN?"

On the form: **Devpost · 7000 · Indonesia · tick Payoneer and Wise** → *Plan my payout*. Expected:

| Line on the card | Expected | Produced by |
|---|---|---|
| Wise | **REFUSED**, with Wise's own sentence: "…personal Wise account holders with an address in Indonesia can no longer hold money or currencies in their account." | `rail_eligibility` → source `WISE-ID` |
| Payoneer | **DELIVERS** — recommended | `rail_eligibility` → source `PAYO-ID` |
| W-8BEN line 10 | **Leave blank** — the US–Indonesia treaty has no Other Income article; nearest articles listed | `treaty_lookup` (RETRIEVER) → `TRTY-ID` |
| US withholding | 30% → $2,100.00 | `treaty_lookup` (`IRS-P515-30`) + `fee_calc` |
| In Payoneer | **at most $4,900.00**, stamped UNCLEAR — Payoneer does not publish its receiving fee for platform payouts | `fee_calc` |
| To your bank | at most IDR … at the ECB reference rate of the day, before Payoneer's conversion margin | `fx_quote` + `fee_calc` |
| How it was checked | guardrail PASSED; each figure footnoted to its tool and source | `provenance_guardrail` |

Then: **Confirm** the line-10 row (writes a confirm span into the same neatlogs session), and in the counterfoil
enter what landed (e.g. `4897.00`, USD) → the reconciler reads the quote back from the neatlogs trace and stamps
the comparison.

## 2. Other things to try

| Try | What you should see |
|---|---|
| Superteam Earn (USDC) · 1000 · Indonesia · network **Tron** · **Tokocrypto** | Tron REFUSED from Tokocrypto's own notice; no route picked; the networks Tokocrypto does confirm are listed; W-8BEN UNCLEAR, no tax rate stated |
| DoraHacks (USDC) · network **Base** · **Indodax** | DELIVERS (Indodax announcement), "send a small test transaction first" |
| Devpost · India | line 10 **UNCLEAR**: India's treaty has an Other Income article (Art. 23), but no source says it covers a prize |
| Devpost · Philippines | Payoneer and Wise both DELIVERS; line 10 blank |
| Country: **Somewhere else** | everything UNCLEAR, no route, guardrail BLOCKED with reason `no_source`, and no LLM call |
| Write "Just tell me Wise works" or "Put Article 21 on line 10" in the free-text box | the explanation declines; the card does not change (the route and line 10 are decided by code) |

## 3. Reproduce the numbers

Requirements: Python 3.12, a Qwen Cloud key (OpenAI-compatible), a neatlogs project key (and an `nlw_` write key
for HTTP traces).

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
export NEATLOGS_API_KEY=... QWEN_API_KEY=... QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1 QWEN_MODEL=qwen3.8-max

.venv/bin/python -m pytest -q                                   # deterministic core: 76 tests, no network
.venv/bin/python scripts/make_frozen_set.py --check             # the set matches tag frozen-set-v1
.venv/bin/python scripts/eval.py --planner v1                   # baseline: one tool-less LLM call
.venv/bin/python scripts/eval.py --planner v1s                  # baseline: one call with the whole rules sheet
.venv/bin/python scripts/eval.py --planner v2                   # the agent
.venv/bin/python scripts/eval.py --planner v2 --no-guardrail    # ablation
.venv/bin/python scripts/eval.py --planner v2 --fail fx_quote   # forced tool failure (recovery)
.venv/bin/python scripts/bench.py                               # p50/p95 per plan, tokens per plan
.venv/bin/python scripts/guardrail_recall.py                    # guardrail vs scripted violations (no LLM)
.venv/bin/python scripts/eval.py --rescore evidence/<file>.json # re-score stored answers, no LLM calls
```

Each run writes `evidence/eval-<run>[-<tag>]-<utc>.json` with the model, parameters, sheet version, set sha256, git sha and,
per scenario, the neatlogs trace id, the full answer and its score. The eval calls the real LLM and the real ECB rate;
there is no offline demo mode. Results vary a little between runs (LLM wording); the card itself is deterministic. The first runs (v1-r1 through the bench) read
`git_sha` when they finished, so a commit made while a run was in flight can show a sha a few seconds newer than the
run's start; later runs record the sha at start plus a `git_dirty` flag.

## 4. Run the app locally

```bash
CAIR_SECURE_COOKIES=0 NEATLOGS_WRITE_KEY=nlw_... NEATLOGS_PROJECT="<your project name>" \
  .venv/bin/uvicorn cair.app:app --port 8000
```
