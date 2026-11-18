# Catatan Serah-Terima: Pengerjaan Tampilan Dashboard

Dokumen ini untuk sesi berikutnya yang mengerjakan sisi tampilan. Isinya keadaan
sekarang, apa yang sudah diverifikasi, dan apa yang belum — supaya tidak perlu
menyusuri ulang riwayatnya.

Terakhir diperbarui: 18 November 2026, sesudah tampilan ponsel (360px)
diperiksa dan dirapikan.

---

## Tugas yang tersisa

**Tampilan ponsel sudah dilihat (18 November 2026)** lewat screenshot Playwright
di lebar 360px dan 1280px, untuk `index.html` maupun `winrate.html`. Yang
ditemukan dan diperbaiki (semuanya di dalam `@media (max-width: 640px)`, jadi
layar lebar tidak berubah):

1. **Kolom Nama memakan lebih dari separuh layar**, sehingga sesudah ticker
   tidak ada satu pun angka yang terlihat. Di layar sempit kolom itu
   disembunyikan (`kol-nama`) dan namanya muncul kecil di bawah ticker, di
   kolom yang lengket (`nama-mini`, terpotong `…` di 112px). Berlaku di kedua
   halaman.
2. **Grup, Sektor, dan Syariah mengisi layar pertama tabel** di `index.html`.
   Di layar sempit `kolomTampil()` memindahkannya ke belakang Harga
   (`geserLabelKeBelakang`), jadi Status, Skor, Red flag, dan Harga yang
   terlihat duluan. Melewati batas 640px memicu render ulang lewat
   `matchMedia`.
3. **Tujuh kartu angka makan ±470px** sebelum tabel. Di layar sempit kartunya
   hanya label + angka (`.sub` disembunyikan); kriterianya tetap ada di
   "Arti kolom". Tinggi halaman turun dari 1996px ke 1692px.
4. **Dropdown filter bertumpuk tidak rata.** Sekarang dua per baris, kotak
   cari selebar penuh.

Tidak ada overflow horizontal di 360px pada kedua halaman, dan tidak ada
galat JS. Dua bilah pagination (geser kolom + nomor halaman) ternyata masih
wajar di 360px, jadi dibiarkan.

Yang **belum** dilihat: perangkat sungguhan (sentuhan, geser dengan jari,
keyboard virtual yang menutupi kotak cari). Mode gelap di 360px sudah dicek lewat screenshot dan terbaca baik.

**Panel rincian per emiten sudah ada (18 November 2026).** Klik/Enter pada
baris membuka `<dialog id="rincian">`; isinya disusun `htmlRincian()` dari
baris `semua.csv`, `hasil/analisa.json` (ditulis `analisa.py --semua-json`
di run malam, diambil malas saat panel pertama dibuka), `swing_smc.csv`, dan
`swing_broker.csv`. Dibuka lewat hash (`#BBCA`) supaya tombol Kembali di
ponsel menutupnya dan tautannya bisa dibagikan. Di ≤ 640px dialognya layar
penuh. Diperiksa lewat screenshot di 1280px dan 360px, terang dan gelap;
`uji_dashboard.js` merender panel untuk ke-402 emiten (dengan dan tanpa
analisa.json) dan memeriksa tidak ada `undefined`/`NaN`/`null` yang bocor.

Yang belum: teks asumsi nilai wajar dan pengurang keyakinan masih berformat
angka Inggris (`2,307.19`, `12.1x`) karena kalimatnya disusun Python dan
juga dipakai laporan Markdown. Ada di dalam `<details>` yang tertutup, jadi
jarang terlihat.

---

## Peta berkas

