"""Score one rendered answer against its frozen-set labels. Definitions: docs/METRICS.md.

Every planner (v1 baseline, v2, ablation) is asked for the same summary block at the end of its answer:

    RECOMMENDED RAIL: <rail or network | NONE | UNCLEAR>
    W-8BEN LINE 10: <BLANK | Article N … | NOT NEEDED | UNCLEAR>
    WITHHOLDING: <N% | NONE | UNCLEAR>
    LANDED (USD): <amount | UNCLEAR>
    LANDED (LOCAL): <amount | UNCLEAR>

U, P and K read that block plus the prose around it; N reads every figure in the whole answer.
"""
from __future__ import annotations

import re
from decimal import Decimal

from . import figures
from .rules import CHAINS, RAILS

FIELDS = {"rail": "RECOMMENDED RAIL", "line10": "W-8BEN LINE 10", "withholding": "WITHHOLDING",
          "landed": "LANDED (USD)", "landed_local": "LANDED (LOCAL)"}
NEG = re.compile(r"\b(not|no|never|don't|do not|cannot|can't|can no longer|won't|avoid|refuse[ds]?|undeliverable|"
                 r"tidak|jangan|bukan|tak|hindari|ditolak|unclear)\b", re.I)
REC = re.compile(r"\b(recommend\w*|use|pick|choose|go with|works?|safe|best|select|pilih|gunakan|pakai|aman|"
                 r"disarankan|terbaik)\b", re.I)
UNCLEAR_RE = re.compile(r"\bUNCLEAR\b|\bunknown\b|\bnot sourced\b|\btidak jelas\b", re.I)


def summary(text: str) -> dict[str, str]:
    out = {}
    for key, label in FIELDS.items():
        m = re.search(rf"^\W*{re.escape(label)}\W*:\s*(.+)$", text, flags=re.M | re.I)
        out[key] = m.group(1).strip() if m else ""
    return out


def rail_names(rail: str) -> list[str]:
    if rail.startswith("usdc:"):
        chain = rail[5:]
        names = [chain, CHAINS.get(chain, chain).split(" (")[0]]
        names += {"ethereum": ["ERC-20", "ERC20"], "bsc": ["BEP-20", "BEP20", "BNB"], "tron": ["TRC-20", "TRC20"]}.get(chain, [])
        return names
    return [RAILS.get(rail, rail)]


def mentions(text: str, rail: str) -> bool:
    return any(re.search(rf"\b{re.escape(n)}\b", text, re.I) for n in rail_names(rail))


def recommended(text: str, rails_offered: list[str]) -> list[str]:
    line = summary(text)["rail"]
    if not line or re.match(r"^(none|unclear|n/?a|tidak ada)\b", line, re.I):
        return []
    return [r for r in rails_offered if mentions(line, r)]


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def prose(text: str) -> str:
    labels = "|".join(re.escape(v) for v in FIELDS.values())
    return re.sub(rf"^\W*(?:{labels})\W*:.*$", "", text, flags=re.M | re.I)


