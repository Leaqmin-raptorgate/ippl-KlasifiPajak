<script setup lang="ts">
/** Native select in a matching shell, with a chevron that cannot be styled away. */
defineOptions({ inheritAttrs: false });

defineProps<{
  id?: string;
  modelValue?: string;
  invalid?: boolean;
  options: { value: string; label: string }[];
}>();

const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <div class="ctl" :class="{ invalid }">
    <select
      :id="id"
      class="sel"
      :value="modelValue"
      :aria-invalid="invalid ? 'true' : undefined"
      v-bind="$attrs"
      @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
    >
      <option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option>
    </select>
    <svg class="chev" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M5 9l7 7 7-7"
        fill="none"
        stroke="currentColor"
        :stroke-width="1.7"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  </div>
</template>

<style scoped>
.ctl {
  position: relative;
  display: flex;
  align-items: center;
  min-height: 2.75rem;
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--r-md);
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

.sel {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0.6875rem calc(var(--s-6) + var(--s-2)) 0.6875rem var(--s-3);
  background: none;
  border: 0;
  appearance: none;
  font: var(--t-body);
  letter-spacing: var(--track-body);
}

@media (max-width: 767px) {
  .sel {
    font-size: 1rem;
    line-height: 1.45;
  }
}

.chev {
  position: absolute;
  right: var(--s-3);
  width: 1.125rem;
  height: 1.125rem;
  color: var(--ink-3);
  pointer-events: none;
}
</style>
