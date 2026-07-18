# Screening Saham Indonesia 🇮🇩

Screener saham Bursa Efek Indonesia (IDX) berbasis Python dengan **data gratis** dari Yahoo Finance — tanpa API key, tanpa biaya.

## API/Sumber Data Saham Indonesia yang Gratis

| Sumber | Gratis? | API Key | Catatan |
|---|---|---|---|
| **Yahoo Finance** (via library `yfinance`) | ✅ Ya, tanpa batas resmi | ❌ Tidak perlu | Dipakai proyek ini. Ticker IDX memakai suffix `.JK` (misal `BBCA.JK`). Ada harga historis, PER, PBV, ROE, dividen, market cap, dll. Tidak resmi (scraping API publik Yahoo), sesekali bisa berubah. |
| **Sectors.app** ⭐ | ✅ Free tier | ✅ Perlu (gratis) | **API pilihan untuk IDX.** Khusus Indonesia (& Singapura), coverage ~99% emiten tercatat. Fundamental, laporan keuangan, valuasi, sektor, indeks (IHSG). API-first, dokumentasi rapi. Kuota free tier terbatas — cek [sectors.app](https://sectors.app/). |
| **GoAPI** (goapi.io) | ✅ Free tier | ✅ Perlu (gratis) | Buatan Indonesia, ada endpoint khusus IDX: harga, profil emiten, indeks. Kuota terbatas di paket gratis. |
| **Finnhub** | ⚠️ Free tier ≠ IDX | ✅ Perlu | Free tier **hanya saham AS** — akses bursa internasional (termasuk IDX) butuh paket berbayar. Tidak cocok untuk screener gratis IDX. |
| **Alpha Vantage** | ⚠️ 25 request/hari | ✅ Perlu | Limit free tier cuma 25 request/hari — satu run screening LQ45 saja tidak cukup. Fundamental praktis hanya saham AS; cakupan IDX tidak jelas. |
| **Situs IDX (idx.co.id)** | ✅ | ❌ | Data resmi (ringkasan perdagangan, laporan keuangan) tapi tidak ada API publik resmi — biasanya diunduh manual/scraping. |

**Rekomendasi:** pakai `yfinance` sebagai sumber data utama (gratis, tanpa registrasi, semua kolom screener tersedia), dan **Sectors.app** sebagai API pelengkap terbaik saat butuh data yang yfinance lemah: laporan keuangan detail, emiten kecil di luar LQ45, dan breakdown sektor. Finnhub dan Alpha Vantage **tidak direkomendasikan** untuk IDX — free tier Finnhub tidak mencakup IDX sama sekali, dan limit 25 request/hari Alpha Vantage terlalu kecil untuk screening.

## Instalasi

```bash
pip install -r requirements.txt
```

## Cara Pakai

```bash
# Screening seluruh LQ45 tanpa filter (lihat semua datanya)
python screener.py

# Value stock: PER ≤ 15, PBV ≤ 2, ROE ≥ 15%
python screener.py --max-per 15 --max-pbv 2 --min-roe 15

# Saham dividen: yield ≥ 5%, market cap ≥ 50 triliun
python screener.py --min-dividen 5 --min-mcap 50

# Teknikal: oversold (RSI ≤ 35) tapi masih uptrend jangka panjang
python screener.py --max-rsi 35 --di-atas-ma200

# Pakai daftar ticker sendiri
python screener.py --tickers tickers/lq45.txt

# Mode demo offline (data contoh, BUKAN data pasar riil)
python screener.py --demo --max-per 15 --min-roe 15
```

Hasil ditampilkan di terminal dan disimpan ke `hasil_screening.csv`.

### Filter yang tersedia

| Opsi | Arti |
|---|---|
| `--max-per N` | Price-to-Earnings Ratio maksimal (PER negatif otomatis gugur) |
| `--max-pbv N` | Price-to-Book Value maksimal |
| `--min-roe N` | Return on Equity minimal (%) |
| `--min-dividen N` | Dividend yield minimal (%) |
| `--min-mcap N` | Market cap minimal (triliun Rp) |
| `--max-rsi N` / `--min-rsi N` | Batas RSI-14 (≤30 oversold, ≥70 overbought) |
| `--di-atas-ma50` / `--di-atas-ma200` | Harga di atas moving average 50/200 hari |
| `--urut KOLOM` | Urutkan hasil (default: PER) |

## Daftar Ticker

`tickers/lq45.txt` berisi konstituen LQ45. Buat file sendiri (satu ticker per baris, suffix `.JK` opsional) dan arahkan dengan `--tickers`.

## Disclaimer

Bukan rekomendasi investasi. Data Yahoo Finance bisa tertunda ±15 menit dan sesekali tidak lengkap untuk emiten kecil. File `data/sample_data.csv` berisi **angka contoh buatan** untuk demo offline, bukan data pasar sungguhan. Selalu verifikasi sebelum mengambil keputusan investasi.
