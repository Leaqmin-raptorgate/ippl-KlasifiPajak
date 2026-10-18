<script setup lang="ts">
/**
 * Category and status pill.
 *
 * One component covers the five semantic states so a category always looks the
 * same wherever it appears: in a table, in a card, in a summary row, or in a
 * filter chip. Values come from the engine's four categories plus the
 * unresolved state.
 */
import { computed } from "vue";
import AppIcon from "./AppIcon.vue";

const props = withDefaults(
  defineProps<{
    tone?: "usaha" | "bebas" | "final" | "non" | "ask" | "neutral" | "accent";
    label: string;
    icon?: string;
    size?: "sm" | "md";
    attention?: boolean;
  }>(),
  { size: "md" },
);

const iconFor: Record<string, string> = {
  usaha: "toko",
  bebas: "pena",
  final: "persen",
  non: "tukar",
  ask: "helpCircle",
  accent: "pembisahan",
};

const glyph = computed(() => props.icon ?? iconFor[props.tone ?? "neutral"] ?? "info");
</script>

<template>
  <span class="pill" :class="[`t-${tone ?? 'neutral'}`, `sz-${size}`]">
    <AppIcon :name="glyph" :size="size === 'sm' ? 12 : 13" :stroke-width="1.9" />
    <span class="txt">{{ label }}</span>
    <span v-if="attention" class="dot" aria-hidden="true" />
  </span>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  gap: 0.3125rem;
  padding: 0.1875rem 0.5rem 0.1875rem 0.4375rem;
  border-radius: var(--r-full);
  border: 1px solid var(--hairline);
  background: var(--surface-sunken);
  color: var(--ink-2);
  font: var(--t-label-sm);
  font-weight: 600;
  letter-spacing: var(--track-label);
  white-space: nowrap;
  max-width: 100%;
}

.sz-sm {
  font-size: 0.6875rem;
  padding: 0.125rem 0.4375rem 0.125rem 0.375rem;
}

.txt {
  overflow: hidden;
  text-overflow: ellipsis;
}

.dot {
  width: 0.375rem;
  height: 0.375rem;
  border-radius: var(--r-full);
  background: currentColor;
  margin-left: 0.0625rem;
  flex: none;
}

.t-usaha {
  color: var(--cat-usaha-ink);
  background: var(--cat-usaha-bg);
  border-color: var(--cat-usaha-line);
}

.t-bebas {
  color: var(--cat-bebas-ink);
  background: var(--cat-bebas-bg);
  border-color: var(--cat-bebas-line);
}

.t-final {
  color: var(--cat-final-ink);
  background: var(--cat-final-bg);
  border-color: var(--cat-final-line);
}

.t-non {
  color: var(--cat-non-ink);
  background: var(--cat-non-bg);
  border-color: var(--cat-non-line);
}

.t-ask {
  color: var(--cat-ask-ink);
  background: var(--cat-ask-bg);
  border-color: var(--cat-ask-line);
}

.t-accent {
  color: var(--accent-soft-ink);
  background: var(--accent-soft);
  border-color: var(--accent-line);
}
</style>
