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
from pathlib import Path

import pandas as pd

KOLOM = [
    "Ticker", "Nama", "Grup", "Status", "Skor", "Harga", "PER", "PBV", "ROE%",
    "LabaYoY%", "OmzetYoY%", "Dividen%",
    "MarketCap(T)", "Vol20(jt)", "Nilai(M)", "VolSpike",
    "RSI14", "MA50", "MA200",
]

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


# Skor = kesimpulan fundamental satu saham dalam satu angka 1-100. Perusahaan
# sehat (untung besar, tumbuh, valuasi wajar) dapat angka tinggi; yang rugi,
# menyusut, atau kemahalan dapat angka rendah.
#
# Bobot tiap komponen. Profitabilitas dan pertumbuhan diberi porsi terbesar
# karena itu yang menentukan sehat-tidaknya bisnisnya; valuasi ikut karena
# perusahaan bagus di harga kemahalan bukan investasi bagus; dividen paling
# kecil karena tidak membayar dividen belum tentu jelek (bisa dipakai
# ekspansi).
BOBOT_SKOR = {
    "ROE%": 25,
    "LabaYoY%": 20,
    "PER": 20,
    "OmzetYoY%": 15,
    "PBV": 10,
    "Dividen%": 10,
}

# Titik-titik konversi nilai mentah -> skor 0-100 per komponen, diurut naik.
# Di antara dua titik dipakai interpolasi linier; di luar rentang dipakai
# nilai ujungnya. Angkanya dipilih dari kebiasaan pasar Indonesia, mis. ROE
# 15% dianggap layak dan PER 10 dianggap murah — bukan hasil optimasi
# statistik, jadi jangan dibaca lebih presisi dari sebenarnya.
TITIK_SKOR = {
    "ROE%":      [(0, 0), (5, 25), (10, 45), (15, 65), (20, 80), (30, 95), (40, 100)],
    "LabaYoY%":  [(-50, 0), (-20, 15), (0, 40), (20, 65), (50, 85), (100, 100)],
    "OmzetYoY%": [(-30, 0), (-10, 20), (0, 40), (10, 60), (25, 80), (50, 100)],
    # PER & PBV: makin kecil makin murah, jadi skornya menurun.
    "PER":       [(5, 100), (10, 85), (15, 70), (20, 55), (25, 40), (35, 20), (50, 5)],
    "PBV":       [(0.5, 100), (1, 90), (2, 70), (3, 55), (5, 30), (8, 10)],
    # Yield 0 tidak dihukum berat — perusahaan tumbuh wajar menahan labanya.
    "Dividen%":  [(0, 30), (2, 55), (4, 75), (6, 90), (8, 100)],
}

# Skor hanya dikeluarkan bila komponen yang tersedia mencakup minimal porsi
# ini dari total bobot. Di bawah itu angkanya lebih menyesatkan daripada
# berguna — lebih baik kosong.
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


def hitung_skor(r) -> int | None:
    """Ringkas fundamental satu saham jadi skor 1-100 (makin tinggi makin sehat).

    Rata-rata tertimbang dari komponen yang datanya ada. Komponen yang kosong
    dibuang dan bobotnya dibagi ulang ke sisanya, jadi saham yang belum bagi
    dividen tidak otomatis kalah dari yang sudah — asal data lain lengkap.
    Kalau yang tersedia terlalu sedikit, hasilnya None (kolom kosong).

    PER atau PBV yang nol/negatif bukan data hilang melainkan kabar buruk:
    PER negatif berarti perusahaannya rugi, PBV negatif berarti ekuitasnya
    minus. Keduanya diberi skor 0, bukan dilewati.
    """
    total_bobot = 0.0
    total_skor = 0.0
    for kolom, bobot in BOBOT_SKOR.items():
        nilai = r.get(kolom)
        if nilai is None or pd.isna(nilai):
            continue
        nilai = float(nilai)
        if kolom in ("PER", "PBV") and nilai <= 0:
            skor = 0.0
        else:
            skor = _interpolasi(nilai, TITIK_SKOR[kolom])
        total_skor += skor * bobot
        total_bobot += bobot

    if total_bobot < MIN_CAKUPAN_SKOR * sum(BOBOT_SKOR.values()):
        return None
    # Dibatasi minimal 1: skor 0 mudah tertukar dengan "tidak ada data".
    return max(1, min(100, round(total_skor / total_bobot)))


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


def normalisasi_persen(nilai) -> float | None:
    """yfinance kadang mengembalikan yield sebagai fraksi (0.035) dan kadang
    sudah persen (3.5), tergantung versi. Nilai <= 1 dianggap fraksi."""
    if nilai is None:
        return None
    return round(nilai * 100, 2) if nilai <= 1 else round(nilai, 2)


def persen_pertumbuhan(nilai) -> float | None:
    """Ubah pertumbuhan dari fraksi ke persen.

    Beda dari normalisasi_persen(): pertumbuhan selalu dikirim yfinance
    sebagai fraksi dan boleh negatif atau lebih besar dari 1 (laba naik 3x =
    2.0), jadi tebakan "kalau <= 1 berarti fraksi" tidak berlaku di sini.
    """
    if nilai is None or pd.isna(nilai):
        return None
    return round(nilai * 100, 1)


