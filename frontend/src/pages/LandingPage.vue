<script setup lang="ts">
/**
 * Public marketing page at `/`. Bare route: no app shell, no session.
 *
 * Sections, top to bottom: a site header, the hero with its trust strip, the
 * three steps, what the tool does and does not do, the four categories, a short
 * FAQ, a closing call to action, and a footer. Every factual sentence is copy
 * the app already shows elsewhere; nothing here is a new tax claim.
 */
import AppButton from "@/components/ui/AppButton.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppPill from "@/components/ui/AppPill.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { KATEGORI_LABEL, PUBLIC_RULESET, type Kategori } from "@/lib/domain";
import { rupiah } from "@/lib/format";

type Tone = "usaha" | "bebas" | "final" | "non";

/** Category key to the pill tone the rest of the app uses for it. */
const TONE: Record<Kategori, Tone> = {
  usaha: "usaha",
  pekerjaan_bebas: "bebas",
  already_final: "final",
  non_object: "non",
};

const langkah = [
  {
    judul: "Catat transaksi",
    deskripsi:
      "Satu baris untuk satu mutasi masuk: nominal, tanggal, dan pihak. Kanal apa pun — ritel, marketplace, atau transfer.",
  },
  {
    judul: "Klasifikasi otomatis",
    deskripsi:
      "Aturan lebih dulu, lalu klarifikasi kalau barisnya masih ambigu. Tidak ada baris yang menebak kategorinya sendiri.",
  },
  {
    judul: "Kertas kerja siap",
    deskripsi:
      "PPh Final, sisa batas omzet usaha, dan jejak klasifikasi tersusun per tahun pajak, siap Anda periksa.",
  },
];

/** What belongs in each category and how it is treated, one sentence each. */
const CARA: Record<Kategori, string> = {
  usaha:
    "Penjualan dan jasa yang berasal dari kegiatan usaha. Dihitung dari omzet kumulatif satu tahun pajak.",
  pekerjaan_bebas:
    "Jasa atau pekerjaan yang dikerjakan atas nama pribadi. Diperhitungkan dengan norma, bukan dari tarif omzet.",
  already_final:
    "Penghasilan yang PPh final-nya sudah dipotong atau dibayar sendiri, seperti dividen. Tidak dihitung dua kali.",
  non_object:
    "Pengembalian, modal, dan transfer yang bukan penghasilan. Tercatat untuk rekap, tidak masuk perhitungan PPh Final.",
};

const kategori: { key: Kategori; label: string; tone: Tone; teks: string }[] = (
  Object.keys(KATEGORI_LABEL) as Kategori[]
).map((key) => ({ key, label: KATEGORI_LABEL[key], tone: TONE[key], teks: CARA[key] }));

const fakta = [
  { icon: "dokumen", teks: `Seluruh angka memakai ${PUBLIC_RULESET.nama}` },
  { icon: "pembisahan", teks: "Baris ambigu jadi pertanyaan, bukan tebakan" },
  { icon: "info", teks: "Hasil akhirnya kertas kerja, bukan SPT" },
];

const dilakukan = [
  "Memisahkan setiap transaksi masuk ke salah satu dari empat kategori.",
  `Menghitung PPh Final dan sisa batas omzet usaha dengan ${PUBLIC_RULESET.nama}.`,
  "Menanyakan baris yang ambigu sebelum apa pun dihitung.",
  "Menyusun jejak klasifikasi per tahun pajak, siap diperiksa.",
];

const tidakDilakukan = [
  "Bukan SPT. Hasilnya kertas kerja, bukan laporan yang sudah disampaikan.",
  "Bukan pelaporan ke DJP dan bukan software resmi DJP.",
  "Tidak ada estimasi Pasal 17.",
  "Tidak ada tombol hitung sekarang yang menggabungkan semua baris jadi satu.",
];

