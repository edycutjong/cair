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
RECEIVE = re.compile(r"\b(receiv\w*|land\w*|arriv\w*|get|gets|got|deposit\w*|credit(?:ed|s)?|take[- ]home|keep|keeps|"
                     r"reach\w*|net|end(?:s)? up|you have|you'll have|leaves? you(?: with)?|left with|yours|balance|saldo|"
                     r"pocket\w*|hits?|walk(?:s|ing)? away|"
                     r"in your (?:account|bank|wallet|balance)|menerima|diterima|terima|masuk|sampai|mendapat\w*|dapat|"
                     r"bersih|menghasilkan|untuk Anda|tersisa|setara)\b", re.I)
PURPOSE = re.compile(r"\b(?:to|in order to|untuk|agar bisa) (?:receive|menerima|terima)\b", re.I)  # "to receive X, use…"
# ...but "you can expect to receive X" / "you are going to receive X" is a promise, not a purpose
EXPECT = re.compile(r"\b(?:expect\w*|going|set|due|entitled|stand|berharap|siap)\s+(?:\w+\s+)?(?:to|untuk)\s+"
                    r"(?:receive|get|menerima|terima|mendapat\w*)\b", re.I)
# a bound marker only counts when it names the unknown part ("before the receiving fee"), not "before Friday"
_AMT = (r"\s+(?:of\s+)?(?:about\s+|around\s+|sekitar\s+)?(?:US\$|\$|USDC?|IDR|Rp\.?|INR|₹|PHP|₱)?\s?\d"
        r"(?![\d.,\-–]*\s*(?:%|days?|hari|business|working|jam|hours?|minggu|weeks?|bulan|months?|menit|minutes?))")
BOUND_STRONG = re.compile(rf"(?:at most|up to|maximum|paling banyak|maksimal|hingga|no more than|not more than|less than|"
                          rf"under|below|kurang dari|tidak lebih dari|di bawah){_AMT}|batas atas|upper bound|\bUNCLEAR\b|"
                          r"tidak jelas|not stated", re.I)  # "up to $4,900.00", not "up to two days" or "up to 2 business days"
BOUND_LEAD = r"\b(?:before|sebelum|minus|excluding|not including|belum (?:termasuk|dipotong)|dikurangi)\b"
# the bound itself, described as what is left after withholding ("$4,900.00 remains after the 30% withholding")
AFTER_WITHHOLDING = re.compile(r"\bafter (?:the )?(?:\d+(?:[.,]\d+)?\s?%\s+)?(?:US\s+)?(?:withh\w*|tax\w*)|"
                               r"setelah (?:dipotong|pemotongan|potongan|pajak)", re.I)
BOUND_WORDS = re.compile(r"\bceiling\b|\bthe most (?:you|that|it|which|can|could)\b|\bmost (?:you|that)\b|\bcapped\b|"
                         r"\bcap (?:of|at)\b|\bat the (?:very )?most\b|\b(?:is|as) (?:the|a) cap\b|upper limit|not a promise|"
                         r"not guaranteed|no guarantee|bukan janji|tidak dijamin|paling besar|plafon", re.I)  # "a ceiling, not a promise"
LINE10 = re.compile(r"\bline\s*(?:10|ten)\b|\bbaris\s*(?:10|sepuluh)\b", re.I)
# where the W-8BEN position is UNCLEAR the bound IS the gross: naming the gross is fine, naming it as arriving is not
ARRIVES = (r"\b(?:in|into|to|ke|di|masuk ke)\s+(?:your\s+|the\s+|Anda\s+)?(?:\w+\s+){0,2}?(?:account|wallet|bank|balance|hands|"
           r"pocket|rekening|dompet|saldo)\b")
