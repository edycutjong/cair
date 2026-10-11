# Cair — architecture

Written from the code in this repository (`cair/`, `scripts/`). One process, one SQLite file, one LLM, three
neatlogs surfaces (SDK spans, HTTP `/v1/trace`, MCP read-back).

## The agent's task

*Get this payout to my bank account intact.* Input: who pays, how much, where the winner lives, which options the
payout form shows. Output: the route to pick (or a refusal), what goes on W-8BEN line 10, the withholding, what lands —
each figure footnoted to the tool span that produced it — and later, a check of what actually landed.

```mermaid
flowchart TD
  U["Browser: ask form"] -->|POST /api/plan| W
  subgraph W["WORKFLOW payout-plan  (cair/planner.py · one trace per plan)"]
    direction TB
    A["AGENT planner"] --> T1["TOOL platform_rails<br/>payer offers · W-8BEN applies?"]
    T1 --> T2["TOOL rail_eligibility ×N<br/>DELIVERS / REFUSED / UNCLEAR"]
    T2 --> R1["RETRIEVER treaty_lookup<br/>sheet position + BM25 nearest articles"]
    R1 --> T3["TOOL fx_quote (USD payers)<br/>ECB rate · retry · fx_quote_fallback"]
    R1 --> T4["TOOL exchange_networks (USDC payers)"]
    T3 --> T5["TOOL fee_calc<br/>Decimal, three-state"]
    T4 --> T5
    T5 --> L["LLM explain<br/>wording only, from the card's facts"]
    L --> G{"GUARDRAIL provenance"}
    G -- "blocked" --> L2["retry once with the findings"] --> G2{"GUARDRAIL"}
    G2 -- "blocked again" --> TPL["template from tool outputs"]
  end
  RULES[("data/rules_sheet.csv<br/>data/sources.md<br/>data/treaties/*.json")] --> T1 & T2 & R1 & T4
  FX["api.frankfurter.dev<br/>/v2/providers/ecb"] --> T3
  W --> DB[("SQLite: plans · confirms · receipts")]
  W -. "OTLP via SDK" .-> NL["neatlogs"]
  C["POST /api/plan/{id}/confirm"] -. "HTTP /v1/trace (server-side nlw_ key)<br/>TASK confirm:&lt;line&gt;" .-> NL
  RC["POST /api/receipt → cair/reconcile.py"] -- "MCP search_traces + get_trace_context<br/>(reads the fee_calc span back)" --> MCP["neatlogs MCP"]
  RC -. "HTTP /v1/trace<br/>MCP_TOOL spans + EVALUATOR" .-> NL
  V["GET /verify"] -- "MCP get_trace_context<br/>redacted projection" --> MCP
```

## Components

| File | Role |
|---|---|
| `cair/planner.py` | The agent. `payout_plan` (WORKFLOW) → `planner` (AGENT): runs the tools in a fixed order through `Attempts.call` (one retry, then a fallback or UNCLEAR), picks the route by code (`RAIL_PREFERENCE` over DELIVERS rails only), builds the card, asks the LLM to word it, runs the guardrail, retries once with the findings, falls back to a template. `render_text` produces the card text the eval scores. |
| `cair/tools.py` | Six tools, each a neatlogs span: `platform_rails`, `rail_eligibility`, `treaty_lookup` (RETRIEVER via `neatlogs.trace`), `fx_quote` + `fx_quote_fallback`, `exchange_networks`, `fee_calc`. `FORCE_FAIL` injects a failure for recovery runs. |
| `cair/rules.py` | Loads the rules sheet; refuses a fact cell filled twice or a fact with no source; most-specific row wins (`country,payer` > `country,*` > `*,payer` > `*,*`). |
| `cair/calc.py` | The only arithmetic that produces a quoted amount (`cair/reconcile.py` computes the receipt delta). `Decimal`, banker's rounding; the withholding is rounded once and everything after it derives from the shown value. Three-state on W-8BEN (YES withholds, NO does not, UNCLEAR makes the landed amount UNCLEAR with an upper bound). Blank is never 0. |
| `cair/treaty.py` | BM25 (`rank_bm25`) over the articles of each US treaty, extracted from the IRS PDFs by `scripts/extract_treaty.py`. |
| `cair/fx.py` | ECB-only rates (IDR, INR, PHP); every success is snapshotted so a later failure can fall back to a real, dated ECB rate — never one older than 7 days (older → UNCLEAR). |
| `cair/guardrail.py` | Provenance check (`check`) and its GUARDRAIL span (`run`). Blocks: a figure not in a typed tool field (money from `fee_calc`/FX, rates from withholding/margin, articles from treaty fields — never from scores, ids or quoted page text); naming a REFUSED rail without saying it is refused (and "use it anyway" follow-ups); an article on line 10; a withholding rate the tools did not produce (also in words); an UNCLEAR upper bound stated as what lands (a USD bound below the gross, and the local-currency bound, must be said to be a bound whatever the verb; where the bound is the gross it may be named but not as arriving, except next to "from <payer>" (README known gaps); a bound word, a purpose or a refusal to say or write something excuses these checks only in its own clause); links, emails or wallet addresses no tool returned; over-long text. The verdict lists violation classes. `no_source` blocks deterministically when nothing in the sheet covers the request. Recall on scripted violations: `scripts/guardrail_recall.py`; held-out sets r3/r4; white-box probes r5–r10 (`scripts/guardrail_probe_r5.py`, `_r6.py` … `_r10.py`). |
| `cair/figures.py` | What a figure is, the typed pools of sourced values, and when two match (equal at the precision shown). Shared by the guardrail and the scorer. |
| `cair/reconcile.py` | Receipt check: MCP read-back of the plan's `fee_calc` span, full or partial comparison, EVALUATOR span over HTTP. Each MCP_TOOL child carries its real `start` and `duration_ms`, and the search step its hit count. |
| `cair/neat.py` | HTTP `/v1/trace` writer and MCP client (Streamable HTTP, project key). |
| `cair/app.py`, `cair/view.py`, `cair/templates/` | FastAPI routes, per-IP and global daily rate limits (client IP from uvicorn proxy headers set by Caddy), HMAC-signed session/end-user/origin cookies, server-rendered plan card, `/verify`, `/rules`. |
| `cair/labels.py`, `cair/scoring.py`, `scripts/eval.py` | Frozen-set labels from the sheet, U/P/K/N scoring, the eval runner (v1 baseline lives only here). |

