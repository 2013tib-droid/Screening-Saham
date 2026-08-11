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

# Fundamental terkuat: skor ≥ 70, diurut dari yang paling tinggi
python screener.py --min-skor 70 --urut Skor

# Saham dividen: yield ≥ 5%, market cap ≥ 50 triliun
python screener.py --min-dividen 5 --min-mcap 50

# Lapkeu terakhir bagus: laba kuartal naik ≥ 20% YoY, ROE ≥ 10%, valuasi belum mahal
python screener.py --min-laba-yoy 20 --min-roe 10 --max-per 25 --min-nilai 1

# Teknikal (medium risk): sedang koreksi (RSI ≤ 50) tapi masih uptrend jangka panjang
python screener.py --max-rsi 50 --di-atas-ma200

# Swing + konfirmasi volume: uptrend, belum overbought, dan volume mulai masuk
python screener.py --max-rsi 65 --di-atas-ma200 --min-volspike 1.2 --min-nilai 5

# Pakai satu daftar saja, atau gabungan beberapa daftar
python screener.py --tickers tickers/lq45.txt
python screener.py --tickers tickers/bakrie.txt tickers/salim.txt

# Hanya saham grup tertentu (cocokkan kolom Grup)
python screener.py --grup Prajogo Hapsoro

# Fundamental kuat, tanpa satu pun red flag, dan cukup likuid
python screener.py --min-skor 75 --tanpa-flag --min-nilai 5 --urut Skor

# Murah dibanding sektornya sendiri, bukan dibanding pasar secara umum
python screener.py --maks-per-sektor 0.7 --min-roe 12 --maks-der 1

# Filter ulang dari CSV hasil sebelumnya, tanpa fetch ulang dari internet
python screener.py --dari-csv hasil_screening.csv --min-dividen 5

# Laporan fundamental lengkap satu emiten (lihat bagian Analisa Satu Emiten)
python analisa.py BBCA

