<script setup lang="ts">
/** Sign-in and account creation. Register does not open a session. */
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppField from "@/components/ui/AppField.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppInput from "@/components/ui/AppInput.vue";
import AppSegmented from "@/components/ui/AppSegmented.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import { CAPABILITIES } from "@/lib/capabilities";
import { useSessionStore } from "@/stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const mode = ref(route.query.mode === "daftar" ? "daftar" : "masuk");
const username = ref("");
const email = ref("");
const sandi = ref("");
const galat = ref("");
const info = ref("");
const sibuk = ref(false);

const modeOpsi = [
  { value: "masuk", label: "Masuk" },
  { value: "daftar", label: "Daftar" },
];

const daftar = computed(() => mode.value === "daftar");
const sesiBerakhir = computed(() => route.query.sesi === "berakhir" || session.sesiBerakhir);
const lanjut = computed(() => {
  const raw = route.query.lanjut;
  const path = Array.isArray(raw) ? raw[0] : raw;
  return path && path.startsWith("/") ? path : "/dasbor";
});

const judul = computed(() => (daftar.value ? "Buat akun KlasifiPajak" : "Masuk ke KlasifiPajak"));
const sub = computed(() =>
  daftar.value
    ? "Surel dan nama pengguna wajib unik. Mendaftar tidak langsung masuk."
    : "Lanjutkan kertas kerja yang belum selesai.",
);
const sandiHint = computed(() => (daftar.value ? "Minimal 10 karakter." : ""));
const sandiAutocomplete = computed(() => (daftar.value ? "new-password" : "current-password"));

async function submit() {
  galat.value = "";
  info.value = "";
  if (daftar.value && sandi.value.length < 10) {
    galat.value = "Kata sandi harus memiliki panjang minimal 10 karakter.";
    return;
  }
  sibuk.value = true;
  try {
    if (daftar.value) {
      await session.daftar(email.value.trim(), username.value.trim(), sandi.value);
      mode.value = "masuk";
      sandi.value = "";
      info.value = "Akun dibuat. Masuk dengan surel atau nama pengguna dan kata sandi Anda.";
      return;
    }
    await session.masuk(email.value.trim(), sandi.value);
    await router.push(lanjut.value);
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Permintaan gagal. Coba lagi.";
  } finally {
    sibuk.value = false;
  }
}
</script>

<template>
  <div class="masuk">
    <main class="stage">
      <RouterLink to="/" class="brand" aria-label="KlasifiPajak, beranda">
        <span class="mark" aria-hidden="true">K</span>
        <span class="word">KlasifiPajak</span>
      </RouterLink>

      <div class="card">
        <AppSegmented v-model="mode" :options="modeOpsi" aria-label="Mode akun" />

        <div class="lead">
          <h1 class="h1">{{ judul }}</h1>
          <p class="sub">{{ sub }}</p>
        </div>

        <p v-if="sesiBerakhir" class="pesan" role="status">Sesi berakhir.</p>
        <p v-if="info" class="pesan" role="status">{{ info }}</p>
        <p v-if="galat" class="galat" role="alert">{{ galat }}</p>

        <form class="form" @submit.prevent="submit">
          <AppField v-if="daftar" label="Nama pengguna" for-id="nama-pengguna">
            <AppInput
              id="nama-pengguna"
              v-model="username"
              type="text"
              autocomplete="username"
              required
            />
          </AppField>

          <AppField :label="daftar ? 'Surel' : 'Surel atau nama pengguna'" for-id="email">
            <AppInput
              id="email"
              v-model="email"
              :type="daftar ? 'email' : 'text'"
              :autocomplete="daftar ? 'email' : 'username'"
              required
            />
          </AppField>

          <AppField label="Kata sandi" for-id="sandi" :hint="sandiHint">
            <AppInput
              id="sandi"
              v-model="sandi"
              type="password"
              :autocomplete="sandiAutocomplete"
            />
          </AppField>

          <AppButton
            type="submit"
            variant="primary"
            size="lg"
            block
            icon-end="arrowRight"
            :disabled="sibuk"
          >
            {{ daftar ? "Buat akun" : "Masuk" }}
          </AppButton>
        </form>

        <RouterLink v-if="CAPABILITIES.passwordReset" to="/atur-ulang" class="helper">
          Lupa kata sandi?
        </RouterLink>

        <div class="data-note">
          <p class="tl">
            <AppIcon name="kunci" :size="16" :stroke-width="1.7" />
            Data tersimpan terpisah per akun. Satu akun tidak dapat membuka data akun lain.
          </p>
          <p class="tl">
            <AppIcon name="dokumen" :size="16" :stroke-width="1.7" />
            Yang dihitung di sini adalah kertas kerja, bukan SPT dan bukan pelaporan ke DJP.
          </p>
        </div>
      </div>

      <div class="foot">
        <WorkpaperNote publik />
        <RouterLink to="/" class="helper">Kembali ke beranda</RouterLink>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* Tokens only. Plain canvas, one centred column, no entry transform. */

.masuk {
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

/* Product mark above the card; links home. */
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

.lead {
  min-width: 0;
}

.h1 {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
}

.sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  margin-top: var(--s-1);
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

.form {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

/* Helper links: 44px tall tap targets, underlined so they read as links. */
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

.data-note {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-4);
  border-radius: var(--r-md);
  background: var(--surface-sunken);
}

.tl {
  display: flex;
  align-items: flex-start;
  gap: var(--s-2);
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.45;
}

.tl svg {
  flex: none;
  margin-top: 0.125rem;
  color: var(--ink-3);
}

.foot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  text-align: center;
}
</style>