| Berkas | Isi |
|---|---|
| `dashboard/index.html` | **Seluruh dashboard** — HTML, CSS, dan JS dalam satu berkas. Tidak ada build step, tidak ada dependensi eksternal. |
| `dashboard/winrate.html` | Halaman uji winrate, berdiri sendiri dengan pola yang sama. Token warnanya **disalin utuh** dari `index.html`, tidak dipisah ke CSS bersama — dua berkas statis tanpa build step, dan satu permintaan jaringan tambahan cuma untuk 60 baris variabel membuat halaman berkedip tanpa gaya saat dimuat. Konsekuensinya: kalau paletnya berubah, keduanya harus ikut diubah. |
| `hasil/semua.csv` | 402 emiten, 65 kolom. Sumber data utama. |
| `hasil/swing.csv`, `value.csv`, `tumbuh.csv` | Hasil tersaring, kolomnya sama. |
| `hasil/winrate.csv` | Satu baris per posisi uji winrate, plus kolom `Hari0%`–`Hari21%`. |
| `hasil/winrate_meta.json` | Parameter simulasi winrate (modal, biaya, panjang jendela). |
| `hasil/winrate_pembanding.csv` | IHSG dan saham acak per **tanggal beli** (`IHSG0%`–`IHSG21%`, `Acak0%`–`Acak21%`, `IHSGdiAtasMA50`). `winrate.html` menyambungkannya ke tiap posisi lewat `TanggalBeli` saat memuat; berkasnya opsional — tanpa itu kartu selisih menulis "pembanding belum tersedia" dan grafik cuma bergaris satu. |
| `hasil/analisa.json` | Ringkasan `analisa.py` per emiten (skor kategori, nilai wajar, kekuatan/kelemahan, flag, keyakinan, rekomendasi) untuk panel rincian. Diambil saat panel pertama dibuka. Opsional: tidak ada = panel tetap tampil dengan angka dari CSV saja. |
| `hasil/pasar.json` | IHSG vs MA50/MA200 untuk bilah kondisi pasar di `index.html`. Opsional: tidak ada = bilah tersembunyi. Tanggalnya dibandingkan dengan `meta.json`; tertinggal > 4 hari = bilah netral "belum diperbarui". |
| `hasil/meta.json` | Stempel waktu pembaruan. |
| `scripts/uji_dashboard.js` | Uji dashboard tanpa browser (lihat di bawah). Hanya `index.html`. |
| `_site/` | Folder staging pratinjau lokal. **Masuk `.gitignore`** — jangan di-commit; workflow menyusunnya sendiri di runner. |

Dashboard mengambil data lewat `fetch` dengan path relatif (`hasil/semua.csv`),
jadi **tidak bisa dibuka dengan `file://`** — harus lewat server.

---

## Cara menjalankan dan menguji

```bash
# 1. Sajikan secara lokal (dashboard butuh HTTP, bukan file://)
mkdir -p _site && cp dashboard/index.html dashboard/winrate.html _site/ && cp -r hasil _site/
cd _site && python -m http.server 8899
# lalu buka http://localhost:8899/ dan http://localhost:8899/winrate.html

# 2. Uji tanpa browser — menjalankan JS dashboard yang sebenarnya di Node
node scripts/uji_dashboard.js
```

`uji_dashboard.js` **belum** menjangkau `winrate.html`: harnessnya dibangun di
sekitar variabel global `index.html` (KOLOM, state, render) dan halaman winrate
punya kumpulan sendiri. Yang sudah diuji dari halaman itu cuma sisi datanya,
lewat `python scripts/uji_winrate.py`. Grafik dan tata letaknya sampai sekarang
diperiksa dengan mata, di browser.

**Periksa dulu port 8899 tidak dipegang server sisa sesi sebelumnya.** Ini sudah
memakan waktu sekali: `python -m http.server` yang masih hidup dari sesi lama
tetap memegang port, server baru gagal bind tanpa pesan yang terlihat, dan
browser dilayani salinan lama — sehingga perubahan tampak "tidak berlaku"
padahal berkasnya sudah benar.

```powershell
Get-NetTCPConnection -LocalPort 8899 -State Listen |
  ForEach-Object { Get-Process -Id $_.OwningProcess }
```

Cara tercepat memastikan yang tersaji versi terbaru: bandingkan ukuran berkas.
Versi sekarang ±48 KB; kalau yang terkirim ±28 KB, itu salinan lama.

`scripts/uji_dashboard.js` menjalankan JavaScript dashboard yang **sebenarnya**
di Node dengan DOM tiruan, lalu memeriksa HTML tabel yang keluar. Ada 30
pemeriksaan dalam dua kelompok:

