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

Winrate sendirian tidak menjawab apa-apa, jadi setiap posisi juga
dibandingkan dengan dua hal yang dibeli di sesi yang sama, dengan biaya yang
sama: IHSG, dan rata-rata seluruh saham likuid di universe ("saham acak").
Kalau daftar swing tidak mengalahkan saham acak, winrate-nya cuma ikut pasar.

Pemakaian:
    python uji_winrate.py                        # perbarui arsip + hitung ulang
    python uji_winrate.py --dari-git             # ikut baca riwayat swing.csv di git
    python uji_winrate.py --modal 5000000        # modal lain per posisi
    python uji_winrate.py --hari 40              # jendela lebih panjang
    python uji_winrate.py --harga-csv contoh.csv # harga dari berkas, tanpa Yahoo
    python uji_winrate.py --tanpa-pembanding     # cepat: tanpa IHSG & saham acak

Keluaran:
    hasil/riwayat_swing.csv      arsip pick harian (tumbuh terus, tidak pernah ditimpa)
    hasil/winrate.csv            satu baris per posisi, plus kolom Hari0%..HariN%
    hasil/winrate_ringkas.csv    winrate, laba, dan selisih vs pembanding per hari ke-N
    hasil/winrate_pembanding.csv IHSG & saham acak per tanggal beli, Hari0%..HariN%
    hasil/winrate_meta.json      parameter simulasi, dibaca dashboard
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

# Sama dengan JAM_DATA_FINAL di screener.py: IDX tutup 15:50 WIB, Yahoo perlu
# beberapa menit memperbarui bar terakhirnya. Sebelum jam ini bar hari ini
# masih berjalan dan dibuang.
JAM_DATA_FINAL = time(16, 15)

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

# ---- pembanding
# Kode Yahoo untuk IHSG. Dikirim apa adanya, tanpa akhiran .JK.
KODE_IHSG = "^JKSE"

# "Saham acak" = rata-rata seluruh emiten universe yang pada malam screening
# cukup likuid untuk lolos syarat likuiditas daftar swing itu sendiri
# (--min-nilai 5 di screening-malam.yml). Dengan begitu yang dibandingkan
# adalah kemampuan MEMILIH, bukan perbedaan antara saham likuid dan saham
# tidur. Kalau ambang di workflow berubah, ubah juga angka ini.
NILAI_MIN_PEMBANDING = 5.0

# Rata-rata dari segelintir emiten bukan "pasar". Di bawah ini (mis. Yahoo
# cuma mengirim sebagian universe malam itu) kolom saham acak dikosongkan
# alih-alih diisi angka yang tampak sah.
MIN_EMITEN_PEMBANDING = 30

# Kondisi pasar saat pick lahir: IHSG di atas MA-nya atau tidak. Periode 50
# dipilih dari uji ulang Apr 2024-Sep 2026 (lihat README, "Kondisi pasar");
# angkanya sama dengan yang dipakai screener.py untuk hasil/pasar.json.
MA_PASAR = 50

# Harga ditarik mundur sejauh ini dari pick paling awal: MA50 IHSG butuh 50
# bar sebelum pick pertama, dan nilai transaksi 20 hari butuh 20 bar. 100 hari
# kalender memberi ~65 bar, cukup untuk keduanya plus libur panjang.
MUNDUR_HARI = 100

# Jumlah simbol per panggilan yf.download.
UKURAN_BLOK = 50

BERKAS_SWING = "hasil/swing.csv"
BERKAS_SEMUA = "hasil/semua.csv"
BERKAS_RIWAYAT = "hasil/riwayat_swing.csv"
BERKAS_META_SCREENING = "hasil/meta.json"
BERKAS_HASIL = "hasil/winrate.csv"
BERKAS_RINGKAS = "hasil/winrate_ringkas.csv"
BERKAS_PEMBANDING = "hasil/winrate_pembanding.csv"
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
KOLOM_HARGA = ["Ticker", "Tanggal", "Open", "High", "Low", "Close", "Volume"]


