<script setup lang="ts">
/**
 * Workspace chrome.
 *
 * Three layouts off one set of destinations: a labelled sidebar from 1280px up,
 * an icon rail from 768px, and a bottom tab bar below that. The destinations are
 * identical in all three, so nothing is reachable on one breakpoint and missing
 * on another.
 */
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";
import { useKuotaStore } from "@/stores/kuota";
import { usePajakStore } from "@/stores/pajak";
import { useProfilStore } from "@/stores/profil";
import AppSidebar from "./AppSidebar.vue";
import AppTabBar from "./AppTabBar.vue";
import AppTopBar from "./AppTopBar.vue";

const route = useRoute();
onMounted(() => {
  void usePajakStore().muat();
  void useProfilStore().muat();
  void useKuotaStore().muat();
});
const bare = computed(() => route.meta.bare === true);
</script>

<template>
  <RouterView v-if="bare" v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="route.path" />
    </Transition>
  </RouterView>

  <div v-else class="shell">
    <AppSidebar />

    <div class="main">
      <AppTopBar />
      <main id="konten" class="sheet-scroll" tabindex="-1">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="route.path" />
          </Transition>
        </RouterView>
      </main>
      <AppTabBar />
    </div>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100svh;
  display: flex;
  background: var(--canvas);
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.sheet-scroll {
  flex: 1;
  padding: var(--s-5) var(--s-4) var(--s-8);
  /* Room for the floating tab bar and the home indicator on a phone. */
  padding-bottom: calc(var(--tabbar-h) + var(--safe-b) + var(--s-8));
}

/* Tablet: the page margin opens up once there is room for it. */
@media (min-width: 768px) {
  .sheet-scroll {
    padding: var(--s-6) var(--s-6) var(--s-10);
  }
}

@media (min-width: 1280px) {
  .sheet-scroll {
    padding: var(--s-8) var(--s-10) var(--s-12);
  }
}

.page-enter-active,
.page-leave-active {
  transition:
    opacity var(--t-base) var(--ease-out-soft),
    transform var(--t-base) var(--ease-out-soft);
}

.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active {
    transition: opacity 120ms linear;
  }

  .page-enter-from {
    transform: none;
  }
}
</style>
