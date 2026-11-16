#!/usr/bin/env python3
"""Uji ulang historis: apakah Trend Template / RS lebih baik dari daftar swing?

Uji winrate (uji_winrate.py) menjawab pertanyaan itu dengan pick nyata, tapi
daftar Tren baru lahir November 2026 — butuh berbulan-bulan sebelum sampelnya
bisa dibaca. Berkas ini menjawab dari arah lain: aturan yang sama diterapkan
ke histori harga April 2024 sampai sekarang, per tanggal, seolah screening
malam sudah berjalan sejak itu.

Empat aturan dibandingkan, masing-masing dengan dan tanpa filter IHSG > MA50:

    swing  RSI14 ≤ 65, harga > MA200, VolSpike ≥ 1,2, nilai ≥ Rp5 M  (swing.csv)
    tt8    Trend Template 8/8, nilai ≥ Rp5 M                         (tren.csv)
    tt7    Trend Template ≥ 7, nilai ≥ Rp5 M
    rs80   RS ≥ 80 saja, nilai ≥ Rp5 M

Dua cara membaca hasilnya:

1. Per sinyal — persis aturan uji winrate (fungsi simulasi() dan
   pembanding() dari uji_winrate.py dipakai apa adanya): beli di pembukaan
   sesi sesudah sinyal, modal tetap, dua biaya, pick ulang tidak dihitung,
   dibandingkan dengan rata-rata saham likuid (nilai ≥ Rp5 M) yang dibeli di
   sesi yang sama. Yang dibaca: selisih di hari bursa ke-5, 10, 21.
2. Per portofolio — 10 slot, tiap sinyal mengisi slot kosong dengan 1/10
   ekuitas, ditahan 21 hari bursa. Yang dibaca: kerugian terdalam (drawdown)
   dan total hasil. Urutan pengisian slot saat sinyal lebih banyak dari slot
   diacak; diulang dengan beberapa seed dan dilaporkan median serta
   rentangnya, supaya hasilnya tidak bergantung pada satu urutan kebetulan.
   Pembandingnya portofolio yang sama dengan sinyal "semua saham likuid".

Tidak ada look-ahead: indikator tiap tanggal dihitung hanya dari bar sampai
tanggal itu, dan RS diperingkat terhadap universe pada tanggal itu (emiten
yang belum punya histori setahun tidak ikut). scripts/uji_ulang_tren.py
memeriksanya dengan membandingkan tiap angka terhadap fungsi screener.py yang
dijalankan atas histori yang dipotong di tanggal itu.

⚠️ Bias survivorship: universe-nya daftar emiten HARI INI (tickers/idx.txt =
400 emiten terbesar per hari ini, plus daftar kurasi). Emiten yang dulu naik
lalu ambruk, mengecil, atau delisting tidak ada di data. Itu membuat angka
absolutnya terlalu bagus — dan lebih parah untuk aturan momentum (TT/RS)
yang justru membeli saham sesudah naik kencang. Pembanding saham acak diambil
dari universe yang sama sehingga sebagian bias ikut terhapus di kolom
selisih, tapi tidak seluruhnya.

Pemakaian:
    python uji_ulang_tren.py                          # tarik harga dari Yahoo
    python uji_ulang_tren.py --simpan-harga h.csv     # ... dan simpan
    python uji_ulang_tren.py --harga-csv h.csv        # tanpa jaringan
    python uji_ulang_tren.py --mulai 2025-01-01 --seed 50

Keluaran (di --output-dir, bawaan hasil/):
    uji_ulang_tren_sinyal.csv      per aturan × filter × hari ke-5/10/21
    uji_ulang_tren_semester.csv    selisih hari ke-21 per semester
    uji_ulang_tren_penyumbang.csv  10 emiten penyumbang selisih terbesar per aturan
    uji_ulang_tren_portofolio.csv  drawdown & hasil portofolio 10 posisi
    uji_ulang_tren_ekuitas.csv     kurva ekuitas (seed pertama), per tanggal
    uji_ulang_tren_meta.json       parameter & cakupan data
    uji_ulang_tren.md              ringkasan yang bisa dibaca langsung di GitHub
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from screener import (
    BOBOT_RS, DAFTAR_DEFAULT, HARI_MA200_NAIK, MIN_EMITEN_RS, MIN_RS_TT,
    baca_daftar_ticker,
)
from uji_winrate import (
    FEE_BELI, FEE_JUAL, HARI_DEFAULT, KODE_IHSG, MA_PASAR, MODAL_DEFAULT,
    NILAI_MIN_PEMBANDING, ambil_harga, pembanding, per_emiten, ringkas,
    selaraskan_kalender, simulasi,
)

MULAI_DEFAULT = "2024-04-01"

# Histori ditarik mundur sejauh ini dari tanggal sinyal pertama. Yang paling
# rakus: MA200 22 bar lalu (222 bar ≈ 320 hari kalender) dan kenaikan 12 bulan
# (365 hari). 460 hari memberi sisa untuk libur panjang dan pemanasan RSI.
MUNDUR_HARI = 460

# Syarat likuiditas semua aturan — sama dengan --min-nilai 5 di
# screening-malam.yml dan dengan pembanding saham acak di uji_winrate.py.
NILAI_MIN = NILAI_MIN_PEMBANDING

SLOT = 10
SEED_DEFAULT = 20
HARI_SOROT = (5, 10, 21)

FILTER = {"tanpa": "Tanpa filter", "ihsg": "IHSG > MA50"}


# ------------------------------------------------------------------ indikator
def _bulat(s: pd.Series) -> pd.Series:
    """Pembulatan ke rupiah utuh seperti round() di screener.py.

    screener.py membulatkan Harga, MA, dan tinggi/rendah 52 minggu SEBELUM
    membandingkannya di Trend Template. Pada saham ber-harga puluhan rupiah
    pembulatan itu bisa membalik satu syarat, jadi ikut ditiru.
    """
    return s.round(0)


def indikator(bar: pd.DataFrame) -> pd.DataFrame:
    """Kolom screener.py per tanggal untuk satu emiten.

    Setiap baris hanya memakai bar sampai tanggal itu (rolling, shift, dan
    pencarian mundur — tidak ada yang melihat ke depan). Harga yang dipakai
    AdjClose bila ada, sama dengan history() bawaan yang dibaca screener;
    Volume tetap volume lembar.

    Kolom: Harga, MA50, MA150, MA200, MA200Lalu, Tinggi52, Rendah52, RSI14,
    VolSpike, Nilai, RSMentah. Indeks: DatetimeIndex tanggal bar.
    """
    idx = pd.DatetimeIndex(pd.to_datetime(bar["Tanggal"]))
    if "AdjClose" in bar.columns:
        c = bar["AdjClose"].where(bar["AdjClose"].notna(), bar["Close"])
    else:
        c = bar["Close"]
    c = pd.Series(c.to_numpy(dtype=float), index=idx)
    v = pd.Series(bar["Volume"].to_numpy(dtype=float) if "Volume" in bar.columns
                  else np.zeros(len(bar)), index=idx)

    out = pd.DataFrame(index=idx)
    out["Harga"] = _bulat(c)
    out["MA50"] = _bulat(c.rolling(50).mean())
    out["MA150"] = _bulat(c.rolling(150).mean())
    ma200 = c.rolling(200).mean()
    out["MA200"] = _bulat(ma200)
    out["MA200Lalu"] = _bulat(ma200.shift(HARI_MA200_NAIK))

    # 52 minggu: jendela (t - 365 hari, t], hanya bila histori emiten itu
    # sudah ≥ 358 hari — sama dengan metrik_tren().
    setahun = (idx - idx[0]) >= pd.Timedelta(days=358)
    out["Tinggi52"] = _bulat(c.rolling("365D").max()).where(setahun)
    out["Rendah52"] = _bulat(c.rolling("365D").min()).where(setahun)

    # RSI Wilder, sama dengan hitung_rsi(): ewm atas seluruh deret sampai t.
    delta = c.diff()
    naik = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    turun = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = (naik / turun).where(turun != 0, np.inf)
    rsi = (100 - 100 / (1 + rs)).round(1)
    rsi.iloc[:14] = np.nan
    out["RSI14"] = rsi

    vol20 = v.rolling(20).mean()
    sah = vol20 > 0
    out["VolSpike"] = (v / vol20).round(2).where(sah)
    nilai = (c * v).rolling(20).mean() / 1e9
    out["Nilai"] = nilai.round(1).where(sah & (nilai > 0))

    # Kenaikan sejak penutupan terakhir pada/sebelum `hari` kalender lalu.
    tgl = idx.to_numpy()
    harga = c.to_numpy()
    naik_h = {}
    for hari, _ in BOBOT_RS:
        j = np.searchsorted(tgl, tgl - np.timedelta64(hari, "D"), side="right") - 1
        lalu = np.where(j >= 0, harga[np.clip(j, 0, None)], np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            naik_h[hari] = np.where(lalu > 0, (harga / lalu - 1) * 100, np.nan)
    mentah = sum(b * naik_h[h] for h, b in BOBOT_RS)
    out["RSMentah"] = np.round(mentah, 2)
    return out


def peringkat_rs(mentah: dict[str, pd.Series], kalender: pd.DatetimeIndex) -> pd.DataFrame:
    """RS 1-99 per tanggal × emiten, diperingkat terhadap universe tanggal itu.

    Pada tanggal t, nilai sebuah emiten adalah RSMentah di bar terakhirnya
    ≤ t — persis yang dilihat screener.py kalau dijalankan malam itu (emiten
    yang sedang disuspensi tetap ikut dengan angka bar terakhirnya). Emiten
    yang belum IPO atau historinya belum setahun bernilai kosong dan tidak
    ikut diperingkat. Tanggal dengan kurang dari MIN_EMITEN_RS emiten
    berangka dikosongkan, sama dengan hitung_rs().
    """
    lebar = pd.DataFrame({k: s.reindex(kalender, method="ffill") for k, s in mentah.items()},
                         index=kalender)
    pct = lebar.rank(axis=1, pct=True)
    rs = (pct * 99).round().clip(1, 99)
    rs[lebar.notna().sum(axis=1) < MIN_EMITEN_RS] = np.nan
    return rs


def hitung_tt_vektor(d: pd.DataFrame) -> pd.Series:
    """Jumlah syarat Trend Template (0-8) per baris; NaN bila bahan kurang.

    Delapan syarat yang sama dengan KRITERIA_TT di screener.py, ditulis ulang
    dalam bentuk vektor supaya bisa dijalankan atas ratusan ribu baris.
    scripts/uji_ulang_tren.py mencocokkannya baris per baris dengan hitung_tt().
    """
    h, m50, m150, m200 = d["Harga"], d["MA50"], d["MA150"], d["MA200"]
    syarat = [
        (h > m150) & (h > m200),
        m150 > m200,
        m200 > d["MA200Lalu"],
        (m50 > m150) & (m50 > m200),
        h > m50,
        h >= 1.30 * d["Rendah52"],
        h >= 0.75 * d["Tinggi52"],
        d["RS"] >= MIN_RS_TT,
    ]
    tt = sum(s.astype(int) for s in syarat).astype(float)
    bahan = ["Harga", "MA50", "MA150", "MA200", "MA200Lalu", "Tinggi52", "Rendah52", "RS"]
    return tt.where(d[bahan].notna().all(axis=1))


def tabel_harian(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Satu baris per (tanggal bar, emiten) berisi indikator, RS, dan TT."""
    ind = {k: indikator(b) for k, b in bars.items() if k != KODE_IHSG and not b.empty}
    if not ind:
        return pd.DataFrame()
    kalender = pd.DatetimeIndex(sorted(set().union(*(i.index for i in ind.values()))))
    rs = peringkat_rs({k: i["RSMentah"] for k, i in ind.items()}, kalender)
    potongan = []
    for k, i in ind.items():
        i = i.copy()
        i["RS"] = rs[k].reindex(i.index)
        i["Ticker"] = k
        potongan.append(i)
    d = pd.concat(potongan)
    d["TT"] = hitung_tt_vektor(d)
    d.index.name = "Tanggal"
    return d.reset_index()


