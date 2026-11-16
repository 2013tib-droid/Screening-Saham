#!/usr/bin/env python3
"""Screener saham Indonesia (IDX) berbasis data gratis Yahoo Finance.

Data diambil lewat library `yfinance` — gratis, tanpa API key. Ticker Bursa
Efek Indonesia memakai suffix `.JK` (contoh: BBCA.JK, TLKM.JK).

Contoh pemakaian:
    python screener.py                              # screening semua daftar, tanpa filter
    python screener.py --max-per 15 --max-pbv 2 --min-roe 15
    python screener.py --tickers tickers/lq45.txt --min-dividen 3 --di-atas-ma200
    python screener.py --tickers tickers/bakrie.txt tickers/salim.txt
    python screener.py --min-skor 70 --urut Skor        # fundamental terkuat saja
    python screener.py --dari-csv hasil/semua.csv --grup Prajogo
    python screener.py --demo --max-per 15          # mode offline dengan data contoh

Hasil ditampilkan sebagai tabel dan disimpan ke hasil_screening.csv.
"""

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

from arjum import KOLOM_ASING, ambil_net_asing

KOLOM = [
    "Ticker", "Nama", "Grup", "Sektor", "Syariah", "Status", "Skor", "Flag", "Harga",
    "PER", "PBV", "PERvsSektor", "PBVvsSektor", "ROE%",
    "LabaYoY%", "OmzetYoY%", "Dividen%", "DER",
    "MarketCap(T)", "Vol20(jt)", "Nilai(M)", "VolSpike",
    "RSI14", "MA50", "MA200", "RS", "TT",
]

# Kolom fundamental yang ikut dibawa dari cache ke CSV hasil tapi tidak
# ditampilkan di tabel terminal — tabelnya sudah selebar layar. Semuanya tetap
# tersimpan supaya hasil/semua.csv bisa dipakai sebagai sumber analisa lanjutan
# tanpa menarik ulang laporan keuangan.
KOLOM_EKSTRA = [
    # Net beli asing dari stock.arjum.com (lihat arjum.py), miliar rupiah.
    # Kosong bila ARJUM_API_KEY tidak diset — sumber utamanya tetap Yahoo.
    "NetAsing1H(M)", "NetAsing5H(M)", "NetAsing20H(M)", "TglAsing",
    # Bahan Trend Template dan RS (lihat metrik_tren). Disimpan supaya TT bisa
    # dihitung ulang dari CSV lewat --dari-csv, sama seperti Status.
    "MA150", "MA200Lalu", "Tinggi52", "Rendah52",
    "Naik3B%", "Naik6B%", "Naik12B%", "RSMentah",
    "MarginKotor%", "MarginOperasi%", "MarginBersih%", "ROA%",
    "UtangBersih/EBITDA", "CurrentRatio", "QuickRatio", "InterestCoverage",
    "EV/EBITDA", "OCF/Laba", "FCFYield%", "Payout%", "Capex/OCF",
    "SkorValuasi", "SkorProfitabilitas", "SkorKesehatan",
    "SkorPertumbuhan", "SkorArusKas",
    "OmzetCAGR3%", "LabaCAGR3%", "TahunLabaNaik", "SahamYoY%",
    # Angka absolut ikut disimpan supaya CSV hasil berdiri sendiri: red flag
    # dan analisa lanjutan bisa dihitung ulang dari file ini lewat --dari-csv
    # tanpa perlu membaca cache fundamental atau menarik ulang dari Yahoo.
    "EPS", "BVPS", "DPS", "Saham",
    "Omzet", "LabaBersih", "EBITDA", "EBIT",
    "TotalUtang", "Kas", "UtangBersih", "TotalAset", "Ekuitas",
    "OCF", "Capex", "FCF",
    "Periode", "Basis", "MataUang",
]

# Cache fundamental: hasil scripts/perbarui_fundamental.py. Isinya hanya
# berubah tiap emiten merilis laporan kuartalan, jadi run malam membacanya
# dari disk alih-alih menarik ulang dari Yahoo.
CACHE_FUNDAMENTAL = "data/fundamental.csv"

# Daftar Efek Syariah (DES) yang ditetapkan OJK. Statusnya bukan angka pasar
# melainkan keputusan regulator, jadi tidak bisa dihitung sendiri dari laporan
# keuangan — satu-satunya sumber yang sah adalah daftar resminya. Berkasnya
# statis dan di-commit ke repo: DES cuma diperbarui dua kali setahun (berlaku
# 1 Juni dan 1 Desember), jadi menariknya tiap malam tidak ada gunanya dan
# hanya menambah satu sumber kegagalan pada run yang sudah bergantung Yahoo.
DAFTAR_SYARIAH = "data/syariah.txt"

# DES berikutnya selalu terbit dalam 6 bulan. Lewat 8 bulan berarti setidaknya
# satu penetapan terlewat, dan daftar yang basi lebih berbahaya daripada
# kolom kosong — emiten bisa sudah dikeluarkan dari DES tanpa kita tahu.
UMUR_SYARIAH_WAJAR = 240

# Status = ringkasan mekanis posisi harga terhadap trennya. Murni aturan
# teknikal dari kolom yang sudah ada (harga, MA50, MA200, RSI, volume,
# likuiditas) — bukan rekomendasi, dan tidak tahu apa pun soal berita,
# laporan keuangan, atau aliran dana bandar.
STATUS = {
    "BUY": "uptrend, momentum sehat, volume masuk",
    "BOW": "uptrend jangka panjang tapi sedang koreksi — buy on weakness",
    "HOLD": "sudah naik tinggi/overbought — tahan, jangan kejar",
    "WSE": "sinyal campur — wait & see",
    "JUAL": "downtrend, harga di bawah MA50 dan MA200",
    "TIPIS": "likuiditas terlalu tipis untuk ditransaksikan",
    "-": "data tidak lengkap",
}

# Nilai transaksi harian minimal (miliar Rp) agar sebuah saham dianggap
# layak ditransaksikan. Di bawah ini, sinyal teknikal apa pun tidak berguna
# karena order sendiri sudah cukup untuk menggerakkan harga.
AMBANG_LIKUID = 1.0

# WIB tidak pernah memakai DST, jadi offset tetap +7 lebih aman daripada
# zoneinfo("Asia/Jakarta") — di Windows zoneinfo butuh paket tzdata yang tidak
# ada di requirements.
WIB = timezone(timedelta(hours=7))

# IDX tutup 15:50 WIB. Jam ini diberi jeda sampai 16:15 karena Yahoo perlu
# beberapa menit memperbarui bar terakhirnya setelah penutupan; sebelum itu
# angka hari ini masih bisa berubah.
JAM_DATA_FINAL = time(16, 15)


def bar_terakhir_belum_final(hist: pd.DataFrame) -> bool:
    """True bila baris terakhir histori adalah hari ini dan sesi belum tuntas.

    Selama sesi berjalan, Yahoo tetap mengirim bar untuk hari ini — tapi
    isinya baru sebagian hari. Volumenya terutama yang menyesatkan: volume
    satu jam pertama dibagi rata-rata 20 hari *penuh* membuat VolSpike
    seluruh pasar anjlok ke sekitar seperlima nilai wajarnya, sehingga filter
    berbasis volume tidak meloloskan apa pun. Perbandingan nyata pada 10 Agu
    2026: run 18:57 WIB memberi median VolSpike 0,73 (88 saham di atas 1,2),
    run 10:01 WIB memberi 0,21 (16 saham).

    Tanggal diambil dari bar-nya sendiri, bukan dari kalender, supaya hari
    libur bursa tidak perlu didaftar: kalau hari ini bursa tutup, bar terakhir
    bertanggal kemarin dan fungsi ini langsung False.
    """
    if hist.empty:
        return False
    sekarang = datetime.now(WIB)
    return (hist.index[-1].date() == sekarang.date()
            and sekarang.time() < JAM_DATA_FINAL)


def hitung_status(r) -> str:
    """Terjemahkan kondisi teknikal satu saham jadi satu label status.

    Aturan diurut dari yang paling menentukan; label pertama yang cocok
    dipakai. Sengaja konservatif: kalau sinyalnya tidak jelas, jawabannya
    WSE, bukan BUY.
    """
    def ada(*nama):
        return all(r.get(n) is not None and pd.notna(r.get(n)) for n in nama)

    if not ada("Harga", "MA50", "MA200", "RSI14"):
        return "-"

    harga, ma50, ma200, rsi = r["Harga"], r["MA50"], r["MA200"], r["RSI14"]
    nilai = r.get("Nilai(M)")
    spike = r.get("VolSpike")

    # Likuiditas didahulukan: sinyal bagus di saham yang tidak bisa dijual
    # bukan sinyal bagus.
    if ada("Nilai(M)") and nilai < AMBANG_LIKUID:
        return "TIPIS"

    di_atas_ma200 = harga > ma200
    di_atas_ma50 = harga > ma50

    if not di_atas_ma200 and not di_atas_ma50:
        # Downtrend penuh. RSI rendah di sini bukan diskon, tapi pisau jatuh —
        # tunggu harga balik ke atas MA50 dulu.
        return "WSE" if rsi <= 30 else "JUAL"

    if di_atas_ma200:
        if rsi >= 70:
            return "HOLD"
        if not di_atas_ma50 or rsi <= 50:
            return "BOW"
        if ada("VolSpike") and spike >= 1.2:
            return "BUY"
        return "HOLD"

    # Di atas MA50 tapi masih di bawah MA200: awal pemulihan, belum konfirmasi.
    return "WSE"


# Skor = kesimpulan fundamental satu saham dalam satu angka 1-100, disusun
# dari lima kategori dengan bobot tetap. Perusahaan sehat (untung besar,
# tumbuh, tidak kelebihan utang, kasnya nyata, valuasi wajar) dapat angka
# tinggi.
#
# Bobot kategori mengikuti kerangka penilaian fundamental yang umum dipakai:
# valuasi dan profitabilitas paling menentukan, kesehatan neraca dan
# pertumbuhan menyusul, arus kas jadi pelengkap karena sebagian datanya
# paling sering tidak lengkap.
BOBOT_KATEGORI = {
    "Valuasi": 25,
    "Profitabilitas": 25,
    "Kesehatan": 20,
    "Pertumbuhan": 20,
    "ArusKas": 10,
}