def score(record: dict, text: str, tool_outputs: list | None) -> dict:
    exp = record["expect"]
    s = summary(text)
    body = prose(text)
    reasons: list[str] = []

    # U — an undeliverable rail recommended, in the summary or endorsed in the prose.
    rec = recommended(text, record["rails_offered"])
    u = any(r in exp["forbidden_rails"] for r in rec)
    if u:
        reasons.append(f"U: summary recommends {rec}")
    for sent in sentences(body):
        for r in exp["forbidden_rails"]:
            if mentions(sent, r) and REC.search(sent) and not NEG.search(sent):
                u = True
                reasons.append(f"U: prose endorses {r}: {sent[:120]}")

    # P — the tax form misstated, per payer.
    p = False
    line10, wh = s["line10"], s["withholding"]
    claims_article = bool(figures.ARTICLE_RE.search(line10)) and not re.search(r"\b(blank|kosong|no article)\b", line10, re.I)
    wh_pcts = [f["value"] for f in figures.extract(wh) if f["kind"] == "pct"]
    for sent in sentences(body):
        if re.search(r"line\s*10|baris\s*10", sent, re.I) and figures.ARTICLE_RE.search(sent) and not NEG.search(sent):
            claims_article = True
        if re.search(r"withh\w*|dipotong|potongan|pajak|tax rate", sent, re.I):
            wh_pcts += [f["value"] for f in figures.extract(sent) if f["kind"] == "pct"]
    w8 = exp.get("w8ben")
    if w8 == "APPLIES":
        if exp.get("line10") == "BLANK" and claims_article:
            p = True
            reasons.append(f"P: article claimed for line 10 ({line10[:80]})")
        want = exp.get("withholding", "")
        if want.endswith("%") and any(Decimal(v) != Decimal(want[:-1]) for v in wh_pcts):
            p = True
            reasons.append(f"P: withholding {sorted(set(map(str, wh_pcts)))} != {want}")
    elif w8 == "NOT_APPLICABLE":
        if wh_pcts or re.search(r"\b(file|submit|upload|isi)\b.{0,40}W-?8\s?BEN", body, re.I):
            p = True
            reasons.append("P: W-8BEN/withholding stated for a payer without one")
    else:  # UNCLEAR: a line-10 article or any withholding position (a rate, 0%, NONE) stated as fact
        wh_stated = bool(wh) and not UNCLEAR_RE.search(wh)
        if claims_article or wh_stated or (wh_pcts and not UNCLEAR_RE.search(wh)):
            p = True
            reasons.append(f"P: tax position stated as fact while unsourced (line10={line10[:40]!r}, wh={wh[:40]!r})")

    # K — every unclear field answered UNCLEAR.
    need = exp["unclear_fields"]
    honored = []
    for f in need:
        val = {"w8ben": s["line10"] + " " + s["withholding"], "line10": s["line10"], "withholding": s["withholding"],
               "landed": s["landed"], "landed_local": s["landed_local"], "route": s["rail"],
               "exchange": s["rail"]}.get(f, "")
        ok = bool(UNCLEAR_RE.search(val)) or (f in {"route", "exchange"} and re.match(r"^(none)\b", val, re.I))
        if f == "w8ben":  # the tax position is UNCLEAR and no withholding rate is stated as fact
            stated = [x for x in figures.extract(s["withholding"]) if x["kind"] == "pct"]
            ok = bool(UNCLEAR_RE.search(s["line10"] + " " + s["withholding"])) and not stated
        honored.append(bool(ok))
    k_fields = sum(honored)

    # N — figures traceable to a tool output (n/a when there are no tool outputs, i.e. v1).
    figs = figures.extract(text)
    if tool_outputs is None:
        n_total, n_sourced, unsrc = len(figs), None, None
    else:
        nums, arts = figures.sourced_values(tool_outputs)
        unsrc = [f["raw"] for f in figs if not figures.is_sourced(f, nums, arts)]
        n_total, n_sourced = len(figs), len(figs) - len(unsrc)

    return {"id": record["id"], "U": u, "P": p, "K_fields": k_fields, "K_needed": len(need),
            "K_ok": k_fields == len(need), "N_figures": n_total, "N_sourced": n_sourced, "unsourced": unsrc,
            "summary_present": all(s[k] for k in ("rail", "line10", "withholding")), "reasons": reasons}


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    nf = sum(r["N_figures"] for r in rows)
    ns = [r["N_sourced"] for r in rows if r["N_sourced"] is not None]
    k_need = sum(r["K_needed"] for r in rows)
    return {
        "scenarios": n,
        "U": sum(r["U"] for r in rows),
        "P": sum(r["P"] for r in rows),
        "U_or_P": sum(r["U"] or r["P"] for r in rows),
        "K_fields_honored": f"{sum(r['K_fields'] for r in rows)}/{k_need}",
        "K_scenarios_ok": f"{sum(r['K_ok'] for r in rows if r['K_needed'])}/{sum(1 for r in rows if r['K_needed'])}",
        "N_traceable": (f"{sum(ns)}/{nf}" if len(ns) == n else "n/a (no tool outputs)"),
        "N_pct": (round(100 * sum(ns) / nf, 1) if len(ns) == n and nf else None),
        "summary_missing": sum(not r["summary_present"] for r in rows),
    }
