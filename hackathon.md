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
- **2026-10-10** — rules sheet (`data/rules_sheet.csv`, sources in `data/sources.md`), frozen set of 48 scenarios
  (tag `frozen-set-v1`) and the scorer (`docs/METRICS.md`) committed before any planner code.
- **2026-10-10** — v1 baseline run: one tool-less call to the same model (`scripts/eval.py --planner v1`).
  Result on 48 scenarios: 18 recommend a rail or network the sources rule out (for example Wise for an Indonesian
  address), 40 misstate the tax form, 44 do one or the other; UNCLEAR honoured on 23 of 143 unclear fields.
  Evidence: `evidence/eval-v1-r1-20261010T071611Z.json` (each scenario has its neatlogs trace id).
- **2026-10-10** — v2 agent: six traced tools, code-decided route and line 10, provenance guardrail with one retry,
  recovery path (retry → stale ECB rate or UNCLEAR). Frozen-set results, same model: U 0/48, P 0/48, UNCLEAR honoured
  143/143 (`evidence/eval-v2-r2-20261010T072626Z.json`; 307/312 figures under the final scorer). Forced FX failure: 48/48 plans completed, U 0, P 0 (`evidence/recovery-01.md`).
- **2026-10-10** — two failures found in v2 traces with the neatlogs MCP server (`search_traces`, `get_trace_context`)
  and fixed: an amount like "2000.00 USD" parsed as a year, and refusals that repeated the user's "0%" falling back to
  the template. Write-up with before/after trace ids: `evidence/rca-01.md`.
- **2026-10-10** — live at https://app.cair.edycu.dev (AWS EC2 + Caddy). First receipt check on the live site: the
  builder's own $7,000 Devpost prize (builder-reported: landed $4,897 on 2026-09-23) against Cair's quote "at most $4,900, fee UNCLEAR":
  within the sourced bound, $3.00 unexplained — a replay of a known outcome.