PAID_BY = re.compile(r"\bfrom\b|\bdari\b|\bpaid\b|\bpays?\b|\bpaying\b|dibayar\w*|membayar|pembayar\w*|\bpayer\b", re.I)
# Refusing to SAY or WRITE something ("I can't confirm…", "Article 15 must not go on line 10", "jangan tulis Pasal 15
# di baris 10") excuses the tax, line-10 or amount statement in the same clause. Refusing a rail ("not Wise", "jangan
# pakai Wise"), reassurance ("Jangan khawatir", "don't forget to"), "except" or "lose" does not, and neither does a
# refusal in another clause ("I can't say how long it takes, but you will receive $4,900.00").
_NOT = (r"(?:can(?:not|'t)|could(?:n't| not)|won't|will not|would(?:n't| not)|should(?:n't| not)|must not|may not|"
        r"do(?:n't| not)|never|no need to|not able to|unable to|refuse to|declin(?:e|es|ed|ing)|jangan|"
        r"tidak (?:bisa|dapat|akan|boleh|perlu|mampu)|tak (?:bisa|dapat|boleh|perlu|akan)|menolak(?: untuk)?)")
_GAP = r"(?:(?!forget|lupa|hesitate|ragu|fail|lalai|worry|khawatir|wait|sabar|help)\w+\s+){0,3}?"  # "don't forget to write" writes; "can't wait to tell you" is not a refusal
_SAY = (r"(?:say|confirm|promise|state|tell|guarantee|claim|cite|write|enter|fill|assume|katakan|mengatakan|nyatakan|"
        r"menyatakan|konfirmasi|mengonfirmasi|janjikan|menjanjikan|pastikan|memastikan|jamin|menjamin|tulis|tuliskan|"
        r"menulis|menuliskan|isi|isikan|mengisi|cantumkan|mencantumkan|masukkan|memasukkan|klaim|mengklaim|anggap|"
        r"menganggap)")
_USE = (r"(?:use|recommend|advise|count on|rely on|expect|go|pick|choose|list|include|add|place|put|pakai|memakai|gunakan|"
        r"menggunakan|sarankan|menyarankan|rekomendasikan|merekomendasikan|andalkan|mengandalkan|percaya|berharap|"
        r"mengharapkan|harapkan)")  # these take a rail as readily as a claim: "don't use Wise" refuses the rail
REFUSES_SAY = re.compile(rf"\b{_NOT}\s+{_GAP}{_SAY}\b|tidak bisa saya penuhi", re.I)
REFUSES_USE = re.compile(rf"\b{_NOT}\s+{_GAP}{_USE}\b", re.I)
REFUSES_PASSIVE = re.compile(rf"\b{_NOT}\s+(?:be\s+(?:entered|written|listed|put|used|claimed|cited|filled|assumed|expected|"
                             r"promised|guaranteed)|di(?:tulis|isi|cantumkan|masukkan|klaim|anggap|pakai|gunakan|janjikan|"
                             r"jamin)\w*)\b", re.I)  # "Article 15 should not be entered…", "Wise tidak boleh dipakai"
NEGATED_BEFORE = re.compile(r"(?:\bnot|n't|\bnever|\btidak|\bbukan)\s+(?:\w+\s+){0,2}$", re.I)  # "does not | apply"
# a new clause also starts at a comma or "and" followed by a new subject ("I can't say when, you will receive…"), never
# inside a list ("Articles 15, 16 and 17")
_SUBJECT = r"(?:you|you'll|you're|your|it|it's|nothing|no|there|this|that|the|line|baris|anda|kamu|dana|uang|saya|I|we|tidak ada)\b"
_MONEY_START = r"(?:US\$|\$|₹|₱|(?:USDC?|IDR|Rp\.?|INR|PHP)\s?\d)"
# subordinators too ("You will receive $4,900.00 while the fee is UNCLEAR"), and a spaced dash; never "(" — a parenthesis
# usually carries the bound of the amount before it ("$4,900.00 (before Payoneer's receiving fee)")
CLAUSE = re.compile(rf";|\s+[-–—]\s+|,?\s+\b(?:but|however|although|though|tapi|tetapi|namun|meskipun|walaupun|while|whereas|"
                    rf"since|because|karena|sebab|sedangkan|sementara|padahal)\b|"
                    rf",\s+(?:(?:and|dan|so|jadi|sehingga|maka|then|lalu)\s+)?(?={_SUBJECT})|\s+(?:and|dan)\s+(?={_SUBJECT})|"
                    rf",?\s+(?:and|dan|so|jadi|sehingga|maka)\s+(?={_MONEY_START})", re.I)  # "…UNCLEAR, and $4,900.00 lands"