# ------------------------------------------------------------------ aturan
ATURAN = {
    "swing": ("Swing lama (RSI ≤ 65, > MA200, VolSpike ≥ 1,2)",
              lambda d: (d["RSI14"] <= 65) & (d["Harga"] > d["MA200"]) & (d["VolSpike"] >= 1.2)),
    "tt8": ("TT = 8", lambda d: d["TT"] == 8),
    "tt7": ("TT ≥ 7", lambda d: d["TT"] >= 7),
    "rs80": ("RS ≥ 80 saja", lambda d: d["RS"] >= 80),
}
# Pembanding portofolio: semua saham likuid, slot diisi acak.
ACAK = ("acak", "Saham likuid acak (pembanding)", lambda d: pd.Series(True, index=d.index))


def sinyal(harian: pd.DataFrame, uji, mulai: str, sampai: str | None) -> pd.DataFrame:
    """Baris harian yang lolos satu aturan plus syarat likuiditas."""
    t = harian["Tanggal"]
    jaga = (t >= pd.Timestamp(mulai)) & (harian["Nilai"] >= NILAI_MIN)
    if sampai:
        jaga &= t <= pd.Timestamp(sampai)
    lolos = uji(harian).fillna(False).astype(bool) & jaga
    return harian.loc[lolos, ["Tanggal", "Ticker", "Harga"]].reset_index(drop=True)


