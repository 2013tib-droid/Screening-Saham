#!/usr/bin/env python3
"""Uji ulang filter pasar untuk daftar swing: MA50 vs FTD, distribution day, breadth.

Aturan yang dipakai sekarang: posisi swing baru hanya dibuka saat IHSG di
atas MA50-nya (README "Kondisi Pasar"). Berkas ini menguji apakah filter lain
— atau tambahan di atas MA50 — memperbaikinya:

    tanpa         tanpa filter pasar
    ma50          IHSG > MA50                         (aturan sekarang)
    ftd           keadaan NAIK sejak follow-through day terakhir
    ma50+ftd      keduanya
    dd5           distribution day aktif < 5          ("tahan bila DD ≥ 5")
    ma50+dd5      keduanya
    breadth       > 50% saham likuid di atas MA50-nya
    ma50+breadth  keduanya

Semua filter dibaca pada penutupan malam sinyal, jadi keputusan beli besok
paginya tidak melihat apa pun sesudah penutupan itu. Definisi DD/FTD persis
hitung_dd_ftd() di screener.py; breadth persis hitung_breadth() di
screener.py, dihitung ulang dari harga yang sama (hasil/breadth.csv baru
mulai Desember 2024 dan MA50-nya baru terisi Februari 2025 — tidak menutup
April 2024; selisihnya terhadap berkas itu di tanggal yang tumpang tindih
dicatat di meta).

Sinyal dan simulasinya sama dengan uji_ulang_tren.py (aturan swing.csv,
nilai ≥ Rp5 M; per sinyal lewat simulasi()/pembanding() uji_winrate; per
portofolio 10 slot, tahan 21 hari bursa, urutan acak diulang --seed kali).
Yang dibaca:
    - drawdown terdalam dan total hasil portofolio 10 posisi
    - selisih per sinyal vs saham likuid acak di hari bursa ke-21
    - HariBoleh%: porsi hari bursa yang filternya mengizinkan beli. Filter
      yang menahan beli lebih sering hampir pasti memangkas drawdown; itu
      belum berarti ia lebih pintar.

⚠️ Bias survivorship sama dengan uji_ulang_tren.py: universe = emiten hari ini.

Pemakaian:
    python uji_ulang_pasar.py                          # tarik harga dari Yahoo
    python uji_ulang_pasar.py --harga-csv h.csv        # tanpa jaringan
    python uji_ulang_pasar.py --mulai 2025-01-01 --seed 50

Keluaran (di --output-dir, bawaan hasil/):
    uji_ulang_pasar_sinyal.csv      per filter × hari ke-5/10/21
    uji_ulang_pasar_portofolio.csv  drawdown & hasil portofolio, swing dan saham acak
    uji_ulang_pasar_harian.csv      keadaan tiap filter per hari bursa
    uji_ulang_pasar_meta.json       parameter, cakupan, jumlah FTD/DD
    uji_ulang_pasar.md              ringkasan
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from screener import (
    DAFTAR_DEFAULT, DD_BATAS, baca_daftar_ticker, hitung_breadth, hitung_dd_ftd,
)
from uji_ulang_tren import (
    ACAK, ATURAN, MUNDUR_HARI, NILAI_MIN, SEED_DEFAULT, SLOT, Pasar, _angka_id,
    ke_riwayat, metrik_ekuitas, pasar_di_atas_ma, portofolio, ringkas_sinyal, sinyal,
    tabel_harian, tabel_md,
)
from uji_winrate import (
    FEE_BELI, FEE_JUAL, HARI_DEFAULT, KODE_IHSG, MODAL_DEFAULT, ambil_harga,
    pembanding, per_emiten, selaraskan_kalender, simulasi,
)

MULAI_DEFAULT = "2024-04-01"
BREADTH_MIN = 50.0   # % saham likuid di atas MA50 — ambang yang disebut README sebelum diuji

FILTER = {
    "tanpa": "Tanpa filter",
    "ma50": "IHSG > MA50",
    "ftd": "Sejak FTD",
    "ma50+ftd": "IHSG > MA50 & sejak FTD",
    "dd5": f"DD aktif < {DD_BATAS}",
    "ma50+dd5": f"IHSG > MA50 & DD < {DD_BATAS}",
    "breadth": f"Breadth > {BREADTH_MIN:g}%",
    "ma50+breadth": f"IHSG > MA50 & breadth > {BREADTH_MIN:g}%",
}


# ------------------------------------------------------------------ keadaan pasar
def keadaan_ihsg(ihsg: pd.DataFrame) -> pd.DataFrame:
    """hitung_dd_ftd() atas bar IHSG format uji_winrate (kolom Tanggal ISO)."""
    b = ihsg.copy()
    b["Volume"] = pd.to_numeric(b["Volume"], errors="coerce")
    b = b[b["Close"].notna() & b["Low"].notna() & (b["Volume"] > 0)]
    b = b.set_index(pd.DatetimeIndex(pd.to_datetime(b["Tanggal"])))[["Close", "Low", "Volume"]]
    return hitung_dd_ftd(b)


def breadth_harian(bars: dict[str, pd.DataFrame]) -> pd.Series:
    """DiAtasMA50% per tanggal ISO, dengan hitung_breadth() screener.py.

    Harga yang dipakai AdjClose bila ada — screener.py membaca history()
    dengan auto_adjust bawaan, jadi itulah yang menghasilkan hasil/breadth.csv.
    """
    seri = {}
    for k, b in bars.items():
        if k == KODE_IHSG or b.empty:
            continue
        c = b["AdjClose"].where(b["AdjClose"].notna(), b["Close"]) if "AdjClose" in b else b["Close"]
        seri[k] = pd.DataFrame({"Close": c.to_numpy(dtype=float),
                                "Volume": b["Volume"].to_numpy(dtype=float)},
                               index=pd.DatetimeIndex(pd.to_datetime(b["Tanggal"])))
    br = hitung_breadth(seri)
    return pd.Series(br["DiAtasMA50%"].to_numpy(dtype=float), index=br["Tanggal"])


def susun_filter(bars: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, dict[str, bool]]]:
    """Tabel harian semua komponen filter + peta tanggal ISO -> boleh beli, per filter."""
    ihsg = bars[KODE_IHSG]
    ma = pasar_di_atas_ma(ihsg)
    kd = keadaan_ihsg(ihsg)
    br = breadth_harian(bars)
    tgl = [t.date().isoformat() for t in kd.index]
    h = pd.DataFrame({
        "Tanggal": tgl,
        "IHSG": ihsg.set_index("Tanggal")["Close"].reindex(tgl).round(2).to_numpy(),
        "DiAtasMA50": [ma.get(t) for t in tgl],
        "DD": kd["DD"].to_numpy(),
        "DDAktif": kd["DDAktif"].to_numpy(),
        "Keadaan": kd["Keadaan"].to_numpy(),
        "HariRally": kd["HariRally"].to_numpy(),
        "FTD": kd["FTD"].to_numpy(),
        "Breadth%": br.reindex(tgl).to_numpy(),
    })
    # Komponen yang belum bisa dihitung (MA50 belum 50 bar, breadth belum
    # terisi) dianggap TIDAK boleh — sama dengan pasar_di_atas_ma().
    m = h["DiAtasMA50"].fillna(False).astype(bool)
    f = h["Keadaan"] == "NAIK"
    d = h["DDAktif"] < DD_BATAS
    b = (h["Breadth%"] > BREADTH_MIN).fillna(False)
    syarat = {
        "tanpa": pd.Series(True, index=h.index),
        "ma50": m, "ftd": f, "ma50+ftd": m & f,
        "dd5": d, "ma50+dd5": m & d,
        "breadth": b, "ma50+breadth": m & b,
    }
    for k, s in syarat.items():
        h[f"ok:{k}"] = s.astype(bool).to_numpy()
    peta = {k: dict(zip(h["Tanggal"], s.astype(bool))) for k, s in syarat.items()}
    return h, peta


def cek_breadth_berkas(br: pd.Series, path: str = "hasil/breadth.csv") -> dict | None:
    """Selisih DiAtasMA50% hitungan ulang vs hasil/breadth.csv di tanggal yang sama."""
    p = Path(path)
    if not p.exists():
        return None
    lama = pd.read_csv(p, dtype={"Tanggal": str}).set_index("Tanggal")["DiAtasMA50%"]
    sama = pd.concat([br.rename("ulang"), lama.rename("berkas")], axis=1, join="inner").dropna()
    if sama.empty:
        return None
    beda = (sama["ulang"] - sama["berkas"]).abs()
    return {"tanggal": int(len(sama)), "dari": sama.index.min(), "sampai": sama.index.max(),
            "rataSelisihPoin": round(float(beda.mean()), 2),
            "maksSelisihPoin": round(float(beda.max()), 2),
            "sisiSamaTerhadap50%": round(float(((sama["ulang"] > BREADTH_MIN)
                                                == (sama["berkas"] > BREADTH_MIN)).mean() * 100), 1)}


# ------------------------------------------------------------------ keluaran
def tulis_md(path: Path, meta: dict, sinyal_df: pd.DataFrame, porto_df: pd.DataFrame) -> None:
    def rentang(m, a, b):
        return f"{_angka_id(m, 1, True)} ({_angka_id(a, 1, True)} … {_angka_id(b, 1, True)})"
    baris = ["# Uji Ulang Filter Pasar untuk Daftar Swing", "",
             f"Dihitung {meta['diperbarui']} oleh `uji_ulang_pasar.py`. Sinyal swing "
             f"{meta['sinyalPertama']} – {meta['sinyalTerakhir']} ({meta['hariBursa']} hari bursa), "
             f"{meta['emitenDenganHarga']} emiten ber-harga.", "",
             "> ⚠️ **Bias survivorship.** Universe = daftar emiten hari ini. Angka absolutnya terlalu "
             "bagus; perbandingan antar-filter lebih bisa dipegang daripada angkanya sendiri.", "",
             "## Portofolio 10 posisi, tahan 21 hari bursa", "",
             f"Median dari {meta['seed']} urutan acak pengisian slot (rentang min–maks dalam kurung). "
             "`HariBoleh%` = porsi hari bursa yang filternya mengizinkan beli.", ""]
    p = porto_df.copy()
    p["MaxDD%"] = [rentang(*x) for x in zip(p["MaxDD%Median"], p["MaxDD%Min"], p["MaxDD%Maks"])]
    p["Total%"] = [rentang(*x) for x in zip(p["Total%Median"], p["Total%Min"], p["Total%Maks"])]
    for kode, judul in (("swing", "Daftar swing"), (ACAK[0], "Saham likuid acak (pembanding)")):
        bagian = p[p["Kode"] == kode]
        baris += [f"### {judul}", "", tabel_md(bagian[["Filter", "HariBoleh%", "MaxDD%", "Total%",
                                                        "CAGR%Median", "Keterisian%",
                                                        "TransaksiMedian"]]), ""]
    if meta.get("ihsg"):
        i = meta["ihsg"]
        baris += [f"IHSG beli-dan-tahan: total {_angka_id(i['Total%'], 1, True)}%, drawdown "
                  f"terdalam {_angka_id(i['MaxDD%'], 1, True)}% ({i['Puncak']} → {i['Lembah']}).", ""]
    baris += ["## Per sinyal: selisih vs saham likuid acak, hari bursa ke-21", "",
              tabel_md(sinyal_df[sinyal_df["Hari"] == 21][
                  ["Filter", "Posisi", "TanggalBeli", "RataLaba%", "RataAcak%", "Selisih%",
                   "SelisihSE%", "MedianSelisih%", "MenangVsAcak%"]]), ""]
    k = meta["keadaan"]
    baris += ["## Keadaan pasar di periode uji", "",
              f"- Follow-through day: {k['jumlahFTD']} kali ({', '.join(k['tanggalFTD']) or '–'}).",
              f"- Hari bursa berkeadaan NAIK (sejak FTD): {_angka_id(k['hariNaik%'], 1, False)}%; "
              f"DD aktif ≥ {DD_BATAS}: {_angka_id(k['hariDD5%'], 1, False)}% hari; "
              f"distribution day: {k['jumlahDD']}.",
              f"- IHSG > MA50: {_angka_id(k['hariMA50%'], 1, False)}% hari; breadth > {BREADTH_MIN:g}%: "
              f"{_angka_id(k['hariBreadth%'], 1, False)}% hari.",
              ""]
    if meta.get("cekBreadth"):
        c = meta["cekBreadth"]
        baris += [f"Breadth hitungan ulang vs `hasil/breadth.csv` ({c['tanggal']} tanggal, "
                  f"{c['dari']} – {c['sampai']}): rata-rata selisih "
                  f"{_angka_id(c['rataSelisihPoin'], 2, False)} poin, maks "
                  f"{_angka_id(c['maksSelisihPoin'], 1, False)}; sisi terhadap {BREADTH_MIN:g}% sama di "
                  f"{_angka_id(c['sisiSamaTerhadap50%'], 1, False)}% tanggal.", ""]
    path.write_text("\n".join(baris) + "\n")


# ------------------------------------------------------------------ CLI
def main() -> int:
    p = argparse.ArgumentParser(description="Uji ulang filter pasar untuk daftar swing.")
    p.add_argument("--mulai", default=MULAI_DEFAULT)
    p.add_argument("--sampai")
    p.add_argument("--tickers", nargs="+", default=DAFTAR_DEFAULT)
    p.add_argument("--harga-csv")
    p.add_argument("--simpan-harga")
    p.add_argument("--modal", type=int, default=MODAL_DEFAULT)
    p.add_argument("--hari", type=int, default=HARI_DEFAULT)
    p.add_argument("--fee-beli", type=float, default=FEE_BELI)
    p.add_argument("--fee-jual", type=float, default=FEE_JUAL)
    p.add_argument("--slot", type=int, default=SLOT)
    p.add_argument("--seed", type=int, default=SEED_DEFAULT)
    p.add_argument("--breadth-csv", default="hasil/breadth.csv",
                   help="berkas breadth untuk pemeriksaan silang (bukan sumber filter)")
    p.add_argument("--output-dir", default="hasil")
    p.add_argument("--awalan", default="uji_ulang_pasar")
    a = p.parse_args()

    if a.harga_csv:
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
    bars = selaraskan_kalender(per_emiten(harga))
    if KODE_IHSG not in bars or bars[KODE_IHSG].empty:
        print("IHSG tidak ada di data harga — filter pasar tidak bisa diuji.", file=sys.stderr)
        return 1
    v = pd.to_numeric(bars[KODE_IHSG]["Volume"], errors="coerce")
    if (v > 0).mean() < 0.95:
        # Permintaannya eksplisit: kalau volume IHSG tidak layak, berhenti —
        # jangan diganti proksi diam-diam.
        print(f"Volume IHSG hanya terisi di {(v > 0).mean():.0%} bar — DD/FTD tidak bisa "
              "dihitung dengan jujur. Berhenti.", file=sys.stderr)
        return 1

    print("Menghitung indikator & keadaan pasar ...", file=sys.stderr)
    harian = tabel_harian(bars)
    keadaan, peta = susun_filter(bars)
    s_swing = sinyal(harian, ATURAN["swing"][1], a.mulai, a.sampai)

    periode = keadaan[keadaan["Tanggal"] >= a.mulai]
    if a.sampai:
        periode = periode[periode["Tanggal"] <= a.sampai]
    boleh_pct = {k: round(float(periode[f"ok:{k}"].mean() * 100), 1) for k in FILTER}

    # ---- per sinyal
    print("Simulasi per sinyal ...", file=sys.stderr)
    posisi = {}
    for f in FILTER:
        s = s_swing[s_swing["Tanggal"].dt.strftime("%Y-%m-%d").map(peta[f]).fillna(False).astype(bool)]
        posisi[f] = (simulasi(ke_riwayat(s), bars, a.modal, a.hari, a.fee_beli, a.fee_jual)
                     if not s.empty else pd.DataFrame())
    tgl_beli = sorted({t for pos in posisi.values() if not pos.empty for t in pos["TanggalBeli"]})
    banding = pembanding(tgl_beli, bars, set(bars) - {KODE_IHSG}, a.hari, a.fee_beli, a.fee_jual)
    baris_sinyal = []
    for f, nama in FILTER.items():
        for r in ringkas_sinyal(posisi[f], banding, a.hari):
            baris_sinyal.append({"Filter": nama, "Kode": f, "HariBoleh%": boleh_pct[f], **r})
    sinyal_df = pd.DataFrame(baris_sinyal)

    # ---- portofolio
    print(f"Simulasi portofolio ({a.seed} urutan acak) ...", file=sys.stderr)
    pasar = Pasar(bars)
    likuid = harian[(harian["Tanggal"] >= pd.Timestamp(a.mulai)) & (harian["Nilai"] >= NILAI_MIN)]
    if a.sampai:
        likuid = likuid[likuid["Tanggal"] <= pd.Timestamp(a.sampai)]

    def per_tgl(s: pd.DataFrame) -> dict[str, list[str]]:
        t = s["Tanggal"].dt.strftime("%Y-%m-%d")
        return {tg: list(g) for tg, g in s["Ticker"].groupby(t)}

    baris_porto = []
    for kode, spt in (("swing", per_tgl(s_swing)), (ACAK[0], per_tgl(likuid))):
        for f, nama in FILTER.items():
            hasil = [portofolio(pasar, spt, a.mulai, a.slot, a.hari, a.fee_beli, a.fee_jual,
                                np.random.default_rng(seed), None if f == "tanpa" else peta[f])
                     for seed in range(a.seed)]
            dd = [h["MaxDD%"] for h in hasil if h["MaxDD%"] is not None]
            tot = [h["Total%"] for h in hasil if h["Total%"] is not None]
            cagr = [h["CAGR%"] for h in hasil if h["CAGR%"] is not None]
            if not dd:
                continue
            tengah = hasil[int(np.argsort(dd)[len(dd) // 2])]
            baris_porto.append({
                "Kode": kode, "Filter": nama, "KodeFilter": f, "HariBoleh%": boleh_pct[f],
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

    ihsg_meta = None
    if pasar.ihsg is not None:
        k0 = max(next((i for i, t in enumerate(pasar.kalender) if t >= a.mulai), 1), 1)
        e = pd.Series(pasar.ihsg[k0 - 1:] / pasar.ihsg[k0 - 1], index=pasar.kalender[k0 - 1:])
        m = metrik_ekuitas(e)
        ihsg_meta = {"Total%": m["Total%"], "MaxDD%": m["MaxDD%"],
                     "Puncak": m["Puncak"], "Lembah": m["Lembah"]}

    br = keadaan.set_index("Tanggal")["Breadth%"].dropna()
    meta = {
        "diperbarui": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mulai": a.mulai, "sampai": a.sampai,
        "sinyalPertama": s_swing["Tanggal"].min().date().isoformat() if len(s_swing) else None,
        "sinyalTerakhir": s_swing["Tanggal"].max().date().isoformat() if len(s_swing) else None,
        "hariBursa": int(len(periode)),
        "universe": len(universe),
        "emitenDenganHarga": len([k for k in bars if k != KODE_IHSG]),
        "modal": a.modal, "hari": a.hari, "feeBeli": a.fee_beli, "feeJual": a.fee_jual,
        "slot": a.slot, "seed": a.seed, "nilaiMin": NILAI_MIN,
        "ddBatas": DD_BATAS, "breadthMin": BREADTH_MIN,
        "hariBoleh%": boleh_pct,
        "keadaan": {
            "jumlahFTD": int(periode["FTD"].sum()),
            "tanggalFTD": list(periode.loc[periode["FTD"], "Tanggal"]),
            "jumlahDD": int(periode["DD"].sum()),
            "hariNaik%": round(float((periode["Keadaan"] == "NAIK").mean() * 100), 1),
            "hariDD5%": round(float((periode["DDAktif"] >= DD_BATAS).mean() * 100), 1),
            "hariMA50%": boleh_pct["ma50"],
            "hariBreadth%": boleh_pct["breadth"],
        },
        "ihsg": ihsg_meta,
        "cekBreadth": cek_breadth_berkas(br, a.breadth_csv),
        "biasSurvivorship": ("Universe = daftar emiten hari ini; emiten yang delisting, "
                             "mengecil, atau keluar dari 400 terbesar tidak ada di data."),
    }

    keluar = Path(a.output_dir)
    keluar.mkdir(parents=True, exist_ok=True)
    awal = a.awalan
    sinyal_df.to_csv(keluar / f"{awal}_sinyal.csv", index=False)
    porto_df.to_csv(keluar / f"{awal}_portofolio.csv", index=False)
    periode.to_csv(keluar / f"{awal}_harian.csv", index=False)
    (keluar / f"{awal}_meta.json").write_text(json.dumps(meta, indent=2, default=str) + "\n")
    tulis_md(keluar / f"{awal}.md", meta, sinyal_df, porto_df)

    print(f"\n{'Filter':<16}{'Boleh%':>8}{'DD swing':>10}{'Tot swing':>11}"
          f"{'DD acak':>9}{'Tot acak':>10}{'Sel21':>8}{'SE':>6}", file=sys.stderr)
    for f in FILTER:
        sw = porto_df[(porto_df["Kode"] == "swing") & (porto_df["KodeFilter"] == f)]
        ac = porto_df[(porto_df["Kode"] == ACAK[0]) & (porto_df["KodeFilter"] == f)]
        sn = sinyal_df[(sinyal_df["Kode"] == f) & (sinyal_df["Hari"] == 21)]
        g = lambda d, k: float(d[k].iloc[0]) if len(d) and pd.notna(d[k].iloc[0]) else float("nan")  # noqa: E731
        print(f"{f:<16}{boleh_pct[f]:>8.1f}{g(sw, 'MaxDD%Median'):>+10.1f}{g(sw, 'Total%Median'):>+11.1f}"
              f"{g(ac, 'MaxDD%Median'):>+9.1f}{g(ac, 'Total%Median'):>+10.1f}"
              f"{g(sn, 'Selisih%'):>+8.2f}{g(sn, 'SelisihSE%'):>6.2f}", file=sys.stderr)
    print(f"\nFTD: {meta['keadaan']['tanggalFTD']}", file=sys.stderr)
    print(f"Disimpan di {keluar}/{awal}_*", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