const tanya = [
  {
    q: "Apakah hasilnya SPT?",
    a: "Bukan. KlasifiPajak menghasilkan kertas kerja, bukan SPT resmi, dan tidak melaporkan apa pun ke DJP.",
  },
  {
    q: "Apakah ini software resmi DJP atau terhubung ke Coretax?",
    a: "Bukan. KlasifiPajak bukan produk DJP/Coretax.",
  },
  {
    q: "Siapa yang menghitung angka pajaknya?",
    a: "Mesin klasifikasi dan perhitungan yang deterministik. Model bahasa tidak pernah menghasilkan angka pajak.",
  },
  {
    q: "Bagaimana dengan data saya?",
    a: "Data tersimpan terpisah per akun. Satu akun tidak dapat membuka data akun lain.",
  },
  {
    q: "Apa yang terjadi jika sebuah transaksi ambigu?",
    a: "Baris itu ditanyakan kepada Anda sebelum dihitung. Tidak ditebak.",
  },
];
</script>

<template>
  <div class="landing">
    <header class="site-header">
      <div class="wrap bar">
        <RouterLink to="/" class="brand" aria-label="KlasifiPajak, beranda">
          <span class="mark" aria-hidden="true">K</span>
          <span class="word">KlasifiPajak</span>
        </RouterLink>

        <nav class="links" aria-label="Bagian halaman">
          <a href="#cara" class="link">Cara kerja</a>
          <a href="#batas" class="link">Yang dilakukan</a>
          <a href="#tanya" class="link">Pertanyaan</a>
        </nav>

        <div class="acts">
          <RouterLink to="/masuk" class="sign">Masuk</RouterLink>
          <AppButton to="/masuk?mode=daftar" variant="primary" size="md">Mulai gratis</AppButton>
        </div>
      </div>
    </header>

    <main>
      <section class="hero wrap" aria-labelledby="h-utama">
        <div class="hero-main">
          <p class="u-eyebrow">Kertas kerja PPh Final UMKM</p>
          <h1 id="h-utama" class="h1">
            Setiap transaksi masuk diklasifikasi sendiri, lalu PPh Final dihitung dari klasifikasi
            itu.
          </h1>
          <p class="lede">
            KlasifiPajak memisahkan omzet usaha, pekerjaan bebas, penghasilan yang sudah berstatus
            final, dan yang bukan objek pajak. Baris yang ambigu ditanyakan, bukan ditebak. Yang
            keluar adalah kertas kerja yang bisa Anda telusuri sampai ke sumber tiap klasifikasi.
          </p>
          <div class="cta">
            <AppButton to="/masuk?mode=daftar" variant="primary" size="lg" icon-end="arrowRight">
              Mulai gratis
            </AppButton>
            <RouterLink to="/masuk" class="secondary">Sudah punya akun? Masuk</RouterLink>
          </div>
        </div>

        <ul class="trust" aria-label="Ringkasan">
          <li v-for="f in fakta" :key="f.teks" class="trust-item">
            <AppIcon :name="f.icon" :size="18" :stroke-width="1.7" />
            <span>{{ f.teks }}</span>
          </li>
        </ul>
      </section>

      <section id="cara" class="sec wrap" aria-labelledby="h-cara">
        <p class="u-eyebrow">Cara kerjanya</p>
        <h2 id="h-cara" class="h2">Tiga langkah, tanpa tebakan.</h2>
        <p class="lede-sm">
          Tidak ada tombol "hitung sekarang" yang menggabungkan semua baris jadi satu. Urutannya
          tetap: catat, klasifikasi, baru hitung.
        </p>

        <ol class="steps">
          <li v-for="(s, i) in langkah" :key="s.judul" class="step">
            <span class="n figure" aria-hidden="true">{{ i + 1 }}</span>
            <h3 class="st">{{ s.judul }}</h3>
            <p class="sd">{{ s.deskripsi }}</p>
          </li>
        </ol>
      </section>

      <section id="batas" class="sec wrap" aria-labelledby="h-batas">
        <p class="u-eyebrow">Ruang lingkup</p>
        <h2 id="h-batas" class="h2">Apa yang dilakukan, dan apa yang tidak.</h2>

        <div class="scope">
          <div class="panel">
            <h3 class="pt">Yang dilakukan</h3>
            <ul class="plist">
              <li v-for="d in dilakukan" :key="d">{{ d }}</li>
            </ul>
          </div>
          <div class="panel">
            <h3 class="pt">Yang tidak dilakukan</h3>
            <ul class="plist">
              <li v-for="t in tidakDilakukan" :key="t">{{ t }}</li>
            </ul>
          </div>
        </div>
      </section>

      <section id="kategori" class="sec wrap" aria-labelledby="h-kategori">
        <p class="u-eyebrow">Empat kategori</p>
        <h2 id="h-kategori" class="h2">Satu transaksi, satu kategori.</h2>
        <p class="lede-sm">
          Mesin klasifikasi hanya mengenal empat kategori di bawah ini, plus keadaan "perlu
          klarifikasi" untuk baris yang masih menunggu jawaban Anda. Dasar penghitungannya
          {{ PUBLIC_RULESET.nama }}.
        </p>

        <ul class="kats">
          <li v-for="k in kategori" :key="k.key" class="kat">
            <AppPill :tone="k.tone" :label="k.label" />
            <p class="kt">{{ k.teks }}</p>
          </li>
        </ul>

        <aside class="batas">
          <div class="bh">
            <AppIcon name="info" :size="18" :stroke-width="1.7" />
            <p class="bt">Batas {{ rupiah(PUBLIC_RULESET.bebasUsaha) }} hanya untuk omzet usaha</p>
          </div>
          <p class="bd">
            Batas tahunan tersebut dipakai kategori Usaha saja. Pekerjaan bebas tidak memakainya,
            jadi kedua jenis penghasilan itu tidak saling mengurangi. Di atas batas itu, tarif PPh
            Final usaha menjadi {{ PUBLIC_RULESET.tarifLabel }}.
          </p>
        </aside>
        <WorkpaperNote publik class="stamp" />
      </section>

      <section id="tanya" class="sec wrap" aria-labelledby="h-tanya">
        <p class="u-eyebrow">Pertanyaan umum</p>
        <h2 id="h-tanya" class="h2">Sebelum Anda mulai.</h2>

        <div class="faq">
          <details v-for="item in tanya" :key="item.q" class="qa">
            <summary>{{ item.q }}</summary>
            <p>{{ item.a }}</p>
          </details>
        </div>
      </section>

      <section id="mulai" class="wrap closing" aria-labelledby="h-mulai">
        <div class="closing-in">
          <div class="closing-text">
            <h2 id="h-mulai" class="h2">Mulai dari satu transaksi.</h2>
            <p class="lede-sm">
              Buat akun, catat mutasi masuk pertama, dan lihat kertas kerjanya terbentuk.
            </p>
          </div>
          <div class="cta">
            <AppButton to="/masuk?mode=daftar" variant="primary" size="lg" icon-end="arrowRight">
              Mulai gratis
            </AppButton>
            <RouterLink to="/masuk" class="secondary">Masuk</RouterLink>
          </div>
        </div>
      </section>
    </main>

    <footer class="site-footer">
      <div class="wrap foot">
        <div class="foot-id">
          <p class="fg">KlasifiPajak</p>
          <p class="fn">Kertas kerja pajak untuk UMKM. Bukan software resmi DJP.</p>
        </div>
        <nav class="foot-links" aria-label="Tautan kaki">
          <RouterLink to="/masuk">Masuk</RouterLink>
          <RouterLink to="/masuk?mode=daftar">Daftar</RouterLink>
        </nav>
        <WorkpaperNote publik class="foot-note" />
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Tokens only. Every colour below is a var(--...) defined for light and dark. */

