<script setup lang="ts">
/** Primary action control. Renders a router-link, an anchor, or a button. */
import { computed } from "vue";
import AppIcon from "./AppIcon.vue";

const props = withDefaults(
  defineProps<{
    variant?: "primary" | "soft" | "outline" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    to?: string;
    href?: string;
    type?: "button" | "submit";
    disabled?: boolean;
    block?: boolean;
    icon?: string;
    iconEnd?: string;
  }>(),
  { variant: "primary", size: "md", type: "button" },
);

const tag = computed(() => (props.to ? "RouterLink" : props.href ? "a" : "button"));
</script>

<template>
  <component
    :is="tag"
    class="btn press"
    :class="[`v-${variant}`, `s-${size}`, { block, 'is-disabled': disabled }]"
    :to="to"
    :href="href"
    :type="tag === 'button' ? type : undefined"
    :disabled="tag === 'button' ? disabled : undefined"
    :aria-disabled="tag !== 'button' && disabled ? true : undefined"
  >
    <AppIcon v-if="icon" :name="icon" :size="size === 'sm' ? 15 : 17" :stroke-width="1.7" />
    <span class="lbl"><slot /></span>
    <AppIcon
      v-if="iconEnd"
      :name="iconEnd"
      :size="size === 'sm' ? 15 : 17"
      :stroke-width="1.7"
      class="end"
    />
  </component>
</template>

<style scoped>
.btn {
  --btn-h: 2.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  height: var(--btn-h);
  min-height: var(--btn-h);
  padding-inline: var(--s-4);
  border-radius: var(--r-md);
  border: 1px solid transparent;
  font: var(--t-label);
  font-weight: 600;
  white-space: nowrap;
  user-select: none;
  position: relative;
}

.s-sm {
  --btn-h: 2.25rem;
  padding-inline: var(--s-3);
  font-size: 0.875rem;
}

.s-lg {
  --btn-h: 3rem;
  padding-inline: var(--s-6);
  font-size: 1rem;
}

.block {
  display: flex;
  width: 100%;
}

.is-disabled,
.btn:disabled {
  opacity: 0.42;
  pointer-events: none;
}

.end {
  flex: none;
}

/* Touch widths meet the 44px tap-target guidance; the pointer build stays compact. */
@media (pointer: coarse), (max-width: 767px) {
  .btn {
    --btn-h: 2.75rem;
  }

  .s-sm {
    --btn-h: 2.5rem;
  }

  .s-lg {
    --btn-h: 3.25rem;
  }
}

/* Primary: the one filled action on a screen. */
.v-primary {
  background: var(--accent);
  color: var(--accent-ink);
}

.v-primary:hover {
  background: var(--accent-hover);
}

.v-primary:active {
  background: var(--accent-press);
}

/* Soft: a tinted action for a secondary emphasis. */
.v-soft {
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
}

.v-soft:hover {
  background: var(--accent-line);
}

/* Secondary: a bordered neutral button. The border is a field-strength line so
   the control is findable without a shadow. */
.v-outline {
  background: var(--surface);
  color: var(--ink);
  border-color: var(--field-line);
}

.v-outline:hover {
  background: var(--surface-sunken);
}

.v-ghost {
  background: transparent;
  color: var(--ink-2);
}

.v-ghost:hover {
  background: var(--surface-sunken);
  color: var(--ink);
}

.v-danger {
  background: var(--surface);
  color: var(--danger);
  border-color: var(--cat-ask-line);
}

.v-danger:hover {
  background: var(--cat-ask-bg);
}
</style>
