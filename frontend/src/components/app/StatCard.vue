<script setup lang="ts">
/**
 * Summary figure.
 *
 * One card, one number. The caption says which basis the number is on, because
 * a total with no basis is the thing that gets misread.
 */
import AppIcon from "@/components/ui/AppIcon.vue";

defineProps<{
  label: string;
  value: string;
  caption?: string;
  icon?: string;
  tone?: "default" | "accent" | "warn" | "ask";
}>();
</script>

<template>
  <div class="stat" :class="`t-${tone ?? 'default'}`">
    <div class="top">
      <span class="lbl">{{ label }}</span>
      <AppIcon v-if="icon" :name="icon" :size="16" :stroke-width="1.7" class="ic" />
    </div>
    <p class="val figure">{{ value }}</p>
    <p v-if="caption" class="cap">{{ caption }}</p>
  </div>
</template>

<style scoped>
.stat {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-4);
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1);
  min-width: 0;
}

.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
}

.lbl {
  font: var(--t-label-sm);
  letter-spacing: var(--track-label-sm);
  color: var(--ink-2);
  font-weight: 500;
}

.ic {
  color: var(--ink-3);
}

.val {
  font: var(--t-figure);
  letter-spacing: -0.02em;
  color: var(--ink);
  overflow-wrap: anywhere;
}

.cap {
  font: var(--t-body-sm);
  color: var(--ink-3);
  line-height: 1.45;
}

.t-accent .val {
  color: var(--accent);
}

.t-accent .ic {
  color: var(--accent);
}

.t-warn {
  border-color: var(--warn-line);
  background: var(--warn-bg);
}

.t-warn .val,
.t-warn .ic {
  color: var(--warn-ink);
}

.t-warn .cap {
  color: color-mix(in oklab, var(--warn-ink) 75%, transparent);
}

.t-ask {
  border-color: var(--cat-ask-line);
  background: var(--cat-ask-bg);
}

.t-ask .val,
.t-ask .ic {
  color: var(--cat-ask-ink);
}

.t-ask .cap {
  color: color-mix(in oklab, var(--cat-ask-ink) 75%, transparent);
}

@media (min-width: 768px) {
  .stat {
    padding: var(--s-5);
  }

  .val {
    font-size: 1.625rem;
  }
}
</style>