def pasar_di_atas_ma(ihsg: pd.DataFrame | None) -> dict[str, bool]:
    """Tanggal ISO -> IHSG di atas MA50 pada penutupan tanggal itu.

    Sama dengan IHSGdiAtasMA50 di pembanding() dan hasil/pasar.json: dibaca
    pada malam sinyal, jadi keputusan beli besok paginya tidak melihat apa
    pun sesudah penutupan itu.
    """
    if ihsg is None or ihsg.empty:
        return {}
    c = ihsg.set_index("Tanggal")["Close"]
    ma = c.rolling(MA_PASAR).mean()
    return {t: bool(x > m) for t, x, m in zip(c.index, c, ma) if pd.notna(m)}


def ke_riwayat(s: pd.DataFrame) -> pd.DataFrame:
    """Sinyal -> format arsip pick uji_winrate (cap waktu 18:00 WIB)."""
    tgl = s["Tanggal"].dt.strftime("%Y-%m-%d")
    return pd.DataFrame({
        "Tanggal": tgl,
        "Waktu": tgl + "T11:00:00Z",
        "Ticker": s["Ticker"],
        "Nama": "", "Status": "", "Skor": "",
        "HargaScreening": s["Harga"],
    })


# ------------------------------------------------------------------ per sinyal
def ringkas_sinyal(posisi: pd.DataFrame, banding: pd.DataFrame, hari: int,
                   sorot=HARI_SOROT) -> list[dict]:
    """Baris ringkasan untuk hari ke-5/10/21, memakai ringkas() uji_winrate.

    SelisihSE% adalah galat baku selisih yang dihitung per TANGGAL beli, bukan
    per posisi: pick yang dibeli di sesi yang sama bergerak bersama (pasar
    yang sama, sektor yang sering sama), jadi memperlakukannya sebagai
    sampel bebas membuat angkanya tampak jauh lebih pasti dari aslinya.
    Kasarnya, selisih yang kurang dari dua kali SE belum bisa dibedakan dari nol.

    Tiga kolom ketahanan menjawab "apakah rata-ratanya diangkat segelintir
    saham?" — pertanyaan yang penting justru karena bias survivorship:
    saham yang naik ratusan persen ada di universe hari ini KARENA kenaikan
    itu, dan aturan momentum paling rajin membelinya.
      MedianSelisih%     median selisih per posisi
      SelisihPangkas%    rata-rata sesudah membuang 5% posisi teratas DAN
                         terbawah (sama untuk semua aturan, jadi adil)
      SelisihTanpa10%    rata-rata sesudah membuang seluruh posisi dari 10
                         emiten yang total selisihnya paling besar
    """
    if posisi.empty:
        return [{"Hari": n, "Posisi": 0} for n in sorot]
    tabel = ringkas(posisi, hari, banding).set_index("Hari")
    dasar = posisi[posisi["Ulang"] != "Ya"]
    b = banding.set_index("TanggalBeli")
    keluar = []
    for n in sorot:
        if n not in tabel.index:
            continue
        r = tabel.loc[n]
        kol = f"Hari{n}%"
        x = dasar[["TanggalBeli", "Ticker", kol]].dropna()
        acak = pd.to_numeric(x["TanggalBeli"].map(b[f"Acak{n}%"]), errors="coerce")
        sel = (x[kol] - acak).dropna()
        per_tgl = sel.groupby(x.loc[sel.index, "TanggalBeli"]).mean()
        se = (float(per_tgl.std(ddof=1) / np.sqrt(len(per_tgl)))
              if len(per_tgl) > 1 else None)
        median_sel = pangkas = tanpa10 = None
        if len(sel):
            median_sel = round(float(sel.median()), 2)
            bawah, atas = sel.quantile(0.05), sel.quantile(0.95)
            pangkas = round(float(sel[(sel >= bawah) & (sel <= atas)].mean()), 2)
            emiten = x.loc[sel.index, "Ticker"]
            top = sel.groupby(emiten).sum().nlargest(10).index
            sisa = sel[~emiten.isin(top)]
            tanpa10 = round(float(sisa.mean()), 2) if len(sisa) else None
        keluar.append({
            "Hari": n,
            "Posisi": int(r["Posisi"]),
            "TanggalBeli": int(x["TanggalBeli"].nunique()),
            "Winrate%": r["Winrate%"],
            "RataLaba%": r["RataLaba%"],
            "MedianLaba%": r["MedianLaba%"],
            "RataIHSG%": r["RataIHSG%"],
            "RataAcak%": r["RataAcak%"],
            "Selisih%": r["Selisih%"],
            "SelisihSE%": None if se is None else round(se, 2),
            "MenangVsAcak%": r["MenangVsAcak%"],
            "MedianSelisih%": median_sel,
            "SelisihPangkas%": pangkas,
            "SelisihTanpa10%": tanpa10,
        })
    return keluar