# Mode demo offline (data contoh, BUKAN data pasar riil)
python screener.py --demo --max-per 15 --min-roe 15
```

Hasil ditampilkan di terminal dan disimpan ke `hasil_screening.csv`.

### Filter yang tersedia

| Opsi | Arti |
|---|---|
| `--min-skor N` | Skor fundamental minimal (1–100), lihat [Kolom Skor](#kolom-skor) |
| `--max-per N` | Price-to-Earnings Ratio maksimal (PER negatif otomatis gugur) |
| `--max-pbv N` | Price-to-Book Value maksimal |
| `--maks-per-sektor N` | PER maksimal **relatif median sektornya** (0.8 = minimal 20% lebih murah dari sektornya) |
| `--maks-pbv-sektor N` | PBV maksimal relatif median sektornya |
| `--min-roe N` | Return on Equity minimal (%) |
| `--maks-der N` | Debt to Equity maksimal (mis. 1.0) |
| `--min-current-ratio N` | Current Ratio minimal (bank tidak punya kolom ini) |
| `--min-ocf-laba N` | Rasio arus kas operasi terhadap laba bersih minimal (0.8 = labanya sebagian besar benar-benar jadi kas) |
| `--sektor NAMA…` | Hanya sektor tertentu (mis. `--sektor Technology 'Real Estate'`) |
| `--min-laba-yoy N` | Pertumbuhan laba kuartal terakhir (YoY) minimal (%) — saringan "lapkeu terakhir bagus" |
| `--min-omzet-yoy N` | Pertumbuhan pendapatan kuartal terakhir (YoY) minimal (%) |
| `--min-dividen N` | Dividend yield minimal (%) |
| `--min-mcap N` | Market cap minimal (triliun Rp) |
| `--min-nilai N` | Nilai transaksi rata-rata 20 hari minimal (miliar Rp) — filter likuiditas |
| `--min-volspike N` | Volume terakhir minimal N× rata-rata 20 hari (mis. 1.5 = ada lonjakan minat) |
| `--max-rsi N` / `--min-rsi N` | Batas RSI-14 (≤30 oversold, ≥70 overbought) |
| `--di-atas-ma50` / `--di-atas-ma200` | Harga di atas moving average 50/200 hari |
| `--grup NAMA…` | Hanya saham dari grup tertentu (mis. `--grup Salim Bakrie`) |
| `--status STATUS…` | Hanya saham dengan status tertentu (mis. `--status BUY BOW`) |
| `--urut KOLOM` | Urutkan hasil (default: PER) |
| `--dari-csv FILE` | Baca data dari CSV hasil sebelumnya, tanpa fetch ulang |

## Analisa Satu Emiten (`analisa.py`)

Screener menjawab *"dari 400 emiten, mana yang layak dilihat"*. Untuk pertanyaan berikutnya — *"emiten ini bagaimana persisnya"* — ada `analisa.py`, yang menghasilkan laporan Markdown lengkap dari data yang sudah ada, tanpa menarik apa pun dari internet:

```bash
python analisa.py BBCA                          # tampilkan di layar
python analisa.py ANTM --output analisa/ANTM.md # simpan ke file
```

Butuh `hasil/semua.csv` (dari run screener) karena median sektor dihitung dari harga terkini.

Isi laporannya: tabel skor lima kategori, rincian tiap metrik beserta bobot dan penyesuaian sektoralnya, angka pendukung dalam rupiah, kekuatan & kelemahan, red flags, status valuasi dengan nilai wajar dan margin of safety, tingkat keyakinan, dan rekomendasi Accumulate / Hold / Reduce / Avoid.

**Nilai wajar** ditaksir dari dua jangkar sekaligus — median PER sektor × EPS, dan median PBV sektor × nilai buku per saham — lalu dirata-ratakan. Keduanya dipakai bersama karena masing-masing punya titik butanya: PER runtuh saat labanya sedang tidak normal, PBV runtuh saat nilai bukunya tidak mencerminkan daya hasil. Laporan menyatakan **arah bias** taksirannya alih-alih menyembunyikannya:

- Kalau ROE-nya jauh di atas median sektor, jangkar PBV kemungkinan **merendahkan** nilai wajar — emiten yang menghasilkan imbal hasil di atas sektornya memang layak dihargai premium terhadap PBV median. Contoh nyata: BBCA (ROE 22,5% vs median sektor 7,8%) keluar sebagai "Overvalued 53%" kalau angkanya ditelan mentah, padahal jangkar PER-nya justru menunjuk harga wajar yang praktis sama dengan harga pasar.
- Kalau kedua jangkar berselisih lebih dari 2×, laporan menyatakan rata-ratanya tidak berarti banyak dan menyuruh memeriksa mana yang lebih relevan.
- Kalau margin of safety melewati ±100%, itu tanda penyebutnya nyaris nol, bukan diskon sebesar itu.

**DCF sengaja tidak dihitung.** Data yang ada hanya menyediakan pertumbuhan tiga tahun ke belakang; menurunkan proyeksi sepuluh tahun ke depan darinya menghasilkan angka yang terlihat presisi tapi sepenuhnya ditentukan asumsi yang dikarang sendiri.

**Yang tidak dihasilkan skrip ini:** bull/bear case, moat, katalis, dan kualitas manajemen. Semuanya menuntut penilaian atas hal yang tidak ada di laporan keuangan — rencana korporasi, posisi bersaing, rekam jejak manajemen memenuhi guidance. Bagian itu keluar sebagai tabel bukti dan pertanyaan terarah ("apakah labanya jadi kas?", "apakah manajemen mendilusi pemegang saham?") dengan angkanya sudah disiapkan, bukan sebagai kesimpulan yang dikarang.

**Tingkat keyakinan** mengukur seberapa jauh angka di laporan boleh dipercaya — bukan seberapa yakin sahamnya akan naik. Turun bila basisnya laporan tahunan (−25), metrik inti kosong (−6 per metrik), pembanding sektornya kurang dari 3 emiten (−15), likuiditasnya tipis (−10), atau emitennya bank (−10, karena NIM/NPL/CAR/LDR tidak tersedia di sumber gratis ini padahal itu metrik penilai utama sebuah bank).

## Kolom Status

Tiap saham dapat satu label ringkas yang merangkum posisi harganya terhadap tren:

| Status | Arti | Aturannya |
|---|---|---|
| **BUY** | Tren naik, momentum sehat, volume masuk | Harga > MA50 dan > MA200, RSI 50–70, VolSpike ≥ 1,2 |
| **BOW** | *Buy on weakness* — uptrend jangka panjang tapi sedang koreksi | Harga > MA200, tapi harga < MA50 **atau** RSI ≤ 50 |
| **HOLD** | Sudah naik tinggi atau volume sepi — tahan, jangan kejar | Harga > MA200 dan RSI ≥ 70, atau tanpa konfirmasi volume |
| **WSE** | *Wait & see* — sinyal campur | Harga > MA50 tapi masih < MA200; atau downtrend dengan RSI ≤ 30 |
| **JUAL** | Tren turun, belum ada tanda pembalikan | Harga < MA50 **dan** < MA200, RSI > 30 |
| **TIPIS** | Likuiditas tidak memadai | Nilai transaksi < 1 miliar Rp/hari (dicek lebih dulu dari semua aturan lain) |
| **-** | Data tidak lengkap | Harga/MA50/MA200/RSI ada yang kosong |

Aturannya diperiksa berurutan, label pertama yang cocok dipakai, dan sengaja dibuat konservatif: kalau sinyalnya tidak jelas jawabannya WSE, bukan BUY. Status selalu dihitung ulang tiap run (tidak dibaca dari CSV lama), jadi kalau aturannya diubah, seluruh tabel ikut menyesuaikan.

⚠️ **Status ini bukan rekomendasi beli/jual.** Ini murni aturan mekanis dari empat angka teknikal — tidak tahu apa pun soal berita emiten, laporan keuangan, rencana korporasi, atau aliran dana bandar. Saham berstatus JUAL bisa saja justru sedang di titik balik, dan yang BUY bisa langsung turun besoknya. Pakai sebagai penyaring awal, bukan sebagai keputusan.

Batas likuiditas `AMBANG_LIKUID` dan seluruh ambang lain ada di bagian atas `screener.py` — silakan disesuaikan dengan gaya trading Anda.

## Kolom Skor

Kalau **Status** merangkum sisi teknikal, **Skor** merangkum sisi fundamental: satu angka **1–100** yang menjawab "perusahaan ini sehat atau tidak". Makin tinggi makin sehat — untung besar, tumbuh, dan valuasinya belum kemahalan.

Skor disusun dari **lima kategori** berbobot tetap, masing-masing berisi beberapa komponen:

| Kategori | Bobot | Komponen |
|---|---|---|
| **Valuasi** | 25 | `PERvsSektor`, `PBVvsSektor`, `PER`, `EV/EBITDA`, `Dividen%` |
| **Profitabilitas & Kualitas Laba** | 25 | `ROE%`, `ROA%`, `MarginBersih%`, `MarginOperasi%`, `OCF/Laba` |
| **Kesehatan Keuangan** | 20 | `DER`, `UtangBersih/EBITDA`, `InterestCoverage`, `CurrentRatio`, `QuickRatio` |
| **Pertumbuhan** | 20 | `LabaYoY%`, `OmzetYoY%`, `LabaCAGR3%`, `OmzetCAGR3%`, `TahunLabaNaik` |
| **Arus Kas & Alokasi Modal** | 10 | `FCFYield%`, `Payout%`, `SahamYoY%`, `Capex/OCF` |

Perbandingan terhadap **median sektor** diberi porsi terbesar di kategori valuasi, karena angka absolut tidak bisa membedakan PBV 2,5 di bank dari PBV 2,5 di emiten batubara.

Tiap komponen dipetakan ke skala 0–100 lewat interpolasi linier antar titik acuan (mis. ROE 15% → 65, ROE 30% → 95; DER 0,6 → 78, DER 2,5 → 22). Sebagian komponen sengaja **berpuncak di tengah**, bukan makin tinggi makin baik: `Payout%` 30–50% dinilai terbaik karena 0% berarti tidak berbagi hasil sementara di atas 100% berarti dividennya melebihi laba; `Capex/OCF` begitu juga, karena capex sangat rendah bisa berarti bisnis ringan modal tapi bisa juga berarti perusahaannya berhenti berinvestasi.

Bobot dan titik acuannya ada di `BOBOT_KATEGORI` dan `KOMPONEN_SKOR` pada `screener.py`. Skor tiap kategori ikut tersimpan di CSV (`SkorValuasi`, `SkorProfitabilitas`, …) supaya angka totalnya bisa dibongkar — dua emiten berskor 70 bisa sampai ke sana lewat jalan yang sangat berbeda.

Cara bacanya:

| Skor | Arti |
|---|---|
| **90–100** | Exceptional |
| **80–89** | Excellent |
| **65–79** | Good |
| **50–64** | Average / Fair |
| **35–49** | Weak |
| **< 35** | Poor / hindari |
| *(kosong)* | Data fundamentalnya terlalu sedikit untuk disimpulkan |

### Penyesuaian sektoral

Satu set bobot tidak berlaku untuk semua industri, jadi `PENYESUAIAN_SEKTOR` mengalikan bobot komponen tertentu per sektor (faktor 0 = komponennya tidak dipakai sama sekali, porsinya dibagi ulang):

| Sektor | Penyesuaian | Alasan |
|---|---|---|
| **Perbankan & Jasa Keuangan** | DER, Net Debt/EBITDA, Current/Quick Ratio, Interest Coverage, EV/EBITDA dimatikan; `PBVvsSektor` ×1,6 dan `ROE%` ×1,4 | Neraca bank tidak mengenal aset lancar, dan utangnya adalah dana pihak ketiga — itu bisnisnya, bukan bebannya. P/B dan ROE memang metrik utama untuk menilai bank |
| **Energi & Komoditas** | `UtangBersih/EBITDA` ×1,6, `FCFYield%` ×1,3; `PER` ×0,6, `LabaYoY%` ×0,7 | Yang menentukan bertahan-tidaknya melewati siklus adalah utang bersih terhadap kas yang dihasilkan, bukan laba satu tahun yang kebetulan sedang di puncak harga komoditas |
| **Properti & Konstruksi** | `DER` ×1,5, `CurrentRatio` ×1,3, `OCF/Laba` ×1,3 | Gearing dan kemampuan mendanai proyek yang menentukan; laba akuntansinya sering mendahului kasnya |
| **Consumer & Retail** | `MarginBersih%` ×1,4, `MarginOperasi%` ×1,3, `OCF/Laba` ×1,3 | Yang membedakan pemenang adalah margin yang bertahan dan kas yang benar-benar masuk |
| **Teknologi** | `PER` ×0,4, `EV/EBITDA` ×0,5, `Dividen%` ×0,3; `OmzetYoY%` ×1,5, `FCFYield%` ×1,4, `SahamYoY%` ×1,5 | Toleransi valuasi lebih tinggi, tapi ditagih lebih keras soal kualitas pertumbuhan, kas yang terbakar, dan dilusi |

### Kolom Flag (red flags)

Kolom `Flag` menandai kondisi yang **menolak dirata-ratakan**. Skor adalah rata-rata, dan rata-rata bisa menutupi satu cacat berat dengan banyak angka bagus — emiten berekuitas negatif tetap bisa dapat skor menengah kalau valuasinya kebetulan tampak murah. Karena itu Flag dihitung terpisah dan **tidak** mengurangi Skor; keduanya menjawab pertanyaan berbeda.

| Kode | Arti |
|---|---|
| `ekuitas-` | Ekuitas negatif — kewajiban melebihi seluruh asetnya |
| `rugi` | Masih merugi pada periode terakhir |
| `OCF-` / `FCF-` | Arus kas operasi / arus kas bebas negatif |
| `kas<laba` | Kas operasi kurang dari separuh laba — kualitas laba dipertanyakan |
| `DER>3` | Utang lebih dari tiga kali ekuitas |
| `bunga<1.5` | Laba operasi nyaris tidak menutup beban bunga |
| `laba-30%` | Laba turun lebih dari 30% YoY |
| `dilusi` | Jumlah saham bertambah lebih dari 10% setahun |
| `payout>100` | Dividen melebihi laba — belum tentu bisa dipertahankan |

Flag `OCF-`, `FCF-`, `kas<laba`, dan `DER>3` **dimatikan untuk sektor perbankan** dengan alasan yang sama seperti bobotnya: arus kas operasi bank sering negatif karena penyaluran kredit menyerap kas, dan itu tanda bank sedang tumbuh. Dibiarkan menyala, flag ini akan menandai hampir seluruh sektor dan berhenti berarti.

Saring dengan `--tanpa-flag` (buang yang punya flag apa pun) atau `--kecuali-flag rugi ekuitas-` (buang yang tertentu saja).

Beberapa hal lain soal perhitungannya:

- **Komponen kosong dibuang, bobotnya dibagi ulang** ke komponen lain dalam kategori yang sama. Jadi bank tidak dihukum karena tidak punya current ratio, dan emiten yang belum bagi dividen tidak otomatis kalah dari yang sudah.
- **Kategori yang datanya kurang dari 40% bobotnya dibuang seluruhnya**, dan bobot kategorinya dibagi ulang ke kategori lain.
- **Kalau kategori yang tersisa kurang dari separuh total bobot, skornya dikosongkan** — angka yang disusun dari dua-tiga komponen lebih menyesatkan daripada berguna.
- **PER, PBV, atau EV/EBITDA nol/negatif dihitung 0, bukan dilewati.** PER negatif berarti perusahaannya rugi dan PBV negatif berarti ekuitasnya minus; kalau dilewati, emiten rugi justru diuntungkan karena komponen terburuknya menghilang.
- Seperti Status, Skor **selalu dihitung ulang tiap run** dan tidak dibaca dari CSV lama, jadi mengubah bobot langsung berlaku ke seluruh tabel.

⚠️ **Skor ini juga bukan rekomendasi.** Ia cuma merangkum enam angka — tidak tahu soal kualitas manajemen, prospek industri, atau apakah laba kuartal lalu berasal dari penjualan aset. Skor tinggi dengan Status JUAL artinya perusahaannya bagus tapi harganya sedang turun tren; dua kolom itu menjawab pertanyaan yang berbeda dan sengaja tidak digabung.

Beban utang, likuiditas, margin, dan arus kas **sudah ikut terambil** dan tersimpan di CSV hasil (lihat bagian berikut), hanya belum masuk ke rumus Skor.

## Cache Fundamental

Laporan keuangan cuma berubah empat kali setahun, sedangkan harga berubah tiap hari. Karena itu keduanya diambil terpisah:

| | Kapan | Yang diambil | Skrip |
|---|---|---|---|
| **Fundamental** | Per kuartal | Laba rugi, neraca, arus kas (~20 menit untuk 400 emiten) | `scripts/perbarui_fundamental.py` → `data/fundamental.csv` |
| **Teknikal** | Tiap malam | Histori harga & volume saja | `screener.py` |

```bash
python scripts/perbarui_fundamental.py                 # seluruh universe
python scripts/perbarui_fundamental.py --maks-umur 80  # hanya yang sudah basi
```

Sejak workflow **Fundamental Kuartalan** ada, ini berjalan otomatis di bulan-bulan setelah batas penyampaian laporan ke IDX — April (tahunan audited), Mei (kuartal I), Agustus (semester I), dan November (kuartal III), tiap tanggal 5. Jalankan manual lewat tab Actions → *Fundamental Kuartalan* → *Run workflow* bila ada emiten yang terlambat menyampaikan laporan.

Workflow itu **menolak commit** kalau cache-nya tidak wajar (kurang dari 100 baris, atau kurang dari 70% punya EPS). Skrip mempertahankan baris lama saat satu emiten gagal diambil, jadi kegagalan sebagian tidak terlihat dari exit code — tanpa pemeriksaan ini, Yahoo yang sedang rusak total bisa mendorong cache kosong yang membuat seluruh kolom Skor menghilang malam itu juga.

Sebelumnya `screener.py` menarik `.info` untuk 400-an emiten **tiap malam** hanya demi ROE dan dua angka pertumbuhan — angka yang sama persis selama tiga bulan. Pemisahan ini bukan cuma menghemat request; karena biayanya tidak lagi ditanggung harian, laporan keuangan penuh jadi terjangkau. Yang ikut tersimpan di CSV hasil sekarang: margin kotor/operasi/bersih, ROA, DER, Net Debt/EBITDA, current & quick ratio, interest coverage, OCF/Laba, FCF Yield, payout, CAGR 3 tahun, dan perubahan jumlah saham beredar (dilusi).

Tiga hal yang perlu diketahui soal datanya:

- **Kolom `Basis`** menandai cara angka labanya didapat. `TTM` = empat kuartal berurutan. `TTM-gabungan` = tahun buku terakhir + YTD tahun ini − YTD tahun lalu; ini yang paling sering dipakai, karena bar kuartal September 2025 hilang di hampir semua emiten IDX dan penjumlahan empat kuartal biasa akan menyeberangi lubang itu. `Tahunan` = terpaksa memakai laporan tahunan, jadi bisa beberapa bulan basi.
- **Laporan berdenominasi USD dikonversi ke rupiah.** Banyak emiten batubara, energi, dan sebagian utilitas menyusun laporan keuangannya dalam dolar sementara sahamnya diperdagangkan dalam rupiah. Tanpa konversi, EPS dan harga berasal dari satuan berbeda dan PER meleset ~17.000×: ADRO terbaca 146.821 alih-alih 8,3, dan median PER sektor Energy sempat 155.093. Kolom `MataUang` mencatat mata uang laporan aslinya. Yield dividen tidak ikut dikonversi — `dividendRate` Yahoo memang sudah dalam mata uang perdagangan.
- **Rasio yang tidak berlaku dibiarkan kosong, bukan diisi nol.** Bank tidak memisahkan aset lancar dan tidak melaporkan gross profit maupun EBITDA, jadi current ratio dan Net Debt/EBITDA-nya memang tidak ada. `Net Debt/EBITDA` juga dikosongkan saat EBITDA negatif — penyebut minus membuat utang besar terbaca sebagai rasio kecil yang menyesatkan.
- **`PERvsSektor` dan `PBVvsSektor`** membandingkan valuasi terhadap median sektornya: 1,0 = persis median, 0,7 = 30% lebih murah, 1,4 = 40% lebih mahal. Ini yang membuat valuasi bisa dibaca lintas industri — PBV 2,5 di bank dan PBV 2,5 di emiten batubara bukan hal yang sama. Kosong bila sektornya berisi kurang dari tiga pembanding.

## Selalu Data Penutupan

Kalau screener dijalankan saat bursa masih buka (IDX 09:00–15:50 WIB), **bar hari ini dibuang** dan seluruh tabel dihitung dari penutupan terakhir. Waktunya ditandai lewat baris `Sesi bursa masih berjalan …` di stderr.

Ini bukan kehati-hatian berlebihan. Selama sesi berjalan Yahoo tetap mengirim bar untuk hari ini, tapi isinya baru sebagian hari — dan yang paling merusak adalah volumenya: volume satu jam pertama dibagi rata-rata 20 hari **penuh** membuat `VolSpike` seluruh pasar anjlok ke sekitar seperlima nilai wajarnya. Akibatnya semua filter berbasis volume berhenti meloloskan apa pun, padahal tabelnya tetap terlihat normal. Perbandingan nyata pada 10 Agustus 2026:

| Run | Median VolSpike | Saham dengan VolSpike ≥ 1,2 |
|---|---|---|
| 18:57 WIB, setelah bursa tutup | 0,73 | 88 dari 402 |
| 10:01 WIB, bursa masih buka (tanpa perbaikan) | 0,21 | 16 dari 402 |
| 10:09 WIB, bursa masih buka (dengan perbaikan) | 0,84 | 12 dari 45 (LQ45) |

Ambangnya `JAM_DATA_FINAL` = 16:15 WIB, diberi jeda 25 menit dari penutupan karena Yahoo perlu beberapa menit memperbarui bar terakhirnya. Hari libur bursa tidak perlu didaftar: tanggal dibaca dari bar-nya sendiri, jadi kalau hari ini bursa tutup, bar terakhir bertanggal kemarin dan tidak ada yang dipotong.

Dulu ada satu sisa ketidakkonsistenan di sini: `PER` dan `PBV` datang jadi dari Yahoo yang menghitungnya dari harga berjalan, sementara semua kolom lain sudah dipotong ke penutupan. Sejak kedua rasio itu dihitung sendiri dari EPS dan nilai buku di cache fundamental (lihat [Cache Fundamental](#cache-fundamental)), satu-satunya variabel harian tinggal harga — jadi seluruh tabel kini mengacu ke titik waktu yang sama tanpa kecuali.

## Daftar Ticker

Screening tidak terbatas LQ45. Secara default `screener.py` membaca **semua** file di bawah ini sekaligus:

| File | Grup | Isi |
|---|---|---|
| `tickers/lq45.txt` | `LQ45` | Konstituen indeks LQ45 |
| `tickers/prajogo.txt` | `Prajogo` | Grup Barito / Prajogo Pangestu — BRPT, TPIA, BREN, CUAN, PTRO, CDIA |
| `tickers/bakrie.txt` | `Bakrie` | Grup Bakrie — BNBR, BUMI, BRMS, ENRG, ELTY, DEWA, VKTR, UNSP |
| `tickers/salim.txt` | `Salim` | Grup Salim — INDF, ICBP, SIMP, LSIP, IMAS, IMJS, DNET, MCAS, plus PANI & CBDK (Agung Sedayu–Salim) |
| `tickers/hapsoro.txt` | `Hapsoro` | Terafiliasi Happy Hapsoro — RAJA, RATU, BUVA |
| `tickers/logam.txt` | `Logam` | Logam di luar LQ45 — HRTA (emas), TINS (timah) |
| `tickers/idx.txt` | *(kosong)* | **Universe pasar** — seluruh emiten IDX dengan kapitalisasi di atas 1 triliun (maks. 400 nama terbesar), dihasilkan otomatis oleh `scripts/perbarui_universe.py`. Jangan disunting tangan. |

### Universe otomatis

Daftar kurasi di atas ada supaya kolom `Grup` bermakna, **bukan** untuk membatasi screening. Pembatas sebenarnya adalah `tickers/idx.txt`: daftar itu disusun ulang tiap run malam langsung dari screener Yahoo Finance (`region=id`, urut kapitalisasi terbesar), jadi emiten yang fundamentalnya bagus tetap ikut tersaring walau tidak pernah dimasukkan ke daftar mana pun secara manual — termasuk emiten yang baru IPO atau baru naik kelas.

```bash
python scripts/perbarui_universe.py                    # default: mcap > 1 T, maks 400 nama
python scripts/perbarui_universe.py --min-mcap 0.5 --maks 600   # jaring lebih lebar
```

Ambangnya ada demi runtime: tiap ticker berarti beberapa request ke Yahoo, dan emiten paling kecil praktis tidak bisa ditransaksikan (screener menandainya `TIPIS`). Turunkan `--min-mcap` kalau memang mau menjaring lebih dalam. Kalau pembaruan universe gagal (Yahoo rewel), `tickers/idx.txt` versi commit terakhir tetap dipakai dan screening jalan terus.

Saham dari universe yang tidak ada di daftar kurasi mana pun berlabel `Grup` kosong — itu normal, bukan data hilang.

Duplikat antar-daftar otomatis digabung: saham yang ada di dua daftar hanya diambil datanya sekali dan kolom `Grup`-nya ditulis gabungan, misal INDF → `LQ45/Salim`.

**Format file:** satu ticker per baris, suffix `.JK` opsional, komentar diawali `#` (boleh di belakang ticker). Baris `# grup: Nama` menentukan label grup; kalau tidak ada, dipakai nama file.

