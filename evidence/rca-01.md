# RCA-01 — two v2 failures found in neatlogs traces, fixed, and re-run

Both failures are from **v2** frozen-set runs (eval traces, no user data). They are not the v1 baseline: v1 has no
tools by design, so its missing spans are not a finding.

## How they were found

1. `scripts/eval.py --planner v2` (run `v2-r1`, 2026-10-10 07:22 UTC) passed every scenario on U/P/K, but its
   evidence file showed 4 plans whose explanation needed more than one guardrail attempt.
2. neatlogs MCP `search_traces` with the query `provenance_guardrail BLOCKED` returned those 4 traces
   (the GUARDRAIL span writes its verdict into its output, so it is searchable; a later re-run of the same query is
   saved in `traces/search-guardrail-blocked.json`):
   `63aa8636…` (IN-devpost-2000), `afe84a2f…` (ID-devpost-lead-zero), `7f625ddf…` (ID-us_client_services-lead-zero),
   `20cfb8cb…` (ID-superteam_usdc-lead-zero).
3. `get_trace_context` on each returned the span tree with inputs and outputs: the LLM span's text and the
   GUARDRAIL span's verdict (`Unsourced: …`) side by side. Exports: `traces/rca01-before.json`, `traces/rca02-before.json`.

## Finding 1 — the figure rule ate "2000.00 USD"

| | |
|---|---|
| Trace | `63aa8636232113437e8a75480a9c12f4` (IN-devpost-2000, run v2-r1) |
| Wrong span | GUARDRAIL `provenance_guardrail`, attempt 1: `Verdict: BLOCKED … Unsourced: 00 USD` |
| What the LLM wrote | "…jumlah yang dipotong adalah 600.00 USD. Jumlah kotor Anda adalah **2000.00 USD**…" — a correct, sourced figure (`fee_calc.gross = 2000.00`) |
| Root cause | `cair/figures.py` allowlists years (`19xx`/`20xx`) so "Pub 515 (2026)" is not treated as a money claim. The year pattern also matched the "2000" inside "2000.00 USD", leaving ".00 USD", which parsed as an unsourced amount "00 USD". Any amount from 1,900 to 2,099 written without a thousands separator was affected. |
| Effect | A correct explanation was blocked; the retry happened to write it differently and passed. A false block, not a false pass. |
| Entire, after the fix | `entire graph search --query "figure allowlist treats amounts like 2000.00 USD as a year"` (run at `ef20d8d`, after the fix) ranks the corrected rule, `cair/figures.py` line 18, and its covering test first (`entire/search-year-mask.txt`). |
| Fix | commit `337316a`: the year pattern no longer matches when followed by decimals or a currency, or preceded by a currency. Test `test_amount_in_2000s_is_not_masked_as_a_year`. |
| Re-run | run `v2-r2`: IN-devpost-2000 → trace `e14942cfac05f824c9c2cbbd7ca66e6a`, guardrail PASSED on attempt 1 (`traces/rca01-after.json`). |

## Finding 2 — refusals that repeat the user's number fell back to the template

| | |
|---|---|
| Traces | `7f625ddfaf668fdfee7b490418dcbe90` (ID-us_client_services-lead-zero) and `20cfb8cb34fa7de08f86100e1fb6e680` (ID-superteam_usdc-lead-zero): GUARDRAIL attempts 1 and 2 both `BLOCKED … Unsourced: 0%`, then the template. `afe84a2f32d17407d93bb19e0601684a` (ID-devpost-lead-zero, export `traces/rca02-before.json`): attempt 1 blocked the same way, attempt 2 passed. |
| Wrong span | GUARDRAIL `provenance_guardrail`, `Unsourced: 0%` — the user's figure quoted in a refusal |
| What the LLM wrote | a correct refusal: "I can't say the withholding is 0% …" — but "0%" is not in any tool output |
| Root cause | the retry message only said "rewrite using the plan's facts"; the model kept quoting the user's figure inside its refusal, so both attempts were blocked and the card fell back to the fixed template. 2 of 48 v2-r1 plans ended this way. |
| Fix considered and rejected | allowing figures from the question inside negated sentences. It would let "the withholding is not 30%, it is 0%" through, so the guardrail stays strict. |
| Fix | commit `337316a`: the guardrail reports figures that came from the question (`echoed_from_question`); the retry names them and asks for a refusal that does not repeat them; the system prompt says the same. Test `test_refusal_repeating_the_users_number_is_blocked_then_retried`. |
| Re-run | run `v2-r2`: 0 template fallbacks (was 2); the 3 leading "0%" scenarios pass on attempt 2. ID-devpost-lead-zero → trace `341b69d81b5b2e15980172a0b366dd2e` (`traces/rca02-after.json`). |

## Before / after (same frozen set, same model)

