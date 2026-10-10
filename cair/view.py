"""View models for the templates: input validation, the plan card with its footnotes, /rules, /verify."""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation

from . import config, neat, rules

UNCLEAR = rules.UNCLEAR
OTHER = "OTHER"


def form_options(card: dict | None = None) -> dict:
    return {"payers": rules.PAYERS, "countries": {**rules.COUNTRIES, OTHER: "Somewhere else (not in the rules sheet)"},
            "rails": rules.RAILS, "chains": rules.CHAINS, "exchanges": {**rules.EXCHANGES, "other": "Self-custody / other"},
            "usdc_payers": sorted(rules.USDC_PAYERS), "prefill": card}


def validate(body: dict) -> dict:
    payer = str(body.get("payer", ""))
    if payer not in rules.PAYERS:
        raise ValueError("Pick who is paying you.")
    country = str(body.get("country", ""))
    if country not in rules.COUNTRIES and country != OTHER:
        raise ValueError("Pick where you live.")
    try:
        amount = Decimal(str(body.get("amount", "")).replace(",", "").strip())
    except InvalidOperation:
        raise ValueError("Enter the amount in USD, e.g. 7000.") from None
    if not (Decimal(1) <= amount <= Decimal(1_000_000)):
        raise ValueError("Enter an amount between 1 and 1,000,000.")
    amount = amount.quantize(Decimal("0.01"))
    exchange = None
    if payer in rules.USDC_PAYERS:
        chain = str(body.get("chain", ""))
        if chain not in rules.CHAINS:
            raise ValueError("Pick the network your organizer pays on (it is in the event's rules).")
        exchange = str(body.get("exchange", "other"))
        if exchange not in rules.EXCHANGES and exchange != "other":
            raise ValueError("Pick where you will receive the USDC.")
        rails = [f"usdc:{chain}"]
    else:
        rails = [r for r in body.get("rails", []) if r in rules.RAILS]
        if not rails:
            raise ValueError("Tick the payout options your form shows you.")
    question = str(body.get("question", "")).strip()[:500]
    if not question:
        where = rules.COUNTRIES.get(country, "a country Cair has no sources for")
        offered = ", ".join(rules.RAILS.get(r, r) for r in rails) if not exchange else (
            f"USDC on {rules.CHAINS[rails[0][5:]]} to {rules.EXCHANGES.get(exchange, 'my own wallet')}")
        question = (f"I live in {where}. {rules.PAYERS[payer]} is paying me ${amount:,.2f}. "
                    f"The form offers: {offered}. Which option should I pick, what goes on the tax form, "
                    f"and how much lands?")
    return {"payer": payer, "country": country, "amount": str(amount), "rails": rails, "exchange": exchange,
            "question": question}


def _short(url: str | None) -> str:
    if not url:
        return ""
    u = url.split("://", 1)[-1]
    return u if len(u) <= 60 else u[:57] + "…"


def card_view(card: dict, confirmed: list[str], receipts: list) -> dict:
    notes: list[dict] = []

    def note(tool: str, src: dict | None, extra: str = "") -> int | None:
        if not src and not extra:
            return None
        entry = {"tool": tool, "id": (src or {}).get("source_id", ""), "url": (src or {}).get("source_url", ""),
                 "short": _short((src or {}).get("source_url")), "accessed": (src or {}).get("accessed_at", ""),
                 "quote": (src or {}).get("quote", ""), "extra": extra}
        for i, n in enumerate(notes, 1):
            if (n["tool"], n["id"], n["extra"]) == (entry["tool"], entry["id"], entry["extra"]):
                return i
        notes.append(entry)
        return len(notes)

    usdc = card["payer"] in rules.USDC_PAYERS
    rails = []
    for r in card["rails"]:
        rails.append({**r, "fn": note("exchange_networks" if usdc else "rail_eligibility", r.get("source")),
                      "recommended": r["rail"] == card["recommended"]})
    w8 = card["w8ben"]
    w8_fn = note("platform_rails", w8.get("source"))
    l10_fn = note("treaty_lookup", w8.get("article_source")) if w8["applies"] == "YES" else None
    wh = card["withholding"]
    wh_fn = note("treaty_lookup", wh.get("source")) if wh.get("source") else None
    ld = card["landed"]
    calc_fn = note("fee_calc", None, "Decimal arithmetic on the cells above; no figure comes from the model")
    fxq = card.get("fx") or {}
    fx_fn = None
    if fxq.get("rate") not in (None, UNCLEAR):
        fx_fn = note("fx_quote_fallback" if fxq.get("stale") else "fx_quote", None,
                     f"ECB reference rate via api.frankfurter.dev, as of {fxq.get('as_of')}"
                     + (" — STALE: the live call failed, this is the last rate fetched" if fxq.get("stale") else ""))

    unit, ccy = card["unit"], card.get("currency") or ""

    def money(x, u):
        if x in (None, UNCLEAR, ""):
            return None
        d = Decimal(x)
        if u == "USD":
            return f"${d:,.2f}"
        return f"{u} {d:,.{0 if u in {'IDR', 'VND'} else 2}f}"

    landed = {
        "gross": money(ld.get("gross"), unit) or f"{card['amount']} {unit}",
        "withheld": money(ld.get("withheld"), unit), "withheld_unclear": ld.get("withheld") == UNCLEAR,
        "usd": money(ld.get("landed_usd"), unit), "usd_bound": money(ld.get("upper_bound_usd"), unit),
        "usd_bound_note": ld.get("upper_bound_note", ""),
        "local": money(ld.get("landed_local"), ccy), "local_bound": money(ld.get("upper_bound_local"), ccy),
        "local_bound_note": ld.get("upper_bound_local_note", ""), "calc_fn": calc_fn, "fx_fn": fx_fn,
    }
    guard = card.get("guardrail") or []
    last = guard[-1] if guard else None
    return {"card": card, "rails": rails, "w8": w8, "w8_fn": w8_fn, "l10_fn": l10_fn, "wh": wh, "wh_fn": wh_fn,
            "landed": landed, "fx": fxq, "notes": notes, "usdc": usdc, "confirmed": set(confirmed),
            "confirmable": confirmable(card), "receipts": [stamp_view(dict(r)) for r in receipts],
            "guard": last, "guard_attempts": len(guard), "recovery": card.get("recovery") or [],
            "rec_name": next((r["name"] for r in card["rails"] if r["rail"] == card["recommended"]), None)}


