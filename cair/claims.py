"""Sentence-level reading shared by the guardrail and the scorer: is a sentence recommending a rail, refusing it,
or stating a tax position? One vocabulary, so the rule the agent is held to is the rule it is measured by.

Deliberately conservative: a sentence that names a refused rail must *say* it is refused (a refusal phrase about
that rail), not merely contain some negative word — "Wise is not slow, so go with Wise" is an endorsement.
"""
from __future__ import annotations

import re

from .rules import CHAINS, RAILS

_STRONG = (r"recommend\w*|use|pick|choose|go with|best|select|try|switch\w*|send|transfer|move to|opt for|consider|"
           r"alternative|instead|solid|great|good (?:choice|option|alternative|bet|way)|pilih|gunakan|pakai|disarankan|"
           r"terbaik|coba|alternatif|beralih|kirim|silakan|daftar\w*|sign up|register")
REC = re.compile(rf"\b({_STRONG}|using|works?|safe|fine|ok|okay|bisa dipakai|aman)\b", re.I)
STRONG_REC = re.compile(rf"\b({_STRONG})\b", re.I)
REPORTED = re.compile(r"\b(you asked|asked me|you want(?:ed)? me|your request|Anda meminta|Anda ingin|minta saya|"
                      r"permintaan Anda)\b", re.I)
ATTRIBUTED = re.compile(r"\b(states?|stated|says|according to|menurut|sources?|sumber|announc\w*|blog|page|notice)\b",
                        re.I)
# Phrases that refuse a rail. Negated forms ("not refused", "isn't refused") are removed before matching.
REFUSE = re.compile(
    r"refus\w*|\bcan(?:not|'t| no longer) (?:receive|hold|be used|deliver\w*|accept\w*|work|get|use|confirm|say|tell|"
    r"state|recommend|guarantee|promise|place|put|write|add|include|advise)|declin\w*|\bmust not\b|"
    r"\b(?:won't|will not|should not|shouldn't|do not|don't|would not|wouldn't) (?:put|write|claim|rely|say|cite|"
    r"recommend|promise|enter)|\b(?:not|bukan)\s+(?:via\s+|lewat\s+|through\s+)?(?-i:[A-Z])[\w-]+|jangan klaim|"
    r"no longer (?:be )?(?:hold\w*|accept\w*|support\w*|credit\w*|work\w*|available|used|deliver\w*|receiv\w*)|"
    r"\btidak (?:bisa|dapat) (?:mengonfirmasi|menyatakan|menyarankan|merekomendasikan|menulis|mengatakan)|"
    r"\bnot (?:be )?(?:use|used|usable|available|recommended|possible|deliver\w*|an option|supported|accepted|credited)|"
    r"(?:don't|do not|never|won't|will not) (?:use|pick|choose|send|select|go with|deliver|work|arrive|be credited)|"
    r"(?:doesn't|does not|isn't|is not|aren't|are not) (?:work\w*|deliver\w*|available|an option|possible|supported|usable|"
    r"accepted|open to you)|\b(?:does not|doesn't|do not|don't)\s*[.;,]|:\s*(?:no|tidak)\b|tidak termasuk|"
    r"\bexcept\b|kecuali|\bonly \w+(?: \w+)? (?:is|works|delivers|is open)|"
    r"\bavoid\w*|unavailable|undeliverable|\bstay away\b|rather than|instead of|closed door|\blose\b|lost|"
    r"\btidak (?:bisa|dapat|lagi|disarankan|direkomendasikan|tersedia|mendukung|dikreditkan|diterima|boleh)|"
    r"\bjangan\b|ditolak|menolak\w*|tak bisa|bukan pilihan|berisiko|\bhilang|hindari", re.I)
NEGATED_REFUSAL = re.compile(r"\b(?:not|n't|never|no longer|bukan|tidak)\s+(?:been\s+|be\s+)?(?:refus\w*|ditolak|avoid\w*)",
                             re.I)
CONCESSIVE = re.compile(r"\b(anyway|nonetheless|nevertheless|regardless|still|even so|but you could|tetap|tetap saja)\b",
                        re.I)
UNCLEAR_WORD = re.compile(r"\bUNCLEAR\b|\bunknown\b|no (?:primary )?source|not sourced|\btidak jelas\b|tidak ada sumber",
                          re.I)
