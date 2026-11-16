#!/usr/bin/env python3
"""Uji position sizer, distribution day / follow-through day, dan uji_ulang_pasar.py.

Kenapa ada: ketiganya berakhir sebagai angka yang tampak masuk akal apa pun
yang terjadi di dalamnya. "12 lot" yang dihitung dari entri bawah alih-alih
entri atas, DD yang gugur satu sesi terlalu cepat, atau hari rally yang mulai
dihitung dari hari yang salah tidak membuat apa pun terlihat aneh — cuma
salah. Jadi semuanya diuji terhadap deret buatan yang jawabannya sudah
diketahui.

Sengaja tanpa jaringan, sama dengan scripts/uji_tren.py.

Pemakaian:
    python scripts/uji_pasar.py        # dari akar repo

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

from analisa_smc import ukuran_posisi  # noqa: E402
from screener import (  # noqa: E402
    DD_UMUR_SESI, JENDELA_RENDAH, bar_ihsg_bersih, hitung_dd_ftd, ringkas_dd_ftd,
)

gagal = 0


def periksa(nama: str, dapat, harap):
    global gagal
    sama = dapat == harap
    if isinstance(harap, float) and isinstance(dapat, (int, float, np.number)):
        sama = abs(float(dapat) - harap) < 1e-6
    if sama:
        print(f"  ok   {nama}")
    else:
        gagal += 1
        print(f"  GAGAL {nama}: dapat {dapat!r}, seharusnya {harap!r}")


# ================================================================ position sizer
print("ukuran_posisi — risiko tetap 1% dari Rp10 juta = Rp100.000")
# Entri 1.000, stop 950: risiko Rp50/lembar = Rp5.000/lot -> 20 lot.
# Nilai 20 lot = Rp2.000.000 = 20% modal, di bawah atap 25%.
r = ukuran_posisi(1000, 950)
periksa("20 lot", r["lot"], 20)
periksa("nilai posisi Rp2.000.000", r["nilai"], 2_000_000)
periksa("porsi 20% modal", r["porsi"], 20.0)
periksa("risiko Rp100.000", r["risiko_rp"], 100_000)
periksa("tanpa catatan", r["catatan"], "")

# floor, bukan round: risiko Rp60/lembar -> 100.000 / 6.000 = 16,67 -> 16 lot.
periksa("dibulatkan ke bawah (16,67 -> 16)", ukuran_posisi(1000, 940)["lot"], 16)

# Atap 25%: entri 1.000 stop 980 -> risiko 50 lot, tapi 25% modal = 2,5 juta
# = 25 lot. Risiko nyatanya jadi 25 × 2.000 = Rp50.000 (0,5%).
r = ukuran_posisi(1000, 980)
periksa("atap 25% memotong 50 -> 25 lot", r["lot"], 25)
periksa("porsi tepat 25%", r["porsi"], 25.0)
periksa("risiko turun ke Rp50.000", r["risiko_rp"], 50_000)
periksa("catatan menyebut atap", "atap 25% modal" in r["catatan"], True)
periksa("catatan: Rp50.000 (0,50% modal)", "Rp50.000 (0,50% modal)" in r["catatan"], True)

# Satu lot pun melebihi risiko: entri 9.000 stop 7.900 -> Rp110.000/lot.
r = ukuran_posisi(9000, 7900)
periksa("1 lot > jatah risiko -> 0 lot, tidak dipaksa 1", r["lot"], 0)
periksa("nilai 0", r["nilai"], 0)
periksa("catatan berisi alasannya", "di atas jatah risiko" in r["catatan"], True)
periksa("angka rupiah di catatan bergaya Indonesia", "Rp110.000" in r["catatan"], True)

# Satu lot melebihi atap porsi: modal 1 juta, saham 3.000 -> 1 lot Rp300.000
# = 30% > 25%; risikonya sendiri cuma Rp10.000 (1%) jadi lolos sisi risiko.
r = ukuran_posisi(3000, 2900, modal=1_000_000)
periksa("1 lot > atap porsi -> 0 lot", r["lot"], 0)
periksa("catatan menyebut atap", "di atas atap" in r["catatan"], True)

# Fraksi harga: entri yang bukan kelipatan fraksi dibulatkan KE ATAS, stop KE
# BAWAH. 1.003 (fraksi Rp5) -> 1.005; 951 -> 950. Risiko 55/lembar ->
# 100.000/5.500 = 18,2 -> 18 lot, nilai 18 × 100.505 = 1.809.000.
r = ukuran_posisi(1003, 951)
periksa("entri dibulatkan ke atas, stop ke bawah: 18 lot", r["lot"], 18)
periksa("nilai pakai entri 1.005", r["nilai"], 18 * 1005 * 100)
# Pada harga sah, pembulatan tidak mengubah apa pun.
periksa("harga sah tidak bergeser", ukuran_posisi(5025, 4800)["lot"], 4)

# Argumen modal/risiko/atap.
periksa("modal 50 juta, risiko 2%: 1.000.000 / 5.000 = 200 -> atap 25% = 125",
        ukuran_posisi(1000, 950, modal=50_000_000, risiko_pct=2)["lot"], 125)
periksa("atap 100% melepas batasnya", ukuran_posisi(1000, 980, maks_posisi_pct=100)["lot"], 50)
periksa("floating point: 10 juta × 1% tidak kehilangan lot (risiko pas 1 lot)",
        ukuran_posisi(1000, 0)["lot"], 1)
periksa("stop ≥ entri: 0 lot", ukuran_posisi(1000, 1000)["lot"], 0)


# ================================================================ DD / FTD
def seri(close, vol, low=None) -> pd.DataFrame:
    close = np.asarray(close, dtype=float)
    low = close * 0.995 if low is None else np.asarray(low, dtype=float)
    return pd.DataFrame({"Close": close, "Low": low, "Volume": np.asarray(vol, dtype=float)},
                        index=pd.bdate_range("2025-01-01", periods=len(close)))


print("\nhitung_dd_ftd — distribution day")
# 40 bar naik pelan, volume tetap (tidak ada DD), lalu skenario.
dasar = [1000 + i for i in range(40)]            # terakhir 1039
c = dasar + [1039 * 0.998, 1039 * 0.998 * 0.9981, 1039 * 0.998 * 0.9981 * 0.99]
v = [100] * 40 + [120, 130, 125]
h = hitung_dd_ftd(seri(c, v))
periksa("turun 0,2% + volume naik = DD", bool(h["DD"].iloc[40]), True)
periksa("turun 0,19% + volume naik bukan DD", bool(h["DD"].iloc[41]), False)
periksa("turun 1% + volume TURUN bukan DD", bool(h["DD"].iloc[42]), False)
periksa("DD aktif 1", int(h["DDAktif"].iloc[42]), 1)

# Umur 25 sesi: DD di bar 40, harga datar sesudahnya (tidak naik 5%).
c = dasar + [1039 * 0.99] + [1039 * 0.99] * 30
v = [100] * 40 + [200] + [200] * 30
h = hitung_dd_ftd(seri(c, v))
periksa(f"masih aktif di sesi ke-{DD_UMUR_SESI} (hari DD = sesi 1)",
        int(h["DDAktif"].iloc[40 + DD_UMUR_SESI - 1]), 1)
periksa(f"gugur di sesi ke-{DD_UMUR_SESI + 1}", int(h["DDAktif"].iloc[40 + DD_UMUR_SESI]), 0)

# Gugur karena naik 5% dari penutupan hari DD, dan tidak hidup lagi.
cd = 1039 * 0.99
c = dasar + [cd, cd * 1.04, cd * 1.049, cd * 1.05 + 0.01, cd]
v = [100] * 40 + [200, 100, 100, 100, 90]
h = hitung_dd_ftd(seri(c, v))
periksa("naik 4,9% belum menggugurkan", int(h["DDAktif"].iloc[42]), 1)
periksa("penutupan ≥ 5% di atasnya menggugurkan", int(h["DDAktif"].iloc[43]), 0)
periksa("turun lagi tidak menghidupkannya", int(h["DDAktif"].iloc[44]), 0)

# Menumpuk: lima DD dalam 25 sesi.
c, v = list(dasar), [100] * 40
for _ in range(5):
    c += [c[-1] * 0.99, c[-1] * 0.99 * 1.001]
    v += [v[-1] + 50, v[-1] + 50 - 10]
h = hitung_dd_ftd(seri(c, v))
periksa("lima DD aktif", int(h["DDAktif"].iloc[-1]), 5)
periksa("tanggal DD tercatat", len(h["DDTanggal"].iloc[-1]), 5)


print("\nhitung_dd_ftd — follow-through day")
# 30 bar turun 1%/hari: tiap bar sejak ke-25 adalah titik terendah 25 sesi
# baru. Bar 29 = titik terendah L.
turun = [1000 * 0.99 ** i for i in range(30)]
cL = turun[-1]


def rally(naik: list[float], vol: list[float], low=None):
    c = list(turun)
    for r in naik:
        c.append(c[-1] * (1 + r))
    vv = [100] * 30 + vol
    lo = None
    if low is not None:
        lo = list(np.asarray(c) * 0.995)
        for i, x in low.items():
            lo[30 + i] = x
    return hitung_dd_ftd(seri(c, vv, lo))


h = rally([0.005, 0.003, 0.003, 0.013], [100, 100, 100, 150])
periksa("titik terendah = bar 29", h["TitikRendah"].iloc[29], h.index[29])
periksa("bar 29 KOREKSI", h["Keadaan"].iloc[29], "KOREKSI")
periksa("hari ke-1 = naik pertama sesudah titik terendah", int(h["HariRally"].iloc[30]), 1)
periksa("hari ke-3 RALLY", (h["Keadaan"].iloc[32], int(h["HariRally"].iloc[32])), ("RALLY", 3))
periksa("hari ke-4 naik 1,3% + volume naik = FTD", bool(h["FTD"].iloc[33]), True)
periksa("keadaan jadi NAIK", h["Keadaan"].iloc[33], "NAIK")
periksa("TanggalFTD", h["TanggalFTD"].iloc[33], h.index[33])

h = rally([0.005, 0.003, 0.020, 0.003], [100, 100, 150, 160])
periksa("hari ke-3 naik 2% bukan FTD (terlalu cepat)", bool(h["FTD"].iloc[32]), False)

h = rally([0.005, 0.003, 0.003, 0.013, 0.013], [100, 100, 100, 90, 120])
periksa("hari ke-4 naik tapi volume turun bukan FTD", bool(h["FTD"].iloc[33]), False)
periksa("hari ke-5 naik 1,3% + volume naik = FTD", bool(h["FTD"].iloc[34]), True)

h = rally([0.005, 0.003, 0.003, 0.012, 0.003], [100, 100, 100, 150, 160])
periksa("naik 1,2% (< 1,25%) bukan FTD", bool(h["FTD"].iloc[33]), False)

h = rally([0.005, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.02],
          [100, 100, 100, 100, 100, 100, 100, 200])
periksa("hari ke-7 masih RALLY", (h["Keadaan"].iloc[36], int(h["HariRally"].iloc[36])), ("RALLY", 7))
periksa("hari ke-8 naik 2% bukan FTD (lewat jendela)", bool(h["FTD"].iloc[37]), False)
periksa("percobaan habis -> KOREKSI", h["Keadaan"].iloc[37], "KOREKSI")

# Hari pertama sesudah titik terendah turun (tanpa titik terendah baru):
# hitungan belum mulai.
h = rally([-0.002, 0.005, 0.003, 0.003, 0.013], [100, 100, 100, 100, 150],
          low={0: cL * 0.996})
periksa("turun tanpa rendah baru: hari rally masih 0", int(h["HariRally"].iloc[30]), 0)
periksa("hari ke-1 di naik pertama", int(h["HariRally"].iloc[31]), 1)
periksa("FTD di hari ke-4 dari situ", bool(h["FTD"].iloc[34]), True)

# Titik terendah rally ditembus: hitungan mulai ulang dari titik baru.
h = rally([0.005, 0.003, -0.01, 0.004, 0.003, 0.003, 0.013],
          [100, 100, 100, 100, 100, 100, 150], low={2: cL * 0.99})
periksa("tembus titik terendah -> KOREKSI, hari 0", (h["Keadaan"].iloc[32], int(h["HariRally"].iloc[32])),
        ("KOREKSI", 0))
periksa("titik terendah pindah", h["TitikRendah"].iloc[32], h.index[32])
periksa("hari ke-4 dihitung dari titik baru = FTD", bool(h["FTD"].iloc[36]), True)

# NAIK berakhir di titik terendah 25 sesi berikutnya.
h = rally([0.005, 0.003, 0.003, 0.013] + [0.001] * 10 + [-0.08], [100, 100, 100, 150] + [100] * 11)
periksa("NAIK bertahan selama tidak ada rendah baru", h["Keadaan"].iloc[40], "NAIK")
periksa("rendah 25 sesi baru -> KOREKSI", h["Keadaan"].iloc[-1], "KOREKSI")
periksa("TanggalFTD dikosongkan", bool(pd.isna(h["TanggalFTD"].iloc[-1])), True)

print("\nhitung_dd_ftd — tidak melihat ke depan")
rng = np.random.default_rng(3)
n = 400
cc = 7000 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
acak = seri(cc, rng.uniform(1e8, 5e8, n), cc * (1 - rng.uniform(0, 0.02, n)))
penuh = hitung_dd_ftd(acak)
sama = all(str(hitung_dd_ftd(acak.iloc[:k + 1]).iloc[-1].to_dict()) == str(penuh.iloc[k].to_dict())
           for k in (60, 150, 260, 399))
periksa("baris ke-k sama dengan hitungan atas histori yang dipotong di k", sama, True)
periksa("ada FTD di deret acak (mesin keadaannya hidup)", bool(penuh["FTD"].any()), True)
periksa("ada DD di deret acak", bool(penuh["DD"].any()), True)
periksa(f"belum ada keadaan sebelum {JENDELA_RENDAH} bar",
        set(penuh["Keadaan"].iloc[:JENDELA_RENDAH]), {"KOREKSI"})

print("\nbar_ihsg_bersih & ringkas_dd_ftd")
mentah = acak.copy()
mentah.index = mentah.index.tz_localize("Asia/Jakarta")
mentah.loc[mentah.index[-1], ["Close", "Volume"]] = [np.nan, 0]   # bar sesi berjalan dari Yahoo
bersih = bar_ihsg_bersih(mentah)
periksa("bar Close NaN / Volume 0 dibuang", len(bersih), n - 1)
periksa("indeks tanpa zona waktu", bersih.index.tz, None)
rk = ringkas_dd_ftd(bersih)
periksa("kunci pasar.json", sorted(rk), ["distribusi", "ftd"])
periksa("jumlah DD aktif = panjang daftar tanggal", rk["distribusi"]["aktif"],
        len(rk["distribusi"]["tanggal"]))
periksa("keadaan sah", rk["ftd"]["keadaan"] in {"NAIK", "RALLY", "KOREKSI"}, True)
json.dumps(rk)   # harus bisa ditulis apa adanya
periksa("histori terlalu pendek -> None", ringkas_dd_ftd(bersih.iloc[:10]), None)


# ================================================================ uji_ulang_pasar
print("\n== uji_ulang_pasar.py ujung ke ujung, harga buatan ==")
from uji_ulang_pasar import susun_filter  # noqa: E402
from uji_ulang_tren import pasar_di_atas_ma  # noqa: E402
from uji_winrate import KODE_IHSG, per_emiten  # noqa: E402

rng = np.random.default_rng(11)
TGL = [t.date().isoformat() for t in pd.bdate_range("2023-01-02", "2025-06-30")]
n = len(TGL)


def emiten(kode, closes, volume):
    closes = np.asarray(closes, dtype=float)
    opens = closes * (1 + rng.normal(0, 0.003, n))
    return pd.DataFrame({"Ticker": kode, "Tanggal": TGL, "Open": opens,
                         "High": np.maximum(opens, closes) * 1.01,
                         "Low": np.minimum(opens, closes) * 0.99, "Close": closes,
                         "Volume": volume, "AdjClose": closes})


# IHSG naik - jatuh dalam - pulih, supaya MA50, DD, FTD, dan breadth semuanya
# berganti keadaan di periode uji.
tren = np.concatenate([np.full(n // 3, 0.001), np.full(n // 3, -0.0025),
                       np.full(n - 2 * (n // 3), 0.002)])
ihsg = 7000 * np.exp(np.cumsum(tren + rng.normal(0, 0.011, n)))
potong = [emiten(KODE_IHSG, ihsg, rng.uniform(1e8, 4e8, n))]
for i in range(40):
    beta = rng.uniform(0.5, 1.5)
    langkah = beta * (tren + rng.normal(0, 0.008, n)) + rng.normal(0, 0.015, n)
    potong.append(emiten(f"E{i:02d}", 1000 * np.exp(np.cumsum(langkah)),
                         rng.uniform(5e6, 4e7, n)))
HARGA = pd.concat(potong, ignore_index=True)

bars = per_emiten(HARGA)
keadaan, peta = susun_filter(bars)
ma = pasar_di_atas_ma(bars[KODE_IHSG])
periksa("filter ma50 = pasar_di_atas_ma() uji_ulang_tren",
        all(peta["ma50"][t] == ma.get(t, False) for t in peta["ma50"]), True)
periksa("filter gabungan = irisan", all(peta["ma50+dd5"][t] == (peta["ma50"][t] and peta["dd5"][t])
                                         for t in peta["dd5"]), True)
periksa("filter tanpa selalu boleh", all(peta["tanpa"].values()), True)
periksa("breadth sempat di atas dan di bawah 50%",
        (keadaan["Breadth%"] > 50).any() and (keadaan["Breadth%"] < 50).any(), True)
periksa("ada FTD di data buatan", bool(keadaan["FTD"].any()), True)

with tempfile.TemporaryDirectory() as dd:
    dd = Path(dd)
    HARGA.to_csv(dd / "harga.csv", index=False)
    hasil = subprocess.run([sys.executable, str(AKAR / "uji_ulang_pasar.py"),
                            "--harga-csv", str(dd / "harga.csv"), "--mulai", "2024-01-02",
                            "--seed", "3", "--breadth-csv", str(dd / "tidak-ada.csv"),
                            "--output-dir", str(dd / "keluar")],
                           capture_output=True, text=True, cwd=AKAR)
    periksa("keluar dengan kode 0", hasil.returncode, 0)
    if hasil.returncode:
        print(hasil.stderr[-3000:])
    ada = {p.name for p in (dd / "keluar").glob("*")} if (dd / "keluar").exists() else set()
    periksa("lima berkas keluaran", ada, {
        "uji_ulang_pasar_sinyal.csv", "uji_ulang_pasar_portofolio.csv",
        "uji_ulang_pasar_harian.csv", "uji_ulang_pasar_meta.json", "uji_ulang_pasar.md"})
    if "uji_ulang_pasar_portofolio.csv" in ada:
        po = pd.read_csv(dd / "keluar/uji_ulang_pasar_portofolio.csv")
        periksa("portofolio: swing + acak × 8 filter", len(po), 16)
        sn = pd.read_csv(dd / "keluar/uji_ulang_pasar_sinyal.csv")
        periksa("sinyal: 8 filter × 3 hari", len(sn), 24)
        tanpa = int(sn[(sn["Kode"] == "tanpa") & (sn["Hari"] == 5)]["Posisi"].iloc[0])
        lain = sn[(sn["Kode"] != "tanpa") & (sn["Hari"] == 5)]["Posisi"].fillna(0)
        periksa("filter tidak pernah menambah posisi", bool((lain <= tanpa).all()), True)
        hb = po.set_index(["Kode", "KodeFilter"])["HariBoleh%"]
        periksa("HariBoleh% tanpa filter = 100", float(hb[("swing", "tanpa")]), 100.0)
        meta = json.loads((dd / "keluar/uji_ulang_pasar_meta.json").read_text())
        periksa("meta mencatat FTD", meta["keadaan"]["jumlahFTD"] == len(meta["keadaan"]["tanggalFTD"]), True)
        periksa("ringkasan menyebut bias survivorship",
                "survivorship" in (dd / "keluar/uji_ulang_pasar.md").read_text(), True)

    # Volume IHSG kosong -> berhenti, bukan diam-diam memakai proksi.
    rusak = HARGA.copy()
    rusak.loc[rusak["Ticker"] == KODE_IHSG, "Volume"] = 0.0
    rusak.to_csv(dd / "rusak.csv", index=False)
    hasil = subprocess.run([sys.executable, str(AKAR / "uji_ulang_pasar.py"),
                            "--harga-csv", str(dd / "rusak.csv"), "--seed", "1",
                            "--output-dir", str(dd / "rusak")],
                           capture_output=True, text=True, cwd=AKAR)
    periksa("volume IHSG kosong -> keluar dengan kode 1", hasil.returncode, 1)
    periksa("... tanpa menulis hasil", (dd / "rusak").exists(), False)


print()
if gagal:
    print(f"{gagal} pemeriksaan gagal.")
    sys.exit(1)
print("Semua pemeriksaan lolos.")
