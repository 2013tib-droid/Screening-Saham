#!/usr/bin/env node
/**
 * Uji dashboard tanpa browser.
 *
 * Kenapa ada: dashboard/index.html adalah satu berkas tanpa build step, dan
 * satu-satunya cara memastikan ia masih cocok dengan CSV yang dihasilkan
 * screener adalah membukanya di browser. Skrip ini menjalankan JavaScript
 * dashboard yang SEBENARNYA di Node dengan DOM tiruan seperlunya, lalu
 * memeriksa HTML tabel yang keluar. Yang diuji kodenya, bukan salinannya.
 *
 * Yang bisa ditangkap: kolom yang namanya tidak ada di CSV, angka yang gagal
 * diparse, nilai yang bocor mentah ke halaman, dan baris yang gagal dirender.
 * Yang TIDAK bisa ditangkap: apa pun soal tampilan — lebar kolom, keterbacaan,
 * warna, perilaku di layar sempit. Itu tetap perlu mata.
 *
 * Pemakaian:
 *     node scripts/uji_dashboard.js            # dari akar repo
 *     node scripts/uji_dashboard.js /path/repo
 *
 * Keluar dengan kode 1 bila ada pemeriksaan yang gagal, jadi bisa dipakai di CI.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const REPO = process.argv[2] || process.cwd();
const BERKAS = path.join(REPO, "dashboard/index.html");

if (!fs.existsSync(BERKAS)) {
  console.error(`Tidak menemukan ${BERKAS}. Jalankan dari akar repo, atau ` +
                `sebutkan lokasinya sebagai argumen.`);
  process.exit(1);
}

const html = fs.readFileSync(BERKAS, "utf8");
// \r?\n karena berkas di repo ini ber-CRLF setelah normalisasi git di Windows.
const cocok = html.match(/<script>\r?\n([\s\S]*?)<\/script>/);
if (!cocok) {
  console.error("Blok <script> tidak ditemukan di dashboard/index.html.");
  process.exit(1);
}
const js = cocok[1];

// ---- DOM tiruan seperlunya --------------------------------------------------
// Hanya yang benar-benar dipakai dashboard: getElementById, querySelectorAll,
// createElement, dan fetch. Nilai yang di-set disimpan supaya bisa diperiksa.
const simpan = {};
function elemen(id) {
  return {
    set innerHTML(v) { simpan[id] = v; },
    get innerHTML() { return simpan[id] || ""; },
    set textContent(v) { simpan[id + ":teks"] = v; },
    get textContent() { return simpan[id + ":teks"] || ""; },
    set hidden(v) {}, set value(v) {}, get value() { return ""; },
    classList: { add() {}, remove() {} },
    dataset: {},
    addEventListener() {},
    appendChild() {},
    querySelectorAll() { return []; },
  };
}

const konteks = {
  document: {
    getElementById: elemen,
    querySelectorAll: () => [],
    createElement: () => elemen("opt"),
  },
  fetch: async (url) => {
    const p = path.join(REPO, url.split("?")[0]);
    if (!fs.existsSync(p)) return { ok: false };
    const teks = fs.readFileSync(p, "utf8");
    return { ok: true, text: async () => teks, json: async () => JSON.parse(teks) };
  },
  console, Intl, Date, Math, Number, String, Array, Object, JSON, Promise,
  setTimeout, RegExp, Boolean, Error,
};
konteks.globalThis = konteks;
vm.createContext(konteks);

// `const KOLOM`, `const state`, dan `function render` adalah binding leksikal
// di dalam skrip, jadi tidak menempel ke objek konteks vm. Diekspor eksplisit
// agar bisa diperiksa dan dikemudikan dari luar (mis. untuk berpindah tab).
vm.runInContext(
  js + "\nglobalThis.__KOLOM = KOLOM;" +
       "\nglobalThis.__state = state;" +
       "\nglobalThis.__render = render;",
  konteks);
const KOLOM = konteks.__KOLOM;

// ---- Pemeriksaan ------------------------------------------------------------
let gagal = 0;
function periksa(nama, lulus, keterangan = "") {
  console.log(`  ${lulus ? "OK  " : "GAGAL"} ${nama}${keterangan ? " — " + keterangan : ""}`);
  if (!lulus) gagal++;
}

function ujiTab(tab) {
  konteks.__state.tab = tab;
  konteks.__render();
  const tabel = simpan["tabel"] || "";
  console.log(`\n=== tab "${tab}" ===`);

  if (!tabel) { periksa("tabel dirender", false); return; }

  const kolomTabel = [...tabel.matchAll(/<th data-kolom="([^"]+)"/g)].map(m => m[1]);
  const baris = tabel.split("<tr>").length - 2;   // dikurangi baris header
  const data = konteks.__state.data[tab] || [];

  periksa("jumlah baris cocok dengan data", baris === data.length,
          `${baris} baris tabel vs ${data.length} baris data`);
  periksa("semua kolom terender", kolomTabel.length === KOLOM.length,
          `${kolomTabel.length} kolom`);

  if (data.length) {
    const hilang = KOLOM.map(k => k.k).filter(k => !(k in data[0]));
    periksa("setiap kolom ada di CSV", hilang.length === 0,
            hilang.length ? "tidak ada di CSV: " + hilang.join(", ") : "");
  }

  // Nilai mentah tidak boleh bocor: kolom teks kosong di CSV tertulis sebagai
  // dua tanda kutip, dan pernah muncul apa adanya di halaman.
  periksa("tidak ada tanda kutip kosong bocor",
          !tabel.includes('>""<') && !tabel.includes("&quot;&quot;"));
  periksa("tidak ada 'undefined' atau 'NaN' bocor",
          !/>undefined<|>NaN</.test(tabel));

  const chip = (tabel.match(/class="flag"/g) || []).length;
  const berflag = data.filter(r => String(r.Flag || "").trim()).length;
  const totalFlag = data.reduce(
    (n, r) => n + String(r.Flag || "").split(",").filter(Boolean).length, 0);
  periksa("chip red flag sesuai jumlah flag di data", chip === totalFlag,
          `${chip} chip untuk ${totalFlag} flag pada ${berflag} emiten`);
}

console.log(`Menguji ${path.relative(REPO, BERKAS)} terhadap CSV di hasil/`);
console.log(`Kolom yang dideklarasikan (${KOLOM.length}): ` +
            KOLOM.map(k => k.k).join(", "));

// Pemuatan data berjalan asinkron lewat fetch tiruan; beri kesempatan selesai.
setTimeout(() => {
  const tiles = ["semua", "swing", "value", "tumbuh"];
  console.log("\n=== pemuatan ===");
  tiles.forEach(t => periksa(`data ${t} termuat`,
    Array.isArray(konteks.__state.data[t]) && konteks.__state.data[t].length >= 0,
    `${(konteks.__state.data[t] || []).length} baris`));
  periksa("waktu pembaruan terbaca",
          Boolean(simpan["pembaruan:teks"]), simpan["pembaruan:teks"] || "");

  tiles.forEach(ujiTab);

  console.log(gagal ? `\n${gagal} pemeriksaan GAGAL.` : "\nSemua pemeriksaan lolos.");
  console.log("Catatan: ini tidak memeriksa tampilan sama sekali — lebar kolom, " +
              "keterbacaan, dan perilaku di layar sempit tetap perlu dilihat " +
              "langsung di browser.");
  process.exit(gagal ? 1 : 0);
}, 800);