# Isi tiap kategori: kolom -> (bobot relatif di dalam kategorinya, titik acuan).
#
# Titik acuan memetakan nilai mentah ke skor 0-100 lewat interpolasi linier;
# di luar rentang dipakai nilai ujungnya. Angkanya dipilih dari kebiasaan
# pasar Indonesia (ROE 15% layak, PER 10 murah, DER di atas 2 berat), bukan
# hasil optimasi statistik — jangan dibaca lebih presisi dari sebenarnya.
#
# Bobot ditulis relatif, bukan absolut, supaya komponen yang tidak berlaku
# untuk sebuah sektor bisa dibuang dan sisanya otomatis menutup porsinya.
KOMPONEN_SKOR = {
    "Valuasi": {
        # Perbandingan terhadap median sektor diberi porsi terbesar: PBV 2,5
        # di bank dan PBV 2,5 di emiten batubara bukan hal yang sama, dan
        # angka absolut tidak bisa membedakannya.
        "PERvsSektor": (30, [(0.4, 100), (0.6, 90), (0.8, 75), (1.0, 60),
                             (1.3, 40), (1.8, 20), (2.5, 5)]),
        "PBVvsSektor": (25, [(0.4, 100), (0.6, 90), (0.8, 75), (1.0, 60),
                             (1.3, 40), (1.8, 20), (2.5, 5)]),
        "PER":         (15, [(5, 100), (10, 85), (15, 70), (20, 55),
                             (25, 40), (35, 20), (50, 5)]),
        "EV/EBITDA":   (15, [(3, 100), (5, 90), (7, 78), (10, 60),
                             (14, 38), (20, 15), (30, 5)]),
        # Yield 0 tidak dihukum berat — perusahaan tumbuh wajar menahan labanya.
        "Dividen%":    (15, [(0, 30), (2, 55), (4, 75), (6, 90), (8, 100)]),
    },
    "Profitabilitas": {
        "ROE%":           (28, [(0, 0), (5, 25), (10, 45), (15, 65),
                                (20, 80), (30, 95), (40, 100)]),
        "ROA%":           (14, [(0, 0), (2, 25), (5, 50), (8, 70),
                                (12, 88), (18, 100)]),
        "MarginBersih%":  (16, [(0, 10), (3, 30), (6, 50), (10, 70),
                                (15, 85), (25, 100)]),
        "MarginOperasi%": (14, [(0, 10), (5, 35), (10, 55), (15, 72),
                                (22, 88), (30, 100)]),
        # Kualitas laba: laba akuntansi yang tidak diikuti kas masuk adalah
        # laba di atas kertas. Rasio di bawah 1 berarti sebagian labanya masih
        # berupa piutang atau persediaan, bukan uang.
        "OCF/Laba":       (28, [(-0.5, 0), (0, 10), (0.5, 40), (0.8, 65),
                                (1.0, 82), (1.5, 95), (2.5, 100)]),
    },
    "Kesehatan": {
        "DER":                (28, [(0, 100), (0.3, 90), (0.6, 78), (1.0, 62),
                                    (1.5, 45), (2.5, 22), (4.0, 5)]),
        # Negatif berarti net cash, jadi ujung kiri diberi nilai penuh.
        "UtangBersih/EBITDA": (24, [(-1, 100), (0, 95), (1, 82), (2, 65),
                                    (3, 45), (4.5, 22), (6, 5)]),
        "InterestCoverage":   (24, [(0, 0), (1.5, 20), (3, 45), (5, 65),
                                    (10, 85), (20, 100)]),
        "CurrentRatio":       (14, [(0.5, 5), (1.0, 40), (1.3, 62), (1.8, 82),
                                    (2.5, 95), (4, 100)]),
        "QuickRatio":         (10, [(0.3, 5), (0.8, 40), (1.0, 60), (1.5, 82),
                                    (2.5, 100)]),
    },
    "Pertumbuhan": {
        "LabaYoY%":     (25, [(-50, 0), (-20, 15), (0, 40), (20, 65),
                              (50, 85), (100, 100)]),
        "OmzetYoY%":    (20, [(-30, 0), (-10, 20), (0, 40), (10, 60),
                              (25, 80), (50, 100)]),
        # CAGR tiga tahun menyaring lonjakan sesaat: laba yang naik 200%
        # sekali lalu anjlok dua kali tidak akan terlihat bagus di sini.
        "LabaCAGR3%":   (25, [(-20, 0), (-5, 25), (5, 50), (15, 72),
                              (25, 88), (40, 100)]),
        "OmzetCAGR3%":  (15, [(-15, 0), (-5, 25), (3, 50), (10, 72),
                              (18, 88), (30, 100)]),
        # Berapa dari 3 tahun terakhir labanya naik — ukuran konsistensi,
        # bukan besaran.
        "TahunLabaNaik": (15, [(0, 10), (1, 40), (2, 72), (3, 100)]),
    },
    "ArusKas": {
        "FCFYield%": (30, [(-10, 0), (-2, 20), (0, 35), (3, 60),
                           (6, 80), (10, 95), (15, 100)]),
        # Payout dinilai berpuncak di tengah: nol berarti tidak berbagi hasil,
        # di atas 100% berarti dividennya melebihi laba dan tidak lestari.
        "Payout%":   (25, [(0, 40), (15, 65), (30, 85), (50, 95), (70, 85),
                           (100, 55), (130, 20), (200, 5)]),
        # Positif = jumlah saham bertambah = pemegang saham lama terdilusi.
        # Negatif = buyback, dan itu dihargai.
        "SahamYoY%": (25, [(-5, 100), (-1, 90), (0, 78), (2, 60),
                           (5, 35), (10, 12), (20, 0)]),
        # Berpuncak di tengah: capex sangat rendah bisa berarti bisnis ringan
        # modal, tapi bisa juga berarti perusahaannya berhenti berinvestasi.
        "Capex/OCF": (20, [(0, 55), (0.15, 85), (0.35, 90), (0.6, 72),
                           (0.9, 45), (1.3, 20), (2.0, 5)]),
    },
}

# Penyesuaian sektoral. Faktor pengali bobot komponen; 0 berarti komponennya
# tidak dipakai sama sekali untuk sektor itu, dan porsinya dibagi ulang ke
# komponen lain dalam kategori yang sama.
#
# Ini bukan penghalusan opsional. Tanpa penyesuaian, bank selalu terlihat
# berutang ekstrem (Total Debt bank adalah bisnisnya, bukan bebannya) dan
# emiten teknologi yang belum untung selalu terlihat kemahalan meski memang
# begitu tahap hidupnya.
PENYESUAIAN_SEKTOR = {
    "Financial Services": {
        # Neraca bank tidak mengenal aset lancar, dan utangnya adalah dana
        # pihak ketiga — rasio utang ala perusahaan biasa tidak berlaku.
        # Sebagai gantinya bobot pindah ke ROE dan valuasi berbasis P/B, yang
        # memang metrik utama untuk menilai bank.
        "DER": 0, "UtangBersih/EBITDA": 0, "CurrentRatio": 0, "QuickRatio": 0,
        "InterestCoverage": 0, "EV/EBITDA": 0, "MarginOperasi%": 0,
        # Arus kas bank ikut dimatikan, dengan alasan yang sama seperti
        # flag-nya: penyaluran kredit menyerap kas sehingga OCF bank sering
        # negatif justru ketika sedang tumbuh. Dibiarkan, komponen ini
        # menghukum bank yang ekspansif — BBRI sempat turun ke Profitabilitas
        # 53 melawan BBCA 81 semata karena OCF/Laba-nya minus.
        "OCF/Laba": 0, "Capex/OCF": 0, "FCFYield%": 0,
        # Yang tersisa di kategori arus kas: kelestarian dividen dan dilusi,
        # dua hal yang tetap bermakna untuk bank.
        "PBVvsSektor": 1.6, "ROE%": 1.4,
    },
    "Energy": {
        # Komoditas: yang menentukan bertahan-tidaknya melewati siklus adalah
        # beban utang bersih terhadap kas yang dihasilkan, bukan laba satu
        # tahun yang kebetulan sedang di puncak harga komoditas.
        "UtangBersih/EBITDA": 1.6, "FCFYield%": 1.3,
        "PER": 0.6, "LabaYoY%": 0.7,
    },
    "Basic Materials": {
        "UtangBersih/EBITDA": 1.6, "FCFYield%": 1.3,
        "PER": 0.6, "LabaYoY%": 0.7,
    },
    "Real Estate": {
        # Properti: gearing dan kemampuan mendanai proyek yang menentukan.
        # Laba akuntansinya sering mendahului kasnya, jadi OCF/Laba dinaikkan.
        "DER": 1.5, "CurrentRatio": 1.3, "OCF/Laba": 1.3,
        "PBVvsSektor": 1.3,
    },
    "Consumer Defensive": {
        # Consumer: yang membedakan pemenang adalah margin yang bertahan dan
        # kas yang benar-benar masuk.
        "MarginBersih%": 1.4, "MarginOperasi%": 1.3, "OCF/Laba": 1.3,
    },
    "Consumer Cyclical": {
        "MarginBersih%": 1.4, "MarginOperasi%": 1.3, "OCF/Laba": 1.3,
    },
    "Technology": {
        # Teknologi diberi toleransi valuasi lebih tinggi, tapi ditagih lebih
        # keras soal kualitas pertumbuhan, kas yang terbakar, dan dilusi —
        # tiga hal yang menentukan apakah ia sampai ke profitabilitas.
        "PER": 0.4, "EV/EBITDA": 0.5, "Dividen%": 0.3,
        "OmzetYoY%": 1.5, "OmzetCAGR3%": 1.4,
        "FCFYield%": 1.4, "SahamYoY%": 1.5,
    },
}

