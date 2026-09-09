#!/usr/bin/env python3
"""Uji winrate: apakah daftar swing malam itu benar-benar menghasilkan uang?

Screening menjawab "saham apa yang lolos filter". Berkas ini menjawab
pertanyaan yang tidak pernah dijawab siapa pun sesudahnya: **kalau daftar itu
benar-benar dibeli, hasilnya bagaimana sebulan kemudian?**

Simulasinya sengaja dibuat sepolos mungkin — tidak ada stop loss, tidak ada
target, tidak ada penilaian ulang. Setiap saham yang muncul di hasil/swing.csv
dibeli dengan modal tetap, lalu dibiarkan dan dicatat nilainya tiap hari bursa
berikutnya sampai 21 hari (kira-kira satu bulan bursa). Itu justru gunanya:
yang mau diukur adalah nilai daftarnya sendiri, bukan nilai manajemen posisi
sesudahnya. Kalau daftar mentah saja sudah tidak menghasilkan, aturan keluar
apa pun cuma menambal.

Pemakaian:
    python uji_winrate.py                        # perbarui arsip + hitung ulang
    python uji_winrate.py --dari-git             # ikut baca riwayat swing.csv di git
    python uji_winrate.py --modal 5000000        # modal lain per posisi
    python uji_winrate.py --hari 40              # jendela lebih panjang
    python uji_winrate.py --harga-csv contoh.csv # harga dari berkas, tanpa Yahoo

Keluaran:
    hasil/riwayat_swing.csv   arsip pick harian (tumbuh terus, tidak pernah ditimpa)
    hasil/winrate.csv         satu baris per posisi, plus kolom Hari0%..HariN%
    hasil/winrate_ringkas.csv winrate & rata-rata laba per hari ke-N
    hasil/winrate_meta.json   parameter simulasi, dibaca dashboard
"""

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from io import StringIO
from pathlib import Path
from statistics import median

import pandas as pd

# WIB tidak pernah memakai DST — alasan yang sama seperti di screener.py.
WIB = timezone(timedelta(hours=7))

# Sesi bursa dibuka 09:00 WIB. Dipakai untuk menjawab satu pertanyaan:
# sesudah screening selesai jam sekian, sesi mana yang paling cepat bisa
# dipakai membeli?
JAM_BUKA = time(9, 0)

# Satu lot IDX = 100 lembar. Order di bawah satu lot cuma bisa lewat pasar
# negosiasi, jadi modal yang tidak cukup untuk satu lot artinya sahamnya
# memang tidak terbeli — bukan dibulatkan ke atas.
LEMBAR_PER_LOT = 100

# Modal per posisi. Tetap, bukan persentase portofolio: yang diukur di sini
# adalah kualitas daftarnya, dan modal yang berubah-ubah membuat hasil satu
# saham ikut bergantung pada berapa saham lain yang kebetulan lolos malam itu.
MODAL_DEFAULT = 10_000_000

# Biaya broker daring Indonesia yang lazim: 0,15% beli, 0,25% jual (selisihnya
# pajak penjualan 0,1%). Kecil, tapi bukan nol — dan justru di jendela pendek
# seperti ini pengaruhnya paling terasa. Posisi yang bergerak +0,3% dalam
# seminggu terbaca untung kalau biayanya diabaikan, padahal aslinya rugi.
FEE_BELI = 0.15
FEE_JUAL = 0.25

# 21 hari bursa ≈ satu bulan kalender. Persis pertanyaan yang mau dijawab:
# "sebulan ke depan efektif atau tidak".
HARI_DEFAULT = 21

BERKAS_SWING = "hasil/swing.csv"
BERKAS_RIWAYAT = "hasil/riwayat_swing.csv"
BERKAS_META_SCREENING = "hasil/meta.json"
BERKAS_HASIL = "hasil/winrate.csv"
BERKAS_RINGKAS = "hasil/winrate_ringkas.csv"
BERKAS_META = "hasil/winrate_meta.json"

KOLOM_RIWAYAT = ["Tanggal", "Waktu", "Ticker", "Nama", "Status", "Skor", "HargaScreening"]


