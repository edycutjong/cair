# Re-run of the published evidence on HEAD 42cda1c (2026-10-11 00:04 WIB)

The published eval numbers were produced at 0a8fc06; later commits changed the guardrail and claims sentence
splitting (0276ebb, 4a9493e). Everything below was re-run on 42cda1c with the real model (qwen3.8-max) and the real ECB feed.

| Run | File | U | P | K fields | Scenarios OK | Figures traced (N) |
|---|---|---|---|---|---|---|
| v2 on the 48-scenario frozen set | `eval-v2-p7-20261010T170416Z.json` | 0 | 0 | 143/143 | 48/48 | 270/270 |
| v2, `fx_quote` forced to fail | `eval-fail-fx_quote-p7-20261010T170507Z.json` | 0 | 0 | 143/143 | 48/48 | 282/282 |

U, P, K and the 48/48 recovery result are **unchanged**. The count of figures in the wording (N) moves between runs
because the model words the card differently each time (v2 runs r1-r10 range 255-359); the ratio stays 100%.
The published N values (359, 350) are the figures of the files they cite, not of this re-run.

Guardrail scripts on 42cda1c: scripted recall 53/53 violations blocked, 0/29 honest texts blocked
(`guardrail-recall-*`); the r4 set, no longer held-out since the guardrail was tuned on it, now blocks 66/66 with
0/66 false blocks (`guardrail-heldout-r4-*`). The README's 62/66 and 3/66 stay as the pre-fix, held-out numbers.