def ambil_harga(tickers: list[str], mulai: date) -> pd.DataFrame:
    """Open/High/Low/Close/Volume harian tiap emiten, dalam format panjang.

    Kolom: Ticker, Tanggal, Open, High, Low, Close, Volume. Format panjang
    dipilih supaya bisa ditulis ke CSV apa adanya dan dibaca ulang lewat
    --harga-csv — itu yang membuat simulasinya bisa diuji tanpa jaringan.

    Ditarik per blok lewat yf.download, bukan satu emiten satu request: sejak
    ada pembanding, yang ditarik bukan lagi puluhan pick melainkan seluruh
    universe (~400 emiten), dan 400 request berurutan makan belasan menit.
    Kode yang diawali "^" (IHSG) dikirim apa adanya; sisanya diberi .JK.
    """
    import yfinance as yf

    simbol = {(k if k.startswith("^") else f"{k}.JK"): k for k in tickers}
    daftar = list(simbol)
    potongan = []
    for i in range(0, len(daftar), UKURAN_BLOK):
        blok = daftar[i:i + UKURAN_BLOK]
        print(f"  [{min(i + UKURAN_BLOK, len(daftar))}/{len(daftar)}] ...", file=sys.stderr)
        try:
            data = yf.download(blok, start=mulai.isoformat(), auto_adjust=False,
                               group_by="ticker", threads=True, progress=False)
        except Exception as e:
            print(f"      blok gagal: {e}", file=sys.stderr)
            continue
        for s in blok:
            try:
                hist = data[s] if isinstance(data.columns, pd.MultiIndex) else data
            except KeyError:
                continue
            # Bar tanpa harga dibuang lebih dulu. Yahoo sesekali mengirimnya
            # (lihat catatan panjang di screener.py soal run 27-31 Agu 2026),
            # dan di sini satu bar cacat di tengah jendela akan menggeser
            # seluruh hitungan hari ke-N sesudahnya.
            hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
            if hist.empty:
                continue
            x = hist[["Open", "High", "Low", "Close"]].astype(float)
            x["Volume"] = (hist["Volume"].fillna(0).astype(float)
                           if "Volume" in hist.columns else 0.0)
            x["Tanggal"] = [t.date().isoformat() for t in hist.index]
            x["Ticker"] = simbol[s]
            potongan.append(x)
    if not potongan:
        return pd.DataFrame(columns=KOLOM_HARGA)
    harga = pd.concat(potongan, ignore_index=True)[KOLOM_HARGA]
    kosong = len(tickers) - harga["Ticker"].nunique()
    if kosong:
        print(f"  {kosong} dari {len(tickers)} simbol tanpa data harga.", file=sys.stderr)
    return harga