- **Kelengkapan data** (per tab) — jumlah baris cocok dengan data, setiap kolom
  yang dideklarasikan benar-benar ada di CSV, tidak ada `undefined`/`NaN`/tanda
  kutip yang bocor, jumlah chip red flag cocok dengan data. Kelompok ini
  **mematikan pagination dulu** (`state.perHal = 0`) supaya yang diperiksa
  seluruh 402 baris, bukan sepuluh baris pertama.
- **Perilaku pagination** (`ujiPagination`) — halaman penuh berisi persis
  `perHal` baris, halaman terakhir berisi sisanya, halaman berbeda isinya
  berbeda, halaman di luar jangkauan dijepit alih-alih mengosongkan tabel, dan
  pilihan "Semua" mengembalikan seluruh baris.

Keluar dengan kode 1 bila ada yang gagal.

Yang **tidak** bisa ditangkapnya: apa pun soal tampilan. Itu justru pekerjaan
yang tersisa.

---

## Struktur JS dashboard

Empat hal yang perlu diketahui sebelum menyunting:

**1. Parser bekerja berdasarkan nama kolom, bukan posisi.** `parseCSV` membangun
objek dari baris header, jadi menambah kolom di CSV tidak akan menggeser apa pun.
Ini sebabnya CSV yang membengkak dari 19 ke 65 kolom tidak merusak dashboard.

**2. Kolom yang ditampilkan ditentukan array `KOLOM`.** Menambah/membuang kolom
cukup menyunting array itu; header, sel, dan pengurutan mengikuti sendiri.
Properti `angka: true` membuatnya diurut secara numerik, `desimal: N` mengatur
format, `relatif: true` menyalakan pewarnaan murah/mahal, `kiri: true` membuat
selnya rata kiri.

**3. `KELOMPOK` memotong 24 kolom jadi himpunan yang lebih kecil.** Objek itu
memetakan nama kelompok ke daftar kunci kolom; `JANGKAR` (Ticker, Nama, Status,
Skor) selalu ikut di kelompok mana pun supaya barisnya tetap bisa dikenali.
Menambah kelompok baru = satu entri di `KELOMPOK` plus satu `<option>` di
`#kelompok`. Fungsi `kolomTampil()` yang menggabungkan keduanya, dan `render`
memakai hasilnya — bukan `KOLOM` langsung.

**4. CSV punya 65 kolom, `KOLOM` cuma menampilkan 24.** Sisanya tetap terbawa di
objek datanya dan bisa dipakai kapan saja tanpa mengubah pipeline — termasuk
skor per kategori (`SkorValuasi`, `SkorProfitabilitas`, `SkorKesehatan`,
`SkorPertumbuhan`, `SkorArusKas`), margin, arus kas, dan angka absolut dalam
rupiah. **Ini bahan mentah paling menjanjikan untuk perbaikan tampilan** —
misalnya panel rincian saat baris diklik, atau bar kecil lima kategori.

---

## Kolom yang ditampilkan sekarang

```
Ticker, Nama, Grup, Sektor, Status, Skor, Flag, Harga, PER, PBV,
PERvsSektor, PBVvsSektor, ROE%, DER, LabaYoY%, OmzetYoY%, Dividen%,
MarketCap(T), Vol20(jt), Nilai(M), VolSpike, RSI14, MA50, MA200
```

- **Flag** — red flag dirender sebagai deretan label kecil (`.flag`). Nilainya di
  CSV berupa teks dipisah koma, mis. `rugi,FCF-`. Kosong → tanda hubung.
- **PERvsSektor / PBVvsSektor** — rasio terhadap median sektornya sendiri.
  1,00 = persis median; < 0,85 diwarnai `rel-murah`, > 1,15 `rel-mahal`.
- **Skor** — pita warna di 65 dan 50 (Good ke atas / Average / Weak-Poor).
- **RSI14 / VolSpike** — angkanya sendiri yang diwarnai (`.nilai`), bukan diberi
  label teks di sampingnya. Lihat bagian berikutnya.

---

## Keputusan tampilan yang sudah diambil (dan alasannya)

Empat pertanyaan yang tercatat di versi sebelumnya sebagai "belum pernah dilihat
orang" sekarang sudah terjawab di browser sungguhan.