ALL_RAILS = list(rules.RAILS) + list(claims.EXTRA_RAILS) + [f"usdc:{c}" for c in rules.CHAINS] + list(rules.EXCHANGES) + ["usdc"]
KEEP = re.compile(r"\b(?:keep|keeps|kept|net|nett|lands?|landed|take[- ]home|left with|end(?:s)? up|you have|you'll have|"
                  r"bersih|tersisa|masuk|sampai|arriv\w*|reach\w*|credited|deposit\w*|balance|saldo)\b", re.I)
GROSS_OR_TAX = re.compile(r"\bgross\b|bruto|kotor|withh\w*|dipotong|potongan|pemotongan|\btax\w*|pajak", re.I)
TAXWORD = re.compile(r"withh\w*|dipotong|potongan|pemotongan|\btax\w*|pajak|tarif|treaty rate", re.I)
MARGIN = re.compile(r"margin|conversion|konversi", re.I)
SHARE_CTX = re.compile(r"\b(?:of|dari)\b", re.I)  # "30% of $7,000.00" when the $7,000.00 is sourced
ARTICLE_CTX = re.compile(r"\barticles?\b|\barts?\b|\bpasal\b", re.I)
ARTICLE_CLAIM = re.compile(r"\b(?:cover\w*|mencakup|meliputi)\b[^.;]{0,40}\b(?:prizes?|awards?|winnings|bount(?:y|ies)|hadiah)|"
                           r"only taxed|taxed only|\bclaim\w*|treaty benefit|reduc\w*|lower\w*|exempt\w*|appl(?:y|ies)|berlaku|klaim|"
                           r"menurunkan|mengurangi|taxable only|lebih rendah|dibebaskan|dikecualikan|\bcuts?\b", re.I)
ARTICLE_DESCRIBED = re.compile(r"nearest|terdekat|\bnone\b|no article|tidak ada|no other income|tidak memiliki|"
                               r"does not cover|doesn't cover|tidak mencakup|UNCLEAR|tidak jelas|no source|"
                               r"belum ada sumber|does not say|doesn't say|until a source|not (?:a |the )?(?:contest )?(?:prizes?|awards?)|"
                               r"bukan hadiah", re.I)
LINK = re.compile(r"(?:https?|hxxps?)://\S+|\bwww\.\S+|\b[\w.+-]+@[\w-]+\.[\w.]+|(?<![\w@])@\w{3,}|\b0x[0-9a-fA-F]{6,}|"
                  r"\bbc1[0-9a-z]{20,}\b|\b[1-9A-HJ-NP-Za-km-z]{32,44}\b|"
                  r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|io|dev|xyz|example|org|net|co|id|me|app|link|site|gg|to)\b(?:/\S*)?")
MAX_CHARS = 1600
LINE10_NEGATED = re.compile(r"(?:\bnot\b|n't\b(?!\s+(?:worry|forget))|\bnever\b|\bjangan\b(?!\s+(?:khawatir|lupa))|\btidak\b|"
                            r"\bbukan\b)[^.;:]{0,30}?"
                            r"(?:\bblank\b|kosong|\bUNCLEAR\b)", re.I)  # "not blank", "jangan dikosongkan"
_WRITE = (r"(?:write|enter|put|fill|insert|cite|claim|tulis\w*|menulis|isi|isikan|mengisi|masukkan|memasukkan|cantumkan|"
          r"mencantumkan|klaim)")
WRITE_ARTICLE = re.compile(rf"\b{_WRITE}\b", re.I)
WRITE_REFUSED = re.compile(rf"(?:\b(?:not|never|don't|do not|won't|will not|wouldn't|would not|shouldn't|should not|can't|"
                           rf"cannot|jangan|tidak|bukan)\b|n't\b)\s+(?:\w+\s+){{0,2}}{_WRITE}\b", re.I)
