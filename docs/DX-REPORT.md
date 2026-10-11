# Neatlogs DX report

A friction log kept while building Cair. Each entry is something verified against the live service, with the date.

## 2026-10-10 — first hour

| What | Result |
|---|---|
| SDK version | `neatlogs` 1.4.26 from PyPI, Python 3.12 |
| `neatlogs.identify` | It is a **context manager**: `identify(session_id=None, end_user_id=None, end_user_metadata=None)`. Its signature lives on `/sdk/sessions`, which the Python SDK page only links to. |
| `extract_trace_context` | In 1.4.26 it accepts `session_id`, `end_user_id`, `end_user_metadata` only. The Python SDK page also shows `parent_session_id` and `session_custom_fields`; passing them raises `TypeError` in this version. Cair puts `origin` in `end_user_metadata` instead. |
| Trace id from inside a span | `with neatlogs.trace(...) as sp` yields an OpenTelemetry span, so `format(sp.get_span_context().trace_id, "032x")` is the same 32-hex id that the MCP server and dashboard use. |
| `@span(kind="WORKFLOW")` input capture | The decorated function's arguments are stored as the root span input and are found by MCP `search_traces` (keyword mode) — a plan id passed as an argument is enough to find the trace later. |
| LLM span with a non-OpenAI `base_url` | `neatlogs.wrap(OpenAI(base_url=<Qwen Cloud compatible endpoint>))` records an LLM span named after the model, with prompt/completion tokens. Cost reads 0 for this model. |
| MCP server | Streamable HTTP at `https://ingest.neatlogs.com/mcp` with the project key as a Bearer token. `whoami`, `ping` and `get_trace_context` work from the Python `mcp` 2.3 client (which now takes an `httpx2.AsyncClient` for headers and returns snake_case fields such as `input_schema` and `structured_content`). |
| MCP tools beyond the docs page | The server lists 24 tools; besides the ones on the MCP page it exposes `create_detection`, `preview_detection`, `list_detection_groups`, `create_detection_group`, `triage_list_versions`, `triage_get_version` and `triage_restore_version`. |
| `get_trace_context` GUARDRAIL attributes | The span tree returns `name`, `type`, `status`, `duration_ms`, input/output text — but not `neatlogs.guardrail.passed`/`score`. To read a guardrail verdict back, Cair also writes the verdict into the span output. |
| HTTP `POST /v1/trace` with an `nlw_` key | `project` must be the project's **display name** (from MCP `whoami`), not its id. An `EVALUATOR` child is stored with `type: evaluator`. Object inputs are flattened to `Key: value` text and `"4900.00"` reads back as `4900`, so Cair sends JSON strings where exact decimals matter. |

## Entire — what did not work for this repository (moved from the README, 2026-10-11)

- `impact` on `rail_eligibility`, run before the unlisted-country fix, reports 0 callers — probably because the planner
  passes the tools as function values (`att.call("fx_quote", tools.fx_quote, …)`), which the graph does not follow.
- `impact` on `fee_calc` and `figures.extract` returned only symbol-disambiguation lists.
  Outputs: `evidence/entire/impact-*.txt`.