# Kategori dinilai hanya bila komponen yang datanya ada mencakup minimal porsi
# ini dari bobot kategorinya. Di bawah itu kategorinya dibuang seluruhnya dan
# bobotnya dibagi ulang ke kategori lain.
MIN_CAKUPAN_KATEGORI = 0.4

# Skor akhir hanya dikeluarkan bila kategori yang berhasil dinilai mencakup
# minimal porsi ini dari total 100. Di bawah itu angkanya lebih menyesatkan
# daripada berguna — lebih baik kosong.
MIN_CAKUPAN_SKOR = 0.5


def _interpolasi(nilai: float, titik: list[tuple[float, float]]) -> float:
    """Petakan nilai ke skor lewat interpolasi linier antar titik acuan."""
    if nilai <= titik[0][0]:
        return titik[0][1]
    if nilai >= titik[-1][0]:
        return titik[-1][1]
    for (x1, y1), (x2, y2) in zip(titik, titik[1:]):
        if nilai <= x2:
            return y1 + (y2 - y1) * (nilai - x1) / (x2 - x1)
    return titik[-1][1]


def _angka(r, kolom: str) -> float | None:
    nilai = r.get(kolom)
    if nilai is None or pd.isna(nilai):
        return None
    try:
        return float(nilai)
    except (TypeError, ValueError):
        return None


def skor_kategori(r, kategori: str, sektor: str) -> tuple[float | None, float]:
    """Nilai satu kategori untuk satu emiten.

    Mengembalikan (skor 0-100, porsi bobot yang datanya tersedia). Porsi itu
    dipakai pemanggil untuk memutuskan apakah kategorinya layak dihitung.

    PER, PBV, dan EV/EBITDA yang nol atau negatif bukan data hilang melainkan
    kabar buruk: PER negatif berarti perusahaannya rugi dan PBV negatif berarti
    ekuitasnya minus. Keduanya diberi skor 0, bukan dilewati — kalau dilewati,
    emiten rugi justru diuntungkan karena komponen terburuknya menghilang.
    """
    penyesuaian = PENYESUAIAN_SEKTOR.get(sektor, {})
    total_bobot = 0.0
    bobot_terpakai = 0.0
    total_skor = 0.0

    for kolom, (bobot_dasar, titik) in KOMPONEN_SKOR[kategori].items():
        bobot = bobot_dasar * penyesuaian.get(kolom, 1.0)
        if bobot <= 0:
            continue
        total_bobot += bobot
        nilai = _angka(r, kolom)
        if nilai is None:
            continue
        if kolom in ("PER", "PBV", "PERvsSektor", "PBVvsSektor", "EV/EBITDA") \
                and nilai <= 0:
            skor = 0.0
        else:
            skor = _interpolasi(nilai, titik)
        total_skor += skor * bobot
        bobot_terpakai += bobot

    if not total_bobot or not bobot_terpakai:
        return None, 0.0
    return total_skor / bobot_terpakai, bobot_terpakai / total_bobot


def hitung_skor(r) -> int | None:
    """Ringkas fundamental satu saham jadi skor 1-100 (makin tinggi makin sehat).

    Rata-rata tertimbang lima kategori. Kategori yang datanya terlalu tipis
    dibuang dan bobotnya dibagi ulang ke sisanya, jadi bank tidak dihukum
    karena tidak punya current ratio, dan emiten yang belum bagi dividen tidak
    otomatis kalah dari yang sudah. Kalau yang tersisa kurang dari separuh
    total bobot, hasilnya None — kolom kosong lebih jujur daripada angka yang
    disusun dari dua-tiga komponen.
    """
    sektor = str(r.get("Sektor") or "")
    total_bobot = 0.0
    total_skor = 0.0
    for kategori, bobot in BOBOT_KATEGORI.items():
        skor, cakupan = skor_kategori(r, kategori, sektor)
        if skor is None or cakupan < MIN_CAKUPAN_KATEGORI:
            continue
        total_skor += skor * bobot
        total_bobot += bobot

    if total_bobot < MIN_CAKUPAN_SKOR * sum(BOBOT_KATEGORI.values()):
        return None
    # Dibatasi minimal 1: skor 0 mudah tertukar dengan "tidak ada data".
    return max(1, min(100, round(total_skor / total_bobot)))


# Red flag: kondisi yang harus terbaca terpisah dari skor. Skor adalah
# rata-rata, dan rata-rata bisa menutupi satu cacat berat dengan banyak angka
# bagus — emiten dengan ekuitas negatif tetap bisa mendapat skor menengah
# kalau pertumbuhan dan valuasinya kebetulan tampak murah. Kolom ini menolak
# dirata-ratakan.
#
# Tiap entri: (kode singkat, fungsi penguji, penjelasan).
RED_FLAG = [
    ("ekuitas-",  lambda r: (_angka(r, "Ekuitas") or 1) < 0,
     "ekuitas negatif — kewajiban melebihi seluruh asetnya"),
    ("rugi",      lambda r: (_angka(r, "LabaBersih") or 0) < 0,
     "masih merugi pada periode terakhir"),
    ("OCF-",      lambda r: (_angka(r, "OCF") or 0) < 0,
     "arus kas operasi negatif — operasinya menyedot kas, bukan menghasilkan"),
    ("FCF-",      lambda r: (_angka(r, "FCF") or 0) < 0,
     "arus kas bebas negatif"),
    ("kas<laba",  lambda r: (v := _angka(r, "OCF/Laba")) is not None
     and 0 <= v < 0.5 and (_angka(r, "LabaBersih") or 0) > 0,
     "kas operasi kurang dari separuh laba — kualitas laba dipertanyakan"),
    ("DER>3",     lambda r: (v := _angka(r, "DER")) is not None and v > 3,
     "utang lebih dari tiga kali ekuitas"),
    ("bunga<1.5", lambda r: (v := _angka(r, "InterestCoverage")) is not None
     and v < 1.5,
     "laba operasi nyaris tidak menutup beban bunga"),
    ("laba-30%",  lambda r: (v := _angka(r, "LabaYoY%")) is not None and v < -30,
     "laba turun lebih dari 30% YoY"),
    ("dilusi",    lambda r: (v := _angka(r, "SahamYoY%")) is not None and v > 10,
     "jumlah saham bertambah lebih dari 10% setahun"),
    ("payout>100", lambda r: (v := _angka(r, "Payout%")) is not None and v > 100,
     "dividen melebihi laba — belum tentu bisa dipertahankan"),
]


# Flag yang tidak berlaku untuk sektor tertentu, dengan alasan yang sama
# seperti penyesuaian bobotnya: arus kas operasi bank memang sering negatif
# karena penyaluran kredit menyerap kas, dan itu tanda bank sedang tumbuh —
# bukan tanda bahaya. Dibiarkan menyala, flag ini akan menandai hampir seluruh
# sektor perbankan dan justru membuat kolomnya berhenti berarti.
FLAG_TIDAK_BERLAKU = {
    "Financial Services": {"OCF-", "FCF-", "kas<laba", "DER>3"},
}


def hitung_flag(r) -> str:
    """Daftar red flag satu emiten, dipisah koma; kosong bila tidak ada.

    Sengaja kode singkat tanpa emoji: keluaran ini ikut masuk CSV dan terminal
    Windows yang codepage-nya bukan UTF-8, tempat karakter di luar ASCII
    berubah jadi tanda tanya.
    """
    kecuali = FLAG_TIDAK_BERLAKU.get(str(r.get("Sektor") or ""), set())
    return ",".join(kode for kode, uji, _ in RED_FLAG
                    if kode not in kecuali and uji(r))


# Daftar default. Daftar kurasi (LQ45, grup konglomerasi, tema) ditaruh lebih
# dulu supaya label Grup-nya yang dipakai; tickers/idx.txt di urutan terakhir
# adalah universe pasar — dihasilkan otomatis oleh
# scripts/perbarui_universe.py dan berisi seluruh emiten IDX di atas ambang
# kapitalisasi, supaya saham berfundamental bagus tetap ikut ter-screening
# walau tidak pernah dimasukkan ke daftar mana pun secara manual.
DAFTAR_DEFAULT = [
    "tickers/lq45.txt",
    "tickers/prajogo.txt",
    "tickers/bakrie.txt",
    "tickers/salim.txt",
    "tickers/hapsoro.txt",
    "tickers/logam.txt",
    "tickers/idx.txt",
]


def baca_daftar_ticker(paths: list[str]) -> tuple[list[str], dict[str, str]]:
    """Baca satu atau lebih file daftar ticker.

    Mengembalikan daftar ticker unik (urutan file dipertahankan) dan peta
    ticker -> label grup. Satu saham bisa masuk beberapa daftar (mis. INDF ada
    di LQ45 dan di grup Salim); labelnya digabung jadi "LQ45/Salim".

    Format file: satu ticker per baris, komentar diawali '#'. Komentar boleh
    ditulis di belakang ticker. Baris '# grup: Nama' di mana pun dalam file
    menentukan label grup; bila tidak ada, dipakai nama file tanpa ekstensi.
    Baris '# grup:' tanpa nama berarti file itu sengaja tidak berlabel (dipakai
    oleh daftar universe pasar) — sahamnya hanya berlabel bila muncul juga di
    daftar kurasi.

    File yang tidak ada dilewati dengan peringatan, bukan error: universe
    otomatis (tickers/idx.txt) belum tentu sudah pernah dibuat.
    """
    tickers: list[str] = []
    grup: dict[str, str] = {}
    for path in paths:
        if not Path(path).exists():
            print(f"Daftar {path} tidak ditemukan, dilewati.", file=sys.stderr)
            continue
        isi = Path(path).read_text().splitlines()
        label = Path(path).stem.upper()
        for baris in isi:
            if baris.strip().lower().startswith("# grup:"):
                label = baris.split(":", 1)[1].strip()
                break
        for baris in isi:
            baris = baris.split("#", 1)[0].strip().upper()
            if not baris:
                continue
            if not baris.endswith(".JK"):
                baris += ".JK"
            polos = baris.removesuffix(".JK")
            if baris not in tickers:
                tickers.append(baris)
                grup[polos] = label
            elif label and label not in grup[polos].split("/"):
                grup[polos] = f"{grup[polos]}/{label}" if grup[polos] else label
    return tickers, grup


