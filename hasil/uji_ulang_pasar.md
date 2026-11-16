# Uji Ulang Filter Pasar untuk Daftar Swing

Dihitung 2026-11-16T22:19:42Z oleh `uji_ulang_pasar.py`. Sinyal swing 2024-04-01 – 2026-11-16 (623 hari bursa), 402 emiten ber-harga.

> ⚠️ **Bias survivorship.** Universe = daftar emiten hari ini. Angka absolutnya terlalu bagus; perbandingan antar-filter lebih bisa dipegang daripada angkanya sendiri.

## Portofolio 10 posisi, tahan 21 hari bursa

Median dari 20 urutan acak pengisian slot (rentang min–maks dalam kurung). `HariBoleh%` = porsi hari bursa yang filternya mengizinkan beli.

### Daftar swing

| Filter | HariBoleh% | MaxDD% | Total% | CAGR%Median | Keterisian% | TransaksiMedian |
|---|---|---|---|---|---|---|
| Tanpa filter | 100,0 | −52,5 (−61,4 … −43,6) | −2,2 (−42,2 … +52,7) | −0,85 | 94,8 | 288 |
| IHSG > MA50 | 49,1 | −23,4 (−29,7 … −14,9) | +111,3 (+63,0 … +184,3) | +32,92 | 63,7 | 189 |
| Sejak FTD | 20,5 | −33,5 (−39,4 … −27,2) | −24,5 (−31,0 … −13,4) | −10,14 | 30,4 | 94 |
| IHSG > MA50 & sejak FTD | 11,1 | −7,5 (−9,3 … −5,9) | +33,3 (+21,0 … +40,2) | +11,54 | 13,5 | 40 |
| DD aktif < 5 | 61,0 | −45,5 (−57,0 … −33,6) | −32,6 (−51,3 … +2,3) | −13,93 | 75,2 | 223 |
| IHSG > MA50 & DD < 5 | 38,8 | −25,2 (−39,5 … −18,4) | +22,4 (−5,2 … +38,9) | +8,00 | 53,6 | 159 |
| Breadth > 50% | 53,6 | −41,2 (−52,8 … −33,3) | +22,4 (−10,1 … +62,8) | +7,99 | 66,7 | 198 |
| IHSG > MA50 & breadth > 50% | 48,2 | −18,9 (−24,1 … −12,2) | +107,2 (+54,5 … +213,8) | +31,93 | 57,0 | 169 |

### Saham likuid acak (pembanding)

| Filter | HariBoleh% | MaxDD% | Total% | CAGR%Median | Keterisian% | TransaksiMedian |
|---|---|---|---|---|---|---|
| Tanpa filter | 100,0 | −49,0 (−61,1 … −43,1) | −10,5 (−51,2 … +94,7) | −4,15 | 95,3 | 290 |
| IHSG > MA50 | 49,1 | −21,8 (−33,1 … −14,9) | +41,3 (−10,8 … +122,2) | +14,04 | 64,0 | 190 |
| Sejak FTD | 20,5 | −32,8 (−42,4 … −21,9) | −21,8 (−37,5 … +22,6) | −8,95 | 30,5 | 100 |
| IHSG > MA50 & sejak FTD | 11,1 | −8,5 (−13,0 … −5,6) | +5,6 (−9,3 … +28,1) | +2,10 | 13,5 | 40 |
| DD aktif < 5 | 61,0 | −39,6 (−52,2 … −30,6) | −7,7 (−40,3 … +61,8) | −3,00 | 77,5 | 230 |
| IHSG > MA50 & DD < 5 | 38,8 | −21,1 (−32,0 … −13,9) | +45,5 (−19,9 … +143,9) | +15,35 | 53,9 | 160 |
| Breadth > 50% | 53,6 | −52,0 (−65,3 … −42,8) | −4,8 (−40,9 … +74,4) | −1,84 | 67,4 | 200 |
| IHSG > MA50 & breadth > 50% | 48,2 | −20,5 (−29,8 … −15,9) | +57,2 (+5,8 … +119,7) | +18,77 | 57,3 | 170 |

IHSG beli-dan-tahan: total −26,7%, drawdown terdalam −46,3% (2026-01-20 → 2026-11-03).

## Per sinyal: selisih vs saham likuid acak, hari bursa ke-21

| Filter | Posisi | TanggalBeli | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MedianSelisih% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Tanpa filter | 1.831 | 533 | −0,82 | −0,26 | −0,54 | ±0,55 | −2,93 | 38,8 |
| IHSG > MA50 | 1.184 | 286 | +2,30 | +2,44 | −0,15 | ±0,68 | −3,46 | 36,9 |
| Sejak FTD | 368 | 101 | −2,67 | −3,38 | +0,71 | ±1,42 | −0,81 | 46,2 |
| IHSG > MA50 & sejak FTD | 175 | 56 | +2,02 | −0,42 | +2,44 | ±1,95 | −0,06 | 49,7 |
| DD aktif < 5 | 1.367 | 335 | +0,19 | +0,43 | −0,24 | ±0,70 | −3,16 | 38,1 |
| IHSG > MA50 & DD < 5 | 948 | 224 | +2,83 | +2,93 | −0,10 | ±0,85 | −3,45 | 36,8 |
| Breadth > 50% | 1.299 | 311 | +0,40 | +0,91 | −0,51 | ±0,76 | −3,64 | 36,8 |
| IHSG > MA50 & breadth > 50% | 1.128 | 280 | +2,68 | +2,76 | −0,08 | ±0,70 | −3,51 | 37,1 |

## Keadaan pasar di periode uji

- Follow-through day: 6 kali (2024-06-28, 2024-11-25, 2025-02-17, 2026-04-01, 2026-06-12, 2026-11-12).
- Hari bursa berkeadaan NAIK (sejak FTD): 20.5%; DD aktif ≥ 5: 39.0% hari; distribution day: 116.
- IHSG > MA50: 49.1% hari; breadth > 50%: 53.6% hari.

Breadth hitungan ulang vs `hasil/breadth.csv` (423 tanggal, 2025-02-05 – 2026-11-13): rata-rata selisih 0.06 poin, maks 2.8; sisi terhadap 50% sama di 100.0% tanggal.

