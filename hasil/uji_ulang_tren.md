# Uji Ulang Tren vs Swing

Dihitung 2026-11-16T00:19:32Z oleh `uji_ulang_tren.py`. Sinyal 2024-04-01 – 2026-11-13, 402 emiten ber-harga dari universe 402 emiten.

> ⚠️ **Bias survivorship.** Universe-nya daftar emiten *hari ini* (400 emiten terbesar per hari ini + daftar kurasi). Emiten yang dulu naik lalu ambruk, mengecil, atau delisting tidak ada di data. Angka absolutnya terlalu bagus, dan biasnya lebih besar untuk aturan momentum (TT/RS) yang membeli sesudah saham naik kencang. Kolom selisih terhadap saham acak (universe yang sama) menghapus sebagian bias itu, tidak seluruhnya.

## Per sinyal: selisih vs saham likuid acak

Aturan uji winrate: beli di pembukaan sesi sesudah sinyal, biaya 0,15% + 0,25%, pick ulang tidak dihitung. `SelisihSE%` = galat baku per tanggal beli; selisih yang kurang dari ±2×SE belum bisa dibedakan dari nol.

### Hari bursa ke-5

| Aturan | Filter | Posisi | Winrate% | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | 1.867 | 40,5 | −0,91 | −0,68 | −0,23 | ±0,30 | 41,8 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | 1.189 | 42,2 | +0,16 | +0,15 | +0,01 | ±0,37 | 41,0 |
| TT = 8 | Tanpa filter | 1.041 | 46,0 | +0,66 | −0,18 | +0,84 | ±0,46 | 46,3 |
| TT = 8 | IHSG > MA50 | 736 | 47,4 | +1,77 | +0,36 | +1,41 | ±0,76 | 45,1 |
| TT ≥ 7 | Tanpa filter | 1.595 | 44,8 | +0,03 | −0,36 | +0,39 | ±0,33 | 45,1 |
| TT ≥ 7 | IHSG > MA50 | 1.141 | 45,6 | +0,93 | +0,19 | +0,74 | ±0,54 | 43,7 |
| RS ≥ 80 saja | Tanpa filter | 1.440 | 44,2 | +0,22 | −0,47 | +0,69 | ±0,42 | 44,5 |
| RS ≥ 80 saja | IHSG > MA50 | 947 | 44,0 | +1,26 | −0,03 | +1,29 | ±0,82 | 44,4 |

### Hari bursa ke-10

| Aturan | Filter | Posisi | Winrate% | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | 1.864 | 40,8 | −0,97 | −0,79 | −0,19 | ±0,40 | 42,0 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | 1.189 | 44,7 | +0,82 | +0,68 | +0,13 | ±0,48 | 41,0 |
| TT = 8 | Tanpa filter | 1.036 | 47,2 | +1,82 | +0,16 | +1,65 | ±0,63 | 45,7 |
| TT = 8 | IHSG > MA50 | 736 | 49,6 | +3,67 | +1,29 | +2,38 | ±1,03 | 45,5 |
| TT ≥ 7 | Tanpa filter | 1.590 | 44,2 | +0,79 | −0,07 | +0,86 | ±0,42 | 44,6 |
| TT ≥ 7 | IHSG > MA50 | 1.141 | 47,2 | +2,18 | +1,15 | +1,02 | ±0,78 | 42,9 |
| RS ≥ 80 saja | Tanpa filter | 1.434 | 46,6 | +0,58 | −0,41 | +0,99 | ±0,54 | 45,9 |
| RS ≥ 80 saja | IHSG > MA50 | 947 | 48,4 | +2,78 | +1,00 | +1,78 | ±1,10 | 46,9 |

### Hari bursa ke-21

| Aturan | Filter | Posisi | Winrate% | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | 1.839 | 39,6 | −0,75 | −0,26 | −0,49 | ±0,55 | 38,8 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | 1.189 | 45,5 | +2,46 | +2,50 | −0,04 | ±0,69 | 37,0 |
| TT = 8 | Tanpa filter | 1.029 | 45,3 | +3,30 | −0,01 | +3,30 | ±1,00 | 44,0 |
| TT = 8 | IHSG > MA50 | 736 | 49,5 | +7,33 | +2,30 | +5,03 | ±1,93 | 45,1 |
| TT ≥ 7 | Tanpa filter | 1.571 | 43,8 | +2,34 | 0,00 | +2,33 | ±0,71 | 42,6 |
| TT ≥ 7 | IHSG > MA50 | 1.141 | 47,0 | +5,55 | +2,33 | +3,22 | ±1,29 | 42,8 |
| RS ≥ 80 saja | Tanpa filter | 1.409 | 46,2 | +2,91 | −0,19 | +3,10 | ±0,96 | 44,0 |
| RS ≥ 80 saja | IHSG > MA50 | 947 | 49,0 | +7,42 | +2,24 | +5,18 | ±2,13 | 46,4 |

