# Guardrail — white-box probes and known gaps

The guardrail is a rule-based provenance check over the model's wording (`cair/guardrail.py`). On a held-out set nobody tuned it on it blocked 62 / 66 violations and 3 / 66 honest sentences ([README](../README.md), `evidence/guardrail-heldout-r4-20261010T084859Z.json`). The probes below were written by reading its code and aiming at it, so they are not held-out estimates; each is a script in `scripts/`, run before and after its fix, with the output in `evidence/`. Moved here from the README on 2026-10-11 so the README stays short; nothing was removed.

## Probe history

That rate holds for phrasings nobody aimed at the rules. A reviewer who
read the guardrail's code and aimed at it did better: on `75ba335` it blocked **0 / 40** of their sentences (`scripts/guardrail_probe_r5.py`,
`evidence/guardrail-probe-r5-20261011T013005Z.json`), because an exemption word anywhere in a sentence ("to receive", "before",
"minus", "blank") switched a check off. The fixes block 37 / 40 with 0 / 22 honest sentences blocked. A second probe written
against the fixed rules still got 12 / 25 through (`scripts/guardrail_probe_r6.py`), so the "UNCLEAR is terminal" check no longer
depends on a verb list where the bound is below the gross: when landed is UNCLEAR, that bound must be stated as a bound. That
probe now blocks 24 / 25. A third probe aimed at those rules (`scripts/guardrail_probe_r7.py`) got 46 / 47 through on `6ba11b2`:
the tax, line-10 and amount checks were excused by a detector of *rail* refusals, so "rather than Wise", "Jangan khawatir" or
"except" anywhere in a sentence switched them off; and where the bound is the gross (39 of the 48 frozen scenarios) the bound rule
left it out. Now a refusal to say or write something excuses a claim only in its own clause, and the gross may be named
but not as arriving: 47 / 47 blocked, 0 / 47 honest; the r3/r4 held-out violations re-checked behind those openers went from
19 / 69 blocked to 69 / 69. A fourth probe (`scripts/guardrail_probe_r8.py`) found that a comma or "and" still let a refusal in
one clause excuse a claim in the next: 2 / 12 blocked on `f785f3e`, 8 / 12 after. A fifth (`scripts/guardrail_probe_r9.py`)
found the same flaw in the bound check: "UNCLEAR", "tidak jelas", "not stated", or "up to"/"maksimal"/"hingga" before any
number (so also "up to 2 business days") anywhere in a sentence excused every amount in it, so "Tidak jelas kapan dananya
tiba, tetapi Anda akan menerima $4.900,00" passed. On `a4d986f` that probe blocked 0 / 16 and blocked 4 / 18 honest sentences
(two of them the ECB rate "1 USD = 62.821 PHP", whose digits equal the PHP 62,821 bound of a $1,000 gross); after the fix it
blocks 16 / 16 with 0 / 18 honest blocked, and the r3/r4 held-out landed-amount violations behind those openers went from
1 / 24 blocked to 24 / 24. A sixth (`scripts/guardrail_probe_r10.py`) put the bound word after "while", "since", "karena" or a
dash, inside the claim's own clause: 1 / 8 blocked on `b05e18e`, 7 / 8 after. A seventh (`scripts/guardrail_probe_r11.py`)
found the tax and line-10 checks still read their describing words on the whole sentence, so "Pajak tidak dipotong, tetapi
biaya Payoneer tidak jelas" and "Write Article 15 on line 10; Payoneer's receiving fee is UNCLEAR" passed: 2 / 13 blocked on
`7904688`, 13 / 13 after with 0 / 9 honest blocked, and the r3/r4 held-out withholding and article violations with a describing
tail went from 15 / 45 blocked to 45 / 45. Checking that fix found one more sentence-wide excuse: a refused write of something
else ("Don't put Wise on the form, and write Article 15 in the treaty box") excused the article; 3 of 4 such sentences were
missed, now 0 (`tests/test_round6_local.py`).
The recall set, both held-out sets and the 144 stored explanations of `eval-v2-r10`, `eval-ablation-r10` and `eval-fail-fx_quote-r9`
get the same verdicts before and after (`evidence/guardrail-probe-r6-…`, `guardrail-heldout-r3/r4-20261011T…`). It is still
rule-based, and a probe aimed at it will find more 

## Re-run and known gaps

(The same scripts re-run on `42cda1c`: the eval's U/P/K and the forced-failure 48/48 are unchanged; figures in the wording counted 270 and 282, since the model words the card differently each run: [`evidence/rerun-at-head-2026-10-11.md`](evidence/rerun-at-head-2026-10-11.md). Known gaps: a bare number with no currency or % sign that ends a sentence, such as "…is 4897.", is not extracted; the pool of sourced amounts has no currency, so "INR 2000" passes when the gross is USD 2,000; "Payoneer shows $4,900.00 after the withholding" passes, because it is literally the after-withholding figure; a refusal, a bound word or a describing word ("UNCLEAR", "blank") still excuses every claim in its own clause, and a clause ends only at ";", a dash, a contrast word or subordinator (but, while, since, because, karena…), or a comma, "and" or "so" before a subject or an amount ("I can't confirm Wise works, as nothing is withheld", "You will receive $4,900.00 (the fee is not stated)" and, on an India card, "Line 10 is UNCLEAR, so write Article 23 there" pass); and where the bound is the gross, only an arrival or receive phrase is checked, and "from <payer>" excuses it ("Your Payoneer account will show $7,000.00", "Expect $2,000.00 in your Payoneer account from Devpost" and "Expect $2,000.00." pass) — narrowing "from" blocked real honest model text ("moving 1,000 USDC from Superteam Earn to your Pintu account")), which is why the route, line 10 and every amount on the card are decided by code, not by the prose.
