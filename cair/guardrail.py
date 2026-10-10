"""Provenance GUARDRAIL: the LLM's explanation may not state anything the tools did not produce.

Blocks (1) any figure — money, rate, treaty-article number — whose value is not in a tool output of this plan,
(2) endorsing a rail or network the tools REFUSED, (3) putting an article on W-8BEN line 10 when the tools say blank
or UNCLEAR, and (4) a withholding rate that differs from the tools' (or any rate when the tax position is UNCLEAR).
The figure rule is cair/figures.py, the same rule the eval scores with.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

import neatlogs

from . import figures
from .scoring import REC, mentions, sentences


REFUSAL = re.compile(
    r"refus\w*|\bcannot\b|can't|can no longer|no longer|\bnot (?:be )?(?:use|used|usable|able|available|recommended|"
    r"possible|deliver\w*|an option|work\w*|supported|accepted)|don't|do not|\bavoid|unavailable|undeliverable|won't|"
    r"will not|\btidak (?:bisa|dapat|lagi|disarankan|direkomendasikan|tersedia|mendukung|dikreditkan|diterima|boleh)|"
    r"\bjangan\b|ditolak|menolak\w*|tak bisa|bukan pilihan|berisiko|\blose\b|\bhilang", re.I)
FOLLOW_UP = re.compile(r"\b(it|that one|this one|that|itu|ini|tersebut|anyway|saja)\b", re.I)
BOUND = re.compile(r"at most|up to|maximum|\bbefore\b|sebelum|paling banyak|maksimal|hingga|batas atas|upper bound|"
                   r"UNCLEAR|tidak jelas|belum (?:termasuk|dipotong)|excluding|not including|\bminus\b", re.I)
TAXWORD = re.compile(r"withh\w*|dipotong|potongan|pemotongan|\btax\w*|pajak|tarif|treaty rate", re.I)
LINK = re.compile(r"https?://\S+|\bwww\.\S+|\b[\w.+-]+@[\w-]+\.[\w.]+|\b0x[0-9a-fA-F]{6,}|\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
MAX_CHARS = 1600


def _strings(x) -> list[str]:
    if isinstance(x, dict):
        return [s for v in x.values() for s in _strings(v)]
    if isinstance(x, (list, tuple)):
        return [s for v in x for s in _strings(v)]
    return [x] if isinstance(x, str) else []


def check(text: str, tool_outputs: list, card: dict, question: str = "") -> dict:
    pools = figures.sourced_values(tool_outputs)
    figs = figures.extract(text)
    # Figures the user typed are flagged separately: a refusal that repeats them is still blocked (allowing it would
    # let "it is not 30%, it is 0%" through), but the retry is told to decline without repeating them. rca-02.
    asked = {(f["kind"], f["value"]) for f in figures.extract(question)}
    unsourced = [f["raw"] for f in figs if not figures.is_sourced(f, pools)]
    echoed = [f["raw"] for f in figs if not figures.is_sourced(f, pools) and (f["kind"], f["value"]) in asked]
    claims: list[str] = []
    classes: set[str] = {"unsourced_figure"} if unsourced else set()
    refused = [r["rail"] for r in card["rails"] if r["verdict"] == "REFUSED"]
    line10 = card["w8ben"]["line10"]
    wh_rate = card["withholding"]["rate"]
    ld = card.get("landed") or {}
    bounds = {figures._dec(ld[k]) for k in ("upper_bound_usd", "upper_bound_local") if ld.get(k)}
    known_text = " ".join(_strings(tool_outputs))
    prev_refused = False

    def claim(cls: str, msg: str) -> None:
        classes.add(cls)
        claims.append(msg)

    for sent in sentences(text):
        # A refused rail may only be named to say it is refused; "use it anyway" right after counts too.
        named = [r for r in refused if mentions(sent, r)]
        for rail in named:
            if not REFUSAL.search(sent):
                claim("refused_rail", f"names refused {rail} without saying it is refused: {sent[:140]}")
        if not named and prev_refused and REC.search(sent) and FOLLOW_UP.search(sent) and not REFUSAL.search(sent):
            claim("refused_rail", f"endorses the refused rail by reference: {sent[:140]}")
        prev_refused = bool(named)
        if (re.search(r"line\s*10|baris\s*10", sent, re.I) and figures.ARTICLE_RE.search(sent)
                and not line10.startswith("ARTICLE") and not REFUSAL.search(sent)):
            claim("line10", f"article on line 10 while the tools say {line10}: {sent[:140]}")
        if TAXWORD.search(sent):
            for f in figures.extract(sent):
                if f["kind"] not in ("pct", "word"):
                    continue
                if not wh_rate.endswith("%") or f["kind"] == "word" or f["value"] != figures._dec(wh_rate[:-1]):
                    claim("withholding", f"withholding {f['raw']} while the tools say {wh_rate}: {sent[:140]}")
        # UNCLEAR is terminal: an upper bound may only appear as a bound, never as what lands.
        if ld.get("landed_usd") == "UNCLEAR" and not BOUND.search(sent):
            for f in figures.extract(sent):
                if f["kind"] in ("money", "number") and any(
                        b is not None and Decimal(f["value"]).quantize(Decimal(1)) == b.quantize(Decimal(1)) for b in bounds):
                    claim("unclear_upgraded", f"upper bound {f['raw']} stated as what lands: {sent[:140]}")
    for m in LINK.finditer(text):  # links, emails and wallet addresses only if a tool output carries them
        if m.group(0).rstrip(".,)") not in known_text:
            claim("link", f"link or address not in any tool output: {m.group(0)[:80]}")
    if len(text) > MAX_CHARS:
        claim("length", f"explanation is {len(text)} characters (max {MAX_CHARS})")
    score = round(1 - len(unsourced) / len(figs), 3) if figs else 1.0
    return {"passed": not unsourced and not claims, "score": score, "figures": len(figs),
            "unsourced": unsourced, "claims": claims, "echoed_from_question": echoed,
            "violation_classes": sorted(classes)}


def run(text: str, tool_outputs: list, card: dict, attempt: int, question: str = "") -> dict:
    """GUARDRAIL span around check(); passed/score set as neatlogs.guardrail.* attributes, verdict in the output."""
    with neatlogs.trace(f"provenance_guardrail", kind="GUARDRAIL") as sp:
        verdict = check(text, tool_outputs, card, question)
        verdict["attempt"] = attempt
        sp.set_attribute("neatlogs.guardrail.passed", verdict["passed"])
        sp.set_attribute("neatlogs.guardrail.score", float(verdict["score"]))
        sp.set_attribute("neatlogs.guardrail.input", text[:4000])
        sp.set_attribute("neatlogs.guardrail.output", json.dumps(
            {"verdict": "PASSED" if verdict["passed"] else "BLOCKED", **verdict}, ensure_ascii=False)[:4000])
        for cls in verdict["violation_classes"]:  # searchable in neatlogs: "violation unsourced_figure" etc.
            neatlogs.log("violation {cls}", cls=cls)
    return verdict


def no_source(card: dict) -> dict:
    """Deterministic block: nothing in the rules sheet covers this payer/country, so there is nothing to explain."""
    with neatlogs.trace("provenance_guardrail", kind="GUARDRAIL") as sp:
        verdict = {"passed": False, "score": 0.0, "reason": "no_source", "figures": 0, "unsourced": [], "claims": [],
                   "detail": f"no sourced rule for {card['payer']} in {card['country']}", "attempt": 0}
        sp.set_attribute("neatlogs.guardrail.passed", False)
        sp.set_attribute("neatlogs.guardrail.score", 0.0)
        sp.set_attribute("neatlogs.guardrail.output", json.dumps({"verdict": "BLOCKED", **verdict}))
    return verdict