## Portofolio 10 posisi, tahan 21 hari bursa

Median dari 20 urutan acak pengisian slot (rentang min–maks dalam kurung). Ekuitas awal 1, tanpa pembulatan lot.

| Aturan | Filter | MaxDD% | Total% | CAGR%Median | Keterisian% | TransaksiMedian |
|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | −55,3 (−63,5 … −45,1) | −7,8 (−39,1 … +26,7) | −3,06 | 94,8 | 288 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | −25,0 (−30,9 … −17,1) | +96,2 (+43,8 … +155,7) | +29,20 | 63,7 | 189 |
| TT = 8 | Tanpa filter | −55,1 (−68,8 … −42,4) | +44,0 (−32,6 … +123,7) | +14,87 | 94,8 | 287 |
| TT = 8 | IHSG > MA50 | −32,0 (−41,7 … −20,3) | +114,4 (+46,2 … +221,4) | +33,66 | 64,0 | 190 |
| TT ≥ 7 | Tanpa filter | −51,5 (−54,1 … −45,1) | +4,8 (−29,0 … +104,0) | +1,81 | 95,3 | 290 |
| TT ≥ 7 | IHSG > MA50 | −28,5 (−35,5 … −21,6) | +133,4 (+56,7 … +367,1) | +38,05 | 64,0 | 190 |
| RS ≥ 80 saja | Tanpa filter | −55,6 (−72,4 … −48,1) | +67,9 (−19,9 … +253,0) | +21,78 | 95,3 | 290 |
| RS ≥ 80 saja | IHSG > MA50 | −37,6 (−43,1 … −30,0) | +149,8 (+59,8 … +470,6) | +41,61 | 64,0 | 190 |
| Saham likuid acak (pembanding) | Tanpa filter | −51,1 (−64,4 … −37,6) | −10,0 (−32,6 … +157,5) | −3,92 | 95,3 | 290 |
| Saham likuid acak (pembanding) | IHSG > MA50 | −21,9 (−32,1 … −14,7) | +47,2 (+0,1 … +155,2) | +15,85 | 64,0 | 190 |

IHSG beli-dan-tahan di periode yang sama: total −26,7%, drawdown terdalam −46,3% (2026-01-20 → 2026-11-03).

## Selisih hari ke-21 per semester (tanpa filter)

| Aturan | Semester | Posisi | RataLaba% | RataAcak% | Selisih% |
|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2024-S1 | 128 | −0,87 | −0,45 | −0,41 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2024-S2 | 379 | +0,47 | +0,53 | −0,06 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2025-S1 | 233 | −1,38 | +1,16 | −2,54 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2025-S2 | 513 | +6,90 | +7,54 | −0,64 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2026-S1 | 440 | −9,75 | −9,00 | −0,74 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2026-S2 | 146 | −2,57 | −5,47 | +2,91 |
| TT = 8 | 2024-S1 | 59 | −2,43 | +0,20 | −2,63 |
| TT = 8 | 2024-S2 | 220 | +3,35 | +0,18 | +3,17 |
| TT = 8 | 2025-S1 | 125 | +2,74 | +1,04 | +1,70 |
| TT = 8 | 2025-S2 | 339 | +14,92 | +6,59 | +8,33 |
| TT = 8 | 2026-S1 | 203 | −12,37 | −8,93 | −3,44 |
| TT = 8 | 2026-S2 | 83 | −1,08 | −7,32 | +6,24 |
| TT ≥ 7 | 2024-S1 | 115 | −1,81 | −0,44 | −1,37 |
| TT ≥ 7 | 2024-S2 | 312 | +2,10 | +0,43 | +1,67 |
| TT ≥ 7 | 2025-S1 | 188 | +1,51 | +0,74 | +0,77 |
| TT ≥ 7 | 2025-S2 | 508 | +11,84 | +7,03 | +4,81 |
| TT ≥ 7 | 2026-S1 | 317 | −9,57 | −9,23 | −0,34 |
| TT ≥ 7 | 2026-S2 | 131 | −0,30 | −6,57 | +6,27 |
| RS ≥ 80 saja | 2024-S1 | 137 | +0,09 | −0,23 | +0,32 |
| RS ≥ 80 saja | 2024-S2 | 255 | +2,91 | +0,58 | +2,33 |
| RS ≥ 80 saja | 2025-S1 | 193 | +4,07 | +1,36 | +2,71 |
| RS ≥ 80 saja | 2025-S2 | 338 | +17,39 | +7,46 | +9,93 |
| RS ≥ 80 saja | 2026-S1 | 308 | −9,55 | −7,41 | −2,15 |
| RS ≥ 80 saja | 2026-S2 | 178 | −2,14 | −4,99 | +2,84 |