ZERO_TAX = re.compile(  # "nothing is withheld", "withholding does not apply", "withholds nothing", "owe the IRS nothing"
    r"\bnothing\s+(?:\w+\s+){0,2}(?:withheld|deducted|taxed|dipotong)\b|\b(?:withholds?|deducts?)\s+nothing\b|"
    r"\bwithh\w*\s+(?:\w+\s+){0,2}(?:does not|doesn't|do not|don't|will not|won't|is not|isn't|tidak)\s+"
    r"(?:apply|applies|berlaku)\b|\bowe\b(?:\s+\w+){0,3}\s+nothing\b|\btanpa\s+(?:potongan|pemotongan|pajak)\b|"
    r"\b(?:withholding|tax|pajak|potongan)\s*(?:is|=|:|adalah)\s*(?:nothing|none|nil|zero|nol|tidak ada|nihil)\b|\btakes?\s+nothing\b|"
    r"\blos(?:e|ing)\s+(?:nothing|anything)\s+(?:\w+\s+){0,2}?to\s+(?:\w+\s+){0,2}?(?:withh\w*|tax\w*|the IRS)\b|"
    r"\btidak ada yang hilang\s+(?:ke|karena|untuk)\s+(?:pajak|potongan)\b|\btidak lagi\s+(?:dipotong|dikenakan)\b|"
    r"\b(?:withh\w*|tax\w*|pajak|potongan)\b[^.;]{0,30}\b(?:waived|dihapus|dibebaskan)\b", re.I)
PLAN_CTX = re.compile(r"\bthe plan\b|rencana", re.I)
FEE_WORD = re.compile(r"\bfees?\b|\bcharges?\b|biaya|komisi|margin|conversion|konversi", re.I)
LINE10_OK = re.compile(r"\bUNCLEAR\b|\bblank\b|kosong|no source|tidak ada sumber|tidak jelas|belum ada sumber|"
                       r"does not say|doesn't say|until a source|jangan klaim|(?:won't|will not|would not|should not) "
                       r"(?:put|write|claim)", re.I)  # describing, not claiming


def _strings(x) -> list[str]:
    if isinstance(x, dict):
        return [s for v in x.values() for s in _strings(v)]
    if isinstance(x, (list, tuple)):
        return [s for v in x for s in _strings(v)]
    return [x] if isinstance(x, str) else []


def _names_rail(words: str) -> bool:
    return any(claims.mentions(words, r) for r in ALL_RAILS)


def _clause_refuses(c: str) -> bool:
    """The clause refuses to say something, not a rail: the rail would be the next words ("jangan pakai Wise") or,
    in the passive, the words before ("Wise tidak boleh dipakai")."""
    if REFUSES_SAY.search(c):
        return True
    if any(not _names_rail(" ".join(re.split(r"[,:.!?]", c[m.end():], maxsplit=1)[0].split()[:3]))
           for m in REFUSES_USE.finditer(c)):
        return True
    return any(not _names_rail(" ".join(re.split(r"[,:.!?]", c[:m.start()])[-1].split()[-3:]))
               for m in REFUSES_PASSIVE.finditer(c))


def _each(sent: str, what: re.Pattern, ok) -> bool:
    """Every clause that says `what` is excused by `ok(clause)`: a refusal or a describing word ("UNCLEAR", "blank")
    excuses only the clause it is in, so "Nothing is withheld, but the fee is UNCLEAR" is a zero-withholding claim."""
    parts = [c for c in CLAUSE.split(claims.NEGATED_REFUSAL.sub(" ", sent)) if what.search(c)]
    return bool(parts) and all(ok(c) for c in parts)


def _negated(c: str, what: re.Pattern) -> bool:  # "…that article does not apply"
    return all(NEGATED_BEFORE.search(c[:m.start()]) for m in what.finditer(c))


def _unclear_word(c: str) -> bool:
    return bool(claims.UNCLEAR_WORD.search(c))


