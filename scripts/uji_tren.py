#!/usr/bin/env python3
"""Uji Trend Template, RS, dan breadth di screener.py dengan harga buatan.

Kenapa ada: TT, RS, dan breadth masing-masing berakhir sebagai satu angka
(7 dari 8, RS 84, "62% di atas MA50") yang tampak masuk akal apa pun yang
terjadi di dalamnya. Jendela 52 minggu yang bergeser satu bulan, bar libur
yang ikut terhitung, atau persentil yang dihitung terbalik tidak membuat
angkanya aneh — cuma salah. Jadi semuanya diuji terhadap deret yang
jawabannya sudah diketahui.

Sengaja tanpa jaringan, sama dengan scripts/uji_winrate.py.

Pemakaian:
    python scripts/uji_tren.py        # dari akar repo

Keluar dengan kode 1 bila ada pemeriksaan yang gagal, jadi bisa dipakai di CI.
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from screener import (  # noqa: E402
    KRITERIA_TT, MIN_EMITEN_BREADTH, hitung_breadth, hitung_rs, hitung_tt,
    metrik_tren, tulis_breadth,
)

gagal = 0


def periksa(nama: str, dapat, harap):
    global gagal
    sama = dapat == harap
    if isinstance(harap, float) and isinstance(dapat, (int, float)):
        sama = abs(dapat - harap) < 1e-6
    if harap is None:
        sama = dapat is None or (not isinstance(dapat, str) and pd.isna(dapat))
    if sama:
        print(f"  ok   {nama}")
    else:
        gagal += 1
        print(f"  GAGAL {nama}: dapat {dapat!r}, seharusnya {harap!r}")


# Hari kerja dengan zona waktu Jakarta, seperti indeks yang dikirim yfinance.
def tanggal(n: int, akhir: str = "2026-11-13") -> pd.DatetimeIndex:
    return pd.bdate_range(end=akhir, periods=n, tz="Asia/Jakarta")


def deret(nilai: list[float], akhir: str = "2026-11-13") -> pd.Series:
    return pd.Series(nilai, index=tanggal(len(nilai), akhir), dtype=float)


print("metrik_tren — deret naik linier dua tahun")
n = 520
naik = deret([1000 + 2 * i for i in range(n)])
m = metrik_tren(naik)
periksa("MA150 = rata-rata 150 bar terakhir", m["MA150"], round(naik.tail(150).mean()))
periksa("MA200Lalu = MA200 yang berakhir 22 bar lalu",
        m["MA200Lalu"], round(naik.iloc[:-22].tail(200).mean()))
periksa("Tinggi52 = penutupan terakhir (deretnya terus naik)", m["Tinggi52"], round(naik.iloc[-1]))
setahun_lalu = naik.index[-1] - pd.Timedelta(days=365)
periksa("Rendah52 = bar pertama SESUDAH tepat setahun lalu",
        m["Rendah52"], round(naik[naik.index > setahun_lalu].iloc[0]))
harga_lalu = naik[naik.index <= setahun_lalu].iloc[-1]
periksa("Naik12B% diukur dari penutupan pada/sebelum setahun lalu",
        m["Naik12B%"], round((naik.iloc[-1] / harga_lalu - 1) * 100, 1))
periksa("RSMentah terisi", m["RSMentah"] is not None, True)

print("\nmetrik_tren — emiten baru (200 bar, < setahun)")
baru = metrik_tren(deret([500 + i for i in range(200)]))
periksa("MA150 tetap dihitung", baru["MA150"] is not None, True)
periksa("MA200Lalu kosong (butuh 222 bar)", baru["MA200Lalu"], None)
periksa("Tinggi52 kosong — bukan 'tertinggi sejak IPO'", baru["Tinggi52"], None)
periksa("Naik12B% kosong", baru["Naik12B%"], None)
periksa("RSMentah kosong bila salah satu jendela tak terjangkau", baru["RSMentah"], None)
periksa("deret kosong tidak melempar", metrik_tren(pd.Series(dtype=float))["MA150"], None)

print("\nhitung_rs")
df = pd.DataFrame({"RSMentah": [float(i) for i in range(1, 41)] + [None]})
rs = hitung_rs(df)
periksa("yang terkuat dapat 99", int(rs.iloc[39]), 99)
periksa("yang terlemah dapat round(1/40*99) = 2", int(rs.iloc[0]), 2)
periksa("urutannya searah RSMentah", bool(rs.iloc[:40].is_monotonic_increasing), True)
periksa("RSMentah kosong -> RS kosong", rs.iloc[40], None)
kecil = hitung_rs(pd.DataFrame({"RSMentah": [1.0, 2.0, 3.0]}))
periksa("universe < 30 emiten -> RS kosong semua", bool(kecil.isna().all()), True)
periksa("tanpa kolom RSMentah -> RS kosong",
        bool(hitung_rs(pd.DataFrame({"Ticker": ["A"]})).isna().all()), True)

print("\nhitung_tt")
lolos = {"Harga": 1500, "MA50": 1400, "MA150": 1300, "MA200": 1200, "MA200Lalu": 1150,
         "Tinggi52": 1600, "Rendah52": 1000, "RS": 85}
periksa("delapan kriteria terdaftar", len(KRITERIA_TT), 8)
periksa("baris ideal = 8", hitung_tt(lolos), 8)
periksa("RS 69 -> 7", hitung_tt({**lolos, "RS": 69}), 7)
periksa("RS tepat 70 masih lolos", hitung_tt({**lolos, "RS": 70}), 8)
periksa("tepat 25% di bawah puncak masih lolos", hitung_tt({**lolos, "Tinggi52": 2000}), 8)
periksa("lebih dari 25% di bawah puncak gagal satu", hitung_tt({**lolos, "Tinggi52": 2001}), 7)
periksa("MA200 turun gagal satu", hitung_tt({**lolos, "MA200Lalu": 1250}), 7)
periksa("kurang dari 30% di atas dasar gagal satu", hitung_tt({**lolos, "Rendah52": 1200}), 7)
periksa("harga di bawah MA50 gagal satu", hitung_tt({**lolos, "Harga": 1390, "Tinggi52": 1500}), 7)
periksa("bahan kurang -> None", hitung_tt({**lolos, "MA150": None}), None)
periksa("NaN dari CSV -> None", hitung_tt({**lolos, "RS": float("nan")}), None)
periksa("angka berupa teks (CSV) tetap terbaca", hitung_tt({k: str(v) for k, v in lolos.items()}), 8)
deret_turun = deret([3000 - 3 * i for i in range(n)])
baris_turun = {**metrik_tren(deret_turun), "Harga": round(deret_turun.iloc[-1]),
               "MA50": round(deret_turun.tail(50).mean()),
               "MA200": round(deret_turun.tail(200).mean()), "RS": 5}
periksa("deret turun lurus lolos 0 kriteria", hitung_tt(baris_turun), 0)
baris_naik = {**m, "Harga": round(naik.iloc[-1]), "MA50": round(naik.tail(50).mean()),
              "MA200": round(naik.tail(200).mean()), "RS": 95}
periksa("deret naik lurus (RS 95) lolos 8 kriteria", hitung_tt(baris_naik), 8)


print("\nhitung_breadth")


def emiten(closes, volume=1e7, akhir="2026-11-13"):
    c = deret(closes, akhir)
    return pd.DataFrame({"Close": c, "Volume": [volume] * len(c)}, index=c.index)


seri = {}
for i in range(30):                       # 30 naik, likuid (1.000 x 10 jt = Rp10 M)
    seri[f"N{i}"] = emiten([1000 + i + 2 * k for k in range(n)])
for i in range(10):                       # 10 turun, likuid
    seri[f"T{i}"] = emiten([3000 - i - 3 * k for k in range(n)])
for i in range(20):                       # 20 naik tapi tidur (Rp1 jt/hari) — tidak dihitung
    seri[f"S{i}"] = emiten([1000 + 2 * k for k in range(n)], volume=1)
# Bar libur ala Yahoo: hari Sabtu, harga datar, volume 0, di 5 emiten saja.
libur = pd.Timestamp("2026-11-07", tz="Asia/Jakarta")
for kode in ["N0", "N1", "N2", "T0", "T1"]:
    tambahan = pd.DataFrame({"Close": [seri[kode]["Close"].iloc[-5]], "Volume": [0]}, index=[libur])
    seri[kode] = pd.concat([seri[kode], tambahan]).sort_index()

b = hitung_breadth(seri)
akhir = b.iloc[-1]
periksa("tanggal terakhir", akhir["Tanggal"], "2026-11-13")
periksa("hanya 40 emiten likuid yang dihitung", int(akhir["Emiten"]), 40)
periksa("75% di atas MA50", float(akhir["DiAtasMA50%"]), 75.0)
periksa("75% di atas MA200", float(akhir["DiAtasMA200%"]), 75.0)
periksa("30 tertinggi 52 minggu baru", int(akhir["TinggiBaru"]), 30)
periksa("10 terendah 52 minggu baru", int(akhir["RendahBaru"]), 10)
periksa("bar libur (volume 0) tidak menjadi tanggal", "2026-11-07" in set(b["Tanggal"]), False)
awal = b.iloc[0]
periksa("baris pertama = saat 20 bar nilai transaksi tersedia",
        awal["Tanggal"], tanggal(n)[19].date().isoformat())
periksa("MA200% kosong sebelum 200 bar", awal["DiAtasMA200%"], None)
periksa("tinggi/rendah 52 minggu 0 sebelum histori setahun", int(awal["TinggiBaru"]), 0)
periksa("kolom sesuai urutan", list(b.columns),
        ["Tanggal", "Emiten", "DiAtasMA50%", "DiAtasMA200%", "TinggiBaru", "RendahBaru"])
sedikit = {k: v for k, v in list(seri.items())[:MIN_EMITEN_BREADTH - 1]}
periksa(f"emiten likuid < {MIN_EMITEN_BREADTH} -> kosong", hitung_breadth(sedikit).empty, True)
periksa("tanpa data -> kosong", hitung_breadth({}).empty, True)

print("\ntulis_breadth")
with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "breadth.csv"
    pd.DataFrame([
        {"Tanggal": "2020-01-02", "Emiten": 99, "DiAtasMA50%": 12.3, "DiAtasMA200%": 45.6,
         "TinggiBaru": 1, "RendahBaru": 2},
        {"Tanggal": "2026-11-13", "Emiten": 1, "DiAtasMA50%": 0.0, "DiAtasMA200%": 0.0,
         "TinggiBaru": 0, "RendahBaru": 0},
    ]).to_csv(path, index=False)
    tulis_breadth(str(path), seri)
    hasil = pd.read_csv(path, dtype={"Tanggal": str})
    periksa("baris lama di luar jangkauan histori dipertahankan", hasil["Tanggal"].iloc[0], "2020-01-02")
    periksa("baris yang tercakup histori ditimpa",
            int(hasil.loc[hasil["Tanggal"] == "2026-11-13", "Emiten"].iloc[0]), 40)
    periksa("tidak ada tanggal ganda", bool(hasil["Tanggal"].is_unique), True)
    periksa("jumlah baris = 1 lama + hasil baru", len(hasil), 1 + len(b))
    ukuran = path.stat().st_size
    tulis_breadth(str(path), sedikit)
    periksa("breadth kosong tidak menimpa berkas lama", path.stat().st_size, ukuran)

if gagal:
    print(f"\n{gagal} pemeriksaan gagal.")
    sys.exit(1)
print("\nSemua pemeriksaan lolos.")
