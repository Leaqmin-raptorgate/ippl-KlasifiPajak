<script setup lang="ts">
/** Marketing page: what the tool does, the three steps, and the four categories. */
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
</script>

<template>
  <div class="page">
    <header class="bar">
      <div class="bar-in">
        <RouterLink to="/" class="brand">
          <span class="mark" aria-hidden="true">K</span>
          <span class="word">KlasifiPajak</span>
        </RouterLink>

        <nav class="links" aria-label="Bagian halaman">
          <a href="#fitur" class="link">Fitur</a>
          <a href="#regulasi" class="link">Dasar regulasi</a>
          <a href="#mulai" class="link">Harga</a>
        </nav>

        <div class="acts">
          <RouterLink to="/masuk" class="sign">Masuk</RouterLink>
          <AppButton to="/masuk" variant="primary">Mulai gratis</AppButton>
        </div>
      </div>
    </header>

    <section class="hero" aria-labelledby="h-utama">
      <p class="u-eyebrow">Kertas kerja PPh Final UMKM</p>
      <h1 id="h-utama" class="h1">
        Setiap transaksi masuk diklasifikasi sendiri, lalu PPh Final dihitung dari klasifikasi itu.
      </h1>
      <p class="lede">
        KlasifiPajak memisahkan omzet usaha, pekerjaan bebas, penghasilan yang sudah berstatus
        final, dan yang bukan objek pajak. Baris yang ambigu ditanyakan, bukan ditebak. Yang keluar
        adalah kertas kerja yang bisa Anda telusuri sampai ke sumber tiap klasifikasi.
      </p>

      <div class="cta">
        <AppButton to="/masuk" variant="primary" size="lg" icon-end="arrowRight">
          Mulai gratis
        </AppButton>
      </div>

      <ul class="facts">
        <li v-for="f in fakta" :key="f.teks" class="fact">
          <AppIcon :name="f.icon" :size="16" :stroke-width="1.7" />
          <span>{{ f.teks }}</span>
        </li>
      </ul>
    </section>

    <section id="fitur" class="sec" aria-labelledby="h-fitur">
      <p class="u-eyebrow">Cara kerjanya</p>
      <h2 id="h-fitur" class="h2">Tiga langkah, tanpa tebakan.</h2>
      <p class="lede-sm">
        Tidak ada tombol "hitung sekarang" yang menggabungkan semua baris jadi satu. Urutannya
        tetap: catat, klasifikasi, baru hitung.
      </p>

      <ol class="steps">
        <li v-for="(s, i) in langkah" :key="s.judul" class="step">
          <span class="n figure" aria-hidden="true">{{ i + 1 }}</span>
          <div class="isi">
            <h3 class="st">{{ s.judul }}</h3>
            <p class="sd">{{ s.deskripsi }}</p>
          </div>
        </li>
      </ol>
    </section>

    <section id="regulasi" class="sec" aria-labelledby="h-kategori">
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
          Batas tahunan tersebut dipakai kategori Usaha saja. Pekerjaan bebas tidak memakainya, jadi
          kedua jenis penghasilan itu tidak saling mengurangi. Di atas batas itu, tarif PPh Final
          usaha menjadi
          {{ PUBLIC_RULESET.tarifLabel }}.
        </p>
      </aside>
      <WorkpaperNote publik class="stamp" />
    </section>

    <section id="mulai" class="band" aria-labelledby="h-mulai">
      <p class="u-eyebrow">Mulai gratis</p>
      <h2 id="h-mulai" class="h2">Mulai dari satu transaksi.</h2>
      <p class="lede-sm">
        Buat akun, catat mutasi masuk pertama, dan lihat kertas kerjanya terbentuk.
      </p>
      <div class="cta">
        <AppButton to="/masuk" variant="primary" size="lg" icon-end="arrowRight">
          Mulai gratis
        </AppButton>
      </div>
    </section>

    <footer class="foot">
      <p class="fg">KlasifiPajak</p>
      <p class="fn">Kertas kerja pajak untuk UMKM. Bukan software resmi DJP.</p>
    </footer>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  max-width: var(--canvas-max);
  margin-inline: auto;
  /* Bare route: no shell, so the page owns the canvas and the gutters. */
  background: var(--canvas);
  padding-inline: var(--s-4);
  padding-bottom: var(--s-12);
}

