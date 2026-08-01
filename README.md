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
# Screening seluruh daftar default tanpa filter (LQ45 + grup konglomerasi)
python screener.py

# Value stock (medium risk): PER ≤ 15, PBV ≤ 3,5, ROE ≥ 15%
python screener.py --max-per 15 --max-pbv 3.5 --min-roe 15

# Saham dividen: yield ≥ 5%, market cap ≥ 50 triliun
python screener.py --min-dividen 5 --min-mcap 50

# Teknikal (medium risk): sedang koreksi (RSI ≤ 50) tapi masih uptrend jangka panjang
python screener.py --max-rsi 50 --di-atas-ma200

# Swing + konfirmasi volume: koreksi, uptrend, dan volume mulai masuk
python screener.py --max-rsi 50 --di-atas-ma200 --min-volspike 1.5 --min-nilai 10

# Pakai satu daftar saja, atau gabungan beberapa daftar
python screener.py --tickers tickers/lq45.txt
python screener.py --tickers tickers/bakrie.txt tickers/salim.txt

# Hanya saham grup tertentu (cocokkan kolom Grup)
python screener.py --grup Prajogo Hapsoro

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
| `--min-nilai N` | Nilai transaksi rata-rata 20 hari minimal (miliar Rp) — filter likuiditas |
| `--min-volspike N` | Volume terakhir minimal N× rata-rata 20 hari (mis. 1.5 = ada lonjakan minat) |
| `--max-rsi N` / `--min-rsi N` | Batas RSI-14 (≤30 oversold, ≥70 overbought) |
| `--di-atas-ma50` / `--di-atas-ma200` | Harga di atas moving average 50/200 hari |
| `--grup NAMA…` | Hanya saham dari grup tertentu (mis. `--grup Salim Bakrie`) |
| `--urut KOLOM` | Urutkan hasil (default: PER) |
| `--dari-csv FILE` | Baca data dari CSV hasil sebelumnya, tanpa fetch ulang |

## Daftar Ticker

Screening tidak terbatas LQ45. Secara default `screener.py` membaca **semua** file di bawah ini sekaligus:

| File | Grup | Isi |
|---|---|---|
| `tickers/lq45.txt` | `LQ45` | Konstituen indeks LQ45 |
| `tickers/prajogo.txt` | `Prajogo` | Grup Barito / Prajogo Pangestu — BRPT, TPIA, BREN, CUAN, PTRO, CDIA |
| `tickers/bakrie.txt` | `Bakrie` | Grup Bakrie — BNBR, BUMI, BRMS, ENRG, ELTY, DEWA, VKTR, UNSP |
| `tickers/salim.txt` | `Salim` | Grup Salim — INDF, ICBP, SIMP, LSIP, IMAS, IMJS, DNET, MCAS, plus PANI & CBDK (Agung Sedayu–Salim) |
| `tickers/hapsoro.txt` | `Hapsoro` | Terafiliasi Happy Hapsoro — RAJA, RATU, BUVA |

Duplikat antar-daftar otomatis digabung: saham yang ada di dua daftar hanya diambil datanya sekali dan kolom `Grup`-nya ditulis gabungan, misal INDF → `LQ45/Salim`.

**Format file:** satu ticker per baris, suffix `.JK` opsional, komentar diawali `#` (boleh di belakang ticker). Baris `# grup: Nama` menentukan label grup; kalau tidak ada, dipakai nama file.

**Bikin daftar sendiri:** buat file baru di `tickers/`, lalu jalankan `python screener.py --tickers tickers/punyaku.txt`. Untuk memasukkannya ke run otomatis tiap malam, tambahkan path-nya ke `DAFTAR_DEFAULT` di `screener.py`.

⚠️ Daftar grup konglomerasi disusun dari struktur kepemilikan publik dan **bisa berubah** kalau ada akuisisi/divestasi — cek ulang di keterbukaan informasi IDX sebelum dipakai untuk keputusan beli. Emiten di luar LQ45 juga banyak yang likuiditasnya tipis; pakai `--min-nilai` untuk menyaring yang benar-benar bisa ditransaksikan.

## Otomasi Screening Malam (GitHub Actions)

Workflow [`.github/workflows/screening-malam.yml`](.github/workflows/screening-malam.yml) menjalankan screening otomatis **setiap hari bursa (Senin–Jumat) pukul ±18:17 WIB** — beberapa jam setelah IDX tutup (15:50 WIB), pas untuk pola swing trade: data penutupan dikumpulkan malam ini, keputusan dieksekusi besok pagi.

Setiap malam workflow:

