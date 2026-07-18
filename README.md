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

**Catatan kesegaran data:** untuk swing trading, data penutupan H-1 sudah cukup — screening dilakukan malam hari setelah pasar tutup, keputusan dieksekusi besok paginya. Delay 10–15 menit yfinance dan update harian Sectors.app sama sekali tidak jadi masalah untuk pola ini. Data real-time hanya relevan untuk scalping/intraday, dan untuk IDX praktis hanya tersedia lewat [layanan data berbayar BEI](https://www.idx.co.id/id/produk/layanan-data-bei/) atau GoAPI (kuota gratis kecil).

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

# Filter ulang dari CSV hasil sebelumnya, tanpa fetch ulang dari internet
python screener.py --dari-csv hasil_screening.csv --min-dividen 5

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
| `--dari-csv FILE` | Baca data dari CSV hasil sebelumnya, tanpa fetch ulang |

## Daftar Ticker

`tickers/lq45.txt` berisi konstituen LQ45. Buat file sendiri (satu ticker per baris, suffix `.JK` opsional) dan arahkan dengan `--tickers`.

## Otomasi Screening Malam (GitHub Actions)

Workflow [`.github/workflows/screening-malam.yml`](.github/workflows/screening-malam.yml) menjalankan screening otomatis **setiap hari bursa (Senin–Jumat) pukul ±18:17 WIB** — beberapa jam setelah IDX tutup (15:50 WIB), pas untuk pola swing trade: data penutupan dikumpulkan malam ini, keputusan dieksekusi besok pagi.

Setiap malam workflow:

1. Mengambil data seluruh LQ45 dari Yahoo Finance **satu kali**, disimpan ke `hasil/semua.csv` (tabel lengkap tanpa filter).
2. Memfilter ulang dari CSV itu (tanpa fetch ulang, pakai `--dari-csv`) menjadi dua daftar siap pakai:
   - `hasil/swing.csv` — oversold tapi masih uptrend (RSI ≤ 35, harga di atas MA200).
   - `hasil/value.csv` — value stock (PER ≤ 15, PBV ≤ 2, ROE ≥ 15%).
3. Meng-commit hasilnya ke repo, jadi tiap pagi tinggal buka ketiga file di folder `hasil/`. Riwayat screening malam-malam sebelumnya tersimpan otomatis di git history.

**Mengubah kriteria:** edit langkah-langkah screening di file workflow — argumennya sama persis dengan CLI `screener.py`. Mau menambah profil screening ketiga? Duplikat saja salah satu langkah `--dari-csv` dengan filter dan nama output berbeda.

**Menjalankan manual:** buka tab **Actions → Screening Malam → Run workflow** di GitHub.

Catatan penting:

- Jadwal cron hanya aktif di **branch default** repo — pastikan workflow ini sudah ter-merge ke branch utama.
- GitHub menonaktifkan cron otomatis jika repo tidak ada aktivitas selama 60 hari; karena workflow ini meng-commit hasil tiap malam, repo tetap "aktif" dengan sendirinya.
- Yahoo Finance sesekali membatasi request dari server GitHub. Kalau run gagal, coba **Run workflow** ulang, atau jalankan screening di komputer sendiri.

## Disclaimer

Bukan rekomendasi investasi. Data Yahoo Finance bisa tertunda ±15 menit dan sesekali tidak lengkap untuk emiten kecil. File `data/sample_data.csv` berisi **angka contoh buatan** untuk demo offline, bukan data pasar sungguhan. Selalu verifikasi sebelum mengambil keputusan investasi.
