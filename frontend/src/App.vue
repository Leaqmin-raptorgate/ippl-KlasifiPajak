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
/* Route change: a short fade only. Total time stays under 200ms. */
.page-enter-active,
.page-leave-active {
  transition: opacity var(--t-fast) linear;
}

.page-enter-from,
.page-leave-to {
  opacity: 0;
}
</style>