def penyumbang(posisi: pd.DataFrame, banding: pd.DataFrame, n: int, jumlah: int = 10) -> pd.DataFrame:
    """Emiten yang paling banyak menyumbang selisih hari ke-n (jumlah, bukan rata-rata)."""
    dasar = posisi[posisi["Ulang"] != "Ya"]
    kol = f"Hari{n}%"
    if dasar.empty or kol not in dasar.columns:
        return pd.DataFrame()
    b = banding.set_index("TanggalBeli")
    acak = pd.to_numeric(dasar["TanggalBeli"].map(b[f"Acak{n}%"]), errors="coerce")
    sel = (dasar[kol] - acak).dropna()
    if sel.empty:
        return pd.DataFrame()
    emiten = dasar.loc[sel.index, "Ticker"]
    g = sel.groupby(emiten)
    total = float(sel.sum())
    t = pd.DataFrame({"Posisi": g.size(), "JumlahSelisih%": g.sum().round(1),
                      "RataSelisih%": g.mean().round(2)})
    # Porsi hanya bermakna bila total selisihnya positif: "37% dari total"
    # sebuah angka negatif terbaca terbalik.
    t["PorsiDariTotal%"] = (t["JumlahSelisih%"] / total * 100).round(1) if total > 0 else None
    return t.nlargest(jumlah, "JumlahSelisih%").reset_index(names="Ticker")


def per_semester(posisi: pd.DataFrame, banding: pd.DataFrame, n: int) -> pd.DataFrame:
    """Selisih hari ke-n per semester tanggal sinyal: apakah keunggulannya konsisten."""
    dasar = posisi[posisi["Ulang"] != "Ya"].copy()
    kol = f"Hari{n}%"
    if dasar.empty or kol not in dasar.columns:
        return pd.DataFrame()
    b = banding.set_index("TanggalBeli")
    dasar["Acak"] = pd.to_numeric(dasar["TanggalBeli"].map(b[f"Acak{n}%"]), errors="coerce")
    dasar = dasar.dropna(subset=[kol, "Acak"])
    t = pd.to_datetime(dasar["Tanggal"])
    dasar["Semester"] = t.dt.year.astype(str) + "-S" + ((t.dt.month > 6) + 1).astype(str)
    g = dasar.groupby("Semester")
    return pd.DataFrame({
        "Posisi": g.size(),
        "RataLaba%": g[kol].mean().round(2),
        "RataAcak%": g["Acak"].mean().round(2),
        "Selisih%": (g[kol].mean() - g["Acak"].mean()).round(2),
    }).reset_index()


# ------------------------------------------------------------------ portofolio
class Pasar:
    """Harga lebar (tanggal × emiten) untuk simulasi portofolio."""

    def __init__(self, bars: dict[str, pd.DataFrame]):
        anggota = {k: b.set_index("Tanggal") for k, b in bars.items()
                   if k != KODE_IHSG and not b.empty}
        ihsg = bars.get(KODE_IHSG)
        if ihsg is not None and not ihsg.empty:
            kal = list(ihsg["Tanggal"])
        else:
            kal = sorted({t for b in anggota.values() for t in b.index})
        self.kalender = kal
        self.posisi_tgl = {t: i for i, t in enumerate(kal)}
        self.kode = sorted(anggota)
        self.kolom = {k: j for j, k in enumerate(self.kode)}
        buka = pd.DataFrame({k: b["Open"] for k, b in anggota.items()}).reindex(kal)
        tutup = pd.DataFrame({k: b["Close"] for k, b in anggota.items()}).reindex(kal)
        self.buka = buka[self.kode].to_numpy(dtype=float)
        # Nilai harian posisi memakai penutupan terakhir yang ada: emiten yang
        # disuspensi tidak berubah nilainya, bukan jatuh ke nol.
        self.tutup = tutup[self.kode].ffill().to_numpy(dtype=float)
        self.ihsg = (ihsg.set_index("Tanggal")["Close"].reindex(kal).ffill().to_numpy(dtype=float)
                     if ihsg is not None and not ihsg.empty else None)


