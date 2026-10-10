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
MULT = {"k": 1_000, "rb": 1_000, "ribu": 1_000, "thousand": 1_000, "m": 1_000_000, "jt": 1_000_000,
        "juta": 1_000_000, "million": 1_000_000, "mn": 1_000_000}
MONEY_RE = re.compile(
    rf"(?:(?:US)?\$|USD|USDC|IDR|Rp\.?|INR|₹|PHP|₱)\s?({_NUM})(?:\s?(k|rb|ribu|thousand|m|mn|jt|juta|million)\b)?"
    rf"|({_NUM})\s?(k|rb|ribu|thousand|m|mn|jt|juta|million)?\s?(?:USD|USDC|IDR|INR|PHP|dollars?|dolar|rupiah)\b", re.I)
PCT_RE = re.compile(rf"({_NUM})\s?(?:%|percent|per cent|pct|persen)", re.I)
# A rate or an amount written in words is never in a tool output, so it is always a new figure.
_WORDNUM = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|"
            r"sixty|seventy|eighty|ninety|hundred|thousand|million|satu|dua|tiga|empat|lima|enam|tujuh|delapan|"
            r"sembilan|sepuluh|seratus|seribu|ratus|ribu|juta|puluh|belas)")
WORD_MONEY_RE = re.compile(rf"\b{_WORDNUM}(?:[\s-]+(?:and\s+)?{_WORDNUM})*\s+(?:US\s)?(?:dollars?|dolar(?: AS)?|USD|USDC|rupiah|IDR|rupees?|INR|pesos?|PHP)\b",
                           re.I)
WORD_PCT_RE = re.compile(r"\b(?:zero|nol|one|two|three|four|five|ten|fifteen|twenty|thirty|forty|fifty|satu|dua|tiga|lima|"
                         r"sepuluh|lima belas|dua puluh|tiga puluh)(?:[- ](?:one|two|five|puluh|belas))?\s?"
                         r"(?:%|percent|per cent|persen)", re.I)
ARTICLE_RE = re.compile(r"\b(?:article|art\.|pasal)\s*(\d{1,2})\b", re.I)
BARE_RE = re.compile(rf"(?<![\w.])({_NUM})(?![\w.])")


_UNITS = {"zero": 0, "nol": 0, "one": 1, "satu": 1, "se": 1, "two": 2, "dua": 2, "three": 3, "tiga": 3, "four": 4,
          "empat": 4, "five": 5, "lima": 5, "six": 6, "enam": 6, "seven": 7, "tujuh": 7, "eight": 8, "delapan": 8,
          "nine": 9, "sembilan": 9, "ten": 10, "sepuluh": 10, "eleven": 11, "sebelas": 11, "twelve": 12, "fifteen": 15,
          "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "ratus": 100, "seratus": 100, "thousand": 1000, "ribu": 1000, "seribu": 1000,
           "million": 1_000_000, "juta": 1_000_000, "sejuta": 1_000_000}


def words_to_number(phrase: str) -> Decimal | None:
    """'two thousand one hundred USD' -> 2100, 'tiga puluh persen' -> 30. None if any word is not a number word."""
    words = re.findall(r"[a-z]+", phrase.lower())
    words = [w for w in words if w not in {"and", "us", "usd", "usdc", "dollar", "dollars", "dolar", "rupiah", "idr",
                                            "inr", "php", "rupee", "rupees", "peso", "pesos", "percent", "per", "cent",
                                            "persen", "pct"}]
    total, current, seen = 0, 0, False
    for w in words:
        if w in ("puluh",):
            current *= 10
        elif w in ("belas",):
            current += 10
        elif w in _UNITS:
            current += _UNITS[w]
        elif w in _SCALES:
            scale = _SCALES[w]
            if w.startswith("se"):
                current += 1
            if scale == 100:
                current = max(current, 1) * 100
            else:
                total += max(current, 1) * scale
                current = 0
        else:
            return None
        seen = True
    return Decimal(total + current) if seen else None


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
            groups = [g for g in m.groups() if g]
            raw = groups[0]
            val = _dec(raw)
            if val is None:
                continue
            if kind == "money" and len(groups) > 1 and groups[1].lower() in MULT:
                val *= MULT[groups[1].lower()]
            found.append({"kind": kind, "value": val, "raw": m.group(0).strip()})
            spans.append(m.span())
    for rx, kind in ((WORD_PCT_RE, "pct"), (WORD_MONEY_RE, "money")):
        for m in rx.finditer(text):
            if taken(*m.span()):
                continue
            val = words_to_number(m.group(0))
            # a number written in words is read like digits; one we cannot read is never sourced
            found.append({"kind": kind if val is not None else "word", "value": val if val is not None else m.group(0),
                          "raw": m.group(0), "words": True})
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
    if fig.get("words"):  # read from words: must equal a sourced value exactly
        pool = pools.pct if fig["kind"] == "pct" else pools.money
        return Decimal(fig["value"]) in pool
    if fig["kind"] == "article":
        return fig["value"] in pools.arts
    try:
        v = Decimal(fig["value"])
        pool = pools.pct if fig["kind"] == "pct" else pools.money
        if v in pool:
            return True
        # Same value at the precision it is displayed with ("$4,900" = 4900.00, "62.82" = 62.821) — nothing looser.
        q = Decimal(1).scaleb(-_places(fig["raw"]))
        return any(n.quantize(q) == v.quantize(q) for n in pool)
    except InvalidOperation:  # absurdly long numbers: never sourced, never a crash
        return False


def unsourced(text: str, tool_outputs: list) -> list[str]:
    pools = sourced_values(tool_outputs)
    return [f["raw"] for f in extract(text) if not is_sourced(f, pools)]