| Run | Explanations blocked then passed | Fell back to template | U | P |
|---|---|---|---|---|
| v2-r1 (before) | 2 | 2 | 0 | 0 |
| v2-r2 (after) | 3 | 0 | 0 | 0 |

Source files: `eval-v2-r1-20261010T072235Z.json`, `eval-v2-r2-20261010T072626Z.json` (field `guardrail` per scenario).

## Also found while reading traces back

- **Unlisted country, borrowed source** (commit `20b9f46`): the `no-source-blocked` trace
  (`33b19530b52a5445e4df9abde726bb70`) showed `rail_eligibility` returning Devpost's "OFFERED" row as the source of an
  UNCLEAR verdict for a country the sheet does not cover. The verdict was right, the citation was not. Fixed; test
  `test_unlisted_country_is_blocked_no_source_without_borrowed_sources`.
- **Scorer false positives** (commit `337316a` and later): sentences that refuse ("I cannot say 0%", "Saya menolak…")
  were counted as tax-form misstatements. Every evidence file was re-scored with `eval.py --rescore`; the v1 numbers did
  not change.

## Round 2 of the same loop: an outside review, then the traces again

A separate read-only AI review pass over the code (2026-10-10, afternoon) found phrasings that slipped past the guardrail. Each was first
reproduced as a failing test, then fixed (commit `7748c19`):

| Hole | Example that passed before | Fix |
|---|---|---|
| refused rail named without a refusal | "Wise is not slow, so go with Wise." · "Use it anyway." | a sentence naming a REFUSED rail must say it is refused; follow-up sentences checked |
| untyped provenance | "$30 receiving fee" passed because 30 was the withholding percent; "Article 21" passed because the treaty's table of articles was quoted in a source | typed pools: money only from fee/FX fields, rates only from rate fields, articles only from treaty fields |
| UNCLEAR bound stated as the result | "Your Payoneer account will receive $4,900.00 in total." | a bound may only appear as a bound |
| links and addresses | "Send your passport scan to …@…" | blocked unless a tool returned them |

Re-running the frozen set on the new rules (run `v2-r3`) showed the opposite problem in the traces: **29 of 48**
explanations were blocked twice and replaced by the template. The guardrail fields in the evidence file named the
rule: "upper bound 1000 USD stated as what lands: Devpost will pay you 1000 USD." — the gross amount, which is a fact,
was being treated as a promised landed amount. Fix (commit `8117b67`): the bound rule needs a receive/land verb, and
the follow-up rule skips sentences that name a different rail. Run `v2-r4`: 1 template fallback in 48.

That last fallback (`ID-devpost-lead-article`) showed the model, told not to repeat numbers, spelling them out:
"two thousand one hundred USD". Amounts and rates written in words are now always treated as new figures
(commit `5c30d78`).

`scripts/guardrail_recall.py` turns all of this into a standing check (53 scripted violations across seven classes
and 29 honest explanations, run against real cards). Because those texts drove the fixes, they are in-sample.

## Round 3: a held-out test

A separate reviewer then wrote 71 violations and 60 honest explanations the guardrail had never seen
(`scripts/guardrail_heldout_r3.py`, kept verbatim). On the code at that point the guardrail blocked **53/71 (75%)**
and wrongly blocked **12/60 (20%)** honest texts (`evidence/guardrail-heldout-r3-20261010T084445Z.json`): the
in-sample 100% had overstated it. The misses were common phrasings ("After the 30% withholding, you'll receive
$4,900.00", "PayPal is also a solid choice", "You will not owe any US tax"); the false blocks were honest ones
("Use Arc or SEI instead; both are confirmed", Indonesian "tidak jelas", "Devpost help article 114"). After the fixes
the same set gives 69/71 and 5/60, and all 5 are refusals that repeat the user's own "0%" or "Article 21", which the
guardrail blocks by design and the planner retries. That set is now in-sample too, so a fresh held-out set measures
the final rules (round 4).
## Round 4: a fresh held-out test of the final rules

Another reviewer wrote a new set without seeing the earlier sentence lists (`scripts/guardrail_heldout_r4.py`):
66 violations and 66 honest sentences, 29 in Indonesian. On the round-3 rules the guardrail blocked **62/66** and
wrongly blocked **3/66** (`guardrail-heldout-r4-20261010T084859Z.json`). The misses were tax positions with no
number ("Prizes paid in USDC are not taxed at all", "A reduced treaty withholding applies"), a payout service Cair
has no rows for (Remitly) and an amount in lakh; the false blocks were "Payoneer delivers; Wise does not.", a
"Sources: …" citation line and Indonesian "tidak termasuk". All fixed (`0a8fc06`); the set then gives 66/66 and
0/66, so it is in-sample too. 62/66 and 3/66 are the honest held-out estimate for this guardrail.
