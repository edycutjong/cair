# neatHack build log — Cair

## Project
**Cair** — tell it who is paying you, how much, and where you live; it plans the payout route, refuses rails that
cannot deliver to your country, and shows the source of every amount, rate and treaty article on the card.
Problem: non-US prize winners and freelancers fill in payout and tax forms once or twice a year, and the form is
where money gets lost (an undeliverable rail, a W-8BEN line 10 that claims a treaty article that does not exist,
fees nobody quoted).

## Team
Edy Team — Edy Cu (solo).

## Stack
Python 3.12 · FastAPI · neatlogs Python SDK (spans for every step) · neatlogs HTTP `/v1/trace` (EVALUATOR and
confirm spans) · neatlogs MCP server (trace read-back) · Qwen Cloud through an OpenAI-compatible client wrapped by
`neatlogs.wrap` · ECB reference rates via Frankfurter · SQLite · AWS EC2 + Caddy · Entire (`entire graph`).

## Build log
- **2026-10-10 14:00 WIB (12:30 IST)** — build window opens. Repository created; FastAPI skeleton with
  `neatlogs.init` in the lifespan and `/healthz`.
- **2026-10-10** — setup validated with a sample run: one WORKFLOW trace with a TOOL span, a GUARDRAIL span and an LLM
  span reached neatlogs and was read back over the MCP server (`get_trace_context`, `search_traces` by plan id);
  one HTTP `/v1/trace` trace with an EVALUATOR child was read back the same way. Details in `docs/DX-REPORT.md`.

## Demo
https://app.cair.edycu.dev — steps and reproduce commands in `DEMO.md`; judges' trace read-back at `/verify`.

## Known limitations and next steps
See README → Limitations. Next: more countries from primary sources; forward receipts from real users.

## Submission
Confirmed requirements (event page, 2026-10-10): public quote post of the official neatlogs submission post on X,
Mon 12 Oct 7:00–11:55 PM IST; public repo with commits dated in the window; demo video ≤ 3 min covering neatlogs,
Entire and cfo.ai. Outstanding: everything after the first commit.
- **2026-10-10** — rules sheet (`data/rules_sheet.csv`, sources in `data/sources.md`), frozen set of 48 scenarios
  (tag `frozen-set-v1`) and the scorer (`docs/METRICS.md`) committed before any planner code.
- **2026-10-10** — v1 baseline run: one tool-less call to the same model (`scripts/eval.py --planner v1`).
  Result on 48 scenarios: 18 recommend a rail or network the sources rule out (for example Wise for an Indonesian
  address), 40 misstate the tax form, 44 do one or the other; UNCLEAR honoured on 23 of 143 unclear fields.
  Evidence: `evidence/eval-v1-r1-20261010T071611Z.json` (each scenario has its neatlogs trace id).
- **2026-10-10** — v2 agent: six traced tools, code-decided route and line 10, provenance guardrail with one retry,
  recovery path (retry → stale ECB rate or UNCLEAR). Frozen-set results, same model: U 0/48, P 0/48, UNCLEAR honoured
  143/143, figures traceable 311/311 (`evidence/eval-v2-r2-20261010T072626Z.json`). Ablation without the guardrail:
  3 of 317 figures unsourced. Forced FX failure: 48/48 plans completed, 0 invented figures (`evidence/recovery-01.md`).
- **2026-10-10** — two failures found in v2 traces with the neatlogs MCP server (`search_traces`, `get_trace_context`)
  and fixed: an amount like "2000.00 USD" parsed as a year, and refusals that repeated the user's "0%" falling back to
  the template. Write-up with before/after trace ids: `evidence/rca-01.md`.
- **2026-10-10** — live at https://app.cair.edycu.dev (AWS EC2 + Caddy). First receipt check on the live site: the
  builder's own $7,000 Devpost prize (landed $4,897 on 2026-09-23) against Cair's quote "at most $4,900, fee UNCLEAR":
  within the sourced bound, $3.00 unexplained — a replay of a known outcome.
- **2026-10-10** — bench: p50 5.49 s, p95 6.83 s per plan, 857 tokens per plan (`evidence/bench-20261010T073454Z.json`).
  Tests: 53 passing. Entire graph outputs in `evidence/entire/`. Business-plan numbers in `docs/BUSINESS-PLAN.md`
  (cfo.ai model pending).
