# Uji Ulang Tren vs Swing

Dihitung 2026-11-16T00:25:35Z oleh `uji_ulang_tren.py`. Sinyal 2024-04-01 – 2026-11-13, 401 emiten ber-harga dari universe 402 emiten.

> ⚠️ **Bias survivorship.** Universe-nya daftar emiten *hari ini* (400 emiten terbesar per hari ini + daftar kurasi). Emiten yang dulu naik lalu ambruk, mengecil, atau delisting tidak ada di data. Angka absolutnya terlalu bagus, dan biasnya lebih besar untuk aturan momentum (TT/RS) yang membeli sesudah saham naik kencang. Kolom selisih terhadap saham acak (universe yang sama) menghapus sebagian bias itu, tidak seluruhnya.

## Per sinyal: selisih vs saham likuid acak

Aturan uji winrate: beli di pembukaan sesi sesudah sinyal, biaya 0,15% + 0,25%, pick ulang tidak dihitung. `SelisihSE%` = galat baku per tanggal beli; selisih yang kurang dari ±2×SE belum bisa dibedakan dari nol.

### Hari bursa ke-5

| Aturan | Filter | Posisi | Winrate% | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | 1.853 | 40,6 | −0,90 | −0,68 | −0,22 | ±0,30 | 41,9 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | 1.181 | 42,3 | +0,16 | +0,15 | +0,01 | ±0,38 | 41,2 |
| TT = 8 | Tanpa filter | 1.036 | 46,3 | +0,69 | −0,18 | +0,87 | ±0,46 | 46,2 |
| TT = 8 | IHSG > MA50 | 734 | 47,7 | +1,80 | +0,37 | +1,44 | ±0,75 | 45,2 |
| TT ≥ 7 | Tanpa filter | 1.588 | 45,0 | +0,09 | −0,35 | +0,44 | ±0,33 | 45,2 |
| TT ≥ 7 | IHSG > MA50 | 1.136 | 45,7 | +1,00 | +0,21 | +0,79 | ±0,55 | 43,8 |
| RS ≥ 80 saja | Tanpa filter | 1.438 | 44,2 | +0,22 | −0,47 | +0,69 | ±0,42 | 44,5 |
| RS ≥ 80 saja | IHSG > MA50 | 946 | 44,1 | +1,26 | −0,02 | +1,28 | ±0,81 | 44,3 |

### Hari bursa ke-10

| Aturan | Filter | Posisi | Winrate% | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | 1.850 | 40,9 | −0,96 | −0,78 | −0,19 | ±0,41 | 41,9 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | 1.181 | 44,7 | +0,83 | +0,69 | +0,14 | ±0,48 | 41,1 |
| TT = 8 | Tanpa filter | 1.031 | 47,5 | +1,86 | +0,15 | +1,70 | ±0,63 | 45,8 |
| TT = 8 | IHSG > MA50 | 734 | 49,9 | +3,70 | +1,30 | +2,40 | ±1,03 | 45,6 |
| TT ≥ 7 | Tanpa filter | 1.583 | 44,1 | +0,78 | −0,05 | +0,83 | ±0,43 | 44,6 |
| TT ≥ 7 | IHSG > MA50 | 1.136 | 46,9 | +2,14 | +1,17 | +0,97 | ±0,79 | 42,8 |
| RS ≥ 80 saja | Tanpa filter | 1.432 | 46,4 | +0,57 | −0,41 | +0,98 | ±0,54 | 45,9 |
| RS ≥ 80 saja | IHSG > MA50 | 946 | 48,1 | +2,76 | +1,01 | +1,75 | ±1,10 | 46,8 |

### Hari bursa ke-21

| Aturan | Filter | Posisi | Winrate% | RataLaba% | RataAcak% | Selisih% | SelisihSE% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | 1.825 | 39,7 | −0,74 | −0,25 | −0,49 | ±0,56 | 38,9 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | 1.181 | 45,5 | +2,48 | +2,51 | −0,03 | ±0,69 | 37,2 |
| TT = 8 | Tanpa filter | 1.024 | 45,5 | +3,35 | −0,01 | +3,35 | ±1,01 | 44,2 |
| TT = 8 | IHSG > MA50 | 734 | 49,6 | +7,37 | +2,30 | +5,07 | ±1,93 | 45,4 |
| TT ≥ 7 | Tanpa filter | 1.564 | 43,7 | +2,35 | +0,01 | +2,34 | ±0,71 | 42,6 |
| TT ≥ 7 | IHSG > MA50 | 1.136 | 46,7 | +5,55 | +2,32 | +3,22 | ±1,30 | 42,8 |
| RS ≥ 80 saja | Tanpa filter | 1.407 | 46,3 | +2,92 | −0,19 | +3,11 | ±0,96 | 44,0 |
| RS ≥ 80 saja | IHSG > MA50 | 946 | 49,2 | +7,44 | +2,26 | +5,18 | ±2,13 | 46,3 |

## Ketahanan: apakah selisihnya datang dari segelintir saham?

