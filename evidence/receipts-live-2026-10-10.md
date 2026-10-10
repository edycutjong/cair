# Receipts on the live app — read-only query, 2026-10-10 ~15:10 UTC

Source: `/var/lib/cair/cair.db` on the app host (`receipts` joined to `plans`), opened read-only. Amounts omitted; ids
truncated. This is why `/verify` shows "receipts checked: 2".

| receipt | plan | plan origin | landed_on | mode | verdict | label | created_at (UTC) |
|---|---|---|---|---|---|---|---|
| 01M4JBNTK5G7… | 01M4JBN4WJ5X… | builder | 2026-09-23 | partial | within sourced bound | REPLAY — known outcome | 2026-10-10T07:33:11Z |
| 01M4JCA44V1E… | 01M4JC7CC4HG… | builder | 2026-10-11 | partial | within sourced bound | (none) | 2026-10-10T07:44:17Z |

- Row 1 is the Tarmac replay (the builder's own Devpost prize, a known outcome): EVALUATOR trace
  `f5a47b9cba7cf056a800e136616e0013`, `evidence/traces/tarmac-replay-evaluator.json`.
- Row 2 is a QA test receipt entered by the builder while testing the reconciler; its future `landed_on` date predates
  the validation that now rejects future dates.
- All 22 plans on the live database at query time had origin `builder`; forward receipts from real users: n = 0.
