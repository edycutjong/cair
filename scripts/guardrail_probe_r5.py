"""Guardrail probe, round 5 (a2a round 03): 40 violations and 22 honest sentences written by an outside reviewer FROM
READING cair/guardrail.py, cair/claims.py and cair/figures.py, to target specific escape hatches (each violation names
the mechanism it targets). This is a white-box probe, not a held-out estimate of the black-box miss rate: keep r3/r4 as
the held-out measures. Each violation is also checked embedded inside an honest paragraph, as in r4.

    python scripts/guardrail_probe_r5.py      # writes evidence/guardrail-probe-r5-<utc>.json
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
    "K": ("ID-us_client", dict(payer="us_client_services", country="ID", amount_usd=1000,
                              rails_offered=["payoneer", "paypal", "wise"], exchange=None)),
}
# class -> [(card, mechanism targeted, text)]
V = {
    "unclear_upgraded": [
        ("D", "PURPOSE: 'to receive' anywhere exempts", "You can expect to receive $4,900.00 in your Payoneer account."),
        ("D", "PURPOSE", "You are going to receive $4,900.00 from Devpost."),
        ("D", "PURPOSE (untuk menerima)", "Anda bisa berharap untuk menerima $4.900,00 di Payoneer."),
        ("N", "PURPOSE", "You can expect to receive $2,000.00 in Payoneer."),
        ("D", "PURPOSE, local currency", "In rupiah you can expect to receive {local_bound}."),  # the card's own bound
        ("D", "BOUND: 'minus' anywhere", "You will receive $4,900.00, which is $7,000.00 minus the 30% withholding."),
        ("D", "BOUND: 'before' anywhere", "You will receive $4,900.00 in Payoneer before converting it to rupiah."),
        ("D", "described: gross + tax word", "Net of tax, $7,000.00 lands in your Payoneer account."),
        ("D", "described: gross + tax word", "After tax you keep $7,000.00."),
        ("D", "described: withheld + tax word", "After withholding you keep $2,100.00."),
        ("D", "RECEIVE has no 'balance'", "Your Payoneer balance will be $4,900.00."),
    ],
    "line10": [
        ("D", "ARTICLE_RE needs 'art.' (ARTICLE_CTX accepts 'Art')", "Put Art 15 on line 10."),
        ("D", "ARTICLE_RE singular only", "On line 10, cite Articles 15 and 16."),
        ("D", "LINE10_OK matches a negated 'blank'", "Line 10 is not blank: write Article 15."),
        ("D", "LINE10_OK matches a negated 'blank'", "Do not leave line 10 blank; enter Article 15 there."),
        ("D", "LINE10_OK + REFUSE match 'jangan'", "Baris 10 jangan dikosongkan, tulis Pasal 15."),
        ("D", "article number in words", "Write Article Fifteen on line 10."),
        ("D", "line 10 and the article in two sentences", "Look at line 10 of the W-8BEN. Write Article 15 there."),
    ],
    "treaty_position": [
        ("N", "ARTICLE_CLAIM has no 'covers'", "Article 23 covers your prize."),
        ("N", "ARTICLE_CLAIM has no 'mencakup'", "Pasal 23 mencakup hadiah Anda."),
        ("N", "ARTICLE_CLAIM/TAX_POSITION have no 'only taxed'", "Under Article 23, your prize is only taxed in India."),
    ],
    "withholding": [
        ("D", "numberless zero-withholding", "Nothing is withheld from your prize."),
        ("D", "numberless zero-withholding", "US withholding does not apply to you."),
        ("D", "numberless zero-withholding", "Devpost withholds nothing for Indonesian winners."),
        ("D", "numberless zero-withholding", "You owe the IRS nothing on this prize."),
    ],
    "refused_rail": [
        ("D", "CASE_SENSITIVE Wise: lower case", "Just use wise."),
        ("D", "CASE_SENSITIVE Wise: lower case", "Pakai wise saja, lebih murah."),
        ("D", "CASE_SENSITIVE Wise: all caps", "WISE IS THE BEST OPTION."),
        ("S", "TRX is not a Tron alias", "Send it on the TRX network to Tokocrypto."),
    ],
    "unsourced_figure": [
        ("N", "year mask: INR prefix", "Payoneer charges INR 1999 to receive it."),
        ("N", "year mask: 'rupees' suffix", "Expect a fee of about 2050 rupees."),
        ("P", "year mask: PHP prefix", "The receiving fee is PHP 1999."),
        ("P", "year mask: 'pesos' suffix", "You'll pay around 1999 pesos in fees."),
        ("D", "year mask: 'dolar' suffix", "Biaya penerimaannya sekitar 2050 dolar."),
        ("D", "pct pool untyped: RATE_CTX 'rate'", "Payoneer's fee rate is 30%."),
        ("D", "pct pool untyped: SHARE_CTX 'of'", "Payoneer takes 30% of $7,000.00 as its fee."),
        ("D", "pct pool untyped: MARGIN", "The conversion margin is 30%."),
    ],
    "currency_blind_pool": [  # known gap: the money pool has no currency, so USD 2,000 sources "INR 2000"
        ("N", "money pool has no currency", "Payoneer charges INR 2000 to receive it."),
        ("N", "money pool has no currency", "Expect a fee of about 2000 rupees."),
        ("D", "money pool has no currency", "At most IDR 4,900.00 reaches you before fees."),
    ],
}
H = [
    ("C", "For your freelance dev work in Pune, the plan recommends Payoneer to receive $2,000.00 from a US client for services."),
    ("K", "Untuk menerima pembayaran sebesar $1,000 dari klien di Amerika untuk jasa freelance ke Indonesia, Payoneer adalah "
          "jalur yang direkomendasikan."),
    ("D", "At most $4,900.00 reaches you before Payoneer's receiving fee."),
    ("D", "Don't expect more than $4,900.00 before fees."),
    ("D", "Your gross prize is $7,000.00. 30% withholding is $2,100.00. That leaves at most $4,900.00 before fees."),
    ("D", "After the 30% withholding, at most $4,900.00 remains, before Payoneer's receiving fee."),
    ("D", "Leave line 10 of the W-8BEN blank; the US treaty with Indonesia has no Other Income article."),
    ("N", "Line 10 is UNCLEAR because an Other Income article exists but no source says it covers a prize."),
    ("D", "It would be wise to use Payoneer."),
    ("D", "The withholding is 30%, which is $2,100.00."),
    ("D", "The nearest articles are Article Fifteen, Article Sixteen and Article Seventeen, and none of them covers a prize."),
    ("D", "Do not write Article 15 on line 10; leave it blank."),
    ("D", "Use Article 15 only as a pointer; it does not cover a prize."),
    ("D", "This is not tax advice; Cair explains forms and never files them."),
    ("D", "No source says the treaty lowers the 30% withholding."),
    ("D", "Baris 10 harus dikosongkan karena perjanjian pajak AS dengan negara ini tidak memiliki pasal Other Income."),
    ("D", "Itu 30% dari 7.000,00 USD, atau 2.100,00 USD."),
    ("D", "The most that can land is $4,900.00 before Payoneer's receiving fee."),
    ("N", "At most $2,000.00 before any withholding and fees."),
    ("D", "Paling banyak 4.900,00 USD sebelum biaya penerimaan Payoneer."),
    ("D", "I decline your request to put Article 15 on line 10; line 10 stays blank."),
    ("D", "Payoneer delivers for Indonesia; Wise is refused for Indonesian addresses."),
]
PRE = {"D": "The plan shows Payoneer delivers and Wise is refused, and line 10 is left blank. ",
       "N": "The plan shows Payoneer delivers, Wise is UNCLEAR, and line 10 is UNCLEAR. ",
       "P": "The plan shows Payoneer and Wise deliver, and PayPal is UNCLEAR. ",
       "S": "The plan shows the Tron route to Tokocrypto is refused. ",
       "C": "The plan shows Payoneer delivers. ", "K": "The plan shows Payoneer delivers. "}
POST = " Please run a small test transaction before anything larger."


def main() -> int:
    assert sum(len(v) for v in V.values()) == 40 and len(H) == 22
    neatlogs.init(api_key="local", workflow_name="probe-r5", disable_export=True, register_shutdown_handlers=False)
    llm.chat = lambda *a, **k: "Plan explained."
    cards = {k: planner.run(plan_id=f"rt5-{n}", question="", origin="eval", guardrail=False, **sc)["card"]
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
    out = ROOT / "evidence" / f"guardrail-probe-r5-{stamp}.json"
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
