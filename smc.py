#!/usr/bin/env python3
"""Mesin deteksi Smart Money Concepts (SMC) untuk saham IDX.

Port dari `tradingviews/lib/smc-core.mjs` — mesin yang sama (pivot, BOS/CHoCH,
FVG, order block, likuiditas, sweep, premium/discount), tapi disesuaikan untuk
saham Bursa Efek Indonesia. Tiga perbedaan yang disengaja:

1. FVG menolak gap antar-sesi. Emas jalan 24 jam, jadi imbalance tiga candle
   di sana murni order flow. Saham IDX tutup tiap malam dan akhir pekan, jadi
   di timeframe intraday gap pembukaan sesi akan terbaca sebagai FVG SETIAP
   HARI — puluhan sinyal palsu yang menenggelamkan yang asli. Lihat `fvg()`.

2. Semua level dibulatkan ke fraksi harga IDX. Angka mentah hasil hitungan
   keluar seperti 7183,4 dan tidak bisa dipasang jadi order. Lihat `bulatkan()`.

3. Perbaikan bug pembuangan pivot pada `struktur()` — lihat komentar di sana.

Semua fungsi murni: masukannya list bar, keluarannya angka. Tidak menyentuh
jaringan, tidak baca file. Pengambil datanya ada di `analisa_smc.py`.

Satu bar adalah dict dengan kunci: waktu (datetime), open, high, low, close.
"""

from __future__ import annotations

import math
from datetime import date as _date

# ---------------------------------------------------------------- fraksi harga
# Fraksi harga (tick size) IDX per Kep-00023/BEI/03-2023. Batas atas eksklusif:
# saham Rp 500 masuk kelompok fraksi Rp 5, bukan Rp 2.
FRAKSI_HARGA = ((200, 1), (500, 2), (2000, 5), (5000, 10), (math.inf, 25))


def fraksi(harga: float) -> int:
    """Fraksi harga yang berlaku untuk satu tingkat harga."""
    for batas, f in FRAKSI_HARGA:
        if harga < batas:
            return f
    return 25


def bulatkan(harga: float, arah: int = 0) -> float:
    """Bulatkan ke fraksi harga IDX terdekat.

    `arah` 0 = terdekat, -1 = ke bawah, +1 = ke atas. Arah dipakai supaya
    pembulatan tidak pernah membuat rencana terlihat lebih bagus dari
    aslinya: untuk posisi beli, stop dan target sama-sama dibulatkan ke bawah,
    sehingga risk/reward hasil pembulatan selalu sama atau lebih konservatif
    dibanding angka mentahnya — tidak pernah lebih optimis.
    """
    if harga is None or not math.isfinite(harga):
        return harga
    f = fraksi(harga)
    if arah < 0:
        return math.floor(harga / f) * f
    if arah > 0:
        return math.ceil(harga / f) * f
    return round(harga / f) * f


# ---------------------------------------------------------------- pivot (fractal)
def pivot(bars: list[dict], k: int) -> list[dict]:
    """Titik pivot fractal: bar yang high/low-nya ekstrem dibanding k bar kiri-kanan."""
    out = []
    for i in range(k, len(bars) - k):
        tinggi = rendah = True
        for j in range(i - k, i + k + 1):
            if j == i:
                continue
            if bars[j]["high"] >= bars[i]["high"]:
                tinggi = False
            if bars[j]["low"] <= bars[i]["low"]:
                rendah = False
        if tinggi:
            out.append({"tipe": "H", "harga": bars[i]["high"], "i": i, "waktu": bars[i]["waktu"]})
        if rendah:
            out.append({"tipe": "L", "harga": bars[i]["low"], "i": i, "waktu": bars[i]["waktu"]})
    out.sort(key=lambda s: s["i"])
    return out


