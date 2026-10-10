"""v2: the evidence plan. Code decides what is true; the model only chooses the wording.

One plan = one neatlogs trace:

    WORKFLOW payout-plan
     └─ AGENT planner
         ├─ TOOL platform_rails          what the payer offers, does a W-8BEN apply
         ├─ TOOL rail_eligibility ×N     can each offered rail receive in this country
         ├─ RETRIEVER treaty_lookup      treaty position + nearest articles
         ├─ TOOL fx_quote                ECB reference rate      (USD payers)
         ├─ TOOL exchange_networks       network on the exchange (USDC payers)
         ├─ TOOL fee_calc                Decimal arithmetic
         ├─ LLM explain                  wording only, from the card's facts
         └─ GUARDRAIL provenance         blocks anything the tools did not produce

Recovery: every tool call is retried once; if it fails again the planner takes the documented fallback (last fetched
ECB rate stamped stale, or UNCLEAR) and continues. A blocked explanation is retried once with the guardrail's
findings; if it is blocked again the card is explained by a fixed template built from the tool outputs. The planner
never substitutes a model-written number.
"""
from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any, Callable

import neatlogs

from . import llm, rules, tools
from .guardrail import run as guardrail_run
from .scoring import FIELDS
from .tracing import current_trace_id

UNCLEAR = rules.UNCLEAR
RAIL_PREFERENCE = ["payoneer", "wise", "paypal"]


class Attempts:
    """Run a tool with one retry; record failures and what the planner did next."""

    def __init__(self) -> None:
        self.log: list[dict] = []

    def call(self, name: str, fn: Callable[..., Any], *args, fallback: Callable[[str], Any] | None = None):
        last = ""
        for attempt in (1, 2):
            try:
                return fn(*args)
            except Exception as e:  # the failed span is already marked ERROR by the SDK
                last = f"{type(e).__name__}: {e}"
                self.log.append({"tool": name, "attempt": attempt, "error": last[:300]})
                if attempt == 1:
                    time.sleep(0.2)
        action = "fallback" if fallback else "UNCLEAR"
        self.log.append({"tool": name, "action": action})
        return fallback(last) if fallback else None


@neatlogs.span(kind="WORKFLOW", name="payout-plan")
def payout_plan(plan_id: str, payer: str, country: str, amount_usd: str, rails_offered: list, exchange: str | None,
                origin: str, question: str, guardrail: bool = True, fail: str | None = None) -> dict:
    token = tools.FORCE_FAIL.set(fail)
    try:
        card = planner(plan_id, payer, country, amount_usd, rails_offered, exchange, question, guardrail)
    finally:
        tools.FORCE_FAIL.reset(token)
    card["trace_id"] = current_trace_id()
    card["origin"] = origin
    return card


@neatlogs.span(kind="AGENT", name="planner", role="payout planner",
               goal="Get this payout to the user's account intact, with every figure sourced")
