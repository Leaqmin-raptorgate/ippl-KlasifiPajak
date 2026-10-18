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
import { useSessionStore } from "@/stores/session";

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const mode = ref("masuk");
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
      info.value = "Akun dibuat. Masuk dengan surel atau nama pengguna.";
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
  <div class="page masuk">
    <header class="top">
      <RouterLink to="/" class="brand">
        <span class="mark" aria-hidden="true">K</span>
        <span class="word">KlasifiPajak</span>
      </RouterLink>
      <RouterLink to="/" class="back">
        <AppIcon name="chevronLeft" :size="15" :stroke-width="1.8" />
        Beranda
      </RouterLink>
    </header>

    <main class="stage">
      <div class="card kp-materialize">
        <AppSegmented v-model="mode" :options="modeOpsi" aria-label="Mode akun" />

        <div class="lead">
          <h1 class="h1">{{ judul }}</h1>
          <p class="sub">{{ sub }}</p>
        </div>

        <p v-if="sesiBerakhir" class="sub" role="status">Sesi berakhir.</p>
        <p v-if="info" class="sub" role="status">{{ info }}</p>
        <p v-if="galat" class="sub" role="alert">{{ galat }}</p>

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

        <RouterLink to="/atur-ulang" class="lanjut">Lupa kata sandi</RouterLink>

        <div class="trust">
          <p class="tl">
            <AppIcon name="kunci" :size="16" :stroke-width="1.7" />
            Data tersimpan terpisah per akun. Satu akun tidak dapat membuka data akun lain.
          </p>
          <p class="tl">
            <AppIcon name="dokumen" :size="16" :stroke-width="1.7" />
            Yang dihitung di sini adalah kertas kerja, bukan SPT dan bukan pelaporan ke DJP.
          </p>
        </div>

        <WorkpaperNote publik class="stamp" />
      </div>
    </main>
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

.masuk {
  /* Bare route: no shell, so the page owns the canvas and its own chrome. */
  min-height: 100svh;
  background: var(--canvas);
  padding: var(--s-4) var(--s-4) calc(var(--s-8) + var(--safe-b));
}

@media (min-width: 768px) {
  .masuk {
    padding: var(--s-6) var(--s-6) var(--s-10);
  }
}

@media (min-width: 1280px) {
  .masuk {
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
  min-width: 0;
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
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.back {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  min-height: 2.5rem;
  padding-inline: var(--s-2);
  margin-right: calc(var(--s-2) * -1);
  border-radius: var(--r-md);
  flex: none;
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--ink-2);
  transition: color var(--t-fast) var(--ease-out-soft);
}

.back:hover {
  color: var(--ink);
}

.back svg {
  transition: transform var(--t-fast) var(--ease-out-soft);
}

.back:hover svg {
  transform: translateX(-2px);
}

.stage {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding-block: var(--s-4);
}

@media (min-width: 768px) {
  .stage {
    padding-block: var(--s-8);
  }
}

.card {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  width: min(26rem, 100%);
  padding: var(--s-5);
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-2);
}

@media (min-width: 768px) {
  .card {
    padding: var(--s-6);
  }
}

.lead {
  min-width: 0;
}

.h1 {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  font-size: clamp(1.125rem, 2.4vw, 1.375rem);
}

.sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  margin-top: var(--s-1);
}

.form {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.lanjut {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: 2.5rem;
  border-radius: var(--r-md);
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--ink-2);
  transition: color var(--t-fast) var(--ease-out-soft);
}

.lanjut:hover {
  color: var(--ink);
}

.lanjut svg {
  transition: transform var(--t-fast) var(--ease-out-soft);
}

.lanjut:hover svg {
  transform: translateX(2px);
}

.trust {
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
  margin-top: 0.125rem;
  color: var(--ink-3);
}

.stamp {
  margin-top: calc(var(--s-1) * -1);
}
</style>