@media (min-width: 768px) {
  .page {
    padding-inline: var(--s-6);
    padding-bottom: var(--s-16);
  }
}

@media (min-width: 1280px) {
  .page {
    padding-inline: var(--s-8);
  }
}

/* ---- Top bar ---------------------------------------------------------- */

.bar {
  position: sticky;
  top: 0;
  z-index: 30;
  margin-inline: calc(var(--s-4) * -1);
  background: var(--material-bar);
  backdrop-filter: var(--blur-bar);
  box-shadow: 0 0.5px 0 var(--material-bar-line);
}

@media (min-width: 768px) {
  .bar {
    margin-inline: calc(var(--s-6) * -1);
  }
}

@media (min-width: 1280px) {
  .bar {
    margin-inline: calc(var(--s-8) * -1);
  }
}

.bar-in {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  height: var(--topbar-h);
  padding-inline: var(--s-4);
}

@media (min-width: 768px) {
  .bar-in {
    gap: var(--s-4);
    height: 3.5rem;
    padding-inline: var(--s-6);
  }
}

@media (min-width: 1280px) {
  .bar-in {
    padding-inline: var(--s-8);
  }
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 2.5rem;
  flex: none;
}

.mark {
  display: grid;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  flex: none;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--accent-ink);
  font: 600 0.875rem/1 var(--font-sans);
  letter-spacing: 0;
}

.word {
  font: var(--t-body);
  font-weight: 600;
  letter-spacing: var(--track-body);
  white-space: nowrap;
}

@media (min-width: 768px) {
  .word {
    font: var(--t-title-3);
    letter-spacing: var(--track-title-3);
  }
}

.links {
  display: none;
  align-items: center;
  gap: var(--s-5);
}

@media (min-width: 768px) {
  .links {
    display: flex;
    gap: var(--s-6);
  }
}

.link {
  display: inline-flex;
  align-items: center;
  min-height: 2.5rem;
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--ink-2);
  transition: color var(--t-fast) var(--ease-out-soft);
}

.link:hover {
  color: var(--ink);
}

.acts {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex: none;
}

@media (min-width: 768px) {
  .acts {
    gap: var(--s-4);
  }
}

.sign {
  display: inline-flex;
  align-items: center;
  min-height: 2.5rem;
  padding-inline: var(--s-2);
  border-radius: var(--r-md);
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--ink-2);
  transition: color var(--t-fast) var(--ease-out-soft);
}

.sign:hover {
  color: var(--ink);
}

/* ---- Hero ------------------------------------------------------------- */

.hero {
  padding-block: var(--s-12) var(--s-10);
}

@media (min-width: 768px) {
  .hero {
    padding-block: var(--s-20) var(--s-16);
  }
}

/* Wide screens get a real second column rather than a decorative one: the
   promises move out of a bottom rule and into their own stack, so the headline
   keeps a readable measure and the page stops trailing off into whitespace. */
@media (min-width: 1024px) {
  .hero {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 20rem;
    align-items: start;
    gap: var(--s-10);
  }

  .hero > .u-eyebrow,
  .hero > .h1,
  .hero > .lede,
  .hero > .cta {
    grid-column: 1;
  }

  .hero > .u-eyebrow {
    grid-row: 1;
  }

  .hero > .h1 {
    grid-row: 2;
  }

  .hero > .lede {
    grid-row: 3;
  }

  .hero > .cta {
    grid-row: 4;
  }

  .hero > .facts {
    grid-column: 2;
    grid-row: 1 / -1;
    align-self: start;
    flex-direction: column;
    gap: var(--s-4);
    margin-top: 0;
    padding-top: 0;
    padding-left: var(--s-6);
    border-top: 0;
    border-left: 1px solid var(--hairline);
  }
}