# ------------------------------------------------------------------ arsip pick
def _baris_pick(teks: str, waktu: datetime) -> list[dict]:
    """Ubah satu isi swing.csv menjadi baris arsip.

    Kolomnya dibaca lewat nama, bukan posisi: swing.csv pernah bertambah kolom
    di tengah (Syariah, 1 Sep 2026), jadi versi lama dan baru tidak sejajar.
    Yang wajib ada cuma Ticker dan Harga.
    """
    if not teks.strip():
        return []
    try:
        df = pd.read_csv(StringIO(teks))
    except Exception:
        return []
    if df.empty or "Ticker" not in df.columns:
        return []

    def kolom(nama):
        return df[nama] if nama in df.columns else pd.Series([None] * len(df))

    stempel = waktu.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    tanggal = waktu.astimezone(WIB).date().isoformat()
    return [
        {
            "Tanggal": tanggal,
            "Waktu": stempel,
            "Ticker": str(t).strip().upper(),
            "Nama": "" if pd.isna(n) else str(n),
            "Status": "" if pd.isna(s) else str(s),
            "Skor": "" if pd.isna(sk) else sk,
            "HargaScreening": "" if pd.isna(h) else h,
        }
        for t, n, s, sk, h in zip(df["Ticker"], kolom("Nama"), kolom("Status"),
                                  kolom("Skor"), kolom("Harga"))
        if isinstance(t, str) and t.strip()
    ]


