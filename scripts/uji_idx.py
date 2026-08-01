#!/usr/bin/env python3
"""Uji coba: apakah data IDX bisa diakses otomatis, dan apakah ada net buy asing?

Skrip ini TIDAK mengubah data screening apa pun. Tugasnya cuma satu: menembak
beberapa endpoint IDX, lalu melaporkan apa yang terjadi. Dijalankan dari
GitHub Actions (workflow "Uji Akses IDX") karena jaringan runner berbeda dari
laptop/sesi lokal — IDX memakai Cloudflare yang rutin memblokir request
non-browser, jadi hasilnya harus diuji di tempat workflow benar-benar jalan.

Dua pertanyaan yang dijawab:
  1. Bisa tembus tidak? (status HTTP, atau diblokir Cloudflare)
  2. Kalau tembus, ada kolom Foreign Buy / Foreign Sell per saham tidak?

Pakai stdlib saja (urllib) supaya tidak menambah dependensi.

Pemakaian lokal:  python scripts/uji_idx.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

# Header ala browser. Tanpa ini Cloudflare hampir pasti menolak; dengan ini pun
# belum tentu lolos — justru itu yang mau diukur.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham",
}

TIMEOUT = 30
# Kata kunci nama kolom yang menandakan data asing.
PETUNJUK_ASING = ("foreign", "asing", "netbuy", "net_buy", "fnet")


def hari_bursa_terakhir(mundur: int = 0) -> str:
    """Tanggal YYYYMMDD hari kerja ke-N terakhir (Sabtu/Minggu dilewati).

    Libur bursa tidak dicek — karena itu skrip mencoba beberapa tanggal.
    """
    d = date.today()
    lewat = 0
    while True:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # 0-4 = Senin-Jumat
            if lewat == mundur:
                return d.strftime("%Y%m%d")
            lewat += 1


def tembak(url: str) -> dict:
    """Ambil satu URL, kembalikan ringkasan hasilnya (tidak pernah melempar)."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
            return {
                "ok": True,
                "status": r.status,
                "ctype": r.headers.get("Content-Type", "?"),
                "bytes": len(body),
                "body": body,
            }
    except urllib.error.HTTPError as e:
        # Cloudflare menolak lewat status HTTP (403 = policy, 503 = challenge).
        return {"ok": False, "status": e.code, "ctype": e.headers.get("Content-Type", "?"),
                "bytes": 0, "error": f"HTTP {e.code} {e.reason}"}
    except Exception as e:  # timeout, DNS, TLS, proxy, dll.
        return {"ok": False, "status": None, "ctype": "?", "bytes": 0,
                "error": f"{type(e).__name__}: {e}"}


def cari_records(data):
    """IDX membungkus datanya dengan nama yang berbeda-beda per endpoint
    ('data', 'Data', 'replies', ...). Cari list-of-dict pertama."""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data
    if isinstance(data, dict):
        for v in data.values():
            hasil = cari_records(v)
            if hasil:
                return hasil
    return None


def periksa(nama: str, url: str, catatan: list) -> dict:
    """Tembak satu endpoint lalu laporkan temuannya."""
    print(f"\n--- {nama}")
    print(f"    {url}")
    h = tembak(url)

    if not h["ok"]:
        print(f"    GAGAL: {h['error']}")
        catatan.append({"nama": nama, "url": url, "status": h["status"],
                        "tembus": False, "asing": False, "pesan": h["error"]})
        return catatan[-1]

    print(f"    HTTP {h['status']} | {h['ctype']} | {h['bytes']} byte")

    # Cloudflare kadang membalas 200 tapi isinya halaman challenge, bukan JSON.
    if "json" not in h["ctype"].lower():
        cuplik = h["body"][:120].decode("utf-8", "replace").replace("\n", " ")
        pesan = f"Tembus tapi bukan JSON (kemungkinan halaman Cloudflare): {cuplik}"
        print(f"    {pesan}")
        catatan.append({"nama": nama, "url": url, "status": h["status"],
                        "tembus": True, "asing": False, "pesan": pesan})
        return catatan[-1]

    try:
        data = json.loads(h["body"])
    except Exception as e:
        catatan.append({"nama": nama, "url": url, "status": h["status"],
                        "tembus": True, "asing": False, "pesan": f"JSON rusak: {e}"})
        print(f"    JSON rusak: {e}")
        return catatan[-1]

    rec = cari_records(data)
    if not rec:
        atas = list(data)[:10] if isinstance(data, dict) else type(data).__name__
        pesan = f"JSON valid tapi tidak ada baris data. Kunci teratas: {atas}"
        print(f"    {pesan}")
        catatan.append({"nama": nama, "url": url, "status": h["status"],
                        "tembus": True, "asing": False, "pesan": pesan})
        return catatan[-1]

    kolom = list(rec[0])
    asing = [k for k in kolom if any(p in k.lower() for p in PETUNJUK_ASING)]
    print(f"    {len(rec)} baris, {len(kolom)} kolom")
    print(f"    Kolom: {', '.join(kolom)}")

    if asing:
        print(f"    >>> KOLOM ASING DITEMUKAN: {', '.join(asing)}")
        # Tampilkan satu contoh nyata supaya ketahuan satuannya (lembar vs rupiah).
        contoh = next((r for r in rec if str(r.get("StockCode", "")).upper() == "BBCA"), rec[0])
        kode = contoh.get("StockCode") or contoh.get("Code") or "(baris pertama)"
        print(f"    Contoh {kode}: " + ", ".join(f"{k}={contoh.get(k)}" for k in asing))
    else:
        print("    (tidak ada kolom asing di endpoint ini)")

    catatan.append({"nama": nama, "url": url, "status": h["status"], "tembus": True,
                    "asing": bool(asing), "kolom_asing": asing, "baris": len(rec),
                    "pesan": f"{len(rec)} baris; kolom asing: {', '.join(asing) or '-'}"})
    return catatan[-1]