**24 kolom memang terlalu sesak — tapi solusinya bukan membuang kolom.**
Rencana lama adalah mengorbankan `Grup`, lalu `MA50`/`MA200`. Yang dikerjakan
justru tiga hal yang membuat 24 kolom tetap terpakai:

- `.wrap` tidak lagi dibatasi lebar (dulu 1080px). Batas itu adalah sumber
  masalah yang sebenarnya: tabelnya butuh 1680px sementara halamannya
  membatasi diri di 1080px, jadi di monitor lebar ada ruang kosong menganggur
  di kiri-kanan **justru ketika** tabelnya terpaksa menggulir.
- Bilah geser kolom (◀ ▶ plus ruas yang bisa diklik) di bawah tabel, dan kolom
  Ticker dibuat lengket di tepi kiri supaya baris tidak kehilangan identitas
  sejauh apa pun digeser.
- Dropdown kelompok kolom, yang memotong tabel jadi 12–14 kolom yang memang
  dibaca bersamaan. `min-width` tabel ikut turun ke 1040px saat kolomnya ≤ 14
  (kelas `.sempit`), supaya tidak tersisa gulir mendatar yang percuma.

**Chip red flag terbaca dengan baik.** Emiten dengan empat sampai lima flag
tidak melebarkan selnya secara tidak wajar; labelnya membungkus rapi.

**Kosakata warna tidak jadi bertambah, malah berkurang satu.** RSI dan VolSpike
dulu menempelkan label teks `overbought` / `spike` di samping angkanya. Label
itu melebarkan kolom hampir dua kali lipat dan **cuma muncul di sebagian
baris**, sehingga angka di kolom yang sama tidak lagi sejajar — cacat yang baru
kelihatan setelah dibuka di browser. Sekarang angkanya sendiri yang diwarnai
(`.nilai.n-panas` merah untuk RSI ≥ 70, `.n-dingin` biru untuk ≤ 30,
`.n-spike` biru untuk VolSpike ≥ 1,5) dengan `title` sebagai penjelasnya.
Tidak ada informasi yang hilang: ambang 70/30 sudah terbaca dari angkanya
sendiri, warnanya cuma menyorot. Zona tengah sengaja dibiarkan polos — kalau
setiap angka diwarnai, tidak ada satu pun yang menonjol.

**Pagination baris dibatasi 10.** Tab "semua" berisi 402 emiten dalam satu
halaman yang tidak ada yang membacanya sampai bawah. Bisa diubah ke 25/50/semua
lewat dropdown. Filter, pencarian, dan **pengurutan** semuanya mengembalikan ke
halaman 1; yang terakhir itu penting, karena setelah mengurutkan yang dicari
orang adalah baris teratas, bukan halaman 7 dari urutan yang lama.

---

## Yang sudah diverifikasi (tidak perlu diulang)

- 24 kolom terender, seluruhnya cocok dengan header CSV, di keempat tab.
- 402 baris di tab "semua"; jumlah baris cocok dengan data di semua tab.
- 472 chip red flag pada 228 emiten — jumlahnya cocok persis dengan data.
- Emiten tanpa data fundamental sama sekali (mis. `WBSA`) turun anggun jadi
  tanda hubung, tidak memunculkan `NaN` atau `undefined`.
- Pagination: halaman penuh, halaman terakhir (2 baris dari 41 halaman),
  halaman di luar jangkauan, dan pilihan "Semua".
- Tampilan di monitor lebar sudah dilihat langsung di browser.
- Situs live sudah memakai versi ini — dicek langsung ke
  https://2013tib-droid.github.io/Screening-Saham/ (±48 KB).

---

## Hal yang mudah membuat bingung

**Branch default repo ini bukan `main`.** Namanya
`claude/indo-stock-screener-98kizz`, dan tidak ada branch `main` sama sekali.
Pastikan dengan `git ls-remote --symref origin HEAD` sebelum bicara soal
"merge ke main". Ini penting karena job `deploy` dijaga
`if: github.ref_name == github.event.repository.default_branch`.

