<script setup lang="ts">
/** Password reset request, and confirm when a token is in the query. */
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppField from "@/components/ui/AppField.vue";
import AppInput from "@/components/ui/AppInput.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
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
  <div class="atur-ulang">
    <main class="stage">
      <RouterLink to="/" class="brand" aria-label="KlasifiPajak, beranda">
        <span class="mark" aria-hidden="true">K</span>
        <span class="word">KlasifiPajak</span>
      </RouterLink>

      <form class="card" @submit.prevent="kirim">
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
          <AppButton type="submit" variant="primary" size="lg" block :disabled="sibuk">
            {{ token ? "Simpan kata sandi" : "Kirim petunjuk" }}
          </AppButton>
        </template>
        <AppButton v-else to="/masuk" variant="primary" size="lg" block> Masuk sekarang </AppButton>
        <RouterLink to="/masuk" class="helper">Kembali ke masuk</RouterLink>
      </form>

      <WorkpaperNote publik class="foot-note" />
    </main>
  </div>
</template>

<style scoped>
/* Tokens only. Same centred column as the sign-in page. */

.atur-ulang {
  min-height: 100svh;
  display: flex;
  flex-direction: column;
  background: var(--canvas);
  color: var(--ink);
  padding-inline: var(--gutter);
}

.stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-6);
  width: 100%;
  max-width: 26rem;
  margin-inline: auto;
  padding-block: var(--s-10);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 2.75rem;
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

.card {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  padding: var(--s-6);
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1);
}

@media (max-width: 479px) {
  .card {
    padding: var(--s-5);
  }
}

.h1 {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
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
  color: var(--cat-ask-ink);
  background: var(--cat-ask-bg);
  border: 1px solid var(--cat-ask-line);
  padding: var(--s-3);
  border-radius: var(--r-md);
  line-height: 1.45;
}

/* Helper link: 44px tap target, underlined. */
.helper {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  font: var(--t-label);
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 3px;
  border-radius: var(--r-md);
  text-align: center;
}

.helper:hover {
  color: var(--accent-hover);
}

.foot-note {
  text-align: center;
}
</style>
