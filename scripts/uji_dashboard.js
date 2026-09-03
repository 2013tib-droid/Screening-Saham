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
       "\nglobalThis.__render = render;" +
       "\nglobalThis.__kolomSet = kolomSet;",
  konteks);
const KOLOM = konteks.__KOLOM;
const kolomSet = konteks.__kolomSet;

// ---- Pemeriksaan ------------------------------------------------------------
let gagal = 0;
function periksa(nama, lulus, keterangan = "") {
  console.log(`  ${lulus ? "OK  " : "GAGAL"} ${nama}${keterangan ? " — " + keterangan : ""}`);
  if (!lulus) gagal++;
}

function ujiTab(tab) {
  konteks.__state.tab = tab;
  // Dashboard membatasi 10 baris per halaman. Pemeriksaan di bawah ini soal
  // kelengkapan data — setiap kolom terender, setiap flag jadi chip — jadi
  // pagination dimatikan dulu (perHal = 0) supaya yang diperiksa seluruh baris,
  // bukan sepuluh baris pertama. Pagination-nya sendiri diuji terpisah di
  // ujiPagination().
  konteks.__state.perHal = 0;
  konteks.__state.hal = 1;
  konteks.__render();
  const tabel = simpan["tabel"] || "";
  console.log(`\n=== tab "${tab}" ===`);

  if (!tabel) { periksa("tabel dirender", false); return; }

  const kolomTabel = [...tabel.matchAll(/<th data-kolom="([^"]+)"/g)].map(m => m[1]);
  const baris = tabel.split("<tr>").length - 2;   // dikurangi baris header
  const data = konteks.__state.data[tab] || [];
  // Tab SMC memakai daftar kolomnya sendiri. Memakai KOLOM untuk semua tab
  // membuat pemeriksaan di bawah menuduh kolom hilang padahal memang beda set.
  const kolomTab = kolomSet(tab);

  periksa("jumlah baris cocok dengan data", baris === data.length,
          `${baris} baris tabel vs ${data.length} baris data`);
  periksa("semua kolom terender", kolomTabel.length === kolomTab.length,
          `${kolomTabel.length} kolom`);

  if (data.length) {
    const hilang = kolomTab.map(k => k.k).filter(k => !(k in data[0]));
    periksa("setiap kolom ada di CSV", hilang.length === 0,
            hilang.length ? "tidak ada di CSV: " + hilang.join(", ") : "");
  }

  // Nilai mentah tidak boleh bocor: kolom teks kosong di CSV tertulis sebagai
  // dua tanda kutip, dan pernah muncul apa adanya di halaman.
  periksa("tidak ada tanda kutip kosong bocor",
          !tabel.includes('>""<') && !tabel.includes("&quot;&quot;"));
  periksa("tidak ada 'undefined' atau 'NaN' bocor",
          !/>undefined<|>NaN</.test(tabel));

  if (tab === "smc") {
    // Setiap baris harus punya badge sinyal. Kalau slug kelasnya meleset,
    // badge tetap muncul tapi tanpa warna — jadi kelasnya ikut diperiksa,
    // bukan cuma keberadaannya.
    const badge = [...tabel.matchAll(/class="status s-([a-z]+)"/g)].map(m => m[1]);
    const sah = ["siap", "pantau", "tunggu", "hindari", "kurang"];
    periksa("setiap baris punya badge sinyal", badge.length === data.length,
            `${badge.length} badge untuk ${data.length} baris`);
    periksa("kelas badge sinyal dikenali CSS", badge.every(b => sah.includes(b)),
            "ditemukan: " + [...new Set(badge)].join(", "));
    // RR harus jadi angka, bukan teks: kalau tidak, pengurutan kolomnya
    // alfabetis dan "1.2" jatuh di bawah "9.8".
    const berRR = data.filter(r => r.RR !== null && r.RR !== "");
    periksa("RR terparse sebagai angka", berRR.every(r => typeof r.RR === "number"),
            `${berRR.length} baris punya rencana utuh`);
    periksa("baris tanpa rencana tetap memberi alasan",
            data.filter(r => r.RR === null || r.RR === "")
                .every(r => String(r.Catatan || "").trim().length > 0),
            `${data.length - berRR.length} baris tanpa rencana`);
    // Kode saham berwarna dan angka di kartu "Zona & target lengkap" dihitung
    // dari syarat yang sama. Kalau salah satunya kelak diubah sendirian,
    // tabel dan kartu diam-diam bercerita beda — dan itu justru kebingungan
    // yang ingin dihilangkan oleh pewarnaan ini.
    const berwarna = (tabel.match(/class="ticker ada-rencana/g) || []).length;
    periksa("kode saham berwarna sebanyak yang rencananya utuh",
            berwarna === berRR.length,
            `${berwarna} kode berwarna untuk ${berRR.length} rencana utuh`);
    return;
  }

  const chip = (tabel.match(/class="flag"/g) || []).length;
  const berflag = data.filter(r => String(r.Flag || "").trim()).length;
  const totalFlag = data.reduce(
    (n, r) => n + String(r.Flag || "").split(",").filter(Boolean).length, 0);
  periksa("chip red flag sesuai jumlah flag di data", chip === totalFlag,
          `${chip} chip untuk ${totalFlag} flag pada ${berflag} emiten`);
}

function barisTabel() {
  return (simpan["tabel"] || "").split("<tr>").length - 2;   // dikurangi header
}

// Pagination baris: dibatasi supaya tab "semua" (402 emiten) tidak jadi halaman
// sepanjang tiga meter. Yang diperiksa: halaman penuh berisi persis perHal
// baris, halaman terakhir berisi sisanya, halaman berbeda berisi baris berbeda,
// dan halaman di luar jangkauan dijepit ke halaman terakhir, bukan kosong.
function ujiPagination() {
  console.log("\n=== pagination baris ===");
  const st = konteks.__state;
  st.tab = "semua";
  st.perHal = 10;
  const total = (st.data.semua || []).length;
  const halTotal = Math.ceil(total / 10);

  st.hal = 1;
  konteks.__render();
  const hal1 = simpan["tabel"] || "";
  periksa("halaman 1 berisi 10 baris", barisTabel() === 10, `${barisTabel()} baris`);

  st.hal = 2;
  konteks.__render();
  const hal2 = simpan["tabel"] || "";
  periksa("halaman 2 berisi 10 baris", barisTabel() === 10, `${barisTabel()} baris`);
  periksa("halaman 2 berbeda dari halaman 1", hal1 !== hal2);

  st.hal = halTotal;
  konteks.__render();
  const sisa = total - (halTotal - 1) * 10;
  periksa("halaman terakhir berisi sisanya", barisTabel() === sisa,
          `${barisTabel()} baris, seharusnya ${sisa} (dari ${total} emiten, ${halTotal} halaman)`);

  st.hal = halTotal + 50;
  konteks.__render();
  periksa("halaman di luar jangkauan dijepit, tidak kosong", barisTabel() === sisa,
          `${barisTabel()} baris`);

  st.perHal = 0;
  st.hal = 1;
  konteks.__render();
  periksa('pilihan "Semua" menampilkan seluruh baris', barisTabel() === total,
          `${barisTabel()} baris`);
}

console.log(`Menguji ${path.relative(REPO, BERKAS)} terhadap CSV di hasil/`);
console.log(`Kolom yang dideklarasikan (${KOLOM.length}): ` +
            KOLOM.map(k => k.k).join(", "));

// Pemuatan data berjalan asinkron lewat fetch tiruan; beri kesempatan selesai.
setTimeout(() => {
  const tiles = ["semua", "swing", "value", "tumbuh", "smc"];
  console.log("\n=== pemuatan ===");
  tiles.forEach(t => periksa(`data ${t} termuat`,
    Array.isArray(konteks.__state.data[t]) && konteks.__state.data[t].length >= 0,
    `${(konteks.__state.data[t] || []).length} baris`));
  periksa("waktu pembaruan terbaca",
          Boolean(simpan["pembaruan:teks"]), simpan["pembaruan:teks"] || "");

  tiles.forEach(ujiTab);
  ujiPagination();

  console.log(gagal ? `\n${gagal} pemeriksaan GAGAL.` : "\nSemua pemeriksaan lolos.");
  console.log("Catatan: ini tidak memeriksa tampilan sama sekali — lebar kolom, " +
              "keterbacaan, dan perilaku di layar sempit tetap perlu dilihat " +
              "langsung di browser.");
  process.exit(gagal ? 1 : 0);
}, 800);