# ---------------------------------------------------------------- struktur pasar
def struktur(bars: list[dict], k: int) -> dict:
    """Deteksi BOS / CHoCH.

    BOS   = break searah tren yang sedang berjalan.
    CHoCH = break pertama melawan arah tren (pergantian karakter).

    Hanya pivot yang sudah terkonfirmasi sebelum bar berjalan yang dipakai
    (`s["i"] + k < i`), jadi tidak ada lookahead bias.

    Dua perbaikan atas versi JS, keduanya soal pembuangan pivot yang sudah
    terpakai:

    1. Di JS, `highs.splice(highs.indexOf(lastH), 1)` berada DI LUAR penjagaan
       duplikat, sehingga bisa terpanggil dengan lastH yang sudah dibuang pada
       iterasi sebelumnya. `indexOf` mengembalikan -1 dan `splice(-1, 1)` di
       JavaScript menghapus elemen TERAKHIR — yaitu pivot masa depan yang sama
       sekali tidak bersalah. Efeknya fatal dan senyap: pada data XAU harian
       466 bar, deteksi berhenti menghasilkan event setelah April 2025 padahal
       datanya sampai Agustus 2026.

    2. JS hanya membuang pivot yang kebetulan sedang dipakai (`siap[-1]`),
       jadi pivot lama yang terlewati tetap mengendap di daftar. Begitu pivot
       yang lebih baru habis, yang basi itu naik jadi `siap[-1]` dan langsung
       memicu "break" atas level yang sudah lama dilewati — muncul sebagai
       urutan BOS yang harganya melompat-lompat mundur. Di sini setiap break
       membuang SEMUA pivot terkonfirmasi yang ikut terlewati harga close,
       karena memang itu arti menembus struktur. Pivot yang belum terkonfirmasi
       tidak disentuh, supaya tidak ada lookahead.
    """
    sw = pivot(bars, k)
    highs = [s for s in sw if s["tipe"] == "H"]
    lows = [s for s in sw if s["tipe"] == "L"]
    events: list[dict] = []
    tren = None
    last_h = last_l = None

    for i in range(len(bars)):
        siap_h = [s for s in highs if s["i"] + k < i]
        siap_l = [s for s in lows if s["i"] + k < i]
        if siap_h:
            last_h = siap_h[-1]
        if siap_l:
            last_l = siap_l[-1]
        c = bars[i]["close"]
        prev = events[-1] if events else None

        if last_h and c > last_h["harga"]:
            if not prev or prev["level"] != last_h["harga"] or prev["arah"] != "bull":
                events.append({
                    "jenis": "CHoCH" if tren == "down" else "BOS",
                    "arah": "bull", "level": last_h["harga"],
                    "waktu": bars[i]["waktu"], "i": i,
                })
                tren = "up"
            highs = [s for s in highs if not (s["i"] + k < i and s["harga"] <= c)]
            last_h = None
        elif last_l and c < last_l["harga"]:
            if not prev or prev["level"] != last_l["harga"] or prev["arah"] != "bear":
                events.append({
                    "jenis": "CHoCH" if tren == "up" else "BOS",
                    "arah": "bear", "level": last_l["harga"],
                    "waktu": bars[i]["waktu"], "i": i,
                })
                tren = "down"
            lows = [s for s in lows if not (s["i"] + k < i and s["harga"] >= c)]
            last_l = None

    return {"pivot": sw, "events": events, "tren": tren}


# ---------------------------------------------------------------- label HH/HL/LH/LL
def label_pivot(sw: list[dict]) -> list[dict]:
    """Beri label HH / HL / LH / LL pada urutan pivot."""
    out = []
    pH = pL = None
    for s in sw:
        d = dict(s)
        if s["tipe"] == "H":
            d["label"] = "H" if pH is None else ("HH" if s["harga"] > pH else "LH")
            pH = s["harga"]
        else:
            d["label"] = "L" if pL is None else ("HL" if s["harga"] > pL else "LL")
            pL = s["harga"]
        out.append(d)
    return out


# ---------------------------------------------------------------- Fair Value Gap
def sesi(bar: dict) -> _date:
    """Tanggal sesi bursa sebuah bar."""
    return bar["waktu"].date()


def fvg(bars: list[dict], intraday: bool = False) -> list[dict]:
    """Imbalance tiga candle, plus seberapa dalam gap itu sudah terisi.

    Pada timeframe intraday, pola hanya dihitung bila ketiga bar berada di
    sesi bursa yang sama. Tanpa syarat itu, jeda semalam (15:50 -> 09:00) dan
    akhir pekan selalu memunculkan "imbalance" antara bar penutup dan bar
    pembuka — bukan jejak order flow, cuma bursa yang tutup. Di timeframe
    harian syarat ini justru tidak boleh dipakai: di sana bar berurutan MEMANG
    selalu beda tanggal, dan gap antar-hari adalah sinyal yang sah.
    """
    out = []
    for i in range(2, len(bars)):
        a, b, c = bars[i - 2], bars[i - 1], bars[i]
        if intraday and not (sesi(a) == sesi(b) == sesi(c)):
            continue
        if c["low"] > a["high"]:
            out.append({"arah": "bull", "atas": c["low"], "bawah": a["high"],
                        "i": i, "waktu": c["waktu"]})
        if c["high"] < a["low"]:
            out.append({"arah": "bear", "atas": a["low"], "bawah": c["high"],
                        "i": i, "waktu": c["waktu"]})

    for g in out:
        terisi = 0.0
        tinggi = g["atas"] - g["bawah"]
        for j in range(g["i"] + 1, len(bars)):
            b = bars[j]
            if g["arah"] == "bull" and b["low"] < g["atas"]:
                terisi = max(terisi, min(1.0, (g["atas"] - max(b["low"], g["bawah"])) / tinggi))
            if g["arah"] == "bear" and b["high"] > g["bawah"]:
                terisi = max(terisi, min(1.0, (min(b["high"], g["atas"]) - g["bawah"]) / tinggi))
        g["terisi"] = terisi
        g["tengah"] = (g["atas"] + g["bawah"]) / 2
        g["ukuran"] = tinggi
    return out