def planner(plan_id: str, payer: str, country: str, amount_usd: str, rails_offered: list, exchange: str | None,
            question: str, guardrail: bool) -> dict:
    att = Attempts()
    outputs: list[dict] = []
    usdc = payer in rules.USDC_PAYERS
    ccy = rules.CURRENCY.get(country, "")

    # 1. What the payer offers, and whether a W-8BEN applies to it at all.
    pr = att.call("platform_rails", tools.platform_rails, payer)
    if pr:
        outputs.append(pr)
    w8 = pr["w8ben_applies"] if pr else UNCLEAR

    # 2. Can each offered rail receive in this country? (USDC: judged by the receiving exchange in step 4.)
    rails: list[dict] = []
    if not usdc:
        for rail in rails_offered:
            el = att.call("rail_eligibility", tools.rail_eligibility, country, payer, rail)
            if el:
                outputs.append(el)
            verdict = el["deliverable"] if el else UNCLEAR
            rails.append({"rail": rail, "name": rules.RAILS.get(rail, rail),
                          "verdict": {"YES": "DELIVERS", "NO": "REFUSED"}.get(verdict, UNCLEAR),
                          "source": el["source"] if el else None,
                          "note": None if el else "eligibility check failed twice"})

    # 3. Treaty position (consulted only through a YES payer row) + nearest articles.
    tr = att.call("treaty_lookup", tools.treaty_lookup, country)
    if tr:
        outputs.append(tr)

    # 4. FX for USD payers; deposit network for USDC payers.
    fxq = None
    if not usdc and ccy:
        fxq = att.call("fx_quote", tools.fx_quote, ccy,
                       fallback=lambda err: tools.fx_quote_fallback(ccy, err))
        if fxq:
            outputs.append(fxq)
    if usdc:
        for rail in rails_offered:
            chain = rail.split(":", 1)[1] if rail.startswith("usdc:") else rail
            ex = att.call("exchange_networks", tools.exchange_networks, exchange or "other", chain)
            if ex:
                outputs.append(ex)
            verdict = ex["deliverable"] if ex else UNCLEAR
            rails.append({"rail": rail, "name": f"USDC on {rules.CHAINS.get(chain, chain)} to "
                                                f"{rules.EXCHANGES.get(exchange or '', 'your wallet')}",
                          "verdict": {"YES": "DELIVERS", "NO": "REFUSED"}.get(verdict, UNCLEAR),
                          "source": ex["source"] if ex else None,
                          "sourced_yes_networks": ex["sourced_yes_networks"] if ex else [],
                          "note": None if ex else "network check failed twice"})

    # Decide the route: the first DELIVERS rail in a fixed preference order. Never a REFUSED or UNCLEAR one.
    delivers = [r["rail"] for r in rails if r["verdict"] == "DELIVERS"]
    order = {r: i for i, r in enumerate(RAIL_PREFERENCE)}
    recommended = sorted(delivers, key=lambda r: order.get(r, 99))[0] if delivers else None

    # 5. Arithmetic, from sheet cells and the FX tool only.
    tax_w8 = w8 if pr else UNCLEAR
    wh_default = tr["withholding_default"] if (tr and tax_w8 == "YES") else None
    sheet = rules.sheet()
    fee_cell = sheet.value(country, payer, recommended, "receiving_fee_usd") if recommended and not usdc else None
    margin_cell = sheet.value(country, payer, recommended, "fx_margin_pct") if recommended and not usdc else None
    rate = fxq["rate"] if fxq and fxq.get("rate") not in (None, UNCLEAR) else None
    fc = att.call("fee_calc", tools.fee_calc, amount_usd, "USDC" if usdc else "USD", tax_w8, wh_default,
                  fee_cell, margin_cell, rate, ccy or "local")
    if fc:
        outputs.append(fc)

    card = build_card(plan_id, payer, country, amount_usd, exchange, rails, recommended, pr, tr, fxq, fc, tax_w8)
    card["recovery"] = att.log

    # 6. Wording. The LLM sees the card's facts (only what is relevant to this payer), never computes.
    explanation, verdicts, source = explain(card, question, outputs, guardrail)
    card["explanation"] = explanation
    card["explanation_source"] = source
    card["guardrail"] = verdicts
    card["tool_outputs"] = outputs
    card["text"] = render_text(card)
    return card