**Push ke branch default langsung memicu run penuh.** Trigger `push` di
`screening-malam.yml` tidak menyaring path, jadi mengubah dokumen saja tetap
menjalankan penarikan data 400 emiten plus deploy. Tidak berbahaya, hanya
berisik — kalau mengganggu, tambahkan `paths-ignore` pada trigger itu.

**Berkas `hasil/*.csv` ikut di-track git.** Karena run malam meng-commit-nya,
branch yang menganggur melewati satu run malam akan bentrok di berkas itu.
Resolusinya bukan memilih salah satu sisi, melainkan menghasilkan ulang dengan
pipeline terkini. Ini sudah terjadi sekali.

**Jangan pakai emoji di keluaran Python.** Terminal Windows di mesin ini
ber-codepage bukan UTF-8; karakter di luar ASCII berubah jadi tanda tanya.
Karena itu kode red flag berupa teks singkat (`rugi`, `OCF-`), bukan 🚩. Di HTML
emoji aman.

---

## Konteks: dari mana angkanya datang

- **`scripts/perbarui_fundamental.py`** — menarik laporan keuangan kuartalan ke
  `data/fundamental.csv`. Jalan per kuartal, bukan tiap malam.
- **`screener.py`** — tiap malam hanya mengambil histori harga, lalu
  menggabungkannya dengan cache fundamental. Skor fundamental disusun dari lima
  kategori berbobot dengan penyesuaian per sektor, plus kolom `Flag`.
- **`analisa.py TICKER`** — laporan Markdown lengkap satu emiten.
  `analisa.py --semua-json hasil/analisa.json` menulis ringkasannya untuk
  seluruh emiten, yang dibaca panel rincian dashboard.

Penjelasan lengkap tiap kolom ada di `README.md` bagian *Kolom Skor* dan
*Cache Fundamental*, dan juga di dalam dashboard sendiri pada bagian
"Arti kolom & cara pakai".

---

## Utang teknis yang diketahui

- **Tiga run malam menerbitkan dashboard nyaris kosong sambil berstatus
  `success` (27, 28, 31 Agu 2026).** Situs live hanya berisi 4 dari 402 emiten,
  dan ketiga tab filter kosong total — yang tampak dari luar seperti "bug
  dashboard", padahal dashboard-nya benar dan datanya yang hilang.

  Sebabnya `round(close.iloc[-1])` di `ambil_histori`: kalau Yahoo mengirim
  Close NaN, `round()` melempar `cannot convert float NaN to integer`, dan
  `except` di bawahnya membuang **seluruh emiten** itu, bukan cuma bar yang
  cacat. Log run 33422515940 memuat error itu 398 kali. Kenapa Yahoo mengirim
  NaN ke runner GitHub sejak 27 Agu belum dipastikan — yfinance 1.7.0 (versi
  yang dipasang CI) maupun 1.4.1 sama-sama menarik BBCA/ASII/TLKM dengan bersih
  dari mesin lokal, jadi ini perbedaan lingkungan, bukan regresi library.

  Sudah diperbaiki di dua lapis: baris ber-Close NaN dibuang sebelum dihitung
  (satu bar cacat tidak lagi menghapus sahamnya), dan `--min-panen` (default
  0,8) menggagalkan run bila emiten yang dapat harga kurang dari 80% —
  sehingga CSV rusak tidak pernah ter-commit dan data bagus sebelumnya tetap
  tersaji. Versi di `requirements.txt` juga dipin supaya CI dan mesin lokal
  tidak diam-diam memasang yfinance yang berbeda.

  Pelajaran yang lebih umum: **`except Exception` sekeliling satu emiten itu
  murah untuk kegagalan yang jarang, dan berbahaya untuk kegagalan yang
  serempak.** Yang membuat ini tidak ketahuan selama lima hari bukan bug-nya,
  melainkan tidak adanya satu pun langkah yang memeriksa apakah panennya wajar.