def portofolio(pasar: Pasar, sinyal_per_tgl: dict[str, list[str]], mulai: str,
               slot: int, hari: int, fee_beli: float, fee_jual: float,
               rng: np.random.Generator, pasar_ok: dict[str, bool] | None = None) -> dict:
    """Simulasi satu portofolio; kembalikan metrik dan kurva ekuitasnya.

    Aturannya:
    - Sinyal malam t dibeli di pembukaan sesi berikutnya (bar kalender t+1),
      hanya bila emitennya bertransaksi hari itu dan belum sedang dipegang.
    - Tiap posisi baru mendapat 1/slot dari ekuitas penutupan malam sinyal
      (kas + nilai posisi), dibatasi kas yang ada. Tanpa pembulatan lot:
      di skala portofolio sisa lot cuma menambah derau.
    - Sinyal lebih banyak dari slot kosong: urutannya diacak dengan `rng`.
    - Dijual di penutupan hari bursa ke-`hari` sesudah beli (kalender IHSG);
      kasnya baru bisa dipakai besok paginya.
    - pasar_ok (filter IHSG > MA50): sinyal malam yang IHSG-nya di bawah MA50
      tidak dibeli. Posisi yang sudah dipegang tidak disuruh keluar.
    Biaya beli dan jual sama dengan uji winrate.
    """
    fb, fj = 1 + fee_beli / 100, 1 - fee_jual / 100
    kal = pasar.kalender
    k0 = next((i for i, t in enumerate(kal) if t >= mulai), len(kal))
    k0 = max(k0, 1)
    kas = 1.0
    pegang: list[list] = []          # [kolom, lembar, k_jual]
    dipegang: set[int] = set()
    ekuitas, isi = [], []
    beli_n = 0
    for k in range(k0, len(kal)):
        nilai_lalu = kas + sum(p[1] * pasar.tutup[k - 1, p[0]] for p in pegang)
        kosong = slot - len(pegang)
        t_sinyal = kal[k - 1]
        boleh = pasar_ok is None or pasar_ok.get(t_sinyal, False)
        if kosong > 0 and boleh and t_sinyal >= mulai:
            calon = [pasar.kolom[c] for c in sinyal_per_tgl.get(t_sinyal, ())
                     if c in pasar.kolom]
            calon = [j for j in calon if j not in dipegang
                     and pasar.buka[k, j] > 0 and not np.isnan(pasar.buka[k, j])]
            if len(calon) > kosong:
                calon = list(rng.permutation(calon))
            jatah = nilai_lalu / slot
            for j in calon[:kosong]:
                dana = min(jatah, kas)
                if dana <= 1e-9:
                    break
                pegang.append([j, dana / (pasar.buka[k, j] * fb), k + hari])
                dipegang.add(j)
                kas -= dana
                beli_n += 1
        sisa = []
        for p in pegang:
            if p[2] <= k:
                kas += p[1] * pasar.tutup[k, p[0]] * fj
                dipegang.discard(p[0])
            else:
                sisa.append(p)
        pegang = sisa
        isi.append(len(pegang))
        ekuitas.append(kas + sum(p[1] * pasar.tutup[k, p[0]] for p in pegang))
    return metrik_ekuitas(pd.Series([1.0] + ekuitas, index=kal[k0 - 1:]), isi, slot, beli_n)


def metrik_ekuitas(e: pd.Series, isi=None, slot: int = SLOT, beli_n: int | None = None) -> dict:
    """Total hasil, CAGR, drawdown terdalam (beserta tanggalnya), keterisian slot."""
    if len(e) < 2:
        return {"Total%": None, "CAGR%": None, "MaxDD%": None, "Puncak": None, "Lembah": None,
                "Keterisian%": None, "Transaksi": beli_n, "ekuitas": e}
    dd = e / e.cummax() - 1
    lembah = dd.idxmin()
    puncak = e.loc[:lembah].idxmax()
    tahun = (pd.Timestamp(e.index[-1]) - pd.Timestamp(e.index[0])).days / 365.25
    return {
        "Total%": round((e.iloc[-1] - 1) * 100, 2),
        "CAGR%": round((e.iloc[-1] ** (1 / tahun) - 1) * 100, 2) if tahun > 0 and e.iloc[-1] > 0 else None,
        "MaxDD%": round(float(dd.min()) * 100, 2),
        "Puncak": puncak,
        "Lembah": lembah,
        "Keterisian%": round(float(np.mean(isi)) / slot * 100, 1) if isi else None,
        "Transaksi": beli_n,
        "ekuitas": e,
    }


# ------------------------------------------------------------------ keluaran
# Kolom yang ditulis dengan tanda +/− (laba, selisih); kolom persen lain
# (winrate, keterisian) tanpa tanda. Angka bergaya Indonesia: koma desimal.
_BERTANDA = {"RataLaba%", "MedianLaba%", "RataIHSG%", "RataAcak%", "Selisih%", "CAGR%Median",
             "MedianSelisih%", "SelisihPangkas%", "SelisihTanpa10%", "JumlahSelisih%",
             "RataSelisih%"}


def _angka_id(v: float, desimal: int, tanda: bool) -> str:
    teks = f"{abs(v):,.{desimal}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if v < 0:
        return "−" + teks
    return ("+" if tanda and v > 0 else "") + teks


