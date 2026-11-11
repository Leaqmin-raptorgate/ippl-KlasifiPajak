<script setup lang="ts">
/** Explicit AI processing choice for the assistant and receipt upload (FR-27). */
import { ref } from "vue";
import { ApiFailure } from "@/lib/api";
import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
const sibuk = ref(false);
const pesan = ref("");

const TEKS_PERSETUJUAN = [
  "Saya menyetujui pengiriman data ke layanan AI di luar aplikasi, hanya untuk fitur yang saya pakai:",
  "• Klasifikasi: deskripsi transaksi, nominal, nama klien (hanya jika berbentuk badan usaha), status NIB, kode KBLI, dan kategori transaksi sebelumnya.",
  "• Baca struk (OCR): seluruh foto struk, termasuk apa pun yang tercetak di dalamnya. Metadata foto dihapus.",
  "• Asisten: pertanyaan yang saya ketik, serta tanggal, nominal dan kategori transaksi, data profil pajak (termasuk status pasangan dan angka peredaran), dan ringkasan bulanan. Deskripsi transaksi, nomor faktur dan nama klien tidak dikirim ke asisten.",
  "Saya dapat mencabut persetujuan kapan saja di Profil. Fitur AI tidak dapat dipakai tanpa persetujuan ini.",
].join("\n");

async function ubah(event: Event) {
  const input = event.target;
  if (!(input instanceof HTMLInputElement)) return;
  const next = input.checked;
  sibuk.value = true;
  pesan.value = "";
  try {
    await session.aturPersetujuanAi(next);
  } catch (error) {
    input.checked = session.persetujuanAi;
    pesan.value = error instanceof ApiFailure ? error.message : "Persetujuan belum tersimpan.";
  } finally {
    sibuk.value = false;
  }
}
</script>

<template>
  <div class="catatan">
    <label class="pilihan">
      <input type="checkbox" :checked="session.persetujuanAi" :disabled="sibuk" @change="ubah" />
      <span class="naskah">{{ TEKS_PERSETUJUAN }}</span>
    </label>
    <p v-if="pesan" class="pesan" role="alert">{{ pesan }}</p>
  </div>
</template>

<style scoped>
.catatan {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.pilihan {
  display: flex;
  align-items: flex-start;
  gap: var(--s-2);
  font: var(--t-body-sm);
  color: var(--ink-2);
  cursor: pointer;
  line-height: 1.4;
}

.pilihan input {
  margin-top: 0.1875rem;
  flex: none;
}

.naskah {
  white-space: pre-line;
}

.pesan {
  font: var(--t-body-sm);
  color: var(--cat-ask-ink);
  line-height: 1.4;
}
</style>
