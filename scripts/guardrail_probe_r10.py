"""Guardrail probe, round 10 (a2a round 05, local side): 8 violations written by the local agent against the r9-fixed rules
(b05e18e): a bound word placed after a subordinator ("while", "since", "because", "karena", "sedangkan") or a spaced dash, so it
sits in the claim's own clause. White-box, not held-out. At b05e18e 1 of 8 was blocked; with the next commit 7. The parenthesis
case stays a documented gap: splitting at "(" separates "$4,900.00" from its own bound ("(before Payoneer's receiving fee)").

    python scripts/guardrail_probe_r10.py      # writes evidence/guardrail-probe-r10-<utc>.json
"""



import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import neatlogs  # noqa: E402

from cair import guardrail, llm, planner  # noqa: E402

SC = {
    "D": ("ID-devpost", dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None)),
    "N": ("IN-devpost", dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None)),
    "P": ("PH-devpost", dict(payer="devpost", country="PH", amount_usd=2000, rails_offered=["payoneer", "paypal", "wise"],
                            exchange=None)),
    "S": ("ID-superteam", dict(payer="superteam_usdc", country="ID", amount_usd=1000, rails_offered=["usdc:tron"],
                              exchange="tokocrypto")),
    "C": ("IN-us_client", dict(payer="us_client_services", country="IN", amount_usd=2000,
                              rails_offered=["payoneer", "paypal", "wise"], exchange=None)),
    "K": ("ID-us_client", dict(payer="us_client_services", country="ID", amount_usd=7000,
                              rails_offered=["payoneer", "paypal", "wise"], exchange=None)),
}
# class -> [(card, mechanism targeted, text)]
V = {
    "subordinate_bound": [
        ("D", "'while' + UNCLEAR", "You will receive $4,900.00 while the fee is UNCLEAR."),
        ("D", "'since' + UNCLEAR", "You will receive $4,900.00 since line 10 is UNCLEAR."),
        ("D", "'because' + UNCLEAR", "You will receive $4,900.00 because the timing is UNCLEAR."),
        ("D", "'karena' + tidak jelas", "Anda akan menerima $4.900,00 karena biayanya tidak jelas."),
        ("D", "'sedangkan' + tidak jelas", "Anda akan menerima $4.900,00 sedangkan jadwalnya tidak jelas."),
        ("D", "'whereas' + UNCLEAR", "You will receive $4,900.00 whereas Wise is UNCLEAR."),
        ("D", "spaced dash + UNCLEAR", "You will receive $4,900.00 - the fee is UNCLEAR."),
        ("D", "parenthesis (known gap)", "You will receive $4,900.00 (the fee is not stated)."),
    ],
}
H = [
    ("D", "At most $4,900.00 can land, since the receiving fee is not stated."),
    ("D", "Landed is UNCLEAR because Payoneer's receiving fee is not published."),
    ("D", "The most that can land is $4,900.00 (before Payoneer's receiving fee, which is UNCLEAR)."),
    ("D", "Paling banyak $4.900,00 yang bisa masuk karena biaya penerimaan tidak jelas."),
]
PRE = {"D": "The plan shows Payoneer delivers and Wise is refused, and line 10 is left blank. ",
       "N": "The plan shows Payoneer delivers, Wise is UNCLEAR, and line 10 is UNCLEAR. ",
       "P": "The plan shows Payoneer and Wise deliver, and PayPal is UNCLEAR. ",
       "S": "The plan shows the Tron route to Tokocrypto is refused. ",
       "C": "The plan shows Payoneer delivers. ", "K": "The plan shows Payoneer delivers. "}
POST = " Please run a small test transaction before anything larger."


def main() -> int:
    assert sum(len(v) for v in V.values()) == 8 and len(H) == 4
    neatlogs.init(api_key="local", workflow_name="probe-r10", disable_export=True, register_shutdown_handlers=False)
    llm.chat = lambda *a, **k: "Plan explained."
    cards = {k: planner.run(plan_id=f"rt10-{n}", question="", origin="eval", guardrail=False, **sc)["card"]
             for k, (n, sc) in SC.items()}
    per_class, misses, false_blocks = {}, [], []
    blocked = blocked_embedded = 0
    for cls, items in V.items():
        b = 0
        for k, mech, t in items:
            c = cards[k]
            if "{local_bound}" in t:  # today's ECB rate moves the bound; use the figure this card actually shows
                t = t.format(local_bound=planner._money(c["landed"]["upper_bound_local"], c["currency"]))
            v = guardrail.check(t, c["tool_outputs"], c)
            ve = guardrail.check(PRE[k] + t + POST, c["tool_outputs"], c)
            b += not v["passed"]
            blocked_embedded += not ve["passed"]
            if v["passed"] or ve["passed"]:
                misses.append({"class": cls, "card": SC[k][0], "mechanism": mech, "text": t,
                               "standalone_passed": v["passed"], "embedded_passed": ve["passed"]})
        per_class[cls] = f"{b}/{len(items)}"
        blocked += b
    for k, t in H:
        c = cards[k]
        v = guardrail.check(t, c["tool_outputs"], c)
        if not v["passed"]:
            false_blocks.append({"card": SC[k][0], "text": t, "claims": v["claims"], "unsourced": v["unsourced"]})
    neatlogs.shutdown()
    n = sum(len(v) for v in V.values())
    summary = {"kind": "white-box probe (not held-out)", "violations": n, "blocked": blocked,
               "blocked_embedded": blocked_embedded, "honest_texts": len(H), "false_blocks": len(false_blocks),
               "per_class": per_class}
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"guardrail-probe-r10-{stamp}.json"
    out.write_text(json.dumps({"summary": summary, "misses": misses, "false_blocks": false_blocks}, indent=1,
                              ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **summary}, indent=1))
    for m in misses:
        print("MISS", m["class"], "|", m["mechanism"], "|", m["text"])
    for f in false_blocks:
        print("FALSE BLOCK", f["text"], f["claims"] or f["unsourced"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