def per_emiten(harga: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Pecah tabel harga panjang jadi satu tabel per emiten, urut tanggal."""
    keluar = {}
    for kode, blok in harga.groupby("Ticker"):
        keluar[str(kode)] = blok.sort_values("Tanggal").reset_index(drop=True)
    return keluar


def hari_bursa(bars: dict[str, pd.DataFrame]) -> set[str] | None:
    """Tanggal yang benar-benar hari bursa, atau None bila tidak bisa dipastikan.

    Yahoo mengirim bar untuk hari libur di sebagian emiten: volume 0, keempat
    harga sama dengan penutupan sebelumnya. Pada data Mei-Sep 2026 ada 1.741
    bar seperti itu — 14-15 dan 27-28 Mei untuk seluruh universe, 25 Agu untuk
    118 emiten, 17 Agu untuk 9. Dibiarkan, bar itu dua kali merusak simulasi:
    pick malam 24 Agu tercatat dibeli di "pembukaan" 25 Agu yang tidak pernah
    ada, dan hitungan hari ke-N emiten itu maju satu dari emiten lain yang
    dibeli di sesi yang sama.

    Acuannya kalender IHSG. Tanggal yang tidak ada di IHSG tetap diakui kalau
    mayoritas emiten benar-benar bertransaksi hari itu — jaga-jaga kalau yang
    bolong justru bar IHSG-nya, bukan bar emitennya.
    """
    ihsg = bars.get(KODE_IHSG)
    if ihsg is None or ihsg.empty:
        return None
    sah = set(ihsg["Tanggal"])
    lain = [b for k, b in bars.items() if k != KODE_IHSG and "Volume" in b.columns]
    if lain:
        semua = pd.concat([b[["Tanggal", "Volume"]] for b in lain])
        per_tgl = semua.groupby("Tanggal")["Volume"].agg(
            ada="size", aktif=lambda v: int((v > 0).sum()))
        sah |= set(per_tgl.index[(per_tgl["aktif"] >= 20)
                                 & (per_tgl["aktif"] * 2 >= per_tgl["ada"])])
    return sah


def selaraskan_kalender(bars: dict[str, pd.DataFrame],
                        sekarang: datetime | None = None) -> dict[str, pd.DataFrame]:
    """Buang bar yang belum final dan bar di luar hari bursa (lihat hari_bursa).

    Bar hari ini dibuang selama sesi belum tuntas, dengan alasan dan ambang
    yang sama seperti bar_terakhir_belum_final di screener.py. Workflow ini
    bisa terpicu push di siang hari, dan penutupan sementara jam 11 bukan
    penutupan: hari ke-N yang dihitung darinya berubah lagi sore harinya.
    """
    hari_ini = (sekarang or datetime.now(WIB)).astimezone(WIB)
    if hari_ini.time() < JAM_DATA_FINAL:
        tgl = hari_ini.date().isoformat()
        bars = {k: b[b["Tanggal"] != tgl].reset_index(drop=True) for k, b in bars.items()}
    sah = hari_bursa(bars)
    if sah is None:
        print("  IHSG tidak ada di data harga — bar hari libur tidak bisa disaring.",
              file=sys.stderr)
        return bars
    keluar, dibuang = {}, 0
    for k, b in bars.items():
        tetap = b["Tanggal"].isin(sah)
        dibuang += int((~tetap).sum())
        keluar[k] = b[tetap].reset_index(drop=True)
    if dibuang:
        print(f"  {dibuang} bar di luar hari bursa dibuang (bar libur dari Yahoo).",
              file=sys.stderr)
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

    Kolom Ulang menandai pick atas saham yang pada sesi belinya MASIH dipegang
    dari pick sebelumnya (dibeli ≤ `hari` bar yang lalu). Orang yang mengikuti
    daftarnya tidak membeli MMIX tujuh kali dalam dua minggu — ia membelinya
    sekali lalu memegangnya. Barisnya tetap ditulis supaya tetap bisa dilihat,
    tapi ringkas() tidak menghitungnya: tanpa itu satu saham yang nongkrong di
    daftar berhari-hari ikut dihitung berkali-kali dan sampelnya terlihat
    jauh lebih tebal daripada aslinya. Pick ulang tidak memperpanjang masa
    pegang — posisi pertamanya tetap dijual di hari ke-`hari`.
    """
    kolom_hari = [f"Hari{n}%" for n in range(hari + 1)]
    baris = []
    dilewati = {}
    # Ticker -> indeks bar beli posisi terakhir yang benar-benar dibuka.
    dipegang: dict[str, int] = {}

    riwayat = riwayat.sort_values(["Tanggal", "Ticker"], kind="stable")
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
        # Posisi sebelumnya dibeli di bar i_lama dan dijual di penutupan bar
        # i_lama + hari. Pembukaan bar mana pun sampai hari itu masih jatuh di
        # masa pegangnya, jadi batasnya ≤, bukan <.
        i_lama = dipegang.get(kode)
        ulang = i_lama is not None and i0 - i_lama <= hari
        if not ulang:
            dipegang[kode] = i0
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
            "Ulang": "Ya" if ulang else "Tidak",
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


# ------------------------------------------------------------------ pembanding
def pembanding(tanggal_beli: list[str], bars: dict[str, pd.DataFrame],
               universe: set[str], hari: int, fee_beli: float,
               fee_jual: float) -> pd.DataFrame:
    """IHSG dan "saham acak" untuk tiap tanggal beli, hari ke-0..N.

    Satu baris per tanggal beli, bukan per posisi: semua pick yang dibeli di
    sesi yang sama berbagi pembanding yang sama persis, jadi menyimpannya per
    posisi cuma menggandakan angka. Dashboard menyambungkannya lewat
    TanggalBeli.

    Aturannya sama dengan posisi: beli di pembukaan sesi itu, nilai di
    penutupan bar ke-N, kedua biaya dipotong. Biaya sengaja ikut dikenakan ke
    pembanding. Yang mau diukur adalah kemampuan memilih — daftar yang sama
    sekali tidak lebih pintar dari pasar harus keluar dengan selisih ≈ 0,
    bukan −0,4% hanya karena pembandingnya dibeli tanpa ongkos.

    Hari ke-N dihitung dari kalender bursa IHSG. Untuk emiten yang tidak
    pernah disuspensi ini sama persis dengan bar ke-N milik posisinya
    sendiri; untuk yang sempat disuspensi, pembandingnya jatuh di tanggal
    bursa yang sedikit berbeda. Selisihnya kecil dan jarang, dan
    menyelaraskannya per posisi berarti menyimpan pembanding per posisi.

    Kolom:
      TanggalBeli, IHSGdiAtasMA50 (Ya/Tidak pada penutupan malam screening),
      AcakJumlah (emiten yang ikut dirata-rata), IHSG0%..IHSGN%, Acak0%..AcakN%.
    """
    fb, fj = 1 + fee_beli / 100, 1 - fee_jual / 100
    ihsg = bars.get(KODE_IHSG)
    if ihsg is not None and not ihsg.empty:
        kalender = list(ihsg["Tanggal"])
    else:
        kalender = sorted({t for b in bars.values() for t in b["Tanggal"]})
    posisi_tgl = {t: i for i, t in enumerate(kalender)}
    idx = pd.Index(kalender)

    anggota = {k: b.set_index("Tanggal") for k, b in bars.items()
               if k in universe and k != KODE_IHSG and not b.empty}
    punya_volume = all("Volume" in b.columns for b in anggota.values())
    if anggota and not punya_volume:
        print("  harga tanpa kolom Volume — saham acak tidak disaring likuiditasnya.",
              file=sys.stderr)

    def lebar(fungsi) -> pd.DataFrame:
        if not anggota:
            return pd.DataFrame(index=idx)
        return pd.DataFrame({k: fungsi(b) for k, b in anggota.items()}).reindex(idx)

    buka = lebar(lambda b: b["Open"])
    tutup = lebar(lambda b: b["Close"])
    # Nilai transaksi 20 hari dihitung dari bar emiten itu sendiri LALU
    # disejajarkan ke kalender — bukan sebaliknya. Rolling di atas kalender
    # akan menghitung hari suspensi sebagai hari tanpa transaksi.
    nilai20 = (lebar(lambda b: (b["Close"] * b["Volume"]).rolling(20).mean() / 1e9)
               if punya_volume else None)

    if ihsg is not None and not ihsg.empty:
        ih = ihsg.set_index("Tanggal")
        ma = ih["Close"].rolling(MA_PASAR).mean()
        di_atas = (ih["Close"] > ma).where(ma.notna())

    baris = []
    for tgl in sorted(set(tanggal_beli)):
        isi = {"TanggalBeli": tgl, "IHSGdiAtasMA50": "", "AcakJumlah": 0}
        for n in range(hari + 1):
            isi[f"IHSG{n}%"] = None
        for n in range(hari + 1):
            isi[f"Acak{n}%"] = None
        k = posisi_tgl.get(tgl)
        if k is None:
            baris.append(isi)
            continue

        if ihsg is not None and not ihsg.empty and tgl in ih.index:
            if k >= 1 and pd.notna(di_atas.iloc[k - 1]):
                isi["IHSGdiAtasMA50"] = "Ya" if di_atas.iloc[k - 1] else "Tidak"
            o = float(ih["Open"].iloc[k])
            for n in range(hari + 1):
                if o > 0 and k + n < len(ih):
                    isi[f"IHSG{n}%"] = round((float(ih["Close"].iloc[k + n]) * fj
                                              / (o * fb) - 1) * 100, 2)

        if anggota and k >= 1:
            o = buka.iloc[k]
            layak = o > 0
            if nilai20 is not None:
                layak &= nilai20.iloc[k - 1] >= NILAI_MIN_PEMBANDING
            isi["AcakJumlah"] = int(layak.sum())
            if isi["AcakJumlah"] >= MIN_EMITEN_PEMBANDING:
                for n in range(hari + 1):
                    if k + n >= len(idx):
                        break
                    r = (tutup.iloc[k + n][layak] * fj / (o[layak] * fb) - 1).dropna()
                    if len(r) >= MIN_EMITEN_PEMBANDING:
                        isi[f"Acak{n}%"] = round(float(r.mean()) * 100, 2)
        baris.append(isi)
    return pd.DataFrame(baris)


def tambah_pembanding(posisi: pd.DataFrame, banding: pd.DataFrame | None) -> pd.DataFrame:
    """Tempelkan IHSG%, Acak%, dan Selisih% di titik akhir tiap posisi.

    Titik akhirnya sama dengan kolom Laba%: hari ke-HariKe. Jadi Selisih%
    menjawab "sampai hari ini, posisi ini lebih baik atau lebih buruk
    daripada membeli saham acak di sesi yang sama".
    """
    posisi = posisi.copy()
    for kol in ("IHSG%", "Acak%", "Selisih%"):
        posisi[kol] = None
    if banding is None or banding.empty or posisi.empty:
        return posisi
    b = banding.set_index("TanggalBeli")

    def ambil(r, awalan):
        kol = f"{awalan}{int(r.HariKe)}%"
        if r.TanggalBeli not in b.index or kol not in b.columns:
            return None
        v = b.at[r.TanggalBeli, kol]
        return None if pd.isna(v) else float(v)

    posisi["IHSG%"] = [ambil(r, "IHSG") for r in posisi.itertuples()]
    posisi["Acak%"] = [ambil(r, "Acak") for r in posisi.itertuples()]
    posisi["Selisih%"] = [None if a is None else round(float(lb) - a, 2)
                          for lb, a in zip(posisi["Laba%"], posisi["Acak%"])]
    return posisi


def ringkas(posisi: pd.DataFrame, hari: int,
            banding: pd.DataFrame | None = None) -> pd.DataFrame:
    """Winrate dan laba rata-rata untuk tiap hari ke-N.

    Tiap baris hanya menghitung posisi yang benar-benar sudah mencapai hari
    itu, jadi kolom Posisi menyusut ke bawah — hari ke-21 selalu punya sampel
    lebih sedikit daripada hari ke-1. Itu bukan cacat, itu keterangannya:
    winrate dari 12 posisi tidak boleh dibaca sepercaya winrate dari 150.

    Pick ulang (kolom Ulang = Ya) tidak ikut dihitung — lihat simulasi().

    Kalau `banding` diberikan, tiap hari juga mendapat rata-rata IHSG dan
    saham acak atas posisi yang SAMA (dipasangkan lewat TanggalBeli), selisih
    rata-rata posisi terhadap saham acak, dan porsi posisi yang mengalahkan
    saham acak. Dua kolom terakhir itulah yang menjawab apakah daftarnya
    punya kemampuan memilih: tanpa kemampuan itu, Selisih% ≈ 0 dan
    MenangVsAcak% ≈ 50, berapa pun winrate-nya.
    """
    if "Ulang" in posisi.columns:
        posisi = posisi[posisi["Ulang"] != "Ya"]
    b = banding.set_index("TanggalBeli") if banding is not None and not banding.empty else None
    baris = []
    for n in range(hari + 1):
        kol = f"Hari{n}%"
        if kol not in posisi.columns:
            continue
        nilai = posisi[kol].dropna()
        if nilai.empty:
            baris.append({"Hari": n, "Posisi": 0, "Menang": 0, "Winrate%": None,
                          "RataLaba%": None, "MedianLaba%": None, "TotalLabaRp": 0,
                          "Terbaik%": None, "Terburuk%": None,
                          "RataIHSG%": None, "RataAcak%": None, "Selisih%": None,
                          "MenangVsAcak%": None})
            continue
        banding_hari = {"RataIHSG%": None, "RataAcak%": None, "Selisih%": None,
                        "MenangVsAcak%": None}
        if b is not None:
            tgl = posisi.loc[nilai.index, "TanggalBeli"]
            ih = tgl.map(b[f"IHSG{n}%"]) if f"IHSG{n}%" in b.columns else pd.Series(dtype=float)
            ac = tgl.map(b[f"Acak{n}%"]) if f"Acak{n}%" in b.columns else pd.Series(dtype=float)
            ih, ac = pd.to_numeric(ih, errors="coerce"), pd.to_numeric(ac, errors="coerce")
            if ih.notna().any():
                banding_hari["RataIHSG%"] = round(float(ih.mean()), 2)
            pasangan = ac.notna()
            if pasangan.any():
                v, a = nilai[pasangan], ac[pasangan]
                banding_hari["RataAcak%"] = round(float(a.mean()), 2)
                banding_hari["Selisih%"] = round(float((v - a).mean()), 2)
                banding_hari["MenangVsAcak%"] = round(float((v > a).mean()) * 100, 1)
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
            **banding_hari,
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
    p.add_argument("--harga-csv", help="baca harga dari CSV (Ticker,Tanggal,Open,High,Low,Close"
                                       "[,Volume]) alih-alih menarik dari Yahoo")
    p.add_argument("--simpan-harga", help="simpan harga yang ditarik ke CSV ini")
    p.add_argument("--semua", default=BERKAS_SEMUA,
                   help="CSV screening lengkap; tickernya jadi universe saham acak")
    p.add_argument("--tanpa-pembanding", action="store_true",
                   help="lewati IHSG & saham acak (tidak menarik harga universe)")
    p.add_argument("--output", default=BERKAS_HASIL, help="CSV hasil per posisi")
    p.add_argument("--output-ringkas", default=BERKAS_RINGKAS, help="CSV ringkasan per hari")
    p.add_argument("--output-pembanding", default=BERKAS_PEMBANDING,
                   help="CSV pembanding per tanggal beli")
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

    pick = sorted(riwayat["Ticker"].unique())
    universe: set[str] = set()
    if not a.tanpa_pembanding:
        if Path(a.semua).exists():
            universe = set(pd.read_csv(a.semua, usecols=["Ticker"])["Ticker"]
                           .dropna().astype(str).str.strip().str.upper())
        else:
            print(f"  {a.semua} tidak ada — saham acak dilewati, cuma IHSG.", file=sys.stderr)
    # IHSG selalu ikut ditarik, juga dengan --tanpa-pembanding: kalendernya
    # yang dipakai membuang bar hari libur (lihat hari_bursa).
    tickers = sorted(set(pick) | universe) + [KODE_IHSG]
    # Mundur dari pick paling awal: bar pembelian bisa jatuh persis di tanggal
    # pick, dan pembanding butuh MA50 IHSG serta nilai transaksi 20 hari yang
    # sudah terbentuk pada malam pick pertama.
    mulai = date.fromisoformat(riwayat["Tanggal"].min()) - timedelta(
        days=7 if a.tanpa_pembanding else MUNDUR_HARI)

    if a.harga_csv:
        print(f"Membaca harga dari {a.harga_csv} ...", file=sys.stderr)
        harga = pd.read_csv(a.harga_csv, dtype={"Ticker": str, "Tanggal": str})
    else:
        print(f"Menarik harga {len(tickers)} simbol sejak {mulai} ...", file=sys.stderr)
        harga = ambil_harga(tickers, mulai)
        if a.simpan_harga:
            harga.to_csv(a.simpan_harga, index=False)
    if harga.empty:
        print("Tidak ada data harga sama sekali — hasil tidak ditulis.", file=sys.stderr)
        return 1

    bars = selaraskan_kalender(per_emiten(harga))
    posisi = simulasi(riwayat, bars, a.modal, a.hari, a.fee_beli, a.fee_jual)
    if posisi.empty:
        print("Tidak ada posisi yang bisa disimulasikan.", file=sys.stderr)
        return 1
    posisi = posisi.sort_values(["Tanggal", "Ticker"]).reset_index(drop=True)

    banding = None
    if not a.tanpa_pembanding:
        banding = pembanding(list(posisi["TanggalBeli"]), bars, universe,
                             a.hari, a.fee_beli, a.fee_jual)
        tanpa_acak = int(banding["Acak0%"].isna().sum())
        if tanpa_acak:
            print(f"  {tanpa_acak} tanggal beli tanpa pembanding saham acak "
                  f"(kurang dari {MIN_EMITEN_PEMBANDING} emiten likuid ber-harga).",
                  file=sys.stderr)
    posisi = tambah_pembanding(posisi, banding)
    tabel = ringkas(posisi, a.hari, banding)

    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    posisi.to_csv(a.output, index=False)
    tabel.to_csv(a.output_ringkas, index=False)
    if banding is not None:
        banding.to_csv(a.output_pembanding, index=False)
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
        "posisiUlang": int((posisi["Ulang"] == "Ya").sum()),
        "pembanding": None if banding is None else {
            "universe": len(universe),
            "nilaiMin": NILAI_MIN_PEMBANDING,
            "minEmiten": MIN_EMITEN_PEMBANDING,
            "maPasar": MA_PASAR,
        },
    }, indent=2) + "\n")

    # Ringkasan terminal: cukup untuk membaca hasilnya tanpa membuka dashboard.
    # Baris hari dipilih, bukan semuanya: 22 baris angka membuat yang penting
    # (hari pertama, seminggu, sebulan) tenggelam di antara yang tidak dibaca.
    sorot = sorted({0, 1, 2, 3, 5, 10, 15, a.hari})
    ulang = int((posisi["Ulang"] == "Ya").sum())
    print(f"\n{len(posisi) - ulang} posisi (+{ulang} pick ulang tidak dihitung), "
          f"{riwayat['Tanggal'].nunique()} hari screening, "
          f"modal {rupiah(a.modal)}/posisi", file=sys.stderr)
    print(f"{'Hari':>5} {'Posisi':>7} {'Winrate':>8} {'Rata':>8} {'Median':>8} "
          f"{'IHSG':>8} {'Acak':>8} {'Selisih':>8} {'Total':>16}", file=sys.stderr)
    for _, r in tabel.iterrows():
        if r["Hari"] not in sorot:
            continue
        # iterrows menyerahkan baris campur tipe sebagai Series float; angka
        # cacahnya dikembalikan ke int supaya tidak tercetak "146.0".
        print(f"{int(r['Hari']):>5} {int(r['Posisi']):>7} {persen(r['Winrate%'], tanda=False):>8} "
              f"{persen(r['RataLaba%']):>8} {persen(r['MedianLaba%']):>8} "
              f"{persen(r['RataIHSG%']):>8} {persen(r['RataAcak%']):>8} "
              f"{persen(r['Selisih%']):>8} "
              f"{rupiah(r['TotalLabaRp'], tanda=True):>16}", file=sys.stderr)
    disimpan = [a.output, a.output_ringkas, a.output_meta]
    if banding is not None:
        disimpan.insert(2, a.output_pembanding)
    print(f"\nDisimpan: {', '.join(disimpan)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
