"""Net beli asing harian dari API stock.arjum.com.

Yahoo Finance tidak punya data transaksi investor asing, dan idx.co.id tidak
bisa diandalkan dari runner GitHub (lihat scripts/uji_idx.py). Endpoint
/api/history/{kode} milik stock.arjum.com mengirim, per hari bursa, lembar
yang dibeli dan dijual asing (f_buy, f_sell) beserta selisihnya (n_foreign).
Uji 28 Sep 2026 (workflow "Uji API Arjum") memastikan isinya.

Butuh API key di environment variable ARJUM_API_KEY. Tanpa key, atau kalau API
sedang bermasalah, kolomnya dibiarkan kosong — screening tetap jalan dengan
data Yahoo seperti sebelumnya. Net asing adalah pelengkap, bukan syarat.

Kuota paket gratis 1.000 request PER HARI (reset 00:00 WIB) — dashboard
stock.arjum.com menulis "req/hr", tapi server membalas 429 "Kuota harian ...
(1000 req/hari)". Tiap emiten butuh satu request dan tidak ada versi batch,
jadi universe ~400 emiten memakai ~40% kuota harian per run. Begitu server
membalas 429, sisa emiten dilewati alih-alih menembak terus.

Karena itu run malam memanggil modul ini sebagai langkah TERPISAH, sesudah
broker.py (lihat screening-malam.yml): broker summary hanya ~5-10 request
tapi paling berharga, dan tidak boleh kehabisan kuota gara-gara net asing.
Emitennya diurut dari yang paling likuid, supaya bila kuota menipis yang
kosong adalah emiten yang paling jarang ditransaksikan.

    python arjum.py                      # isi kolom NetAsing di hasil/*.csv
"""

import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd

BASE = "https://stock.arjum.com"
TIMEOUT = 20
# Paralel secukupnya: ~400 request berurutan makan ~5 menit, empat jalur
# memangkasnya ke ~1 menit tanpa terlihat seperti banjir request.
PARALEL = 4

KOLOM_ASING = ["NetAsing1H(M)", "NetAsing5H(M)", "NetAsing20H(M)", "TglAsing"]


def panggil(path: str, key: str, **query) -> dict:
    """GET satu endpoint, kembalikan JSON-nya. Melempar bila gagal (HTTPError
    membawa status, supaya pemanggil bisa membedakan 429/401 dari 5xx)."""
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={
        "X-API-Key": key, "Accept": "application/json",
        "User-Agent": "Screening-Saham/screener"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _ambil(kode: str, key: str) -> list[dict]:
    """Baris histori harian satu emiten, terbaru dulu. Melempar bila gagal."""
    return panggil(f"/api/history/{urllib.parse.quote(kode)}", key).get("rows") or []


def net_asing(rows: list[dict], buang_tanggal: date | None = None) -> dict:
    """Jumlahkan net asing 1, 5, dan 20 hari bursa terakhir, dalam miliar rupiah.

    n_foreign dalam lembar, jadi dikali harga rata-rata hari itu (avg; close
    bila avg kosong) supaya bisa dibandingkan antar-emiten: net 10 juta lembar
    di saham Rp100 dan di saham Rp10.000 bukan hal yang sama.

    buang_tanggal: bar bertanggal ini dibuang — dipakai untuk bar hari ini
    selama sesi bursa belum tuntas, sama seperti histori Yahoo di screener.
    """
    bar = []
    for r in rows:
        try:
            tgl = date.fromisoformat(str(r["date"])[:10])
            n = float(r["n_foreign"])
            harga = float(r.get("avg") or r.get("close"))
        except (KeyError, TypeError, ValueError):
            continue
        if tgl == buang_tanggal:
            continue
        bar.append((tgl, n * harga))
    bar.sort(reverse=True)
    if not bar:
        return {}
    hasil = {"TglAsing": bar[0][0].isoformat()}
    for hari, kolom in ((1, "NetAsing1H(M)"), (5, "NetAsing5H(M)"), (20, "NetAsing20H(M)")):
        if len(bar) >= hari:
            hasil[kolom] = round(sum(v for _, v in bar[:hari]) / 1e9, 1)
    return hasil


def ambil_net_asing(kode_list: list[str], buang_tanggal: date | None = None) -> pd.DataFrame:
    """Tabel Ticker + KOLOM_ASING untuk emiten yang berhasil diambil.

    Tidak pernah melempar: tanpa key atau saat API bermasalah hasilnya tabel
    kosong (atau sebagian), dan screener menggabungkannya apa adanya.
    """
    key = os.environ.get("ARJUM_API_KEY", "").strip()
    if not key:
        print("Net asing dilewati: ARJUM_API_KEY tidak diset.", file=sys.stderr)
        return pd.DataFrame(columns=["Ticker"] + KOLOM_ASING)

    # Dua alasan berhenti menembak di tengah jalan: kuota habis (429), atau
    # key ditolak (401/403) — mis. sudah dicabut di dashboard. Keduanya berlaku
    # untuk semua emiten, jadi 400 request berikutnya pasti gagal juga.
    berhenti = threading.Event()
    alasan = []
    gagal = []

    def satu(kode: str) -> dict | None:
        if berhenti.is_set():
            return None
        for percobaan in range(2):
            try:
                hasil = net_asing(_ambil(kode, key), buang_tanggal)
                return {"Ticker": kode, **hasil} if hasil else None
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 429):
                    if not berhenti.is_set():
                        alasan.append("kuota API habis (HTTP 429)" if e.code == 429
                                      else f"API key ditolak (HTTP {e.code})")
                        berhenti.set()
                    return None
                # 404: kode tidak dikenal API — mencoba ulang tidak mengubah apa-apa.
                if e.code < 500 or percobaan:
                    gagal.append(f"{kode} (HTTP {e.code})")
                    return None
            except Exception as e:  # timeout, DNS, JSON rusak
                if percobaan:
                    gagal.append(f"{kode} ({type(e).__name__})")
                    return None
        return None

    print(f"Mengambil net asing {len(kode_list)} saham dari stock.arjum.com ...",
          file=sys.stderr)
    with ThreadPoolExecutor(PARALEL) as ex:
        baris = [b for b in ex.map(satu, kode_list) if b]

    print(f"Net asing: {len(baris)} dari {len(kode_list)} emiten.", file=sys.stderr)
    if alasan:
        print(f"  Berhenti: {alasan[0]} — sisa emiten dibiarkan kosong.",
              file=sys.stderr)
    if gagal:
        print(f"  Gagal: {', '.join(gagal[:15])}" + (" …" if len(gagal) > 15 else ""),
              file=sys.stderr)
    return pd.DataFrame(baris, columns=["Ticker"] + KOLOM_ASING)


