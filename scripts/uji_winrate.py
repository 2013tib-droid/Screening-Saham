#!/usr/bin/env python3
"""Uji simulasi uji_winrate.py dengan harga buatan.

Kenapa ada: hasil uji winrate berupa satu angka persen yang tidak bisa
dicocokkan dengan apa pun. Kalau tanggal belinya bergeser satu hari, atau
biaya jual lupa dipotong, angkanya tetap tampak masuk akal — cuma salah.
Jadi matematikanya diuji terhadap harga yang sudah diketahui jawabannya,
bukan terhadap data pasar.

Harganya sengaja dibuat sendiri, bukan ditarik dari Yahoo: uji yang butuh
jaringan akan gagal karena alasan yang tidak ada hubungannya dengan kodenya,
dan uji yang hasilnya berubah tiap hari tidak bisa memvonis apa-apa.

Pemakaian:
    python scripts/uji_winrate.py        # dari akar repo

Keluar dengan kode 1 bila ada pemeriksaan yang gagal, jadi bisa dipakai di CI.
"""

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from uji_winrate import (  # noqa: E402
    LEMBAR_PER_LOT, WIB, per_emiten, ringkas, simulasi, tanggal_beli,
)

gagal = 0


def periksa(nama: str, dapat, harap):
    global gagal
    if dapat == harap or (isinstance(harap, float) and isinstance(dapat, (int, float))
                          and abs(dapat - harap) < 1e-6):
        print(f"  ok   {nama}")
    else:
        gagal += 1
        print(f"  GAGAL {nama}: dapat {dapat!r}, seharusnya {harap!r}")


def bar(kode: str, mulai: date, closes: list[float], opens: list[float] | None = None):
    """Deret bar harian berturut-turut, satu bar per hari (tanpa akhir pekan).

    Akhir pekan sengaja diabaikan: yang diuji adalah hitungan "hari bursa
    ke-N", dan simulasinya menghitung itu dari urutan bar yang ada, bukan dari
    kalender. Deret rapat justru membuat pergeseran satu bar langsung
    kelihatan.
    """
    opens = opens if opens is not None else closes
    return pd.DataFrame([
        {"Ticker": kode, "Tanggal": (mulai + timedelta(days=i)).isoformat(),
         "Open": o, "High": max(o, c), "Low": min(o, c), "Close": c}
        for i, (o, c) in enumerate(zip(opens, closes))
    ])


print("== Tanggal beli: sesi pertama yang dibuka SESUDAH screening ==")
b = bar("AAAA", date(2026, 3, 2), [100, 101, 102, 103])
# Run malam 18:00 WIB tanggal 2 Maret: sesi 2 Maret sudah tutup, jadi bar
# pertama yang bisa dipakai adalah 3 Maret.
periksa("run malam -> bar besoknya",
        tanggal_beli(b, datetime(2026, 3, 2, 18, 0, tzinfo=WIB)), 1)
# Run pagi 08:00 WIB tanggal 3 Maret: sesi hari itu belum buka, jadi bar
# 3 Maret masih terbeli.
periksa("run pagi -> bar hari itu juga",
        tanggal_beli(b, datetime(2026, 3, 3, 8, 0, tzinfo=WIB)), 1)
# Run 09:30 WIB: sesi sudah telanjur dibuka, harga pembukaannya lewat.
periksa("run saat sesi berjalan -> bar berikutnya",
        tanggal_beli(b, datetime(2026, 3, 3, 9, 30, tzinfo=WIB)), 2)
periksa("cap waktu UTC dikonversi ke WIB",
        tanggal_beli(b, datetime(2026, 3, 2, 11, 0, tzinfo=timezone.utc)), 1)
periksa("screening sesudah bar terakhir -> tidak ada yang bisa dibeli",
        tanggal_beli(b, datetime(2026, 4, 1, 18, 0, tzinfo=WIB)), None)


def riwayat_satu(kode: str, waktu: str) -> pd.DataFrame:
    return pd.DataFrame([{"Tanggal": waktu[:10], "Waktu": waktu, "Ticker": kode,
                          "Nama": kode, "Status": "BUY", "Skor": 70,
                          "HargaScreening": 100}])


