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

from . import claims, figures, rules

FOLLOW_UP = re.compile(r"\b(it|that one|this one|that|itu|ini|tersebut|anyway|saja)\b", re.I)
BOUND = re.compile(r"at most|up to|maximum|\bbefore\b|sebelum|paling banyak|maksimal|hingga|batas atas|upper bound|"
                   r"UNCLEAR|tidak jelas|belum (?:termasuk|dipotong)|excluding|not including|\bminus\b|not stated", re.I)
RECEIVE = re.compile(r"\b(receiv\w*|land\w*|arriv\w*|get|gets|got|deposit\w*|credit(?:ed|s)?|take[- ]home|keep|keeps|"
                     r"reach\w*|net|end(?:s)? up|you have|you'll have|leaves? you(?: with)?|left with|yours|"
                     r"in your (?:account|bank|wallet|balance)|menerima|diterima|terima|masuk|sampai|mendapat\w*|dapat|"
                     r"bersih|menghasilkan|untuk Anda|tersisa|setara)\b", re.I)
PURPOSE = re.compile(r"\b(?:to|in order to|untuk|agar bisa) (?:receive|menerima|terima)\b", re.I)  # "to receive X, use…"
GROSS_OR_TAX = re.compile(r"\bgross\b|bruto|kotor|withh\w*|dipotong|potongan|pemotongan|\btax\w*|pajak", re.I)
TAXWORD = re.compile(r"withh\w*|dipotong|potongan|pemotongan|\btax\w*|pajak|tarif|treaty rate", re.I)
MARGIN = re.compile(r"margin|conversion|konversi", re.I)
RATE_CTX = re.compile(r"\brate\b|\bthe plan\b|rencana", re.I)  # "the plan says 30%"
SHARE_CTX = re.compile(r"\b(?:of|dari)\b", re.I)  # "30% of $7,000.00" when the $7,000.00 is sourced
ARTICLE_CTX = re.compile(r"\barticles?\b|\barts?\b|\bpasal\b", re.I)
ARTICLE_CLAIM = re.compile(r"\bclaim\w*|treaty benefit|reduc\w*|lower\w*|exempt\w*|appl(?:y|ies)|berlaku|klaim|"
                           r"menurunkan|mengurangi|taxable only|lebih rendah|dibebaskan|dikecualikan|\bcuts?\b", re.I)
ARTICLE_DESCRIBED = re.compile(r"nearest|terdekat|\bnone\b|no article|tidak ada|no other income|tidak memiliki|"
                               r"does not cover|doesn't cover|tidak mencakup|UNCLEAR|tidak jelas|no source|"
                               r"belum ada sumber|does not say|doesn't say|until a source", re.I)
LINK = re.compile(r"(?:https?|hxxps?)://\S+|\bwww\.\S+|\b[\w.+-]+@[\w-]+\.[\w.]+|(?<![\w@])@\w{3,}|\b0x[0-9a-fA-F]{6,}|"
                  r"\bbc1[0-9a-z]{20,}\b|\b[1-9A-HJ-NP-Za-km-z]{32,44}\b|"
                  r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|io|dev|xyz|example|org|net|co|id|me|app|link|site|gg|to)\b(?:/\S*)?")
MAX_CHARS = 1600
LINE10_OK = re.compile(r"\bUNCLEAR\b|\bblank\b|kosong|no source|tidak ada sumber|tidak jelas|belum ada sumber|"
                       r"does not say|doesn't say|until a source|jangan klaim|(?:won't|will not|would not|should not) "
                       r"(?:put|write|claim)", re.I)  # describing, not claiming


def _strings(x) -> list[str]:
    if isinstance(x, dict):
        return [s for v in x.values() for s in _strings(v)]
    if isinstance(x, (list, tuple)):
        return [s for v in x for s in _strings(v)]
    return [x] if isinstance(x, str) else []