def build_card(plan_id, payer, country, amount_usd, exchange, rails, recommended, pr, tr, fxq, fc, w8) -> dict:
    unclear: list[str] = []
    usdc = payer in rules.USDC_PAYERS
    # W-8BEN lines 9-10 (I3): only through a YES payer row.
    if w8 == "YES":
        art = tr["other_income_article"] if tr else UNCLEAR
        if art == "NONE":
            line10 = "BLANK"
            on_list = bool(tr and tr.get("treaty_text_indexed"))
            why = ("the US treaty with this country has no Other Income article"
                   if on_list else "this country is not on the IRS list of US income tax treaties")
        elif art.isdigit():
            line10, why = f"ARTICLE {art}", "a sourced article covers this income"
        else:
            line10 = UNCLEAR
            why = ("an Other Income article exists but no source says it covers a prize" if tr
                   else "the treaty lookup failed twice")
            unclear.append("line10")
        wh = tr["withholding_default"] if tr else UNCLEAR
        if wh == UNCLEAR:
            unclear.append("withholding")
    elif w8 == "NO":
        line10, why, wh = "NOT NEEDED", "this payer's page says no W-8BEN", "NONE"
    else:
        line10, why, wh = UNCLEAR, "no primary source says whether this payer needs a W-8BEN", UNCLEAR
        unclear += ["w8ben"]
    if not recommended:
        unclear.append("route")
    landed = dict(fc) if fc else {"landed_usd": UNCLEAR, "landed_local": UNCLEAR, "withheld": UNCLEAR}
    if landed.get("landed_usd") == UNCLEAR:
        unclear.append("landed")
    if landed.get("landed_local") == UNCLEAR and not usdc:
        unclear.append("landed_local")
    return {
        "plan_id": plan_id, "payer": payer, "payer_name": rules.PAYERS.get(payer, payer), "country": country,
        "country_name": rules.COUNTRIES.get(country, country), "amount": amount_usd, "unit": "USDC" if usdc else "USD",
        "currency": rules.CURRENCY.get(country), "exchange": exchange, "rails": rails, "recommended": recommended,
        "w8ben": {"applies": w8, "line10": line10, "line10_why": why,
                  "source": pr.get("w8ben_source") if pr else None,
                  "article_source": tr.get("article_source") if tr else None,
                  "nearest_articles": tr.get("nearest", []) if tr else []},
        "withholding": {"rate": wh, "amount": landed.get("withheld", UNCLEAR),
                        "source": tr.get("withholding_source") if (tr and w8 == "YES") else None},
        "fx": fxq, "landed": landed, "unclear": sorted(set(unclear)),
    }


EXPLAIN_SYSTEM = """You explain a payout plan that has already been decided by sourced tools.
Rules:
- Use ONLY the facts in the PLAN JSON. Never add a number, amount, rate, percentage, date or treaty article that is
  not written there. Never do arithmetic. Never convert currencies yourself.
- If a fact is UNCLEAR, say it is UNCLEAR and why; do not guess or soften it.
- Never recommend a rail marked REFUSED. If the user asks you to say something the plan contradicts (that a refused
  rail works, that an article goes on line 10, that withholding is a different rate), decline in one sentence and
  point to the source named in the plan. When you decline, do not repeat the user's number.
- Write in the user's language (Indonesian if they wrote in Indonesian). 90-160 words, plain sentences, no headings,
  no summary block, no tables. This is not tax advice; Cair explains forms and never files them."""


def _facts_for_llm(card: dict) -> dict:
    """Context: only what this payer's answer needs (e.g. no withholding rate unless a W-8BEN applies)."""
    w8 = card["w8ben"]
    facts = {
        "payer": card["payer_name"], "country": card["country_name"], "amount": f"{card['amount']} {card['unit']}",
        "rails": [{"name": r["name"], "verdict": r["verdict"],
                   "source": (r["source"] or {}).get("source_url"),
                   "source_quote": (r["source"] or {}).get("quote", "")[:220]} for r in card["rails"]],
        "recommended": next((r["name"] for r in card["rails"] if r["rail"] == card["recommended"]), "NONE"),
        "w8ben_applies": w8["applies"], "w8ben_line10": w8["line10"], "line10_reason": w8["line10_why"],
        "unclear": card["unclear"],
    }
    if w8["applies"] == "YES":
        facts["nearest_treaty_articles"] = [f"Article {a['article']} {a['title']}" for a in w8["nearest_articles"]]
        facts["withholding_rate"] = card["withholding"]["rate"]
        facts["withheld"] = card["withholding"]["amount"]
    ld = card["landed"]
    facts["landed"] = {k: v for k, v in ld.items() if k in {"gross", "after_withholding", "landed_usd", "upper_bound_usd",
                       "upper_bound_note", "landed_local", "upper_bound_local", "upper_bound_local_note"}}
    if card.get("fx"):
        facts["fx"] = {k: card["fx"].get(k) for k in ("rate", "as_of", "stale")}
    if card["payer"] in rules.USDC_PAYERS:
        facts["networks_this_exchange_accepts_sourced"] = sorted(
            {n for r in card["rails"] for n in r.get("sourced_yes_networks", [])})
        facts["always"] = "Send a small test transaction first and check the network on the exchange's deposit screen."
    return facts