- **2026-10-10** — (superseded by the evening entry) bench: p50 5.49 s, p95 6.83 s per plan, 857 tokens per plan (`evidence/bench-20261010T073454Z.json`).
  Tests: 53 passing. Entire graph outputs in `evidence/entire/`. Business-plan numbers in `docs/BUSINESS-PLAN.md`
  (cfo.ai model now exported: https://cfo.ai/s/PQ2HUGmiJl3P0RQB).
- **2026-10-10 afternoon** — a separate read-only AI review pass over the agent code (loop QA round 1). It found phrasings that slipped
  past the guardrail and a scorer that mixed two kinds of tax error. Closed with tests first; the guardrail now has a
  standing recall check (at that time 30/30 scripted violations blocked, 0/14 honest texts blocked; superseded below). Re-running the frozen set on
  the stricter rules exposed over-blocking (29/48 explanations replaced by the template), found from the guardrail
  fields in the evidence file and fixed (`evidence/rca-01.md`, second half).
- **2026-10-10** — runs after round 1: v2 U 0 / P 0 / UNCLEAR 143/143 / figures 310/310 (`eval-v2-r5`); a new baseline,
  one LLM call with the whole rules sheet in its prompt (`eval-v1s-r1`), still had U 2, P 11, UNCLEAR 110/143.
  v1 repeated 3 times: U 18 every run. Tests: 74.
- **2026-10-10 evening** — second review pass (loop QA round 2): more guardrail bypasses (negated "not refused",
  recommending an unchecked rail, tax claims without numbers, amounts phrased as "credited"/"net"), a crash on
  absurdly long numbers and a rate-limit ordering bug were fixed; then three re-runs (r6–r8) found and removed
  over-blocking of honest refusals. Final: v2 U 0 / P 0 / UNCLEAR 143/143 / figures 345/345 with no template
  fallbacks (`eval-v2-r8`); forced FX failure 48/48, 341/341 (`eval-fail-fx_quote-r7`); guardrail recall 53/53
  with 0/29 honest texts blocked. Bench: p50 5.27 s, p95 10.81 s, $0.0034 per plan
  (`evidence/bench-20261010T083109Z.json`). Tests: 76.
- **2026-10-10 evening (later)** — held-out testing (loop QA rounds 3–4). A first held-out set written by a separate
  reviewer showed the guardrail at 53/71 violations blocked and 12/60 honest sentences blocked — much worse than the
  in-sample 100%. After fixing those, a second, fresh held-out set measured 62/66 and 3/66; its misses were fixed too
  (`evidence/rca-01.md`, rounds 3–4). Final runs at `0a8fc06`: v2 U 0 / P 0 / UNCLEAR 143/143 / figures 359/359, no
  template fallbacks (`eval-v2-r10`); forced FX failure 48/48, 350/350 (`eval-fail-fx_quote-r9`); bench p50 5.50 s,
  p95 10.31 s, $0.0033 per plan (`evidence/bench-20261010T085809Z.json`). Tests: 76 at that point (571 after the coverage pass).
- **2026-10-10 evening** — cfo.ai: the business plan is entered and shared (https://cfo.ai/s/PQ2HUGmiJl3P0RQB); export in `docs/cfo/Runway.xlsx`, rendered in
  `docs/BUSINESS-PLAN.md`. neatlogs dashboard traces are linked from the README and `evidence/`.
- **2026-10-10 night** — hardening (enhance pass): ruff and mypy clean, unit tests and 23 browser tests in CI, CodeQL, gitleaks over
  full history and pip-audit green, community profile 100%; an exhaustive 2,448-scenario check of the real planner found 0
  violations (breaking the route rule gives 2,256). Testing found one real defect, fixed: receipt amounts were capped at 10M for
  every currency, so IDR 87,616,900 was refused. A coverage pass then took the suite to 571 tests at 100% line+branch coverage.
- **2026-10-10 night** — landing page https://cair.edycu.dev and an 11-slide pitch deck https://cair.edycu.dev/pitch/ (GitHub Pages
  from `/docs`); every number on them is read from `evidence/`.
- **2026-10-11 morning** — an outside architecture review (a2a round 3) read the guardrail's code and wrote 40 sentences
  aimed at it: the guardrail blocked none (`evidence/guardrail-probe-r5-…`). An exemption word anywhere in a sentence switched
  a check off. Fixed: 37/40 blocked, 0/22 honest. Checking the fix with 25 new sentences got 12 through, so "UNCLEAR is
  terminal" now keys on the bound amount, not on a verb list: 24/25. Also fixed: cents on the card did not add up
  (`1000.05` gave $300.02 + $700.04), and the receipt trace showed 0 ms on every span. Published eval verdicts unchanged;
  631 tests, 100% line+branch.
- **2026-10-11 late morning** — a2a round 4: the same reviewer found that the tax, line-10 and amount checks were excused by a
  detector of *rail* refusals ("rather than Wise", "Jangan khawatir"), and that the bound rule had nothing to check on 24 of 48
  frozen scenarios, so the README's "whatever the verb" was false. Fixed with its patch (probe r7: 1/47 → 47/47); checking the fix
  found a comma or "and" still carried a refusal into the next clause (probe r8: 2/12 → 8/12). The docs now say where the rule
  applies and list what still passes. Published verdicts unchanged; 694 tests, 100% line+branch.
- **2026-10-11 midday** — a2a round 5: the bound check was never clause-scoped ("Tidak jelas kapan dananya tiba, tetapi Anda akan
  menerima $4.900,00" passed), and "up to 2 business days" counted as a bound. Fixed with the reviewer's patch (probe r9: 0/16 →
  16/16, and an ECB rate quote no longer reads as the PHP bound); checking it found that "while", "since", "karena" or a dash
  kept the bound word in the claim's clause (probe r10: 1/8 → 7/8). Published verdicts unchanged; 733 tests, 100% line+branch.
- **2026-10-11 early afternoon** — a2a round 6: the tax and line-10 checks still read "UNCLEAR", "blank" and "no source" on the
  whole sentence, so "Nothing is withheld, but Payoneer's receiving fee is UNCLEAR" passed (probe r11: 2/13 → 13/13). Checking it
  found a refused write of something else still excused an article instruction (3/4 missed → 0/4). The architecture review loop
  ends here: six rounds, no published number moved. 758 tests, 100% line+branch.

## Demo
Video (2:57, covers neatlogs, Entire and cfo.ai): https://youtu.be/UC7pSo3hUlk

https://app.cair.edycu.dev — steps and reproduce commands in `DEMO.md`; judges' trace read-back at `/verify`.

## Known limitations and next steps
See README → Honest limits. Next: more countries from primary sources; forward receipts from real users.

## Submission
Confirmed requirements (event page, 2026-10-10): public quote post of the official neatlogs submission post on X,
Mon 12 Oct 7:00–11:55 PM IST; public repo with commits dated in the window; demo video ≤ 3 min covering neatlogs,
Entire and cfo.ai. The submission is that quote post, posted by the builder inside the window.

## Built in public (#neatHack)
- [Launch post](https://x.com/edycutjong/status/2108905407381213633) — Sat 10 Oct ~20:00 WIB.
- [The recovery story](https://x.com/edycutjong/status/2108938150072705311) — Sat 10 Oct 22:10 WIB: the FX tool fails twice, the agent falls back and the plan finishes.
- [Shared in the neatHack Discord](https://discord.com/channels/1528866100207419472/1554463484752830504/1558498173591232603) — Sat 10 Oct ~22:15 WIB.
- [Demo video on YouTube](https://youtu.be/UC7pSo3hUlk) — Sun 11 Oct.
- [758 tests at 100% line + branch; Entire's graph ranks the fixed rule first](https://x.com/edycutjong/status/2109380165960921479) — Mon 12 Oct 03:26 WIB.
- [Same model, same 48 scenarios: one call 18/48 dead routes, Cair 0/48](https://x.com/edycutjong/status/2109380608556499399) — Mon 12 Oct 03:28 WIB.
- [Post linking the dev.to write-up](https://x.com/edycutjong/status/2109381012426047885) — Mon 12 Oct 03:29 WIB.
- [dev.to write-up: An agent that refuses](https://dev.to/edycutjong/an-agent-that-refuses-building-a-payout-agent-with-neatlogs-entire-and-cfoai-oo3) — Sun 11 Oct 17:15 WIB.