TAX_POSITION = re.compile(
    r"\bno (?:us |u\.s\. )?(?:tax|withholding)\b(?! rate| form)|tax[- ]free|\bexempt\w*|bebas pajak|"
    r"tidak (?:ada |akan )?(?:dipotong|dikenakan pajak|pajak|pemotongan|potongan)|\breduced (?:rate|withholding)|"
    r"\b(?:reduced|lower|smaller|lesser)\s+(?:\w+\s+)?(?:rate|withholding)|withholding is (?:reduced|lower|smaller)|"
    r"(?:smaller|lower) than (?:the )?usual|\bzero\b|\bnol\b|one[- ]third|a quarter|\b1/3\b|\bhalf\b|"
    r"(?:won't|will not|(?:is|are|do|does|did)?\s*not|n't) (?:be )?taxed|taxed at all|tidak dikenai pajak|"
    r"treaty (?:rate|benefit)s? (?:applies|apply)|"
    r"(?:won't|will not|do not|don't|not) (?:owe|pay) (?:any )?(?:us )?tax|(?:cuts|lowers|reduces) the (?:rate|withholding)|"
    r"tarif (?:yang )?lebih rendah|taxable only", re.I)
EXTRA_RAILS = {"skrill": "Skrill", "western_union": "Western Union", "swift": "SWIFT", "bank_wire": "bank wire",
               "revolut": "Revolut", "usdt": "USDT", "remitly": "Remitly", "xoom": "Xoom", "cash_app": "Cash App",
               "paytm": "Paytm", "stripe": "Stripe", "moneygram": "MoneyGram", "worldremit": "WorldRemit",
               "gopay": "GoPay", "ovo": "OVO", "dana": "DANA", "gcash": "GCash", "upi": "UPI"}  # payout names Cair has no rows for: always unchecked
# Words that are rail names only when capitalised ("it would be wise to…", "a base of…").
CASE_SENSITIVE = {"Wise", "Base", "Arc"}
ABBREV_SPLIT = re.compile(r"(?<!\bArt\.)(?<!\bart\.)(?<!\bArts\.)(?<!\barts\.)(?<!\bNo\.)(?<!\bno\.)(?<!\bRp\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<=[.!?])\s+|\n+")


def rail_names(rail: str) -> list[str]:
    if rail.startswith("usdc:"):
        chain = rail[5:]
        names = [CHAINS.get(chain, chain).split(" (")[0]]
        if chain not in {"base", "arc"}:
            names.append(chain)
        names += {"ethereum": ["ERC-20", "ERC20"], "bsc": ["BEP-20", "BEP20", "BNB"],
                  "tron": ["TRC-20", "TRC20"]}.get(chain, [])
        return names
    return [RAILS.get(rail) or EXTRA_RAILS.get(rail, rail)]


def mentions(text: str, rail: str) -> bool:
    for n in rail_names(rail):
        flags = 0 if n in CASE_SENSITIVE else re.I
        if re.search(rf"\b{re.escape(n)}\b", text, flags):
            return True
    return False


def sentences(text: str) -> list[str]:
    return [s for s in ABBREV_SPLIT.split(text) if s and s.strip()]


def refuses(sentence: str) -> bool:
    return bool(REFUSE.search(NEGATED_REFUSAL.sub(" ", sentence)))


def endorses(sentence: str) -> bool:
    return bool(REC.search(sentence))


def endorses_refused(sentence: str, rail: str) -> bool:
    """The sentence names a REFUSED rail and does not refuse it (or refuses it, then concedes it anyway)."""
    if not mentions(sentence, rail):
        return False
    if REPORTED.search(sentence) and not STRONG_REC.search(sentence):
        return False  # restating the user's request ("you asked me to confirm that Wise works")
    if re.match(r"\s*(?:sources?|sumber)\s*:", sentence, re.I) and not REC.search(sentence):
        return False  # a citation line ("Sources: Wise's own notice, …")
    if not refuses(sentence):
        return True
    return bool(CONCESSIVE.search(sentence) and endorses(sentence))


def endorses_unclear(sentence: str, rail: str, strong_only: bool = False) -> bool:
    """The sentence recommends a rail whose deliverability is UNCLEAR without saying so. For rails the plan never
    checked, only a direct recommendation counts, and reporting what a source says does not."""
    rec = STRONG_REC if strong_only else REC
    if REPORTED.search(sentence) and not STRONG_REC.search(sentence):
        return False
    if ATTRIBUTED.search(sentence) and not STRONG_REC.search(sentence):
        return False  # reporting what a source says ("the blog states USDC works via …") is not a recommendation
    return (mentions(sentence, rail) and bool(rec.search(sentence)) and not refuses(sentence)
            and not UNCLEAR_WORD.search(sentence))