def pick_dari_git(berkas: str) -> list[dict]:
    """Semua versi swing.csv yang pernah di-commit, beserta waktu commit-nya.

    Arsip pick tidak pernah ditulis sampai hari ini, tapi datanya sebetulnya
    sudah ada: tiap run malam meng-commit hasil/swing.csv, jadi riwayat git
    adalah catatan pick harian yang lengkap. Sekali dibongkar ke
    hasil/riwayat_swing.csv, uji winrate langsung punya data sebulan penuh
    alih-alih harus menunggu sebulan dulu.

    Dipanggil hanya lewat --dari-git. Checkout di GitHub Actions dangkal
    (fetch-depth 1) sehingga di CI fungsi ini tidak menemukan apa-apa; itu
    bukan kegagalan, cuma tidak ada yang bisa ditambahkan.
    """
    try:
        keluaran = subprocess.run(
            ["git", "log", "--format=%H %cI", "--", berkas],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  riwayat git tidak terbaca ({e}) — dilewati.", file=sys.stderr)
        return []

    baris = []
    for entri in keluaran.splitlines():
        sha, _, iso = entri.partition(" ")
        if not sha or not iso:
            continue
        try:
            isi = subprocess.run(
                ["git", "show", f"{sha}:{berkas}"],
                capture_output=True, text=True, check=True,
            ).stdout
        except subprocess.CalledProcessError:
            continue
        baris += _baris_pick(isi, datetime.fromisoformat(iso))
    print(f"  {len(baris)} baris pick dari {len(keluaran.splitlines())} commit.",
          file=sys.stderr)
    return baris


def pick_terkini(berkas: str, meta: str) -> list[dict]:
    """Isi swing.csv sekarang, dicap dengan waktu run yang menghasilkannya.

    Waktunya diambil dari hasil/meta.json, bukan dari jam sekarang. Bedanya
    penting: kalau skrip ini dijalankan ulang berhari-hari kemudian atas CSV
    lama, memakai jam sekarang akan mencatat pick itu seolah lahir hari ini
    dan membelinya di harga yang salah.
    """
    p = Path(berkas)
    if not p.exists():
        print(f"  {berkas} tidak ada — tidak ada pick baru.", file=sys.stderr)
        return []
    waktu = datetime.now(timezone.utc)
    m = Path(meta)
    if m.exists():
        try:
            stempel = json.loads(m.read_text()).get("diperbarui")
            if stempel:
                waktu = datetime.fromisoformat(stempel.replace("Z", "+00:00"))
        except (ValueError, OSError) as e:
            print(f"  {meta} tidak terbaca ({e}) — dipakai jam sekarang.", file=sys.stderr)
    return _baris_pick(p.read_text(), waktu)


def perbarui_riwayat(berkas: str, baru: list[dict]) -> pd.DataFrame:
    """Gabungkan pick baru ke arsip, buang duplikat, simpan, kembalikan isinya.

    Arsipnya hanya bertambah — sekali sebuah pick tercatat, ia tidak pernah
    dihapus meski swing.csv hari ini sudah tidak memuatnya lagi. Justru itu
    intinya: yang diuji adalah keputusan yang diambil malam itu, bukan daftar
    yang berlaku sekarang.

    Duplikat dibuang per (Tanggal, Ticker) dan yang dipertahankan adalah run
    paling awal hari itu. Sebagian hari punya dua-tiga commit (run terjadwal
    plus run yang terpicu push), dan yang paling awal adalah yang paling cepat
    bisa ditindaklanjuti.
    """
    lama = pd.read_csv(berkas) if Path(berkas).exists() else pd.DataFrame(columns=KOLOM_RIWAYAT)
    gabung = pd.concat([lama, pd.DataFrame(baru, columns=KOLOM_RIWAYAT)], ignore_index=True)
    if gabung.empty:
        return gabung
    gabung["Ticker"] = gabung["Ticker"].astype(str).str.strip().str.upper()
    gabung = (gabung.sort_values("Waktu")
                    .drop_duplicates(subset=["Tanggal", "Ticker"], keep="first")
                    .sort_values(["Tanggal", "Ticker"])
                    .reset_index(drop=True))
    Path(berkas).parent.mkdir(parents=True, exist_ok=True)
    gabung.to_csv(berkas, index=False)
    print(f"Arsip pick: {len(gabung)} baris, "
          f"{gabung['Tanggal'].nunique()} hari screening -> {berkas}", file=sys.stderr)
    return gabung


# ------------------------------------------------------------------ harga
def ambil_harga(tickers: list[str], mulai: date) -> pd.DataFrame:
    """Open/High/Low/Close harian tiap emiten, dalam format panjang.

    Kolom: Ticker, Tanggal, Open, High, Low, Close. Format panjang dipilih
    supaya bisa ditulis ke CSV apa adanya dan dibaca ulang lewat --harga-csv —
    itu yang membuat simulasinya bisa diuji tanpa jaringan.
    """
    import yfinance as yf

    baris = []
    for i, kode in enumerate(tickers, 1):
        tkr = f"{kode}.JK"
        print(f"  [{i}/{len(tickers)}] {tkr} ...", file=sys.stderr)
        try:
            hist = yf.Ticker(tkr).history(start=mulai.isoformat(), auto_adjust=False)
            # Bar tanpa harga dibuang lebih dulu. Yahoo sesekali mengirimnya
            # (lihat catatan panjang di screener.py soal run 27-31 Agu 2026),
            # dan di sini satu bar cacat di tengah jendela akan menggeser
            # seluruh hitungan hari ke-N sesudahnya.
            hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
            if hist.empty:
                print("      kosong.", file=sys.stderr)
                continue
            for t, r in zip(hist.index, hist.itertuples()):
                baris.append({
                    "Ticker": kode, "Tanggal": t.date().isoformat(),
                    "Open": float(r.Open), "High": float(r.High),
                    "Low": float(r.Low), "Close": float(r.Close),
                })
        except Exception as e:
            print(f"      gagal: {e}", file=sys.stderr)
    return pd.DataFrame(baris, columns=["Ticker", "Tanggal", "Open", "High", "Low", "Close"])


def per_emiten(harga: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pecah tabel harga panjang jadi satu tabel per emiten, urut tanggal."""
    keluar = {}
    for kode, blok in harga.groupby("Ticker"):
        keluar[str(kode)] = blok.sort_values("Tanggal").reset_index(drop=True)
    return keluar


# ------------------------------------------------------------------ simulasi
def tanggal_beli(bar: pd.DataFrame, waktu: datetime) -> int | None:
    """Indeks bar pertama yang sesinya baru dibuka SESUDAH screening selesai.

    Ini satu-satunya bagian simulasi yang gampang salah dan diam-diam
    membesarkan hasilnya. Screening malam jalan jam 18-an WIB, jadi harga
    penutupan yang dipakainya sudah lewat — tidak ada seorang pun yang bisa
    membeli di harga itu. Membeli di penutupan hari screening berarti
    memberi simulasinya kemampuan melihat masa depan sebesar satu hari,
    dan pada saham yang lolos justru karena volume masuk hari itu, satu hari
    adalah bagian terbesar kenaikannya.

    Yang dipakai karena itu harga PEMBUKAAN sesi berikutnya: harga paling
    awal yang benar-benar bisa dieksekusi. Run pagi (mis. commit 08:08 WIB)
    ikut tertangani sendiri — sesi hari itu belum buka, jadi bar hari itu
    juga yang terpilih.
    """
    batas = waktu.astimezone(WIB)
    for i, t in enumerate(bar["Tanggal"]):
        buka = datetime.combine(date.fromisoformat(t), JAM_BUKA, tzinfo=WIB)
        if buka > batas:
            return i
    return None


def simulasi(riwayat: pd.DataFrame, bars: dict[str, pd.DataFrame],
             modal: int, hari: int, fee_beli: float, fee_jual: float) -> pd.DataFrame:
    """Satu baris per posisi, plus kolom Hari0%..HariN%.

    Hari0 adalah penutupan hari beli itu sendiri (sudah dipotong biaya beli,
    jadi hampir selalu negatif tipis), Hari1 penutupan besoknya, dan
    seterusnya. Kolom hari yang belum sampai dibiarkan kosong — posisi yang
    baru berumur tiga hari tidak boleh ikut menghitung winrate hari ke-21,
    dan mengisinya dengan nilai terakhir akan membuatnya ikut.
    """
    kolom_hari = [f"Hari{n}%" for n in range(hari + 1)]
    baris = []
    dilewati = {}

    for r in riwayat.itertuples():
        kode = r.Ticker
        bar = bars.get(kode)
        if bar is None or bar.empty:
            dilewati["tanpa data harga"] = dilewati.get("tanpa data harga", 0) + 1
            continue
        i0 = tanggal_beli(bar, datetime.fromisoformat(str(r.Waktu).replace("Z", "+00:00")))
        if i0 is None:
            dilewati["belum ada sesi sesudah screening"] = \
                dilewati.get("belum ada sesi sesudah screening", 0) + 1
            continue

        beli = float(bar["Open"].iloc[i0])
        # Harga nol atau negatif tidak masuk akal, tapi bukan mustahil keluar
        # dari Yahoo (lihat catatan soal bar cacat di atas). Tanpa penjagaan
        # ini barisnya membagi dengan nol dan menghanguskan seluruh run.
        if beli <= 0:
            dilewati["harga beli tidak masuk akal"] = \
                dilewati.get("harga beli tidak masuk akal", 0) + 1
            continue
        lot = int(modal // (beli * LEMBAR_PER_LOT))
        if lot < 1:
            dilewati["harga di atas modal satu lot"] = \
                dilewati.get("harga di atas modal satu lot", 0) + 1
            continue
        lembar = lot * LEMBAR_PER_LOT
        pokok = lembar * beli
        # Biaya beli menambah ongkos masuk, biaya jual mengurangi hasil keluar.
        # Keduanya dipakai di tiap hari ke-N, bukan hanya di akhir: kolom
        # Hari5% harus menjawab "kalau dijual hari itu, untung berapa" — dan
        # menjual hari itu ya kena biaya jual.
        ongkos = pokok * (1 + fee_beli / 100)

        jendela = bar.iloc[i0:i0 + hari + 1]
        nilai_per_hari, gerak_per_hari = [], []
        for tutup in jendela["Close"]:
            hasil_jual = lembar * float(tutup) * (1 - fee_jual / 100)
            nilai_per_hari.append(hasil_jual)
            gerak_per_hari.append((hasil_jual - ongkos) / ongkos * 100)

        # Titik akhir = hari terakhir yang datanya sudah ada. Untuk posisi yang
        # jendelanya sudah tuntas ini hari ke-N; untuk yang masih berjalan,
        # penutupan kemarin.
        akhir = len(jendela) - 1
        tertinggi = max(gerak_per_hari)
        terendah = min(gerak_per_hari)

        isi = {
            "Tanggal": r.Tanggal,
            "Ticker": kode,
            "Nama": r.Nama,
            "Status": r.Status,
            "Skor": r.Skor,
            "TanggalBeli": jendela["Tanggal"].iloc[0],
            "HargaBeli": round(beli, 2),
            "Lot": lot,
            "Lembar": lembar,
            "Modal": round(ongkos),
            "TanggalAkhir": jendela["Tanggal"].iloc[akhir],
            "HargaAkhir": round(float(jendela["Close"].iloc[akhir]), 2),
            "HariKe": akhir,
            "Selesai": "Ya" if akhir >= hari else "Tidak",
            "Nilai": round(nilai_per_hari[akhir]),
            "LabaRp": round(nilai_per_hari[akhir] - ongkos),
            "Laba%": round(gerak_per_hari[akhir], 2),
            "Puncak%": round(tertinggi, 2),
            "Jatuh%": round(terendah, 2),
        }
        for n, kol in enumerate(kolom_hari):
            isi[kol] = round(gerak_per_hari[n], 2) if n < len(gerak_per_hari) else None
        baris.append(isi)

    for alasan, jumlah in dilewati.items():
        print(f"  {jumlah} pick dilewati: {alasan}.", file=sys.stderr)
    return pd.DataFrame(baris)


def ringkas(posisi: pd.DataFrame, hari: int) -> pd.DataFrame:
    """Winrate dan laba rata-rata untuk tiap hari ke-N.

    Tiap baris hanya menghitung posisi yang benar-benar sudah mencapai hari
    itu, jadi kolom Posisi menyusut ke bawah — hari ke-21 selalu punya sampel
    lebih sedikit daripada hari ke-1. Itu bukan cacat, itu keterangannya:
    winrate dari 12 posisi tidak boleh dibaca sepercaya winrate dari 150.
    """
    baris = []
    for n in range(hari + 1):
        kol = f"Hari{n}%"
        if kol not in posisi.columns:
            continue
        nilai = posisi[kol].dropna()
        if nilai.empty:
            baris.append({"Hari": n, "Posisi": 0, "Menang": 0, "Winrate%": None,
                          "RataLaba%": None, "MedianLaba%": None, "TotalLabaRp": 0,
                          "Terbaik%": None, "Terburuk%": None})
            continue
        # Modal per posisi tetap, jadi laba rupiah bisa dihitung ulang dari
        # persennya tanpa menyimpan kolom rupiah untuk tiap hari ke-N.
        laba_rp = (nilai / 100 * posisi.loc[nilai.index, "Modal"]).sum()
        menang = int((nilai > 0).sum())
        baris.append({
            "Hari": n,
            "Posisi": len(nilai),
            "Menang": menang,
            "Winrate%": round(menang / len(nilai) * 100, 1),
            "RataLaba%": round(float(nilai.mean()), 2),
            "MedianLaba%": round(float(median(nilai)), 2),
            "TotalLabaRp": round(float(laba_rp)),
            "Terbaik%": round(float(nilai.max()), 2),
            "Terburuk%": round(float(nilai.min()), 2),
        })
    return pd.DataFrame(baris)


# ------------------------------------------------------------------ tampilan
def rupiah(n, tanda: bool = False) -> str:
    """Angka rupiah bergaya Indonesia (titik ribuan)."""
    if n is None or pd.isna(n):
        return "–"
    return f"Rp{n:+,.0f}".replace(",", ".") if tanda else f"Rp{n:,.0f}".replace(",", ".")


def persen(n, tanda: bool = True) -> str:
    if n is None or pd.isna(n):
        return "–"
    return f"{n:+.2f}%" if tanda else f"{n:.1f}%"


# ------------------------------------------------------------------ CLI
def main() -> int:
    p = argparse.ArgumentParser(
        description="Uji winrate daftar swing: beli modal tetap, tahan sampai N hari bursa.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Pemakaian:")[1] if "Pemakaian:" in __doc__ else None,
    )
    p.add_argument("--swing", default=BERKAS_SWING, help="CSV pick swing terkini")
    p.add_argument("--riwayat", default=BERKAS_RIWAYAT, help="arsip pick harian")
    p.add_argument("--meta-screening", default=BERKAS_META_SCREENING,
                   help="meta.json untuk cap waktu pick terkini")
    p.add_argument("--dari-git", action="store_true",
                   help="bongkar riwayat commit hasil/swing.csv ke arsip (butuh clone penuh)")
    p.add_argument("--tanpa-pick-baru", action="store_true",
                   help="hitung ulang dari arsip saja, jangan baca swing.csv")
    p.add_argument("--modal", type=int, default=MODAL_DEFAULT,
                   help=f"modal per posisi, rupiah (default {MODAL_DEFAULT:,})".replace(",", "."))
    p.add_argument("--hari", type=int, default=HARI_DEFAULT,
                   help=f"panjang jendela dalam hari bursa (default {HARI_DEFAULT})")
    p.add_argument("--fee-beli", type=float, default=FEE_BELI, help="biaya beli, persen")
    p.add_argument("--fee-jual", type=float, default=FEE_JUAL, help="biaya jual, persen")
    p.add_argument("--harga-csv", help="baca harga dari CSV (Ticker,Tanggal,Open,High,Low,Close) "
                                       "alih-alih menarik dari Yahoo")
    p.add_argument("--simpan-harga", help="simpan harga yang ditarik ke CSV ini")
    p.add_argument("--output", default=BERKAS_HASIL, help="CSV hasil per posisi")
    p.add_argument("--output-ringkas", default=BERKAS_RINGKAS, help="CSV ringkasan per hari")
    p.add_argument("--output-meta", default=BERKAS_META, help="JSON parameter simulasi")
    a = p.parse_args()

    if a.hari < 1:
        print("--hari minimal 1.", file=sys.stderr)
        return 2

    print("Menyusun arsip pick ...", file=sys.stderr)
    baru = []
    if a.dari_git:
        baru += pick_dari_git(a.swing)
    if not a.tanpa_pick_baru:
        baru += pick_terkini(a.swing, a.meta_screening)
    riwayat = perbarui_riwayat(a.riwayat, baru)
    if riwayat.empty:
        print("Arsip masih kosong — belum ada yang bisa diuji.", file=sys.stderr)
        return 1

    tickers = sorted(riwayat["Ticker"].unique())
    # Mundur seminggu dari pick paling awal: bar pembelian bisa jatuh persis di
    # tanggal pick, dan margin ini menjaga agar libur panjang tidak membuat
    # jendelanya mulai kosong.
    mulai = date.fromisoformat(riwayat["Tanggal"].min()) - timedelta(days=7)

    if a.harga_csv:
        print(f"Membaca harga dari {a.harga_csv} ...", file=sys.stderr)
        harga = pd.read_csv(a.harga_csv, dtype={"Ticker": str, "Tanggal": str})
    else:
        print(f"Menarik harga {len(tickers)} emiten sejak {mulai} ...", file=sys.stderr)
        harga = ambil_harga(tickers, mulai)
        if a.simpan_harga:
            harga.to_csv(a.simpan_harga, index=False)
    if harga.empty:
        print("Tidak ada data harga sama sekali — hasil tidak ditulis.", file=sys.stderr)
        return 1

    posisi = simulasi(riwayat, per_emiten(harga), a.modal, a.hari, a.fee_beli, a.fee_jual)
    if posisi.empty:
        print("Tidak ada posisi yang bisa disimulasikan.", file=sys.stderr)
        return 1
    posisi = posisi.sort_values(["Tanggal", "Ticker"]).reset_index(drop=True)
    tabel = ringkas(posisi, a.hari)

    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    posisi.to_csv(a.output, index=False)
    tabel.to_csv(a.output_ringkas, index=False)
    Path(a.output_meta).write_text(json.dumps({
        "diperbarui": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modal": a.modal,
        "hari": a.hari,
        "feeBeli": a.fee_beli,
        "feeJual": a.fee_jual,
        "lembarPerLot": LEMBAR_PER_LOT,
        "posisi": len(posisi),
        "posisiSelesai": int((posisi["Selesai"] == "Ya").sum()),
        "hariScreening": int(riwayat["Tanggal"].nunique()),
        "pickPertama": posisi["Tanggal"].min(),
        "pickTerakhir": posisi["Tanggal"].max(),
    }, indent=2) + "\n")

    # Ringkasan terminal: cukup untuk membaca hasilnya tanpa membuka dashboard.
    # Baris hari dipilih, bukan semuanya: 22 baris angka membuat yang penting
    # (hari pertama, seminggu, sebulan) tenggelam di antara yang tidak dibaca.
    sorot = sorted({0, 1, 2, 3, 5, 10, 15, a.hari})
    print(f"\n{len(posisi)} posisi, {riwayat['Tanggal'].nunique()} hari screening, "
          f"modal {rupiah(a.modal)}/posisi", file=sys.stderr)
    print(f"{'Hari':>5} {'Posisi':>7} {'Winrate':>8} {'Rata':>8} {'Median':>8} {'Total':>16}",
          file=sys.stderr)
    for _, r in tabel.iterrows():
        if r["Hari"] not in sorot:
            continue
        # iterrows menyerahkan baris campur tipe sebagai Series float; angka
        # cacahnya dikembalikan ke int supaya tidak tercetak "146.0".
        print(f"{int(r['Hari']):>5} {int(r['Posisi']):>7} {persen(r['Winrate%'], tanda=False):>8} "
              f"{persen(r['RataLaba%']):>8} {persen(r['MedianLaba%']):>8} "
              f"{rupiah(r['TotalLabaRp'], tanda=True):>16}", file=sys.stderr)
    print(f"\nDisimpan: {a.output}, {a.output_ringkas}, {a.output_meta}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
