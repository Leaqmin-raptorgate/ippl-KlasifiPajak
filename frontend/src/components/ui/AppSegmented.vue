<script setup lang="ts">
/**
 * Segmented control with a sliding indicator.
 *
 * The indicator animates its transform, which is compositor-only, and it starts
 * from whatever offset is on screen right now, so tapping a different segment
 * mid-slide retargets instead of restarting.
 */
import { computed, onMounted, ref, watch } from "vue";

const props = defineProps<{
  modelValue: string;
  options: { value: string; label: string; count?: number }[];
  ariaLabel?: string;
}>();

const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const root = ref<HTMLElement | null>(null);
const activeIndex = computed(() =>
  Math.max(
    0,
    props.options.findIndex((o) => o.value === props.modelValue),
  ),
);

const thumbStyle = computed(() => {
  const count = props.options.length;
  if (count === 0) return { display: "none" };
  return {
    width: `calc((100% - 0.375rem) / ${count})`,
    transform: `translateX(calc(${activeIndex.value} * 100%))`,
  };
});

function onKeydown(e: KeyboardEvent) {
  const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
  if (!delta) return;
  e.preventDefault();
  const next = (activeIndex.value + delta + props.options.length) % props.options.length;
  emit("update:modelValue", props.options[next].value);
}

onMounted(() => root.value?.setAttribute("role", "radiogroup"));
watch(
  () => props.modelValue,
  () =>
    root.value?.querySelectorAll("[role=radio]").forEach((el, i) => {
      el.setAttribute("aria-checked", i === activeIndex.value ? "true" : "false");
      el.setAttribute("tabindex", i === activeIndex.value ? "0" : "-1");
    }),
  { immediate: true },
);
</script>

<template>
  <div ref="root" class="seg" :aria-label="ariaLabel" @keydown="onKeydown">
    <span class="thumb" :style="thumbStyle" aria-hidden="true" />
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      class="opt"
      :class="{ on: o.value === modelValue }"
      :aria-checked="o.value === modelValue ? 'true' : 'false'"
      :tabindex="o.value === modelValue ? 0 : -1"
      @click="emit('update:modelValue', o.value)"
    >
      <span class="ol">{{ o.label }}</span>
      <span v-if="o.count !== undefined" class="oc figure">{{ o.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.seg {
  position: relative;
  display: flex;
  gap: 0;
  padding: 0.1875rem;
  background: var(--surface-sunken);
  border: 1px solid var(--hairline);
  border-radius: var(--r-md);
  isolation: isolate;
}

.thumb {
  position: absolute;
  z-index: -1;
  top: 0.1875rem;
  left: 0.1875rem;
  bottom: 0.1875rem;
  border-radius: calc(var(--r-md) - 0.1875rem);
  background: var(--surface);
  box-shadow: var(--shadow-1);
  transition: transform var(--t-base) var(--ease-spring);
}

@media (prefers-reduced-motion: reduce) {
  .thumb {
    transition: none;
  }
}

.opt {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  height: 2.5rem;
  padding-inline: var(--s-2);
  border-radius: calc(var(--r-md) - 0.1875rem);
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--ink-2);
  transition: color var(--t-fast) var(--ease-out-soft);
  white-space: nowrap;
}

.opt:hover {
  color: var(--ink);
}

.opt.on {
  color: var(--ink);
  font-weight: 600;
}

.ol {
  overflow: hidden;
  text-overflow: ellipsis;
}

.oc {
  font-size: 0.6875rem;
  color: var(--ink-3);
}

.opt.on .oc {
  color: var(--accent);
}
</style>