**Bikin daftar sendiri:** buat file baru di `tickers/`, lalu jalankan `python screener.py --tickers tickers/punyaku.txt`. Untuk memasukkannya ke run otomatis tiap malam, tambahkan path-nya ke `DAFTAR_DEFAULT` di `screener.py`.

⚠️ Daftar grup konglomerasi disusun dari struktur kepemilikan publik dan **bisa berubah** kalau ada akuisisi/divestasi — cek ulang di keterbukaan informasi IDX sebelum dipakai untuk keputusan beli. Emiten di luar LQ45 juga banyak yang likuiditasnya tipis; pakai `--min-nilai` untuk menyaring yang benar-benar bisa ditransaksikan.

## Otomasi Screening Malam (GitHub Actions)

Workflow [`.github/workflows/screening-malam.yml`](.github/workflows/screening-malam.yml) menjalankan screening otomatis **setiap hari bursa (Senin–Jumat) pukul ±18:17 WIB** — beberapa jam setelah IDX tutup (15:50 WIB), pas untuk pola swing trade: data penutupan dikumpulkan malam ini, keputusan dieksekusi besok pagi.

Setiap malam workflow:

1. Menyusun ulang universe pasar (`tickers/idx.txt`) lewat `scripts/perbarui_universe.py`, supaya emiten baru atau yang naik kelas ikut ter-screening tanpa disebut manual. Kalau langkah ini gagal, universe versi commit terakhir dipakai dan run tetap lanjut.
2. Mengambil data seluruh daftar default (universe IDX + daftar kurasi) dari Yahoo Finance **satu kali**, disimpan ke `hasil/semua.csv` (tabel lengkap tanpa filter).
3. Memfilter ulang dari CSV itu (tanpa fetch ulang, pakai `--dari-csv`) menjadi tiga daftar siap pakai:
   - `hasil/swing.csv` — masih uptrend dan belum overbought, **dengan konfirmasi volume** (RSI ≤ 65, harga di atas MA200, volume terakhir ≥ 1,2× rata-rata 20 hari, nilai transaksi ≥ 5 miliar Rp). Ambang RSI sengaja tidak dipatok 50: `--max-rsi` dan `--min-volspike` saling menggerus, karena volume yang masuk hari ini justru yang mengangkat RSI. Menuntut "harga lagi lemah" sekaligus "volume lagi ramai" menghasilkan tabel kosong hampir tiap malam — bukan sinyal yang lebih tajam, cuma daftar yang tidak pernah terisi.
   - `hasil/value.csv` — value stock profil **medium risk** (PER ≤ 15, PBV ≤ 3,5, ROE ≥ 15%). PBV dipatok 3,5 (bukan 2) supaya blue chip berkualitas yang memang selalu dihargai premium — BBCA, SIDO — tidak otomatis tersaring keluar.
   - `hasil/tumbuh.csv` — **lapkeu terakhir bagus**: laba kuartalan naik ≥ 20% YoY, ROE ≥ 10%, PER ≤ 25, dan nilai transaksi ≥ 1 miliar Rp. Murni saringan fundamental, tanpa syarat teknikal.
