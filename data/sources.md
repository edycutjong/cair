# Sources for `rules_sheet.csv`

Every non-blank fact cell in `rules_sheet.csv` names a `source_id` below. Quotes are verbatim from the page or the
official PDF text layer, read on **2026-10-10**; Indonesian quotes stay in Indonesian with a gloss in [brackets].
A cell with no primary source is `UNCLEAR`, and `UNCLEAR` is a valid answer. Blog posts, forums and chatbot answers
never fill a cell. This is open data: corrections with a primary source are welcome.

<!-- Each entry: ### <id> · <url> · then the quote(s) and the cell(s) they support. The app parses this file. -->

### DP114
URL: https://help.devpost.com/article/114-how-to-claim-your-hackathon-cash-prize-winners-only
> Upload the relevant Tax Form. The options include: US residents: Upload a W-9. International winners who are claiming the prize as an individual: Upload a W-8BEN. International winners who are claiming the prize on behalf of an organization: Upload a W-8BEN-E.
> If you choose Paypal, Payoneer, or Wise, fill out the email address associated with that payment method.
> If your prize is undeliverable, you may incur fees that will be deducted from your prize, or be delaying or forfeiting receipt of the prize.

Supports: Devpost `_payer` w8ben_applies = YES (individual international winners); Devpost offers PayPal, Payoneer and Wise.
Also on the page: "Select a Payment Method. Note that payment method options vary based on the country of residence of the winner." — which rails appear for a given country is not listed publicly, so Cair asks which ones your form shows.

### DORA
URL: https://dorahacks.io/blog/news/prize-distribution/
> allowing you to manage hackathon prize funds and distribute prizes to winners directly from your Organizer Dashboard, while all payout services and compliance procedures are handled by Merit Systems.

Supports: DoraHacks `_payer` w8ben_applies = UNCLEAR (no public page names a tax form for winners or says none is needed). The post's "USDC (Base)" is the organizer's deposit rail, not the winner's payout network, which each event sets.

### SUPERTEAM
URL: https://docs.superteam.fun/the-superteam-handbook/community/faqs/superteam-earn-faq
> Note that the winner needs to complete KYC to receive money for Superteam / Solana-sponsored listings.
> Occasionally, some sponsors might ask for invoices, KYC, etc. as per their respective payment processes.

Supports: Superteam `_payer` w8ben_applies = UNCLEAR (KYC is stated; a US tax form is neither required nor ruled out).

### IRS-P515-SVC
URL: https://www.irs.gov/publications/p515
> If the income is for personal services performed in the United States, it is from U.S. sources. The place where the services are performed determines the source of the income, regardless of where the contract was made, the place of payment, or the residence of the payer.

Supports: `us_client_services` `_payer` w8ben_applies = UNCLEAR — services performed outside the US are not US-source, but no IRS page checked says whether a US client still asks a non-US contractor for a W-8BEN.

### IRS-P515-30
URL: https://www.irs.gov/publications/p515
> In most cases, a foreign person is subject to U.S. tax on its U.S. source income. Most types of U.S. source income received by a foreign person are subject to U.S. tax of 30%. A reduced rate, including exemption, may apply if there is a tax treaty between the foreign person's country of residence and the United States.
> Other grants, prizes, and awards made by grantors that reside in the United States are treated as income from sources within the United States.

Supports: `_treaty` withholding_default = 30% for ID, IN and PH (no treaty article reduces the rate on a prize).

### IRS-AZ-NOTREATY
URL: https://www.irs.gov/businesses/international-businesses/united-states-income-tax-treaties-a-to-z
> If the treaty does not cover a particular kind of income, or if there is no treaty between your country and the United States, you must pay tax on the income in the same way and at the same rates shown in the instructions for the applicable U.S. tax return.

Supports: withholding_default = 30% for VN and NG (with IRS-P515-30).

### IRS-AZ-VN
URL: https://www.irs.gov/businesses/international-businesses/united-states-income-tax-treaties-a-to-z
> (absence) Vietnam is not on the IRS "United States Income Tax Treaties - A to Z" list (page last reviewed 03-Jan-2026). Treasury lists a 2015 signed agreement only.

Supports: VN treaty_other_income_article = NONE, phrased on the card as "not on the IRS list of US income tax treaties".

### IRS-AZ-NG
URL: https://www.irs.gov/businesses/international-businesses/united-states-income-tax-treaties-a-to-z
> (absence) Nigeria is not on the IRS "United States Income Tax Treaties - A to Z" list (page last reviewed 03-Jan-2026).

Supports: NG treaty_other_income_article = NONE, phrased as "not on the IRS list of US income tax treaties".

### IRS-W8BEN
URL: https://www.irs.gov/instructions/iw8ben
> Line 10 must be used only if you are claiming treaty benefits that require that you meet conditions not covered by the representations you make on line 9 and Part III.

Supports: the card's line-10 wording (blank unless a sourced article covers the income).

