<script setup lang="ts">
/**
 * Route shell.
 *
 * Marketing and sign-in render bare. Everything else sits inside the workspace
 * shell, which is the only place the navigation chrome exists.
 */
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppShell from "@/components/app/AppShell.vue";

const route = useRoute();
const bare = computed(() => route.meta.bare === true);
</script>

<template>
  <RouterView v-if="bare" v-slot="{ Component }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="route.path" />
    </Transition>
  </RouterView>
  <AppShell v-else />
</template>

<style>
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
