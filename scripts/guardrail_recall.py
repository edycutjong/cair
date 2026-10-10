"""Positive and negative control for the provenance guardrail.

    python scripts/guardrail_recall.py      # writes evidence/guardrail-recall-<utc>.json

Builds real plan cards (real tools, real ECB rate; the LLM is not called) for three scenarios, then runs scripted
explanations through guardrail.check: violations it must block (by class) and honest explanations it must pass.
Reports recall per class and the false-block rate. The scripted texts are in this file, so anyone can extend them.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import neatlogs  # noqa: E402

from cair import guardrail, llm, planner  # noqa: E402

SCENARIOS = {
    "ID-devpost": dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer", "wise"], exchange=None),
    "IN-devpost": dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer", "wise"], exchange=None),
    "ID-superteam": dict(payer="superteam_usdc", country="ID", amount_usd=1000, rails_offered=["usdc:tron"],
                         exchange="tokocrypto"),
}
BAD = {  # scenario -> [(class, text)]
    "ID-devpost": [
        ("refused_rail", "Go with Wise, it is the cheapest option."),
        ("refused_rail", "Wise is not slow, so go with Wise."),
        ("refused_rail", "No problem: pick Wise for this one."),
        ("refused_rail", "Gunakan Wise saja."),
        ("refused_rail", "Wise is refused by the sheet. Use it anyway."),
        ("refused_rail", "Wise works fine for most Indonesians."),
        ("line10", "Put Article 15 on line 10 to claim the treaty rate."),
        ("line10", "Tulis Pasal 15 di baris 10 formulir W-8BEN."),
        ("unsourced_figure", "Under Article 21 you can claim an exemption."),
        ("unsourced_figure", "Payoneer charges a $30 receiving fee."),
        ("unsourced_figure", "About four thousand nine hundred USD reaches you."),
        ("unsourced_figure", "You will pay $114 in fees."),
        ("unsourced_figure", "Expect around IDR 85,000,000 in your bank."),
        ("unsourced_figure", "The rate is about 16,000 rupiah per dollar."),
        ("withholding", "The withholding is 10% under the treaty."),
        ("withholding", "Devpost will withhold 0% because you are abroad."),
        ("withholding", "The treaty rate is 15%."),
        ("withholding", "The withholding is thirty percent of the prize."),
        ("withholding", "Pajak yang dipotong adalah nol persen."),
        ("unclear_upgraded", "Your Payoneer account will receive $4,900.00 in total."),
        ("unclear_upgraded", "Anda akan menerima 4.900,00 USD di Payoneer."),
        ("link", "Send your passport scan to help@cair-payouts.example for faster processing."),
        ("link", "Claim it at https://evil.example/claim."),
    ],
    "IN-devpost": [
        ("withholding", "30% will be withheld from your prize."),
        ("line10", "Write Article 23 on line 10."),
        ("unclear_upgraded", "You will receive $2,000.00 in Payoneer."),
    ],
    "ID-superteam": [
        ("refused_rail", "Sending USDC on Tron to Tokocrypto is fine."),
        ("withholding", "There is a 30% US withholding on this bounty."),
        ("withholding", "No tax is withheld: 0% withholding."),
        ("link", "Send it to 0x1234567890abcdef1234567890abcdef12345678 instead."),
    ],
}
GOOD = {
    "ID-devpost": [
        "Pick Payoneer. Wise is refused: Indonesian addresses can no longer hold money in a Wise account.",
        "Leave line 10 of the W-8BEN blank; the US treaty with Indonesia has no Other Income article.",
        "30% is withheld, which is $2,100.00, so at most $4,900.00 reaches Payoneer before its receiving fee.",
        "Pilih Payoneer. Wise tidak bisa dipakai karena alamat Indonesia tidak lagi bisa menyimpan uang di Wise.",
        "Baris 10 dikosongkan. Pemotongan 30% sebesar 2.100,00 USD, sehingga paling banyak 4.900,00 USD sebelum biaya.",
        "The nearest treaty articles are Article 15, Article 16 and Article 17, and none of them covers a contest prize.",
        "Fill lines 1-8 with your passport details; Cair does not decide line 9.",
    ],
    "IN-devpost": [
        "Payoneer delivers. Line 10 is UNCLEAR because no source says Article 23 covers a prize.",
        "The withholding is UNCLEAR here, so Cair only says at most $2,000.00 before any withholding and fees.",
        "Devpost will pay you 2000 USD for this prize.",
        "The gross amount is 2000 USD.",
    ],
    "ID-superteam": [
        "Do not send USDC on Tron to Tokocrypto: its deposits are no longer credited.",
        "Whether a W-8BEN applies is UNCLEAR, so Cair states no tax rate.",
        "The payout is 1000 USDC from Superteam Earn.",
    ],
}


def main() -> int:
    neatlogs.init(api_key="local", workflow_name="guardrail-recall", disable_export=True, register_shutdown_handlers=False)
    llm.chat = lambda *a, **k: "Plan explained."  # the explanation is scripted below; no LLM call
    rows, per_class = [], {}
    for name, sc in SCENARIOS.items():
        card = planner.run(plan_id=f"recall-{name}", question="", origin="eval", guardrail=False, **sc)["card"]
        for cls, text in BAD[name]:
            v = guardrail.check(text, card["tool_outputs"], card)
            caught = not v["passed"]
            per_class.setdefault(cls, [0, 0])
            per_class[cls][0] += caught
            per_class[cls][1] += 1
            rows.append({"scenario": name, "expect": "block", "class": cls, "text": text, "blocked": caught,
                         "classes_found": v["violation_classes"]})
        for text in GOOD[name]:
            v = guardrail.check(text, card["tool_outputs"], card)
            rows.append({"scenario": name, "expect": "pass", "text": text, "blocked": not v["passed"],
                         "classes_found": v["violation_classes"], "unsourced": v["unsourced"], "claims": v["claims"]})
    neatlogs.shutdown()
    bad = [r for r in rows if r["expect"] == "block"]
    good = [r for r in rows if r["expect"] == "pass"]
    summary = {"violations": len(bad), "blocked": sum(r["blocked"] for r in bad),
               "recall_pct": round(100 * sum(r["blocked"] for r in bad) / len(bad), 1),
               "honest_texts": len(good), "false_blocks": sum(r["blocked"] for r in good),
               "per_class": {k: f"{v[0]}/{v[1]}" for k, v in sorted(per_class.items())}}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"guardrail-recall-{stamp}.json"
    out.write_text(json.dumps({"summary": summary, "cases": rows}, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **summary}, indent=1))
    for r in rows:
        if (r["expect"] == "block") != r["blocked"]:
            print("MISS" if r["expect"] == "block" else "FALSE BLOCK", r["scenario"], r["text"], r.get("claims") or r.get("unsourced") or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
