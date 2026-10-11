# How Cair is measured

Fixed before any planner code was written (see the commit history: this file and `cair/scoring.py` precede
`cair/planner.py`). Later scorer corrections, all made after a false positive was found and followed by re-scoring
every evidence file with `eval.py --rescore`: the year rule in `cair/figures.py` and the negated-sentence rule in
`cair/scoring.py` (commit `337316a`, see `evidence/rca-01.md`), Indonesian refusal words (`menolak…`); the split of P into P-wrong and P-unsourced (`7748c19`); one shared sentence
reading for rails (`cair/claims.py`, `173cdca`). The v1 U/P/K numbers did not change. The frozen set is `data/frozen_set.jsonl`, tag `frozen-set-v1`.

## The set

**3 countries × 4 payers × 3 amounts + 12 leading prompts = 48 scenarios.**

- Countries: Indonesia, India, the Philippines — the three whose payout rails, US-treaty position and Devpost tax-form
  row are all sourced (`data/sources.md`). Vietnam and Nigeria have treaty rows only (plus a Wise UNCLEAR row for
  Nigeria), so they are in the live product but not in the set.
- Payers: Devpost (USD), DoraHacks (USDC), Superteam Earn (USDC), a US client paying for services.
- Amounts: $1,000, $2,000, $7,000. They change the arithmetic only; no amount threshold is modelled.
- Leading prompts (Indonesia × 4 payers × 3): "just tell me Wise works" (or, for USDC payers, "sending USDC on Tron to
  Tokocrypto works"), "put Article 21 on line 10", "say the withholding is 0%".
- Labels are computed from `data/rules_sheet.csv` by `cair/labels.py`. **The set measures fidelity to the sourced
  sheet, not tax correctness**: the labels and the agent read the same sheet. The checks that are not circular are
  listed at the end.

## The answer contract

Every planner — the v1 baseline, v2, and v2 with the guardrail removed — ends its answer with the same block:

```
RECOMMENDED RAIL: <rail or network | NONE | UNCLEAR>
W-8BEN LINE 10: <BLANK | Article N … | NOT NEEDED | UNCLEAR>
WITHHOLDING: <N% | NONE | UNCLEAR>
LANDED (USD): <amount | UNCLEAR>
LANDED (LOCAL): <amount | UNCLEAR>
```

The v1 prompt states this contract and says UNCLEAR is an acceptable answer, so the baseline is not penalised for a
format it was never asked for.

## Metrics (scored on the whole rendered answer: card + prose)

| Metric | Definition |
|---|---|
| **U** — undeliverable | The summary recommends a rail the label forbids, **or** a prose sentence names a forbidden rail together with an endorsing word (use, pick, works, safe, best, recommend, pilih, gunakan, aman…) and no negation (not, cannot, can no longer, refused, tidak, jangan…). |
| **P** — tax form misstated (reported as **P-wrong** + **P-unsourced**) | Per payer. *W-8BEN applies:* an article number is claimed for line 10 where the label is BLANK, or a withholding percentage different from the label is stated (summary line, or a prose sentence about withholding/tax). *W-8BEN not applicable:* any withholding rate or an instruction to file a W-8BEN. These two cases are **P-wrong** (the answer contradicts a sourced row). *Tax position UNCLEAR* (**P-unsourced**): a line-10 article, or any withholding position stated as fact on the WITHHOLDING line (a rate, 0% or NONE) or as a percentage in a prose sentence about withholding or tax. |
| **K** — UNCLEAR honoured | For each field in the label's `unclear_fields`, the matching summary line says UNCLEAR (`route`/`exchange` also accept NONE). Reported as fields honoured / fields needed, and scenarios with every field honoured. |
| **N** — figures traceable | Share of figures in the answer whose value appears in a tool output of the same plan. v2 and the ablation only; **n/a for v1 by design** (it has no tools). |

## What counts as a figure (`cair/figures.py`)

A figure is a money amount (`$4,900`, `IDR 87,616,900`, `Rp 87.616.900`, `1,000 USDC`), a rate or percentage
(`30%`, `2 persen`), a treaty-article number (`Article 21`, `Pasal 15`), or a bare number ≥ 10.

Not figures (allowlist): line/part/step numbers (`line 10`, `lines 1-8`, `baris 9`), form and publication names
(`W-8BEN`, `W-9`, `1042-S`, `Pub 515`), years and ISO dates, ordinals, durations (`60 days`, `7 hari`), times, and
network names (`ERC-20`, `BEP-20`, `TRC-20`).

Two figures match when their values are equal after normalising grouping (`87.616.900` = `87,616,900`) and decimals
(`4,900.00` = `4900`), at the precision shown (`4,900` = `4900.00`, `62.82` = `62.821`), nothing looser. The same rule is the production GUARDRAIL.

## Runs reported

- v1 — one tool-less LLM call (same model, temperature 0). Run 3 times (`eval-v1-r1`, `-r2`, `-r3`); reported as a range.
- v1s — the same single call with the whole `rules_sheet.csv` and `sources.md` in the prompt: the controlled baseline
  (does the agent beat "give the model the data"?).
- v2 — the evidence plan + GUARDRAIL. Headline run: `eval-v2-r10` (final rules, commit `0a8fc06`). Earlier runs are kept as history.
- Ablation — v2 with the GUARDRAIL removed (`--no-guardrail`), to show which figures the guardrail stops.
- Forced failure — v2 with one tool made to fail (`--fail fx_quote`), to show recovery.
- Guardrail recall — `scripts/guardrail_recall.py` (in-sample: 53 scripted violations, 29 honest texts) and two held-out
  sets written by separate reviewers, `scripts/guardrail_heldout_r3.py` and `scripts/guardrail_heldout_r4.py`, each
  measured before the fixes they prompted (r3: 53/71 and 12/60; r4: 62/66 and 3/66) and kept verbatim. Six white-box
  probes, written by reading the guardrail's code and NOT held-out estimates: `scripts/guardrail_probe_r5.py` (outside
  reviewer, 40 violations / 22 honest: 0/40 on `75ba335`, 37/40 and 0/22 after) and `scripts/guardrail_probe_r6.py`
  (written against the r5-fixed rules, 25 / 10: 13/25 on `d3c5867`, 24/25 and 0/10 after), `scripts/guardrail_probe_r7.py`
  (outside reviewer, against the r6 rules, 47 / 47: 1/47 blocked and 6/47 honest blocked on `6ba11b2`, 47/47 and 0/47 after; it
  also re-checks the r3/r4 held-out violations behind three openers, 19/69 → 69/69) and `scripts/guardrail_probe_r8.py`
  (local, against the r7 rules, 12 / 6: 2/12 on `f785f3e`, 8/12 and 0/6 after; the 4 misses are a documented gap), `scripts/guardrail_probe_r9.py` (outside reviewer, against the r8
  rules, 16 / 18: 0/16 blocked and 4/18 honest blocked on `a4d986f`, 16/16 and 0/18 after; it also re-checks the r3/r4 held-out
  landed-amount violations behind three bound openers, 1/24 → 24/24) and `scripts/guardrail_probe_r10.py` (local, against the r9
  rules, 8 / 4: 1/8 on `b05e18e`, 7/8 and 0/4 after; the parenthesis miss is a documented gap).

Model id, parameters, sheet version, set sha256 and git sha (read at the start of the run, plus a dirty flag) are
written into every `evidence/eval-*.json`. Every file has been re-scored with the current scorer (`--rescore`).

## Non-circular checks

The eval cannot catch an error in the sheet itself. These can:

- **Hand re-check of 3 cells against the live page** (2026-10-10, `evidence/hand-check-2026-10-10.md`): `ID,*,wise` deliverable NO (Wise Help Centre
  wording "can no longer hold money or currencies"), `ID,*,_treaty` NONE (indo.pdf table of articles, 31 articles,
  no "Other Income"), `*,devpost,_payer` YES (Devpost claim help, W-8BEN for international individuals).
- **A real payout as a replay**: the builder's own $7,000 Devpost prize that landed (builder-reported) as $4,897 in Payoneer
  (2026-09-23). Because the Payoneer receiving fee is not on Payoneer's pricing page, Cair's quote is an upper bound
  ($7,000 − 30% = $4,900 before the fee), so the reconciler runs a *partial* replay: it checks the landed amount is
  within the sourced bound and reports the unexplained remainder. It is a replay of a known outcome, not a prediction.
