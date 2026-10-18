<script setup lang="ts">
/** A grouped surface. `inset` drops it to a sunken well for secondary content. */
withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    inset?: boolean;
    flush?: boolean;
    as?: string;
  }>(),
  { as: "section" },
);
</script>

<template>
  <component :is="as" class="card" :class="{ inset, flush }">
    <header v-if="title || $slots.actions" class="head">
      <div class="titles">
        <h2 v-if="title" class="t3">{{ title }}</h2>
        <p v-if="subtitle" class="sub">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="acts"><slot name="actions" /></div>
    </header>
    <div class="body" :class="{ 'has-head': title || $slots.actions }">
      <slot />
    </div>
  </component>
</template>

<style scoped>
.card {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1);
  overflow: clip;
}

.inset {
  background: var(--surface-sunken);
  box-shadow: none;
}

.flush .body {
  padding: 0;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-4);
  padding: var(--s-4) var(--s-5) 0;
}

.titles {
  min-width: 0;
}

.t3 {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
}

.sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  margin-top: 0.125rem;
}

.acts {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex: none;
}

.body {
  padding: var(--s-5);
}

.body.has-head {
  padding-top: var(--s-4);
}
</style>