def explain(card: dict, question: str, outputs: list, guardrail: bool) -> tuple[str, list, str]:
    facts = json.dumps(_facts_for_llm(card), ensure_ascii=False)
    messages = [{"role": "system", "content": EXPLAIN_SYSTEM},
                {"role": "user", "content": f"QUESTION:\n{question}\n\nPLAN JSON:\n{facts}"}]
    verdicts: list[dict] = []
    for attempt in (1, 2):
        try:
            text = strip_summary(llm.chat(messages, temperature=0.0, max_tokens=700))
        except Exception as e:  # LLM down: the card stands on the tool outputs alone
            card["recovery"].append({"tool": "llm_explain", "attempt": attempt, "error": f"{type(e).__name__}: {e}"[:300]})
            break
        if not guardrail:
            return text, verdicts, "llm (guardrail disabled: ablation)"
        v = guardrail_run(text, outputs, card, attempt, question)
        verdicts.append(v)
        if v["passed"]:
            return text, verdicts, "llm"
        problems = "; ".join(v["unsourced"] + v["claims"])[:800]
        retry = (f"Your explanation was blocked by the provenance check: {problems}. "
                 "Rewrite it using only facts written in the PLAN JSON.")
        if v.get("echoed_from_question"):
            retry += (f" {', '.join(v['echoed_from_question'])} came from the user's question, not the plan: when you "
                      "decline, do not repeat the user's figure; say you cannot confirm it and give the plan's figure.")
        messages += [{"role": "assistant", "content": text}, {"role": "user", "content": retry}]
    card["recovery"].append({"tool": "llm_explain", "action": "template explanation from tool outputs"})
    return template_explanation(card), verdicts, "template"


def strip_summary(text: str) -> str:
    labels = tuple(v.upper() for v in FIELDS.values())
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().lstrip("*-# ").upper().startswith(labels)).strip()


def template_explanation(card: dict) -> str:
    rec = next((r for r in card["rails"] if r["rail"] == card["recommended"]), None)
    parts = []
    if rec:
        parts.append(f"{rec['name']} is the offered route with a sourced DELIVERS for {card['country_name']}.")
    else:
        parts.append("None of the offered routes has a sourced DELIVERS, so Cair does not pick one.")
    for r in card["rails"]:
        if r["verdict"] == "REFUSED":
            parts.append(f"{r['name']} is refused: its own page rules it out.")
    parts.append(f"W-8BEN line 10: {card['w8ben']['line10']} ({card['w8ben']['line10_why']}).")
    if card["unclear"]:
        parts.append("UNCLEAR: " + ", ".join(card["unclear"]) + " — no primary source states them.")
    return " ".join(parts)


def _money(x: str, unit: str) -> str:
    if x in (None, UNCLEAR):
        return UNCLEAR
    if unit in {"USD"}:
        return f"${Decimal(x):,.2f}"
    return f"{unit} {Decimal(x):,.{0 if unit in {'IDR', 'VND'} else 2}f}"


