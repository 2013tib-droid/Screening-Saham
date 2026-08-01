#!/usr/bin/env python3
"""Screener saham Indonesia (IDX) berbasis data gratis Yahoo Finance.

Data diambil lewat library `yfinance` — gratis, tanpa API key. Ticker Bursa
Efek Indonesia memakai suffix `.JK` (contoh: BBCA.JK, TLKM.JK).

Contoh pemakaian:
    python screener.py                              # screening semua daftar, tanpa filter
    python screener.py --max-per 15 --max-pbv 2 --min-roe 15
    python screener.py --tickers tickers/lq45.txt --min-dividen 3 --di-atas-ma200
    python screener.py --tickers tickers/bakrie.txt tickers/salim.txt
    python screener.py --dari-csv hasil/semua.csv --grup Prajogo
    python screener.py --demo --max-per 15          # mode offline dengan data contoh

Hasil ditampilkan sebagai tabel dan disimpan ke hasil_screening.csv.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

KOLOM = [
    "Ticker", "Nama", "Grup", "Harga", "PER", "PBV", "ROE%", "Dividen%",
    "MarketCap(T)", "Vol20(jt)", "Nilai(M)", "VolSpike",
    "RSI14", "MA50", "MA200",
]

# Daftar default: LQ45 plus saham grup konglomerasi besar di luar LQ45.
DAFTAR_DEFAULT = [
    "tickers/lq45.txt",
    "tickers/prajogo.txt",
    "tickers/bakrie.txt",
    "tickers/salim.txt",
    "tickers/hapsoro.txt",
]


def baca_daftar_ticker(paths: list[str]) -> tuple[list[str], dict[str, str]]:
    """Baca satu atau lebih file daftar ticker.

    Mengembalikan daftar ticker unik (urutan file dipertahankan) dan peta
    ticker -> label grup. Satu saham bisa masuk beberapa daftar (mis. INDF ada
    di LQ45 dan di grup Salim); labelnya digabung jadi "LQ45/Salim".

    Format file: satu ticker per baris, komentar diawali '#'. Komentar boleh
    ditulis di belakang ticker. Baris '# grup: Nama' di mana pun dalam file
    menentukan label grup; bila tidak ada, dipakai nama file tanpa ekstensi.
    """
    tickers: list[str] = []
    grup: dict[str, str] = {}
    for path in paths:
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
            elif label not in grup[polos].split("/"):
                grup[polos] += "/" + label
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
    if args.max_per is not None:
        saring((df["PER"] > 0) & (df["PER"] <= args.max_per))
    if args.max_pbv is not None:
        saring((df["PBV"] > 0) & (df["PBV"] <= args.max_pbv))
    if args.min_roe is not None:
        saring(df["ROE%"] >= args.min_roe)
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
    f = p.add_argument_group("filter fundamental")
    f.add_argument("--max-per", type=float, help="PER maksimal (dan harus > 0)")
    f.add_argument("--max-pbv", type=float, help="PBV maksimal (dan harus > 0)")
    f.add_argument("--min-roe", type=float, help="ROE minimal dalam persen")
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

    # CSV lama (dan data contoh) belum punya kolom Grup — tambahkan agar
    # filter dan urutan kolom tetap konsisten.
    if "Grup" not in df.columns:
        df["Grup"] = ""
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
