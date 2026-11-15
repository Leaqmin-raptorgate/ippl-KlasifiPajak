<script setup lang="ts">
/** Read-only assistant. The answer and the remaining quota come from the API. */
import { computed, onMounted, ref, watch } from "vue";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppField from "@/components/ui/AppField.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppPill from "@/components/ui/AppPill.vue";
import AiConsentNote from "@/components/app/AiConsentNote.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure, api } from "@/lib/api";
import { CAPABILITIES } from "@/lib/capabilities";
import { useKuotaStore } from "@/stores/kuota";
import { useSessionStore } from "@/stores/session";
import type { AssistantAnswer } from "@/lib/wire";

const session = useSessionStore();
const kuota = useKuotaStore();

const tanya = ref("");
const berpikir = ref(false);
const galat = ref("");
const jawaban = ref<AssistantAnswer | null>(null);
const pertanyaanTerakhir = ref("");

const chat = computed(() => kuota.quotas?.assistant_chat);
const sisa = computed(() => (chat.value ? Math.max(0, chat.value.limit - chat.value.used) : 0));
const habis = computed(() => chat.value?.status === "exhausted");

const pertanyaanSiap = [
  "Kenapa transaksi saya masuk kategori pekerjaan bebas, bukan usaha?",
  "Apakah batas bebas usaha juga dipakai oleh pekerjaan bebas?",
  "Berapa sisa bayar pajak saya untuk bulan ini?",
];

onMounted(() => {
  void kuota.muat();
});

// The consent alert is only true until consent is saved.
watch(
  () => session.persetujuanAi,
  (setuju) => {
    if (setuju && galat.value.startsWith("Persetujuan")) galat.value = "";
  },
);

async function kirim() {
  const teks = tanya.value.trim();
  if (!teks || berpikir.value || habis.value) return;
  if (!session.persetujuanAi) {
    galat.value = "Persetujuan pemrosesan AI diperlukan sebelum fitur ini digunakan.";
    return;
  }
  berpikir.value = true;
  galat.value = "";
  jawaban.value = null;
  pertanyaanTerakhir.value = teks;
  tanya.value = "";
  try {
    jawaban.value = await api<AssistantAnswer>("/assistant/query", {
      method: "POST",
      body: JSON.stringify({ question: teks }),
    });
    await kuota.muat();
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Asisten belum tersedia.";
  } finally {
    berpikir.value = false;
  }
}

function isiPertanyaan(teks: string) {
  tanya.value = teks;
}
</script>

