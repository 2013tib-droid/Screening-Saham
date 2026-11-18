# Uji Ulang Filter Pasar untuk Daftar Swing

Dihitung 2026-11-18T14:14:17Z oleh `uji_ulang_pasar.py`. Sinyal swing 2024-04-01 – 2026-11-18 (625 hari bursa), 402 emiten ber-harga.

> ⚠️ **Bias survivorship.** Universe = daftar emiten hari ini. Angka absolutnya terlalu bagus; perbandingan antar-filter lebih bisa dipegang daripada angkanya sendiri.

## Portofolio 10 posisi, tahan 21 hari bursa

Median dari 20 urutan acak pengisian slot (rentang min–maks dalam kurung). `HariBoleh%` = porsi hari bursa yang filternya mengizinkan beli.

### Daftar swing

| Filter | HariBoleh% | MaxDD% | Total% | CAGR%Median | Keterisian% | TransaksiMedian |
|---|---|---|---|---|---|---|
| Tanpa filter | 100,0 | −52,9 (−61,4 … −46,2) | −8,4 (−45,0 … +56,4) | −3,25 | 94,8 | 290 |
| IHSG > MA50 | 49,0 | −23,4 (−29,7 … −14,9) | +111,3 (+63,0 … +184,3) | +32,72 | 63,4 | 189 |
| Sejak FTD | 20,8 | −33,5 (−39,4 … −27,2) | −25,1 (−31,6 … −14,1) | −10,38 | 30,6 | 98 |
| IHSG > MA50 & sejak FTD | 11,0 | −7,5 (−9,3 … −5,9) | +33,3 (+21,0 … +40,2) | +11,48 | 13,4 | 40 |
| Sejak FTD (tanpa batas hari ke-7) | 51,0 | −47,9 (−55,0 … −38,3) | −38,3 (−51,6 … −13,3) | −16,71 | 67,5 | 208 |
| IHSG > MA50 & sejak FTD (tanpa batas) | 35,8 | −24,9 (−29,3 … −21,1) | +35,3 (+10,5 … +52,0) | +12,13 | 47,0 | 140 |
| DD aktif < 5 | 60,8 | −45,1 (−57,0 … −33,6) | −30,4 (−48,5 … −7,2) | −12,84 | 74,8 | 223 |
| IHSG > MA50 & DD < 5 | 38,7 | −25,2 (−39,5 … −18,4) | +22,4 (−5,2 … +38,9) | +7,96 | 53,3 | 159 |
| Breadth > 50% | 53,4 | −41,2 (−52,8 … −33,3) | +22,4 (−10,1 … +62,8) | +7,95 | 66,4 | 198 |
| IHSG > MA50 & breadth > 50% | 48,0 | −18,9 (−24,1 … −12,2) | +107,2 (+54,5 … +213,8) | +31,73 | 56,7 | 169 |

### Saham likuid acak (pembanding)

