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
Pending — live URL will be https://app.cair.edycu.dev

## Known limitations and next steps
Pending.

## Submission
Confirmed requirements (event page, 2026-10-10): public quote post of the official neatlogs submission post on X,
Mon 12 Oct 7:00–11:55 PM IST; public repo with commits dated in the window; demo video ≤ 3 min covering neatlogs,
Entire and cfo.ai. Outstanding: everything after the first commit.