def confirmable(card: dict) -> dict:
    out = {}
    rec = next((r["name"] for r in card["rails"] if r["rail"] == card["recommended"]), None)
    if rec:
        out["rail"] = rec
    w8 = card["w8ben"]
    if w8["applies"] == "YES" and w8["line10"] != UNCLEAR:
        out["line10"] = "leave blank" if w8["line10"] == "BLANK" else w8["line10"]
    return out


def stamp_view(r: dict) -> dict:
    mode = r.get("mode")
    if mode == "full":
        title = f"LANDED · quoted {r.get('quoted')} · received {r.get('landed') or r.get('landed_amount')} · Δ {r.get('error_pct')}%"
    elif mode == "partial":
        unexplained = r.get("unexplained_usd") or r.get("unexplained")
        title = (f"LANDED · at most {r.get('quoted_upper') or r.get('quoted')} quoted · received "
                 f"{r.get('landed') or r.get('landed_amount')} · {unexplained} not explained by the sourced rules")
    else:
        title = f"RECEIVED · {r.get('landed') or r.get('landed_amount')} {r.get('currency') or r.get('landed_currency')} · not compared"
    return {"title": title, "verdict": r.get("verdict"), "mode": mode, "label": r.get("label"),
            "partial": mode == "partial", "trace": r.get("evaluator_trace_id"),
            "source": r.get("quote_source", "")}


def rules_rows(sheet: rules.Sheet) -> list[dict]:
    rows = []
    with open(config.DATA / "rules_sheet.csv") as f:
        for row in csv.DictReader(f):
            q = sheet.quotes.get(row["source_id"], {})
            rows.append({**row, "quote": q.get("quote", "")[:300], "short": _short(row["source_url"])})
    return rows


def band(amount: str) -> str:
    a = Decimal(amount)
    return "< $1k" if a < 1000 else ("$1k–5k" if a <= 5000 else "> $5k")


def verify_rows(plans: list) -> tuple[list[dict], str]:
    """Redacted projection (I7): span names, kinds, status, durations and the guardrail verdict — never span bodies,
    never raw amounts. Read back from neatlogs over MCP; if that fails, the same columns from our DB copy."""
    import json

    tids = [p["trace_id"] for p in plans if p["trace_id"]]
    ctxs: dict[str, dict] = {}
    source = "Read back from neatlogs (MCP get_trace_context)"
    try:
        if tids:
            res = neat.mcp([("get_trace_context", {"trace_id": t}) for t in tids], timeout=45)
            ctxs = {t: r for t, r in zip(tids, res) if isinstance(r, dict)}
    except Exception:
        source = "DB copy — neatlogs read-back unavailable right now"
    rows = []
    for p in plans:
        card = json.loads(p["card_json"])
        guard = card.get("guardrail") or []
        ctx = ctxs.get(p["trace_id"] or "")
        spans = []
        if ctx:
            for s in ctx.get("spans", []):
                spans.append({"name": s.get("name"), "kind": s.get("type"), "status": s.get("status"),
                              "ms": round(float(s.get("duration_ms") or 0))})
        rows.append({
            "plan": p["id"][-8:], "created": p["created_at"], "payer": p["payer"], "country": p["country"],
            "band": band(p["amount_usd"]), "user": p["end_user_hash"][:8], "origin": p["origin"],
            "guardrail": ("PASSED" if guard[-1]["passed"] else "BLOCKED") if guard else "—",
            "attempts": len(guard), "trace": p["trace_id"], "spans": spans,
            "readback": bool(ctx), "span_count": ctx.get("span_count") if ctx else None,
            "recoveries": len([r for r in card.get("recovery", []) if "action" in r]),
        })
    return rows, source