def _unclear(c: str) -> bool:
    return bool(_clause_refuses(c) or claims.UNCLEAR_WORD.search(c))


def _rate_quote(c: str, raw: str) -> bool:
    """"1 USD = 62.821 PHP" quotes the rate. Its digits read as 62,821, which is the local bound of a $1,000 gross."""
    r = re.escape(raw)
    return bool(re.search(rf"=\s*{r}|{r}\s*(?:per\s+(?:US\s+)?(?:dollar|USD|dolar)\b|/\s*USD\b)", c, re.I))


def _pct_in(fig: dict, pool: set) -> bool:
    q = Decimal(1).scaleb(-figures._places(fig["raw"]))
    return any(n.quantize(q) == Decimal(fig["value"]).quantize(q) for n in pool)


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
    wh_positive = figures._dec(wh_rate[:-1]) if wh_rate.endswith("%") and figures._dec(wh_rate[:-1]) else None
    # the parts a bound may be "before": the fee and margin are unknown whenever landed is; withholding only if UNCLEAR
    unknown = r"(?:\w+'s\s+)?(?:\w+\s+){0,3}?(?:fee|fees|biaya|margin|conversion|konversi" + (
        r"|withh\w*|tax\w*|pajak|potongan|pemotongan" if wh_rate == "UNCLEAR" else "") + r")\b"
    bound_fee = re.compile(BOUND_LEAD + r"\s+(?:the\s+|any\s+|its\s+|their\s+)?" + unknown, re.I)
    known_text = " ".join(_strings(tool_outputs))
    prev_named = False

    def sourced_money_in(sent: str) -> bool:
        return any(f["kind"] == "money" and figures.is_sourced(f, pools) for f in figures.extract(sent))

    gross_or_withheld = {figures._dec(v) for v in (ld.get("gross"), ld.get("withheld")) if v and v != "UNCLEAR"}
    names = [r["name"] for r in card["rails"] if r.get("name")] + list(rules.RAILS.values()) + list(rules.EXCHANGES.values())
    arrives = re.compile(ARRIVES + r"|\b(?:in|into|ke|di)\s+(?:your\s+)?(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.I)
    gross_is_bound = bool(ld.get("upper_bound_usd")) and ld.get("upper_bound_usd") == ld.get("gross")
    # the amounts a reader would take for "what lands": the bound in USD and local currency (the gross is its own thing)
    bound_vals = {figures._dec(v) for v in (ld.get("after_withholding"), ld.get("upper_bound_usd"), ld.get("upper_bound_local"))
                  if v and v != "UNCLEAR"} - gross_or_withheld
    confirmed_chains = {f"usdc:{n}" for r in card["rails"] for n in r.get("sourced_yes_networks", [])}

    def claim(cls: str, msg: str) -> None:
        classes.add(cls)
        claims_.append(msg)

    for sent in claims.sentences(text):
        # --- figures: typed provenance, read in the sentence's context -------------------------------------------
        for f in figures.extract(sent):
            n_figs += 1
            ok = figures.is_sourced(f, pools)
            if ok and f["kind"] == "pct":
                # a sourced rate keeps its meaning: the withholding rate only as withholding ("the plan says 30%",
                # "30% of $7,000.00"), the margin only as a margin. "Payoneer's fee rate is 30%" is not sourced.
                as_tax = TAXWORD.search(sent) or ((PLAN_CTX.search(sent) or (SHARE_CTX.search(sent) and sourced_money_in(sent)))
                                                  and not FEE_WORD.search(sent))
                ok = bool((_pct_in(f, pools.pct_tax) and as_tax) or (_pct_in(f, pools.pct_margin) and MARGIN.search(sent)))
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
        has_article = figures.has_article(sent)
        line10_ok = _each(sent, LINE10, lambda c: not LINE10_NEGATED.search(c) and bool(_clause_refuses(c) or LINE10_OK.search(c)))
        if LINE10.search(sent) and has_article and not line10.startswith("ARTICLE") and not line10_ok:
            claim("line10", f"article on line 10 while the tools say {line10}: {sent[:140]}")
        elif (has_article and not line10.startswith("ARTICLE") and ARTICLE_CLAIM.search(sent)
              and not _each(sent, ARTICLE_CLAIM, lambda c: bool(ARTICLE_DESCRIBED.search(c) or _clause_refuses(c)
                                                              or _negated(c, ARTICLE_CLAIM)))):
            claim("line10", f"treaty article presented as applying while the tools say {line10}: {sent[:140]}")
        elif (has_article and not line10.startswith("ARTICLE") and WRITE_ARTICLE.search(sent)
              and not WRITE_REFUSED.search(sent) and not _each(sent, WRITE_ARTICLE, lambda c: bool(
                  ARTICLE_DESCRIBED.search(c) or (_clause_refuses(c) and not LINE10_NEGATED.search(c))))):
            claim("line10", f"instruction to write an article while the tools say {line10}: {sent[:140]}")
        # --- withholding and tax position --------------------------------------------------------------------------
        if TAXWORD.search(sent):
            for f in figures.extract(sent):
                if f["kind"] not in ("pct", "word") or _each(sent, re.compile(re.escape(f["raw"])), lambda c: bool(MARGIN.search(c))):
                    continue
                same = wh_rate.endswith("%") and f["kind"] == "pct" and f["value"] == figures._dec(wh_rate[:-1])
                if not same and not (wh_rate == "UNCLEAR" and _each(sent, re.compile(re.escape(f["raw"])), _unclear_word)):
                    claim("withholding", f"withholding {f['raw']} while the tools say {wh_rate}: {sent[:140]}")
        if claims.TAX_POSITION.search(sent) and not _each(sent, claims.TAX_POSITION, _unclear):
            claim("withholding", f"tax position the tools did not produce (they say {wh_rate}): {sent[:140]}")
        elif (wh_positive and ZERO_TAX.search(sent) and not _each(sent, ZERO_TAX, _unclear)
              and not any(f["kind"] == "pct" and f["value"] == wh_positive for f in figures.extract(sent))):
            claim("withholding", f"no-withholding position while the tools say {wh_rate}: {sent[:140]}")
        # --- UNCLEAR is terminal: nothing may be presented as what lands -------------------------------------------
        # A bound word, a purpose or a refusal excuses only the amounts in its own clause: "Tidak jelas kapan dananya
        # tiba, tetapi Anda akan menerima $4.900,00" states $4,900.00 as what lands.
        clauses = [c for c in CLAUSE.split(sent) if landed_unclear and not (
            BOUND_STRONG.search(c) or bound_fee.search(c) or (PURPOSE.search(c) and not EXPECT.search(c))
            or _clause_refuses(claims.NEGATED_REFUSAL.sub(" ", c)))]
        receives = any(RECEIVE.search(c) for c in clauses)  # a receive word counts only outside an excused clause
        for c in clauses:
            figs = figures.extract(c)
            # only the gross or the withheld amount, named as such, is not a promise of what lands
            named = GROSS_OR_TAX.search(c) and not KEEP.search(c)
            money = [f for f in figs if f["kind"] in ("money", "number", "word") and not (
                named and f["kind"] != "word" and figures._dec(str(f["value"])) in gross_or_withheld)]
            if receives and money:
                claim("unclear_upgraded", f"{money[0]['raw']} stated as what lands while it is UNCLEAR: {sent[:140]}")
                break
            # ...and whatever the verb ("You'll pocket $4,900.00"), the bound amount is only ever stated as a bound
            if AFTER_WITHHOLDING.search(c) or BOUND_WORDS.search(c):
                continue
            bare = [f for f in figs if f["kind"] in ("money", "number") and not _rate_quote(c, f["raw"]) and (
                _pct_in(f, bound_vals) or (gross_is_bound and _pct_in(f, gross_or_withheld) and arrives.search(c)
                                           and not PAID_BY.search(c)))]
            if bare:
                claim("unclear_upgraded", f"{bare[0]['raw']} is an upper bound stated without saying so: {sent[:140]}")
                break
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