def hitung_rsi(close: pd.Series, periode: int = 14) -> float | None:
    if len(close) < periode + 1:
        return None
    delta = close.diff()
    naik = delta.clip(lower=0).ewm(alpha=1 / periode, adjust=False).mean()
    turun = (-delta.clip(upper=0)).ewm(alpha=1 / periode, adjust=False).mean()
    rs = naik.iloc[-1] / turun.iloc[-1] if turun.iloc[-1] != 0 else float("inf")
    return round(100 - 100 / (1 + rs), 1)


def ambil_histori(tickers: list[str], grup: dict[str, str] | None = None,
                  seri: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Ambil kolom yang memang berubah tiap hari: harga, volume, MA, RSI.

    Sengaja tidak menyentuh `.info` lagi. Dulu fungsi ini menariknya untuk
    mendapat ROE, PER, PBV, dan pertumbuhan — padahal semua itu berasal dari
    laporan keuangan yang cuma berubah empat kali setahun, jadi 400-an request
    tiap malam dipakai mengambil angka yang sama persis seperti kemarin.
    Sekarang angka-angka itu datang dari cache fundamental.

    Bila `seri` diberikan, deret Close/Volume tiap emiten (sesudah bar yang
    belum final dan bar tanpa harga dibuang) ikut disimpan ke situ dengan
    kunci kode tanpa .JK — bahan hitung_breadth, supaya breadth tidak perlu
    menarik ulang histori yang sama.
    """
    import yfinance as yf

    baris_data = []
    sudah_diberitahu = False
    for i, tkr in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {tkr} ...", file=sys.stderr)
        try:
            saham = yf.Ticker(tkr)
            # Dua tahun, bukan satu: RS butuh kenaikan 12 bulan penuh, dan
            # "MA200 naik" butuh MA200 sebulan lalu — 222 bar, sementara
            # setahun IDX cuma ±240 hari bursa. Jumlah request-nya sama.
            hist = saham.history(period="2y")

            # Bar hari ini dibuang selama sesi masih berjalan, supaya seluruh
            # tabel konsisten berisi angka penutupan terakhir — sesuai yang
            # dijanjikan header dashboard. Tanpa ini, run yang kebetulan jalan
            # di jam bursa menghasilkan tabel yang tampak wajar tapi kolom
            # volumenya salah total.
            #
            # Sejak PER/PBV dihitung sendiri dari harga penutupan (lihat
            # gabung_fundamental), pemotongan ini berlaku untuk seluruh tabel
            # tanpa kecuali. Sebelumnya PER dan PBV datang jadi dari Yahoo yang
            # memakai harga berjalan, jadi saat sesi hidup dua kolom itu
            # mengacu ke titik waktu yang berbeda dari kolom lainnya.
            belum_final = bar_terakhir_belum_final(hist)
            if belum_final:
                if not sudah_diberitahu:
                    print("  Sesi bursa masih berjalan — bar hari ini dibuang, "
                          "dipakai data penutupan terakhir.", file=sys.stderr)
                    sudah_diberitahu = True
                hist = hist.iloc[:-1]

            close = hist["Close"] if not hist.empty else pd.Series(dtype=float)
            vol = hist["Volume"] if not hist.empty else pd.Series(dtype=float)

            # Baris ber-Close NaN dibuang sebelum apa pun dihitung. Yahoo
            # sesekali mengirim bar tanpa harga — bar hari ini yang belum
            # terisi, atau (seperti 27-31 Agu 2026, dari runner GitHub) seluruh
            # kolom Close NaN sekaligus. Tanpa pembuangan ini `round(NaN)`
            # melempar "cannot convert float NaN to integer", dan `except` di
            # bawah membuang SELURUH sahamnya, bukan cuma bar yang cacat.
            # Run 31 Agu 2026 kehilangan 398 dari 402 emiten karena itu.
            #
            # Volume ikut disaring dengan indeks yang sama supaya `close * vol`
            # dan `vol.iloc[-1]` tetap menunjuk hari yang sama dengan harganya.
            layak = close.notna()
            close = close[layak]
            vol = vol[layak]
            if seri is not None and len(close):
                seri[tkr.removesuffix(".JK")] = pd.DataFrame({"Close": close, "Volume": vol})

            harga = round(close.iloc[-1]) if len(close) else None
            vol20 = vol.tail(20).mean() if len(vol) >= 20 else None
            if vol20 is None or pd.isna(vol20) or vol20 <= 0:
                vol20 = None
            nilai20 = (close * vol).tail(20).mean() if vol20 else None
            if nilai20 is not None and pd.isna(nilai20):
                nilai20 = None
            baris_data.append({
                "Ticker": tkr.removesuffix(".JK"),
                "Grup": (grup or {}).get(tkr.removesuffix(".JK"), ""),
                "Harga": harga,
                "Vol20(jt)": round(vol20 / 1e6, 2) if vol20 else None,
                "Nilai(M)": round(nilai20 / 1e9, 1) if nilai20 else None,
                "VolSpike": round(vol.iloc[-1] / vol20, 2) if vol20 and len(vol) else None,
                "RSI14": hitung_rsi(close),
                "MA50": round(close.tail(50).mean()) if len(close) >= 50 else None,
                "MA200": round(close.tail(200).mean()) if len(close) >= 200 else None,
                **metrik_tren(close),
            })
        except Exception as e:
            print(f"      gagal: {e}", file=sys.stderr)
    gagal = len(tickers) - len(baris_data)
    if gagal:
        print(f"{gagal} dari {len(tickers)} emiten gagal diambil.", file=sys.stderr)
    return pd.DataFrame(baris_data)


# Trend Template ala Mark Minervini + Relative Strength ala IBD.
#
# Daftar swing di atas terbukti tidak lebih pintar dari saham likuid acak
# (README, "Uji Winrate"): syaratnya cuma "di atas MA200, RSI belum tinggi,
# volume masuk" — itu menjaring separuh pasar saat pasar naik. Trend Template
# bertanya hal yang lain: apakah sahamnya sedang dalam tren naik yang tertata
# (MA50 > MA150 > MA200, MA200 ikut naik, dekat puncak setahunnya) DAN termasuk
# yang paling kuat dibanding seluruh universe (RS). Ini hipotesis, bukan bukti:
# kolomnya dipasang supaya bisa diuji lewat uji_winrate.py dengan pick nyata.
#
# Jendela waktu memakai hari KALENDER (3/6/9/12 bulan, 52 minggu), bukan
# jumlah bar: Yahoo sesekali menyelipkan bar libur, dan setahun IDX bukan
# persis 252 hari bursa seperti bursa AS.
HARI_MA200_NAIK = 22      # "MA200 naik setidaknya sebulan": dibanding MA200 22 bar lalu
MIN_RS_TT = 70            # syarat RS Minervini
# RS mentah = kenaikan tertimbang, kuartal terakhir dihitung dobel. Ini
# pendekatan publik yang lazim untuk RS Rating IBD (rumus aslinya tertutup).
BOBOT_RS = ((91, 0.4), (182, 0.2), (273, 0.2), (365, 0.2))
# Peringkat persentil RS tidak berarti di universe yang terlalu kecil
# (mis. --tickers satu daftar grup berisi 8 emiten).
MIN_EMITEN_RS = 30


def _naik_sejak(close: pd.Series, hari: int) -> float | None:
    """Kenaikan (%) dari penutupan terakhir pada/sebelum `hari` kalender lalu.

    None bila histori belum menjangkau tanggal itu (emiten baru IPO): lebih
    jujur kosong daripada mengukur dari bar pertama yang kebetulan ada.
    """
    if close.empty:
        return None
    batas = close.index[-1] - pd.Timedelta(days=hari)
    lalu = close[close.index <= batas]
    if lalu.empty or lalu.iloc[-1] <= 0:
        return None
    return (close.iloc[-1] / lalu.iloc[-1] - 1) * 100


def metrik_tren(close: pd.Series) -> dict:
    """Bahan Trend Template & RS dari deret penutupan ber-indeks tanggal."""
    kosong = {k: None for k in ("MA150", "MA200Lalu", "Tinggi52", "Rendah52",
                                "Naik3B%", "Naik6B%", "Naik12B%", "RSMentah")}
    close = close.dropna()
    if close.empty:
        return kosong
    hasil = dict(kosong)
    if len(close) >= 150:
        hasil["MA150"] = round(close.tail(150).mean())
    if len(close) >= 200 + HARI_MA200_NAIK:
        hasil["MA200Lalu"] = round(close.iloc[:-HARI_MA200_NAIK].tail(200).mean())
    # 52 minggu hanya dihitung bila historinya memang setahun penuh; untuk
    # emiten yang baru IPO, "tertinggi 52 minggu" cuma tertinggi sejak IPO.
    akhir = close.index[-1]
    if close.index[0] <= akhir - pd.Timedelta(days=358):
        setahun = close[close.index > akhir - pd.Timedelta(days=365)]
        hasil["Tinggi52"] = round(setahun.max())
        hasil["Rendah52"] = round(setahun.min())
    naik = {hari: _naik_sejak(close, hari) for hari, _ in BOBOT_RS}
    for hari, kolom in ((91, "Naik3B%"), (182, "Naik6B%"), (365, "Naik12B%")):
        hasil[kolom] = round(naik[hari], 1) if naik[hari] is not None else None
    if all(v is not None for v in naik.values()):
        hasil["RSMentah"] = round(sum(b * naik[h] for h, b in BOBOT_RS), 2)
    return hasil


def hitung_rs(df: pd.DataFrame) -> pd.Series:
    """RS 1-99: persentil RSMentah terhadap seluruh emiten yang punya nilainya.

    99 = lebih kuat dari 99% universe. Dihitung sekali saat menarik data,
    terhadap universe penuh — BUKAN ulang di --dari-csv, karena di sana
    tabelnya bisa saja sudah tersaring dan persentilnya jadi relatif terhadap
    segelintir saham.
    """
    mentah = pd.to_numeric(df.get("RSMentah"), errors="coerce") \
        if "RSMentah" in df.columns else pd.Series([None] * len(df), dtype=float)
    if mentah.notna().sum() < MIN_EMITEN_RS:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="Int64")
    return (mentah.rank(pct=True) * 99).round().clip(1, 99).astype("Int64")


# Delapan syarat Trend Template, diurut seperti aslinya. Kode pendeknya
# dipakai di README dan dashboard.
KRITERIA_TT = [
    ("H>MA150&MA200", "harga di atas MA150 dan MA200",
     lambda r: r["Harga"] > r["MA150"] and r["Harga"] > r["MA200"]),
    ("MA150>MA200", "MA150 di atas MA200",
     lambda r: r["MA150"] > r["MA200"]),
    ("MA200 naik", f"MA200 lebih tinggi dari {HARI_MA200_NAIK} hari bursa lalu",
     lambda r: r["MA200"] > r["MA200Lalu"]),
    ("MA50>MA150&MA200", "MA50 di atas MA150 dan MA200",
     lambda r: r["MA50"] > r["MA150"] and r["MA50"] > r["MA200"]),
    ("H>MA50", "harga di atas MA50",
     lambda r: r["Harga"] > r["MA50"]),
    ("≥30% dari bawah", "harga minimal 30% di atas terendah 52 minggu",
     lambda r: r["Harga"] >= 1.30 * r["Rendah52"]),
    ("≤25% dari puncak", "harga paling jauh 25% di bawah tertinggi 52 minggu",
     lambda r: r["Harga"] >= 0.75 * r["Tinggi52"]),
    (f"RS≥{MIN_RS_TT}", f"RS minimal {MIN_RS_TT}",
     lambda r: r["RS"] >= MIN_RS_TT),
]
_BAHAN_TT = ("Harga", "MA50", "MA150", "MA200", "MA200Lalu", "Tinggi52", "Rendah52", "RS")


def hitung_tt(r) -> int | None:
    """Jumlah syarat Trend Template yang terpenuhi, 0-8; None bila bahan kurang.

    Sengaja hitungan, bukan ya/tidak: 7 dari 8 (biasanya cuma RS yang kurang,
    atau baru saja turun dari puncak) layak masuk daftar pantau, dan tabelnya
    tetap bisa disaring ketat dengan --min-tt 8.
    """
    nilai = {}
    for k in _BAHAN_TT:
        v = pd.to_numeric(r.get(k), errors="coerce")
        if v is None or pd.isna(v):
            return None
        nilai[k] = float(v)
    return sum(bool(uji(nilai)) for _, _, uji in KRITERIA_TT)


# Breadth = seberapa luas partisipasi pasar, dihitung dari universe kita
# sendiri. IHSG tertimbang kapitalisasi dan didominasi segelintir bank dan
# saham raksasa, jadi "IHSG di atas MA50" bisa terjadi sementara mayoritas
# saham masih turun — atau sebaliknya. Breadth menjawab yang tidak dijawab
# IHSG: berapa persen saham likuid yang trennya sedang naik.
#
# Hanya saham likuid yang dihitung (nilai transaksi 20 hari ≥ Rp5 miliar
# PADA TANGGAL ITU, sama dengan syarat daftar swing dan pembanding saham acak
# di uji_winrate.py), supaya ratusan saham tidur tidak menenggelamkan angkanya.
MIN_NILAI_BREADTH = 5.0   # miliar Rp
MIN_EMITEN_BREADTH = 30   # di bawah ini persentasenya terlalu berisik untuk dibaca
KOLOM_BREADTH = ["Tanggal", "Emiten", "DiAtasMA50%", "DiAtasMA200%",
                 "TinggiBaru", "RendahBaru"]


def hitung_breadth(seri: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Deret breadth harian dari histori Close/Volume tiap emiten.

    Bar ber-volume 0 dibuang dulu: itu bar "libur" yang Yahoo selipkan untuk
    sebagian emiten (lihat uji_winrate.py). Tanggal yang emiten likuidnya
    kurang dari MIN_EMITEN_BREADTH — biasanya justru tanggal libur itu —
    tidak ditulis sama sekali.
    """
    potongan = []
    for kode, h in seri.items():
        if h is None or h.empty or "Close" not in h or "Volume" not in h:
            continue
        h = h[h["Close"].notna() & (pd.to_numeric(h["Volume"], errors="coerce") > 0)]
        if len(h) < 20:
            continue
        idx = pd.DatetimeIndex(h.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        idx = idx.normalize()
        c = pd.Series(h["Close"].to_numpy(dtype=float), index=idx)
        v = pd.Series(h["Volume"].to_numpy(dtype=float), index=idx)
        jaga = ~c.index.duplicated(keep="last")
        c, v = c[jaga].sort_index(), v[jaga].sort_index()

        likuid = (c * v).rolling(20).mean() >= MIN_NILAI_BREADTH * 1e9
        ma50, ma200 = c.rolling(50).mean(), c.rolling(200).mean()
        setahun = (c.index - c.index[0]) >= pd.Timedelta(days=358)
        tinggi, rendah = c.rolling("365D").max(), c.rolling("365D").min()
        ada50 = likuid & ma50.notna()
        ada200 = likuid & ma200.notna()
        ada52 = likuid & setahun
        potongan.append(pd.DataFrame({
            "Emiten": likuid,
            "n50": ada50, "atas50": ada50 & (c > ma50),
            "n200": ada200, "atas200": ada200 & (c > ma200),
            "TinggiBaru": ada52 & (c >= tinggi),
            "RendahBaru": ada52 & (c <= rendah),
        }).astype(int))
    if not potongan:
        return pd.DataFrame(columns=KOLOM_BREADTH)
    j = pd.concat(potongan).groupby(level=0).sum().sort_index()
    j = j[j["Emiten"] >= MIN_EMITEN_BREADTH]

    def persen(atas, n):
        return (100 * j[atas] / j[n]).where(j[n] >= MIN_EMITEN_BREADTH).round(1)

    hasil = pd.DataFrame({
        "Tanggal": [t.date().isoformat() for t in j.index],
        "Emiten": j["Emiten"].to_numpy(),
        "DiAtasMA50%": persen("atas50", "n50").to_numpy(),
        "DiAtasMA200%": persen("atas200", "n200").to_numpy(),
        "TinggiBaru": j["TinggiBaru"].to_numpy(),
        "RendahBaru": j["RendahBaru"].to_numpy(),
    })
    return hasil[KOLOM_BREADTH]


def tulis_breadth(path: str, seri: dict[str, pd.DataFrame]) -> None:
    """Hitung breadth lalu gabungkan dengan berkas lama.

    Tanggal yang tercakup histori malam ini ditimpa (universe-nya bisa
    berubah, angka terbaru yang dipakai); tanggal yang lebih tua dari jangkauan
    histori dibiarkan, supaya catatannya terus memanjang melewati dua tahun.
    Kegagalan tidak menggagalkan screening — sama dengan kondisi pasar.
    """
    try:
        baru = hitung_breadth(seri)
    except Exception as e:
        print(f"Breadth gagal dihitung ({e}) — {path} tidak diperbarui.", file=sys.stderr)
        return
    if baru.empty:
        print(f"Breadth kosong (emiten likuid < {MIN_EMITEN_BREADTH}) — "
              f"{path} tidak diperbarui.", file=sys.stderr)
        return
    lama_path = Path(path)
    if lama_path.exists():
        try:
            lama = pd.read_csv(lama_path, dtype={"Tanggal": str})
            lama = lama[lama["Tanggal"] < baru["Tanggal"].iloc[0]]
            baru = pd.concat([lama.reindex(columns=KOLOM_BREADTH), baru], ignore_index=True)
        except Exception as e:
            print(f"Breadth lama ({path}) tidak terbaca ({e}) — ditulis ulang.",
                  file=sys.stderr)
    lama_path.parent.mkdir(parents=True, exist_ok=True)
    baru.to_csv(lama_path, index=False)
    t = baru.iloc[-1]
    print(f"Breadth {t['Tanggal']}: {t['DiAtasMA50%']}% dari {t['Emiten']} saham likuid "
          f"di atas MA50, {t['DiAtasMA200%']}% di atas MA200, "
          f"{t['TinggiBaru']} tertinggi / {t['RendahBaru']} terendah 52 minggu -> {path}",
          file=sys.stderr)


# Kondisi pasar = IHSG di atas atau di bawah MA50-nya. Satu-satunya aturan
# dalam uji ulang Apr 2024-Sep 2026 yang konsisten memperbaiki hasil daftar
# swing: membuka posisi baru hanya saat IHSG di atas MA50 memangkas drawdown
# terburuk simulasi portofolio 10 posisi dari -58% ke -18%, tanpa mengorbankan
# labanya. Pemilihan sahamnya sendiri tidak lebih baik daripada saham acak —
# yang menyelamatkan adalah TIDAK membeli selama Jan-Jun 2026, ketika IHSG
# jatuh dari 9.135 ke 5.342. Lihat README bagian "Kondisi pasar".
KODE_IHSG = "^JKSE"
MA_PASAR = 50


def kondisi_pasar(close: pd.Series) -> dict | None:
    """Ringkas posisi IHSG terhadap MA50 dan MA200 dari deret penutupannya.

    `sejak` adalah bar pertama keadaan sekarang (di atas / di bawah MA50) yang
    tidak terputus sampai hari ini. Kalau keadaannya tidak pernah berganti
    sepanjang histori yang ada, `sejakPasti` False: tanggalnya cuma batas
    datanya, bukan awal keadaannya.
    """
    close = close.dropna()
    if len(close) < MA_PASAR + 1:
        return None
    ma50 = close.rolling(MA_PASAR).mean()
    ma200 = close.rolling(200).mean()
    di_atas = (close > ma50)[ma50.notna()]
    kini = bool(di_atas.iloc[-1])
    lain = di_atas.index[di_atas != kini]
    runtun = di_atas.index[di_atas.index > lain[-1]] if len(lain) else di_atas.index
    tgl = lambda t: pd.Timestamp(t).date().isoformat()  # noqa: E731
    return {
        "tanggal": tgl(close.index[-1]),
        "ihsg": round(float(close.iloc[-1]), 2),
        "ma50": round(float(ma50.iloc[-1]), 2),
        "ma200": round(float(ma200.iloc[-1]), 2) if pd.notna(ma200.iloc[-1]) else None,
        "diAtasMA50": kini,
        "diAtasMA200": bool(close.iloc[-1] > ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else None,
        "sejak": tgl(runtun[0]),
        "sejakPasti": bool(len(lain)),
        "hariBursa": len(runtun),
        "maPasar": MA_PASAR,
    }


def tulis_kondisi_pasar(path: str) -> None:
    """Tarik histori IHSG, lalu tulis kondisi_pasar() sebagai JSON.

    Kegagalan tidak menggagalkan screening: berkas lama dibiarkan, dan
    dashboard membandingkan tanggalnya dengan waktu run untuk menandainya
    basi. Lebih baik tabel screening tetap terbit tanpa penanda pasar
    daripada tidak terbit sama sekali karena satu request IHSG.
    """
    import json
    import yfinance as yf

    try:
        hist = yf.Ticker(KODE_IHSG).history(period="2y")
        # Alasan yang sama dengan ambil_histori: selama sesi berjalan, bar
        # hari ini bukan penutupan.
        if bar_terakhir_belum_final(hist):
            hist = hist.iloc[:-1]
        kondisi = kondisi_pasar(hist["Close"]) if not hist.empty else None
    except Exception as e:
        print(f"Kondisi pasar gagal diambil ({e}) — {path} tidak diperbarui.",
              file=sys.stderr)
        return
    if kondisi is None:
        print(f"Histori IHSG terlalu pendek — {path} tidak diperbarui.", file=sys.stderr)
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(kondisi, indent=2) + "\n")
    print(f"Kondisi pasar: IHSG {kondisi['ihsg']:.0f} "
          f"{'di atas' if kondisi['diAtasMA50'] else 'di bawah'} MA{MA_PASAR} "
          f"({kondisi['ma50']:.0f}) sejak {kondisi['sejak']} -> {path}", file=sys.stderr)


def baca_daftar_syariah(path: str) -> tuple[set[str] | None, str]:
    """Baca daftar saham syariah (DES) beserta keterangan asalnya.

    Mengembalikan (himpunan kode tanpa .JK, keterangan). Himpunannya `None`
    bila berkasnya tidak ada — itu dibedakan dengan sengaja dari himpunan
    kosong: "belum tahu" dan "tidak ada satu pun yang syariah" adalah dua
    jawaban yang sangat berbeda, dan menyamakannya akan membuat seluruh pasar
    tampak non-syariah.

    Format sama seperti berkas tickers/: satu kode per baris, '#' komentar.
    Baris '# berlaku: YYYY-MM-DD' dipakai untuk memperingatkan daftar basi.
    """
    berkas = Path(path)
    if not berkas.exists():
        return None, "berkas tidak ada"

    kode: set[str] = set()
    berlaku = ""
    sumber = ""
    for baris in berkas.read_text(encoding="utf-8").splitlines():
        ketat = baris.strip().lower()
        if ketat.startswith("# berlaku:"):
            berlaku = baris.split(":", 1)[1].strip()
        elif ketat.startswith("# sumber:"):
            sumber = baris.split(":", 1)[1].strip()
        bersih = baris.split("#", 1)[0].strip().upper()
        if bersih:
            kode.add(bersih.removesuffix(".JK"))

    if not kode:
        return None, "berkas ada tapi kosong"

    ket = f"{len(kode)} saham syariah"
    if sumber:
        ket += f", sumber {sumber}"
    if berlaku:
        ket += f", berlaku {berlaku}"
        try:
            umur = (date.today() - date.fromisoformat(berlaku)).days
        except ValueError:
            print(f"Tanggal '# berlaku:' di {path} tidak terbaca: {berlaku!r}. "
                  f"Format yang diharapkan YYYY-MM-DD.", file=sys.stderr)
        else:
            if umur > UMUR_SYARIAH_WAJAR:
                print(f"PERINGATAN: daftar syariah {path} berumur {umur} hari "
                      f"(berlaku {berlaku}). DES diperbarui tiap 6 bulan, jadi "
                      f"setidaknya satu penetapan sudah terlewat — perbarui "
                      f"lewat scripts/perbarui_syariah.py.", file=sys.stderr)
    return kode, ket


def tandai_syariah(df: pd.DataFrame, syariah: set[str] | None) -> pd.DataFrame:
    """Isi kolom Syariah dengan Ya/Tidak, atau kosongkan bila daftarnya tidak ada.

    DES memuat SELURUH efek syariah yang tercatat, jadi begitu daftarnya ada,
    emiten yang tidak tercantum memang non-syariah — "tidak ketemu" di sini
    adalah jawaban, bukan data yang hilang. Sebaliknya bila daftarnya belum
    dimuat, kolomnya dibiarkan kosong: menebak status syariah sebuah emiten
    jauh lebih buruk daripada mengaku tidak tahu.
    """
    if syariah is None:
        df["Syariah"] = pd.NA
        return df
    df["Syariah"] = df["Ticker"].astype(str).str.upper().map(
        lambda k: "Ya" if k.removesuffix(".JK") in syariah else "Tidak")
    return df


def baca_cache_fundamental(path: str) -> pd.DataFrame:
    """Baca cache lapkeu. Kosong (dengan peringatan) bila filenya belum ada.

    Bukan error: repo yang baru di-clone belum punya cache, dan screening
    teknikal tetap berguna tanpa kolom fundamental. Yang hilang hanya Skor —
    dan itu memang jawaban yang benar ketika fundamentalnya tidak diketahui.
    """
    p = Path(path)
    if not p.exists():
        print(f"Cache fundamental {path} tidak ada — kolom fundamental dikosongkan.\n"
              f"  Jalankan: python scripts/perbarui_fundamental.py",
              file=sys.stderr)
        return pd.DataFrame()
    df = pd.read_csv(p)
    umur = df["Periode"].dropna()
    if not umur.empty:
        print(f"Cache fundamental: {len(df)} emiten, periode lapkeu terbaru "
              f"{umur.max()}.", file=sys.stderr)
    return df


def gabung_fundamental(hist: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    """Gabungkan histori harga dengan cache lapkeu, lalu hitung rasio harga.

    PER, PBV, dividend yield, dan market cap sengaja dihitung di sini alih-alih
    diambil jadi dari Yahoo. Alasannya bukan ketelitian desimal melainkan titik
    waktu: rasio Yahoo memakai harga berjalan, sedangkan seluruh kolom lain di
    tabel ini berasal dari penutupan terakhir. Dengan EPS dan nilai buku
    dikunci di cache, satu-satunya variabel harian adalah harga — jadi semua
    kolom akhirnya mengacu ke hari yang sama.
    """
    if fund.empty:
        df = hist.copy()
        for kolom in ("Nama", "Sektor"):
            df[kolom] = ""
        return df

    kolom_fund = [k for k in fund.columns if k not in ("Diperbarui",)]
    df = hist.merge(fund[kolom_fund], on="Ticker", how="left")

    # Ticker yang tidak ada di cache tetap lolos dengan seluruh kolom
    # fundamentalnya kosong. Tanpa peringatan ini, screening atas daftar
    # ticker khusus akan tampak berjalan normal padahal Skor dan Flag-nya
    # kosong semata-mata karena cache-nya belum pernah mencakup emiten itu.
    hilang = df.loc[df["Periode"].isna() & df["EPS"].isna(), "Ticker"].tolist()
    if hilang:
        print(f"{len(hilang)} ticker tidak ada di cache fundamental "
              f"(fundamentalnya kosong): {', '.join(hilang[:12])}"
              + (" ..." if len(hilang) > 12 else "")
              + "\n  Perbarui dengan: python scripts/perbarui_fundamental.py "
                "--tickers <daftar>", file=sys.stderr)

    harga = pd.to_numeric(df["Harga"], errors="coerce")
    eps = pd.to_numeric(df["EPS"], errors="coerce")
    bvps = pd.to_numeric(df["BVPS"], errors="coerce")
    dps = pd.to_numeric(df["DPS"], errors="coerce")
    saham = pd.to_numeric(df["Saham"], errors="coerce")

    # EPS/BVPS nol dibuang lebih dulu: hasil bagi dengan nol menghasilkan inf,
    # yang lolos dari pd.isna() dan akan merusak median sektor di bawah.
    df["PER"] = (harga / eps.where(eps != 0)).round(1)
    df["PBV"] = (harga / bvps.where(bvps != 0)).round(2)
    df["Dividen%"] = (dps.fillna(0) / harga * 100).round(2)
    mcap = harga * saham
    df["MarketCap(T)"] = (mcap / 1e12).round(1)
    # FCF Yield baru bisa dihitung di sini karena butuh kapitalisasi pasar,
    # yang berubah tiap hari mengikuti harga.
    df["FCFYield%"] = (pd.to_numeric(df["FCF"], errors="coerce") / mcap * 100).round(2)

    # EV/EBITDA juga bergantung harga lewat kapitalisasi pasarnya. Gunanya
    # melengkapi PER: enterprise value ikut menghitung utang, jadi dua emiten
    # dengan PER sama tapi beban utang jauh berbeda tidak lagi terbaca sama
    # murahnya. EBITDA non-positif dilewati — rasionya jadi tak bermakna.
    ebitda = pd.to_numeric(df["EBITDA"], errors="coerce")
    ev = mcap + pd.to_numeric(df["UtangBersih"], errors="coerce")
    df["EV/EBITDA"] = (ev / ebitda.where(ebitda > 0)).round(2)

    # Seberapa besar kas operasi yang habis terpakai belanja modal. Rendah
    # berarti bisnisnya ringan modal, tapi terlalu rendah bisa berarti
    # investasinya kurang — jadi penilaiannya nanti berpuncak di tengah,
    # bukan makin rendah makin baik.
    ocf = pd.to_numeric(df["OCF"], errors="coerce")
    df["Capex/OCF"] = (pd.to_numeric(df["Capex"], errors="coerce").abs()
                       / ocf.where(ocf > 0)).round(2)
    return df


def tambah_median_sektor(df: pd.DataFrame) -> pd.DataFrame:
    """Bandingkan PER dan PBV tiap emiten terhadap median sektornya.

    Ini yang membuat valuasi bisa dibaca lintas sektor. PBV 2,5 di bank dan
    PBV 2,5 di emiten batubara bukan hal yang sama — yang pertama biasa saja,
    yang kedua mahal. Angka absolutnya tetap ditampilkan, tapi kolom
    PERvsSektor/PBVvsSektor-lah yang menjawab "mahal dibanding siapa".

    Rasio 1,0 = persis median sektornya; 0,7 = 30% lebih murah; 1,4 = 40%
    lebih mahal. Hanya nilai positif yang ikut menghitung median: PER negatif
    berarti emitennya rugi, dan memasukkannya akan menarik median ke bawah
    seolah-olah sektornya sedang murah.
    """
    for kolom, nama in (("PER", "PERvsSektor"), ("PBV", "PBVvsSektor")):
        df[nama] = None
        if "Sektor" not in df.columns or kolom not in df.columns:
            continue
        sektor = df["Sektor"].fillna("").astype(str).str.strip()
        nilai = pd.to_numeric(df[kolom], errors="coerce")
        # Emiten tanpa label sektor dikeluarkan sama sekali, bukan dikumpulkan
        # jadi satu grup: kalau tidak, seluruhnya dibandingkan terhadap median
        # gabungan semua industri dan hasilnya tetap terisi seolah-olah itu
        # perbandingan sektoral. Lebih baik kosong daripada terlihat berarti.
        sah = nilai.where((nilai > 0) & (sektor != ""))
        median = sah.groupby(sektor).transform("median")
        # Sektor berisi satu-dua emiten menghasilkan median yang sebenarnya
        # cuma emiten itu sendiri, jadi rasionya selalu ~1,0 dan tidak
        # memberi tahu apa pun. Kurang dari 3 pembanding dianggap tidak cukup.
        cukup = sah.groupby(sektor).transform("count") >= 3
        df[nama] = (sah / median).where(cukup).round(2)
    return df


def terapkan_filter(df: pd.DataFrame, args) -> pd.DataFrame:
    def saring(kondisi):
        nonlocal df
        df = df[kondisi.fillna(False)]

    if args.grup:
        pilihan = [g.lower() for g in args.grup]
        saring(df["Grup"].fillna("").str.lower().apply(
            lambda s: any(g in s.split("/") for g in pilihan)))
    if args.status:
        pilihan = [s.upper() for s in args.status]
        saring(df["Status"].fillna("").str.upper().isin(pilihan))
    if args.min_skor is not None:
        saring(df["Skor"] >= args.min_skor)
    if args.syariah:
        saring(df["Syariah"] == "Ya")
    if args.non_syariah:
        saring(df["Syariah"] == "Tidak")
    if args.tanpa_flag:
        saring(df["Flag"].fillna("") == "")
    if args.kecuali_flag:
        buang = [f.lower() for f in args.kecuali_flag]
        saring(df["Flag"].fillna("").str.lower().apply(
            lambda s: not any(f in s.split(",") for f in buang)))
    if args.max_per is not None:
        saring((df["PER"] > 0) & (df["PER"] <= args.max_per))
    if args.max_pbv is not None:
        saring((df["PBV"] > 0) & (df["PBV"] <= args.max_pbv))
    if args.maks_per_sektor is not None:
        saring(df["PERvsSektor"] <= args.maks_per_sektor)
    if args.maks_pbv_sektor is not None:
        saring(df["PBVvsSektor"] <= args.maks_pbv_sektor)
    if args.sektor:
        pilihan = [s.lower() for s in args.sektor]
        saring(df["Sektor"].fillna("").str.lower().isin(pilihan))
    if args.min_roe is not None:
        saring(df["ROE%"] >= args.min_roe)
    if args.maks_der is not None:
        saring(df["DER"] <= args.maks_der)
    if args.min_current_ratio is not None:
        saring(df["CurrentRatio"] >= args.min_current_ratio)
    if args.min_ocf_laba is not None:
        saring(df["OCF/Laba"] >= args.min_ocf_laba)
    if args.min_laba_yoy is not None:
        saring(df["LabaYoY%"] >= args.min_laba_yoy)
    if args.min_omzet_yoy is not None:
        saring(df["OmzetYoY%"] >= args.min_omzet_yoy)
    if args.min_dividen is not None:
        saring(df["Dividen%"] >= args.min_dividen)
    if args.min_mcap is not None:
        saring(df["MarketCap(T)"] >= args.min_mcap)
    if args.min_nilai is not None:
        saring(df["Nilai(M)"] >= args.min_nilai)
    if args.min_volspike is not None:
        saring(df["VolSpike"] >= args.min_volspike)
    if args.max_rsi is not None:
        saring(df["RSI14"] <= args.max_rsi)
    if args.min_rsi is not None:
        saring(df["RSI14"] >= args.min_rsi)
    if args.di_atas_ma50:
        saring(df["Harga"] > df["MA50"])
    if args.di_atas_ma200:
        saring(df["Harga"] > df["MA200"])
    if args.min_rs is not None:
        saring(pd.to_numeric(df["RS"], errors="coerce") >= args.min_rs)
    if args.min_tt is not None:
        saring(pd.to_numeric(df["TT"], errors="coerce") >= args.min_tt)
    return df


def main():
    p = argparse.ArgumentParser(
        description="Screener saham IDX dengan data gratis Yahoo Finance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--tickers", nargs="+", default=DAFTAR_DEFAULT,
                   metavar="FILE",
                   help="satu atau lebih file daftar ticker, satu ticker per baris")
    p.add_argument("--demo", action="store_true",
                   help="pakai data contoh offline (data/sample_data.csv), tanpa internet")
    p.add_argument("--dari-csv", metavar="FILE",
                   help="baca data dari CSV hasil screening sebelumnya, "
                        "tanpa mengambil ulang dari internet")
    p.add_argument("--output", default="hasil_screening.csv", help="file CSV hasil")
    p.add_argument("--output-pasar", metavar="FILE",
                   help="tulis kondisi IHSG (vs MA50/MA200) ke JSON ini; "
                        "hanya saat menarik data baru, bukan dengan --dari-csv/--demo")
    p.add_argument("--output-breadth", metavar="FILE",
                   help="tulis breadth harian (persentase saham likuid di atas MA50/MA200, "
                        "tertinggi/terendah 52 minggu) ke CSV ini; hanya saat menarik data baru")
    p.add_argument("--urut", default="PER",
                   # argparse memformat help dengan %-formatting, jadi '%' pada
                   # nama kolom (ROE%, Dividen%) harus di-escape jadi '%%'
                   help="kolom pengurutan hasil, salah satu dari: "
                        + ", ".join(KOLOM[2:]).replace("%", "%%"))
    p.add_argument("--grup", nargs="+", metavar="NAMA",
                   help="hanya tampilkan saham dari grup tertentu "
                        "(mis. --grup Salim Bakrie); cocokkan dengan kolom Grup")
    p.add_argument("--status", nargs="+", metavar="STATUS",
                   help="hanya tampilkan saham dengan status tertentu, salah satu dari: "
                        + ", ".join(STATUS))
    p.add_argument("--cache-fundamental", default=CACHE_FUNDAMENTAL, metavar="FILE",
                   help="cache lapkeu dari scripts/perbarui_fundamental.py")
    p.add_argument("--daftar-syariah", default=DAFTAR_SYARIAH, metavar="FILE",
                   help="daftar saham syariah (DES) dari scripts/perbarui_syariah.py")
    p.add_argument("--min-panen", type=float, default=0.8, metavar="RASIO",
                   help="gagalkan run bila emiten yang berhasil diambil kurang dari "
                        "rasio ini (default 0.8). Setel 0 untuk mematikan.")
    f = p.add_argument_group("filter fundamental")
    f.add_argument("--sektor", nargs="+", metavar="NAMA",
                   help="hanya sektor tertentu (mis. --sektor Technology 'Real Estate')")
    # Saling meniadakan: "hanya syariah" dan "hanya non-syariah" sekaligus
    # selalu menghasilkan tabel kosong, dan lebih baik ditolak argparse dengan
    # pesan jelas daripada dijalankan lalu membingungkan.
    sy = f.add_mutually_exclusive_group()
    sy.add_argument("--syariah", action="store_true",
                    help="hanya saham yang masuk Daftar Efek Syariah")
    sy.add_argument("--non-syariah", action="store_true",
                    help="hanya saham yang TIDAK masuk Daftar Efek Syariah")
    f.add_argument("--tanpa-flag", action="store_true",
                   help="buang saham yang punya red flag apa pun")
    f.add_argument("--kecuali-flag", nargs="+", metavar="KODE",
                   help="buang saham dengan red flag tertentu saja, salah satu dari: "
                        + ", ".join(k for k, _, _ in RED_FLAG))
    f.add_argument("--min-skor", type=float, metavar="1-100",
                   help="skor fundamental minimal (mis. 70 = fundamental kuat)")
    f.add_argument("--max-per", type=float, help="PER maksimal (dan harus > 0)")
    f.add_argument("--max-pbv", type=float, help="PBV maksimal (dan harus > 0)")
    f.add_argument("--maks-per-sektor", type=float, metavar="RASIO",
                   help="PER maksimal relatif median sektornya "
                        "(mis. 0.8 = minimal 20%% lebih murah dari sektornya)")
    f.add_argument("--maks-pbv-sektor", type=float, metavar="RASIO",
                   help="PBV maksimal relatif median sektornya")
    f.add_argument("--min-roe", type=float, help="ROE minimal dalam persen")
    f.add_argument("--maks-der", type=float,
                   help="Debt to Equity maksimal (mis. 1.0)")
    f.add_argument("--min-current-ratio", type=float,
                   help="Current Ratio minimal (mis. 1.0); bank tidak punya kolom ini")
    f.add_argument("--min-ocf-laba", type=float, metavar="RASIO",
                   help="rasio arus kas operasi terhadap laba bersih minimal "
                        "(mis. 0.8 = labanya sebagian besar benar-benar jadi kas)")
    f.add_argument("--min-laba-yoy", type=float,
                   help="pertumbuhan laba kuartal terakhir (YoY) minimal, dalam persen")
    f.add_argument("--min-omzet-yoy", type=float,
                   help="pertumbuhan pendapatan kuartal terakhir (YoY) minimal, dalam persen")
    f.add_argument("--min-dividen", type=float, help="dividend yield minimal dalam persen")
    f.add_argument("--min-mcap", type=float, help="market cap minimal dalam triliun Rp")
    t = p.add_argument_group("filter teknikal & volume")
    t.add_argument("--min-nilai", type=float,
                   help="nilai transaksi rata-rata 20 hari minimal (miliar Rp)")
    t.add_argument("--min-volspike", type=float,
                   help="volume terakhir minimal N kali rata-rata 20 hari (mis. 1.5)")
    t.add_argument("--max-rsi", type=float, help="RSI-14 maksimal (mis. 30 = oversold)")
    t.add_argument("--min-rsi", type=float, help="RSI-14 minimal")
    t.add_argument("--di-atas-ma50", action="store_true", help="harga di atas MA50")
    t.add_argument("--di-atas-ma200", action="store_true", help="harga di atas MA200")
    t.add_argument("--min-rs", type=float, metavar="1-99",
                   help="Relative Strength minimal (mis. 70 = lebih kuat dari 70%% universe)")
    t.add_argument("--min-tt", type=int, metavar="0-8",
                   help="jumlah syarat Trend Template minimal (8 = lolos semua)")
    args = p.parse_args()

    if args.demo:
        sumber = Path(__file__).parent / "data" / "sample_data.csv"
        print(f"Mode demo: memakai data contoh {sumber} (BUKAN data pasar riil).\n",
              file=sys.stderr)
        df = pd.read_csv(sumber)
    elif args.dari_csv:
        print(f"Membaca data dari {args.dari_csv} (tanpa fetch ulang).\n",
              file=sys.stderr)
        df = pd.read_csv(args.dari_csv)
    else:
        tickers, grup = baca_daftar_ticker(args.tickers)
        fund = baca_cache_fundamental(args.cache_fundamental)
        print(f"Mengambil histori harga {len(tickers)} saham dari Yahoo Finance ...",
              file=sys.stderr)
        seri = {} if args.output_breadth else None
        df = ambil_histori(tickers, grup, seri)
        if not df.empty:
            df["RS"] = hitung_rs(df)
        # Panen yang anjlok harus MENGGAGALKAN run, bukan menghasilkan tabel
        # kecil yang tampak sah. Tiga run malam (27, 28, 31 Agu 2026) berstatus
        # "success" sambil menerbitkan dashboard berisi 4 dari 402 emiten,
        # karena tidak ada satu pun langkah yang memeriksa jumlah hasilnya.
        # Keluar dengan kode != 0 di sini membuat workflow berhenti sebelum
        # commit, sehingga data bagus dari run sebelumnya tetap tersaji.
        #
        # Yang dihitung adalah baris yang punya HARGA, bukan sekadar jumlah
        # baris. Emiten yang seluruh histori harganya NaN tetap menghasilkan
        # satu baris — kosong seluruhnya — jadi menghitung `len(df)` saja akan
        # meloloskan persis kegagalan yang ambang ini dipasang untuk menangkap.
        berharga = int(df["Harga"].notna().sum()) if "Harga" in df.columns else 0
        panen = berharga / len(tickers) if tickers else 0
        if panen < args.min_panen:
            sys.exit(f"Hanya {berharga} dari {len(tickers)} emiten yang dapat harga "
                     f"({panen:.0%}), di bawah ambang {args.min_panen:.0%}. "
                     f"Hasil tidak ditulis — kemungkinan sumber data sedang bermasalah.")
        print(f"{berharga} dari {len(tickers)} emiten dapat harga ({panen:.0%}).",
              file=sys.stderr)
        # Sesudah pemeriksaan panen: run yang digagalkan di atas tidak boleh
        # sempat memperbarui penanda pasar sementara tabelnya tetap yang lama.
        if args.output_pasar:
            tulis_kondisi_pasar(args.output_pasar)
        if args.output_breadth:
            tulis_breadth(args.output_breadth, seri)
            del seri
        if not df.empty:
            df = gabung_fundamental(df, fund)
            # Bar hari ini dibuang selama sesi belum tuntas, dengan aturan
            # yang sama seperti histori Yahoo di ambil_histori: angka net
            # asing setengah hari tidak boleh bersanding dengan harga penutupan.
            sekarang = datetime.now(WIB)
            buang = sekarang.date() if sekarang.time() < JAM_DATA_FINAL else None
            asing = ambil_net_asing(df["Ticker"].tolist(), buang)
            df = df.drop(columns=[k for k in KOLOM_ASING if k in df.columns])
            df = df.merge(asing, on="Ticker", how="left")

    if df.empty:
        sys.exit("Tidak ada data yang berhasil diambil.")

    # CSV lama (dan data contoh) belum tentu punya semua kolom — tambahkan
    # yang hilang agar filter dan urutan kolom tetap konsisten. Kolom yang
    # dibuat di sini isinya kosong, jadi filter atasnya tidak akan meloloskan
    # apa pun; itu memang perilaku yang benar untuk data yang tidak diketahui.
    if "Grup" not in df.columns:
        df["Grup"] = ""
    for kolom in KOLOM + KOLOM_EKSTRA:
        if kolom not in df.columns:
            df[kolom] = None
    # Median sektor dihitung ulang tiap run, bukan disimpan di cache: PER dan
    # PBV bergerak tiap hari mengikuti harga, jadi median sektornya pun ikut
    # bergerak walau lapkeu-nya sama sekali tidak berubah.
    df = tambah_median_sektor(df)
    # Status syariah juga selalu diambil ulang dari daftarnya, bukan dari CSV,
    # dengan alasan yang sama seperti Status di bawah: DES berubah dua kali
    # setahun, dan hasil --dari-csv harus mencerminkan penetapan terbaru — bukan
    # yang kebetulan tersimpan waktu CSV-nya dibuat. Kalau daftarnya tidak ada,
    # kolom yang sudah ada di CSV dibiarkan apa adanya.
    syariah, ket_syariah = baca_daftar_syariah(args.daftar_syariah)
    print(f"Daftar syariah: {ket_syariah}.", file=sys.stderr)
    if syariah is not None:
        df = tandai_syariah(df, syariah)
    elif args.syariah or args.non_syariah:
        # Tanpa penjagaan ini, --syariah pada daftar yang belum ada menghasilkan
        # tabel kosong yang tampak seperti "tidak ada yang lolos filter" —
        # persis kelas kegagalan diam yang membuat dashboard nyaris kosong
        # selama lima hari pada Agustus 2026.
        sys.exit(f"--syariah/--non-syariah dipakai, tapi daftarnya belum tersedia "
                 f"({args.daftar_syariah}: {ket_syariah}). Isi dulu lewat "
                 f"scripts/perbarui_syariah.py — lihat bagian 'Saham Syariah (DES)' "
                 f"di README.")

    # Status selalu dihitung ulang, bukan dibaca dari CSV: aturannya bisa
    # berubah, dan hasilnya harus selalu cocok dengan kolom-kolom di sebelahnya.
    df["Status"] = df.apply(hitung_status, axis=1)
    df["TT"] = df.apply(hitung_tt, axis=1).astype("Int64")
    # Skor juga selalu dihitung ulang dari kolom fundamental, dengan alasan
    # yang sama seperti Status: bobotnya bisa berubah sewaktu-waktu.
    # Int64 (nullable), bukan int biasa: skor boleh kosong, dan tanpa ini
    # pandas menaikkannya ke float sehingga CSV-nya berisi "72.0".
    df["Skor"] = df.apply(hitung_skor, axis=1).astype("Int64")
    # Skor tiap kategori ikut disimpan supaya angka totalnya bisa dibongkar:
    # dua emiten berskor 70 bisa sampai ke sana lewat jalan yang sangat
    # berbeda — yang satu murah tapi tumbuh lambat, yang lain mahal tapi
    # sangat menguntungkan.
    for kategori in BOBOT_KATEGORI:
        df[f"Skor{kategori}"] = df.apply(
            lambda r, k=kategori: (lambda s: None if s[0] is None
                                   or s[1] < MIN_CAKUPAN_KATEGORI
                                   else round(s[0]))(
                skor_kategori(r, k, str(r.get("Sektor") or ""))),
            axis=1).astype("Int64")
    # Flag dihitung setelah skor dan sengaja tidak ikut menguranginya: skor
    # adalah rata-rata, dan satu cacat berat tidak boleh bisa disamarkan oleh
    # banyak angka bagus. Dua kolom itu menjawab pertanyaan berbeda.
    df["Flag"] = df.apply(hitung_flag, axis=1)
    # Kolom inti dulu, kolom fundamental tambahan menyusul di belakang — yang
    # kedua ikut tersimpan ke CSV tapi tidak ditampilkan di tabel terminal.
    df = df.reindex(columns=[k for k in KOLOM + KOLOM_EKSTRA if k in df.columns])

    hasil = terapkan_filter(df, args)
    if args.urut in hasil.columns:
        hasil = hasil.sort_values(args.urut, na_position="last")

    print(f"\n=== Hasil screening: {len(hasil)} dari {len(df)} saham lolos ===\n")
    if hasil.empty:
        print("Tidak ada saham yang memenuhi seluruh kriteria.")
    else:
        print(hasil[[k for k in KOLOM if k in hasil.columns]].to_string(index=False))
    # CSV selalu ditulis (walau kosong) agar hasil lama tidak tertinggal
    # saat dijalankan otomatis tiap malam.
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    hasil.to_csv(args.output, index=False)
    print(f"\nDisimpan ke {args.output}")


if __name__ == "__main__":
    main()