<template>
  <div class="page">
    <div class="col">
      <header class="lede">
        <div class="lede-teks">
          <p class="sub">
            Halo {{ session.tampilanNama }}. Asisten ini menjelaskan kertas kerja yang sudah Anda
            punya: kategori, dasar aturan, dan alasan di baliknya. Ia tidak menghitung apa pun yang
            baru, tidak mengubah klasifikasi, dan tidak mengirim apa pun ke DJP.
          </p>
        </div>
        <div v-if="CAPABILITIES.assistantChat" class="kuota">
          <AppPill
            :tone="sisa <= 2 ? 'ask' : 'accent'"
            icon="kuota"
            :label="chat ? `${sisa} dari ${chat.limit} jawaban bulan ini` : 'Kuota belum dimuat'"
          />
        </div>
      </header>

      <AppCard
        v-if="CAPABILITIES.assistantChat"
        title="Tanya kertas kerja Anda"
        subtitle="Jawabannya disusun dari baris yang tersimpan, lalu ditampilkan di halaman ini."
      >
        <div class="form">
          <div class="info">
            <AiConsentNote />
          </div>

          <div class="thread" role="log" aria-live="polite" aria-label="Percakapan dengan asisten">
            <p v-if="!pertanyaanTerakhir" class="thread-kosong">
              Belum ada pertanyaan. Tulis pertanyaan di bawah, atau pilih salah satu contoh.
            </p>

            <div v-if="pertanyaanTerakhir" class="pesan pesan-anda">
              <p class="pesan-label">Anda</p>
              <p class="pesan-isi">{{ pertanyaanTerakhir }}</p>
            </div>

            <div v-if="berpikir" class="berpikir" role="status">
              <span class="jalur" aria-hidden="true"><span class="sweep kp-sweep" /></span>
              <span class="berpikir-teks">Menyusun penjelasan dari kertas kerja…</span>
            </div>

            <div v-if="jawaban" class="pesan pesan-asisten">
              <p class="pesan-label">Asisten</p>
              <p class="pesan-isi">{{ jawaban.answer }}</p>
              <ul v-if="jawaban.citations.length" class="sitasi">
                <li v-for="sitasi in jawaban.citations" :key="sitasi">{{ sitasi }}</li>
              </ul>
              <p class="pesan-meta">Sisa kuota jawaban: {{ jawaban.quota_remaining }}</p>
            </div>

            <p v-if="galat" class="info info-galat" role="alert">{{ galat }}</p>
            <p v-if="habis" class="info info-galat">
              Kuota bulan ini sudah habis. Kertas kerja Anda tetap terbaca di halaman transaksi.
            </p>
          </div>

          <div class="composer">
            <AppField
              label="Pertanyaan Anda"
              for-id="tanya-asisten"
              hint="Satu pertanyaan. Jawaban memakai angka yang sudah ada di kertas kerja."
            >
              <textarea
                id="tanya-asisten"
                v-model="tanya"
                class="ta"
                rows="4"
                placeholder="mis. kenapa baris saya masuk pekerjaan bebas?"
                @keydown.meta.enter.prevent="kirim"
                @keydown.ctrl.enter.prevent="kirim"
              />
            </AppField>

            <div class="aksi">
              <AppButton
                variant="primary"
                size="lg"
                icon="obrolan"
                :disabled="tanya.trim() === '' || berpikir || habis"
                @click="kirim"
              >
                Kirim pertanyaan
              </AppButton>
              <p class="demo-note">Jawaban tidak disimpan sebagai arsip percakapan.</p>
            </div>
          </div>
        </div>
      </AppCard>

      <AppCard
        v-if="CAPABILITIES.assistantChat"
        title="Pertanyaan yang sering diajukan"
        subtitle="Ketuk satu untuk mengisi kolom di atas."
      >
        <div class="saran">
          <button
            v-for="q in pertanyaanSiap"
            :key="q"
            type="button"
            class="saran-item press"
            @click="isiPertanyaan(q)"
          >
            <AppIcon name="chevronRight" :size="15" :stroke-width="1.8" />
            <span>{{ q }}</span>
          </button>
        </div>
      </AppCard>

      <AppCard
        v-if="!CAPABILITIES.assistantChat"
        title="Tanya kertas kerja"
        subtitle="Layanan asisten interaktif saat ini belum diaktifkan pada server ini."
      >
        <div class="belum-aktif">
          <p class="belum-aktif-teks">
            Fitur tanya-jawab asisten berbasis model bahasa sedang dalam tahap penyiapan. Kertas
            kerja dan ringkasan pajak Anda tetap dapat dipantau langsung melalui dasbor dan daftar
            transaksi.
          </p>
          <div class="belum-aktif-aksi">
            <AppButton to="/dasbor" variant="outline" icon="dasbor"> Buka dasbor pajak </AppButton>
            <AppButton to="/transaksi" variant="outline" icon="transaksi">
              Buka daftar transaksi
            </AppButton>
          </div>
        </div>
      </AppCard>

      <AppCard class="batas-ases" inset>
        <div class="batas-isi">
          <span class="batas-ic"><AppIcon name="info" :size="18" /></span>
          <div>
            <p class="batas-judul">Asisten hanya membaca</p>
            <p class="batas-sub">
              Semua yang tampil di halaman ini dibaca dari transaksi yang sudah tersimpan dan dari
              kertas kerja yang sudah tersimpan. Tidak ada hitungan baru, tidak ada pengajuan, dan
              tidak ada kewajiban yang muncul dari sini.
            </p>
          </div>
        </div>
      </AppCard>

      <WorkpaperNote />
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  max-width: var(--canvas-max);
  margin-inline: auto;
}

/* A reading column. The canvas is wider than a paragraph wants to run. */
.col {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  width: 100%;
  max-width: 48rem;
  /* Left-aligned with the page title the shell renders above it. */
  margin-inline: 0;
}

.lede {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-4);
  flex-wrap: wrap;
}

.lede-teks {
  min-width: 0;
}

.t1 {
  font: var(--t-title-1);
  letter-spacing: var(--track-title-1);
}

.sub {
  font: var(--t-body);
  color: var(--ink-2);
  max-width: 38rem;
  margin-top: var(--s-2);
}

.kuota {
  flex: none;
}

.form {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

/* ---- Regular information blocks: consent, quota, errors ---------------- */

.info {
  padding: var(--s-3) var(--s-4);
  border: 1px solid var(--hairline);
  border-radius: var(--r-md);
  background: var(--surface-sunken);
  color: var(--ink-2);
  font: var(--t-body-sm);
  line-height: 1.5;
}

.info-galat {
  border-color: var(--cat-ask-line);
  background: var(--cat-ask-bg);
  color: var(--cat-ask-ink);
}

/* ---- Conversation panel ------------------------------------------------ */

/* A bordered panel on the page, not a chat surface pinned to the screen. */
.thread {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  min-height: 8rem;
  padding: var(--s-4);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--r-lg);
  background: var(--canvas);
}

.thread-kosong {
  margin: auto 0;
  color: var(--ink-3);
  font: var(--t-body-sm);
  line-height: 1.5;
}

