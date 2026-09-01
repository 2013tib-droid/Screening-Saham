#!/usr/bin/env python3
"""Susun ulang data/syariah.txt dari Daftar Efek Syariah (DES) resmi.

DES ditetapkan OJK dua kali setahun (berlaku 1 Juni dan 1 Desember), plus
penetapan insidentil untuk emiten yang baru IPO. Hasilnya di-commit ke repo
sehingga run malam tidak pernah bergantung pada jaringan untuk kolom ini.

Berkas PDF-nya bisa diunduh langsung dari OJK — inilah yang dipakai:

    https://ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/

Perhatikan kanalnya: **syariah**, bukan pasar-modal. Salah kanal menjawab
"Request Rejected" dari WAF, dan itu gampang disalahartikan sebagai "OJK
memblokir akses otomatis". Yang benar-benar terkunci cuma IDX: endpoint
`Index/GetConstituent` dan halaman `idx.co.id/id/idx-syariah/` menjawab 503
dari Varnish, dan arsip `StockData/GetIndexConstituent` berhenti di 2018.

Pemakaian:
    python scripts/perbarui_syariah.py --dari DES.pdf \\
        --berlaku 2026-06-01 --sumber "OJK KEP-21/D.04/2026"

    # periksa dulu tanpa menulis apa pun
    python scripts/perbarui_syariah.py --dari DES.pdf --berlaku 2026-06-01 --uji-coba

Format masukan: .pdf (butuh pdfplumber), .xlsx/.xls (butuh openpyxl), .csv,
.txt, atau apa pun yang isinya teks. Kode dibaca dari bentuk baris tabelnya
("1 BANK PT Bank Aladin Syariah Tbk"); berkas yang isinya cuma daftar kode
polos ditangani jalur cadangan yang lebih longgar dan lebih berisik.
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

KELUARAN = "data/syariah.txt"
UNIVERSE_CADANGAN = "tickers/idx.txt"

# Baris tabel DES: nomor urut, kode empat huruf, lalu nama penerbitnya.
#     1 BANK PT Bank Aladin Syariah Tbk
# Ini jalur utamanya, dan jauh lebih tepat daripada menyapu seluruh teks.
POLA_BARIS = re.compile(r"^\s*\d+\s+([A-Z]{4})\s+\S.*$", re.M)

# Cadangan untuk berkas yang isinya cuma daftar kode tanpa nomor dan nama,
# mis. hasil salin-tempel satu kode per baris.
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


def ambil_kode(teks: str) -> tuple[list[str], bool]:
    """Ambil kode saham dari teks DES. Mengembalikan (kode, terstruktur).

    Dua jalur, dan yang pertama jauh lebih dipercaya.

    Menyapu seluruh teks untuk kata empat huruf terdengar cukup sampai dicoba
    pada DES sungguhan. Sapuan atas KEP-21/D.04/2026 menghasilkan 699
    kandidat, dan yang lolos pencocokan dengan daftar emiten IDX pun masih
    625 — tiga lebih banyak daripada 622 yang sebenarnya. Kelebihannya bukan
    sampah yang gampang dikenali, melainkan kata di dalam NAMA perusahaan
    yang kebetulan juga kode sah: "PT Adhi Karya" menyumbang ADHI, "PT Duta
    Intidaya" menyumbang DUTA. Pencocokan ke daftar emiten tidak bisa
    menolongnya, justru karena kode-kode itu memang benar-benar ada.

    Jadi yang dipakai adalah bentuk barisnya. Membaca baris tabel bernomor
    memberi tepat 622 kode, cocok dengan jumlah yang diumumkan OJK.
    """
    baris = POLA_BARIS.findall(teks)
    if baris:
        return sorted(set(baris)), True
    return sorted(set(POLA_KODE.findall(teks.upper()))), False


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
    kode, terstruktur = ambil_kode(teks)
    cara = "baris tabel bernomor" if terstruktur else "sapuan kata empat huruf"
    print(f"{len(kode)} kode dibaca dari {sumber_berkas.name} lewat {cara}.",
          file=sys.stderr)

    tercatat, asal_pembanding = emiten_tercatat()
    if terstruktur:
        # Bentuk barisnya sudah menjamin ini kolom kode, bukan kata yang
        # kebetulan empat huruf, jadi daftar emiten IDX dipakai untuk
        # MELAPORKAN saja — bukan menyaring. DES memuat juga perusahaan
        # publik yang tidak tercatat di bursa (mis. Bank Muamalat), dan
        # membuangnya akan membuat daftar ini tidak lagi sama dengan DES.
        luar = sorted(set(kode) - tercatat) if tercatat else []
        if luar:
            print(f"{len(luar)} kode tidak ada di {asal_pembanding} — "
                  f"tetap disimpan, kemungkinan perusahaan publik non-bursa "
                  f"atau emiten yang baru tercatat: {', '.join(luar[:15])}"
                  f"{' ...' if len(luar) > 15 else ''}", file=sys.stderr)
    elif tercatat:
        # Jalur sapuan tidak bisa membedakan kode dari kata, jadi di sini
        # pencocokan ke daftar emiten benar-benar dipakai untuk menyaring —
        # dan hasilnya tetap perlu dilihat mata sebelum di-commit.
        semula = len(kode)
        dibuang = sorted(set(kode) - tercatat)
        kode = sorted(set(kode) & tercatat)
        print(f"Dicocokkan dengan {asal_pembanding}: {len(kode)} dari {semula} "
              f"cocok, {len(dibuang)} dibuang.", file=sys.stderr)
        if dibuang:
            print(f"  Dibuang: {', '.join(dibuang[:15])}"
                  f"{' ...' if len(dibuang) > 15 else ''}", file=sys.stderr)
        print("PERINGATAN: berkas ini tidak berbentuk tabel bernomor, jadi "
              "kode dibaca lewat sapuan yang bisa menangkap kata dari nama "
              "perusahaan. Periksa jumlahnya sebelum di-commit.", file=sys.stderr)
    else:
        print("Tidak ada pembanding — kode dipakai apa adanya. Periksa "
              "hasilnya dengan mata.", file=sys.stderr)

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
        "# Daftar Efek Syariah (DES) OJK - efek syariah berupa saham.",
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
