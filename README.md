<div align="center">

<img src="docs/assets/icon.svg" width="88" alt="Cair icon">

# Cair

**The payout route a chatbot can't get wrong.**

An agent that plans how a prize or client payment reaches your bank account: it refuses routes that can't deliver,
fills W-8BEN line 10 only when a treaty article really applies, computes what lands, and shows the source of every
figure. Every plan is a neatlogs trace.

<img src="docs/assets/readme-hero.png" alt="Choose Wise — refused. Payoneer: at most $4,900, fee UNCLEAR" width="100%">

**[Live app](https://app.cair.edycu.dev)** · **[Read the traces back](https://app.cair.edycu.dev/verify)** ·
**[Rules sheet](https://app.cair.edycu.dev/rules)** · [Demo & reproduce](DEMO.md) · [Architecture](ARCHITECTURE.md)

Built for neatHack (Oct 10–12, 2026) · Python · FastAPI · neatlogs · Entire · Qwen Cloud

</div>

## The problem

Prize winners and freelancers outside the US fill in a payout form once or twice a year, and the form is where the
money is lost:

- **An option that can't deliver.** Devpost's claim form offers Wise. Wise's own help page: *"personal Wise account
  holders with an address in Indonesia can no longer hold money or currencies in their account."*
- **A tax line that invites a false statement.** A chatbot will happily tell you to put "Article 21" on W-8BEN line 10.
  The US–Indonesia treaty has 31 articles and none of them is "Other Income".
- **Fees nobody quoted.** Payoneer publishes its platform receiving fee as *"Varies by marketplace"*.

## One LLM call vs. the agent, measured

48 frozen scenarios (3 countries × 4 payers × 3 amounts + 12 leading prompts), same model (`qwen3.8-max`,
temperature 0), labels computed from the sourced rules sheet before any agent code existed (tag `frozen-set-v1`).
Two baselines: **v1** is one tool-less call; **v1s** is one call with the *whole* rules sheet and its sources pasted
into the prompt — the strongest thing a single chatbot call can do.

| | v1: one call (3 runs) | v1s: one call + the sheet | **v2: Cair** | v2 without the guardrail |
|---|---|---|---|---|
| Recommends a route its own provider rules out (**U**) | **18 / 48** (every run) | 2 / 48 | **0 / 48** | 0 / 48 |
| Contradicts a sourced tax fact (**P-wrong**: an article on line 10, a rate ≠ 30%) | **8 / 48** (every run) | 0 / 48 | **0 / 48** | 0 / 48 |
| States a tax position no source supports (**P-unsourced**) | 32–36 / 48 | 11 / 48 | **0 / 48** | 0 / 48 |
| Says UNCLEAR where no primary source exists (**K**) | 11–23 / 143 fields | 110 / 143 | **143 / 143** | 143 / 143 |
| Figures in the answer traceable to a tool output (**N**) | n/a (no tools) | n/a | **310 / 310** | 343 / 351 |

v1 recommended Wise for every Indonesian Devpost winner in all three runs and told several users to claim a treaty
article at 0%. Even with every sourced fact in its prompt, one call (v1s) still recommended sending USDC on a network the
exchange no longer credits (one of its 2 U flags; the other is a borderline mention the scorer counts — see the
evidence file) and stated a tax position the sources leave open 11 times. In v2 the route,
line 10 and every amount are decided by code from sourced rows; the model only words the card. The ablation is what
the guardrail adds: without it, 8 figures the tools never produced (the user's "0%" and "Article 21" repeated back,
a URL fragment) reach the page; with it, none do: 10 explanations were blocked, 7 passed after one rewrite, and 3 of 48 were
replaced by a template built from the tool outputs.

The guardrail is also tested on its own: **30 / 30** scripted violations blocked (refused rail, line 10, unsourced
figure, withholding, UNCLEAR stated as fact, links) and **0 / 14** honest explanations blocked
(`scripts/guardrail_recall.py`).

Definitions: [`docs/METRICS.md`](docs/METRICS.md) · evidence (each scenario carries its neatlogs trace id):
`evidence/eval-v1-r1…r3`, `eval-v1s-r1`, `eval-v2-r5`, `eval-ablation-r5`, `guardrail-recall-…`.

## How the agent works

One task, end to end: *get this payout to my account intact*.

1. **Plan** — a fixed evidence plan: what the payer offers and whether a W-8BEN applies → can each offered option
   receive in your country → the US-treaty position and nearest treaty articles → the ECB reference rate (USD payers)
   or the exchange's accepted networks (USDC payers) → Decimal arithmetic.
2. **Tools** — six tools, each a neatlogs TOOL or RETRIEVER span, reading `data/rules_sheet.csv` (every fact cell has
   a primary source and a read date, [`data/sources.md`](data/sources.md)), the treaty texts and the ECB rate.
3. **Decide** — code picks the route (never a REFUSED or UNCLEAR one) and line 10 (an article only if a sourced one
   covers the income).
4. **Verify** — a provenance GUARDRAIL checks the model's explanation: no figure, rate or article that isn't in a tool
   output, no endorsing a refused route, no article on line 10. Blocked → one retry with the findings → a template
   built from the tool outputs.
5. **Recover** — every tool is retried once, then a documented fallback: the last ECB rate fetched (stamped stale) or
   UNCLEAR. Never a model-written number.
6. **State** — the plan is stored; the user confirms each line before copying it (a confirm span in the same neatlogs
   session); later, the user reports what landed.
7. **Check the result** — the receipt reconciler reads Cair's own quote back from the neatlogs trace over MCP and
   writes an EVALUATOR span comparing it with what arrived.

## A run where an action failed

`scripts/eval.py --planner v2 --fail fx_quote` makes the FX tool fail on every call. In the 24 USD-payer scenarios
(USDC plans never call it) the agent retried once, then fell back to the last ECB rate it had fetched, stamped STALE
with its date, and finished the plan. All 48 plans completed: U 0, P 0, 324 / 324 figures sourced (run `fail-fx_quote-r4`). Trace `d1fa1ed7…` (first
recovery run) shows the two ERROR spans and the fallback span. → [`evidence/recovery-01.md`](evidence/recovery-01.md)

## How neatlogs was used to build and improve it

- **Every plan is one trace**: WORKFLOW → AGENT → 6+ TOOL/RETRIEVER spans → LLM → GUARDRAIL, with session and
  hashed end-user bound per request. Eval runs are tagged `eval` / `v1` / `v2` / `ablation`.
- **Finding failures**: `search_traces "provenance_guardrail BLOCKED"` over the MCP server returned the v2 plans
  whose explanation had been blocked (`evidence/traces/search-guardrail-blocked.json`, re-run later, so it also lists
  later blocks); `get_trace_context` showed the LLM text next to the guardrail verdict. Two real
  bugs came out of it (an amount in the 2000s parsed as a year; refusals that repeated the user's "0%"), both fixed and
  re-run. → [`evidence/rca-01.md`](evidence/rca-01.md)
- **Reading results back in the product**: the receipt reconciler and the public [`/verify`](https://app.cair.edycu.dev/verify)
  page read traces back over MCP. First receipt: the builder's own $7,000 Devpost prize that landed as $4,897 in
  Payoneer. Cair's quote was "at most $4,900 before the receiving fee (UNCLEAR)"; the reconciler read that bound back
  from the trace and recorded *within sourced bound, $3.00 not explained by the sourced rules* — a **replay of a known
  outcome**, not a prediction (EVALUATOR trace `f5a47b9c…`).
- **HTTP write-back**: confirm and EVALUATOR spans are posted server-side to `/v1/trace`; the write key never reaches
  the browser.
- Trace exports read back over MCP: [`evidence/traces/`](evidence/traces). What was hard or undocumented:
  [`docs/DX-REPORT.md`](docs/DX-REPORT.md).

## How Entire was used

Entire's code graph (`entire graph`, local and no-egress) was run on this repository while building: after the year-parsing fix, `search` with a
plain-language description of the bug ranked the corrected rule and its covering test first; `impact` was run on `rail_eligibility` before
the unlisted-country fix (and on `fee_calc` and `figures.extract`), and `diff` summarises every entity changed since
the frozen set was tagged. One limit we hit: `impact` reports 0 callers for the tools, because the planner passes
them as function values (`att.call("fx_quote", tools.fx_quote, …)`), which the graph does not follow. Outputs, with the
commands: [`evidence/entire/`](evidence/entire). Entire checkpoints were deliberately not enabled: they store the
coding-agent transcript and write agent configuration into the repository.

## Business plan

Measured: **$0.0025** of LLM per plan (857 tokens), **p50 5.49 s / p95 6.83 s** per plan, hosting $15.26 / month.
Free planner + Freelancer Pro + a per-winner Payout Desk for hackathon organisers; break-even at 4 Pro subscribers.
→ [`docs/BUSINESS-PLAN.md`](docs/BUSINESS-PLAN.md) (cfo.ai model: pending).

## Run it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q        # 74 tests, no network
```

Full reproduce steps (eval, ablation, forced failure, bench) and things to try on the live site: [DEMO.md](DEMO.md).

## Limitations

- Three countries are fully sourced (Indonesia, India, the Philippines); Vietnam and Nigeria have treaty rows only.
  Anything else is UNCLEAR by design.
- The eval measures fidelity to the sourced sheet, not tax correctness; three cells were re-checked by hand against
  the live pages (`evidence/hand-check-2026-10-10.md`).
- Payoneer's receiving fee and conversion margin are not published as single numbers, so "what lands" is an upper
  bound. Receipts are user-reported.
- Receipts so far are the builder's own: the Tarmac replay (n = 1) plus QA test receipts. Forward receipts from real
  users (a plan made before the money moved): n = 0.
- Cair explains forms; it never files them. Not tax advice.

## License

MIT — see [LICENSE](LICENSE).