# ---------------------------------------------------------------- Order Block
def order_block(bars: list[dict], events: list[dict], lookback: int = 15) -> list[dict]:
    """Candle berlawanan terakhir sebelum break struktur.

    `dimitigasi` True artinya harga sudah pernah kembali menyentuh zona itu —
    order yang menunggu di sana kemungkinan besar sudah terserap, jadi yang
    dicari untuk entri baru adalah yang masih FRESH.
    """
    obs = []
    # Dua break berturut-turut sering menunjuk candle asal yang sama; tanpa ini
    # zona yang identik muncul dua kali di laporan dan seolah-olah jadi dua
    # bukti berbeda.
    terpakai = set()
    for e in events:
        i = e["i"]
        mau_turun = e["arah"] == "bull"
        for j in range(i - 1, max(0, i - lookback) - 1, -1):
            turun = bars[j]["close"] < bars[j]["open"]
            if turun == mau_turun:
                if (j, e["arah"]) not in terpakai:
                    terpakai.add((j, e["arah"]))
                    obs.append({
                        "arah": e["arah"], "atas": bars[j]["high"], "bawah": bars[j]["low"],
                        "waktu": bars[j]["waktu"], "dari": e["jenis"], "i": j,
                    })
                break
    for ob in obs:
        tersentuh = False
        for j in range(ob["i"] + 3, len(bars)):
            if bars[j]["low"] <= ob["atas"] and bars[j]["high"] >= ob["bawah"]:
                tersentuh = True
                break
        ob["dimitigasi"] = tersentuh
    return obs


# ---------------------------------------------------------------- likuiditas
def likuiditas(sw: list[dict], tol: float = 0.0012) -> dict:
    """Kolam likuiditas: equal highs / equal lows (level yang disentuh >= 2 kali)."""
    def kelompok(arr):
        s = sorted(arr, key=lambda p: p["harga"])
        cl = []
        for p in s:
            if cl and abs(p["harga"] - cl[-1]["pts"][-1]["harga"]) / p["harga"] < tol:
                cl[-1]["pts"].append(p)
            else:
                cl.append({"pts": [p]})
        return [
            {
                "level": sum(x["harga"] for x in c["pts"]) / len(c["pts"]),
                "jumlah": len(c["pts"]),
                "terakhir": max(x["waktu"] for x in c["pts"]),
            }
            for c in cl if len(c["pts"]) >= 2
        ]
    return {
        "eqh": kelompok([s for s in sw if s["tipe"] == "H"]),
        "eql": kelompok([s for s in sw if s["tipe"] == "L"]),
    }


# ---------------------------------------------------------------- sweep
def sweep(bars: list[dict], sw: list[dict], lookback: int = 40) -> list[dict]:
    """Wick menembus pivot lalu close balik ke dalam (stop hunt).

    'BSL raid' = likuiditas di atas high diambil, harga ditolak turun.
    'SSL raid' = likuiditas di bawah low diambil, harga ditolak naik.
    """
    out = []
    mulai = max(0, len(bars) - lookback)
    for i in range(mulai, len(bars)):
        b = bars[i]
        for s in sw:
            if s["i"] >= i - 2:
                continue
            if s["tipe"] == "H" and b["high"] > s["harga"] and b["close"] < s["harga"]:
                out.append({"jenis": "BSL raid", "disapu": s["harga"], "waktu": b["waktu"]})
            if s["tipe"] == "L" and b["low"] < s["harga"] and b["close"] > s["harga"]:
                out.append({"jenis": "SSL raid", "disapu": s["harga"], "waktu": b["waktu"]})
    terlihat = set()
    unik = []
    for o in out:
        kunci = (o["jenis"], bulatkan(o["disapu"]))
        if kunci in terlihat:
            continue
        terlihat.add(kunci)
        unik.append(o)
    return unik[-6:]


# ---------------------------------------------------------------- premium/discount
def premium_diskon(sw: list[dict], last: float, window: int = 30) -> dict | None:
    """Posisi harga dalam dealing range yang dibentuk pivot-pivot terakhir."""
    recent = sw[-window:]
    if not recent:
        return None
    hi = max(s["harga"] for s in recent)
    lo = min(s["harga"] for s in recent)
    if hi <= lo:
        return None
    pct = (last - lo) / (hi - lo)
    return {
        "atas": hi, "bawah": lo, "tengah": (hi + lo) / 2, "pct": pct,
        "zona": "PREMIUM" if pct > 0.62 else ("DISCOUNT" if pct < 0.38 else "EQUILIBRIUM"),
    }


# ---------------------------------------------------------------- ATR
def atr(bars: list[dict], period: int = 14) -> float:
    """Average True Range. Memakai rata-rata sederhana, sama seperti versi JS."""
    tr = []
    for i in range(1, len(bars)):
        b, p = bars[i], bars[i - 1]
        tr.append(max(b["high"] - b["low"],
                      abs(b["high"] - p["close"]),
                      abs(b["low"] - p["close"])))
    if not tr:
        return float("nan")
    potong = tr[-period:]
    return sum(potong) / len(potong)