def main():
    tanggal = [hari_bursa_terakhir(i) for i in range(3)]
    print("=" * 72)
    print("UJI AKSES IDX — apakah GitHub Actions bisa menembus, dan ada net buy asing?")
    print(f"Tanggal yang dicoba (hari kerja terakhir): {', '.join(tanggal)}")
    print("=" * 72)

    catatan: list = []
    d = tanggal[0]

    # Endpoint utama yang kita incar: ringkasan saham harian per emiten.
    periksa("Stock Summary (www, dengan tanggal)",
            f"https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
            f"?length=10&start=0&date={d}", catatan)

    # Tanpa tanggal — sebagian endpoint IDX memakai tanggal perdagangan terakhir.
    periksa("Stock Summary (www, tanpa tanggal)",
            "https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
            "?length=10&start=0", catatan)

    # Host tanpa 'www' kadang punya perlakuan Cloudflare berbeda.
    periksa("Stock Summary (tanpa www)",
            f"https://idx.co.id/primary/TradingSummary/GetStockSummary"
            f"?length=10&start=0&date={d}", catatan)

    # Kontrol: endpoint lain yang lebih ringan. Kalau ini tembus tapi stock
    # summary tidak, berarti masalahnya di endpoint, bukan di blokir menyeluruh.
    periksa("Index Summary (kontrol)",
            f"https://www.idx.co.id/primary/TradingSummary/GetIndexSummary"
            f"?length=10&start=0&date={d}", catatan)

    # Kalau tanggal pertama kena libur bursa, coba mundur.
    if not any(c.get("baris") for c in catatan):
        for d2 in tanggal[1:]:
            periksa(f"Stock Summary (tanggal mundur {d2})",
                    f"https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
                    f"?length=10&start=0&date={d2}", catatan)

    # ---- Kesimpulan
    tembus = [c for c in catatan if c["tembus"]]
    dengan_asing = [c for c in catatan if c["asing"]]

    # Jangan mengklaim "GitHub Actions" kalau ternyata dijalankan dari laptop.
    tempat = "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") else "lingkungan ini"

    print("\n" + "=" * 72)
    if dengan_asing:
        verdict = f"BISA — data asing tersedia lewat {tempat}"
        saran = (f"Pakai: {dengan_asing[0]['url']}\n"
                 f"Kolom asing: {', '.join(dengan_asing[0].get('kolom_asing', []))}")
    elif tembus:
        verdict = "SEBAGIAN — IDX tembus, tapi kolom asing belum ketemu di endpoint ini"
        saran = "Perlu cari endpoint/berkas lain (mis. unduhan XLSX Ringkasan Saham)."
    else:
        verdict = f"DIBLOKIR — {tempat} tidak bisa menembus IDX"
        saran = "Integrasi langsung ke idx.co.id tidak layak; perlu sumber alternatif."
    print(f"KESIMPULAN: {verdict}")
    print(saran)
    print("=" * 72)

    # Ringkasan yang tampil di halaman ringkasan job GitHub Actions.
    ringkas = os.environ.get("GITHUB_STEP_SUMMARY")
    if ringkas:
        with open(ringkas, "a") as f:
            f.write(f"## Uji Akses IDX\n\n**{verdict}**\n\n{saran}\n\n")
            f.write("| Endpoint | Status | Tembus | Kolom asing |\n")
            f.write("|---|---|---|---|\n")
            for c in catatan:
                f.write(f"| {c['nama']} | {c['status'] or 'gagal'} | "
                        f"{'ya' if c['tembus'] else 'tidak'} | "
                        f"{'ya — ' + ', '.join(c.get('kolom_asing', [])) if c['asing'] else 'tidak'} |\n")

    # Selalu keluar 0: ini uji coba diagnostik, "diblokir" itu HASIL yang sah,
    # bukan kegagalan build.
    return 0


if __name__ == "__main__":
    sys.exit(main())
