#!/usr/bin/env python3
"""Susun ulang universe screening (tickers/idx.txt) langsung dari Yahoo Finance.

Kenapa skrip ini ada: sebelumnya universe screener disusun tangan — LQ45 plus
beberapa daftar grup konglomerasi. Akibatnya saham dengan fundamental bagus di
luar daftar itu tidak pernah lolos filter, karena datanya memang tidak pernah
diambil. Filter fundamental cuma bisa memilih dari apa yang disodorkan.

Skrip ini mengambil daftar emiten Indonesia dari screener Yahoo Finance
(region = id), diurut dari kapitalisasi terbesar, lalu menulisnya ke
tickers/idx.txt. File itu ikut dibaca screener secara default, jadi setiap
emiten yang cukup besar otomatis masuk universe tanpa perlu disebut namanya.

Batas kapitalisasi dan jumlah maksimal ada supaya runtime screening tetap
masuk akal (setiap ticker = beberapa request ke Yahoo). Emiten yang terlalu
kecil praktis tidak bisa ditransaksikan dan tetap akan ditandai TIPIS oleh
screener.

Pemakaian:
    python scripts/perbarui_universe.py                 # default: mcap >= 1 T, maks 400
    python scripts/perbarui_universe.py --min-mcap 0.5 --maks 600
    python scripts/perbarui_universe.py --output tickers/idx.txt
"""

import argparse
import sys
from datetime import date
from pathlib import Path

# Yahoo membatasi satu panggilan screener maksimal 250 baris.
UKURAN_HALAMAN = 250


def ambil_universe(min_mcap: float, maks: int) -> list[tuple[str, str, float | None]]:
    """Ambil emiten IDX dari screener Yahoo, urut kapitalisasi terbesar.

    Mengembalikan daftar (ticker tanpa .JK, nama pendek, kapitalisasi).
    """
    import yfinance as yf

    kueri = yf.EquityQuery("and", [
        yf.EquityQuery("eq", ["region", "id"]),
        yf.EquityQuery("gt", ["intradaymarketcap", min_mcap]),
    ])

    hasil: list[tuple[str, str, float | None]] = []
    sudah: set[str] = set()
    offset = 0
    while len(hasil) < maks:
        jatah = min(UKURAN_HALAMAN, maks - len(hasil))
        resp = yf.screen(kueri, offset=offset, size=jatah,
                         sortField="intradaymarketcap", sortAsc=False)
        baris = (resp or {}).get("quotes") or []
        if not baris:
            break
        for q in baris:
            simbol = str(q.get("symbol") or "").upper()
            # Saring ke papan Jakarta saja: region=id sesekali menyertakan
            # listing sekunder emiten yang sama di bursa lain.
            if not simbol.endswith(".JK"):
                continue
            kode = simbol.removesuffix(".JK")
            if kode in sudah:
                continue
            sudah.add(kode)
            nama = str(q.get("shortName") or q.get("longName") or "").strip()
            hasil.append((kode, nama, q.get("marketCap")))
        if len(baris) < jatah:
            break
        offset += len(baris)
    return hasil


def tulis(path: Path, emiten: list[tuple[str, str, float | None]],
          min_mcap: float, maks: int) -> None:
    hari_ini = date.today().isoformat()
    baris = [
        "# grup:",
        "# ^ sengaja kosong: file ini adalah universe pasar, bukan tema atau grup",
        "#   konglomerasi. Saham yang juga ada di daftar kurasi (LQ45, Salim, dst.)",
        "#   tetap memakai label dari daftar itu; sisanya berlabel kosong.",
        "#",
        "# DIHASILKAN OTOMATIS oleh scripts/perbarui_universe.py — jangan disunting",
        "# tangan, isinya akan ditimpa pada pembaruan berikutnya.",
        f"# Kriteria: emiten Indonesia (Yahoo region=id) dengan kapitalisasi pasar",
        f"#   di atas {min_mcap / 1e12:g} triliun rupiah, diurut dari yang terbesar,",
        f"#   maksimal {maks} nama.",
        f"# Diperbarui: {hari_ini} — {len(emiten)} emiten.",
        "",
    ]
    lebar = max((len(k) for k, _, _ in emiten), default=4)
    for kode, nama, mcap in emiten:
        # Tanda '#' pada nama emiten akan merusak pemisahan komentar di
        # pembaca daftar ticker, jadi dibuang.
        nama = nama.replace("#", "").strip()
        catatan = f"{nama} — {mcap / 1e12:.1f} T" if mcap else nama
        baris.append(f"{kode:<{lebar}}  # {catatan}" if catatan else kode)
    path.write_text("\n".join(baris) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Perbarui daftar universe IDX dari screener Yahoo Finance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--output", default="tickers/idx.txt", help="file daftar ticker yang ditulis")
    p.add_argument("--min-mcap", type=float, default=1.0,
                   help="kapitalisasi pasar minimal, dalam triliun rupiah")
    p.add_argument("--maks", type=int, default=400,
                   help="jumlah emiten maksimal (pembatas runtime screening)")
    args = p.parse_args()

    print(f"Mengambil emiten IDX dengan kapitalisasi > {args.min_mcap} T "
          f"(maksimal {args.maks}) ...", file=sys.stderr)
    try:
        emiten = ambil_universe(args.min_mcap * 1e12, args.maks)
    except Exception as e:
        # Kegagalan di sini tidak boleh menggagalkan screening malam: file
        # universe yang lama masih ada di repo dan tetap bisa dipakai.
        print(f"GAGAL mengambil universe: {type(e).__name__}: {e}", file=sys.stderr)
        print("File universe lama dipertahankan.", file=sys.stderr)
        return 1

    if not emiten:
        print("Screener Yahoo tidak mengembalikan satu emiten pun — "
              "file universe lama dipertahankan.", file=sys.stderr)
        return 1

    path = Path(args.output)
    lama = set()
    if path.exists():
        lama = {b.split("#", 1)[0].strip().upper()
                for b in path.read_text().splitlines()
                if b.split("#", 1)[0].strip()}
    baru = {k for k, _, _ in emiten}

    path.parent.mkdir(parents=True, exist_ok=True)
    tulis(path, emiten, args.min_mcap * 1e12, args.maks)

    masuk = sorted(baru - lama)
    keluar = sorted(lama - baru)
    print(f"{len(emiten)} emiten ditulis ke {path}", file=sys.stderr)
    if lama:
        print(f"  masuk ({len(masuk)}): {', '.join(masuk) or '-'}", file=sys.stderr)
        print(f"  keluar ({len(keluar)}): {', '.join(keluar) or '-'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
