# Hand re-check of three rules-sheet cells against the live pages — 2026-10-10 07:48 UTC

The eval measures fidelity to the rules sheet. These three cells were re-read by hand against the primary page on
the day the sheet was built, to check the sheet itself.

| Cell | Re-read on the live page | Matches the sheet |
|---|---|---|
| `ID,*,wise` deliverable = NO | Page title "Changes to the Multi-currency account for customers in Indonesia": "personal Wise account holders with an address in Indonesia can no longer hold money or currencies in their account" | yes |
| `*,devpost,_payer` w8ben_applies = YES | help.devpost.com article 114 ("Last updated on August 21, 2026"): "International winners who are claiming the prize as an individual: Upload a W-8BEN." and "If you choose Paypal, Payoneer, or Wise, fill out the email address associated with that payment method." | yes |
| `ID,*,_treaty` other income article = NONE | irs.gov/pub/irs-trty/indo.pdf (sha256 prefix 1b04dbbd28b5469a), text layer via `pdftotext -layout`: the Table of Articles lists 31 articles, none titled "Other Income"; the phrase "other income" occurs twice in the whole text and neither is an article heading | yes |
