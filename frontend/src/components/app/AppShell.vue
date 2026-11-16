<script setup lang="ts">
/**
 * Route shell.
 *
 * Marketing and sign-in render bare. Everything else sits in one conventional
 * page: a site header, a centred content column with the page title as its h1,
 * and a site footer. No rail, sidebar, tab bar or bottom sheet.
 */
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useKuotaStore } from "@/stores/kuota";
import { usePajakStore } from "@/stores/pajak";
import { useProfilStore } from "@/stores/profil";
import AppSiteFooter from "./AppSiteFooter.vue";
import AppSiteHeader from "./AppSiteHeader.vue";

const route = useRoute();
const bare = computed(() => route.meta.bare === true);
const judul = computed(() => (route.meta.title as string | undefined) ?? "KlasifiPajak");

onMounted(async () => {
  void useKuotaStore().muat();
  const profil = useProfilStore();
  await profil.muat();
  // The dashboard answers 404 until the tax-year profile exists. Skip it only for that case;
  // a failed profile read (503, dropped connection) must not leave the header without figures.
  if (!profil.belumAda) void usePajakStore().muat();
});
</script>

<template>
  <RouterView v-if="bare" v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="route.path" />
    </Transition>
  </RouterView>

  <div v-else class="shell">
    <a class="skip" href="#konten">Lewati ke konten utama</a>
    <AppSiteHeader />

    <main id="konten" class="main" tabindex="-1">
      <div class="column">
        <h1 class="page-title">{{ judul }}</h1>
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </Transition>
        </RouterView>
      </div>
    </main>

    <AppSiteFooter />
  </div>
</template>

<style scoped>
.shell {
  min-height: 100svh;
  display: flex;
  flex-direction: column;
  background: var(--canvas);
}

.skip {
  position: absolute;
  left: var(--s-4);
  top: var(--s-2);
  z-index: 60;
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-md);
  background: var(--surface);
  color: var(--ink);
  border: 1px solid var(--hairline-strong);
  transform: translateY(-200%);
}

.skip:focus {
  transform: none;
}

.main {
  flex: 1;
  min-width: 0;
  width: 100%;
  max-width: var(--canvas-max);
  margin-inline: auto;
  padding: var(--s-6) var(--gutter) var(--s-12);
}

.main:focus {
  outline: none;
}

.column {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  min-width: 0;
}

/* Pages set `margin-inline: auto`, which stops a flex child from stretching and
   lets it shrink to its content. Give every page root the full column width so
   a long unbroken label cannot widen the page past the viewport. */
.column > * {
  width: 100%;
  min-width: 0;
}

.page-title {
  font: var(--t-title-1);
  color: var(--ink);
}

@media (min-width: 880px) {
  .main {
    padding: var(--s-8) var(--s-6) var(--s-16);
  }
}
</style>