1. Mengambil data seluruh daftar default (LQ45 + grup Prajogo, Bakrie, Salim, Hapsoro) dari Yahoo Finance **satu kali**, disimpan ke `hasil/semua.csv` (tabel lengkap tanpa filter).
2. Memfilter ulang dari CSV itu (tanpa fetch ulang, pakai `--dari-csv`) menjadi dua daftar siap pakai:
   - `hasil/swing.csv` — sedang koreksi tapi masih uptrend, **dengan konfirmasi volume** (RSI ≤ 50, harga di atas MA200, volume terakhir ≥ 1,5× rata-rata 20 hari, nilai transaksi ≥ 10 miliar Rp). Sinyal ini lebih jarang muncul tapi lebih tajam — wajar kalau ada malam di mana tidak ada yang lolos.
   - `hasil/value.csv` — value stock profil **medium risk** (PER ≤ 15, PBV ≤ 3,5, ROE ≥ 15%). PBV dipatok 3,5 (bukan 2) supaya blue chip berkualitas yang memang selalu dihargai premium — BBCA, SIDO — tidak otomatis tersaring keluar.
3. Meng-commit hasilnya ke repo, jadi tiap pagi tinggal buka ketiga file di folder `hasil/`. Riwayat screening malam-malam sebelumnya tersimpan otomatis di git history.
4. Men-deploy **dashboard web** ke GitHub Pages (lihat di bawah).

**Mengubah kriteria:** edit langkah-langkah screening di file workflow — argumennya sama persis dengan CLI `screener.py`. Mau menambah profil screening ketiga? Duplikat saja salah satu langkah `--dari-csv` dengan filter dan nama output berbeda.

**Menjalankan manual:** buka tab **Actions → Screening Malam → Run workflow** di GitHub.

### Dashboard Web

Hasil screening bisa dilihat lewat dashboard di:

**<https://2013tib-droid.github.io/Screening-Saham/>**

Fitur dashboard:

- Tiga tab: **Swing**, **Value**, dan **Semua** (tabel lengkap seluruh saham yang dipantau), plus ringkasan jumlah saham yang lolos tiap filter.
- Kolom **Grup** dan dropdown **filter grup** — bisa lihat khusus saham grup Prajogo, Bakrie, Salim, Hapsoro, atau LQ45 saja.
- Klik judul kolom untuk mengurutkan (misalnya urutkan per RSI atau dividen), kotak pencarian untuk mencari ticker/nama.
- Nyaman dibuka di HP, mendukung mode gelap, dan menampilkan waktu pembaruan terakhir (WIB).

Dashboard di-deploy otomatis di akhir setiap run workflow — sumbernya file statis [`dashboard/index.html`](dashboard/index.html), datanya dibaca langsung dari folder `hasil/`. GitHub Pages diaktifkan otomatis pada run pertama; kalau gagal di langkah "Aktifkan & konfigurasi GitHub Pages", aktifkan manual sekali lewat **Settings → Pages → Source: GitHub Actions**, lalu jalankan ulang workflow-nya.

Catatan penting:

- Jadwal cron hanya aktif di **branch default** repo — pastikan workflow ini sudah ter-merge ke branch utama. Workflow juga otomatis jalan sekali setiap ada push ke branch utama, jadi begitu di-merge, hasil pertama dan dashboard langsung tersedia tanpa menunggu malam.
- GitHub menonaktifkan cron otomatis jika repo tidak ada aktivitas selama 60 hari; karena workflow ini meng-commit hasil tiap malam, repo tetap "aktif" dengan sendirinya.
- Yahoo Finance sesekali membatasi request dari server GitHub. Kalau run gagal, coba **Run workflow** ulang, atau jalankan screening di komputer sendiri.

## Uji Akses IDX (net buy asing)

Yahoo Finance **tidak** menyediakan data net buy asing, padahal itu salah satu sinyal yang sering dipakai. Sumber gratisnya ada di IDX ([Ringkasan Saham](https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham), berisi Foreign Buy/Sell per emiten per hari), tapi idx.co.id memakai Cloudflare yang rutin memblokir request non-browser — jadi kelayakannya harus diuji dulu di tempat workflow benar-benar jalan.

Workflow **Uji Akses IDX** (`.github/workflows/uji-idx.yml`) melakukan itu: tab **Actions → Uji Akses IDX → Run workflow**. Dia hanya menembak beberapa endpoint IDX lalu melapor — tidak menyentuh data screening dan tidak commit apa pun. Hasilnya muncul di ringkasan job sebagai salah satu dari tiga kesimpulan:

- **BISA** — endpoint tembus dan kolom asing ketemu; lanjut ke integrasi.
- **SEBAGIAN** — IDX tembus tapi kolom asing tidak ada di endpoint itu; perlu cari berkas lain.
- **DIBLOKIR** — Cloudflare menolak; integrasi langsung tidak layak, perlu sumber alternatif.

Skripnya (`scripts/uji_idx.py`) hanya memakai stdlib, jadi bisa dijalankan lokal juga: `python scripts/uji_idx.py`.

## Disclaimer

Bukan rekomendasi investasi. Data Yahoo Finance bisa tertunda ±15 menit dan sesekali tidak lengkap untuk emiten kecil. File `data/sample_data.csv` berisi **angka contoh buatan** untuk demo offline, bukan data pasar sungguhan. Selalu verifikasi sebelum mengambil keputusan investasi.
