# Catatan Serah-Terima: Pengerjaan Tampilan Dashboard

Dokumen ini untuk sesi berikutnya yang mengerjakan sisi tampilan. Isinya keadaan
sekarang, apa yang sudah diverifikasi, dan apa yang belum — supaya tidak perlu
menyusuri ulang riwayatnya.

Terakhir diperbarui: 11 Agustus 2026.

---

## Tugas yang tersisa

**Dashboard baru saja bertambah dari 19 ke 24 kolom, dan belum pernah dilihat
orang di browser sungguhan.** Itu satu-satunya pekerjaan yang tertinggal, dan
memang tidak bisa diselesaikan tanpa mata.

Yang perlu dinilai:

1. **Apakah 24 kolom terlalu sesak?** Tabel dipaksa `min-width: 1640px` di dalam
   pembungkus `overflow-x: auto`, jadi di layar biasa ia menggulir mendatar.
   Kalau terasa berat, kandidat pertama untuk dibuang: `Grup` (informasinya
   sudah ada di dropdown filter), lalu `MA50`/`MA200` (jarang dibaca langsung —
   informasinya sudah terangkum di kolom Status).
2. **Apakah chip red flag terbaca?** Emiten terburuk bisa membawa lima flag
   sekaligus dalam satu sel. Perlu dilihat apakah selnya melebar tidak wajar
   atau chip-nya menumpuk berantakan.
3. **Perilaku di layar sempit / ponsel.** Belum diuji sama sekali.
4. **Apakah pewarnaan sudah membantu, bukan ramai.** Sekarang ada tiga kosakata
   warna sekaligus dalam satu baris: Status (5 warna), Skor (3 pita), dan
   `rel-murah`/`rel-mahal` pada kolom vs-sektor. Mungkin terlalu banyak.

---

## Peta berkas

| Berkas | Isi |
|---|---|
| `dashboard/index.html` | **Seluruh dashboard** — HTML, CSS, dan JS dalam satu berkas. Tidak ada build step, tidak ada dependensi eksternal. |
| `hasil/semua.csv` | 402 emiten, 65 kolom. Sumber data utama. |
| `hasil/swing.csv`, `value.csv`, `tumbuh.csv` | Hasil tersaring, kolomnya sama. |
| `hasil/meta.json` | Stempel waktu pembaruan. |
| `scripts/uji_dashboard.js` | Uji dashboard tanpa browser (lihat di bawah). |

Dashboard mengambil data lewat `fetch` dengan path relatif (`hasil/semua.csv`),
jadi **tidak bisa dibuka dengan `file://`** — harus lewat server.

---

## Cara menjalankan dan menguji

```bash
# 1. Sajikan secara lokal (dashboard butuh HTTP, bukan file://)
mkdir -p _site && cp dashboard/index.html _site/ && cp -r hasil _site/
cd _site && python -m http.server 8899
# lalu buka http://localhost:8899/

# 2. Uji tanpa browser — menjalankan JS dashboard yang sebenarnya di Node
node scripts/uji_dashboard.js
```

`scripts/uji_dashboard.js` menjalankan JavaScript dashboard yang **sebenarnya**
di Node dengan DOM tiruan, lalu memeriksa HTML tabel yang keluar: jumlah baris
cocok dengan data, setiap kolom yang dideklarasikan benar-benar ada di CSV,
tidak ada `undefined`/`NaN`/tanda kutip yang bocor ke halaman, dan jumlah chip
red flag cocok dengan jumlah flag di data. Keluar dengan kode 1 bila ada yang
gagal.

Yang **tidak** bisa ditangkapnya: apa pun soal tampilan. Itu justru pekerjaan
yang tersisa.

---

## Struktur JS dashboard

Tiga hal yang perlu diketahui sebelum menyunting:

**1. Parser bekerja berdasarkan nama kolom, bukan posisi.** `parseCSV` membangun
objek dari baris header, jadi menambah kolom di CSV tidak akan menggeser apa pun.
Ini sebabnya CSV yang membengkak dari 19 ke 65 kolom tidak merusak dashboard.

