<script setup lang="ts">
/** Single icon component over the shared geometry. */
import { computed } from "vue";
import { ICON_PATHS, type IconProp } from "./icons";

const props = withDefaults(
  defineProps<{
    name: IconProp;
    size?: number;
    strokeWidth?: number;
    filled?: boolean;
  }>(),
  { size: 20, strokeWidth: 1.6, filled: false },
);

const d = computed(() => ICON_PATHS[props.name as keyof typeof ICON_PATHS] ?? ICON_PATHS.info);
</script>

<template>
  <svg
    class="icon"
    :style="{ width: `${size}px`, height: `${size}px` }"
    viewBox="0 0 24 24"
    aria-hidden="true"
    focusable="false"
    :fill="filled ? 'currentColor' : 'none'"
    :stroke="filled ? 'none' : 'currentColor'"
    stroke-linecap="round"
    stroke-linejoin="round"
    :stroke-width="strokeWidth"
  >
    <path :d="d" />
  </svg>
</template>

<style scoped>
.icon {
  flex: none;
  overflow: visible;
}
</style>