def tulis_ke_csv(path: str, asing: pd.DataFrame) -> None:
    """Ganti kolom KOLOM_ASING di satu CSV hasil dengan data baru.

    Kolomnya diletakkan sesudah MA200, sama seperti urutan KOLOM_EKSTRA di
    screener, supaya CSV yang ditulis screener dan yang diperkaya di sini
    berbentuk sama. Emiten tanpa data asing dibiarkan kosong.
    """
    df = pd.read_csv(path)
    if "Ticker" not in df.columns:
        return
    df = df.drop(columns=[k for k in KOLOM_ASING if k in df.columns])
    df = df.merge(asing, on="Ticker", how="left")
    kolom = [k for k in df.columns if k not in KOLOM_ASING]
    sisip = kolom.index("MA200") + 1 if "MA200" in kolom else len(kolom)
    df = df[kolom[:sisip] + KOLOM_ASING + kolom[sisip:]]
    df.to_csv(path, index=False)


def main() -> int:
    from datetime import datetime

    from screener import JAM_DATA_FINAL, WIB

    p = argparse.ArgumentParser(description="Isi kolom net beli asing di CSV hasil screening.")
    p.add_argument("--sumber", default="hasil/semua.csv",
                   help="CSV berisi seluruh emiten yang diambil (kolom Ticker, Nilai(M))")
    p.add_argument("--ke", nargs="+", metavar="CSV",
                   default=["hasil/semua.csv", "hasil/swing.csv",
                            "hasil/value.csv", "hasil/tumbuh.csv"],
                   help="CSV yang kolom NetAsing-nya diisi ulang")
    args = p.parse_args()

    sumber = pd.read_csv(args.sumber)
    if "Nilai(M)" in sumber.columns:
        sumber = sumber.sort_values("Nilai(M)", ascending=False, na_position="last")
    sekarang = datetime.now(WIB)
    buang = sekarang.date() if sekarang.time() < JAM_DATA_FINAL else None
    asing = ambil_net_asing(sumber["Ticker"].astype(str).tolist(), buang)
    for path in args.ke:
        if os.path.exists(path):
            tulis_ke_csv(path, asing)
            print(f"Kolom net asing ditulis ke {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