.landing {
  min-height: 100svh;
  display: flex;
  flex-direction: column;
  background: var(--canvas);
  color: var(--ink);
}

/* Container: 72rem wide, 16px gutters, 24px from 768px. */
.wrap {
  width: 100%;
  max-width: var(--canvas-max);
  margin-inline: auto;
  padding-inline: var(--gutter);
}

@media (min-width: 768px) {
  .wrap {
    padding-inline: var(--s-6);
  }
}

/* ---- Header --------------------------------------------------------- */

.site-header {
  position: sticky;
  top: 0;
  z-index: 30;
  background: var(--surface);
  border-bottom: 1px solid var(--hairline);
}

.bar {
  display: flex;
  align-items: center;
  gap: var(--s-4);
  height: var(--header-h);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 2.75rem;
  flex: none;
  color: var(--ink);
  border-radius: var(--r-md);
}

.mark {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  flex: none;
  border-radius: var(--r-md);
  background: var(--accent);
  color: var(--accent-ink);
  font: 600 0.9375rem/1 var(--font-sans);
}

.word {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  white-space: nowrap;
}

.links {
  display: none;
  align-items: center;
  gap: var(--s-1);
  flex: 1;
  min-width: 0;
}

@media (min-width: 880px) {
  .links {
    display: flex;
  }
}

