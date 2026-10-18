<script setup lang="ts">
/**
 * Threshold meter.
 *
 * The fill grows from zero rather than fading in at its final width, so growth
 * reads as accumulation. The tone escalates on approach to and past the limit,
 * which is the only thing the user needs to notice about it.
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    label?: string;
    caption?: string;
    value: number;
    max: number;
    /** Fraction at which the tone escalates to warning. */
    warnAt?: number;
  }>(),
  { warnAt: 0.8 },
);

const ratio = computed(() => (props.max > 0 ? Math.min(props.value / props.max, 1) : 0));
const tone = computed(() =>
  ratio.value >= 1 ? "over" : ratio.value >= props.warnAt ? "warn" : "ok",
);
</script>

<template>
  <div class="meter" :class="tone">
    <div v-if="label || caption" class="top">
      <span v-if="label" class="lbl">{{ label }}</span>
      <span v-if="caption" class="cap">{{ caption }}</span>
    </div>
    <div
      class="track"
      role="meter"
      :aria-valuenow="Math.round(ratio * 100)"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div
        class="fill kp-meter-fill"
        :style="{ transform: `scaleX(${ratio})`, '--meter-ratio': ratio }"
      />
    </div>
    <div v-if="$slots.default" class="foot"><slot /></div>
  </div>
</template>

<style scoped>
.meter {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}

.lbl {
  font: var(--t-label);
  color: var(--ink);
  font-weight: 600;
}

.cap {
  font: var(--t-label-sm);
  color: var(--ink-3);
  white-space: nowrap;
}

.track {
  height: 0.5rem;
  border-radius: var(--r-full);
  background: var(--surface-sunken);
  border: 1px solid var(--hairline);
  overflow: clip;
}

.fill {
  height: 100%;
  width: 100%;
  border-radius: var(--r-full);
  background: var(--accent);
  transition: background-color var(--t-base) var(--ease-out-soft);
}

.warn .fill {
  background: var(--warn-ink);
}

.over .fill {
  background: var(--cat-ask-ink);
}

.warn .cap {
  color: var(--warn-ink);
  font-weight: 600;
}

.over .cap {
  color: var(--cat-ask-ink);
  font-weight: 600;
}

.foot {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.45;
}
</style>