.pesan {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-4);
  border: 1px solid var(--hairline);
  border-radius: var(--r-md);
  background: var(--surface);
  max-width: 100%;
}

/* The user's turn is tinted with the accent and carries its own label. */
.pesan-anda {
  background: var(--accent-soft);
  border-color: var(--accent-line);
}

.pesan-label {
  font: var(--t-label-sm);
  letter-spacing: var(--track-label-sm);
  font-weight: 600;
  color: var(--ink-2);
}

.pesan-anda .pesan-label {
  color: var(--accent-soft-ink);
}

.pesan-isi {
  font: var(--t-body);
  color: var(--ink);
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.pesan-meta {
  font: var(--t-body-sm);
  color: var(--ink-3);
}

.sitasi {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding-top: var(--s-3);
  border-top: 1px solid var(--hairline);
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}

@media (min-width: 640px) {
  .pesan-anda {
    width: min(100%, 36rem);
    margin-left: auto;
  }
}

.berpikir {
  display: flex;
  align-items: center;
  gap: var(--s-3);
}

.jalur {
  position: relative;
  display: block;
  flex: 1;
  max-width: 14rem;
  height: 0.375rem;
  border-radius: var(--r-full);
  background: var(--surface-sunken);
  border: 1px solid var(--hairline);
  overflow: clip;
}

.sweep {
  display: block;
  width: 30%;
  height: 100%;
  border-radius: var(--r-full);
  background: var(--accent);
}

.berpikir-teks {
  font: var(--t-body-sm);
  color: var(--ink-2);
}

/* ---- Composer ---------------------------------------------------------- */

.composer {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

/* Same shell as AppInput, so a textarea does not read as a different control. */
.ta {
  width: 100%;
  min-height: 2.75rem;
  padding: 0.6875rem var(--s-3);
  background: var(--surface);
  border: 1px solid var(--field-line);
  border-radius: var(--r-md);
  font: var(--t-body);
  letter-spacing: var(--track-body);
  resize: vertical;
  transition:
    border-color var(--t-fast) var(--ease-out-soft),
    box-shadow var(--t-fast) var(--ease-out-soft);
}

.ta::placeholder {
  color: var(--ink-3);
}

.ta:focus {
  border-color: var(--focus);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--focus) 20%, transparent);
}

/* A phone must not zoom the page when the field is focused. */
@media (max-width: 767px) {
  .ta {
    font-size: 1rem;
    line-height: 1.45;
  }
}

.aksi {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--s-3);
}

.aksi > :first-child {
  align-self: stretch;
}

.demo-note {
  font: var(--t-body-sm);
  color: var(--ink-3);
  line-height: 1.5;
  max-width: 34rem;
}

@media (min-width: 640px) {
  .aksi {
    flex-direction: row;
    align-items: center;
    gap: var(--s-4);
  }

  .aksi > :first-child {
    align-self: auto;
  }

  /* The button keeps its intrinsic width; the prose beside it has to be allowed
     to shrink, or it pushes past the card edge on a tablet. */
  .demo-note {
    flex: 1 1 auto;
    min-width: 0;
  }
}

/* ---- Suggestions ------------------------------------------------------- */

.saran {
  display: grid;
  gap: var(--s-2);
}

.saran-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 2.75rem;
  padding: var(--s-3);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--r-md);
  background: var(--surface);
  font: var(--t-body-sm);
  color: var(--ink);
  line-height: 1.45;
  text-align: left;
  transition:
    border-color var(--t-fast) var(--ease-out-soft),
    color var(--t-fast) var(--ease-out-soft),
    background-color var(--t-fast) var(--ease-out-soft);
}

.saran-item:hover {
  border-color: var(--accent-line);
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
}

.saran-item svg {
  flex: none;
  color: var(--ink-3);
}

.saran-item:hover svg {
  color: var(--accent-soft-ink);
}

/* ---- Read-only notice -------------------------------------------------- */

.batas-isi {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
}

.batas-ic {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  flex: none;
  border-radius: var(--r-full);
  background: var(--surface);
  border: 1px solid var(--hairline);
  color: var(--ink-3);
}

.batas-judul {
  font: var(--t-label);
  letter-spacing: var(--track-label);
  font-weight: 600;
  color: var(--ink);
}

.batas-sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
  margin-top: var(--s-1);
}

/* ---- Not enabled on this server --------------------------------------- */

.belum-aktif {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.belum-aktif-teks {
  font: var(--t-body);
  color: var(--ink-2);
  line-height: 1.5;
}

.belum-aktif-aksi {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3);
}

.form :deep(.lab .u-label) {
  font: var(--t-label);
  letter-spacing: var(--track-label);
}

@media (prefers-reduced-motion: reduce) {
  .sweep {
    display: none;
  }
}
</style>