.h1 {
  font: var(--t-display);
  letter-spacing: var(--track-display);
  font-size: clamp(1.75rem, 5.2vw, 3.25rem);
  max-width: 34rem;
  margin-top: var(--s-3);
}

@media (min-width: 768px) {
  .h1 {
    max-width: 38rem;
  }
}

.lede {
  font: var(--t-body);
  color: var(--ink-2);
  max-width: 38rem;
  margin-top: var(--s-5);
}

@media (min-width: 768px) {
  .lede {
    font-size: 1.0625rem;
    margin-top: var(--s-6);
  }
}

.cta {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-6);
}

@media (min-width: 560px) {
  .cta {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
  }
}

.facts {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-10);
  padding-top: var(--s-5);
  border-top: 1px solid var(--hairline);
}

@media (min-width: 768px) {
  .facts {
    flex-direction: row;
    flex-wrap: wrap;
    gap: var(--s-3) var(--s-8);
  }
}

.fact {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-width: 0;
  font: var(--t-body-sm);
  color: var(--ink-2);
}

.fact svg {
  color: var(--ink-3);
}

/* ---- Sections --------------------------------------------------------- */

.sec {
  padding-block: var(--s-10);
  scroll-margin-top: calc(var(--topbar-h) + var(--s-4));
}

@media (min-width: 768px) {
  .sec {
    padding-block: var(--s-16);
    scroll-margin-top: calc(3.5rem + var(--s-6));
  }
}

.h2 {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
  font-size: clamp(1.25rem, 2.6vw, 1.625rem);
  max-width: 30rem;
  margin-top: var(--s-2);
}

.lede-sm {
  font: var(--t-body);
  color: var(--ink-2);
  max-width: 40rem;
  margin-top: var(--s-3);
}

.steps {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--s-6);
  margin-top: var(--s-8);
}

@media (min-width: 768px) {
  .steps {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--s-6);
  }
}

.step {
  display: flex;
  gap: var(--s-3);
  min-width: 0;
  padding-top: var(--s-4);
  border-top: 1px solid var(--hairline);
}

.n {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  flex: none;
  border-radius: var(--r-sm);
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
  font: var(--t-label);
  font-weight: 600;
}

.isi {
  min-width: 0;
}

.st {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
}

.sd {
  font: var(--t-body-sm);
  color: var(--ink-2);
  margin-top: var(--s-1);
}

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
  padding: var(--s-4);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  background: var(--surface);
}

.kt {
  font: var(--t-body-sm);
  color: var(--ink-2);
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
  max-width: 46rem;
}

.stamp {
  margin-top: var(--s-4);
}

/* ---- Closing band ------------------------------------------------------ */

.band {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: var(--s-6);
  border: 1px solid var(--hairline);
  border-radius: var(--r-2xl);
  background: var(--surface);
  box-shadow: var(--shadow-2);
  scroll-margin-top: calc(var(--topbar-h) + var(--s-4));
}

@media (min-width: 768px) {
  .band {
    padding: var(--s-10);
    scroll-margin-top: calc(3.5rem + var(--s-6));
  }
}

.band .cta {
  margin-top: var(--s-2);
}

/* ---- Footer ------------------------------------------------------------ */

.foot {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding-top: var(--s-6);
  border-top: 1px solid var(--hairline);
}

@media (min-width: 768px) {
  .foot {
    flex-direction: row;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-4);
  }
}

.fg {
  font: var(--t-label);
  font-weight: 600;
  letter-spacing: var(--track-label);
}

.fn {
  font: var(--t-body-sm);
  color: var(--ink-3);
}
</style>