## Trace shape (one plan)

```
WORKFLOW payout-plan                inputs: plan id, payer, country, amount, rails, exchange, origin, question
 └─ AGENT planner
     ├─ TOOL platform_rails
     ├─ TOOL rail_eligibility        × each offered rail (USD payers; USDC payers use exchange_networks)
     ├─ RETRIEVER treaty_lookup      neatlogs.retriever.query / .documents
     ├─ TOOL fx_quote                (USD payers in IDR/INR/PHP; ERROR ×2 → TOOL fx_quote_fallback in a recovery run)
     ├─ TOOL exchange_networks       (USDC payers)
     ├─ TOOL fee_calc
     ├─ LLM qwen3.8-max              (wrapped OpenAI-compatible client)
     └─ GUARDRAIL provenance_guardrail   neatlogs.guardrail.passed / .score; verdict in the output
```

Session and end user are bound per request with `neatlogs.identify(session_id=…, end_user_id=<hashed cookie>,
end_user_metadata={"origin": …})`. Confirms and receipt checks are separate traces in the same session.

## Invariants (1–4 and 6 have tests in `tests/`; 5 is enforced by `eval.py` and `make_frozen_set.py --check`)

1. **Provenance** — every money amount, rate and treaty-article number in the explanation appears in a tool output of
   the same plan (on the card by construction; in the model's explanation through the rule-based guardrail, measured by
   the recall, held-out and probe scripts — the pool of sourced amounts has no currency) (`test_guardrail_blocks_unsourced_number`, `test_guardrail_allows_line_numbers`).
2. **Deliverability** — a REFUSED rail is never the recommendation (`test_refused_rail_never_recommended`).
3. **Line 10** — an article only when the sheet has a sourced article that covers the income; NONE → blank;
   otherwise UNCLEAR. Withholding only when the payer's own page says a W-8BEN applies
   (`test_line10_blank_without_article`, `test_line10_unclear_when_applicability_unsourced`,
   `test_no_withholding_unless_w8ben_applies`).
4. **UNCLEAR is terminal** — the model cannot upgrade an UNCLEAR line (on the card by construction; in the explanation through the guardrail, probes r5–r10; `test_unclear_landed_cannot_be_upgraded_by_the_llm`).
5. **Frozen set integrity** — `eval.py` refuses to run if `data/frozen_set.jsonl` differs from tag `frozen-set-v1`
   or the tag is missing.
6. **Public read-back is redacted** — `/verify` never shows span inputs or outputs or raw amounts: per plan it shows
   span names, kinds, status and durations read back over MCP, the guardrail verdict, the trace id, payer type,
   country, an amount band and a hashed-user prefix (`test_verify_has_no_raw_amounts`); `tests/test_boundary.py`
   adds that no public route returns a key or token.

Invariants 1–4 are also checked exhaustively: `tests/test_exhaustive.py` runs every payer × country × option set ×
amount band (2,448 scenarios) through the real planner and asserts them on each resulting card.

## Hosting

`uvicorn` behind Caddy (automatic HTTPS) on an AWS EC2 t3.small at `https://app.cair.edycu.dev`; secrets come from
an environment file outside the repository. neatlogs is
initialised once in the FastAPI lifespan and flushed once at shutdown.
