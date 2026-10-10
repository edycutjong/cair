# Recovery-01 — the FX tool fails; what the agent does next

Command: `python scripts/eval.py --planner v2 --fail fx_quote` (run `fail-fx_quote-r1`, 2026-10-10 07:27 UTC,
48 scenarios). `--fail fx_quote` makes the ECB rate tool raise on every call, as if the FX API were down.

## What the agent did (trace `d1fa1ed78810601ea4f2d6de5dfacec5`, ID-devpost-7000, export `traces/recovery-fx.json`)

| Step | Span | Status | What happened |
|---|---|---|---|
| 1 | TOOL `fx_quote` | **ERROR** | `ToolFailure: fx_quote unavailable` |
| 2 | TOOL `fx_quote` (retry) | **ERROR** | same failure on the one retry |
| 3 | TOOL `fx_quote_fallback` | SUCCESS | the last ECB rate this machine fetched: 1 USD = 17881 IDR, `as_of` 2026-10-09, `stale: true` |
| 4 | TOOL `fee_calc` | SUCCESS | the upper bound in IDR computed from the stale rate, labelled as such |
| 5 | LLM + GUARDRAIL | PASSED | explanation written from the card; no new figures |

The neatlogs trace status is `error` with 2 errored spans, and the plan still completed. The card shows
`FX: 1 USD = 17881 IDR (ECB reference rate, as of 2026-10-09) — STALE: live rate unavailable, last fetched ECB rate`.
If no earlier rate exists, the fallback returns `UNCLEAR` and the local-currency line reads UNCLEAR
(`test_fx_failure_without_snapshot_is_unclear`). The agent never asks the model for a rate.

## Across the whole set

| | v2 (normal, run v2-r8) | v2 with fx_quote failing (run fail-fx_quote-r7) |
|---|---|---|
| Plans completed | 48/48 | 48/48 |
| U / P | 0 / 0 | 0 / 0 |
| UNCLEAR fields honoured | 143/143 | 143/143 |
| Figures traceable to a tool output | 345/345 | 341/341 |
| Plans that used the stale-rate fallback | 0 | 24 (every USD plan; USDC plans do not call fx_quote) |

Sources: `eval-fail-fx_quote-r7-20261010T083829Z.json` (field `recovery` per scenario) vs
`eval-v2-r8-20261010T083708Z.json`. The first forced-failure run (`fail-fx_quote-r1`, before the round-1 guardrail
fixes) gave the same 48/48 and 0/0; the trace above is from that run.

## Other recovery paths (tested in `tests/test_invariants.py`)

| Failure | Next action |
|---|---|
| `treaty_lookup` fails twice | W-8BEN line 10 and the withholding rate become UNCLEAR; nothing is guessed (`test_treaty_failure_makes_line10_unclear_not_guessed`) |
| the LLM is down or times out | the card renders from tool outputs with a fixed template explanation (`test_llm_down_card_still_renders_from_tools`) |
| the explanation is blocked twice by the guardrail | same template fallback, recorded on the card and in the trace (`test_refused_rail_never_recommended`) |
| neatlogs MCP read-back fails during a receipt check | the reconciler retries with back-off, then compares against the plan's DB copy and labels it "DB copy" |