4. Meng-commit hasilnya ke repo (termasuk `tickers/idx.txt` yang dipakai malam itu), jadi tiap pagi tinggal buka file-file di folder `hasil/`. Riwayat screening malam-malam sebelumnya tersimpan otomatis di git history.
5. Men-deploy **dashboard web** ke GitHub Pages (lihat di bawah).

**Mengubah kriteria:** edit langkah-langkah screening di file workflow — argumennya sama persis dengan CLI `screener.py`. Mau menambah profil screening ketiga? Duplikat saja salah satu langkah `--dari-csv` dengan filter dan nama output berbeda.

**Menjalankan manual:** buka tab **Actions → Screening Malam → Run workflow** di GitHub, lalu pilih branch-nya.

**Menjalankan dari branch selain branch default:** bisa — screening jalan dan CSV-nya di-commit ke branch itu. Yang dilewati hanya langkah deploy dashboard, karena environment `github-pages` memang dibatasi ke branch default. Job `deploy` di workflow dipisah dari job `screening` justru supaya batasan itu tidak menggagalkan seluruh run (kalau digabung, run dari branch fitur gagal dalam hitungan detik tanpa log sama sekali).

### Dashboard Web

Hasil screening bisa dilihat lewat dashboard di:

**<https://2013tib-droid.github.io/Screening-Saham/>**

Fitur dashboard:

- Tiga tab: **Swing**, **Value**, dan **Semua** (tabel lengkap seluruh saham yang dipantau), plus ringkasan jumlah saham yang lolos tiap filter.
- Kolom **Grup** dan dropdown **filter grup** — bisa lihat khusus saham grup Prajogo, Bakrie, Salim, Hapsoro, atau LQ45 saja.
- Kolom **Status** berwarna (BUY / BOW / HOLD / WSE / JUAL / TIPIS) plus dropdown filter status; klik judul kolomnya untuk mengurutkan dari paling positif ke paling negatif.
- Kolom **Skor** berwarna (hijau ≥ 70, kuning 40–69, merah < 40) — kesimpulan fundamental 1–100; klik judulnya untuk mengurutkan dari fundamental terkuat.
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