def ambil_data(tickers: list[str], grup: dict[str, str] | None = None) -> pd.DataFrame:
    import yfinance as yf

    baris_data = []
    for i, tkr in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {tkr} ...", file=sys.stderr)
        try:
            saham = yf.Ticker(tkr)
            info = saham.info or {}
            hist = saham.history(period="1y")
            close = hist["Close"] if not hist.empty else pd.Series(dtype=float)
            vol = hist["Volume"] if not hist.empty else pd.Series(dtype=float)

            harga = info.get("currentPrice") or (
                round(close.iloc[-1]) if len(close) else None)
            roe = info.get("returnOnEquity")
            mcap = info.get("marketCap")
            vol20 = vol.tail(20).mean() if len(vol) >= 20 else None
            if vol20 is None or pd.isna(vol20) or vol20 <= 0:
                vol20 = None
            nilai20 = (close * vol).tail(20).mean() if vol20 else None
            if nilai20 is not None and pd.isna(nilai20):
                nilai20 = None
            baris_data.append({
                "Ticker": tkr.removesuffix(".JK"),
                "Nama": (info.get("shortName") or "")[:28],
                "Grup": (grup or {}).get(tkr.removesuffix(".JK"), ""),
                "Harga": harga,
                "PER": round(info["trailingPE"], 1) if info.get("trailingPE") else None,
                "PBV": round(info["priceToBook"], 2) if info.get("priceToBook") else None,
                "ROE%": round(roe * 100, 1) if roe is not None else None,
                # Pertumbuhan kuartal terakhir dibanding kuartal yang sama
                # setahun lalu (YoY) — ini yang paling dekat dengan "lapkeu
                # terakhir bagus atau tidak". Ikut dari .info yang sudah
                # diambil, jadi tidak menambah request.
                "LabaYoY%": persen_pertumbuhan(info.get("earningsQuarterlyGrowth")),
                "OmzetYoY%": persen_pertumbuhan(info.get("revenueGrowth")),
                "Dividen%": normalisasi_persen(info.get("dividendYield")),
                "MarketCap(T)": round(mcap / 1e12, 1) if mcap else None,
                "Vol20(jt)": round(vol20 / 1e6, 2) if vol20 else None,
                "Nilai(M)": round(nilai20 / 1e9, 1) if nilai20 else None,
                "VolSpike": round(vol.iloc[-1] / vol20, 2) if vol20 else None,
                "RSI14": hitung_rsi(close),
                "MA50": round(close.tail(50).mean()) if len(close) >= 50 else None,
                "MA200": round(close.tail(200).mean()) if len(close) >= 200 else None,
            })
        except Exception as e:
            print(f"      gagal: {e}", file=sys.stderr)
    return pd.DataFrame(baris_data, columns=KOLOM)


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
    if args.max_per is not None:
        saring((df["PER"] > 0) & (df["PER"] <= args.max_per))
    if args.max_pbv is not None:
        saring((df["PBV"] > 0) & (df["PBV"] <= args.max_pbv))
    if args.min_roe is not None:
        saring(df["ROE%"] >= args.min_roe)
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
    f = p.add_argument_group("filter fundamental")
    f.add_argument("--min-skor", type=float, metavar="1-100",
                   help="skor fundamental minimal (mis. 70 = fundamental kuat)")
    f.add_argument("--max-per", type=float, help="PER maksimal (dan harus > 0)")
    f.add_argument("--max-pbv", type=float, help="PBV maksimal (dan harus > 0)")
    f.add_argument("--min-roe", type=float, help="ROE minimal dalam persen")
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
        print(f"Mengambil data {len(tickers)} saham dari Yahoo Finance ...",
              file=sys.stderr)
        df = ambil_data(tickers, grup)

    if df.empty:
        sys.exit("Tidak ada data yang berhasil diambil.")

    # CSV lama (dan data contoh) belum tentu punya semua kolom — tambahkan
    # yang hilang agar filter dan urutan kolom tetap konsisten. Kolom yang
    # dibuat di sini isinya kosong, jadi filter atasnya tidak akan meloloskan
    # apa pun; itu memang perilaku yang benar untuk data yang tidak diketahui.
    if "Grup" not in df.columns:
        df["Grup"] = ""
    for kolom in KOLOM:
        if kolom not in df.columns:
            df[kolom] = None
    # Status selalu dihitung ulang, bukan dibaca dari CSV: aturannya bisa
    # berubah, dan hasilnya harus selalu cocok dengan kolom-kolom di sebelahnya.
    df["Status"] = df.apply(hitung_status, axis=1)
    # Skor juga selalu dihitung ulang dari kolom fundamental, dengan alasan
    # yang sama seperti Status: bobotnya bisa berubah sewaktu-waktu.
    # Int64 (nullable), bukan int biasa: skor boleh kosong, dan tanpa ini
    # pandas menaikkannya ke float sehingga CSV-nya berisi "72.0".
    df["Skor"] = df.apply(hitung_skor, axis=1).astype("Int64")
    df = df.reindex(columns=[k for k in KOLOM if k in df.columns])

    hasil = terapkan_filter(df, args)
    if args.urut in hasil.columns:
        hasil = hasil.sort_values(args.urut, na_position="last")

    print(f"\n=== Hasil screening: {len(hasil)} dari {len(df)} saham lolos ===\n")
    if hasil.empty:
        print("Tidak ada saham yang memenuhi seluruh kriteria.")
    else:
        print(hasil.to_string(index=False))
    # CSV selalu ditulis (walau kosong) agar hasil lama tidak tertinggal
    # saat dijalankan otomatis tiap malam.
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    hasil.to_csv(args.output, index=False)
    print(f"\nDisimpan ke {args.output}")


if __name__ == "__main__":
    main()