print("\n== Pembulatan lot dan modal ==")
# Harga beli 1.000 -> satu lot 100.000 -> 100 lot pas dari modal 10 juta.
harga = per_emiten(bar("BBBB", date(2026, 3, 2), [1000, 1000, 1000]))
p = simulasi(riwayat_satu("BBBB", "2026-03-02T11:00:00Z"), harga,
             modal=10_000_000, hari=1, fee_beli=0.15, fee_jual=0.25)
periksa("lot penuh", int(p["Lot"].iloc[0]), 100)
periksa("lembar", int(p["Lembar"].iloc[0]), 100 * LEMBAR_PER_LOT)
periksa("modal termasuk fee beli", int(p["Modal"].iloc[0]), round(10_000_000 * 1.0015))

# Harga 3.120: satu lot 312.000, modal 10 juta cuma cukup 32 lot (9.984.000).
# Sisanya menganggur — dibulatkan ke bawah, bukan ke atas.
harga = per_emiten(bar("CCCC", date(2026, 3, 2), [3120, 3120, 3120]))
p = simulasi(riwayat_satu("CCCC", "2026-03-02T11:00:00Z"), harga,
             modal=10_000_000, hari=1, fee_beli=0, fee_jual=0)
periksa("lot dibulatkan ke bawah", int(p["Lot"].iloc[0]), 32)
periksa("sisa modal tidak dipakai", int(p["Modal"].iloc[0]), 9_984_000)

# Satu lot lebih mahal daripada modal: posisinya tidak ada, bukan dipaksakan.
harga = per_emiten(bar("DDDD", date(2026, 3, 2), [150_000, 150_000, 150_000]))
p = simulasi(riwayat_satu("DDDD", "2026-03-02T11:00:00Z"), harga,
             modal=10_000_000, hari=1, fee_beli=0, fee_jual=0)
periksa("harga di atas modal satu lot -> dilewati", len(p), 0)


# Harga nol lolos dari dropna: nilainya ada, cuma tidak masuk akal.
harga = per_emiten(bar("EEE0", date(2026, 3, 2), [0, 0, 0]))
p = simulasi(riwayat_satu("EEE0", "2026-03-02T11:00:00Z"), harga,
             modal=10_000_000, hari=1, fee_beli=0, fee_jual=0)
periksa("harga beli nol -> dilewati, tidak membagi nol", len(p), 0)


print("\n== Laba dihitung dari pembukaan, sesudah dua biaya ==")
# Beli di pembukaan 1.000, tutup hari beli 1.000, besoknya 1.100 (+10%).
harga = per_emiten(bar("EEEE", date(2026, 3, 2), [1000, 1000, 1100],
                       opens=[1000, 1000, 1050]))
p = simulasi(riwayat_satu("EEEE", "2026-03-02T11:00:00Z"), harga,
             modal=10_000_000, hari=1, fee_beli=0.15, fee_jual=0.25)
periksa("beli di pembukaan, bukan penutupan", float(p["HargaBeli"].iloc[0]), 1000.0)
periksa("tanggal beli", p["TanggalBeli"].iloc[0], "2026-03-03")
# Hari0 = harga rata, jadi yang tersisa persis kedua biaya:
# (1 - 0,0025) / 1,0015 - 1 = -0,3993%
periksa("hari beli rata harga -> rugi sebesar biaya", float(p["Hari0%"].iloc[0]), -0.4)
# Hari1 = +10% harga: 1,1 * (1 - 0,0025) / 1,0015 - 1 = +9,5606%
periksa("hari berikutnya +10% harga", float(p["Hari1%"].iloc[0]), 9.56)
periksa("Laba% = hari terakhir yang ada datanya", float(p["Laba%"].iloc[0]), 9.56)
periksa("HariKe", int(p["HariKe"].iloc[0]), 1)
periksa("jendela tuntas", p["Selesai"].iloc[0], "Ya")