.link {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  padding-inline: var(--s-3);
  border-radius: var(--r-md);
  font: var(--t-label);
  color: var(--ink-2);
  white-space: nowrap;
  transition:
    color var(--t-fast) var(--ease-out-soft),
    background-color var(--t-fast) var(--ease-out-soft);
}

.link:hover {
  color: var(--ink);
  background: var(--surface-sunken);
}

.acts {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-left: auto;
  flex: none;
}

.sign {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  padding-inline: var(--s-3);
  border-radius: var(--r-md);
  font: var(--t-label);
  color: var(--ink-2);
  transition: color var(--t-fast) var(--ease-out-soft);
}

.sign:hover {
  color: var(--ink);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* ---- Shared text ---------------------------------------------------- */

.h1 {
  font: var(--t-display);
  letter-spacing: var(--track-display);
  font-size: clamp(1.75rem, 5vw, 2.75rem);
  max-width: 24ch;
  margin-top: var(--s-3);
}

.h2 {
  font: var(--t-title-1);
  letter-spacing: var(--track-title-1);
  font-size: clamp(1.375rem, 3vw, 1.75rem);
  max-width: 28ch;
  margin-top: var(--s-2);
}

.lede {
  font: var(--t-body);
  color: var(--ink-2);
  max-width: 65ch;
  margin-top: var(--s-5);
}

.lede-sm {
  font: var(--t-body);
  color: var(--ink-2);
  max-width: 65ch;
  margin-top: var(--s-3);
}

.figure {
  font-variant-numeric: tabular-nums;
}

/* ---- Hero ----------------------------------------------------------- */

.hero {
  display: flex;
  flex-direction: column;
  gap: var(--s-10);
  padding-block: var(--s-12) var(--s-10);
}

@media (min-width: 768px) {
  .hero {
    padding-block: var(--s-16) var(--s-12);
  }
}

@media (min-width: 1024px) {
  .hero {
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--s-12);
  }

  .hero-main {
    max-width: 40rem;
  }
}

.cta {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--s-3);
  margin-top: var(--s-6);
}

@media (min-width: 480px) {
  .cta {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--s-4);
  }
}

/* Secondary text action: a link with a 44px tap target. */
.secondary {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  font: var(--t-label);
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 3px;
  border-radius: var(--r-md);
}

.secondary:hover {
  color: var(--accent-hover);
}

/* Trust strip: a bordered panel beside the hero on wide screens, stacked below it otherwise. */
.trust {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  background: var(--surface);
  overflow: hidden;
}

@media (min-width: 1024px) {
  .trust {
    width: 19rem;
    flex: none;
  }
}

.trust-item {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  padding: var(--s-4) var(--s-5);
  font: var(--t-body-sm);
  color: var(--ink-2);
}

.trust-item + .trust-item {
  border-top: 1px solid var(--hairline);
}

.trust-item svg {
  flex: none;
  margin-top: 0.125rem;
  color: var(--accent);
}

/* ---- Sections ------------------------------------------------------- */

.sec {
  padding-block: var(--s-12);
  border-top: 1px solid var(--hairline);
  scroll-margin-top: var(--header-h);
}

@media (min-width: 768px) {
  .sec {
    padding-block: var(--s-16);
  }
}

/* Steps: numbered, one column on phones, three on wider screens. */
.steps {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--s-4);
  margin-top: var(--s-8);
  counter-reset: none;
}

@media (min-width: 768px) {
  .steps {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--s-6);
  }
}

.step {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  column-gap: var(--s-3);
  row-gap: var(--s-1);
  align-items: start;
  padding: var(--s-5);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  background: var(--surface);
}

.n {
  display: grid;
  place-items: center;
  grid-row: span 2;
  width: 2rem;
  height: 2rem;
  border-radius: var(--r-md);
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
  font: var(--t-label);
  font-weight: 600;
}

