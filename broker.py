#!/usr/bin/env python3
"""Broker summary (bandarmologi) untuk kandidat swing, dari stock.arjum.com.

Screener dan SMC membaca harga; skrip ini membaca SIAPA yang bertransaksi.
Untuk tiap emiten di daftar kandidat (default `hasil/swing.csv`) ia menarik
/api/broker-summary/{kode} selama beberapa hari bursa terakhir, lalu merangkum:

  - tiga broker net beli terbesar dan tiga broker net jual terbesar;
  - Dominasi%: porsi net beli top-3 pembeli terhadap total top-3 pembeli +
    top-3 penjual. 50% berarti seimbang;
  - Bandar: "Akumulasi" bila Dominasi >= 60%, "Distribusi" bila <= 40%;
  - harga rata-rata beli top-3 pembeli, dan jarak harga terakhir ke sana.
    Harga yang masih dekat rata-rata mereka berarti belum jauh "ketinggalan
    kereta"; jauh di atasnya berarti mereka sudah untung besar dan bisa jadi
    penjual berikutnya.

Ini pembacaan heuristik atas aliran dana, bukan kepastian ada bandar: satu
kode broker menampung ribuan nasabah ritel sekaligus institusi.

`all_data=true` wajib: tanpa itu API hanya mengirim 20 broker net BELI
teratas, sehingga sisi penjual tidak pernah terlihat.

Contoh pemakaian:
    python broker.py                                # dari hasil/swing.csv
    python broker.py --ticker BBCA TLKM             # ad-hoc, tanpa CSV
    python broker.py --hari 10                      # jendela 10 hari bursa

Butuh ARJUM_API_KEY. Hasil disimpan ke `hasil/swing_broker.csv`.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from arjum import panggil
from screener import JAM_DATA_FINAL, WIB

AMBANG_AKUMULASI = 60.0
AMBANG_DISTRIBUSI = 40.0
TOP = 3

KOLOM = [
    "Ticker", "Nama", "Harga", "Bandar", "Dominasi%",
    "NetBeliTop3(M)", "NetJualTop3(M)", "TopBeli", "TopJual",
    "AvgBeliTop3", "JarakAvg%", "Mulai", "Akhir", "Catatan",
]


def mundur_hari_kerja(akhir: date, n: int) -> date:
    """Tanggal awal jendela n hari kerja yang berakhir di `akhir` (inklusif).

    Libur bursa tidak dicek; jendelanya jadi sedikit lebih pendek di minggu
    yang ada liburnya. Tanggal sebenarnya dari API ikut dicatat di kolom
    Mulai/Akhir, jadi tidak ada yang tersembunyi.
    """
    d, sisa = akhir, n - 1
    while sisa > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            sisa -= 1
    return d


def tanggal_akhir(df: pd.DataFrame | None) -> date:
    """Hari bursa terakhir yang datanya sudah final.

    TglAsing di CSV screener adalah tanggal bar yang dipakai malam itu — dipakai
    supaya jendela broker berakhir di hari yang sama dengan kolom harganya.
    Tanpa kolom itu (mode --ticker), mundur dari hari ini: hari ini sendiri
    hanya ikut bila sesi sudah tuntas, sama dengan aturan screener.
    """
    if df is not None and "TglAsing" in df.columns:
        tgl = pd.to_datetime(df["TglAsing"], errors="coerce").dropna()
        if len(tgl):
            return tgl.max().date()
    sekarang = datetime.now(WIB)
    d = sekarang.date()
    if sekarang.time() < JAM_DATA_FINAL:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _angka_id(v: float) -> str:
    """1234.5 -> '1.234,5' — dibaca di dashboard berbahasa Indonesia."""
    return f"{v:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")


def ringkas(resp: dict, harga: float | None) -> dict:
    """Rangkuman satu response broker-summary. Kosong bila tak ada transaksi."""
    brokers = []
    for b in resp.get("brokers") or []:
        try:
            bval, sval = float(b.get("bval") or 0), float(b.get("sval") or 0)
            bvol = float(b.get("bvol") or 0)
        except (TypeError, ValueError):
            continue
        brokers.append((str(b.get("broker_code") or "?"), bval - sval, bval, bvol))
    beli = sorted((b for b in brokers if b[1] > 0), key=lambda b: -b[1])[:TOP]
    jual = sorted((b for b in brokers if b[1] < 0), key=lambda b: b[1])[:TOP]
    if not beli and not jual:
        return {"Catatan": "tidak ada transaksi broker di periode ini"}

    nb = sum(b[1] for b in beli)
    nj = sum(b[1] for b in jual)
    dominasi = nb / (nb - nj) * 100 if nb - nj else None
    bandar = ("Akumulasi" if dominasi is not None and dominasi >= AMBANG_AKUMULASI
              else "Distribusi" if dominasi is not None and dominasi <= AMBANG_DISTRIBUSI
              else "Netral")
    # Rata-rata harga beli KOTOR (bval/bvol) top pembeli — itu harga modal
    # mereka, bukan harga net. bvol dalam lembar.
    vol = sum(b[3] for b in beli)
    avg = sum(b[2] for b in beli) / vol if vol else None
    return {
        "Bandar": bandar,
        "Dominasi%": round(dominasi, 1) if dominasi is not None else None,
        "NetBeliTop3(M)": round(nb / 1e9, 1),
        "NetJualTop3(M)": round(nj / 1e9, 1),
        "TopBeli": " · ".join(f"{k} {_angka_id(n / 1e9)}" for k, n, _, _ in beli),
        "TopJual": " · ".join(f"{k} {_angka_id(n / 1e9)}" for k, n, _, _ in jual),
        "AvgBeliTop3": round(avg) if avg else None,
        "JarakAvg%": round((harga / avg - 1) * 100, 1) if avg and harga else None,
        "Mulai": resp.get("broker_start_date"),
        "Akhir": resp.get("broker_end_date"),
        "Catatan": "",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dari-csv", default="hasil/swing.csv",
                   help="CSV kandidat (butuh kolom Ticker; Nama/Harga/TglAsing opsional)")
    p.add_argument("--ticker", nargs="+", metavar="KODE", help="kode saham ad-hoc, tanpa CSV")
    p.add_argument("--hari", type=int, default=5, help="panjang jendela dalam hari bursa")
    p.add_argument("--output", default="hasil/swing_broker.csv", help="file CSV hasil")
    args = p.parse_args()

    if args.ticker:
        sumber = pd.DataFrame({"Ticker": [t.upper().removesuffix(".JK") for t in args.ticker]})
    else:
        sumber = pd.read_csv(args.dari_csv)
    akhir = tanggal_akhir(sumber)
    mulai = mundur_hari_kerja(akhir, args.hari)
    key = os.environ.get("ARJUM_API_KEY", "").strip()
    print(f"Broker summary {len(sumber)} emiten, {mulai} s.d. {akhir} "
          f"({args.hari} hari kerja).", file=sys.stderr)

    baris = []
    berhenti = ""
    for _, r in sumber.iterrows():
        kode = str(r["Ticker"])
        harga = pd.to_numeric(r.get("Harga"), errors="coerce")
        dasar = {"Ticker": kode, "Nama": r.get("Nama", ""),
                 "Harga": None if pd.isna(harga) else harga}
        # CSV selalu memuat setiap kandidat, termasuk yang datanya gagal
        # diambil, dengan alasannya di Catatan — sama seperti tab SMC. Baris
        # yang diam-diam hilang terbaca sebagai "tidak lolos", bukan "gagal".
        if not key:
            baris.append({**dasar, "Catatan": "ARJUM_API_KEY tidak diset"})
            continue
        if berhenti:
            baris.append({**dasar, "Catatan": berhenti})
            continue
        try:
            resp = panggil(f"/api/broker-summary/{urllib.parse.quote(kode)}", key,
                           start_date=mulai.isoformat(), end_date=akhir.isoformat(),
                           all_data="true")
            baris.append({**dasar, **ringkas(resp, dasar["Harga"])})
        except urllib.error.HTTPError as e:
            ket = f"API membalas HTTP {e.code}"
            # Kuota habis / key ditolak berlaku untuk semua emiten berikutnya.
            if e.code in (401, 403, 429):
                berhenti = ket
            baris.append({**dasar, "Catatan": ket})
        except Exception as e:  # timeout, DNS, JSON rusak
            baris.append({**dasar, "Catatan": f"gagal: {type(e).__name__}"})
        print(f"  {kode}: {baris[-1].get('Bandar') or baris[-1]['Catatan']}", file=sys.stderr)

    df = pd.DataFrame(baris, columns=KOLOM)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    if len(df):
        print(df[["Ticker", "Bandar", "Dominasi%", "TopBeli", "TopJual", "JarakAvg%"]]
              .to_string(index=False))
    print(f"\nDisimpan ke {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
