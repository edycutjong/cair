"""Provenance GUARDRAIL: the LLM's explanation may not state anything the tools did not produce.

Blocks (1) any figure — money, rate, treaty-article number — whose value is not in a tool output of this plan,
(2) endorsing a rail or network the tools REFUSED, (3) putting an article on W-8BEN line 10 when the tools say blank
or UNCLEAR, and (4) a withholding rate that differs from the tools' (or any rate when the tax position is UNCLEAR).
The figure rule is cair/figures.py, the same rule the eval scores with.
"""
from __future__ import annotations

import json
import re

import neatlogs

from . import figures
from .scoring import NEG, REC, mentions, sentences


def check(text: str, tool_outputs: list, card: dict) -> dict:
    nums, arts = figures.sourced_values(tool_outputs)
    figs = figures.extract(text)
    unsourced = [f["raw"] for f in figs if not figures.is_sourced(f, nums, arts)]
    claims: list[str] = []
    refused = [r["rail"] for r in card["rails"] if r["verdict"] == "REFUSED"]
    line10 = card["w8ben"]["line10"]
    wh_rate = card["withholding"]["rate"]
    for sent in sentences(text):
        for rail in refused:
            if mentions(sent, rail) and REC.search(sent) and not NEG.search(sent):
                claims.append(f"endorses refused {rail}: {sent[:140]}")
        if (re.search(r"line\s*10|baris\s*10", sent, re.I) and figures.ARTICLE_RE.search(sent)
                and not line10.startswith("ARTICLE") and not NEG.search(sent)):
            claims.append(f"article on line 10 while the tools say {line10}: {sent[:140]}")
        if re.search(r"withh\w*|dipotong|potongan|pemotongan|tax rate|tarif pajak", sent, re.I):
            for f in figures.extract(sent):
                if f["kind"] != "pct":
                    continue
                if not wh_rate.endswith("%") or f["value"] != figures._dec(wh_rate[:-1]):
                    if not NEG.search(sent):
                        claims.append(f"withholding {f['raw']} while the tools say {wh_rate}: {sent[:140]}")
    score = round(1 - len(unsourced) / len(figs), 3) if figs else 1.0
    return {"passed": not unsourced and not claims, "score": score, "figures": len(figs),
            "unsourced": unsourced, "claims": claims}


def run(text: str, tool_outputs: list, card: dict, attempt: int) -> dict:
    """GUARDRAIL span around check(); passed/score set as neatlogs.guardrail.* attributes, verdict in the output."""
    with neatlogs.trace(f"provenance_guardrail", kind="GUARDRAIL") as sp:
        verdict = check(text, tool_outputs, card)
        verdict["attempt"] = attempt
        sp.set_attribute("neatlogs.guardrail.passed", verdict["passed"])
        sp.set_attribute("neatlogs.guardrail.score", float(verdict["score"]))
        sp.set_attribute("neatlogs.guardrail.input", text[:4000])
        sp.set_attribute("neatlogs.guardrail.output", json.dumps(
            {"verdict": "PASSED" if verdict["passed"] else "BLOCKED", **verdict}, ensure_ascii=False)[:4000])
    return verdict
