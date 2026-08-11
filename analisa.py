#!/usr/bin/env python3
"""Laporan fundamental lengkap untuk satu emiten, dalam format Markdown.

Beda dari screener: screener menjawab "dari 400 emiten, mana yang layak
dilihat", sedangkan skrip ini menjawab "emiten ini bagaimana persisnya".
Keduanya memakai sumber angka yang sama (cache fundamental + hasil screening),
jadi laporan ini tidak menarik apa pun dari internet selama datanya sudah ada.

Yang dihasilkan: tabel skor lima kategori, rincian metrik per kategori
lengkap dengan pembanding median sektor, red flag, taksiran nilai wajar
beserta margin of safety, dan tingkat keyakinan yang dihitung dari
selengkap-tidaknya data.

Yang TIDAK dihasilkan dan memang tidak bisa: bull/bear case, moat, kualitas
manajemen, dan katalis. Semua itu menuntut penilaian atas hal-hal yang tidak
ada di laporan keuangan — rencana korporasi, posisi bersaing, rekam jejak
manajemen mengalokasikan modal. Bagian itu dikeluarkan sebagai daftar bukti
dan pertanyaan terarah, bukan sebagai kesimpulan yang dikarang skrip.

Pemakaian:
    python analisa.py BBCA
    python analisa.py ANTM --dari-csv hasil/semua.csv
    python analisa.py TLKM --output analisa_TLKM.md
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from screener import (BOBOT_KATEGORI, CACHE_FUNDAMENTAL, FLAG_TIDAK_BERLAKU,
                      KOMPONEN_SKOR, MIN_CAKUPAN_KATEGORI, PENYESUAIAN_SEKTOR,
                      RED_FLAG, STATUS, _angka, hitung_flag, hitung_skor,
                      skor_kategori)

# Ambang penilaian valuasi terhadap taksiran nilai wajar. Rentang 15% di
# kedua sisi sengaja lebar: taksiran ini berbasis median sektor yang sendirinya
# bergerak tiap hari, jadi selisih beberapa persen bukan sinyal apa-apa.
BATAS_MURAH, BATAS_MAHAL = 0.85, 1.15

KATEGORI_JUDUL = {
    "Valuasi": "Valuation",
    "Profitabilitas": "Profitability & Earnings Quality",
    "Kesehatan": "Financial Health",
    "Pertumbuhan": "Growth",
    "ArusKas": "Cash Flow & Capital Allocation",
}

# Ambang "bagus" dan "buruk" per komponen, dipakai menyusun daftar kekuatan
# dan kelemahan. Diambil dari titik acuan skor: komponen yang skornya >= 75
# dianggap kekuatan, <= 40 dianggap kelemahan — jadi daftarnya selalu
# konsisten dengan angka di tabel, bukan penilaian terpisah.
SKOR_KUAT, SKOR_LEMAH = 75, 40

SATUAN = {
    "PER": "x", "PBV": "x", "EV/EBITDA": "x", "DER": "x",
    "UtangBersih/EBITDA": "x", "CurrentRatio": "x", "QuickRatio": "x",
    "InterestCoverage": "x", "OCF/Laba": "x", "Capex/OCF": "x",
    "PERvsSektor": "x median", "PBVvsSektor": "x median",
    "TahunLabaNaik": " dari 3 tahun",
}


def _teks(r, kolom: str) -> str:
    """Nilai teks satu kolom, dengan NaN diperlakukan sebagai kosong.

    Perlu helper sendiri karena `r.get(k) or ""` tidak cukup: NaN adalah nilai
    yang truthy, jadi ungkapan itu meloloskannya dan str() mengubahnya jadi
    "nan" — string yang lalu tercetak apa adanya di laporan dan, lebih buruk,
    lolos dari pemeriksaan "kalau kosong".
    """
    nilai = r.get(kolom)
    if nilai is None or (isinstance(nilai, float) and pd.isna(nilai)):
        return ""
    return str(nilai)


def format_nilai(kolom: str, nilai) -> str:
    if nilai is None or pd.isna(nilai):
        return "-"
    nilai = float(nilai)
    if kolom.endswith("%"):
        return f"{nilai:,.1f}%"
    return f"{nilai:,.2f}{SATUAN.get(kolom, '')}"


def format_rupiah(nilai) -> str:
    """Angka rupiah besar dalam satuan triliun/miliar, biar terbaca manusia."""
    if nilai is None or pd.isna(nilai):
        return "-"
    nilai = float(nilai)
    tanda = "-" if nilai < 0 else ""
    n = abs(nilai)
    if n >= 1e12:
        return f"{tanda}Rp {n / 1e12:,.2f} T"
    if n >= 1e9:
        return f"{tanda}Rp {n / 1e9:,.1f} M"
    if n >= 1e6:
        return f"{tanda}Rp {n / 1e6:,.1f} jt"
    return f"{tanda}Rp {n:,.0f}"


def median_sektor(df: pd.DataFrame, sektor: str, kolom: str) -> float | None:
    """Median satu kolom di dalam sektor, hanya dari nilai positif.

    Nilai negatif dibuang dengan alasan yang sama seperti di screener: PER
    negatif berarti emitennya rugi, dan memasukkannya menarik median ke bawah
    seolah-olah sektornya sedang murah.
    """
    if not sektor or kolom not in df.columns:
        return None
    nilai = pd.to_numeric(df.loc[df["Sektor"] == sektor, kolom], errors="coerce")
    nilai = nilai[nilai > 0]
    return float(nilai.median()) if len(nilai) >= 3 else None


def nilai_wajar(r, df: pd.DataFrame) -> tuple[float | None, list[str], list[str]]:
    """Taksir nilai wajar per saham dari median sektor.

    Dua jangkar dipakai bersama, bukan salah satu: PER × EPS runtuh ketika
    labanya sedang tidak normal, dan PBV × BVPS runtuh ketika nilai bukunya
    tidak mencerminkan daya hasil. Kalau keduanya ada, dipakai rata-ratanya.

    DCF sengaja tidak dilakukan. Data yang ada hanya menyediakan pertumbuhan
    tiga tahun ke belakang; menurunkan proyeksi arus kas sepuluh tahun ke depan
    darinya akan menghasilkan angka yang terlihat presisi tapi sepenuhnya
    ditentukan asumsi yang dikarang sendiri.

    Mengembalikan (nilai wajar, daftar asumsi, daftar peringatan).
    """
    sektor = _teks(r, "Sektor")
    eps, bvps = _angka(r, "EPS"), _angka(r, "BVPS")
    taksiran, asumsi, catatan = [], [], []

    med_per = median_sektor(df, sektor, "PER")
    if med_per and eps and eps > 0:
        taksiran.append(med_per * eps)
        asumsi.append(f"PER wajar = median sektor {sektor} ({med_per:,.1f}x), "
                      f"dikalikan EPS {eps:,.2f}")
    elif eps is not None and eps <= 0:
        catatan.append("EPS negatif — jangkar PER tidak dipakai")
    elif not med_per:
        catatan.append(f"median PER sektor {sektor} tidak tersedia "
                       "(pembanding kurang dari 3 emiten)")

    med_pbv = median_sektor(df, sektor, "PBV")
    if med_pbv and bvps and bvps > 0:
        taksiran.append(med_pbv * bvps)
        asumsi.append(f"PBV wajar = median sektor {sektor} ({med_pbv:,.2f}x), "
                      f"dikalikan nilai buku per saham {bvps:,.2f}")
    elif bvps is not None and bvps <= 0:
        catatan.append("nilai buku per saham negatif — jangkar PBV tidak dipakai")

    # Median sektor memperlakukan seluruh isi sektor sebagai sebanding, padahal
    # tidak. "Financial Services" menampung 68 emiten mulai dari bank terbesar
    # sampai multifinance kecil, dan median PBV-nya 0,88 — dipakai apa adanya,
    # jangkar itu menyimpulkan BBCA (PBV 2,9) kemahalan 53%. Padahal perusahaan
    # yang menghasilkan imbal hasil jauh di atas sektornya memang layak
    # diperdagangkan di atas PBV median; itu hubungan yang melekat antara ROE
    # dan P/B, bukan anomali harga. Selisihnya tidak dikoreksi otomatis — arah
    # biasnya saja yang dinyatakan, supaya pembacanya tidak menelan angka MoS
    # mentah-mentah.
    roe = _angka(r, "ROE%")
    med_roe = median_sektor(df, sektor, "ROE%")
    if roe and med_roe and med_roe > 0:
        if roe > 1.3 * med_roe:
            catatan.append(
                f"ROE {roe:,.1f}% jauh di atas median sektor ({med_roe:,.1f}%) — "
                "jangkar PBV kemungkinan **merendahkan** nilai wajarnya, karena "
                "emiten dengan imbal hasil di atas sektornya wajar dihargai "
                "premium terhadap PBV median")
        elif roe < 0.7 * med_roe:
            catatan.append(
                f"ROE {roe:,.1f}% di bawah median sektor ({med_roe:,.1f}%) — "
                "jangkar PBV kemungkinan **meninggikan** nilai wajarnya")

    if not taksiran:
        return None, asumsi, catatan
    if len(taksiran) == 2:
        selisih = max(taksiran) / min(taksiran) if min(taksiran) > 0 else None
        asumsi.append("Nilai wajar akhir = rata-rata kedua jangkar, karena "
                      "masing-masing punya titik butanya sendiri")
        if selisih and selisih > 2:
            catatan.append(
                f"kedua jangkar berselisih {selisih:.1f}x "
                f"(PER menunjuk {max(taksiran):,.0f}, PBV menunjuk "
                f"{min(taksiran):,.0f} — atau sebaliknya). Selisih sebesar itu "
                "berarti rata-ratanya tidak berarti banyak; periksa mana yang "
                "lebih relevan untuk emiten ini sebelum memakainya")
    return sum(taksiran) / len(taksiran), asumsi, catatan


def tingkat_keyakinan(r, df: pd.DataFrame) -> tuple[int, list[str]]:
    """Keyakinan 0-100 atas laporan ini, beserta alasan pengurangannya.

    Bukan keyakinan bahwa sahamnya akan naik — melainkan seberapa jauh angka
    di laporan ini boleh dipercaya. Turun ketika datanya tidak lengkap, basi,
    atau ketika pembanding sektornya terlalu tipis untuk berarti.
    """
    nilai = 100
    alasan = []

    basis = _teks(r, "Basis")
    if basis == "Tahunan":
        nilai -= 25
        alasan.append("angka aliran memakai laporan **tahunan**, bukan TTM — "
                      "bisa beberapa bulan tertinggal dari kondisi terakhir")
    elif basis == "TTM-gabungan":
        nilai -= 5
        alasan.append("TTM disusun dari tahunan + YTD karena ada kuartal yang "
                      "hilang di data Yahoo (lazim untuk emiten IDX)")
    elif not basis:
        nilai -= 35
        alasan.append("basis perhitungan tidak diketahui — emiten ini mungkin "
                      "belum tercakup cache fundamental")

    kosong = [k for k in ("EPS", "BVPS", "ROE%", "OCF", "FCF", "TotalUtang")
              if _angka(r, k) is None]
    if kosong:
        nilai -= min(30, 6 * len(kosong))
        alasan.append(f"{len(kosong)} metrik inti kosong: {', '.join(kosong)}")

    sektor = _teks(r, "Sektor")
    jumlah_sektor = int((df["Sektor"] == sektor).sum()) if sektor else 0
    if jumlah_sektor < 3:
        nilai -= 15
        alasan.append(f"pembanding sektor cuma {jumlah_sektor} emiten — "
                      "perbandingan valuasi relatif tidak bisa diandalkan")

    nilai_transaksi = _angka(r, "Nilai(M)")
    if nilai_transaksi is not None and nilai_transaksi < 1:
        nilai -= 10
        alasan.append("likuiditas sangat tipis — harga pasarnya sendiri belum "
                      "tentu mencerminkan nilai yang bisa direalisasi")

    if sektor == "Financial Services":
        nilai -= 10
        alasan.append("emiten keuangan: NIM, NPL, CAR, dan LDR tidak tersedia "
                      "di sumber data gratis ini, padahal itu justru metrik "
                      "penilai utama sebuah bank")

    return max(5, min(100, nilai)), alasan


def kategori_skor(skor: int | None) -> str:
    if skor is None:
        return "Tidak dapat disimpulkan"
    for batas, label in ((90, "Exceptional"), (80, "Excellent"), (65, "Good"),
                         (50, "Average / Fair"), (35, "Weak")):
        if skor >= batas:
            return label
    return "Poor / Avoid"


def rekomendasi(skor: int | None, mos: float | None, flag: str) -> tuple[str, str]:
    """Rekomendasi akhir beserta alasannya.

    Aturannya sengaja kaku dan bisa diperiksa, bukan penilaian bebas: cacat
    berat memveto skor bagus, karena skor adalah rata-rata dan rata-rata bisa
    menutupi satu lubang besar dengan banyak angka bagus.
    """
    punya = set(flag.split(",")) if flag else set()

    # Dua tingkat veto, bukan satu. Ekuitas negatif dan kerugian adalah cacat
    # struktural: perusahaannya sedang menghancurkan modal, dan berapa pun
    # murahnya itu tidak berubah.
    struktural = {"ekuitas-", "rugi"} & punya
    if struktural:
        return "Avoid", (f"cacat struktural pada {', '.join(sorted(struktural))} "
                         "memveto berapa pun skornya")
    if skor is None:
        return "Avoid", "data fundamentalnya terlalu tipis untuk dinilai"

    # Arus kas operasi negatif diperlakukan lebih ringan: pada emiten yang
    # tetap untung, ini sering ayunan modal kerja satu periode — persediaan
    # menumpuk atau piutang membengkak — bukan tanda bisnisnya rusak. Cukup
    # untuk membatalkan ajakan menambah posisi, belum cukup untuk menyuruh
    # keluar. ANTM contohnya: skor 74 dengan OCF minus satu periode.
    if "OCF-" in punya and skor >= 65:
        return "Hold", ("fundamentalnya layak, tapi arus kas operasi negatif "
                        "harus dipastikan dulu penyebabnya sebelum menambah")

    if skor >= 75 and (mos is None or mos > 10):
        return "Accumulate", "fundamental kuat dan harganya belum melampaui taksiran wajar"
    if skor >= 65:
        return "Hold", "fundamental layak, tapi harganya tidak memberi diskon berarti"
    if skor >= 50:
        return "Hold", "fundamental menengah — tidak ada alasan menambah maupun buru-buru keluar"
    if skor >= 35:
        return "Reduce", "fundamentalnya lemah di lebih dari satu kategori"
    return "Avoid", "fundamentalnya buruk"


def baris_komponen(r, kategori: str, sektor: str) -> list[str]:
    """Rincian tiap komponen dalam satu kategori sebagai baris tabel Markdown."""
    penyesuaian = PENYESUAIAN_SEKTOR.get(sektor, {})
    baris = []
    for kolom, (bobot_dasar, titik) in KOMPONEN_SKOR[kategori].items():
        faktor = penyesuaian.get(kolom, 1.0)
        if faktor <= 0:
            baris.append(f"| {kolom} | – | – | tidak berlaku untuk sektor ini |")
            continue
        nilai = _angka(r, kolom)
        if nilai is None:
            baris.append(f"| {kolom} | - | - | data tidak tersedia |")
            continue
        from screener import _interpolasi
        skor = (0.0 if kolom in ("PER", "PBV", "PERvsSektor", "PBVvsSektor",
                                 "EV/EBITDA") and nilai <= 0
                else _interpolasi(nilai, titik))
        bobot = f"{bobot_dasar * faktor:.0f}"
        if faktor != 1.0:
            bobot += f" (×{faktor:g})"
        baris.append(f"| {kolom} | {format_nilai(kolom, nilai)} | "
                     f"{skor:.0f} | bobot {bobot} |")
    return baris


def susun_laporan(r, df: pd.DataFrame) -> str:
    sektor = _teks(r, "Sektor")
    harga = _angka(r, "Harga")
    skor = hitung_skor(r)
    flag = hitung_flag(r)
    fv, asumsi, catatan_fv = nilai_wajar(r, df)
    mos = (fv - harga) / fv * 100 if fv and harga else None
    keyakinan, alasan_keyakinan = tingkat_keyakinan(r, df)
    aksi, alasan_aksi = rekomendasi(skor, mos, flag)

    if fv and harga:
        rasio = harga / fv
        status_valuasi = ("Undervalued" if rasio < BATAS_MURAH
                          else "Overvalued" if rasio > BATAS_MAHAL
                          else "Fairly Valued")
    else:
        status_valuasi = "Tidak dapat ditentukan"

    # Kekuatan dan kelemahan diambil dari komponen yang skornya ekstrem, jadi
    # daftarnya selalu konsisten dengan tabel di atasnya.
    from screener import _interpolasi
    kuat, lemah = [], []
    penyesuaian = PENYESUAIAN_SEKTOR.get(sektor, {})
    for kategori, komponen in KOMPONEN_SKOR.items():
        for kolom, (bobot_dasar, titik) in komponen.items():
            if penyesuaian.get(kolom, 1.0) <= 0:
                continue
            nilai = _angka(r, kolom)
            if nilai is None:
                continue
            s = (0.0 if kolom in ("PER", "PBV", "PERvsSektor", "PBVvsSektor",
                                  "EV/EBITDA") and nilai <= 0
                 else _interpolasi(nilai, titik))
            teks = f"**{kolom}** {format_nilai(kolom, nilai)}"
            if s >= SKOR_KUAT:
                kuat.append((s, teks))
            elif s <= SKOR_LEMAH:
                lemah.append((s, teks))
    kuat.sort(reverse=True)
    lemah.sort()

    b = []
    a = b.append
    nama = r.get("Nama") or r["Ticker"]
    a(f"# Analisa Fundamental: {r['Ticker']} — {nama}\n")
    mata_uang = _teks(r, "MataUang")
    a(f"> Sektor {sektor or '-'} · harga {format_nilai('Harga', harga)} · "
      f"periode lapkeu {_teks(r, 'Periode') or '-'} "
      f"(basis {_teks(r, 'Basis') or '-'}"
      + (f", laporan dalam {mata_uang}" if mata_uang not in ("", "IDR") else "")
      + ")\n")

    # 1. Ringkasan
    a("## 1. Ringkasan\n")
    ringkas = [
        f"{r['Ticker']} mendapat skor fundamental **{skor if skor is not None else '-'}"
        f"/100** ({kategori_skor(skor)}).",
    ]
    if kuat:
        ringkas.append(f"Kekuatan terbesarnya ada pada {kuat[0][1]}"
                       + (f" dan {kuat[1][1]}" if len(kuat) > 1 else "") + ".")
    if lemah:
        ringkas.append(f"Titik terlemahnya {lemah[0][1]}"
                       + (f" dan {lemah[1][1]}" if len(lemah) > 1 else "") + ".")
    ringkas.append(f"Valuasinya **{status_valuasi}**"
                   + (f" dengan margin of safety {mos:+.1f}%" if mos is not None else "")
                   + ".")
    ringkas.append(f"Red flag: {flag if flag else 'tidak ada'}.")
    ringkas.append(f"Rekomendasi **{aksi}** ({alasan_aksi}) "
                   f"pada tingkat keyakinan {keyakinan}%.")
    a(" ".join(ringkas) + "\n")

    # 2. Tabel skor
    a("## 2. Tabel Skor\n")
    a("| Faktor | Bobot | Skor |")
    a("|---|---|---|")
    dipakai = 0
    for kategori, bobot in BOBOT_KATEGORI.items():
        s, cakupan = skor_kategori(r, kategori, sektor)
        if s is None or cakupan < MIN_CAKUPAN_KATEGORI:
            a(f"| {KATEGORI_JUDUL[kategori]} | {bobot} | – (data tidak cukup) |")
            continue
        dipakai += bobot
        a(f"| {KATEGORI_JUDUL[kategori]} | {bobot} | {s:.0f} |")
    a(f"| **Total Fundamental Score** | 100 | "
      f"**{skor if skor is not None else '-'}/100** |\n")
    if dipakai < 100:
        a(f"Kategori yang datanya tidak cukup dibuang dan bobotnya dibagi ulang; "
          f"skor akhir disusun dari {dipakai} dari 100 bobot asli.\n")

    # 3. Rincian per kategori
    a("## 3. Rincian per Kategori\n")
    for kategori in BOBOT_KATEGORI:
        a(f"### {KATEGORI_JUDUL[kategori]}\n")
        a("| Metrik | Nilai | Skor | Catatan |")
        a("|---|---|---|---|")
        b.extend(baris_komponen(r, kategori, sektor))
        a("")

    # 4. Angka pendukung
    a("## 4. Angka Pendukung\n")
    a("| Pos | Nilai |")
    a("|---|---|")
    for label, kolom in (("Kapitalisasi pasar", "MarketCap(T)"),
                         ("Omzet (TTM)", "Omzet"),
                         ("Laba bersih (TTM)", "LabaBersih"),
                         ("EBITDA", "EBITDA"),
                         ("Arus kas operasi", "OCF"),
                         ("Belanja modal", "Capex"),
                         ("Arus kas bebas", "FCF"),
                         ("Total utang", "TotalUtang"),
                         ("Kas & setara", "Kas"),
                         ("Utang bersih", "UtangBersih"),
                         ("Ekuitas", "Ekuitas")):
        nilai = _angka(r, kolom)
        teks = (f"{nilai:,.1f} T" if kolom == "MarketCap(T)" and nilai is not None
                else format_rupiah(nilai))
        a(f"| {label} | {teks} |")
    a(f"| EPS | {format_nilai('EPS', _angka(r, 'EPS'))} |")
    a(f"| Nilai buku per saham | {format_nilai('BVPS', _angka(r, 'BVPS'))} |")
    a(f"| Dividen per saham | {format_nilai('DPS', _angka(r, 'DPS'))} |")
    a("")

    # 5. Kekuatan & kelemahan
    a("## 5. Kekuatan dan Kelemahan\n")
    a("**Kekuatan utama**\n")
    b.extend(f"- {t}" for _, t in kuat[:6]) if kuat else a(
        "- Tidak ada metrik yang menonjol kuat.")
    a("")
    a("**Kelemahan dan risiko**\n")
    b.extend(f"- {t}" for _, t in lemah[:6]) if lemah else a(
        "- Tidak ada metrik yang menonjol lemah.")
    a("")

    # 6. Red flags
    a("## 6. Red Flags\n")
    if flag:
        kecuali = FLAG_TIDAK_BERLAKU.get(sektor, set())
        for kode, uji, penjelasan in RED_FLAG:
            if kode not in kecuali and uji(r):
                a(f"- 🚩 **{kode}** — {penjelasan}")
    else:
        a("Tidak ada red flag terdeteksi.")
    if sektor in FLAG_TIDAK_BERLAKU:
        a(f"\nCatatan: flag {', '.join(sorted(FLAG_TIDAK_BERLAKU[sektor]))} "
          f"dimatikan untuk sektor {sektor} karena tidak bermakna di sana.")
    a("")

    # 7. Valuasi
    a("## 7. Status Valuasi dan Nilai Wajar\n")
    a(f"**Status: {status_valuasi}**\n")
    a("| | Nilai |")
    a("|---|---|")
    a(f"| Harga saat ini | {format_nilai('Harga', harga)} |")
    a(f"| Taksiran nilai wajar | {format_nilai('FV', fv) if fv else '-'} |")
    a(f"| Margin of Safety | {f'{mos:+.1f}%' if mos is not None else '-'} |")
    if fv and harga:
        a(f"| Harga terhadap nilai wajar | {harga / fv:,.2f}x |")
    a(f"| PER | {format_nilai('PER', _angka(r, 'PER'))} "
      f"(median sektor {format_nilai('PER', median_sektor(df, sektor, 'PER'))}) |")
    a(f"| PBV | {format_nilai('PBV', _angka(r, 'PBV'))} "
      f"(median sektor {format_nilai('PBV', median_sektor(df, sektor, 'PBV'))}) |")
    a(f"| EV/EBITDA | {format_nilai('EV/EBITDA', _angka(r, 'EV/EBITDA'))} |")
    a("")
    if asumsi:
        a("**Asumsi yang dipakai**\n")
        b.extend(f"- {x}" for x in asumsi)
        a("")
    # Margin of safety di luar ±100% bukan pengukuran lagi. Itu terjadi ketika
    # penyebutnya nyaris nol — SRAJ menghasilkan -6.675% semata karena nilai
    # bukunya tinggal sesaput. Angkanya tetap ditampilkan apa adanya, tapi
    # pembacanya diberi tahu bahwa yang dibaca adalah penyebut yang runtuh,
    # bukan diskon atau premi sebesar itu.
    if mos is not None and abs(mos) > 100:
        catatan_fv.append(
            "margin of safety melampaui ±100%, yang berarti penyebutnya "
            "(taksiran nilai wajar) nyaris nol — bacalah sebagai 'jangkar "
            "valuasinya runtuh', bukan sebagai besaran diskon atau premi")
    if catatan_fv:
        a("**Keterbatasan taksiran**\n")
        b.extend(f"- {x}" for x in catatan_fv)
        a("")
    a("DCF sengaja tidak dihitung: data yang ada hanya menyediakan pertumbuhan "
      "tiga tahun ke belakang, dan menurunkan proyeksi sepuluh tahun ke depan "
      "darinya menghasilkan angka yang terlihat presisi tapi sepenuhnya "
      "ditentukan asumsi yang dikarang sendiri.\n")

    # 8. Bahan investment thesis
    a("## 8. Bahan Investment Thesis\n")
    a("Bagian ini **tidak** disimpulkan otomatis. Bull/bear case, moat, "
      "katalis, dan kualitas manajemen menuntut penilaian atas hal yang tidak "
      "ada di laporan keuangan. Yang bisa disediakan skrip adalah buktinya:\n")
    a("| Pertanyaan | Bukti dari data |")
    a("|---|---|")
    a(f"| Apakah pertumbuhannya konsisten atau sesaat? | laba naik "
      f"{format_nilai('TahunLabaNaik', _angka(r, 'TahunLabaNaik'))}; "
      f"CAGR laba 3 th {format_nilai('LabaCAGR3%', _angka(r, 'LabaCAGR3%'))}, "
      f"YoY terakhir {format_nilai('LabaYoY%', _angka(r, 'LabaYoY%'))} |")
    a(f"| Apakah labanya jadi kas? | OCF/Laba "
      f"{format_nilai('OCF/Laba', _angka(r, 'OCF/Laba'))}, FCF "
      f"{format_rupiah(_angka(r, 'FCF'))} |")
    a(f"| Apakah manajemen mendilusi pemegang saham? | jumlah saham "
      f"{format_nilai('SahamYoY%', _angka(r, 'SahamYoY%'))} YoY "
      f"(negatif = buyback) |")
    a(f"| Apakah dividennya lestari? | payout "
      f"{format_nilai('Payout%', _angka(r, 'Payout%'))}, yield "
      f"{format_nilai('Dividen%', _angka(r, 'Dividen%'))}, FCF yield "
      f"{format_nilai('FCFYield%', _angka(r, 'FCFYield%'))} |")
    a(f"| Seberapa agresif belanja modalnya? | Capex "
      f"{format_rupiah(_angka(r, 'Capex'))}, Capex/OCF "
      f"{format_nilai('Capex/OCF', _angka(r, 'Capex/OCF'))} |")
    a(f"| Sanggupkah bertahan bila kondisi memburuk? | DER "
      f"{format_nilai('DER', _angka(r, 'DER'))}, interest coverage "
      f"{format_nilai('InterestCoverage', _angka(r, 'InterestCoverage'))}, "
      f"utang bersih {format_rupiah(_angka(r, 'UtangBersih'))} |")
    a("")
    a("Yang masih harus dicari di luar skrip ini: rencana korporasi dan "
      "katalis 6–12 bulan, posisi bersaing dan sumber moat, rekam jejak "
      "manajemen memenuhi guidance, serta apakah laba terakhir mengandung "
      "pos sekali jalan seperti penjualan aset atau selisih kurs.\n")

    # 9. Keyakinan & kesimpulan
    a("## 9. Tingkat Keyakinan\n")
    a(f"**{keyakinan}%** — seberapa jauh angka di laporan ini boleh dipercaya, "
      "bukan seberapa yakin sahamnya akan naik.\n")
    if alasan_keyakinan:
        a("Pengurangnya:\n")
        b.extend(f"- {x}" for x in alasan_keyakinan)
    else:
        a("Data lengkap dan segar; tidak ada pengurang.")
    a("")

    a("## 10. Kesimpulan\n")
    a(f"**{aksi}** — {alasan_aksi}.\n")
    status_teknikal = _teks(r, "Status") or "-"
    a(f"Sebagai catatan waktu masuk, status teknikalnya saat ini "
      f"**{status_teknikal}** ({STATUS.get(status_teknikal, '-')}). "
      "Skor fundamental dan status teknikal menjawab pertanyaan yang berbeda "
      "dan sengaja tidak digabung: emiten bagus yang sedang turun tren tetap "
      "emiten bagus, hanya belum tentu saat ini waktunya.\n")
    a("---\n")
    a("*Laporan ini disusun otomatis dari data Yahoo Finance dan bukan "
      "rekomendasi investasi. Angkanya sebaik sumbernya — periksa ulang pos "
      "yang menentukan keputusan Anda langsung ke laporan keuangan emiten.*")
    return "\n".join(b)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Laporan fundamental lengkap satu emiten IDX.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("ticker", help="kode saham, dengan atau tanpa .JK (mis. BBCA)")
    p.add_argument("--dari-csv", default="hasil/semua.csv", metavar="FILE",
                   help="CSV hasil screening; dipakai untuk median sektor")
    p.add_argument("--cache-fundamental", default=CACHE_FUNDAMENTAL, metavar="FILE",
                   help="cache lapkeu, dipakai bila CSV hasil belum ada")
    p.add_argument("--output", metavar="FILE",
                   help="simpan ke file Markdown (default: tampilkan di layar)")
    args = p.parse_args()

    kode = args.ticker.upper().removesuffix(".JK")

    sumber = Path(args.dari_csv)
    if not sumber.exists():
        print(f"{sumber} tidak ada — jalankan screener.py dulu supaya median "
              f"sektor bisa dihitung dari harga terkini.", file=sys.stderr)
        return 1
    df = pd.read_csv(sumber)

    if "Sektor" not in df.columns:
        print(f"{sumber} tidak punya kolom Sektor — kemungkinan CSV versi lama. "
              "Jalankan ulang screener.py.", file=sys.stderr)
        return 1

    cocok = df[df["Ticker"].astype(str).str.upper() == kode]
    if cocok.empty:
        print(f"{kode} tidak ada di {sumber}.", file=sys.stderr)
        return 1

    laporan = susun_laporan(cocok.iloc[0], df)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(laporan, encoding="utf-8")
        print(f"Disimpan ke {args.output}", file=sys.stderr)
    else:
        # Terminal Windows sering ber-codepage bukan UTF-8; tulis sebagai byte
        # supaya emoji dan tanda pisah panjang tidak menggagalkan seluruh
        # keluaran hanya karena satu karakter.
        sys.stdout.buffer.write(laporan.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