### TRTY-ID
URL: https://www.irs.gov/pub/irs-trty/indo.pdf
> Article 20 — Teachers and Researchers / Article 21 — Private Pensions and Annuities / Article 22 — Social Security Payments / Article 23 — Relief from Double Taxation … Article 30 — Entry into Force / Article 31 — Termination

Supports: ID treaty_other_income_article = NONE. The US–Indonesia convention has 31 articles and none is titled "Other Income"; the full list is in `treaties/id.json`.

### TRTY-IN
URL: https://www.irs.gov/pub/irs-trty/india.pdf
> ARTICLE 23 Other Income 1. Subject to the provisions of paragraph 2, items of income of a resident of a Contracting state, wherever arising, which are not expressly dealt with in the foregoing Articles of this Convention shall be taxable only in that Contracting state.
> 3. Notwithstanding the provisions of paragraphs 1 and 2, items of income of a resident of a Contracting state not dealt with in the foregoing articles of this Convention and arising in the other Contracting state may also be taxed in that other State

Supports: IN treaty_other_income_article = UNCLEAR. An Other Income article exists, but no source says it covers a contest prize, and paragraph 3 keeps the US's right to tax.

### TRTY-PH
URL: https://www.irs.gov/pub/irs-trty/philip.pdf
> Article 18 Private Pensions and Annuities / Article 19 Social Security Payments / Article 20 Governmental Functions / Article 21 Teachers / Article 22 Students and Trainees / Article 23 Relief from Double Taxation / … Article 29 Entry into Force / Article 30 Termination

Supports: PH treaty_other_income_article = NONE (30 articles, none titled "Other Income"; full list in `treaties/ph.json`).

### PAYO-ID
URL: https://www.payoneer.com/id/
> Setelah menerima pembayaran, Anda dapat menarik dana tersebut ke rekening bank lokal milik Anda. [After receiving a payment, you can withdraw it to your own local bank account.]

Supports: ID payoneer deliverable = YES.

### PAYO-IN
URL: https://www.payoneer.com/en-in/
> Get paid like a local with virtual accounts in world's major currencies, including USD, EUR, and GBP – easy, fast, and friction-free.

Supports: IN payoneer deliverable = YES.

### PAYO-PH
URL: https://www.payoneer.com/pricing/
> Sandra has a big customer in the United States who pays her Payoneer account in US Dollars. Once a month, Sandra withdraws her US Dollar earnings from her Payoneer account to her local Philippine Pesos bank account in the Philippines.

