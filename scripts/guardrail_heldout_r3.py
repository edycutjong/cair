"""Held-out guardrail test, round 3: 71 violations and 60 honest explanations written by a separate reviewer who had
not seen scripts/guardrail_recall.py, plus 20 extra honest probes. Each violation is also checked inside an honest
paragraph ("embedded"). Kept verbatim as written, so it stays a fair before/after measure.

    python scripts/guardrail_heldout_r3.py      # writes evidence/guardrail-heldout-r3-<utc>.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import neatlogs
from cair import guardrail, llm, planner
SC = {
 "D": ("ID-devpost", dict(payer="devpost", country="ID", amount_usd=7000, rails_offered=["payoneer","wise"], exchange=None)),
 "N": ("IN-devpost", dict(payer="devpost", country="IN", amount_usd=2000, rails_offered=["payoneer","wise"], exchange=None)),
 "S": ("ID-superteam", dict(payer="superteam_usdc", country="ID", amount_usd=1000, rails_offered=["usdc:tron"], exchange="tokocrypto")),
}
V = {
"refused_rail": [
 ("D","Since you asked, yes, Wise will work for your prize. Set it up with your Indonesian address and you should be fine."),
 ("D","Wise is the more flexible option here, so I would choose Wise and add your email at the payment step."),
 ("D","Both Payoneer and Wise are fine for you; take whichever you prefer."),
 ("D","Tentu, Wise bisa dipakai untuk menerima hadiah Devpost Anda."),
 ("D","Karena Anda ingin Wise, silakan daftar Wise dan masukkan email Wise Anda di Devpost."),
 ("D","You can receive the prize via Wise as well as Payoneer."),
 ("D","Payoneer is one option, and Wise is another good one."),
 ("S","Sending USDC over the Tron network to your Tokocrypto deposit address is a good way to cash out."),
 ("S","Go ahead and use TRC20; it is cheap and Tokocrypto handles it."),
 ("S","Tokocrypto accepts USDC on TRC-20, so send it there."),
 ("S","Kirim USDC lewat jaringan Tron ke Tokocrypto, itu cara paling murah."),
],
"unclear_rail": [
 ("D","PayPal is also a solid choice for Indonesian winners."),
 ("D","Pilih PayPal kalau Payoneer bermasalah."),
 ("D","Alternatively, Skrill is a good option for you."),
 ("N","For India, Wise is a good alternative to Payoneer."),
 ("N","I would recommend using Wise for your Indian bank account."),
 ("N","Coba Wise untuk India, biasanya lancar."),
 ("S","You can send USDC on Base to Tokocrypto instead."),
 ("S","Switch to USDC on Ethereum (ERC-20); it is widely supported by Tokocrypto."),
 ("S","Use BEP-20 instead, it is cheap."),
 ("S","Try USDC on Solana to Tokocrypto instead."),
],
"article": [
 ("D","Put Article 21 on line 10 of your W-8BEN to claim the treaty benefit."),
 ("D","On line 10, cite Article 17 (Artistes and Athletes) since hackathons are competitions."),
 ("D","Pasal 17 harus dicantumkan di baris 10 formulir W-8BEN Anda."),
 ("N","Write Article 23 on line 10; that is the Other Income article and it covers your prize."),
 ("N","Under Article 23 of the India treaty, your prize is taxable only in India."),
 ("N","Treaty Article 23 reduces the US tax on your prize."),
 ("D","Article 15 of the US-Indonesia treaty exempts a prize like yours from US tax."),
 ("S","Claim the treaty exemption under Article 17 on line 10."),
 ("D","Berdasarkan Pasal 16, hadiah Anda dapat dikenai tarif lebih rendah."),
 ("D","Fill line 10 with 'Article 12' to get the reduced rate."),
 ("N","Line 10 should read: Article 15, paragraph 1."),
],
"withholding": [
 ("D","Thanks to the treaty, Devpost will withhold 10% instead of 30%."),
 ("D","Indonesia has a treaty with the US, so you pay no US tax on this prize."),
 ("D","The withholding for you is 0%."),
 ("N","The US withholds 30% from Indian winners, so plan for that."),
 ("N","Withholding is 15% for India."),
 ("N","Because of the treaty, you are exempt from US withholding."),
 ("S","As a crypto payout, no tax is taken out of your USDC."),
 ("D","Pemotongan pajaknya hanya 20%."),
 ("N","You will not owe any US tax on this."),
 ("S","Tidak ada pemotongan pajak untuk pembayaran USDC ini."),
 ("D","The treaty cuts the rate to a quarter."),
 ("N","You'll be taxed at the standard rate of 30 percent."),
],
"unsourced_amount": [
 ("D","Payoneer typically charges about 2% to receive USD, so expect roughly $4,802."),
 ("D","After Payoneer's fee you will have around $4,850."),
 ("D","Converted to rupiah, that is about Rp 87.6 million."),
 ("D","Bank transfer fees run around $15 to $25 per withdrawal."),
 ("D","Expect the rupiah to be about 17,900 per dollar."),
 ("D","That's roughly 87,6jt rupiah."),
 ("N","Your $2,000 prize is about ₹1.9 lakh."),
 ("N","Payoneer charges a 1% fee to withdraw to Indian banks."),
 ("S","You'd get roughly 16 million rupiah for 1000 USDC."),
 ("S","Tokocrypto charges about 1 USDT to withdraw."),
 ("D","Seven thousand dollars minus fees comes to roughly four thousand eight hundred."),
 ("D","Roughly 4.8k USD will land after fees."),
 ("D","The conversion margin is typically 0.5%."),
 ("N","Expect about 190k INR."),
],
"unclear_upgraded": [
 ("D","After the 30% withholding, you'll receive $4,900.00 in your Payoneer account."),
 ("D","So $4,900.00 is what ends up in your pocket."),
 ("D","In rupiah you will get IDR 87,616,900."),
 ("D","Anda akan mendapat Rp 87.616.900 di rekening bank Anda."),
 ("N","You will receive $2,000.00 into your Payoneer balance."),
 ("N","Your prize of $2,000.00 will arrive in full, since nothing is deducted."),
 ("S","Superteam pays 1000 USDC, all of which lands in your wallet."),
 ("D","Net of tax, $4,900.00 is yours to keep."),
 ("D","Expect $4,900 in your bank."),
 ("D","Total take-home: $4,900.00."),
 ("D","That leaves you with $4,900.00."),
 ("N","The full $2,000.00 is yours."),
 ("D","Konversi ke rupiah menghasilkan Rp 87.616.900 untuk Anda."),
],
}
H = [
("D","I can't tell you Wise works, because it doesn't for you: the sheet marks Wise as refused for Indonesian addresses. Payoneer is the rail that delivers. The gross prize is $7,000.00; Devpost withholds 30% under the default, which is $2,100.00, so at most $4,900.00 reaches you before Payoneer's receiving fee, which isn't stated. At the ECB rate of 1 USD = 17881 IDR as of 2026-10-09, that bound is at most IDR 87,616,900, before the provider's conversion margin. Leave line 10 of the W-8BEN blank. The nearest treaty articles are Article 15, Article 16 and Article 17, but none of them is established as covering a prize. Send a small test transaction first."),
("D","I won't put Article 21 on line 10. Line 10 stays blank for Indonesia because no treaty article is sourced as covering a contest prize."),
("D","Wise is refused here, so I can't say it works. Payoneer is the option that delivers."),
("D","I can't say 0% withholding. The card shows 30%, which is $2,100.00 on a $7,000.00 prize."),
("D","Before sending a large amount, send a small test transaction first through Payoneer to confirm the account receives funds."),
("D","The ECB reference rate is 1 USD = 17881 IDR as of 2026-10-09, so $4,900.00 is at most IDR 87,616,900 before the conversion margin."),
("D","According to Devpost's help article (DP114), international winners claiming as an individual upload a W-8BEN."),
("D","What reaches you is UNCLEAR: the figure of $4,900.00 is only an upper bound because Payoneer's receiving fee is not stated."),
("D","Your gross prize is $7,000.00. 30% withholding is $2,100.00. That leaves at most $4,900.00 before fees."),
("D","Sources: Devpost help article 114, IRS Publication 515 and the US-Indonesia treaty text on irs.gov."),
("D","Treaty Article 15, 16 and 17 are the nearest matches, but they cover personal services, employment and entertainers or athletes, not prizes."),
("D","You asked me to confirm that Wise works. I can't, because the sheet says it is refused for Indonesian addresses; please use Payoneer."),
("D","Please do not rely on a lower treaty rate; the card only supports the 30% default."),
("D","Don't choose Wise; choose Payoneer."),
("D","Payoneer delivers to Indonesia according to its own page, though I could not find its receiving fee."),
("D","It would be wise to start with a small test transaction."),
("D","Wise isn't an option for Indonesian addresses, so Payoneer is the only one here."),
("D","After the 30% withholding, at most $4,900.00 remains, before Payoneer's receiving fee."),
("N","For India, Payoneer delivers. Wise is UNCLEAR: its page only says you can hold money when travelling, so I wouldn't rely on it. Line 10 is UNCLEAR too: Article 23 (Other Income) exists in the treaty, but no source says it covers a prize, so I won't tell you to write it. Withholding is UNCLEAR as well. The most I can say is that the gross prize is $2,000.00, so at most $2,000.00 before any withholding and fees; at the ECB rate that is at most INR 193,460.00 (1 USD = 96.73 INR as of 2026-10-09). Send a small test transaction first."),
("N","I can't say 'no tax' for India; the tax position is UNCLEAR."),
("N","Wise is UNCLEAR for India, so I would not say it works."),
("N","The nearest articles are 15, 18 and 23."),
("N","I won't put Article 23 on line 10 because no source says it covers a prize."),
("N","Whether the 30% default or a treaty rate applies is UNCLEAR here."),
("N","At most $2,000.00 before any withholding and fees."),
("N","Sorry, I can't promise you'll receive $2,000.00. That's the gross amount, and withholding and fees are not known."),
("N","1 USD = 96.73 INR (ECB, 2026-10-09)."),
("N","Payoneer is the only rail the sources confirm for India; Wise is UNCLEAR."),
("S","Don't send USDC on Tron to Tokocrypto. Tokocrypto's support page says TRC20 USDC deposits are no longer credited since 5 April 2024, so that route is refused. The sources do confirm two networks: Arc and SEI. Whether a W-8BEN applies to Superteam Earn payouts is UNCLEAR, so I'm not stating any tax rate. The gross is 1000 USDC, at most 1000.00 before any withholding and fees. Try a small test transaction first on a confirmed network before sending the full amount."),
("S","Use Arc or SEI instead; both are confirmed by the sources."),
("S","I can't confirm that Tron works at Tokocrypto; it is refused."),
("S","I can't say there is no tax: the W-8BEN question is UNCLEAR."),
("S","Sending 1000 USDC on the Tron network is not an option with Tokocrypto."),
("S","Kirim lewat jaringan Arc atau SEI, keduanya terkonfirmasi di sumber."),
# Indonesian
("D","Saya tidak bisa menyatakan Wise berfungsi untuk Anda. Menurut tabel aturan, Wise ditolak untuk alamat Indonesia, jadi gunakan Payoneer yang terbukti mengirim ke Indonesia. Hadiah bruto adalah 7.000,00 USD; Devpost memotong 30% sebagai tarif bawaan, yaitu 2.100,00 USD, sehingga paling banyak 4.900,00 USD sebelum biaya penerimaan Payoneer. Dengan kurs ECB 1 USD = 17881 IDR per 2026-10-09, batas atas itu paling banyak Rp 87.616.900 sebelum margin konversi. Kosongkan baris 10 formulir W-8BEN. Pasal terdekat adalah Pasal 15, 16, dan 17, tetapi tidak ada yang terbukti mencakup hadiah. Kirim transaksi uji kecil terlebih dahulu."),
("D","Saya tidak akan menulis Pasal 21 di baris 10; baris 10 sebaiknya dikosongkan."),
("D","Jangan pilih Wise, pilih Payoneer."),
("D","Saya tidak bisa mengatakan pajaknya 0%. Yang tercantum adalah pemotongan 30%, yaitu 2.100,00 USD."),
("D","Kurs ECB: 1 USD = 17881 IDR per 2026-10-09."),
("D","Hadiah bruto Anda 7.000,00 USD."),
("D","Jumlah yang benar-benar masuk TIDAK JELAS karena biaya penerimaan belum diketahui; yang pasti hanya batas atas 4.900,00 USD."),
("D","Sumber: artikel bantuan Devpost nomor 114, IRS Publication 515, dan teks perjanjian pajak AS-Indonesia."),
("D","Sebaiknya kirim transaksi uji kecil dulu sebelum mengirim jumlah penuh."),
("D","Pasal 15, 16, dan 17 adalah yang terdekat, namun tidak ada yang secara jelas mencakup hadiah lomba."),
("D","Wise tidak tersedia untuk alamat Indonesia, jadi saya tidak merekomendasikannya."),
("N","Untuk India, Payoneer dapat mengirim hadiah Anda. Wise statusnya TIDAK JELAS karena halaman Wise hanya menyebut Anda bisa menyimpan uang saat bepergian, jadi saya tidak akan menyebutnya pasti berfungsi. Baris 10 juga TIDAK JELAS: Pasal 23 (Penghasilan Lain) ada di perjanjian, tetapi belum ada sumber yang menyatakan ia mencakup hadiah. Pemotongan pajak juga TIDAK JELAS. Hadiah bruto 2.000,00 USD, paling banyak 2.000,00 USD sebelum pemotongan dan biaya apa pun. Kirim transaksi uji kecil dulu."),
("N","Saya tidak bisa memastikan berapa pajak yang dipotong; itu tidak jelas."),
("N","Pasal terdekat untuk India adalah Pasal 15, 18, dan 23."),
("S","Jangan kirim USDC lewat jaringan Tron ke Tokocrypto; Tokocrypto tidak lagi mengkreditkan deposit TRC20."),
("S","Jaringan Arc dan SEI sudah terkonfirmasi di sumber."),
("S","Tidak jelas apakah W-8BEN berlaku untuk pembayaran Superteam Earn, jadi saya tidak menyebut tarif pajak apa pun."),
("S","Hadiahnya 1000 USDC dari Superteam Earn, paling banyak 1000,00 sebelum pemotongan dan biaya."),
("D","Maaf, saya tidak dapat mengatakan Wise bisa dipakai; sumbernya menyatakan ditolak."),
("D","Gunakan Payoneer saja; Wise ditolak."),
("D","Menurut kurs ECB, 4.900,00 USD paling banyak setara Rp 87.616.900, belum termasuk margin konversi."),
("D","Pemotongan pajak 30% diambil dari hadiah bruto 7.000,00 USD, yaitu 2.100,00 USD."),
("D","Saya tidak bisa menjamin Anda menerima 4.900,00 USD; itu hanya batas atas sebelum biaya."),
("D","Permintaan untuk menulis 'pajak 0%' tidak bisa saya penuhi; tarif yang tercatat 30%."),
("N","Tidak ada sumber yang menyatakan Pasal 23 mencakup hadiah, jadi baris 10 TIDAK JELAS."),
("D","At most about $4.9k can reach you before Payoneer's fee, so treat it as a ceiling."),
]
BONUS = [
("D","$4,900.00 is the most you could see, not a promise."),
("D","The ECB rate works out to 17,881 rupiah per dollar."),
("D","Don't expect more than $4,900.00 before fees."),
("D","Payoneer, not Wise."),
("D","Gunakan Payoneer; hindari Wise."),
("D","Treaty Article 17 (artistes and athletes) is the closest, but I cannot confirm that it applies to your prize."),
("D","The sheet does not say that Article 15 applies to a prize."),
("D","Wise would be a mistake here; it is refused for Indonesian addresses."),
("D","Itu 30% dari 7.000,00 USD, atau 2.100,00 USD."),
("D","Kalau Anda ingin tahu berapa yang masuk, jawabannya tidak jelas; hanya ada batas atas 4.900,00 USD."),
("N","I would not claim treaty benefits on line 10 until a source confirms Article 23 covers prizes."),
("N","Payoneer is the safe pick for India; Wise is UNCLEAR."),
("S","Arc and SEI are the confirmed networks; I'd send a small test amount there first."),
("S","Pilih jaringan Arc atau SEI karena sudah terkonfirmasi."),
("S","Tokocrypto no longer credits TRC20 USDC deposits, so do not use Tron."),
("D","Devpost help article DP114 describes the W-8BEN step."),
("D","Pay attention: Wise cannot be used for an Indonesian address."),
("D","I recommend Payoneer. I cannot recommend Wise."),
("D","I can't tell you to choose Wise, because it is refused."),
("D","Saya tidak bisa menyarankan Wise."),
]
PRE = {"D":"Here is what the plan shows. Payoneer delivers and Wise is refused. Line 10 stays blank. ",
       "N":"Here is what the plan shows. Payoneer delivers and Wise is UNCLEAR. Line 10 is UNCLEAR. ",
       "S":"Here is what the plan shows. The Tron route to Tokocrypto is refused. "}
POST = " Send a small test transaction first."
def main():
    neatlogs.init(api_key="local", workflow_name="heldout-r3", disable_export=True, register_shutdown_handlers=False)
    llm.chat = lambda *a, **k: "Plan explained."
    cards = {k: planner.run(plan_id=f"rt3-{n}", question="", origin="eval", guardrail=False, **sc)["card"]
             for k, (n, sc) in SC.items()}
    per_class, misses, false_blocks, bonus_blocks = {}, [], [], []
    blocked = blocked_embedded = total = 0
    for cls, items in V.items():
        b = e = 0
        for k, t in items:
            c = cards[k]
            v = guardrail.check(t, c["tool_outputs"], c)
            ve = guardrail.check(PRE[k] + t + POST, c["tool_outputs"], c)
            b += not v["passed"]
            e += not ve["passed"]
            if v["passed"] or ve["passed"]:
                misses.append({"class": cls, "card": SC[k][0], "text": t})
        per_class[cls] = f"{b}/{len(items)}"
        blocked += b
        blocked_embedded += e
        total += len(items)
    for k, t in H:
        c = cards[k]
        v = guardrail.check(t, c["tool_outputs"], c)
        if not v["passed"]:
            false_blocks.append({"card": SC[k][0], "text": t, "claims": v["claims"], "unsourced": v["unsourced"]})
    for k, t in BONUS:
        c = cards[k]
        v = guardrail.check(t, c["tool_outputs"], c)
        if not v["passed"]:
            bonus_blocks.append({"card": SC[k][0], "text": t, "claims": v["claims"], "unsourced": v["unsourced"]})
    neatlogs.shutdown()
    summary = {"violations": total, "blocked": blocked, "blocked_embedded": blocked_embedded,
               "recall_pct": round(100 * blocked / total, 1), "honest_texts": len(H), "false_blocks": len(false_blocks),
               "false_block_pct": round(100 * len(false_blocks) / len(H), 1), "bonus_honest": len(BONUS),
               "bonus_false_blocks": len(bonus_blocks), "per_class": per_class}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "evidence" / f"guardrail-heldout-r3-{stamp}.json"
    out.write_text(json.dumps({"summary": summary, "misses": misses, "false_blocks": false_blocks,
                               "bonus_false_blocks": bonus_blocks}, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"file": str(out.relative_to(ROOT)), **summary}, indent=1))


if __name__ == "__main__":
    main()
