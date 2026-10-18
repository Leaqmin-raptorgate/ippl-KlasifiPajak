<script setup lang="ts">
/** Password reset request, and confirm when a token is in the query. */
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppField from "@/components/ui/AppField.vue";
import AppInput from "@/components/ui/AppInput.vue";
import { ApiFailure } from "@/lib/api";
import { useSessionStore } from "@/stores/session";

const route = useRoute();
const session = useSessionStore();

const token = computed(() => {
  const raw = route.query.token;
  return Array.isArray(raw) ? (raw[0] ?? "") : (raw ?? "");
});
const email = ref("");
const sandi = ref("");
const pesan = ref("");
const galat = ref("");
const sibuk = ref(false);

async function kirim() {
  galat.value = "";
  pesan.value = "";
  sibuk.value = true;
  try {
    if (token.value) {
      if (sandi.value.length < 10) {
        galat.value = "Kata sandi baru harus memiliki panjang minimal 10 karakter.";
        return;
      }
      const hasil = await session.konfirmasiReset(token.value, sandi.value);
      pesan.value = `${hasil.message} Silakan masuk kembali.`;
      return;
    }
    const hasil = await session.mintaReset(email.value.trim());
    pesan.value = hasil.message;
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Permintaan gagal. Coba lagi.";
  } finally {
    sibuk.value = false;
  }
}
</script>

<template>
  <div class="page">
    <main class="stage">
      <form class="card" @submit.prevent="kirim">
        <h1 class="h1">{{ token ? "Kata sandi baru" : "Atur ulang kata sandi" }}</h1>
        <p v-if="pesan" class="pesan" role="status">{{ pesan }}</p>
        <p v-if="galat" class="galat" role="alert">{{ galat }}</p>
        <AppField v-if="!token" label="Surel" for-id="reset-email">
          <AppInput id="reset-email" v-model="email" type="email" autocomplete="email" required />
        </AppField>
        <AppField v-else label="Kata sandi baru" for-id="reset-sandi" hint="Minimal 10 karakter.">
          <AppInput
            id="reset-sandi"
            v-model="sandi"
            type="password"
            autocomplete="new-password"
            required
          />
        </AppField>
        <AppButton type="submit" variant="primary" block :disabled="sibuk">
          {{ token ? "Simpan kata sandi" : "Kirim petunjuk" }}
        </AppButton>
        <RouterLink to="/masuk" class="kembali">Kembali ke masuk</RouterLink>
      </form>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100svh;
  background: var(--canvas);
  display: flex;
  flex-direction: column;
}
.stage {
  flex: 1;
  display: grid;
  place-items: center;
  padding: var(--s-6);
}
.card {
  width: min(100%, 24rem);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-6);
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
}
.h1 {
  font: var(--t-title-1);
  letter-spacing: var(--track-title-1);
}
.pesan,
.galat,
.kembali {
  font: var(--t-body-sm);
}
.galat {
  color: var(--danger, var(--ink));
}
</style>