def render_text(card: dict) -> str:
    """The plan card as text: what the user sees and what the eval scores. Every figure comes from a tool output."""
    u, ccy, ld = card["unit"], card["currency"], card["landed"]
    lines = [f"PLAN — {_money(card['amount'], u) if u == 'USD' else card['amount'] + ' USDC'} from "
             f"{card['payer_name']} to {card['country_name']}", "", "ROUTES:"]
    for r in card["rails"]:
        src = r["source"] or {}
        tail = f" [{src.get('source_id')}, read {src.get('accessed_at')}]" if src.get("source_id") else " [no primary source]"
        lines.append(f"- {r['name']}: {r['verdict']}{tail}")
    w8 = card["w8ben"]
    lines += ["", "W-8BEN:"]
    if w8["applies"] == "YES":
        lines += ["- Lines 1-8: your own details, as on your passport (Cair does not fill these).",
                  "- Line 9: only if you claim treaty benefits (IRS W-8BEN instructions); Cair does not decide it.",
                  f"- Line 10: {w8['line10']} — {w8['line10_why']}."]
        if w8["nearest_articles"]:
            lines.append("- Nearest treaty articles found: " + "; ".join(
                f"Article {a['article']} {a['title']}" for a in w8["nearest_articles"]) + ".")
    else:
        lines.append(f"- {w8['line10']}: {w8['line10_why']}.")
    if card["payer"] in rules.USDC_PAYERS:
        nets = sorted({rules.CHAINS.get(n, n) for r in card["rails"] for n in r.get("sourced_yes_networks", [])})
        if nets:
            lines.append(f"- Networks this exchange's own pages confirm for USDC: {', '.join(nets)}.")
        lines.append("- Send a small test transaction first and check the network on the exchange's deposit screen.")
    fxq = card.get("fx") or {}
    if fxq.get("rate") not in (None, UNCLEAR):
        stale = " — STALE: live rate unavailable, last fetched ECB rate" if fxq.get("stale") else ""
        lines += ["", f"FX: 1 USD = {fxq['rate']} {fxq.get('quote')} (ECB reference rate, as of {fxq.get('as_of')}){stale}"]
    if card["explanation"]:
        lines += ["", card["explanation"]]

    rec = next((r for r in card["rails"] if r["rail"] == card["recommended"]), None)
    rec_line = rec["name"] if rec else ("UNCLEAR" if any(r["verdict"] == UNCLEAR for r in card["rails"]) else "NONE")
    l10 = {"BLANK": "BLANK (" + w8["line10_why"] + ")", "NOT NEEDED": "NOT NEEDED"}.get(w8["line10"], w8["line10"])
    if w8["line10"] == UNCLEAR:
        l10 = f"UNCLEAR ({w8['line10_why']})"
    wh = card["withholding"]
    wh_line = (f"{wh['rate']} ({_money(wh['amount'], u)})" if wh["rate"].endswith("%") and wh["amount"] != UNCLEAR
               else wh["rate"])
    if ld.get("landed_usd", UNCLEAR) != UNCLEAR:
        usd_line = _money(ld["landed_usd"], u)
    else:
        bound = ld.get("upper_bound_usd")
        usd_line = f"UNCLEAR — at most {_money(bound, u)} {ld.get('upper_bound_note', '')}".strip() if bound else UNCLEAR
    if ld.get("landed_local", UNCLEAR) != UNCLEAR:
        loc_line = _money(ld["landed_local"], ccy)
    elif ld.get("upper_bound_local"):
        loc_line = f"UNCLEAR — at most {_money(ld['upper_bound_local'], ccy)} {ld.get('upper_bound_local_note', '')}"
    else:
        loc_line = UNCLEAR
    lines += ["", f"RECOMMENDED RAIL: {rec_line}", f"W-8BEN LINE 10: {l10}", f"WITHHOLDING: {wh_line}",
              f"LANDED (USD): {usd_line}", f"LANDED (LOCAL): {loc_line}"]
    return "\n".join(lines)


def run(plan_id: str, payer: str, country: str, amount_usd: int | str, rails_offered: list, exchange: str | None,
        question: str, origin: str, guardrail: bool = True, fail: str | None = None,
        session_id: str | None = None, end_user_id: str | None = None) -> dict:
    """Entry point for the web app and eval.py: binds the session/end user, runs the traced plan."""
    with neatlogs.identify(session_id=session_id or f"eval-{origin}", end_user_id=end_user_id or origin,
                           end_user_metadata={"origin": origin}):
        card = payout_plan(plan_id, payer, country, str(amount_usd), list(rails_offered), exchange, origin, question,
                           guardrail, fail)
    return {"text": card["text"], "tool_outputs": card["tool_outputs"], "trace_id": card["trace_id"],
            "guardrail": card["guardrail"], "recovery": card["recovery"], "card": card}