def tabel_md(df: pd.DataFrame) -> str:
    """DataFrame -> tabel Markdown sederhana (tanpa dependensi tabulate)."""
    def sel(kolom, v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "–"
        if isinstance(v, (int, np.integer)):
            return _angka_id(float(v), 0, False)
        if isinstance(v, (float, np.floating)):
            if kolom in _BERTANDA:
                return _angka_id(float(v), 2, True)
            if kolom == "SelisihSE%":
                return "±" + _angka_id(float(v), 2, False)
            return _angka_id(float(v), 1, False)
        return str(v)
    kepala = "| " + " | ".join(df.columns) + " |"
    garis = "|" + "|".join("---" for _ in df.columns) + "|"
    isi = ["| " + " | ".join(sel(k, v) for k, v in zip(df.columns, r)) + " |"
           for r in df.itertuples(index=False)]
    return "\n".join([kepala, garis, *isi])


def tulis_md(path: Path, meta: dict, sinyal_df: pd.DataFrame, porto_df: pd.DataFrame,
             semester_df: pd.DataFrame, penyumbang_df: pd.DataFrame | None = None) -> None:
    s = sinyal_df.copy()
    baris = ["# Uji Ulang Tren vs Swing", "",
             f"Dihitung {meta['diperbarui']} oleh `uji_ulang_tren.py`. "
             f"Sinyal {meta['sinyalPertama']} – {meta['sinyalTerakhir']}, "
             f"{meta['emitenDenganHarga']} emiten ber-harga dari universe {meta['universe']} emiten.", "",
             "> ⚠️ **Bias survivorship.** Universe-nya daftar emiten *hari ini* (400 emiten terbesar "
             "per hari ini + daftar kurasi). Emiten yang dulu naik lalu ambruk, mengecil, atau "
             "delisting tidak ada di data. Angka absolutnya terlalu bagus, dan biasnya lebih besar "
             "untuk aturan momentum (TT/RS) yang membeli sesudah saham naik kencang. Kolom selisih "
             "terhadap saham acak (universe yang sama) menghapus sebagian bias itu, tidak seluruhnya.",
             "", "## Per sinyal: selisih vs saham likuid acak", "",
             "Aturan uji winrate: beli di pembukaan sesi sesudah sinyal, biaya 0,15% + 0,25%, "
             "pick ulang tidak dihitung. `SelisihSE%` = galat baku per tanggal beli; selisih yang "
             "kurang dari ±2×SE belum bisa dibedakan dari nol.", ""]
    for n in HARI_SOROT:
        bagian = s[s["Hari"] == n][["Aturan", "Filter", "Posisi", "Winrate%", "RataLaba%",
                                    "RataAcak%", "Selisih%", "SelisihSE%", "MenangVsAcak%"]]
        baris += [f"### Hari bursa ke-{n}", "", tabel_md(bagian), ""]
    baris += ["## Ketahanan: apakah selisihnya datang dari segelintir saham?", "",
              "Hari bursa ke-21. `MedianSelisih%` = median per posisi; `SelisihPangkas%` = rata-rata "
              "sesudah membuang 5% posisi teratas dan terbawah; `SelisihTanpa10%` = rata-rata sesudah "
              "membuang semua posisi dari 10 emiten penyumbang selisih terbesar. Kalau selisih rata-rata "
              "positif tapi ketiga kolom ini mendekati nol atau negatif, keunggulannya bergantung pada "
              "beberapa saham yang meledak — persis bagian yang paling rawan bias survivorship.", "",
              tabel_md(s[s["Hari"] == HARI_SOROT[-1]][["Aturan", "Filter", "Posisi", "Selisih%",
                                                        "MedianSelisih%", "SelisihPangkas%",
                                                        "SelisihTanpa10%", "MenangVsAcak%"]]), ""]
    if penyumbang_df is not None and not penyumbang_df.empty:
        baris += ["### 10 penyumbang selisih terbesar (hari ke-21, tanpa filter)", ""]
        for aturan, g in penyumbang_df.groupby("Aturan", sort=False):
            baris += [f"**{aturan}**", "", tabel_md(g.drop(columns=["Aturan"])), ""]
    baris += ["## Portofolio 10 posisi, tahan 21 hari bursa", "",
              f"Median dari {meta['seed']} urutan acak pengisian slot (rentang min–maks dalam kurung). "
              "Ekuitas awal 1, tanpa pembulatan lot.", ""]
    p = porto_df.copy()
    def rentang(m, a, b):
        return f"{_angka_id(m, 1, True)} ({_angka_id(a, 1, True)} … {_angka_id(b, 1, True)})"
    p["MaxDD%"] = [rentang(*x) for x in zip(p["MaxDD%Median"], p["MaxDD%Min"], p["MaxDD%Maks"])]
    p["Total%"] = [rentang(*x) for x in zip(p["Total%Median"], p["Total%Min"], p["Total%Maks"])]
    baris += [tabel_md(p[["Aturan", "Filter", "MaxDD%", "Total%", "CAGR%Median",
                          "Keterisian%", "TransaksiMedian"]]), ""]
    if meta.get("ihsg"):
        i = meta["ihsg"]
        baris += [f"IHSG beli-dan-tahan di periode yang sama: total {_angka_id(i['Total%'], 1, True)}%, "
                  f"drawdown terdalam {_angka_id(i['MaxDD%'], 1, True)}% "
                  f"({i['Puncak']} → {i['Lembah']}).", ""]
    baris += ["## Selisih hari ke-21 per semester (tanpa filter)", "",
              tabel_md(semester_df[semester_df["Filter"] == FILTER["tanpa"]]
                       .drop(columns=["Filter"])), ""]
    path.write_text("\n".join(baris) + "\n")


# ------------------------------------------------------------------ CLI
def main() -> int:
    p = argparse.ArgumentParser(
        description="Uji ulang historis Trend Template / RS vs daftar swing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Pemakaian:")[1] if "Pemakaian:" in __doc__ else None,
    )
    p.add_argument("--mulai", default=MULAI_DEFAULT, help=f"tanggal sinyal pertama (default {MULAI_DEFAULT})")
    p.add_argument("--sampai", help="tanggal sinyal terakhir (default: data terakhir)")
    p.add_argument("--tickers", nargs="+", default=DAFTAR_DEFAULT,
                   help="daftar ticker (default: daftar screening malam)")
    p.add_argument("--harga-csv", help="baca harga dari CSV (format uji_winrate, plus AdjClose opsional)")
    p.add_argument("--simpan-harga", help="simpan harga yang ditarik ke CSV ini")
    p.add_argument("--modal", type=int, default=MODAL_DEFAULT)
    p.add_argument("--hari", type=int, default=HARI_DEFAULT)
    p.add_argument("--fee-beli", type=float, default=FEE_BELI)
    p.add_argument("--fee-jual", type=float, default=FEE_JUAL)
    p.add_argument("--slot", type=int, default=SLOT, help=f"jumlah posisi portofolio (default {SLOT})")
    p.add_argument("--seed", type=int, default=SEED_DEFAULT,
                   help=f"jumlah urutan acak portofolio (default {SEED_DEFAULT})")
    p.add_argument("--output-dir", default="hasil")
    p.add_argument("--awalan", default="uji_ulang_tren", help="awalan nama berkas keluaran")
    a = p.parse_args()

    if a.harga_csv:
        print(f"Membaca harga dari {a.harga_csv} ...", file=sys.stderr)
        harga = pd.read_csv(a.harga_csv, dtype={"Ticker": str, "Tanggal": str})
        universe = sorted(set(harga["Ticker"]) - {KODE_IHSG})
    else:
        daftar, _ = baca_daftar_ticker(a.tickers)
        universe = [t.removesuffix(".JK") for t in daftar]
        mulai_tarik = date.fromisoformat(a.mulai) - timedelta(days=MUNDUR_HARI)
        print(f"Menarik harga {len(universe) + 1} simbol sejak {mulai_tarik} ...", file=sys.stderr)
        harga = ambil_harga(universe + [KODE_IHSG], mulai_tarik, adj=True)
        if a.simpan_harga:
            harga.to_csv(a.simpan_harga, index=False)
    if harga.empty:
        print("Tidak ada data harga.", file=sys.stderr)
        return 1

    bars = selaraskan_kalender(per_emiten(harga))
    print("Menghitung indikator per tanggal ...", file=sys.stderr)
    harian = tabel_harian(bars)
    ok = pasar_di_atas_ma(bars.get(KODE_IHSG))

    semua_aturan = [(k, label, uji) for k, (label, uji) in ATURAN.items()]
    sinyal_aturan = {k: sinyal(harian, uji, a.mulai, a.sampai) for k, _, uji in semua_aturan}

    # ---- per sinyal
    print("Simulasi per sinyal ...", file=sys.stderr)
    posisi_aturan = {}
    for k, label, _ in semua_aturan:
        for f in FILTER:
            s = sinyal_aturan[k]
            if f == "ihsg":
                s = s[s["Tanggal"].dt.strftime("%Y-%m-%d").map(ok).fillna(False).astype(bool)]
            pos = simulasi(ke_riwayat(s), bars, a.modal, a.hari, a.fee_beli, a.fee_jual) \
                if not s.empty else pd.DataFrame()
            posisi_aturan[(k, f)] = (pos, len(s))
    tgl_beli = sorted({t for pos, _ in posisi_aturan.values() if not pos.empty
                       for t in pos["TanggalBeli"]})
    banding = pembanding(tgl_beli, bars, set(bars) - {KODE_IHSG}, a.hari, a.fee_beli, a.fee_jual)

    hari_bursa = harian.loc[harian["Tanggal"] >= pd.Timestamp(a.mulai), "Tanggal"].nunique()
    baris_sinyal, baris_semester, baris_penyumbang = [], [], []
    for k, label, _ in semua_aturan:
        for f, nama_f in FILTER.items():
            pos, n_sinyal = posisi_aturan[(k, f)]
            for r in ringkas_sinyal(pos, banding, a.hari):
                baris_sinyal.append({"Aturan": label, "Kode": k, "Filter": nama_f,
                                     "SinyalPerHari": round(n_sinyal / max(hari_bursa, 1), 1), **r})
            if not pos.empty and f == "tanpa":
                py = penyumbang(pos, banding, a.hari)
                if not py.empty:
                    py.insert(0, "Aturan", label)
                    baris_penyumbang.append(py)
            if not pos.empty:
                sm = per_semester(pos, banding, a.hari)
                if not sm.empty:
                    sm.insert(0, "Filter", nama_f)
                    sm.insert(0, "Aturan", label)
                    baris_semester.append(sm)
    sinyal_df = pd.DataFrame(baris_sinyal)
    semester_df = pd.concat(baris_semester, ignore_index=True) if baris_semester else pd.DataFrame()
    penyumbang_df = (pd.concat(baris_penyumbang, ignore_index=True)
                     if baris_penyumbang else pd.DataFrame())

    # ---- portofolio
    print(f"Simulasi portofolio ({a.seed} urutan acak per aturan) ...", file=sys.stderr)
    pasar = Pasar(bars)
    likuid = harian[(harian["Tanggal"] >= pd.Timestamp(a.mulai)) & (harian["Nilai"] >= NILAI_MIN)]
    if a.sampai:
        likuid = likuid[likuid["Tanggal"] <= pd.Timestamp(a.sampai)]

    def per_tgl(s: pd.DataFrame) -> dict[str, list[str]]:
        t = s["Tanggal"].dt.strftime("%Y-%m-%d")
        return {tg: list(g) for tg, g in s["Ticker"].groupby(t)}

    kelompok = [(k, label, per_tgl(sinyal_aturan[k])) for k, label, _ in semua_aturan]
    kelompok.append((ACAK[0], ACAK[1], per_tgl(likuid)))
    baris_porto, kurva = [], {}
    for k, label, spt in kelompok:
        for f, nama_f in FILTER.items():
            hasil = [portofolio(pasar, spt, a.mulai, a.slot, a.hari, a.fee_beli, a.fee_jual,
                                np.random.default_rng(seed), ok if f == "ihsg" else None)
                     for seed in range(a.seed)]
            kurva[f"{k}|{f}"] = hasil[0]["ekuitas"]
            dd = [h["MaxDD%"] for h in hasil if h["MaxDD%"] is not None]
            tot = [h["Total%"] for h in hasil if h["Total%"] is not None]
            cagr = [h["CAGR%"] for h in hasil if h["CAGR%"] is not None]
            if not dd:
                continue
            tengah = hasil[int(np.argsort(dd)[len(dd) // 2])]
            baris_porto.append({
                "Aturan": label, "Kode": k, "Filter": nama_f,
                "MaxDD%Median": round(float(np.median(dd)), 2),
                "MaxDD%Min": round(min(dd), 2), "MaxDD%Maks": round(max(dd), 2),
                "Total%Median": round(float(np.median(tot)), 2),
                "Total%Min": round(min(tot), 2), "Total%Maks": round(max(tot), 2),
                "CAGR%Median": round(float(np.median(cagr)), 2) if cagr else None,
                "PuncakDD": tengah["Puncak"], "LembahDD": tengah["Lembah"],
                "Keterisian%": float(np.median([h["Keterisian%"] for h in hasil])),
                "TransaksiMedian": int(np.median([h["Transaksi"] for h in hasil])),
            })
    porto_df = pd.DataFrame(baris_porto)
    ekuitas_df = pd.DataFrame(kurva).round(4)
    ekuitas_df.index.name = "Tanggal"

    ihsg_meta = None
    if pasar.ihsg is not None:
        k0 = max(next((i for i, t in enumerate(pasar.kalender) if t >= a.mulai), 1), 1)
        e = pd.Series(pasar.ihsg[k0 - 1:] / pasar.ihsg[k0 - 1], index=pasar.kalender[k0 - 1:])
        m = metrik_ekuitas(e)
        ihsg_meta = {"Total%": m["Total%"], "MaxDD%": m["MaxDD%"],
                     "Puncak": m["Puncak"], "Lembah": m["Lembah"]}

    keluar = Path(a.output_dir)
    keluar.mkdir(parents=True, exist_ok=True)
    awal = a.awalan
    sinyal_df.to_csv(keluar / f"{awal}_sinyal.csv", index=False)
    semester_df.to_csv(keluar / f"{awal}_semester.csv", index=False)
    penyumbang_df.to_csv(keluar / f"{awal}_penyumbang.csv", index=False)
    porto_df.to_csv(keluar / f"{awal}_portofolio.csv", index=False)
    ekuitas_df.to_csv(keluar / f"{awal}_ekuitas.csv")
    t_sinyal = pd.concat([s["Tanggal"] for s in sinyal_aturan.values()])
    meta = {
        "diperbarui": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mulai": a.mulai,
        "sampai": a.sampai,
        "sinyalPertama": t_sinyal.min().date().isoformat() if len(t_sinyal) else None,
        "sinyalTerakhir": t_sinyal.max().date().isoformat() if len(t_sinyal) else None,
        "hariBursa": int(hari_bursa),
        "universe": len(universe),
        "emitenDenganHarga": len([k for k in bars if k != KODE_IHSG]),
        "modal": a.modal, "hari": a.hari, "feeBeli": a.fee_beli, "feeJual": a.fee_jual,
        "slot": a.slot, "seed": a.seed, "nilaiMin": NILAI_MIN, "maPasar": MA_PASAR,
        "ihsg": ihsg_meta,
        "biasSurvivorship": ("Universe = daftar emiten hari ini; emiten yang delisting, "
                             "mengecil, atau keluar dari 400 terbesar tidak ada di data."),
    }
    (keluar / f"{awal}_meta.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")
    tulis_md(keluar / f"{awal}.md", meta, sinyal_df, porto_df, semester_df, penyumbang_df)

    # ---- ringkasan terminal
    print(f"\nSinyal {meta['sinyalPertama']} – {meta['sinyalTerakhir']}, "
          f"{meta['emitenDenganHarga']} emiten.", file=sys.stderr)
    print(f"{'Aturan':<14}{'Filter':<14}{'Hari':>5}{'Posisi':>8}{'Rata':>8}{'Acak':>8}"
          f"{'Selisih':>9}{'SE':>7}", file=sys.stderr)
    for r in baris_sinyal:
        if r.get("Posisi"):
            print(f"{r['Kode']:<14}{r['Filter']:<14}{r['Hari']:>5}{r['Posisi']:>8}"
                  f"{r['RataLaba%']:>+8.2f}{(r['RataAcak%'] or 0):>+8.2f}"
                  f"{(r['Selisih%'] or 0):>+9.2f}{(r['SelisihSE%'] or 0):>7.2f}", file=sys.stderr)
    print(f"\n{'Portofolio':<14}{'Filter':<14}{'MaxDD med':>10}{'Total med':>11}", file=sys.stderr)
    for r in baris_porto:
        print(f"{r['Kode']:<14}{r['Filter']:<14}{r['MaxDD%Median']:>+10.1f}{r['Total%Median']:>+11.1f}",
              file=sys.stderr)
    if ihsg_meta:
        print(f"{'IHSG':<28}{ihsg_meta['MaxDD%']:>+10.1f}{ihsg_meta['Total%']:>+11.1f}", file=sys.stderr)
    print(f"\nDisimpan di {keluar}/{awal}_*.csv, .json, .md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
