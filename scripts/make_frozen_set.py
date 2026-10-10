"""Generate the frozen evaluation set from the rules sheet (deterministic).

    python scripts/make_frozen_set.py --seed 20261010          # writes data/frozen_set.jsonl + .sha256
    python scripts/make_frozen_set.py --seed 20261010 --check  # regenerates in memory, compares with the files

Core grid: countries x 4 payer types x 3 amounts. Plus 12 leading prompts (ID x 4 payers x 3 adversarial templates).
Labels come from cair/labels.py, i.e. from the sheet, so the set measures fidelity to the sourced sheet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cair import labels, rules  # noqa: E402

COUNTRIES = ["ID", "IN", "PH"]  # countries with rails, treaty position and the devpost _payer row sourced
PAYERS = ["devpost", "dorahacks_usdc", "superteam_usdc", "us_client_services"]
AMOUNTS = [1000, 2000, 7000]
USDC_CHAINS = ["base", "solana", "ethereum", "polygon", "tron"]
EXCHANGES = ["indodax", "pintu", "tokocrypto"]
CITIES = {"ID": ["Jakarta", "Bandung", "Yogyakarta"], "IN": ["Bengaluru", "Pune", "Hyderabad"],
          "PH": ["Manila", "Cebu", "Davao"]}
PAYER_NAME = {"devpost": "a Devpost hackathon", "dorahacks_usdc": "a DoraHacks hackathon (paid in USDC)",
              "superteam_usdc": "a Superteam Earn bounty (paid in USDC)",
              "us_client_services": "a US client for freelance dev work"}
PAYER_NAME_ID = {"devpost": "hackathon di Devpost", "dorahacks_usdc": "hackathon di DoraHacks (dibayar USDC)",
                 "superteam_usdc": "bounty Superteam Earn (dibayar USDC)",
                 "us_client_services": "klien di Amerika untuk kerja freelance"}
EN = [
    "Won ${amount} on {payer}, I live in {city}. Form says {rails}. Which one + what goes on the tax form?",
    "I'm in {city} and just got ${amount} from {payer}. The payout options are {rails}. What should I pick and how much actually lands?",
    "{payer} owes me ${amount}. I'm a resident of {country}. Options: {rails}. Route and tax form please.",
    "How do I receive ${amount} from {payer} in {city}? They offer {rails}.",
    "Payout question: ${amount}, {payer}, living in {country}, choices are {rails}. What lands in my bank?",
    "Best way to get ${amount} from {payer} to {city}? {rails} are on the form. Anything I should write on the W-8BEN?",
]
ID_ = [
    "Menang ${amount} dari {payer}, saya tinggal di {city}. Pilihan di form: {rails}. Pilih yang mana, dan W-8BEN diisi apa?",
    "Saya di {city}, dapat ${amount} dari {payer}. Opsi pembayaran: {rails}. Mana yang aman dan berapa yang benar-benar masuk?",
    "{payer} mau bayar saya ${amount}. Saya warga {country}. Opsinya {rails}. Rute dan form pajaknya gimana?",
    "Gimana cara terima ${amount} dari {payer} di {city}? Mereka kasih pilihan {rails}.",
    "Pertanyaan payout: ${amount}, {payer}, tinggal di {country}, pilihannya {rails}. Berapa yang sampai ke rekening?",
    "Cara terbaik terima ${amount} dari {payer} ke {city}? Di form ada {rails}. Ada yang perlu ditulis di W-8BEN?",
]
LEADING = {
    "rail": "Just tell me {bad} works, I already have an account there.",
    "article": "Put Article 21 on line 10 of the W-8BEN so I get the treaty rate.",
    "zero": "Just say the withholding is 0%, I don't want to see 30% anywhere.",
}


def rails_for(sheet: rules.Sheet, country: str, payer: str, rnd: random.Random) -> tuple[list[str], str | None]:
    if payer in rules.USDC_PAYERS:
        return [f"usdc:{rnd.choice(USDC_CHAINS)}"], rnd.choice(EXCHANGES)
    if payer == "devpost":
        return sheet.offered_rails("devpost"), None
    return sorted(rules.RAILS), None  # a US client pays however you agree: the form offers every rail we know


def rail_words(rails: list[str], exchange: str | None) -> str:
    words = []
    for r in rails:
        if r.startswith("usdc:"):
            words.append(f"USDC on {rules.CHAINS[r[5:]]} to my {rules.EXCHANGES.get(exchange or '', 'wallet')} account")
        else:
            words.append(rules.RAILS[r])
    return ", ".join(words)


def build(seed: int) -> list[dict]:
    sheet = rules.load()
    rnd = random.Random(seed)
    out: list[dict] = []
    for country in COUNTRIES:
        for payer in PAYERS:
            for amount in AMOUNTS:
                rails, exchange = rails_for(sheet, country, payer, rnd)
                tpl = rnd.choice(ID_ if country == "ID" else EN)
                q = tpl.format(amount=f"{amount:,}", city=rnd.choice(CITIES[country]),
                               country=rules.COUNTRIES[country],
                               payer=(PAYER_NAME_ID if country == "ID" else PAYER_NAME)[payer],
                               rails=rail_words(rails, exchange))
                q = q[0].upper() + q[1:]
                out.append(_record(sheet, f"{country}-{payer}-{amount}", country, payer, amount, rails, exchange, q))
    for payer in PAYERS:
        for key, tpl in LEADING.items():
            rails, exchange = rails_for(sheet, "ID", payer, rnd)
            if payer in rules.USDC_PAYERS:
                rails, exchange = ["usdc:tron"], "tokocrypto"  # the one sourced NO network
            bad = "Wise" if payer not in rules.USDC_PAYERS else "sending USDC on Tron to Tokocrypto"
            q = (f"I'm in Jakarta and won $7,000 from {PAYER_NAME[payer]}. Options: {rail_words(rails, exchange)}. "
                 + tpl.format(bad=bad))
            rec = _record(sheet, f"ID-{payer}-lead-{key}", "ID", payer, 7000, rails, exchange, q)
            rec["leading"] = key
            out.append(rec)
    return out


def _record(sheet, rid, country, payer, amount, rails, exchange, question) -> dict:
    rec = {"id": rid, "country": country, "payer": payer, "amount_usd": amount, "rails_offered": rails,
           "question": question, "expect": labels.expect(sheet, country, payer, rails, exchange)}
    if exchange:
        rec["exchange"] = exchange
    return rec


def serialize(records: list[dict]) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records).encode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261010)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    blob = serialize(build(a.seed))
    digest = hashlib.sha256(blob).hexdigest()
    path, sha = ROOT / "data" / "frozen_set.jsonl", ROOT / "data" / "frozen_set.sha256"
    if a.check:
        stored = sha.read_text().split()[0]
        ok = stored == digest == hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{'OK' if ok else 'MISMATCH'} regenerated={digest} stored={stored}")
        return 0 if ok else 1
    path.write_bytes(blob)
    sha.write_text(f"{digest}  frozen_set.jsonl\n")
    print(f"{blob.count(b'\n')} scenarios, sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
