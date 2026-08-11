#!/usr/bin/env python3
"""Susun cache fundamental (data/fundamental.csv) dari laporan keuangan Yahoo.

Kenapa skrip ini terpisah dari screener: laporan keuangan hanya berubah empat
kali setahun, sedangkan harga berubah tiap hari. Sebelumnya screener menarik
`.info` tiap malam untuk semua emiten hanya demi ROE dan pertumbuhan — angka
yang sama persis selama tiga bulan. Dengan pemisahan ini, data lapkeu diambil
sekali per kuartal dan disimpan; run malam tinggal membacanya dan cuma perlu
mengambil histori harga.

Efek sampingnya yang lebih penting: karena biaya pengambilan tidak lagi
ditanggung tiap hari, metrik yang mahal jadi terjangkau. `.info` hanya memberi
ROE dan dua angka pertumbuhan; laporan keuangan penuh memberi utang, likuiditas,
margin, arus kas, dan jumlah saham beredar — dasar untuk menilai kesehatan
keuangan dan dilusi, yang selama ini tidak tersentuh sama sekali.

Butuh ~20 menit untuk 400-an emiten (empat request per emiten, dan Yahoo makin
melambat setelah beberapa ratus panggilan berturut-turut). Lama, tapi hanya
perlu dijalankan sekali tiap musim lapkeu — pakai --maks-umur agar run
berikutnya cuma menyentuh emiten yang datanya sudah basi.

Pemakaian:
    python scripts/perbarui_fundamental.py                    # seluruh universe
    python scripts/perbarui_fundamental.py --maks-umur 80     # hanya yang sudah basi
    python scripts/perbarui_fundamental.py --tickers tickers/lq45.txt
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from screener import DAFTAR_DEFAULT, baca_daftar_ticker  # noqa: E402

KOLOM_FUNDAMENTAL = [
    "Ticker", "Nama", "Sektor", "Industri", "Periode", "Basis", "MataUang",
    "Diperbarui",
    # Per lembar — dipakai screener untuk menghitung PER/PBV/Dividen% sendiri
    # dari harga penutupan, bukan mengambilnya jadi dari Yahoo.
    "Saham", "EPS", "BVPS", "DPS",
    # Profitabilitas & kualitas laba
    "Omzet", "LabaBersih", "EBITDA", "EBIT",
    "MarginKotor%", "MarginOperasi%", "MarginBersih%", "ROE%", "ROA%",
    # Kesehatan keuangan
    "TotalUtang", "Kas", "UtangBersih", "TotalAset", "Ekuitas",
    "DER", "UtangBersih/EBITDA", "CurrentRatio", "QuickRatio", "InterestCoverage",
    # Arus kas & alokasi modal
    "OCF", "Capex", "FCF", "OCF/Laba", "Payout%",
    # Pertumbuhan
    "OmzetYoY%", "LabaYoY%", "OmzetCAGR3%", "LabaCAGR3%", "TahunLabaNaik",
    # Dilusi
    "SahamYoY%",
]

# Nama baris laporan keuangan Yahoo tidak seragam antar emiten, jadi tiap
# metrik dicari lewat daftar alias — dipakai yang pertama ketemu.
#
# Yang paling menipu: `Operating Cash Flow` hanya ada di 2 dari 12 emiten IDX
# yang diuji. Sisanya memakai `Cash Flowsfromusedin Operating Activities
# Direct`, karena mayoritas emiten Indonesia menyusun arus kas dengan metode
# langsung. Tanpa alias ini kolom OCF kosong hampir di seluruh bursa.
ALIAS = {
    "omzet":        ["Total Revenue", "Operating Revenue"],
    # "Net Income Common Stockholders" didahulukan, bukan "Net Income": yang
    # dipakai untuk EPS dan ROE harus laba yang jadi hak pemegang saham induk.
    # Pada emiten dengan kepentingan nonpengendali besar, dua angka itu beda,
    # dan memakai yang salah membuat EPS tidak sebanding dengan BVPS yang
    # memang dihitung dari Common Stock Equity.
    "laba":         ["Net Income Common Stockholders", "Net Income",
                     "Net Income Including Noncontrolling Interests"],
    "laba_kotor":   ["Gross Profit"],
    "laba_operasi": ["Operating Income", "Total Operating Income As Reported"],
    "ebitda":       ["EBITDA", "Normalized EBITDA"],
    "ebit":         ["EBIT"],
    "bunga":        ["Interest Expense", "Interest Expense Non Operating"],
    "utang":        ["Total Debt"],
    "kas":          ["Cash And Cash Equivalents",
                     "Cash Cash Equivalents And Short Term Investments"],
    "utang_bersih": ["Net Debt"],
    "aset":         ["Total Assets"],
    "ekuitas":      ["Common Stock Equity", "Stockholders Equity",
                     "Total Equity Gross Minority Interest"],
    "aset_lancar":  ["Current Assets"],
    "utang_lancar": ["Current Liabilities"],
    "persediaan":   ["Inventory"],
    "saham":        ["Ordinary Shares Number", "Share Issued"],
    "capex":        ["Capital Expenditure"],
    "fcf":          ["Free Cash Flow"],
    "ocf":          ["Operating Cash Flow",
                     "Cash Flow From Continuing Operating Activities",
                     "Cash Flowsfromusedin Operating Activities Direct"],
}

# Rentang hari yang dianggap sah antara kuartal terbaru dan kuartal keempat
# dari belakang. Empat kuartal berurutan berjarak ~9 bulan (270 hari); kalau
# jaraknya jauh lebih panjang berarti ada kuartal yang hilang dari data Yahoo
# dan penjumlahannya akan melompati lubang itu.
TTM_MIN_HARI, TTM_MAKS_HARI = 225, 315


_KURS: dict[str, float] = {"IDR": 1.0}


def kurs_ke_idr(mata_uang: str | None) -> float:
    """Kurs satu satuan `mata_uang` ke rupiah, di-cache per mata uang.

    Ini bukan kehalusan akuntansi melainkan syarat agar valuasinya masuk akal.
    Emiten batubara, energi, dan sebagian utilitas IDX menyusun laporan
    keuangan dalam USD sementara sahamnya diperdagangkan dalam rupiah — jadi
    EPS dan harga berasal dari satuan yang berbeda. Tanpa konversi, PER ADRO
    keluar sebagai 146.821 alih-alih 8,3, dan median PER sektor Energy sempat
    terbaca 155.093.

    Kalau kursnya gagal diambil, hasilnya 0.0 supaya pemanggil bisa memilih
    mengosongkan angkanya — lebih baik kolom kosong daripada nilai yang meleset
    empat digit.
    """
    if not mata_uang:
        return 1.0
    kode = mata_uang.upper()
    if kode in _KURS:
        return _KURS[kode]
    import yfinance as yf
    try:
        hist = yf.Ticker(f"{kode}IDR=X").history(period="5d")
        _KURS[kode] = float(hist["Close"].iloc[-1]) if not hist.empty else 0.0
    except Exception as e:
        print(f"      kurs {kode}->IDR gagal: {e}", file=sys.stderr)
        _KURS[kode] = 0.0
    if _KURS[kode]:
        print(f"  Kurs {kode}/IDR = {_KURS[kode]:,.0f}", file=sys.stderr)
    return _KURS[kode]


def _baris(df: pd.DataFrame | None, kunci: str) -> pd.Series | None:
    """Ambil satu baris laporan lewat daftar alias, kolom sudah dibuang NaN-nya."""
    if df is None or df.empty:
        return None
    for nama in ALIAS[kunci]:
        if nama in df.index:
            s = pd.to_numeric(df.loc[nama], errors="coerce").dropna()
            if not s.empty:
                return s
    return None


def _stok(df: pd.DataFrame | None, kunci: str, mundur: int = 0) -> float | None:
    """Nilai neraca pada periode ke-`mundur` dari yang terbaru.

    Pos neraca adalah posisi pada satu tanggal, bukan aliran sepanjang periode,
    jadi diambil apa adanya — tidak dijumlahkan seperti TTM.
    """
    s = _baris(df, kunci)
    if s is None or len(s) <= mundur:
        return None
    return float(s.iloc[mundur])


def _ttm_empat_kuartal(s: pd.Series) -> float | None:
    """Jumlah empat kuartal terakhir, hanya bila keempatnya benar berurutan.

    Angka kuartalan Yahoo untuk emiten IDX sudah diskrit (bukan kumulatif YTD
    seperti di laporan aslinya), jadi penjumlahan memang cara yang benar —
    TLKM: jumlah 4 kuartal = 149,62 T, sama persis dengan TTM Yahoo.

    Yang harus dijaga adalah lubang di tengah. Mengambil "empat baris teratas"
    pada deret berlubang diam-diam menjumlahkan rentang 15 bulan seolah-olah
    12 bulan — hasilnya tampak wajar tapi salah, jadi jarak tanggalnya
    diperiksa dulu.
    """
    if len(s) < 4:
        return None
    empat = s.iloc[:4]
    if not TTM_MIN_HARI <= (empat.index[0] - empat.index[3]).days <= TTM_MAKS_HARI:
        return None
    return float(empat.sum())


def _ttm_bergulir(s: pd.Series, tahunan: pd.Series | None) -> float | None:
    """TTM = tahun buku terakhir + YTD tahun ini - YTD periode sama tahun lalu.

    Ini jalan keluar untuk lubang kuartal, dan lubangnya bukan kasus pinggiran:
    bar September 2025 hilang di hampir semua emiten IDX yang diuji. Kalau
    hanya mengandalkan empat kuartal berurutan, nyaris seluruh bursa terpaksa
    memakai laporan tahunan yang bisa delapan bulan basi — dua kuartal terakhir
    yang justru paling ingin dilihat malah terbuang.

    Rumus ini kebal terhadap lubang di tengah karena bagian yang berlubang
    sudah termasuk di dalam angka tahunan yang diaudit. Yang perlu ada hanya
    kuartal-kuartal setelah tutup buku dan padanannya setahun sebelumnya.
    """
    if tahunan is None or tahunan.empty:
        return None
    akhir_buku = tahunan.index[0]
    berjalan = s[s.index > akhir_buku]
    if berjalan.empty:
        # Tutup buku adalah periode terbaru: angka tahunannya sudah TTM.
        return float(tahunan.iloc[0])

    pembanding = []
    for tanggal in berjalan.index:
        setahun_lalu = tanggal - pd.DateOffset(years=1)
        cocok = [d for d in s.index if abs((d - setahun_lalu).days) <= 10]
        if not cocok:
            return None
        pembanding.append(float(s.loc[cocok[0]]))
    return float(tahunan.iloc[0]) + float(berjalan.sum()) - sum(pembanding)


def _arus(kuartal: pd.DataFrame | None, tahunan: pd.DataFrame | None,
          kunci: str) -> tuple[float | None, str | None]:
    """Nilai aliran (laba, omzet, arus kas) beserta cara ia dihitung.

    Diurut dari yang paling segar ke yang paling aman; metode yang dipakai
    ikut dikembalikan supaya bisa dicatat di kolom Basis — tabel yang diam-diam
    mencampur TTM dan angka tahunan lebih berbahaya daripada tabel yang basi
    tapi jujur.
    """
    s = _baris(kuartal, kunci)
    st = _baris(tahunan, kunci)

    if s is not None:
        nilai = _ttm_empat_kuartal(s)
        if nilai is not None:
            return nilai, "TTM"
        nilai = _ttm_bergulir(s, st)
        if nilai is not None:
            return nilai, "TTM-gabungan"
    if st is not None:
        return float(st.iloc[0]), "Tahunan"
    return None, None


def _bagi(a: float | None, b: float | None, kali: float = 1.0,
          desimal: int = 2) -> float | None:
    """Bagi dua angka dengan aman; None bila salah satu kosong atau penyebut nol."""
    if a is None or b is None or b == 0:
        return None
    return round(a / b * kali, desimal)


def _rerata(kini: float | None, lalu: float | None) -> float | None:
    """Rata-rata posisi awal dan akhir periode; jatuh ke posisi akhir bila
    data setahun lalu tidak ada."""
    if kini is None:
        return None
    return (kini + lalu) / 2 if lalu is not None else kini


def _cagr(awal: float | None, akhir: float | None, tahun: int) -> float | None:
    """CAGR dalam persen. None bila titik awalnya nol atau negatif.

    Pertumbuhan majemuk dari basis negatif tidak punya arti — perusahaan yang
    rugi 100 lalu untung 50 tidak "tumbuh sekian persen per tahun". Kasus itu
    dibiarkan kosong, bukan dipaksa jadi angka.
    """
    if awal is None or akhir is None or awal <= 0 or tahun <= 0:
        return None
    if akhir <= 0:
        return None
    return round(((akhir / awal) ** (1 / tahun) - 1) * 100, 1)


def _yoy(s: pd.Series | None) -> float | None:
    """Pertumbuhan periode terakhir dibanding periode yang sama setahun lalu.

    Pembagi dipakai nilai mutlaknya supaya pembalikan dari rugi ke untung
    keluar sebagai angka positif, bukan negatif akibat penyebut minus.
    """
    if s is None or len(s) < 5:
        return None
    kini, lalu = float(s.iloc[0]), float(s.iloc[4])
    if lalu == 0:
        return None
    return round((kini - lalu) / abs(lalu) * 100, 1)


def _tahun_laba_naik(tahunan: pd.DataFrame | None) -> int | None:
    """Berapa dari 3 tahun terakhir labanya naik dibanding tahun sebelumnya.

    Ini ukuran konsistensi, bukan besaran: laba yang naik 8% tiga tahun
    berturut-turut lebih bisa dipercaya daripada yang melonjak 200% sekali
    lalu anjlok dua kali.
    """
    s = _baris(tahunan, "laba")
    if s is None or len(s) < 2:
        return None
    pasang = list(zip(s.iloc[:-1], s.iloc[1:]))[:3]
    return sum(1 for kini, lalu in pasang if float(kini) > float(lalu))


def hitung_fundamental(tkr: str, info: dict, q, b, c, a, ab, ac) -> dict:
    """Rangkum laporan keuangan satu emiten jadi satu baris cache.

    q/b/c = laporan kuartalan (laba rugi, neraca, arus kas), a/ab/ac = tahunan.
    Rasio yang tidak berlaku untuk sebuah emiten dibiarkan kosong, bukan
    diisi nol: bank tidak memisahkan aset lancar dan tidak melaporkan gross
    profit maupun EBITDA, jadi current ratio dan Net Debt/EBITDA-nya memang
    tidak ada — bukan data yang gagal diambil.
    """
    omzet, _ = _arus(q, a, "omzet")
    laba, basis = _arus(q, a, "laba")
    laba_kotor, _ = _arus(q, a, "laba_kotor")
    laba_operasi, _ = _arus(q, a, "laba_operasi")
    ebitda, _ = _arus(q, a, "ebitda")
    ebit, _ = _arus(q, a, "ebit")
    bunga, _ = _arus(q, a, "bunga")
    ocf, _ = _arus(c, ac, "ocf")
    capex, _ = _arus(c, ac, "capex")
    fcf, _ = _arus(c, ac, "fcf")
    # Capex dari Yahoo bertanda negatif (arus kas keluar). FCF dihitung sendiri
    # bila barisnya tidak ada, memakai penjumlahan supaya tandanya konsisten.
    if fcf is None and ocf is not None and capex is not None:
        fcf = ocf + capex

    ekuitas = _stok(b, "ekuitas") or _stok(ab, "ekuitas")
    ekuitas_lalu = _stok(b, "ekuitas", 4) or _stok(ab, "ekuitas", 1)
    aset = _stok(b, "aset") or _stok(ab, "aset")
    aset_lalu = _stok(b, "aset", 4) or _stok(ab, "aset", 1)
    utang = _stok(b, "utang") or _stok(ab, "utang")
    kas = _stok(b, "kas") or _stok(ab, "kas")
    utang_bersih = _stok(b, "utang_bersih")
    # Net Debt hilang justru pada emiten yang kasnya lebih besar dari utangnya
    # (ANTM, CTRA, GOTO) — Yahoo tidak menuliskan angka negatif. Dihitung
    # sendiri supaya posisi net cash tetap terekam, bukan jadi kolom kosong.
    if utang_bersih is None and utang is not None and kas is not None:
        utang_bersih = utang - kas
    aset_lancar = _stok(b, "aset_lancar") or _stok(ab, "aset_lancar")
    utang_lancar = _stok(b, "utang_lancar") or _stok(ab, "utang_lancar")
    persediaan = _stok(b, "persediaan") or _stok(ab, "persediaan") or 0.0
    saham = _stok(b, "saham") or _stok(ab, "saham") or info.get("sharesOutstanding")
    saham_lalu = _stok(b, "saham", 4) or _stok(ab, "saham", 1)

    # Ekuitas dan aset dipakai rata-rata awal-akhir periode, bukan posisi akhir
    # saja, karena labanya dihasilkan sepanjang periode itu. Keduanya harus
    # diperlakukan sama: memakai ekuitas rata-rata tapi aset akhir sempat
    # menghasilkan ROA SIDO (37,7) lebih besar dari ROE-nya (36,7) — mustahil
    # untuk perusahaan yang punya utang, dan murni artefak beda penyebut.
    ekuitas_roe = _rerata(ekuitas, ekuitas_lalu)
    aset_roa = _rerata(aset, aset_lalu)

    baris_q = _baris(q, "omzet")
    baris_laba_q = _baris(q, "laba")
    periode = baris_q.index[0].date().isoformat() if baris_q is not None else None

    # Semua angka rupiah dan per-lembar dikonversi ke IDR; rasio tidak perlu
    # disentuh karena pembilang dan penyebutnya sama-sama ikut terskala.
    mata_uang = (info.get("financialCurrency") or "IDR").upper()
    kurs = kurs_ke_idr(mata_uang)

    def idr(nilai: float | None) -> float | None:
        if nilai is None or not kurs:
            return None
        return nilai * kurs

    return {
        "Ticker": tkr.removesuffix(".JK"),
        "Nama": (info.get("shortName") or "")[:28],
        "Sektor": info.get("sector") or "",
        "Industri": info.get("industry") or "",
        "Periode": periode,
        # Cara angka labanya didapat: "TTM" (4 kuartal berurutan),
        # "TTM-gabungan" (tahunan + YTD - YTD), atau "Tahunan" (basi, tapi
        # benar). Tanpa penanda ini tabelnya diam-diam mencampur tiga basis
        # sementara kolom Periode tetap menampilkan tanggal kuartal terbaru,
        # sehingga yang basi tidak kelihatan basi.
        "Basis": basis,
        "MataUang": mata_uang,
        "Diperbarui": date.today().isoformat(),

        "Saham": saham,
        # Empat desimal, bukan dua: banyak emiten IDX berharga puluhan rupiah
        # dengan EPS di bawah satu rupiah. Pembulatan dua desimal membuat EPS
        # GOTO jatuh ke 0,00 dan PER-nya ikut hilang — bukan karena datanya
        # tidak ada, melainkan karena dibulatkan habis.
        "EPS": _bagi(idr(laba), saham, desimal=4),
        "BVPS": _bagi(idr(ekuitas), saham, desimal=4),
        # dividendRate sudah dalam mata uang perdagangan (rupiah), bukan mata
        # uang laporan, jadi justru tidak boleh ikut dikonversi. Ini yield per
        # lembar setahun — screener yang mengubahnya jadi persen memakai harga
        # penutupan malam itu.
        "DPS": info.get("dividendRate"),

        "Omzet": idr(omzet),
        "LabaBersih": idr(laba),
        "EBITDA": idr(ebitda),
        "EBIT": idr(ebit),
        "MarginKotor%": _bagi(laba_kotor, omzet, 100),
        "MarginOperasi%": _bagi(laba_operasi, omzet, 100),
        "MarginBersih%": _bagi(laba, omzet, 100),
        "ROE%": _bagi(laba, ekuitas_roe, 100),
        "ROA%": _bagi(laba, aset_roa, 100),

        "TotalUtang": idr(utang),
        "Kas": idr(kas),
        "UtangBersih": idr(utang_bersih),
        "TotalAset": idr(aset),
        "Ekuitas": idr(ekuitas),
        "DER": _bagi(utang, ekuitas),
        # Hanya bermakna bila EBITDA positif. Pada emiten yang EBITDA-nya minus,
        # penyebut negatif membuat utang besar tampak sebagai rasio kecil —
        # WIKA (EBITDA -8,3 T, utang bersih 31,7 T) akan keluar sebagai -3,8,
        # angka yang terbaca sehat padahal artinya perusahaan tidak
        # menghasilkan kas sama sekali untuk membayarnya. Nilai negatif yang
        # tersisa di kolom ini berarti net cash, bukan sekadar utang rendah.
        "UtangBersih/EBITDA": _bagi(utang_bersih, ebitda) if (ebitda or 0) > 0 else None,
        "CurrentRatio": _bagi(aset_lancar, utang_lancar),
        "QuickRatio": _bagi(
            aset_lancar - persediaan if aset_lancar is not None else None,
            utang_lancar),
        # Interest Expense dari Yahoo bertanda positif (besaran beban), jadi
        # rasionya tidak perlu dibalik tandanya.
        "InterestCoverage": _bagi(ebit, bunga),

        "OCF": idr(ocf),
        "Capex": idr(capex),
        "FCF": idr(fcf),
        # Inti uji kualitas laba: laba akuntansi yang tidak diikuti kas masuk
        # adalah laba di atas kertas.
        "OCF/Laba": _bagi(ocf, laba),
        "Payout%": _bagi(info.get("payoutRatio"), 1, 100),

        "OmzetYoY%": _yoy(baris_q),
        "LabaYoY%": _yoy(baris_laba_q),
        "OmzetCAGR3%": _cagr(_nilai_tahun(a, "omzet", 3), _nilai_tahun(a, "omzet", 0), 3),
        "LabaCAGR3%": _cagr(_nilai_tahun(a, "laba", 3), _nilai_tahun(a, "laba", 0), 3),
        "TahunLabaNaik": _tahun_laba_naik(a),

        # Positif = jumlah saham bertambah = pemegang saham lama terdilusi.
        "SahamYoY%": _bagi(
            saham - saham_lalu if saham is not None and saham_lalu is not None else None,
            saham_lalu, 100),
    }


def _nilai_tahun(tahunan: pd.DataFrame | None, kunci: str, mundur: int) -> float | None:
    s = _baris(tahunan, kunci)
    if s is None or len(s) <= mundur:
        return None
    return float(s.iloc[mundur])


def ambil_fundamental(tickers: list[str], lama: pd.DataFrame,
                      maks_umur: int) -> pd.DataFrame:
    """Ambil lapkeu tiap emiten; baris lama dipertahankan bila masih segar/gagal."""
    import yfinance as yf

    peta_lama = ({r["Ticker"]: r for _, r in lama.iterrows()}
                 if not lama.empty else {})
    hari_ini = date.today()
    baris, dilewati, gagal = [], 0, 0

    for i, tkr in enumerate(tickers, 1):
        kode = tkr.removesuffix(".JK")
        sebelumnya = peta_lama.get(kode)

        if maks_umur > 0 and sebelumnya is not None:
            stempel = str(sebelumnya.get("Diperbarui") or "")
            try:
                umur = (hari_ini - datetime.fromisoformat(stempel).date()).days
            except ValueError:
                umur = None
            if umur is not None and umur < maks_umur:
                baris.append(sebelumnya.to_dict())
                dilewati += 1
                continue

        print(f"  [{i}/{len(tickers)}] {tkr} ...", file=sys.stderr)
        try:
            s = yf.Ticker(tkr)
            data = hitung_fundamental(
                tkr, s.info or {},
                s.quarterly_financials, s.quarterly_balance_sheet, s.quarterly_cashflow,
                s.financials, s.balance_sheet, s.cashflow)
            # Yang menentukan baris lama dipertahankan adalah ada-tidaknya isi,
            # bukan ada-tidaknya kolom Periode. Emiten yang baru IPO sering
            # hanya punya laporan tahunan sehingga Periode-nya kosong padahal
            # EPS dan ekuitasnya terbaca — baris seperti itu tetap berguna dan
            # tidak boleh dibuang demi baris lama yang lebih tua.
            kosong = all(data[k] is None for k in ("Periode", "EPS", "Ekuitas"))
            if kosong and sebelumnya is not None:
                print("      laporan kosong — baris lama dipertahankan", file=sys.stderr)
                baris.append(sebelumnya.to_dict())
                gagal += 1
                continue
            baris.append(data)
        except Exception as e:
            print(f"      gagal: {type(e).__name__}: {e}", file=sys.stderr)
            gagal += 1
            if sebelumnya is not None:
                baris.append(sebelumnya.to_dict())

    print(f"\n{len(baris)} emiten di cache "
          f"({dilewati} dilewati karena masih segar, {gagal} gagal/kosong).",
          file=sys.stderr)
    return pd.DataFrame(baris, columns=KOLOM_FUNDAMENTAL)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Perbarui cache fundamental dari laporan keuangan Yahoo Finance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--tickers", nargs="+", default=DAFTAR_DEFAULT, metavar="FILE",
                   help="satu atau lebih file daftar ticker")
    p.add_argument("--output", default="data/fundamental.csv",
                   help="file CSV cache fundamental")
    p.add_argument("--maks-umur", type=int, default=0, metavar="HARI",
                   help="lewati emiten yang barisnya lebih baru dari ini "
                        "(0 = ambil ulang semua; 80 cocok untuk run bulanan)")
    args = p.parse_args()

    tickers, _ = baca_daftar_ticker(args.tickers)
    if not tickers:
        print("Tidak ada ticker untuk diproses.", file=sys.stderr)
        return 1

    path = Path(args.output)
    lama = pd.read_csv(path) if path.exists() else pd.DataFrame()

    print(f"Mengambil laporan keuangan {len(tickers)} emiten ...", file=sys.stderr)
    df = ambil_fundamental(tickers, lama, args.maks_umur)

    if df.empty:
        print("Tidak ada data yang berhasil diambil — cache lama dipertahankan.",
              file=sys.stderr)
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    terisi = df["Periode"].notna().sum()
    print(f"Disimpan ke {path} ({terisi}/{len(df)} punya periode lapkeu).",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
