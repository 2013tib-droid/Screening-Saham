#!/usr/bin/env python3
"""Uji coba: endpoint apa saja dari API stock.arjum.com yang bisa dipakai?

Skrip ini TIDAK mengubah data screening apa pun. Tugasnya cuma menembak ke-13
endpoint REST stock.arjum.com dengan API key dari secret ARJUM_API_KEY, lalu
melaporkan status HTTP dan bentuk response-nya. Gunanya menentukan data mana
yang layak disambungkan ke screener (bandarmologi, seasonal, dll).

Key dikirim lewat header X-API-Key dan TIDAK pernah dicetak ke log.
Kalau sebuah endpoint butuh parameter yang tidak kita kirim, server (FastAPI)
membalas 422 dengan daftar parameter yang kurang — itu ikut dilaporkan,
jadi hasil uji sekaligus jadi dokumentasi.

Pakai stdlib saja (urllib) supaya tidak menambah dependensi.

Pemakaian lokal:  ARJUM_API_KEY=sk_live_... python scripts/uji_arjum.py [KODE]
Satu endpoint utuh: JALUR=/api/openapi.json python scripts/uji_arjum.py
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://stock.arjum.com"
TIMEOUT = 30
# Potongan response yang dicetak per endpoint. Cukup untuk melihat nama kolom
# dan contoh nilai tanpa membanjiri log (history bisa ratusan bar).
CONTOH_MAKS = 1500


def endpoint(kode: str) -> list:
    """(nama, path) semua endpoint REST, urut seperti di halaman dokumentasi."""
    q = urllib.parse.quote
    return [
        ("Server Health Check", "/api/health"),
        ("Screener Saham Terkini", "/api/screener/latest"),
        ("Analisa Saham Komprehensif", f"/api/analysis/{q(kode)}"),
        ("Broker Summary (Bandarmologi)", f"/api/broker-summary/{q(kode)}"),
        ("Akumulasi Broker Historis", f"/api/broker-accumulation/{q(kode)}"),
        ("Riwayat Candlestick & Volume", f"/api/history/{q(kode)}"),
        ("Matriks Musim (Seasonality)", f"/api/seasonal/{q(kode)}"),
        ("Market Cap & Saham Beredar", "/api/market-cap"),
        ("Pencarian Saham", f"/api/search?q={q(kode)}"),
        ("Laporan Keuangan", f"/api/financial-statements/{q(kode)}"),
        ("Transaksi Insider", f"/api/insiders/{q(kode)}"),
        ("Done Details (Order Flow)", f"/api/done-details?code={q(kode)}"),
        ("Harga Realtime", f"/api/price/{q(kode)}"),
    ]


def tembak(path: str, key: str) -> dict:
    """Ambil satu endpoint, kembalikan ringkasan hasilnya (tidak pernah melempar)."""
    req = urllib.request.Request(BASE + path, headers={
        "X-API-Key": key,
        "Accept": "application/json",
        "User-Agent": "Screening-Saham/uji_arjum",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return {"status": r.status, "body": r.read()}
    except urllib.error.HTTPError as e:
        # Body error tetap dibaca: di situ FastAPI menaruh alasan (401/422/429).
        return {"status": e.code, "body": e.read()}
    except Exception as e:  # timeout, DNS, TLS, dll.
        return {"status": None, "body": b"", "error": f"{type(e).__name__}: {e}"}


def bentuk(data, dalam: int = 0) -> str:
    """Ringkasan struktur JSON: kunci di level atas, panjang list, dst."""
    if isinstance(data, dict):
        if dalam >= 1:
            return "{" + ", ".join(list(data)[:15]) + ("…" if len(data) > 15 else "") + "}"
        return "{" + ", ".join(f"{k}: {bentuk(v, dalam + 1)}" for k, v in list(data.items())[:15]) + "}"
    if isinstance(data, list):
        isi = bentuk(data[0], dalam + 1) if data else "-"
        return f"list[{len(data)}] of {isi}"
    return type(data).__name__


def main() -> int:
    key = os.environ.get("ARJUM_API_KEY", "").strip()
    kode = (sys.argv[1] if len(sys.argv) > 1 else "BBCA").upper()
    if not key:
        print("ARJUM_API_KEY kosong. Tambahkan dulu di GitHub: Settings -> Secrets and "
              "variables -> Actions -> New repository secret (Name: ARJUM_API_KEY).")
        return 1

    # Mode satu jalur: cetak response UTUH satu endpoint (mis. openapi.json,
    # atau endpoint dengan parameter tertentu) untuk dipelajari sebelum dipakai.
    jalur = os.environ.get("JALUR", "").strip()
    if jalur:
        h = tembak(jalur if jalur.startswith("/") else "/" + jalur, key)
        print(f"GET {jalur} -> HTTP {h['status']} {h.get('error', '')}")
        teks = h["body"].decode("utf-8", "replace")
        try:
            teks = json.dumps(json.loads(teks), ensure_ascii=False, indent=1)
        except json.JSONDecodeError:
            pass
        print(teks)
        return 0 if h["status"] == 200 else 1

    print("=" * 72)
    print(f"UJI API stock.arjum.com — kode contoh: {kode}")
    print("=" * 72)

    baris = []
    for nama, path in endpoint(kode):
        h = tembak(path, key)
        print(f"\n--- {nama}\n    GET {path}")
        if h["status"] is None:
            print(f"    GAGAL: {h['error']}")
            baris.append((nama, path, "gagal", h["error"]))
            continue
        teks = h["body"].decode("utf-8", "replace")
        try:
            data = json.loads(teks)
            ringkas = bentuk(data)
        except json.JSONDecodeError:
            data, ringkas = None, f"bukan JSON ({len(h['body'])} byte)"
        print(f"    HTTP {h['status']} | {len(h['body'])} byte")
        print(f"    Bentuk: {ringkas}")
        contoh = json.dumps(data, ensure_ascii=False, indent=1) if data is not None else teks
        print("    Contoh: " + contoh[:CONTOH_MAKS].replace("\n", "\n    ")
              + ("\n    …(dipotong)" if len(contoh) > CONTOH_MAKS else ""))
        baris.append((nama, path, h["status"], ringkas))

    ok = sum(1 for b in baris if b[2] == 200)
    print("\n" + "=" * 72)
    print(f"KESIMPULAN: {ok}/{len(baris)} endpoint membalas 200.")
    print("=" * 72)

    # Ringkasan tabel di halaman run Actions, supaya hasilnya terbaca tanpa
    # membuka log (enak dilihat dari HP).
    ringkasan = os.environ.get("GITHUB_STEP_SUMMARY")
    if ringkasan:
        with open(ringkasan, "a", encoding="utf-8") as f:
            f.write(f"## Uji API stock.arjum.com ({kode})\n\n"
                    f"**{ok}/{len(baris)}** endpoint membalas 200.\n\n"
                    "| Endpoint | Path | HTTP | Bentuk response |\n|---|---|---|---|\n")
            for nama, path, status, isi in baris:
                isi = str(isi).replace("|", "\\|")[:300]
                f.write(f"| {nama} | `{path}` | {status} | {isi} |\n")

    # Gagal hanya kalau semua endpoint ber-key ditolak (key salah/dicabut);
    # sebagian endpoint 4xx itu temuan, bukan kegagalan uji.
    return 0 if ok > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
