#!/usr/bin/env python3
"""Analisa struktur SMC untuk kandidat hasil screening.

Screener menjawab "saham apa" — fundamental, RSI, MA, volume. Skrip ini
menjawab lanjutannya: "masuk di harga berapa, batal di harga berapa". Ia
membaca daftar kandidat (default `hasil/swing.csv`), menarik bar harian dan
per jam dari Yahoo, lalu menjalankan mesin di `smc.py` untuk tiga timeframe:
D1, SESI (satu bar per sesi bursa — pengganti H4 untuk IDX), dan H1.

Contoh pemakaian:
    python analisa_smc.py                                   # dari hasil/swing.csv
    python analisa_smc.py --detail                          # + laporan panjang per emiten
    python analisa_smc.py --ticker BBCA TLKM                # ad-hoc, tanpa CSV
    python analisa_smc.py --dari-csv hasil/value.csv --output hasil/value_smc.csv

Hasil disimpan ke `hasil/swing_smc.csv` dan diringkas sebagai tabel.

Angka yang keluar adalah pembacaan teknikal, bukan saran investasi.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

import smc

WIB = timezone(timedelta(hours=7))

# Sesi IDX tutup 15:50 WIB; Yahoo masih merapikan bar terakhir beberapa menit
# setelahnya. Angka ini disamakan dengan JAM_DATA_FINAL di screener.py supaya
# kedua tabel selalu mengacu ke titik waktu yang sama — kalau tidak, kolom
# Harga di swing.csv dan level entri di sini bisa berasal dari hari berbeda.
JAM_DATA_FINAL = time(16, 15)

# Batas bar per timeframe. Sama dengan BARS di fetch-data.mjs supaya hasilnya
# sebanding dengan jalur TradingView.
MAKS_BAR = 500

# Hanya dua kali tarik ke Yahoo. Bar per sesi diturunkan dari bar 1 jam, jadi
# tidak perlu request sendiri.
SUMBER = (("D1", "2y", "1d"), ("H1", "2y", "1h"))

# Timeframe yang dianalisa. M15 sengaja tidak ada: untuk horizon swing saham,
# bar 15 menit isinya hampir seluruhnya noise mikro dan zona yang lahir dari
# situ terlalu tipis untuk jadi dasar order.
#
# "SESI" adalah pengganti H4 untuk IDX. Bucket 4 jam kalender tidak punya arti
# di sini: hari bursa cuma 6,5 jam dan terpotong jeda makan siang, jadi tiap
# bucket akan mencampur potongan sesi pagi dengan sesi siang, atau menempel ke
# gap semalam. Yang alami adalah sesi bursa itu sendiri — data Yahoo memang
# jatuh persis di dua kelompok, 09-11 dan 13-16 (jam 12 nyaris selalu kosong),
# jadi satu hari = tepat dua bar.
#
# k = kekuatan fractal; timeframe rendah butuh k lebih besar supaya noise
# tersaring, mengikuti tuning yang dipakai smc.mjs.
#
# `intraday` menyalakan penolakan gap antar-sesi di fvg(). Hanya H1 yang
# butuh: di sana gap semalam jauh lebih besar dari gerak antar-jam, jadi tanpa
# filter ia mendominasi. Untuk D1 dan SESI justru harus mati — bar berurutan
# di sana MEMANG selalu terpisah jeda bursa, dan lompatannya adalah sinyalnya.
TIMEFRAME = [
    {"nama": "D1", "dari": "D1", "k": 3, "intraday": False},
    {"nama": "SESI", "dari": "H1", "k": 3, "intraday": False},
    {"nama": "H1", "dari": "H1", "k": 4, "intraday": True},
]

# Timeframe yang boleh menyumbang zona entri. Stop dan target selalu dari D1,
# jadi zona pun harus cukup tebal untuk dipasangkan ke sana; H1 dipakai sebagai
# konteks tren saja. Tambahkan "H1" di sini kalau ingin zona yang lebih rapat.
TF_ENTRI = ("D1", "SESI")

# Di bawah ini struktur tidak bisa dibaca dengan jujur: pivot fractal butuh
# k bar di kiri dan kanan, dan dealing range butuh cukup banyak pivot.
MIN_BAR = 60

# --------------------------------------------------------------- batas jarak
# Tanpa batas jarak, seluruh rencana jadi omong kosong meski tiap levelnya
# benar secara struktur. Contoh nyata dari run pertama skrip ini (2 Sep 2026):
# target OASA jatuh 81% di atas harga dan IATA 61%, karena equal-high terdekat
# di atas harga berasal dari puncak 1-2 tahun lalu; sebaliknya target SMSM cuma
# 0,87% dan INDF 1,05% karena kebetulan ada EQH persis di atas harga. RR yang
# lahir dari situ (10,6 dan 0,65) tidak mengukur apa pun.
#
# Batasnya dipasang ganda — kelipatan ATR DAN persentase harga — karena
# sendirian keduanya pincang. Murni ATR gagal di saham bergejolak: IATA ber-ATR
# harian 9,2%, jadi "8x ATR" berarti target 74%. Murni persentase gagal di
# saham tenang: SMSM ber-ATR 1,0%, target 25% berarti 25 hari perdagangan
# searah tanpa jeda. Yang dipakai selalu yang lebih ketat dari keduanya.
MAKS_ENTRI_ATR, MAKS_ENTRI_PCT = 3.0, 8.0      # pullback masih masuk akal ditunggu
MIN_TARGET_ATR, MIN_TARGET_PCT = 1.0, 3.0      # di bawah ini bukan target, cuma noise
MAKS_TARGET_ATR, MAKS_TARGET_PCT = 8.0, 25.0   # di atas ini bukan swing lagi
MAKS_RISIKO_ATR, MAKS_RISIKO_PCT = 4.0, 15.0   # stop lebih lebar dari ini tidak tertanggung

# Stop yang lebih rapat dari satu ATR berada di dalam gerak harian biasa: ia
# akan kena oleh naik-turun rutin, bukan karena rencananya salah. Run pertama
# memberi AKRA RR 6,85 justru karena stop strukturalnya kebetulan cuma 2,5% di
# bawah entri sementara ATR hariannya 2,6% — RR besar yang lahir dari stop yang
# hampir pasti tersentuh. Kalau stop struktural lebih rapat dari ini, yang
# dipakai adalah lantai ATR: risiko melebar, RR mengecil, tidak sebaliknya.
MIN_RISIKO_ATR = 1.0

# Zona entri yang lebih tinggi dari ini bukan level, tapi wilayah. FVG D1 BDMN
# pada run pertama terentang 3110-4070 — 22% dari harga; "entri di zona itu"
# tidak berarti apa-apa karena hasilnya beda jauh tergantung di mana persisnya
# kena.
MAKS_LEBAR_ZONA_ATR = 1.5

# FVG yang lebih tipis dari ini bukan imbalance yang berarti, cuma selisih
# beberapa fraksi harga antara dua bar. Versi JS menyaringnya dengan 0,4% dari
# lebar dealing range; ATR dipakai di sini karena lebih langsung mengukur
# "gerakan sehari yang wajar" untuk saham yang bersangkutan.
MIN_FVG_ATR = 0.3

KOLOM = [
    "Ticker", "Nama", "Skor", "StatusScreener", "Harga",
    "TrenD1", "ZonaD1", "PosisiD1%", "EventD1", "TrenSesi", "TrenH1",
    "TipeEntri", "EntriAtas", "EntriBawah", "Stop", "Target", "RR",
    "JarakEntri%", "ATR_D1%", "SweepTerakhir", "Sinyal", "Catatan",
]


# ---------------------------------------------------------------- pengambilan data
def bar_intraday_belum_final(idx_terakhir) -> bool:
    """True bila bar intraday terakhir masih dari sesi hari ini yang berjalan.

    Alasannya sama dengan `bar_terakhir_belum_final` di screener.py: bar yang
    belum tuntas isinya baru sebagian. Bedanya di sini yang rusak bukan volume
    melainkan struktur — high/low bar berjalan bisa berubah beberapa kali
    sampai sesi tutup, dan pivot yang lahir dari bar itu ikut berubah-ubah.
    """
    sekarang = datetime.now(WIB)
    return (idx_terakhir.date() == sekarang.date()
            and sekarang.time() < JAM_DATA_FINAL)


def tarik(tkr: str, period: str, interval: str) -> list[dict]:
    """Tarik satu interval dari Yahoo, kembalikan sebagai list bar untuk smc.py."""
    import yfinance as yf

    hist = yf.Ticker(tkr).history(period=period, interval=interval)
    if hist.empty:
        return []

    # Yahoo sesekali mengirim bar tanpa harga (lihat catatan panjang di
    # screener.py soal run 27-31 Agu 2026). Baris cacat dibuang lebih dulu,
    # bukan dibiarkan meledak di tengah hitungan dan menghanguskan sahamnya.
    hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
    if hist.empty:
        return []

    if bar_intraday_belum_final(hist.index[-1]):
        hist = hist.iloc[:-1]

    return [
        {"waktu": t.to_pydatetime(), "open": float(r.Open), "high": float(r.High),
         "low": float(r.Low), "close": float(r.Close)}
        for t, r in zip(hist.index, hist.itertuples())
    ]


def ke_sesi(bars: list[dict]) -> list[dict]:
    """Gabungkan bar 1 jam menjadi satu bar per sesi bursa.

    Sesi 1 = jam 09-11, sesi 2 = jam 13-16 (termasuk bar lelang penutupan
    16:00). Batasnya dipasang di jam 12 karena jeda makan siang membuat jam itu
    nyaris selalu kosong — dari 3.168 bar BBCA selama dua tahun, hanya 3 yang
    jatuh di jam 12.
    """
    out: list[dict] = []
    kunci_kini = None
    kini: dict | None = None
    for b in bars:
        kunci = (b["waktu"].date(), 1 if b["waktu"].hour < 12 else 2)
        if kunci != kunci_kini:
            if kini:
                out.append(kini)
            kini = dict(b)
            kunci_kini = kunci
        else:
            kini["high"] = max(kini["high"], b["high"])
            kini["low"] = min(kini["low"], b["low"])
            kini["close"] = b["close"]
    if kini:
        out.append(kini)
    return out


def ambil_semua(tkr: str) -> dict[str, list[dict]]:
    """Semua timeframe untuk satu emiten, dari dua kali tarik ke Yahoo."""
    mentah = {nama: tarik(tkr, period, interval) for nama, period, interval in SUMBER}
    return {
        tf["nama"]: (ke_sesi(mentah[tf["dari"]]) if tf["nama"] == "SESI"
                     else mentah[tf["dari"]])[-MAKS_BAR:]
        for tf in TIMEFRAME
    }


# ---------------------------------------------------------------- analisa satu TF
def analisa_tf(bars: list[dict], k: int, intraday: bool) -> dict | None:
    """Jalankan seluruh mesin SMC untuk satu timeframe."""
    if len(bars) < MIN_BAR:
        return None
    last = bars[-1]["close"]
    st = smc.struktur(bars, k)
    pd_ = smc.premium_diskon(st["pivot"], last)
    return {
        "bars": bars,
        "last": last,
        "tren": st["tren"],
        "pivot": st["pivot"],
        "label": smc.label_pivot(st["pivot"]),
        "events": st["events"],
        "fvg": smc.fvg(bars, intraday=intraday),
        "ob": smc.order_block(bars, st["events"]),
        "likuiditas": smc.likuiditas(st["pivot"]),
        "sweep": smc.sweep(bars, st["pivot"]),
        "pd": pd_,
        "atr": smc.atr(bars),
    }


# ---------------------------------------------------------------- rencana entri
def batas(atr: float, harga: float, n_atr: float, pct: float) -> float:
    """Jarak dalam rupiah, diambil dari yang lebih ketat antara kelipatan ATR dan % harga."""
    return min(n_atr * atr, pct / 100 * harga)


def zona_entri(hasil: dict[str, dict], harga: float, atr: float) -> dict | None:
    """Zona beli terdekat di bawah harga: OB fresh atau FVG bullish yang masih terbuka.

    Dikumpulkan dari D1 dan H1 sekaligus lalu diambil yang paling dekat ke
    harga, tapi hanya yang masih dalam jangkauan pullback yang wajar ditunggu.
    Timeframe mana saja yang boleh menyumbang diatur lewat TF_ENTRI.
    """
    terjauh = harga - batas(atr, harga, MAKS_ENTRI_ATR, MAKS_ENTRI_PCT)
    maks_lebar = MAKS_LEBAR_ZONA_ATR * atr

    def layak(atas, bawah):
        return terjauh <= atas < harga and (atas - bawah) <= maks_lebar

    kandidat = []
    for tf in TF_ENTRI:
        h = hasil.get(tf)
        if not h:
            continue
        for ob in h["ob"]:
            if ob["arah"] == "bull" and not ob["dimitigasi"] and layak(ob["atas"], ob["bawah"]):
                kandidat.append({"tipe": f"OB {tf}", "atas": ob["atas"], "bawah": ob["bawah"]})
        for g in h["fvg"]:
            if (g["arah"] == "bull" and g["terisi"] < 0.5
                    and g["ukuran"] >= MIN_FVG_ATR * atr
                    and layak(g["atas"], g["bawah"])):
                kandidat.append({"tipe": f"FVG {tf}", "atas": g["atas"], "bawah": g["bawah"]})
    if not kandidat:
        return None
    return max(kandidat, key=lambda z: z["atas"])


def susun_rencana(hasil: dict[str, dict], harga: float) -> dict:
    """Rangkai zona entri, stop, dan target jadi satu rencana dengan risk/reward."""
    r = {"tipe": "", "atas": None, "bawah": None, "stop": None,
         "target": None, "rr": None, "jarak": None, "tolak": ""}

    d1 = hasil.get("D1")
    if not d1:
        return r
    atr = d1["atr"]

    z = zona_entri(hasil, harga, atr)
    if not z:
        r["tolak"] = "tidak ada OB fresh / FVG terbuka dalam jangkauan pullback"
        return r
    r["tipe"] = z["tipe"]
    r["atas"] = smc.bulatkan(z["atas"], -1)
    r["bawah"] = smc.bulatkan(z["bawah"], -1)
    r["jarak"] = (harga - z["atas"]) / harga * 100
    tengah = (r["atas"] + r["bawah"]) / 2

    # Stop di bawah HL terakhir yang masih di bawah zona entri: kalau harga
    # menembus itu, alasan strukturalnya hilang dan rencananya batal — bukan
    # sekadar rugi sekian persen. Stop tidak pernah digeser mendekat supaya
    # RR-nya enak dilihat; kalau kelewat lebar, rencananya yang ditolak.
    hl = [s for s in d1["label"] if s["tipe"] == "L" and s["harga"] < z["bawah"]]
    dasar = hl[-1]["harga"] if hl else (d1["pd"]["bawah"] if d1["pd"] else None)
    if dasar is None:
        r["tolak"] = "tidak ada HL di bawah zona untuk jadi invalidasi"
        return r
    # Lantai ATR dipasang di sini: mana pun yang lebih rendah antara stop
    # struktural dan "satu ATR di bawah tengah zona" yang dipakai.
    r["stop"] = smc.bulatkan(min(dasar, tengah - MIN_RISIKO_ATR * atr), -1)
    risiko = tengah - r["stop"]
    if risiko <= 0:
        r["tolak"] = "stop tidak berada di bawah zona entri"
        return r
    if risiko > batas(atr, harga, MAKS_RISIKO_ATR, MAKS_RISIKO_PCT):
        r["tolak"] = f"stop struktural terlalu lebar ({risiko / harga * 100:.0f}% dari harga)"
        return r

    # Target = kolam likuiditas (equal highs) terdekat di atas harga; di situ
    # stop order menumpuk sehingga harga cenderung ditarik ke sana. Yang
    # dipakai hanya level dalam pita jarak yang masuk akal — yang terlalu
    # rapat bukan target, yang terlalu jauh bukan swing. Atap dealing range
    # jadi cadangan kalau tidak ada EQH yang lolos.
    dekat = harga + max(MIN_TARGET_ATR * atr, MIN_TARGET_PCT / 100 * harga)
    jauh = harga + batas(atr, harga, MAKS_TARGET_ATR, MAKS_TARGET_PCT)
    puncak = sorted(x["level"] for x in d1["likuiditas"]["eqh"] if dekat <= x["level"] <= jauh)
    if puncak:
        r["target"] = smc.bulatkan(puncak[0], -1)
    elif d1["pd"] and dekat <= d1["pd"]["atas"] <= jauh:
        r["target"] = smc.bulatkan(d1["pd"]["atas"], -1)
    else:
        r["tolak"] = "tidak ada likuiditas di atas harga dalam jangkauan target"
        return r

    r["rr"] = round((r["target"] - tengah) / risiko, 2)
    return r


def baca_sinyal(hasil: dict[str, dict], rencana: dict) -> tuple[str, str]:
    """Terjemahkan struktur + rencana jadi satu label, plus alasannya."""
    d1 = hasil.get("D1")
    if not d1:
        return "DATA KURANG", "bar harian tidak cukup untuk membaca struktur"
    if d1["tren"] == "down":
        return "HINDARI", "struktur D1 masih bearish"
    if rencana["rr"] is None:
        return "TUNGGU", rencana["tolak"] or "rencana tidak lengkap"
    zona = d1["pd"]["zona"] if d1["pd"] else ""
    if zona == "PREMIUM":
        return "TUNGGU", "harga di premium — tunggu pullback ke zona"
    if rencana["rr"] >= 2:
        return "SIAP", f"zona {rencana['tipe']} aktif, RR {rencana['rr']}"
    return "PANTAU", f"RR baru {rencana['rr']} — di bawah 2"


# ---------------------------------------------------------------- laporan panjang
def cetak_detail(kode: str, hasil: dict[str, dict]) -> None:
    print(f"\n{'=' * 62}\n{kode}\n{'=' * 62}")
    for nama in [tf["nama"] for tf in TIMEFRAME]:
        h = hasil.get(nama)
        print(f"\n---------------- {nama} ----------------")
        if not h:
            print("  DILEWATI: bar tidak cukup")
            continue
        b = h["bars"]
        print(f"  {len(b)} bar  {b[0]['waktu']:%Y-%m-%d %H:%M} -> {b[-1]['waktu']:%Y-%m-%d %H:%M}")
        atr_pct = h["atr"] / h["last"] * 100
        print(f"  close {h['last']:.0f}   ATR14 {h['atr']:.1f} ({atr_pct:.1f}%)   tren {h['tren']}")

        if h["pd"]:
            p = h["pd"]
            print(f"\n  DEALING RANGE  {p['bawah']:.0f} | {p['tengah']:.0f} | {p['atas']:.0f}"
                  f"  -> harga di {p['pct'] * 100:.0f}% = {p['zona']}")

        print("\n  EVENT STRUKTUR (4 terakhir)")
        for e in h["events"][-4:]:
            print(f"    {e['jenis']:<5} {e['arah']:<4} @ {smc.bulatkan(e['level']):.0f}"
                  f"   {e['waktu']:%Y-%m-%d %H:%M}")

        print("\n  URUTAN PIVOT (6 terakhir)")
        for s in h["label"][-6:]:
            print(f"    {s['label']:<3} {smc.bulatkan(s['harga']):.0f}   {s['waktu']:%Y-%m-%d %H:%M}")

        segar = [o for o in h["ob"] if not o["dimitigasi"]]
        print(f"\n  ORDER BLOCK FRESH ({len(segar)} dari {len(h['ob'])})")
        for o in segar[-4:]:
            print(f"    {o['arah']:<4} {smc.bulatkan(o['bawah']):.0f} - {smc.bulatkan(o['atas']):.0f}"
                  f"   via {o['dari']}   {o['waktu']:%Y-%m-%d %H:%M}")

        buka = sorted([g for g in h["fvg"] if g["terisi"] < 0.5],
                      key=lambda g: abs(g["tengah"] - h["last"]))[:4]
        print(f"\n  FVG TERBUKA ({len(buka)} terdekat, <50% terisi)")
        for g in buka:
            print(f"    {g['arah']:<4} {smc.bulatkan(g['bawah']):.0f} - {smc.bulatkan(g['atas']):.0f}"
                  f"   {g['terisi'] * 100:.0f}% terisi   {g['waktu']:%Y-%m-%d %H:%M}")

        print("\n  SWEEP TERAKHIR")
        for s in h["sweep"][-3:]:
            print(f"    {s['jenis']} @ {smc.bulatkan(s['disapu']):.0f}   {s['waktu']:%Y-%m-%d %H:%M}")


# ---------------------------------------------------------------- alur utama
def muat_kandidat(args) -> list[dict]:
    """Daftar kandidat: dari --ticker, atau dari CSV hasil screening."""
    if args.ticker:
        return [{"Ticker": t.upper().removesuffix(".JK")} for t in args.ticker]

    berkas = Path(args.dari_csv)
    if not berkas.exists():
        sys.exit(f"File {berkas} tidak ada. Jalankan screener.py dulu, "
                 f"atau pakai --ticker untuk analisa ad-hoc.")
    df = pd.read_csv(berkas)
    if df.empty:
        sys.exit(f"{berkas} kosong — tidak ada kandidat untuk dianalisa.")
    return df.to_dict("records")


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--dari-csv", default="hasil/swing.csv",
                   help="CSV hasil screening yang jadi sumber kandidat")
    p.add_argument("--ticker", nargs="+", metavar="KODE",
                   help="analisa kode tertentu saja, abaikan CSV (mis. BBCA TLKM)")
    p.add_argument("--output", default="hasil/swing_smc.csv", help="file CSV hasil")
    p.add_argument("--detail", action="store_true",
                   help="cetak laporan struktur lengkap per emiten per timeframe")
    args = p.parse_args()

    kandidat = muat_kandidat(args)
    print(f"Menganalisa {len(kandidat)} emiten dari "
          f"{'--ticker' if args.ticker else args.dari_csv} ...", file=sys.stderr)

    baris = []
    for n, k in enumerate(kandidat, 1):
        kode = str(k["Ticker"]).upper().removesuffix(".JK")
        tkr = f"{kode}.JK"
        print(f"  [{n}/{len(kandidat)}] {kode} ...", file=sys.stderr)

        hasil: dict[str, dict] = {}
        catatan = []
        try:
            bar = ambil_semua(tkr)
            for tf in TIMEFRAME:
                a = analisa_tf(bar[tf["nama"]], tf["k"], tf["intraday"])
                if a:
                    hasil[tf["nama"]] = a
                else:
                    catatan.append(f"{tf['nama']} bar kurang ({len(bar[tf['nama']])})")
        except Exception as err:
            # Satu emiten yang gagal tidak boleh menjatuhkan seluruh tabel.
            print(f"      gagal: {err}", file=sys.stderr)
            catatan.append(f"gagal ambil data: {err}")

        d1 = hasil.get("D1")
        harga = d1["last"] if d1 else float("nan")
        rencana = susun_rencana(hasil, harga) if d1 else {
            "tipe": "", "atas": None, "bawah": None, "stop": None,
            "target": None, "rr": None, "jarak": None, "tolak": ""}
        sinyal, alasan = baca_sinyal(hasil, rencana)

        sw = hasil.get("D1", {}).get("sweep") or []
        baris.append({
            "Ticker": kode,
            "Nama": k.get("Nama", ""),
            "Skor": k.get("Skor", ""),
            "StatusScreener": k.get("Status", ""),
            "Harga": round(harga) if d1 else "",
            "TrenD1": d1["tren"] if d1 else "",
            "ZonaD1": d1["pd"]["zona"] if d1 and d1["pd"] else "",
            "PosisiD1%": round(d1["pd"]["pct"] * 100) if d1 and d1["pd"] else "",
            "EventD1": (f"{d1['events'][-1]['jenis']} {d1['events'][-1]['arah']}"
                        if d1 and d1["events"] else ""),
            "TrenSesi": hasil["SESI"]["tren"] if "SESI" in hasil else "",
            "TrenH1": hasil["H1"]["tren"] if "H1" in hasil else "",
            "TipeEntri": rencana["tipe"],
            "EntriAtas": rencana["atas"] if rencana["atas"] is not None else "",
            "EntriBawah": rencana["bawah"] if rencana["bawah"] is not None else "",
            "Stop": rencana["stop"] if rencana["stop"] is not None else "",
            "Target": rencana["target"] if rencana["target"] is not None else "",
            "RR": rencana["rr"] if rencana["rr"] is not None else "",
            "JarakEntri%": round(rencana["jarak"], 1) if rencana["jarak"] is not None else "",
            "ATR_D1%": round(d1["atr"] / d1["last"] * 100, 1) if d1 else "",
            "SweepTerakhir": f"{sw[-1]['jenis']} @ {smc.bulatkan(sw[-1]['disapu']):.0f}" if sw else "",
            "Sinyal": sinyal,
            "Catatan": alasan + ("; " + "; ".join(catatan) if catatan else ""),
        })

        if args.detail and hasil:
            cetak_detail(kode, hasil)

    df = pd.DataFrame(baris, columns=KOLOM)

    # Urutan tampil mengikuti kesiapan, bukan abjad: yang bisa ditindaklanjuti
    # hari ini naik ke atas, yang cuma perlu dipantau turun ke bawah.
    urut = {"SIAP": 0, "PANTAU": 1, "TUNGGU": 2, "HINDARI": 3, "DATA KURANG": 4}
    df = df.sort_values(
        by=["Sinyal", "RR"],
        key=lambda s: s.map(urut) if s.name == "Sinyal" else pd.to_numeric(s, errors="coerce"),
        ascending=[True, False],
    ).reset_index(drop=True)

    keluar = Path(args.output)
    keluar.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(keluar, index=False)

    ringkas = ["Ticker", "Harga", "TrenD1", "TrenSesi", "ZonaD1", "TipeEntri",
               "EntriBawah", "EntriAtas", "Stop", "Target", "RR", "Sinyal"]
    print()
    print(df[ringkas].to_string(index=False))
    print(f"\nTersimpan ke {keluar}")
    print("Pembacaan teknikal, bukan saran investasi.")


if __name__ == "__main__":
    main()
