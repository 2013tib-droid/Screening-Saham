#!/usr/bin/env python3
"""Susun ulang data/syariah.txt dari Daftar Efek Syariah (DES) resmi.

Kenapa skrip ini tidak menarik sendiri dari sumbernya: dicoba, dan diblokir.
Per 1 September 2026, endpoint IDX `Index/GetConstituent` dan halaman
`idx.co.id/id/idx-syariah/` menjawab 503 dari Varnish, endpoint arsip
`StockData/GetIndexConstituent` berhenti di 2018, dan ojk.go.id menjawab
"Request Rejected" dari WAF-nya. Jadi berkas DES-nya diunduh manual lewat
browser, dan skrip ini yang mengubahnya jadi daftar kode yang bersih.

Itu bukan kompromi yang menyakitkan: DES hanya ditetapkan dua kali setahun
(berlaku 1 Juni dan 1 Desember), plus sesekali penetapan insidentil untuk
emiten yang baru IPO. Pekerjaan manualnya dua kali setahun, dan hasilnya
di-commit sehingga run malam tidak pernah bergantung padanya.

Di mana berkasnya:
  - OJK  https://www.ojk.go.id  ->  Pasar Modal -> Data dan Statistik
                                    -> Daftar Efek Syariah
  - IDX  https://www.idx.co.id/id/idx-syariah/saham-syariah/

Pemakaian:
    python scripts/perbarui_syariah.py --dari ~/Downloads/DES.xlsx \\
        --berlaku 2026-06-01 --sumber "OJK Kep-45/D.04/2026"

    # periksa dulu tanpa menulis apa pun
    python scripts/perbarui_syariah.py --dari DES.xlsx --berlaku 2026-06-01 --uji-coba

Format masukan yang diterima: .xlsx/.xls (butuh openpyxl), .csv, .txt, atau
apa pun yang isinya teks — termasuk hasil salin-tempel dari PDF. Skrip ini
tidak peduli tata letaknya; ia menyapu seluruh teks untuk kode empat huruf,
lalu membuang yang bukan emiten tercatat.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

KELUARAN = "data/syariah.txt"
UNIVERSE_CADANGAN = "tickers/idx.txt"

# Kode saham IDX selalu empat huruf kapital. Pola ini sengaja longgar — yang
# menyaring sungguhan adalah pencocokan dengan daftar emiten tercatat di
# bawah, bukan regex ini. Menyaring lewat regex saja akan meloloskan kata
# seperti "DAFTAR" atau "TOTAL" yang kebetulan ada di berkas DES.
POLA_KODE = re.compile(r"\b[A-Z]{4}\b")


def baca_teks(path: Path) -> str:
    """Ambil seluruh isi berkas sebagai teks, apa pun formatnya."""
    akhiran = path.suffix.lower()

    if akhiran in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError:
            sys.exit("Butuh pandas untuk membaca Excel. Jalankan: pip install pandas openpyxl")
        try:
            # sheet_name=None: DES kadang menaruh sahamnya di sheet kedua,
            # dengan sheet pertama berisi kata pengantar. Semua sheet dibaca
            # lalu disatukan jadi teks — lebih tahan banting daripada menebak.
            lembar = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        except ImportError:
            sys.exit("Butuh openpyxl untuk membaca .xlsx. Jalankan: pip install openpyxl")
        return "\n".join(df.to_string() for df in lembar.values())

    if akhiran == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            sys.exit(
                "Berkas PDF butuh pdfplumber (pip install pdfplumber).\n"
                "Alternatif tanpa memasang apa pun: buka PDF-nya, salin seluruh\n"
                "isinya ke berkas .txt, lalu jalankan skrip ini atas berkas itu."
            )
        with pdfplumber.open(path) as pdf:
            return "\n".join(h.extract_text() or "" for h in pdf.pages)

    return path.read_text(encoding="utf-8", errors="replace")


def emiten_tercatat() -> tuple[set[str], str]:
    """Himpunan seluruh kode emiten yang tercatat di IDX, untuk validasi.

    Sumber utamanya endpoint IDX; kalau tidak bisa dihubungi, dipakai
    tickers/idx.txt yang sudah ada di repo. Cadangan itu hanya memuat ~400
    emiten terbesar, jadi kode syariah di luar itu akan ikut terbuang —
    karena itu kegagalan endpoint dilaporkan dengan jelas, bukan didiamkan.
    """
    try:
        from curl_cffi import requests

        r = requests.get(
            "https://www.idx.co.id/primary/StockData/GetSecuritiesStock"
            "?start=0&length=2000&code=&sector=&board=&language=en-us",
            impersonate="chrome", timeout=60,
        )
        r.raise_for_status()
        kode = {str(b["Code"]).upper() for b in r.json()["data"] if b.get("Code")}
        if kode:
            return kode, f"IDX GetSecuritiesStock ({len(kode)} emiten tercatat)"
    except Exception as e:
        print(f"Tidak bisa menghubungi IDX ({type(e).__name__}), memakai "
              f"{UNIVERSE_CADANGAN} sebagai pembanding.", file=sys.stderr)

    cadangan = Path(UNIVERSE_CADANGAN)
    if not cadangan.exists():
        return set(), "tanpa pembanding"
    kode = set()
    for baris in cadangan.read_text(encoding="utf-8").splitlines():
        bersih = baris.split("#", 1)[0].strip().upper().removesuffix(".JK")
        if bersih:
            kode.add(bersih)
    print("PERINGATAN: memakai universe cadangan yang hanya memuat emiten besar. "
          "Saham syariah di luar daftar itu akan terbuang — periksa jumlah "
          "hasilnya sebelum di-commit.", file=sys.stderr)
    return kode, f"{UNIVERSE_CADANGAN} ({len(kode)} emiten, cadangan)"


def kode_sebelumnya(path: Path) -> set[str]:
    if not path.exists():
        return set()
    hasil = set()
    for baris in path.read_text(encoding="utf-8").splitlines():
        bersih = baris.split("#", 1)[0].strip().upper().removesuffix(".JK")
        if bersih:
            hasil.add(bersih)
    return hasil


def main():
    p = argparse.ArgumentParser(
        description="Ubah berkas DES resmi jadi data/syariah.txt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Pemakaian:")[1] if "Pemakaian:" in __doc__ else None,
    )
    p.add_argument("--dari", required=True, metavar="FILE",
                   help="berkas DES yang diunduh dari OJK/IDX (.xlsx, .csv, .txt, .pdf)")
    p.add_argument("--berlaku", required=True, metavar="YYYY-MM-DD",
                   help="tanggal mulai berlakunya penetapan DES ini")
    p.add_argument("--sumber", default="", metavar="TEKS",
                   help='keterangan asal, mis. "OJK Kep-45/D.04/2026"')
    p.add_argument("--output", default=KELUARAN, metavar="FILE")
    p.add_argument("--min-kode", type=int, default=300, metavar="N",
                   help="tolak hasil bila kode yang terbaca kurang dari ini "
                        "(default 300; DES biasanya memuat 500-600 saham)")
    p.add_argument("--uji-coba", action="store_true",
                   help="tampilkan hasilnya saja, jangan tulis berkas")
    args = p.parse_args()

    sumber_berkas = Path(args.dari)
    if not sumber_berkas.exists():
        sys.exit(f"Berkas {sumber_berkas} tidak ada.")
    try:
        date.fromisoformat(args.berlaku)
    except ValueError:
        sys.exit(f"--berlaku harus YYYY-MM-DD, bukan {args.berlaku!r}.")

    teks = baca_teks(sumber_berkas)
    kandidat = set(POLA_KODE.findall(teks.upper()))
    print(f"{len(kandidat)} kode empat huruf ditemukan di {sumber_berkas.name}.",
          file=sys.stderr)

    tercatat, asal_pembanding = emiten_tercatat()
    if tercatat:
        kode = sorted(kandidat & tercatat)
        dibuang = sorted(kandidat - tercatat)
        print(f"Dicocokkan dengan {asal_pembanding}: {len(kode)} cocok, "
              f"{len(dibuang)} dibuang.", file=sys.stderr)
        if dibuang:
            print(f"  Dibuang: {', '.join(dibuang[:15])}"
                  f"{' ...' if len(dibuang) > 15 else ''}", file=sys.stderr)
    else:
        kode = sorted(kandidat)
        print("Tidak ada pembanding — seluruh kode empat huruf dipakai apa "
              "adanya. Periksa hasilnya dengan mata.", file=sys.stderr)

    # Ambang ini yang membedakan "berkasnya terbaca" dari "berkasnya terbuka
    # tapi isinya bukan yang kita kira". Tanpa ini, salah pilih berkas
    # menghasilkan data/syariah.txt berisi tiga kode, dan seluruh pasar
    # mendadak tampak non-syariah tanpa satu pun pesan error.
    if len(kode) < args.min_kode:
        sys.exit(f"Hanya {len(kode)} kode yang terbaca, di bawah ambang "
                 f"{args.min_kode}. Kemungkinan berkasnya salah atau tata "
                 f"letaknya tidak terbaca. Periksa dulu; pakai --min-kode "
                 f"untuk menurunkan ambang bila memang disengaja.")

    keluaran = Path(args.output)
    lama = kode_sebelumnya(keluaran)
    if lama:
        masuk = sorted(set(kode) - lama)
        keluar = sorted(lama - set(kode))
        print(f"Dibanding daftar lama ({len(lama)} saham): "
              f"+{len(masuk)} masuk, -{len(keluar)} keluar.", file=sys.stderr)
        if masuk:
            print(f"  Masuk DES : {', '.join(masuk)}", file=sys.stderr)
        if keluar:
            print(f"  Keluar DES: {', '.join(keluar)}", file=sys.stderr)

    baris = [
        "# Daftar Efek Syariah (DES) — saham syariah yang tercatat di IDX.",
        "#",
        "# Dibuat oleh scripts/perbarui_syariah.py. Jangan disunting tangan:",
        "# jalankan ulang skripnya atas berkas DES resmi yang baru, supaya",
        "# provenance di bawah selalu cocok dengan isinya.",
        "#",
        f"# sumber: {args.sumber or sumber_berkas.name}",
        f"# berlaku: {args.berlaku}",
        f"# disusun: {date.today().isoformat()}",
        f"# jumlah: {len(kode)}",
        "",
    ] + kode + [""]
    isi = "\n".join(baris)

    if args.uji_coba:
        print(f"\n[uji coba] {len(kode)} kode, {keluaran} TIDAK ditulis.",
              file=sys.stderr)
        print(isi[:400] + ("\n..." if len(isi) > 400 else ""))
        return

    keluaran.parent.mkdir(parents=True, exist_ok=True)
    keluaran.write_text(isi, encoding="utf-8")
    print(f"{len(kode)} saham syariah ditulis ke {keluaran}.", file=sys.stderr)


if __name__ == "__main__":
    main()
