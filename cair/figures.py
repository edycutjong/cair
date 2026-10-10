"""What counts as a figure, and how two figures are compared.

A figure is a money amount, a rate/percentage or a treaty-article number. Line numbers, form names, years, dates,
ordinals and durations are not figures (allowlist below). Used by the provenance GUARDRAIL and by the scorer, so the
rule the agent is held to in production is the rule it is measured by.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Text that looks numeric but is not a claim about money, rates or treaty articles.
_ALLOW = [
    r"\bW-?8\s?BEN(?:-E)?\b", r"\bW-?9\b", r"\b1042-S\b", r"\bForm\s+\d+\b", r"\bPub(?:lication)?\.?\s*\d+\b",
    r"\b(?:line|lines|baris|part|bagian|step|langkah)s?\s*\d+(?:\s*(?:[-–]|to|and|dan|&)\s*\d+)?\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    # A year: not an amount like "2000.00 USD", "$2050" or "USD 2000" (rca-01: the year rule ate "2000.00 USD").
    r"(?<![$₹₱\d.,])(?<!USD )(?<!Rp )\b(?:19|20)\d{2}\b(?![.,]\d)(?!\s*(?:%|USD|IDR|INR|PHP|USDC|dollars?|rupiah))",
    r"\b\d+\s*(?:business\s+)?(?:days?|hari|weeks?|minggu|months?|bulan|hours?|jam|minutes?|menit)\b",
    r"\b\d+(?:st|nd|rd|th)\b", r"\bERC-?20\b", r"\bBEP-?20\b", r"\bTRC-?20\b", r"\b[A-Z]\d\b", r"\b\d{1,2}:\d{2}\b",
    r"\b(?:Q[1-4]|h\d+)\b", r"\bfrozen-set-v\d\b", r"\bv\d\b",
    r"\b1\s?(?:USD|USDC|US\$)\s?=",  # the unit side of an exchange rate ("1 USD = 17881 IDR")
]
ALLOW_RE = re.compile("|".join(_ALLOW), re.I)

_NUM = r"\d{1,3}(?:[,.\s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
MONEY_RE = re.compile(
    rf"(?:(?:US)?\$|USD|USDC|IDR|Rp\.?|INR|₹|PHP|₱)\s?({_NUM})(?:\s?(?:juta|million|jt))?"
    rf"|({_NUM})\s?(?:USD|USDC|IDR|INR|PHP|dollars?|dolar|rupiah)\b", re.I)
PCT_RE = re.compile(rf"({_NUM})\s?(?:%|percent|per cent|pct|persen)", re.I)
# A rate written in words is never in a tool output, so it is always a new figure.
WORD_PCT_RE = re.compile(r"\b(?:zero|nol|one|two|three|four|five|ten|fifteen|twenty|thirty|forty|fifty|satu|dua|tiga|lima|"
                         r"sepuluh|lima belas|dua puluh|tiga puluh)(?:[- ](?:one|two|five|puluh|belas))?\s?"
                         r"(?:%|percent|per cent|persen)", re.I)
ARTICLE_RE = re.compile(r"\b(?:article|art\.|pasal)\s*(\d{1,2})\b", re.I)
BARE_RE = re.compile(rf"(?<![\w.])({_NUM})(?![\w.])")


def _dec(raw: str) -> Decimal | None:
    s = raw.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):  # Indonesian 1.234.567,89
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", s):  # 4,5 (decimal comma)
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def extract(text: str) -> list[dict]:
    """Return figures in `text`: [{'kind': money|pct|article|number, 'value': Decimal|int, 'raw': str}]."""
    masked = ALLOW_RE.sub(lambda m: " " * len(m.group(0)), text)
    found: list[dict] = []
    spans: list[tuple[int, int]] = []

    def taken(a: int, b: int) -> bool:
        return any(a < y and x < b for x, y in spans)

    for m in ARTICLE_RE.finditer(text):  # articles are read from the unmasked text
        found.append({"kind": "article", "value": int(m.group(1)), "raw": m.group(0)})
        spans.append(m.span())
    for rx, kind in ((PCT_RE, "pct"), (MONEY_RE, "money")):
        for m in rx.finditer(masked):
            if taken(*m.span()):
                continue
            raw = next(g for g in m.groups() if g)
            val = _dec(raw)
            if val is None:
                continue
            if kind == "money" and re.search(r"juta|jt", m.group(0), re.I):
                val *= 1_000_000
            if kind == "money" and re.search(r"million", m.group(0), re.I):
                val *= 1_000_000
            found.append({"kind": kind, "value": val, "raw": m.group(0).strip()})
            spans.append(m.span())
    for m in WORD_PCT_RE.finditer(text):
        if not taken(*m.span()):
            found.append({"kind": "word", "value": m.group(0), "raw": m.group(0)})
            spans.append(m.span())
    for m in BARE_RE.finditer(masked):
        if taken(*m.span()):
            continue
        val = _dec(m.group(1))
        if val is None or val < 10:  # small bare integers are counts and list markers, not claims
            continue
        found.append({"kind": "number", "value": val, "raw": m.group(1)})
        spans.append(m.span())
    return found


ARTICLE_KEYS = {"article", "treaty_other_income_article", "other_income_article"}
MONEY_KEYS = {"gross", "withheld", "after_withholding", "landed_usd", "upper_bound_usd", "landed_local",
              "upper_bound_local", "rate", "fx_rate", "receiving_fee_usd", "amount", "amount_usd"}
PCT_KEYS = {"withholding_default", "fx_margin_pct", "withholding_rate"}


class Pools:
    """Typed values a plan's tools produced: money/plain numbers, percentages and treaty-article numbers.
    Only these named fields count — never BM25 scores, source ids, or numbers inside quoted page text."""

    def __init__(self) -> None:
        self.money: set[Decimal] = set()
        self.pct: set[Decimal] = set()
        self.arts: set[int] = set()


def sourced_values(tool_outputs: list) -> Pools:
    pools = Pools()

    def num(x) -> Decimal | None:
        if isinstance(x, bool) or x is None:
            return None
        if isinstance(x, (int, float, Decimal)):
            return Decimal(str(x))
        if isinstance(x, str) and re.fullmatch(rf"\s*(?:{_NUM})%?\s*", x):
            return _dec(x.strip().rstrip("%"))
        return None

    def walk(x, key: str = "") -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v, key)
        else:
            d = num(x)
            if d is None:
                return
            if key in MONEY_KEYS:
                pools.money.add(d)
            elif key in PCT_KEYS:
                pools.pct.add(d)
            elif key in ARTICLE_KEYS and d == d.to_integral_value():
                pools.arts.add(int(d))

    walk(tool_outputs)
    return pools


def _places(raw: str) -> int:
    m = re.search(r"[.,](\d{1,2})(?!\d)", raw)
    return len(m.group(1)) if m else 0


def is_sourced(fig: dict, pools: Pools) -> bool:
    if fig["kind"] == "word":
        return False
    if fig["kind"] == "article":
        return fig["value"] in pools.arts
    v = Decimal(fig["value"])
    pool = pools.pct if fig["kind"] == "pct" else pools.money
    if v in pool:
        return True
    # Same value at the precision it is displayed with ("$4,900" = 4900.00, "62.82" = 62.821) — nothing looser.
    q = Decimal(1).scaleb(-_places(fig["raw"]))
    return any(n.quantize(q) == v.quantize(q) for n in pool)


def unsourced(text: str, tool_outputs: list) -> list[str]:
    pools = sourced_values(tool_outputs)
    return [f["raw"] for f in extract(text) if not is_sourced(f, pools)]