- **Job `deploy` pernah menggantung `queued` berjam-jam, dua kali berturut-turut,
  tanpa sebab yang ditemukan.** Run #33 (1j 31m) dan #34 (2j 8m), keduanya
  dengan job `screening` yang sukses normal dalam ~90 detik di runner yang sama.
  Yang sudah diperiksa lewat API dan **semuanya bersih**: `build_type` Pages
  sudah `workflow` (bukan "deploy from a branch"), `pending_deployments` kosong
  (bukan menunggu approval), deployment branch policy berisi persis branch
  default, tidak ada deployment lama yang nyangkut, repo publik dan tidak
  archived/disabled, dan tidak ada run lain yang memegang concurrency group.
  Run #32 sebelumnya sukses penuh dalam 1m47s dengan versi actions yang sama,
  dan perubahan repo sesudahnya tidak menyentuh workflow — jadi tidak ada
  perubahan di repo yang bisa menjelaskannya.

  **Penawarnya: batalkan run yang macet, lalu jalankan ulang.** Run #35
  (`workflow_dispatch`, commit dan workflow identik dengan #34) sukses dalam
  1m51s. Perlu dicatat jujur bahwa yang berhasil adalah penawarnya, bukan
  perbaikan atas sebab yang terdiagnosis. Kalau terulang, baca log runner
  **saat kejadian** — bukan sesudahnya seperti hari ini.

  Ingat juga concurrency group `tulis-repo` dengan `cancel-in-progress: false`:
  satu run yang macet menahan semua run berikutnya di status `pending`. Jadi run
  yang macet bukan cuma gagal sendiri, ia memblokir antrean.

- **Run terjadwal #29 (10 Agu) gagal** di langkah "Commit hasil" dengan
  `exit code 1`, padahal commit-nya terbukti sampai ke remote. Sebabnya belum
  terdiagnosis. Sudah ada penanggulangan (push dicoba 3× dengan rebase saat
  ditolak), tapi itu menangani kelas kegagalannya, bukan sebab yang dipastikan.
  Sekarang log-nya sudah bisa dibaca — lihat di bawah.

---

## `gh` CLI sudah terpasang

Hambatan yang tercatat di versi sebelumnya ("`gh` belum terpasang, PR harus
lewat browser, log Actions tidak terbaca") **sudah hilang**. Terpasang v2.97.0
dan sudah login sebagai `2013tib-droid`; token tersimpan di Windows keyring
sehingga bertahan lintas sesi, dengan scope `repo`, `workflow`, `read:org`,
`gist`. Endpoint billing butuh scope `user` yang belum diberikan — tidak
relevan, repo ini publik jadi menit Actions-nya gratis.

Cara pasangnya, kalau perlu diulang di mesin lain: **wajib menyebut source
`winget` secara eksplisit.**

```powershell
winget install --id GitHub.cli -e --source winget --scope user
```

Tanpa `--source winget`, winget juga menyisir source `msstore`, yang di jaringan
ini gagal dengan `0x8a15005e: The server certificate did not match any of the
expected values` (khas jaringan yang meng-inspeksi TLS). Winget lalu berhenti
karena hasilnya jadi ambigu, dan pesan errornya tidak menyebut bahwa cukup
memilih salah satu source. `--scope user` menghindari prompt UAC.

Sesudah instalasi, **shell yang sudah terbuka tidak akan menemukan `gh`** —
PATH-nya salinan lama dari saat shell itu dibuka. Buka jendela baru, atau muat
ulang di tempat:

```powershell
$env:Path = [Environment]::GetEnvironmentVariable("Path","User") + ";" +
            [Environment]::GetEnvironmentVariable("Path","Machine")
```

Catatan: winget melaporkan "Command line alias added: gh", tapi
`WinGet\Links\gh.exe` tidak benar-benar dibuat. Yang dipakai adalah direktori
`WinGet\Packages\GitHub.cli_*\bin` yang ditambahkan ke PATH user.

Perintah yang berguna untuk menelusuri kemacetan seperti di atas:

```bash
gh run list --repo 2013tib-droid/Screening-Saham --limit 10
gh run view <run-id> --log            # <run-id>, bukan nomor run
gh run cancel <run-id>
gh workflow run "Screening Malam" --ref claude/indo-stock-screener-98kizz
gh api repos/2013tib-droid/Screening-Saham/pages
gh api repos/2013tib-droid/Screening-Saham/actions/runs/<run-id>/pending_deployments
```

`gh run view` menerima **run ID** (angka panjang dari `gh run list`), bukan nomor
run yang tampil di halaman Actions. `gh run view 34` akan menjawab 404.