Hari bursa ke-21. `MedianSelisih%` = median per posisi; `SelisihPangkas%` = rata-rata sesudah membuang 5% posisi teratas dan terbawah; `SelisihTanpa10%` = rata-rata sesudah membuang semua posisi dari 10 emiten penyumbang selisih terbesar. Kalau selisih rata-rata positif tapi ketiga kolom ini mendekati nol atau negatif, keunggulannya bergantung pada beberapa saham yang meledak — persis bagian yang paling rawan bias survivorship.

| Aturan | Filter | Posisi | Selisih% | MedianSelisih% | SelisihPangkas% | SelisihTanpa10% | MenangVsAcak% |
|---|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | 1.825 | −0,49 | −2,97 | −2,19 | −1,51 | 38,9 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | 1.181 | −0,03 | −3,54 | −2,28 | −1,63 | 37,2 |
| TT = 8 | Tanpa filter | 1.024 | +3,35 | −2,62 | −0,03 | +0,94 | 44,2 |
| TT = 8 | IHSG > MA50 | 734 | +5,07 | −2,77 | +1,10 | +1,69 | 45,4 |
| TT ≥ 7 | Tanpa filter | 1.564 | +2,34 | −2,72 | −0,56 | +0,79 | 42,6 |
| TT ≥ 7 | IHSG > MA50 | 1.136 | +3,22 | −2,85 | −0,02 | +0,96 | 42,8 |
| RS ≥ 80 saja | Tanpa filter | 1.407 | +3,11 | −1,90 | +0,02 | +1,37 | 44,0 |
| RS ≥ 80 saja | IHSG > MA50 | 946 | +5,18 | −1,93 | +1,34 | +2,53 | 46,3 |

### 10 penyumbang selisih terbesar (hari ke-21, tanpa filter)

**Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2)**

| Ticker | Posisi | JumlahSelisih% | RataSelisih% | PorsiDariTotal% |
|---|---|---|---|---|
| BUVA | 8 | +334,80 | +41,84 | −37,5 |
| PTRO | 16 | +279,80 | +17,49 | −31,4 |
| MDIA | 5 | +158,20 | +31,65 | −17,7 |
| ENRG | 15 | +142,80 | +9,52 | −16,0 |
| MINA | 9 | +137,60 | +15,29 | −15,4 |
| DEWA | 15 | +136,80 | +9,12 | −15,3 |
| WIFI | 13 | +133,00 | +10,23 | −14,9 |
| TINS | 19 | +123,70 | +6,51 | −13,9 |
| ASLI | 5 | +121,30 | +24,26 | −13,6 |
| RAJA | 18 | +113,70 | +6,32 | −12,7 |

**TT = 8**

| Ticker | Posisi | JumlahSelisih% | RataSelisih% | PorsiDariTotal% |
|---|---|---|---|---|
| BUVA | 7 | +304,40 | +43,48 | 8,9 |
| WIFI | 15 | +300,50 | +20,03 | 8,8 |
| JARR | 4 | +290,20 | +72,54 | 8,5 |
| INDS | 2 | +284,50 | +142,24 | 8,3 |
| INET | 10 | +255,80 | +25,58 | 7,4 |
| NATO | 1 | +250,20 | +250,17 | 7,3 |
| MLPT | 4 | +237,60 | +59,41 | 6,9 |
| PTRO | 18 | +231,90 | +12,88 | 6,8 |
| CBRE | 2 | +211,70 | +105,87 | 6,2 |
| ASLI | 4 | +171,00 | +42,74 | 5,0 |

**TT ≥ 7**

| Ticker | Posisi | JumlahSelisih% | RataSelisih% | PorsiDariTotal% |
|---|---|---|---|---|
| BUVA | 10 | +384,20 | +38,42 | 10,5 |
| WIFI | 17 | +320,60 | +18,86 | 8,8 |
| INDS | 2 | +284,50 | +142,24 | 7,8 |
| PTRO | 18 | +283,20 | +15,73 | 7,7 |
| JARR | 6 | +271,20 | +45,21 | 7,4 |
| MLPT | 4 | +237,60 | +59,41 | 6,5 |
| IMPC | 6 | +193,20 | +32,20 | 5,3 |
| CBRE | 4 | +181,40 | +45,36 | 5,0 |
| INET | 11 | +169,40 | +15,40 | 4,6 |
| DEWA | 16 | +167,90 | +10,49 | 4,6 |

**RS ≥ 80 saja**

| Ticker | Posisi | JumlahSelisih% | RataSelisih% | PorsiDariTotal% |
|---|---|---|---|---|
| WIFI | 18 | +351,50 | +19,53 | 8,0 |
| BUVA | 14 | +342,10 | +24,44 | 7,8 |
| PTRO | 20 | +328,20 | +16,41 | 7,5 |
| INDS | 4 | +282,60 | +70,66 | 6,5 |
| JARR | 16 | +257,20 | +16,07 | 5,9 |
| ASLI | 9 | +230,00 | +25,56 | 5,3 |
| IMPC | 11 | +214,80 | +19,53 | 4,9 |
| NATO | 2 | +211,80 | +105,88 | 4,8 |
| VKTR | 14 | +199,80 | +14,27 | 4,6 |
| MLPT | 6 | +187,10 | +31,18 | 4,3 |

