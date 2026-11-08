<script setup lang="ts">
/** Explicit AI processing choice for the assistant and receipt upload (FR-27). */
import { ref } from "vue";
import { ApiFailure } from "@/lib/api";
import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
const sibuk = ref(false);
const pesan = ref("");

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
      <span>
        Saya setuju deskripsi transaksi atau foto struk diproses oleh model yang dikonfigurasi.
        Persetujuan pemrosesan AI diperlukan sebelum fitur ini digunakan.
      </span>
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

.pesan {
  font: var(--t-body-sm);
  color: var(--cat-ask-ink);
  line-height: 1.4;
}
</style>
