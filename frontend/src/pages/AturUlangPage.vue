<script setup lang="ts">
/** Password reset request, and confirm when a token is in the query. */
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppField from "@/components/ui/AppField.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
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
const berhasilReset = ref(false);

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
      pesan.value = `${hasil.message} Silakan masuk kembali dengan kata sandi baru Anda.`;
      berhasilReset.value = true;
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
  <div class="page atur-ulang">
    <header class="top">
      <RouterLink to="/" class="brand">
        <span class="mark" aria-hidden="true">K</span>
        <span class="word">KlasifiPajak</span>
      </RouterLink>
      <RouterLink to="/masuk" class="back">
        <AppIcon name="chevronLeft" :size="15" :stroke-width="1.8" />
        Masuk
      </RouterLink>
    </header>

    <main class="stage">
      <form class="card kp-materialize" @submit.prevent="kirim">
        <h1 class="h1">{{ token ? "Kata sandi baru" : "Atur ulang kata sandi" }}</h1>
        <p v-if="pesan" class="pesan" role="status">{{ pesan }}</p>
        <p v-if="galat" class="galat" role="alert">{{ galat }}</p>
        <template v-if="!berhasilReset">
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
        </template>
        <AppButton v-else to="/masuk" variant="primary" block> Masuk sekarang </AppButton>
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
.atur-ulang {
  padding: var(--s-4) var(--s-4) calc(var(--s-8) + var(--safe-b));
}
@media (min-width: 768px) {
  .atur-ulang {
    padding: var(--s-6) var(--s-6) var(--s-10);
  }
}
@media (min-width: 1280px) {
  .atur-ulang {
    padding-inline: var(--s-10);
  }
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  min-height: var(--topbar-h);
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 2.5rem;
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
}
.word {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  white-space: nowrap;
}
.back {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  min-height: 2.5rem;
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--ink-2);
  transition: color var(--t-fast) var(--ease-out-soft);
}
.back:hover {
  color: var(--ink);
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
  box-shadow: var(--shadow-2);
}
.h1 {
  font: var(--t-title-1);
  letter-spacing: var(--track-title-1);
}
.pesan {
  font: var(--t-body-sm);
  color: var(--cat-usaha-ink);
  background: var(--cat-usaha-bg);
  border: 1px solid var(--cat-usaha-line);
  padding: var(--s-3);
  border-radius: var(--r-md);
  line-height: 1.45;
}
.galat {
  font: var(--t-body-sm);
  color: var(--danger, var(--ink));
  background: var(--cat-ask-bg);
  border: 1px solid var(--cat-ask-line);
  padding: var(--s-3);
  border-radius: var(--r-md);
  line-height: 1.45;
}
.kembali {
  font: var(--t-body-sm);
  color: var(--ink-2);
  text-align: center;
  margin-top: var(--s-2);
}
.kembali:hover {
  color: var(--ink);
}
</style>