**2. Kolom yang ditampilkan ditentukan array `KOLOM`.** Menambah/membuang kolom
cukup menyunting array itu; header, sel, dan pengurutan mengikuti sendiri.
Properti `angka: true` membuatnya diurut secara numerik, `desimal: N` mengatur
format, `relatif: true` menyalakan pewarnaan murah/mahal.

**3. CSV punya 65 kolom, `KOLOM` cuma menampilkan 24.** Sisanya tetap terbawa di
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

Lima yang baru: **Sektor, Flag, PERvsSektor, PBVvsSektor, DER**.

- **Flag** — red flag dirender sebagai deretan label kecil (`.flag`). Nilainya di
  CSV berupa teks dipisah koma, mis. `rugi,FCF-`. Kosong → tanda hubung.
- **PERvsSektor / PBVvsSektor** — rasio terhadap median sektornya sendiri.
  1,00 = persis median; < 0,85 diwarnai `rel-murah`, > 1,15 `rel-mahal`.
- **Skor** — pita warna di 65 dan 50 (Good ke atas / Average / Weak-Poor).

---

## Yang sudah diverifikasi (tidak perlu diulang)

- 24 kolom terender, seluruhnya cocok dengan header CSV, di keempat tab.
- 402 baris di tab "semua"; jumlah baris cocok dengan data di semua tab.
- 472 chip red flag pada 228 emiten — jumlahnya cocok persis dengan data.
- Emiten tanpa data fundamental sama sekali (mis. `WBSA`) turun anggun jadi
  tanda hubung, tidak memunculkan `NaN` atau `undefined`.
- Situs live sudah memakai versi ini — dicek langsung ke
  https://2013tib-droid.github.io/Screening-Saham/

---

## Hal yang mudah membuat bingung

**Perubahan dashboard tidak langsung tampil di situs.** Job `deploy` di
`.github/workflows/screening-malam.yml` dijaga
`if: github.ref_name == github.event.repository.default_branch`. Push ke branch
fitur **tidak** menerbitkan ulang situs — itu disengaja, supaya branch percobaan
tidak menimpa dashboard publik. Situs baru berubah setelah merge ke branch
default dan run malam berikutnya jalan (18:17 WIB, Senin–Jumat), atau dipicu
manual lewat Actions → Screening Malam → Run workflow.

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

Baru saja selesai dikerjakan (sudah merge):

- **`scripts/perbarui_fundamental.py`** — menarik laporan keuangan kuartalan ke
  `data/fundamental.csv`. Jalan per kuartal, bukan tiap malam.
- **`screener.py`** — tiap malam hanya mengambil histori harga, lalu
  menggabungkannya dengan cache fundamental. Skor fundamental disusun dari lima
  kategori berbobot dengan penyesuaian per sektor, plus kolom `Flag`.
- **`analisa.py TICKER`** — laporan Markdown lengkap satu emiten. Belum punya
  antarmuka apa pun di dashboard; **ini kandidat kuat untuk pekerjaan tampilan
  berikutnya** (mis. tombol "analisa" per baris).

Penjelasan lengkap tiap kolom ada di `README.md` bagian *Kolom Skor* dan
*Cache Fundamental*, dan juga di dalam dashboard sendiri pada bagian
"Arti kolom & cara pakai".

---

## Utang teknis yang diketahui

- **Run terjadwal #29 (10 Agu) gagal** di langkah "Commit hasil" dengan
  `exit code 1`, padahal commit-nya terbukti sampai ke remote. Sebabnya belum
  terdiagnosis — unduhan log Actions butuh autentikasi. Sudah ada penanggulangan
  (push dicoba 3× dengan rebase saat ditolak) di PR terpisah, tapi itu menangani
  kelas kegagalannya, bukan sebab yang sudah dipastikan.
- **`gh` CLI belum terpasang** di mesin ini dan tidak ada `GH_TOKEN`, jadi PR
  harus dibuat manual lewat browser dan log Actions tidak bisa dibaca dari sesi.
  `winget install GitHub.cli` lalu `gh auth login` akan menghilangkan hambatan
  ini.
