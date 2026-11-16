<script setup lang="ts">
/**
 * Summary figure.
 *
 * One card, one number. The caption says which basis the number is on, because
 * a total with no basis is the thing that gets misread.
 *
 * `valueKind="text"` is for a word, such as a status. It sets at title size so it
 * stays on one line where the card allows, instead of wrapping at figure size.
 */
import AppIcon from "@/components/ui/AppIcon.vue";

defineProps<{
  label: string;
  value: string;
  caption?: string;
  icon?: string;
  tone?: "default" | "accent" | "warn" | "ask";
  valueKind?: "figure" | "text";
}>();
</script>

<template>
  <div class="stat" :class="`t-${tone ?? 'default'}`">
    <div class="top">
      <span class="lbl">{{ label }}</span>
      <AppIcon v-if="icon" :name="icon" :size="16" :stroke-width="1.7" class="ic" />
    </div>
    <p class="val" :class="valueKind === 'text' ? 'is-teks' : 'figure'">{{ value }}</p>
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

/* A word value: title size, so "Memenuhi syarat" fits on one line in a quarter-width card. */
.val.is-teks {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  font-family: var(--font-sans);
  font-variant-numeric: normal;
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

/* Captions keep full text colour on tinted cards: a faded caption fails 4.5:1. */
.t-warn .cap,
.t-ask .cap {
  color: var(--ink-2);
}

.t-ask {
  border-color: var(--cat-ask-line);
  background: var(--cat-ask-bg);
}

.t-ask .val,
.t-ask .ic {
  color: var(--cat-ask-ink);
}

@media (min-width: 768px) {
  .stat {
    padding: var(--s-5);
  }

  .val {
    font-size: 1.625rem;
  }

  .val.is-teks {
    font-size: 1.125rem;
  }
}
</style>
