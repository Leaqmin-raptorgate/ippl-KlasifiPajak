<script setup lang="ts">
/**
 * Text input. The control shell is fixed here so every form in the app matches
 * the finger on a phone and the pointer on a desktop. Use `#pre` for a fixed
 * unit badge (for example the `Rp` prefix on a currency field).
 */
/* Attributes belong to the inner input, not to the control shell: without this
   a caller's `type`, `placeholder` or `inputmode` would also land on the
   wrapper as invalid markup. */
defineOptions({ inheritAttrs: false });

defineProps<{
  id?: string;
  modelValue?: string | number;
  invalid?: boolean;
  mono?: boolean;
}>();

const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <div class="ctl" :class="{ invalid, mono }">
    <span v-if="$slots.pre" class="pre"><slot name="pre" /></span>
    <input
      :id="id"
      class="in"
      :value="modelValue"
      :aria-invalid="invalid ? 'true' : undefined"
      autocomplete="off"
      v-bind="$attrs"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="$slots.post" class="post"><slot name="post" /></span>
  </div>
</template>

<style scoped>
.ctl {
  display: flex;
  align-items: stretch;
  min-height: 2.75rem;
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--r-md);
  overflow: clip;
  transition:
    border-color var(--t-fast) var(--ease-out-soft),
    box-shadow var(--t-fast) var(--ease-out-soft);
}

.ctl:focus-within {
  border-color: var(--focus);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--focus) 20%, transparent);
}

.invalid {
  border-color: var(--cat-ask-line);
}

.in {
  flex: 1;
  min-width: 0;
  padding: 0.6875rem var(--s-3);
  background: none;
  border: 0;
  border-radius: inherit;
  font: var(--t-body);
  letter-spacing: var(--track-body);
}

.in::placeholder {
  color: var(--ink-3);
}

/* A phone must not zoom the page when a field is focused. */
@media (max-width: 767px) {
  .in {
    font-size: 1rem;
    line-height: 1.45;
  }
}

.pre,
.post {
  display: flex;
  align-items: center;
  padding-inline: var(--s-3);
  background: var(--surface-sunken);
  color: var(--ink-3);
  font: var(--t-label-sm);
  font-weight: 600;
  white-space: nowrap;
}

.pre {
  border-right: 1px solid var(--hairline);
}

.post {
  border-left: 1px solid var(--hairline);
}

.mono .in {
  text-align: right;
  font-family: var(--font-numeric);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}
</style>