## Portofolio 10 posisi, tahan 21 hari bursa

Median dari 20 urutan acak pengisian slot (rentang min–maks dalam kurung). Ekuitas awal 1, tanpa pembulatan lot.

| Aturan | Filter | MaxDD% | Total% | CAGR%Median | Keterisian% | TransaksiMedian |
|---|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | Tanpa filter | −49,7 (−57,1 … −45,3) | +12,1 (−32,6 … +92,0) | +4,45 | 94,8 | 288 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | IHSG > MA50 | −23,1 (−30,0 … −15,4) | +103,8 (+57,2 … +164,9) | +31,10 | 63,7 | 189 |
| TT = 8 | Tanpa filter | −54,7 (−62,8 … −42,4) | +46,1 (−13,8 … +95,0) | +15,53 | 94,8 | 287 |
| TT = 8 | IHSG > MA50 | −32,0 (−41,7 … −20,3) | +114,4 (+46,2 … +221,4) | +33,66 | 64,0 | 190 |
| TT ≥ 7 | Tanpa filter | −50,4 (−61,5 … −41,8) | +25,2 (−27,4 … +102,9) | +8,94 | 95,3 | 290 |
| TT ≥ 7 | IHSG > MA50 | −24,9 (−38,9 … −17,3) | +165,4 (+31,2 … +427,2) | +44,97 | 64,0 | 190 |
| RS ≥ 80 saja | Tanpa filter | −55,6 (−72,4 … −48,1) | +71,1 (−17,2 … +269,9) | +22,66 | 95,3 | 290 |
| RS ≥ 80 saja | IHSG > MA50 | −37,8 (−49,0 … −30,0) | +162,2 (+63,6 … +492,6) | +44,31 | 64,0 | 190 |
| Saham likuid acak (pembanding) | Tanpa filter | −50,9 (−70,0 … −38,6) | +7,0 (−46,3 … +109,3) | +2,58 | 95,3 | 290 |
| Saham likuid acak (pembanding) | IHSG > MA50 | −22,6 (−32,1 … −15,2) | +48,2 (−23,0 … +124,3) | +16,04 | 64,0 | 190 |

IHSG beli-dan-tahan di periode yang sama: total −26,7%, drawdown terdalam −46,3% (2026-01-20 → 2026-11-03).

## Selisih hari ke-21 per semester (tanpa filter)

| Aturan | Semester | Posisi | RataLaba% | RataAcak% | Selisih% |
|---|---|---|---|---|---|
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2024-S1 | 128 | −0,87 | −0,41 | −0,45 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2024-S2 | 376 | +0,49 | +0,55 | −0,06 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2025-S1 | 229 | −1,33 | +1,18 | −2,51 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2025-S2 | 509 | +6,92 | +7,56 | −0,64 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2026-S1 | 437 | −9,77 | −9,00 | −0,77 |
| Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2) | 2026-S2 | 146 | −2,57 | −5,49 | +2,92 |
| TT = 8 | 2024-S1 | 59 | −2,43 | +0,25 | −2,68 |
| TT = 8 | 2024-S2 | 220 | +3,35 | +0,17 | +3,18 |
| TT = 8 | 2025-S1 | 124 | +2,78 | +1,13 | +1,65 |
| TT = 8 | 2025-S2 | 337 | +15,05 | +6,61 | +8,44 |
| TT = 8 | 2026-S1 | 201 | −12,39 | −9,03 | −3,36 |
| TT = 8 | 2026-S2 | 83 | −1,08 | −7,35 | +6,27 |
| TT ≥ 7 | 2024-S1 | 115 | −1,81 | −0,40 | −1,41 |
| TT ≥ 7 | 2024-S2 | 312 | +2,10 | +0,43 | +1,67 |
| TT ≥ 7 | 2025-S1 | 188 | +1,48 | +0,71 | +0,76 |
| TT ≥ 7 | 2025-S2 | 504 | +11,89 | +7,03 | +4,86 |
| TT ≥ 7 | 2026-S1 | 314 | −9,54 | −9,17 | −0,37 |
| TT ≥ 7 | 2026-S2 | 131 | −0,30 | −6,60 | +6,29 |
| RS ≥ 80 saja | 2024-S1 | 137 | +0,09 | −0,19 | +0,28 |
| RS ≥ 80 saja | 2024-S2 | 253 | +3,01 | +0,55 | +2,46 |
| RS ≥ 80 saja | 2025-S1 | 193 | +4,07 | +1,37 | +2,70 |
| RS ≥ 80 saja | 2025-S2 | 338 | +17,39 | +7,49 | +9,90 |
| RS ≥ 80 saja | 2026-S1 | 308 | −9,55 | −7,41 | −2,14 |
| RS ≥ 80 saja | 2026-S2 | 178 | −2,14 | −5,00 | +2,86 |

