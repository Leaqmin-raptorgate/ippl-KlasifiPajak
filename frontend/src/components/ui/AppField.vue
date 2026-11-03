<script setup lang="ts">
/** Label + control + hint/error, wired for assistive tech. */
defineProps<{
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
  required?: boolean;
  forId?: string;
  /** API field name (e.g. `tx_date`); tags the error node for 422 field_errors. */
  field?: string;
}>();
</script>

<template>
  <div class="field">
    <div class="lab">
      <label class="u-label" :for="forId">{{ label }}</label>
      <span v-if="optional" class="opt">opsional</span>
    </div>
    <slot />
    <p
      v-if="error"
      :id="forId ? `${forId}-err` : undefined"
      class="msg err"
      role="alert"
      :data-field-error="field"
    >
      {{ error }}
    </p>
    <p v-else-if="hint" class="msg">{{ hint }}</p>
  </div>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

.lab {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-2);
}

.lab :deep(label) {
  color: var(--ink-2);
}

.opt {
  font: var(--t-caption);
  color: var(--ink-3);
}

.msg {
  font: var(--t-body-sm);
  color: var(--ink-3);
  line-height: 1.45;
}

.err {
  color: var(--cat-ask-ink);
}
</style>
