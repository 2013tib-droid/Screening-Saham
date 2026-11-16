#!/usr/bin/env python3
"""Uji uji_ulang_tren.py dengan harga buatan.

Kenapa ada: uji ulang menghitung ulang kolom screener.py (MA, RSI, RS, TT)
untuk tiap tanggal sekaligus, dalam bentuk vektor. Kesalahan yang paling
mahal di sana justru yang tidak kelihatan: rolling yang melihat satu bar ke
depan, RS yang diperingkat terhadap universe hari ini alih-alih universe
tanggal itu, atau satu syarat TT yang terbalik. Hasilnya tetap tabel yang
tampak masuk akal — cuma salah.

Jadi tiap angka dicocokkan dengan fungsi screener.py yang SEBENARNYA,
dijalankan atas histori yang dipotong di tanggal itu: kalau versi vektornya
sama dengan screener yang hanya melihat masa lalu, ia tidak melihat masa
depan. Portofolio diuji terhadap deret yang hasilnya bisa dihitung tangan.

Sengaja tanpa jaringan, sama dengan scripts/uji_winrate.py dan uji_tren.py.

Pemakaian:
    python scripts/uji_ulang_tren.py        # dari akar repo

Keluar dengan kode 1 bila ada pemeriksaan yang gagal.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))

from screener import hitung_rs, hitung_rsi, hitung_tt, metrik_tren  # noqa: E402
from uji_ulang_tren import (  # noqa: E402
    ATURAN, Pasar, indikator, metrik_ekuitas, pasar_di_atas_ma, portofolio,
    ringkas_sinyal, sinyal, tabel_harian,
)
from uji_winrate import KODE_IHSG, per_emiten, simulasi  # noqa: E402

gagal = 0


def periksa(nama: str, dapat, harap, toleransi: float = 1e-6):
    global gagal
    kosong = lambda v: v is None or (isinstance(v, float) and np.isnan(v))  # noqa: E731
    if kosong(harap):
        sama = kosong(dapat)
    elif isinstance(harap, (int, float)) and isinstance(dapat, (int, float, np.number)):
        sama = not kosong(dapat) and abs(float(dapat) - float(harap)) <= toleransi
    else:
        sama = dapat == harap
    if sama:
        print(f"  ok   {nama}")
    else:
        gagal += 1
        print(f"  GAGAL {nama}: dapat {dapat!r}, seharusnya {harap!r}")


# ---------------------------------------------------------------- data buatan
# 45 emiten, ~2,5 tahun hari kerja. Sebagian naik bertahap (supaya ada yang
# lolos TT 8/8), sebagian turun, sisanya acak. Satu emiten baru "IPO" di
# tengah jalan, satu disuspensi tiga minggu, satu tidak likuid.
rng = np.random.default_rng(7)
TGL = pd.bdate_range("2023-06-01", "2025-12-31")
STR = [t.date().isoformat() for t in TGL]


def emiten(kode, closes, volume, mulai=0, bolong=()):
    closes = np.asarray(closes, dtype=float)
    opens = closes * (1 + rng.normal(0, 0.003, len(closes)))
    df = pd.DataFrame({"Ticker": kode, "Tanggal": STR[mulai:mulai + len(closes)],
                       "Open": opens, "High": np.maximum(opens, closes) * 1.01,
                       "Low": np.minimum(opens, closes) * 0.99, "Close": closes,
                       "Volume": volume if np.ndim(volume) else np.full(len(closes), float(volume))})
    df["AdjClose"] = df["Close"] * 0.98      # faktor dividen tetap: rasio tidak berubah
    if bolong:
        df = df[~df["Tanggal"].isin(bolong)]
    return df


n = len(TGL)
potong = []
for i in range(15):          # tren naik dengan derau
    langkah = rng.normal(0.0015 + i * 0.0001, 0.012, n)
    potong.append(emiten(f"N{i:02d}", 1000 * np.exp(np.cumsum(langkah)),
                         rng.uniform(5e6, 3e7, n)))
for i in range(10):          # tren turun
    potong.append(emiten(f"T{i:02d}", 3000 * np.exp(np.cumsum(rng.normal(-0.001, 0.015, n))),
                         rng.uniform(5e6, 3e7, n)))
for i in range(17):          # acak
    potong.append(emiten(f"A{i:02d}", 500 * np.exp(np.cumsum(rng.normal(0, 0.02, n))),
                         rng.uniform(1e6, 4e7, n)))
potong.append(emiten("IPO1", 800 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n - 300))),
                     2e7, mulai=300))
BOLONG = STR[400:415]
potong.append(emiten("SUSP", 1200 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n))), 2e7,
                     bolong=BOLONG))
potong.append(emiten("TIDUR", 900 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), 100))
ihsg = 7000 * np.exp(np.cumsum(rng.normal(0.0003, 0.008, n)))
potong.append(emiten(KODE_IHSG, ihsg, 1e9))
HARGA = pd.concat(potong, ignore_index=True)
BARS = per_emiten(HARGA)


print("== indikator per tanggal = screener.py atas histori yang dipotong ==")
harian = tabel_harian(BARS)
for kode in ["N03", "T02", "A05", "IPO1", "SUSP"]:
    b = BARS[kode]
    ind = indikator(b)
    adj = pd.Series(b["AdjClose"].to_numpy(), index=pd.to_datetime(b["Tanggal"]))
    vol = pd.Series(b["Volume"].to_numpy(), index=adj.index)
    for pos in [10, 160, 230, 300, len(b) - 1]:
        if pos >= len(b):
            continue
        t = adj.index[pos]
        c, v = adj.iloc[:pos + 1], vol.iloc[:pos + 1]
        r = ind.loc[t]
        m = metrik_tren(c)
        label = f"{kode} @ {t.date()}"
        periksa(f"{label} Harga", r["Harga"], round(c.iloc[-1]))
        periksa(f"{label} MA50", r["MA50"], round(c.tail(50).mean()) if len(c) >= 50 else None)
        periksa(f"{label} MA200", r["MA200"], round(c.tail(200).mean()) if len(c) >= 200 else None)
        periksa(f"{label} MA150", r["MA150"], m["MA150"])
        periksa(f"{label} MA200Lalu", r["MA200Lalu"], m["MA200Lalu"])
        periksa(f"{label} Tinggi52", r["Tinggi52"], m["Tinggi52"])
        periksa(f"{label} Rendah52", r["Rendah52"], m["Rendah52"])
        periksa(f"{label} RSMentah", r["RSMentah"], m["RSMentah"], toleransi=0.011)
        periksa(f"{label} RSI14", r["RSI14"], hitung_rsi(c))
        # Rumus Vol20/Nilai/VolSpike disalin dari ambil_histori().
        vol20 = v.tail(20).mean() if len(v) >= 20 else None
        nilai20 = (c * v).tail(20).mean() if vol20 else None
        periksa(f"{label} VolSpike", r["VolSpike"], round(v.iloc[-1] / vol20, 2) if vol20 else None)
        periksa(f"{label} Nilai", r["Nilai"], round(nilai20 / 1e9, 1) if nilai20 else None)


print("\n== RS diperingkat terhadap universe PADA tanggal itu ==")
for tgl in ["2024-03-15", "2024-08-05", BOLONG[7], "2025-12-31"]:
    t = pd.Timestamp(tgl)
    baris = []
    for kode, b in BARS.items():
        if kode == KODE_IHSG:
            continue
        adj = pd.Series(b["AdjClose"].to_numpy(), index=pd.to_datetime(b["Tanggal"]))
        c = adj[adj.index <= t]
        if c.empty:
            continue
        baris.append({"Ticker": kode, **metrik_tren(c)})
    acuan = pd.DataFrame(baris)
    acuan["RS"] = hitung_rs(acuan)
    h = harian[harian["Tanggal"] == t].set_index("Ticker")
    cocok = [(k, rs) for k, rs in zip(acuan["Ticker"], acuan["RS"]) if k in h.index]
    beda = [k for k, rs in cocok
            if not ((pd.isna(rs) and pd.isna(h.at[k, "RS"])) or rs == h.at[k, "RS"])]
    periksa(f"{tgl}: RS {len(cocok)} emiten sama dengan hitung_rs()", beda, [])
    if tgl == BOLONG[7]:
        periksa("emiten yang disuspensi tetap ikut diperingkat (bar terakhirnya)",
                "SUSP" in set(acuan["Ticker"]) and "SUSP" not in h.index, True)
    if tgl == "2024-03-15":
        periksa("emiten yang belum IPO tidak ikut", "IPO1" in set(acuan["Ticker"]), False)


print("\n== Tanpa look-ahead: masa depan diubah, masa lalu tidak bergeser ==")
batas = "2024-09-30"
masa_depan = HARGA.copy()
ubah = masa_depan["Tanggal"] > batas
for kol in ["Open", "High", "Low", "Close", "AdjClose"]:
    masa_depan.loc[ubah, kol] *= rng.uniform(0.3, 3.0, ubah.sum())
masa_depan.loc[ubah, "Volume"] *= 5
h2 = tabel_harian(per_emiten(masa_depan))
kol = ["Harga", "MA50", "MA200", "RSI14", "VolSpike", "Nilai", "RS", "TT"]
a1 = harian[harian["Tanggal"] <= batas].set_index(["Tanggal", "Ticker"])[kol].sort_index()
a2 = h2[h2["Tanggal"] <= batas].set_index(["Tanggal", "Ticker"])[kol].sort_index()
periksa("semua baris s.d. batas identik", a1.equals(a2), True)
b1 = harian[harian["Tanggal"] > batas]["RS"].fillna(-1).to_numpy()
b2 = h2[h2["Tanggal"] > batas]["RS"].fillna(-1).to_numpy()
periksa("... dan sesudah batas memang berubah (ujinya tidak hampa)", bool((b1 != b2).any()), True)


print("\n== TT vektor = hitung_tt() baris per baris ==")
contoh = harian.dropna(subset=["RS"]).sample(400, random_state=1)
beda = 0
for _, r in contoh.iterrows():
    harap = hitung_tt(r.to_dict())
    if not ((harap is None and pd.isna(r["TT"])) or harap == r["TT"]):
        beda += 1
periksa("400 baris acak cocok", beda, 0)
periksa("ada baris TT = 8 di data buatan (aturan tt8 teruji)", bool((harian["TT"] == 8).any()), True)
periksa("TT kosong bila RS kosong", bool(harian.loc[harian["RS"].isna(), "TT"].isna().all()), True)


print("\n== Aturan sinyal ==")
d = pd.DataFrame({
    "Tanggal": pd.to_datetime(["2024-05-01"] * 6), "Ticker": list("ABCDEF"), "Harga": [100] * 6,
    "RSI14": [60, 66, 60, 60, 60, 60], "MA200": [90, 90, 110, 90, 90, 90],
    "VolSpike": [1.3, 1.3, 1.3, 1.1, 1.3, 1.3], "Nilai": [6, 6, 6, 6, 4.9, 6],
    "TT": [8, 8, 7, 8, 8, 6], "RS": [85, 79, 80, 90, 95, 50],
})
cek = lambda k: list(sinyal(d, ATURAN[k][1], "2024-01-01", None)["Ticker"])  # noqa: E731
periksa("swing: RSI ≤ 65, > MA200, spike ≥ 1,2, nilai ≥ 5", cek("swing"), ["A", "F"])
periksa("tt8: TT = 8 dan likuid", cek("tt8"), ["A", "B", "D"])
periksa("tt7: TT ≥ 7 dan likuid", cek("tt7"), ["A", "B", "C", "D"])
periksa("rs80: RS ≥ 80 dan likuid", cek("rs80"), ["A", "C", "D"])
periksa("sebelum tanggal mulai tidak dihitung", list(sinyal(d, ATURAN["tt8"][1], "2024-06-01", None)["Ticker"]), [])
ok = pasar_di_atas_ma(BARS[KODE_IHSG])
c = BARS[KODE_IHSG]["Close"]
periksa("IHSG > MA50 dibaca di penutupan tanggal itu",
        ok[STR[100]], bool(c.iloc[100] > c.iloc[51:101].mean()))
periksa("belum ada MA50 -> tidak ada keputusan", STR[10] in ok, False)


print("\n== Portofolio: angka yang bisa dihitung tangan ==")
# 6 hari, IHSG datar. A naik 10% di hari 2, B turun 20% di hari 2, C datar.
tg = [f"2025-01-0{i}" for i in range(1, 7)]
def b(kode, closes, opens=None):  # noqa: E302
    return pd.DataFrame({"Ticker": kode, "Tanggal": tg, "Open": opens or closes,
                         "High": closes, "Low": closes, "Close": closes, "Volume": 1e9})
kecil = per_emiten(pd.concat([
    b(KODE_IHSG, [100] * 6),
    b("A", [100, 100, 110, 110, 110, 110]),
    b("B", [100, 100, 80, 80, 80, 80]),
    b("C", [100] * 6),
], ignore_index=True))
psr = Pasar(kecil)
rg = np.random.default_rng(0)
# Sinyal malam hari 0 untuk A dan B; beli di pembukaan hari 1 (100), tahan 2
# hari -> jual di penutupan hari 3. Masing-masing 1/2 ekuitas.
h = portofolio(psr, {tg[0]: ["A", "B"]}, tg[0], slot=2, hari=2, fee_beli=0, fee_jual=0, rng=rg)
e = h["ekuitas"]
periksa("ekuitas awal 1", float(e.iloc[0]), 1.0)
periksa("hari 2: (1,1 + 0,8) / 2 = 0,95", float(e.loc[tg[2]]), 0.95)
periksa("sesudah jual tetap 0,95", float(e.iloc[-1]), 0.95)
periksa("Total% = -5", h["Total%"], -5.0)
periksa("MaxDD% = -5", h["MaxDD%"], -5.0)
periksa("dua transaksi", h["Transaksi"], 2)

# Slot 1, tiga sinyal: hanya satu yang terbeli.
h = portofolio(psr, {tg[0]: ["A", "B", "C"]}, tg[0], slot=1, hari=2, fee_beli=0, fee_jual=0, rng=rg)
periksa("slot penuh -> sinyal lain tidak dibeli", h["Transaksi"], 1)

# Biaya: beli 1 lalu jual 1 dengan fee 0,15/0,25 -> 0,9975/1,0015.
h = portofolio(psr, {tg[0]: ["C"]}, tg[0], slot=1, hari=2, fee_beli=0.15, fee_jual=0.25, rng=rg)
periksa("biaya beli & jual dipotong", float(h["ekuitas"].iloc[-1]), 0.9975 / 1.0015, toleransi=1e-9)

# Sinyal yang emitennya sedang dipegang tidak dibeli lagi; sesudah dijual
# boleh dibeli lagi.
h = portofolio(psr, {tg[0]: ["C"], tg[1]: ["C"], tg[3]: ["C"]}, tg[0], slot=2, hari=2,
               fee_beli=0, fee_jual=0, rng=rg)
periksa("pick ulang saat masih dipegang dilewati", h["Transaksi"], 2)

# Filter pasar menolak sinyal malam yang IHSG-nya di bawah MA50.
h = portofolio(psr, {tg[0]: ["A"]}, tg[0], slot=1, hari=2, fee_beli=0, fee_jual=0, rng=rg,
               pasar_ok={tg[0]: False})
periksa("filter IHSG menahan pembelian", h["Transaksi"], 0)
periksa("... ekuitas tetap 1", float(h["ekuitas"].iloc[-1]), 1.0)

m = metrik_ekuitas(pd.Series([1.0, 1.2, 0.9, 1.0], index=tg[:4]))
periksa("drawdown terdalam dari puncak 1,2 ke 0,9", m["MaxDD%"], -25.0)
periksa("tanggal puncak", m["Puncak"], tg[1])
periksa("tanggal lembah", m["Lembah"], tg[2])


print("\n== Ringkasan per sinyal & galat baku per tanggal ==")
banding = pd.DataFrame({"TanggalBeli": ["d1", "d2"], "IHSGdiAtasMA50": ["Ya", "Ya"],
                        "AcakJumlah": [40, 40], "IHSG5%": [0.0, 0.0], "Acak5%": [1.0, 2.0]})
posisi = pd.DataFrame({
    "TanggalBeli": ["d1", "d1", "d2", "d2"], "Ulang": ["Tidak"] * 4, "Modal": [1e7] * 4,
    "Hari5%": [3.0, 1.0, 2.0, 6.0],
})
r = ringkas_sinyal(posisi, banding, hari=5, sorot=(5,))[0]
# Selisih per posisi: 2, 0, 0, 4 -> rata 1,5. Per tanggal: d1 = 1, d2 = 2
# -> SE = std([1, 2]) / sqrt(2) = 0,7071 / 1,4142 = 0,5.
periksa("selisih rata-rata", r["Selisih%"], 1.5)
periksa("SE dihitung per tanggal beli, bukan per posisi", r["SelisihSE%"], 0.5)
periksa("jumlah tanggal beli", r["TanggalBeli"], 2)


print("\n== Sinyal -> simulasi uji_winrate (aturan sama persis) ==")
s = sinyal(harian, ATURAN["tt8"][1], "2025-01-01", None)
from uji_ulang_tren import ke_riwayat  # noqa: E402
rw = ke_riwayat(s)
periksa("cap waktu 18:00 WIB malam sinyal", rw["Waktu"].iloc[0], rw["Tanggal"].iloc[0] + "T11:00:00Z")
pos = simulasi(rw, BARS, 10_000_000, 21, 0.15, 0.25)
satu = pos.iloc[0]
periksa("dibeli di sesi SESUDAH sinyal", satu["TanggalBeli"] > satu["Tanggal"], True)


print("\n== Ujung ke ujung: main() atas harga buatan ==")
with tempfile.TemporaryDirectory() as dd:
    dd = Path(dd)
    HARGA.to_csv(dd / "harga.csv", index=False)
    hasil = subprocess.run([sys.executable, str(AKAR / "uji_ulang_tren.py"),
                            "--harga-csv", str(dd / "harga.csv"), "--mulai", "2024-06-01",
                            "--seed", "3", "--output-dir", str(dd / "keluar")],
                           capture_output=True, text=True, cwd=AKAR)
    periksa("keluar dengan kode 0", hasil.returncode, 0)
    if hasil.returncode:
        print(hasil.stderr[-3000:])
    ada = {p.name for p in (dd / "keluar").glob("*")} if (dd / "keluar").exists() else set()
    periksa("enam berkas keluaran", ada, {
        "uji_ulang_tren_sinyal.csv", "uji_ulang_tren_semester.csv",
        "uji_ulang_tren_portofolio.csv", "uji_ulang_tren_ekuitas.csv",
        "uji_ulang_tren_meta.json", "uji_ulang_tren.md"})
    if "uji_ulang_tren_sinyal.csv" in ada:
        sn = pd.read_csv(dd / "keluar/uji_ulang_tren_sinyal.csv")
        periksa("4 aturan × 2 filter × 3 hari", len(sn), 24)
        po = pd.read_csv(dd / "keluar/uji_ulang_tren_portofolio.csv")
        periksa("portofolio: 4 aturan + acak, × 2 filter", len(po), 10)
        meta = json.loads((dd / "keluar/uji_ulang_tren_meta.json").read_text())
        periksa("meta mencatat sinyal pertama ≥ mulai", meta["sinyalPertama"] >= "2024-06-01", True)
        periksa("ringkasan menyebut bias survivorship",
                "survivorship" in (dd / "keluar/uji_ulang_tren.md").read_text(), True)


print()
if gagal:
    print(f"{gagal} pemeriksaan gagal.")
    sys.exit(1)
print("Semua pemeriksaan lolos.")