| Filter | HariBoleh% | MaxDD% | Total% | CAGR%Median | Keterisian% | TransaksiMedian |
|---|---|---|---|---|---|---|
| Tanpa filter | 100,0 | −47,7 (−67,1 … −41,6) | −19,4 (−51,4 … +65,7) | −7,84 | 95,4 | 290 |
| IHSG > MA50 | 49,0 | −22,1 (−33,1 … −14,9) | +40,7 (−7,2 … +117,6) | +13,79 | 63,7 | 190 |
| Sejak FTD | 20,8 | −33,5 (−52,7 … −23,1) | −22,8 (−46,2 … +9,7) | −9,34 | 30,8 | 100 |
| IHSG > MA50 & sejak FTD | 11,0 | −9,0 (−13,5 … −5,8) | +6,5 (−2,5 … +25,4) | +2,43 | 13,4 | 40 |
| Sejak FTD (tanpa batas hari ke-7) | 51,0 | −40,3 (−57,2 … −25,2) | −30,7 (−50,3 … +49,6) | −12,96 | 67,7 | 210 |
| IHSG > MA50 & sejak FTD (tanpa batas) | 35,8 | −19,2 (−28,8 … −13,7) | +44,8 (−16,3 … +126,6) | +15,04 | 47,0 | 140 |
| DD aktif < 5 | 60,8 | −38,6 (−50,1 … −29,2) | −6,4 (−37,3 … +90,2) | −2,50 | 77,2 | 230 |
| IHSG > MA50 & DD < 5 | 38,7 | −19,7 (−32,6 … −13,9) | +47,9 (−16,4 … +143,8) | +15,97 | 53,7 | 160 |
| Breadth > 50% | 53,4 | −53,0 (−64,5 … −40,6) | +1,9 (−38,9 … +89,3) | +0,73 | 67,1 | 200 |
| IHSG > MA50 & breadth > 50% | 48,0 | −20,5 (−29,8 … −15,9) | +62,5 (−4,6 … +139,6) | +20,16 | 57,0 | 170 |

IHSG beli-dan-tahan: total −28,0%, drawdown terdalam −46,3% (2026-01-20 → 2026-11-03).

## Per sinyal: selisih vs saham likuid acak, hari bursa ke-21

| Filter | Posisi | TanggalBeli | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MedianSelisih% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Tanpa filter | 1.839 | 535 | −0,80 | −0,27 | −0,53 | ±0,55 | −2,91 | 38,9 |
| IHSG > MA50 | 1.186 | 286 | +2,28 | +2,43 | −0,15 | ±0,68 | −3,44 | 36,9 |
| Sejak FTD | 368 | 101 | −2,67 | −3,39 | +0,71 | ±1,42 | −0,81 | 46,2 |
| IHSG > MA50 & sejak FTD | 175 | 56 | +2,02 | −0,42 | +2,44 | ±1,95 | −0,06 | 49,7 |
| Sejak FTD (tanpa batas hari ke-7) | 1.222 | 283 | −1,36 | −0,59 | −0,77 | ±0,72 | −3,38 | 37,2 |
| IHSG > MA50 & sejak FTD (tanpa batas) | 886 | 205 | +1,66 | +2,08 | −0,42 | ±0,87 | −4,11 | 35,8 |
| DD aktif < 5 | 1.369 | 335 | +0,18 | +0,43 | −0,25 | ±0,70 | −3,16 | 38,1 |
| IHSG > MA50 & DD < 5 | 950 | 224 | +2,82 | +2,92 | −0,10 | ±0,85 | −3,41 | 36,8 |
| Breadth > 50% | 1.301 | 311 | +0,40 | +0,91 | −0,51 | ±0,76 | −3,64 | 36,8 |
| IHSG > MA50 & breadth > 50% | 1.130 | 280 | +2,67 | +2,75 | −0,08 | ±0,70 | −3,50 | 37,1 |

## Keadaan pasar di periode uji

- Follow-through day: 6 kali (2024-06-28, 2024-11-25, 2025-02-17, 2026-04-01, 2026-06-12, 2026-11-12).
- Follow-through day tanpa batas hari ke-7: 11 kali (2024-05-15, 2024-06-28, 2024-11-25, 2025-01-15, 2025-02-17, 2025-04-22, 2025-08-12, 2026-02-11, 2026-04-01, 2026-06-12, 2026-11-12); hari berkeadaan NAIK 51,0%.
- Hari bursa berkeadaan NAIK (sejak FTD): 20,8%; DD aktif ≥ 5: 39,2% hari; distribution day: 117.
- IHSG > MA50: 49,0% hari; breadth > 50%: 53,4% hari.

Breadth hitungan ulang vs `hasil/breadth.csv` (425 tanggal, 2025-02-05 – 2026-11-17): rata-rata selisih 0,04 poin, maks 2,8; sisi terhadap 50% sama di 100,0% tanggal.

