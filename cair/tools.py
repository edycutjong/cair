"""The agent's tools. Each is a neatlogs span (TOOL or RETRIEVER) whose captured output is the evidence the plan card
and the guardrail are allowed to use. Tools read the rules sheet, the treaty index and the ECB rate; none of them
calls the LLM, and none returns a value it cannot source.
"""
from __future__ import annotations

import contextvars
import json

import neatlogs

from . import calc, fx, rules, treaty

UNCLEAR = rules.UNCLEAR
# Forced failure for recovery runs (`eval.py --fail <tool>`); set per plan by the planner, never by a request.
FORCE_FAIL: contextvars.ContextVar[str | None] = contextvars.ContextVar("cair_force_fail", default=None)


class ToolFailure(RuntimeError):
    pass


def _maybe_fail(name: str) -> None:
    if FORCE_FAIL.get() == name:
        raise ToolFailure(f"{name} unavailable (forced failure injected for a recovery run)")


def _src(fact: rules.Fact | None, sheet: rules.Sheet) -> dict | None:
    if fact is None:
        return None
    d = fact.as_dict()
    if fact.source_id in sheet.quotes:
        d["quote"] = sheet.quotes[fact.source_id]["quote"][:400]
    return d


@neatlogs.span(kind="TOOL", tool_name="platform_rails",
               description="Rails this payer offers and whether a W-8BEN applies to it, from the payer's own page")
def platform_rails(payer: str) -> dict:
    _maybe_fail("platform_rails")
    sheet = rules.sheet()
    w8 = sheet.get("*", payer, "_payer", "w8ben_applies")
    return {"payer": payer, "known_payer": payer in rules.PAYERS, "offered_rails": sheet.offered_rails(payer),
            "w8ben_applies": w8.value if w8 else UNCLEAR, "w8ben_source": _src(w8, sheet)}


@neatlogs.span(kind="TOOL", tool_name="rail_eligibility",
               description="Can this rail receive money for a resident of this country? YES / NO / UNCLEAR, sourced")
def rail_eligibility(country: str, payer: str, rail: str) -> dict:
    _maybe_fail("rail_eligibility")
    sheet = rules.sheet()
    fact = sheet.get(country, payer, rail, "deliverable")
    value = fact.value if fact and fact.value in {"YES", "NO", UNCLEAR} else UNCLEAR
    return {"country": country, "rail": rail, "deliverable": value, "source": _src(fact, sheet) if value != UNCLEAR or fact else None}


def treaty_lookup(country: str, query: str = treaty.QUERY) -> dict:
    """RETRIEVER span: the country's US-treaty position from the sheet + the nearest treaty articles by BM25."""
    with neatlogs.trace("treaty_lookup", kind="RETRIEVER") as sp:
        sp.set_attribute("neatlogs.retriever.query", query)
        _maybe_fail("treaty_lookup")
        sheet = rules.sheet()
        art = sheet.get(country, "*", "_treaty", "treaty_other_income_article")
        wh = sheet.get(country, "*", "_treaty", "withholding_default")
        hits = treaty.nearest(country, query)
        out = {"country": country,
               "other_income_article": art.value if art else UNCLEAR, "article_source": _src(art, sheet),
               "withholding_default": wh.value if wh else UNCLEAR, "withholding_source": _src(wh, sheet),
               **hits}
        sp.set_attribute("neatlogs.retriever.documents", json.dumps(hits.get("nearest", [])))
        sp.set_attribute("neatlogs.retriever.output", json.dumps(out)[:4000])
        return out


@neatlogs.span(kind="TOOL", tool_name="fx_quote", description="ECB daily reference rate USD -> local currency")
def fx_quote(quote_ccy: str) -> dict:
    _maybe_fail("fx_quote")
    return fx.live(quote_ccy)


@neatlogs.span(kind="TOOL", tool_name="fx_quote_fallback",
               description="Recovery: last ECB rate this server fetched, with its as_of date, stamped stale")
def fx_quote_fallback(quote_ccy: str, error: str) -> dict:
    hit = fx.cached(quote_ccy)
    if hit is None:
        return {"quote": quote_ccy, "rate": UNCLEAR, "as_of": None, "stale": True,
                "reason": f"live ECB rate failed ({error}) and no earlier snapshot exists"}
    return {**hit, "reason": f"live ECB rate failed ({error}); using the last fetched ECB rate"}


@neatlogs.span(kind="TOOL", tool_name="exchange_networks",
               description="Does this exchange accept USDC deposits on this network? From the exchange's own page")
def exchange_networks(exchange: str, chain: str) -> dict:
    _maybe_fail("exchange_networks")
    sheet = rules.sheet()
    rows = sheet.exchange_rows(exchange) if exchange in rules.EXCHANGES else {}
    hit = rows.get(chain)
    return {"exchange": exchange, "chain": chain, "deliverable": hit.value if hit else UNCLEAR,
            "source": _src(hit, sheet),
            "sourced_yes_networks": sorted(c for c, f in rows.items() if f.value == "YES"),
            "always": "Send a small test transaction first and check the network on the exchange's deposit screen."}


@neatlogs.span(kind="TOOL", tool_name="fee_calc",
               description="Deterministic Decimal arithmetic: withholding, fees, FX, what lands")
def fee_calc(gross: str, unit: str, w8ben_applies: str, withholding_default: str | None,
             receiving_fee_usd: str | None, fx_margin_pct: str | None, fx_rate: str | None, local_ccy: str) -> dict:
    _maybe_fail("fee_calc")
    return calc.fee_calc(gross, unit, w8ben_applies, withholding_default, receiving_fee_usd, fx_margin_pct,
                         fx_rate, local_ccy)