(That example is on https://www.payoneer.com/resources/how-to-use-payoneer/how-payoneer-calculates-withdrawal-fees/; the pricing page row "To a bank account in the same country as yours, in local currency (in supported countries)" lists the Philippines.)
Supports: PH payoneer deliverable = YES.

### PAYO-PRICING
URL: https://www.payoneer.com/pricing/
> From marketplaces and integrated platforms — Varies by marketplace
> To a bank account in the recipient's non-local currency (with currency conversion) E.g., USA to UK, USD to EUR 1.2% – 4%

Supports: payoneer receiving_fee_usd = UNCLEAR (no flat fee is stated for platform payouts) and fx_margin_pct = UNCLEAR (a 1.2%–4% range, not one number).

### WISE-ID
URL: https://wise.com/help/articles/7GuCMPA7SYaX3NFgM3uxgp/changes-to-the-multi-currency-account-for-customers-in-indonesia
> Due to local financial regulations in Indonesia, personal Wise account holders with an address in Indonesia can no longer hold money or currencies in their account.

Supports: ID wise deliverable = NO. The page says "can no longer hold money", and a USD prize paid to Wise has to land in a held USD balance.

### WISE-IN
URL: https://wise.com/help/articles/2813542/where-do-i-need-to-live-to-hold-money-with-wise
> India — You can hold money in your account when travelling overseas.

Supports: IN wise deliverable = UNCLEAR (no page says a personal India account can receive a USD prize).

### WISE-PH
URL: https://wise.com/help/articles/2813542/where-do-i-need-to-live-to-hold-money-with-wise
> You can hold money in your account if you live in one of the following countries and territories:

The table lists the Philippines with no restriction, and the Philippines is not on Wise's "You can't get USD account details if your address is in:" list (https://wise.com/help/articles/2810318/can-i-get-usd-account-details).
Supports: PH wise deliverable = YES.

### WISE-USD-NG
URL: https://wise.com/help/articles/2810318/can-i-get-usd-account-details
> You can't get USD account details if your address is in: … Nevada, Nigeria, North Korea …

Supports: NG wise deliverable = UNCLEAR. USD account details are ruled out; whether a payer can still reach a Nigerian Wise account another way is not stated.

### IDX-SOL
URL: https://blog.indodax.com/penambahan-jaringan-solana-untuk-koin-usdc/ (announcement dated 8 Oct 2024)
> Saat ini, USDC yang tersedia di INDODAX dapat didepositkan dan ditarik melalui jaringan ERC20, BEP20, Polygon, dan Base. [USDC on INDODAX can currently be deposited and withdrawn via ERC20, BEP20, Polygon and Base.]
> Namun, mulai Rabu, 9 Oktober 2024, pukul 14.00 WIB, kami akan menambahkan jaringan Solana sebagai opsi baru untuk transaksi USDC. [From Wednesday 9 October 2024, 14:00 WIB, we will add the Solana network as a new option for USDC transactions.]

Supports: Indodax USDC deposit = YES on Ethereum (ERC20), BSC (BEP20), Polygon, Base and Solana.

### PINTU-2024
URL: https://pintu.co.id/blog/pengumuman-usdc-dan-cara-swap (updated 1 Mar 2024)
> Pintu Exchange tidak mendukung USDC.e dan hanya mendukung USDC di Jaringan Ethereum, BNB chain, Arbitrum, Polygon, Optimism, dan Avalanche. [Pintu does not support USDC.e and supports USDC only on Ethereum, BNB chain, Arbitrum, Polygon, Optimism and Avalanche.]

Supports: Pintu USDC = YES on those six networks.

### PINTU-2022
URL: https://pintu.co.id/blog/daftar-integrasi-jaringan-blockchain-terbaru-pintu (22 Jun 2022)
> Aset USDT dan USDC, bisa kirim/terima melalui jaringan: Polygon / Solana / BNB Smart Chain (BEP-20) / AVAX – C Chain

Supports: Pintu USDC on Solana = UNCLEAR — this 2022 page lists Solana, the 2024 page's "only" list does not.

### TOKO-ARC
URL: https://support.tokocrypto.com/hc/id/articles/48934462996877-Tokocrypto-Tambahkan-Dukungan-Arc-untuk-Deposit-dan-Penarikan-USDC (16 Sep 2026)
> Tokocrypto kini menghadirkan dukungan jaringan Arc untuk layanan deposit dan penarikan USD Coin (USDC)… [Tokocrypto now supports the Arc network for USDC deposits and withdrawals]

Supports: Tokocrypto USDC on Arc = YES.

### TOKO-SEI
URL: https://support.tokocrypto.com/hc/id/articles/41312010494861-Deposit-dan-Penarikan-USDC-di-Jaringan-SEI-Kini-Tersedia-di-Tokocrypto (21 Nov 2025)
> Deposit dan Penarikan USDC di Jaringan SEI Kini Tersedia di Tokocrypto [USDC deposits and withdrawals on the SEI network are now available at Tokocrypto]

Supports: Tokocrypto USDC on SEI (SEIEVM) = YES.

### TOKO-TRC20
URL: https://support.tokocrypto.com/hc/id/articles/25605850992141-Tokocrypto-Akan-Menghentikan-Dukungan-untuk-Deposit-dan-Penarikan-USDC-melalui-Jaringan-Tron-TRC20 (4 Apr 2024)
> Deposit token USDC melalui TRC20 tidak akan lagi dikreditkan ke akun pengguna setelah 05 April 2024 09:00 WIB. [USDC deposits via TRC20 will no longer be credited to user accounts after 5 April 2024 09:00 WIB.]

Supports: Tokocrypto USDC on Tron = NO.

### TOKO-POLY
URL: https://support.tokocrypto.com/hc/id/articles/20624850372109-Tokocrypto-Akan-Mendukung-Native-USD-Coin-USDC-di-Jaringan-Polygon (23 Oct 2023)
> Deposit dan penarikan akan segera dibuka, dan akan diumumkan secara terpisah. [Deposits and withdrawals will open soon and will be announced separately.]

Supports: Tokocrypto USDC on Polygon = UNCLEAR (the follow-up announcement was not found).

### TOKO-SOL
URL: https://support.tokocrypto.com/hc/id/articles/40202649641869-Pemeliharaan-Dompet-untuk-Penarikan-USDC-di-Jaringan-Tertentu-pada-10-Oktober-2025 (9 Oct 2025)
> Tokocrypto akan melakukan pemeliharaan dompet untuk penarikan USD Coin (USDC) melalui jaringan World Chain (WLD), Celo (CELO), dan Solana (SOL)… [wallet maintenance for USDC withdrawals via World Chain, Celo and Solana]

Supports: Tokocrypto USDC deposit on Solana = UNCLEAR (a withdrawal notice says nothing about deposits).

### FX-ECB
URL: https://api.frankfurter.dev/v2/providers/ecb
> "key":"ECB","name":"European Central Bank","rate_type":"reference rate","pivot_currency":"EUR","publish_cadence":"daily"

Supports: `fx_quote` uses the ECB daily reference rate only (no weekend rates, so the card always shows the `as_of` date). ECB publishes IDR, INR and PHP; it does not publish VND or NGN, so those amounts are UNCLEAR.