def check(text: str, tool_outputs: list, card: dict, question: str = "") -> dict:
    pools = figures.sourced_values(tool_outputs)
    asked = {(f["kind"], str(f["value"])) for f in figures.extract(question)}
    claims_: list[str] = []
    classes: set[str] = set()
    unsourced: list[str] = []
    echoed: list[str] = []
    n_figs = 0
    refused = [r["rail"] for r in card["rails"] if r["verdict"] == "REFUSED"]
    unclear_rails = [r["rail"] for r in card["rails"] if r["verdict"] == "UNCLEAR"]
    line10 = card["w8ben"]["line10"]
    wh_rate = card["withholding"]["rate"]
    ld = card.get("landed") or {}
    landed_unclear = ld.get("landed_usd") == "UNCLEAR"
    known_text = " ".join(_strings(tool_outputs))
    prev_named = False

    def sourced_money_in(sent: str) -> bool:
        return any(f["kind"] == "money" and figures.is_sourced(f, pools) for f in figures.extract(sent))

    gross_or_withheld = {figures._dec(v) for v in (ld.get("gross"), ld.get("withheld")) if v and v != "UNCLEAR"}
    confirmed_chains = {f"usdc:{n}" for r in card["rails"] for n in r.get("sourced_yes_networks", [])}

    def claim(cls: str, msg: str) -> None:
        classes.add(cls)
        claims_.append(msg)

    for sent in claims.sentences(text):
        # --- figures: typed provenance, read in the sentence's context -------------------------------------------
        for f in figures.extract(sent):
            n_figs += 1
            ok = figures.is_sourced(f, pools)
            if ok and f["kind"] == "pct" and not (TAXWORD.search(sent) or MARGIN.search(sent) or RATE_CTX.search(sent)
                                                  or (SHARE_CTX.search(sent) and sourced_money_in(sent))):
                ok = False  # a sourced rate is a withholding or margin rate; "Payoneer charges 30%" is not sourced
            if (not ok and f["kind"] == "number" and ARTICLE_CTX.search(sent)
                    and Decimal(f["value"]) == Decimal(f["value"]).to_integral_value()
                    and int(f["value"]) in pools.arts):
                ok = True  # "the nearest articles (15, 16 and 17)"
            if not ok:
                unsourced.append(f["raw"])
                classes.add("unsourced_figure")
                if (f["kind"], str(f["value"])) in asked:
                    echoed.append(f["raw"])
        # --- rails -------------------------------------------------------------------------------------------------
        named_refused = [r for r in refused if claims.mentions(sent, r)]
        for rail in named_refused:
            if claims.endorses_refused(sent, rail):
                claim("refused_rail", f"names refused {rail} without refusing it: {sent[:140]}")
        for rail in unclear_rails:
            if claims.endorses_unclear(sent, rail):
                claim("unclear_rail", f"recommends {rail}, whose deliverability is UNCLEAR: {sent[:140]}")
        on_card = {r["rail"] for r in card["rails"]}
        unchecked = ([r for r in rules.RAILS if r not in on_card] + list(claims.EXTRA_RAILS)
                     + [f"usdc:{c}" for c in rules.CHAINS if f"usdc:{c}" not in on_card | confirmed_chains])
        for rail in unchecked:
            if claims.endorses_unclear(sent, rail, strong_only=True):  # a rail the plan never checked is UNCLEAR
                claim("unclear_rail", f"recommends {rail}, which this plan did not check: {sent[:140]}")
        others = [r["rail"] for r in card["rails"] if r["rail"] not in refused and claims.mentions(sent, r["rail"])]
        if (not named_refused and not others and prev_named and claims.endorses(sent) and FOLLOW_UP.search(sent)
                and not claims.refuses(sent)):
            claim("refused_rail", f"endorses the refused rail by reference: {sent[:140]}")
        prev_named = bool(named_refused)
        # --- W-8BEN line 10 and treaty articles --------------------------------------------------------------------
        has_article = figures.ARTICLE_RE.search(sent)
        if (re.search(r"line\s*10|baris\s*10", sent, re.I) and has_article and not line10.startswith("ARTICLE")
                and not claims.refuses(sent) and not LINE10_OK.search(sent)):
            claim("line10", f"article on line 10 while the tools say {line10}: {sent[:140]}")
        elif (has_article and not line10.startswith("ARTICLE") and ARTICLE_CLAIM.search(sent)
              and not ARTICLE_DESCRIBED.search(sent) and not claims.refuses(sent)):
            claim("line10", f"treaty article presented as applying while the tools say {line10}: {sent[:140]}")
        # --- withholding and tax position --------------------------------------------------------------------------
        if TAXWORD.search(sent):
            for f in figures.extract(sent):
                if f["kind"] not in ("pct", "word") or MARGIN.search(sent):
                    continue
                same = wh_rate.endswith("%") and f["kind"] == "pct" and f["value"] == figures._dec(wh_rate[:-1])
                if not same and not (wh_rate == "UNCLEAR" and claims.UNCLEAR_WORD.search(sent)):
                    claim("withholding", f"withholding {f['raw']} while the tools say {wh_rate}: {sent[:140]}")
        if claims.TAX_POSITION.search(sent) and not claims.refuses(sent) and not claims.UNCLEAR_WORD.search(sent):
            claim("withholding", f"tax position the tools did not produce (they say {wh_rate}): {sent[:140]}")
        # --- UNCLEAR is terminal: nothing may be presented as what lands -------------------------------------------
        if (landed_unclear and RECEIVE.search(sent) and not BOUND.search(sent) and not PURPOSE.search(sent)
                and not claims.refuses(sent)):
            money = [f for f in figures.extract(sent) if f["kind"] in ("money", "number", "word")]
            # only the gross or the withheld amount, named as such, is not a promise of what lands
            described = GROSS_OR_TAX.search(sent) and all(
                f["kind"] != "word" and figures._dec(str(f["value"])) in gross_or_withheld for f in money)
            if money and not described:
                claim("unclear_upgraded", f"{money[0]['raw']} stated as what lands while it is UNCLEAR: {sent[:140]}")
    for m in LINK.finditer(text):  # links, emails, handles and wallet addresses only if a tool output carries them
        if m.group(0).rstrip(".,)") not in known_text:
            claim("link", f"link or address not in any tool output: {m.group(0)[:80]}")
    if len(text) > MAX_CHARS:
        claim("length", f"explanation is {len(text)} characters (max {MAX_CHARS})")
    score = round(1 - len(unsourced) / n_figs, 3) if n_figs else 1.0
    return {"passed": not unsourced and not claims_, "score": score, "figures": n_figs,
            "unsourced": unsourced, "claims": claims_, "echoed_from_question": echoed,
            "violation_classes": sorted(classes)}


def run(text: str, tool_outputs: list, card: dict, attempt: int, question: str = "") -> dict:
    """GUARDRAIL span around check(); passed/score set as neatlogs.guardrail.* attributes, verdict in the output."""
    with neatlogs.trace("provenance_guardrail", kind="GUARDRAIL") as sp:
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