print("\n== Jendela yang belum tuntas ==")
# Jendela diminta 5 hari, harga cuma tersedia 3 bar sesudah beli.
harga = per_emiten(bar("FFFF", date(2026, 3, 2), [100, 100, 110, 120]))
p = simulasi(riwayat_satu("FFFF", "2026-03-02T11:00:00Z"), harga,
             modal=10_000_000, hari=5, fee_beli=0, fee_jual=0)
periksa("hari yang sudah ada terisi", float(p["Hari2%"].iloc[0]), 20.0)
periksa("hari yang belum sampai dibiarkan kosong", pd.isna(p["Hari3%"].iloc[0]), True)
periksa("posisi berjalan ditandai belum selesai", p["Selesai"].iloc[0], "Tidak")
periksa("HariKe berhenti di data terakhir", int(p["HariKe"].iloc[0]), 2)


print("\n== Puncak dan jatuh terdalam ==")
# Naik dulu ke +30%, lalu balik ke -10%. Laba akhir -10%, tapi pernah +30%.
harga = per_emiten(bar("GGGG", date(2026, 3, 2), [100, 100, 130, 90]))
p = simulasi(riwayat_satu("GGGG", "2026-03-02T11:00:00Z"), harga,
             modal=10_000_000, hari=2, fee_beli=0, fee_jual=0)
periksa("Puncak%", float(p["Puncak%"].iloc[0]), 30.0)
periksa("Jatuh%", float(p["Jatuh%"].iloc[0]), -10.0)
periksa("Laba% tetap nilai akhir", float(p["Laba%"].iloc[0]), -10.0)


print("\n== Ringkasan per hari ke-N ==")
# Tiga posisi: satu menang, satu rugi, satu jendelanya cuma sampai hari 1.
riwayat = pd.concat([riwayat_satu("HHHH", "2026-03-02T11:00:00Z"),
                     riwayat_satu("IIII", "2026-03-02T11:00:00Z"),
                     riwayat_satu("JJJJ", "2026-03-02T11:00:00Z")], ignore_index=True)
harga = per_emiten(pd.concat([
    bar("HHHH", date(2026, 3, 2), [100, 100, 110, 120]),   # +10%, +20%
    bar("IIII", date(2026, 3, 2), [100, 100, 90, 80]),     # -10%, -20%
    bar("JJJJ", date(2026, 3, 2), [100, 100, 105]),        # +5%, lalu habis
], ignore_index=True))
p = simulasi(riwayat, harga, modal=10_000_000, hari=2, fee_beli=0, fee_jual=0)
r = ringkas(p, hari=2).set_index("Hari")
periksa("hari 1: tiga posisi terhitung", int(r.loc[1, "Posisi"]), 3)
periksa("hari 1: dua menang dari tiga", float(r.loc[1, "Winrate%"]), 66.7)
periksa("hari 1: rata-rata (10-10+5)/3", float(r.loc[1, "RataLaba%"]), 1.67)
periksa("hari 1: median", float(r.loc[1, "MedianLaba%"]), 5.0)
# Posisi JJJJ tidak punya hari ke-2, jadi tidak boleh ikut menghitung.
periksa("hari 2: hanya posisi yang sampai situ", int(r.loc[2, "Posisi"]), 2)
periksa("hari 2: winrate dari dua posisi", float(r.loc[2, "Winrate%"]), 50.0)
periksa("hari 2: total rupiah 20% - 20% dari 10 juta", int(r.loc[2, "TotalLabaRp"]), 0)
periksa("hari 2: terbaik", float(r.loc[2, "Terbaik%"]), 20.0)
periksa("hari 2: terburuk", float(r.loc[2, "Terburuk%"]), -20.0)


print("\n== Emiten tanpa data harga ==")
p = simulasi(riwayat_satu("ZZZZ", "2026-03-02T11:00:00Z"),
             per_emiten(bar("AAAA", date(2026, 3, 2), [100, 100])),
             modal=10_000_000, hari=1, fee_beli=0, fee_jual=0)
periksa("dilewati, tidak meledak", len(p), 0)


print()
if gagal:
    print(f"{gagal} pemeriksaan gagal.")
    sys.exit(1)
print("Semua pemeriksaan lolos.")
