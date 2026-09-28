"""Net beli asing harian dari API stock.arjum.com.

Yahoo Finance tidak punya data transaksi investor asing, dan idx.co.id tidak
bisa diandalkan dari runner GitHub (lihat scripts/uji_idx.py). Endpoint
/api/history/{kode} milik stock.arjum.com mengirim, per hari bursa, lembar
yang dibeli dan dijual asing (f_buy, f_sell) beserta selisihnya (n_foreign).
Uji 28 Sep 2026 (workflow "Uji API Arjum") memastikan isinya.

Butuh API key di environment variable ARJUM_API_KEY. Tanpa key, atau kalau API
sedang bermasalah, kolomnya dibiarkan kosong — screening tetap jalan dengan
data Yahoo seperti sebelumnya. Net asing adalah pelengkap, bukan syarat.

Kuota paket gratis 1.000 request/jam, dan tiap emiten butuh satu request.
Universe ~400 emiten muat, tapi dua run berdekatan (mis. push beruntun) bisa
menabrak batasnya; begitu server membalas 429, sisa emiten dilewati alih-alih
menembak terus dan memperparah.
"""

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


def _ambil(kode: str, key: str) -> list[dict]:
    """Baris histori harian satu emiten, terbaru dulu. Melempar bila gagal."""
    req = urllib.request.Request(
        f"{BASE}/api/history/{urllib.parse.quote(kode)}",
        headers={"X-API-Key": key, "Accept": "application/json",
                 "User-Agent": "Screening-Saham/screener"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r).get("rows") or []


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