.st {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
}

.sd {
  font: var(--t-body-sm);
  color: var(--ink-2);
  max-width: 65ch;
  grid-column: 2;
}

/* Scope: two panels, stacked on phones. */
.scope {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--s-4);
  margin-top: var(--s-8);
}

@media (min-width: 768px) {
  .scope {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--s-6);
  }
}

.panel {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-6);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  background: var(--surface);
}

.pt {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  padding-bottom: var(--s-3);
  border-bottom: 1px solid var(--hairline);
}

.plist {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  font: var(--t-body-sm);
  color: var(--ink-2);
}

.plist li {
  position: relative;
  padding-left: var(--s-5);
}

.plist li::before {
  content: "";
  position: absolute;
  left: 0.25rem;
  top: 0.55rem;
  width: 0.375rem;
  height: 0.375rem;
  border-radius: var(--r-full);
  background: var(--ink-3);
}

/* Categories: two columns from 768px. */
.kats {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--s-3);
  margin-top: var(--s-8);
}

@media (min-width: 768px) {
  .kats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--s-4);
  }
}

.kat {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-3);
  min-width: 0;
  padding: var(--s-5);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  background: var(--surface);
}

.kt {
  font: var(--t-body-sm);
  color: var(--ink-2);
  max-width: 65ch;
}

.batas {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-6);
  padding: var(--s-5);
  border: 1px solid var(--accent-line);
  border-radius: var(--r-lg);
  background: var(--accent-soft);
}

.bh {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--accent-soft-ink);
}

.bt {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  color: var(--accent-soft-ink);
}

.bd {
  font: var(--t-body-sm);
  color: var(--accent-soft-ink);
  max-width: 65ch;
}

.stamp {
  margin-top: var(--s-6);
}

/* FAQ: native disclosure, full-width rows with 44px summaries. */
.faq {
  display: flex;
  flex-direction: column;
  margin-top: var(--s-8);
  max-width: 48rem;
  border-top: 1px solid var(--hairline);
}

.qa {
  border-bottom: 1px solid var(--hairline);
}

.qa summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  min-height: 2.75rem;
  padding-block: var(--s-3);
  font: var(--t-title-3);
  font-size: 1rem;
  letter-spacing: var(--track-title-3);
  cursor: pointer;
  list-style: none;
  border-radius: var(--r-sm);
}

.qa summary::-webkit-details-marker {
  display: none;
}

.qa summary::after {
  content: "+";
  flex: none;
  font: var(--t-title-2);
  color: var(--ink-3);
  line-height: 1;
}

.qa[open] summary::after {
  content: "−";
}

.qa summary:hover {
  color: var(--accent);
}

.qa p {
  font: var(--t-body-sm);
  color: var(--ink-2);
  max-width: 65ch;
  padding-bottom: var(--s-4);
}

/* ---- Closing band --------------------------------------------------- */

.closing {
  padding-block: var(--s-10) var(--s-12);
  border-top: 1px solid var(--hairline);
}

.closing-in {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  padding: var(--s-6);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  background: var(--surface);
}

@media (min-width: 768px) {
  .closing-in {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: var(--s-10);
  }
}

.closing-in .cta {
  margin-top: 0;
}

.closing-text .h2 {
  margin-top: 0;
}

.closing-text .lede-sm {
  margin-top: var(--s-2);
}

/* ---- Footer --------------------------------------------------------- */

.site-footer {
  margin-top: auto;
  background: var(--surface);
  border-top: 1px solid var(--hairline);
}

.foot {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding-block: var(--s-8);
}

@media (min-width: 768px) {
  .foot {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
  }
}

.fg {
  font: var(--t-label);
  font-weight: 600;
}

.fn {
  font: var(--t-body-sm);
  color: var(--ink-3);
  margin-top: var(--s-1);
}

.foot-links {
  display: flex;
  gap: var(--s-5);
  font: var(--t-label);
}

.foot-links a {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  color: var(--ink-2);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.foot-links a:hover {
  color: var(--ink);
}

.foot-note {
  flex-basis: 100%;
}

@media (min-width: 768px) {
  .foot-note {
    flex-basis: auto;
  }
}
</style>
