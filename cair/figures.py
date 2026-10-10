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
PCT_RE = re.compile(rf"({_NUM})\s?(?:%|percent|persen)", re.I)
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
    for m in BARE_RE.finditer(masked):
        if taken(*m.span()):
            continue
        val = _dec(m.group(1))
        if val is None or val < 10:  # small bare integers are counts and list markers, not claims
            continue
        found.append({"kind": "number", "value": val, "raw": m.group(1)})
        spans.append(m.span())
    return found


def sourced_values(tool_outputs: list) -> tuple[set[Decimal], set[int]]:
    """Every number and article number that appears anywhere in the tool outputs of one plan."""
    nums: set[Decimal] = set()
    arts: set[int] = set()

    def walk(x, key: str = "") -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, k)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v, key)
        elif isinstance(x, bool) or x is None:
            return
        elif isinstance(x, (int, float, Decimal)):
            nums.add(Decimal(str(x)))
            if key in {"article", "treaty_other_income_article"}:
                arts.add(int(x))
        elif isinstance(x, str):
            if key in {"article", "treaty_other_income_article"} and x.isdigit():
                arts.add(int(x))
            for f in extract(x):
                if f["kind"] == "article":
                    arts.add(f["value"])
                else:
                    nums.add(Decimal(f["value"]))
            d = _dec(x.rstrip("%")) if re.fullmatch(rf"(?:{_NUM})%?", x.strip()) else None
            if d is not None:
                nums.add(d)

    walk(tool_outputs)
    return nums, arts


def is_sourced(fig: dict, nums: set[Decimal], arts: set[int]) -> bool:
    if fig["kind"] == "article":
        return fig["value"] in arts
    v = Decimal(fig["value"])
    if v in nums:
        return True
    # Same amount at display precision: 87,616,900.00 vs 87616900, or a rate shown to fewer decimals.
    return any(abs(v - n) <= Decimal("0.005") * max(Decimal(1), abs(n)) / 100 for n in nums)


def unsourced(text: str, tool_outputs: list) -> list[str]:
    nums, arts = sourced_values(tool_outputs)
    return [f["raw"] for f in extract(text) if not is_sourced(f, nums, arts)]
