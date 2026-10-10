"""The rules sheet: every fact Cair may state, each with a source. Loaded once; lookups never guess.

A row key is (country, payer, rail). `*` in country or payer means "any". A key may have several rows when its facts
need different sources, but each fact cell is filled on exactly one row (the loader refuses a cell filled twice).
Blank means "this row does not carry that fact"; a fact that no row fills is UNCLEAR.
"""
from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import DATA

UNCLEAR = "UNCLEAR"
FACTS = ("deliverable", "w8ben_applies", "treaty_other_income_article", "withholding_default",
         "receiving_fee_usd", "fx_margin_pct")
TRI = {"YES", "NO", UNCLEAR}
COUNTRIES = {"ID": "Indonesia", "IN": "India", "PH": "Philippines", "VN": "Vietnam", "NG": "Nigeria"}
CURRENCY = {"ID": "IDR", "IN": "INR", "PH": "PHP", "VN": "VND", "NG": "NGN"}
PAYERS = {"devpost": "Devpost", "dorahacks_usdc": "DoraHacks (USDC)", "superteam_usdc": "Superteam Earn (USDC)",
          "us_client_services": "A US client (services)"}
USDC_PAYERS = {"dorahacks_usdc", "superteam_usdc"}
RAILS = {"payoneer": "Payoneer", "wise": "Wise", "paypal": "PayPal"}
EXCHANGES = {"indodax": "Indodax", "pintu": "Pintu", "tokocrypto": "Tokocrypto"}
EXCHANGE_COUNTRY = {"indodax": {"ID"}, "pintu": {"ID"}, "tokocrypto": {"ID"}}  # Indonesian exchanges
CHAINS = {"ethereum": "Ethereum (ERC-20)", "bsc": "BNB Smart Chain (BEP-20)", "polygon": "Polygon", "base": "Base",
          "solana": "Solana", "arbitrum": "Arbitrum", "optimism": "Optimism", "avalanche": "Avalanche C-Chain",
          "tron": "Tron (TRC-20)", "arc": "Arc", "sei": "SEI (EVM)"}


@dataclass(frozen=True)
class Fact:
    value: str
    source_id: str
    source_url: str
    accessed_at: str
    row_key: str

    def as_dict(self) -> dict:
        return {"value": self.value, "source_id": self.source_id, "source_url": self.source_url,
                "accessed_at": self.accessed_at, "row": self.row_key}


class SheetError(ValueError):
    pass


@dataclass
class Sheet:
    facts: dict[tuple[str, str, str, str], Fact]  # (country, payer, rail, fact) -> Fact
    quotes: dict[str, dict]
    version: str

    def get(self, country: str, payer: str, rail: str, fact: str) -> Fact | None:
        """Most specific row wins: (country, payer) > (country, *) > (*, payer) > (*, *)."""
        for c, p in ((country, payer), (country, "*"), ("*", payer), ("*", "*")):
            hit = self.facts.get((c, p, rail, fact))
            if hit is not None:
                return hit
        return None

    def value(self, country: str, payer: str, rail: str, fact: str) -> str:
        hit = self.get(country, payer, rail, fact)
        return hit.value if hit else UNCLEAR

    def offered_rails(self, payer: str) -> list[str]:
        return sorted({r for (c, p, r, f), v in self.facts.items()
                       if p == payer and f == "deliverable" and v.value == "OFFERED"})

    def exchange_rows(self, exchange: str) -> dict[str, Fact]:
        out = {}
        for (_c, p, r, f), v in self.facts.items():
            if p == "_exchange" and f == "deliverable" and r.startswith(f"{exchange}:usdc:"):
                out[r.split(":", 2)[2]] = v
        return out


def _parse_quotes(text: str) -> dict[str, dict]:
    quotes: dict[str, dict] = {}
    for block in re.split(r"^### ", text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        url = re.search(r"^URL: (\S+)", body, flags=re.M)
        lines = [ln[2:].strip() for ln in body.splitlines() if ln.startswith("> ")]
        dated = re.search(r"^URL: \S+ \(([^)]*\d{4}[^)]*)\)", body, flags=re.M)
        quotes[head.strip()] = {"url": url.group(1) if url else "", "quote": " ".join(lines),
                                "page_date": dated.group(1) if dated else ""}
    return quotes


def load(path: Path | None = None, sources: Path | None = None) -> Sheet:
    path = path or DATA / "rules_sheet.csv"
    sources = sources or DATA / "sources.md"
    raw = path.read_bytes()
    quotes = _parse_quotes(sources.read_text())
    facts: dict[tuple[str, str, str, str], Fact] = {}
    for n, row in enumerate(csv.DictReader(raw.decode().splitlines()), start=2):
        key = (row["country"], row["payer"], row["rail"])
        rk = "|".join(key)
        for fact in FACTS:
            val = (row.get(fact) or "").strip()
            if not val:
                continue
            if (*key, fact) in facts:
                raise SheetError(f"line {n}: {fact} for {rk} is filled twice")
            sid = (row.get("source_id") or "").strip()
            if val != UNCLEAR and not sid:
                raise SheetError(f"line {n}: {fact}={val} for {rk} has no source")
            if sid and sid not in quotes:
                raise SheetError(f"line {n}: source {sid} is not in sources.md")
            _validate(fact, val, n)
            facts[(*key, fact)] = Fact(val, sid, row.get("source_url", ""), row.get("accessed_at", ""), rk)
    return Sheet(facts=facts, quotes=quotes, version=hashlib.sha256(raw).hexdigest()[:12])


def _validate(fact: str, val: str, n: int) -> None:
    ok = {
        "deliverable": val in TRI | {"OFFERED"},
        "w8ben_applies": val in TRI,
        "treaty_other_income_article": val in {"NONE", UNCLEAR} or val.isdigit(),
        "withholding_default": val == UNCLEAR or bool(re.fullmatch(r"\d+(\.\d+)?%", val)),
        "receiving_fee_usd": val == UNCLEAR or bool(re.fullmatch(r"\d+(\.\d+)?", val)),
        "fx_margin_pct": val == UNCLEAR or bool(re.fullmatch(r"\d+(\.\d+)?", val)),
    }[fact]
    if not ok:
        raise SheetError(f"line {n}: {fact}={val!r} is not a valid value")


@lru_cache(maxsize=1)
def sheet() -> Sheet:
    return load()
