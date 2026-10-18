<script setup lang="ts">
/**
 * Sheet / dialog.
 *
 * Anchored to the bottom edge on a phone, where the thumb is, and presented as
 * a centered dialog from tablet up. Enter and exit share one path: the panel
 * comes from the bottom and leaves toward the bottom, so a dismissal reads as a
 * reversal rather than a detour.
 *
 * The scrim is the only thing that blocks input, and it dismisses on tap. There
 * is no busy state to wait out, so nothing ever locks the user mid-transition.
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import AppIcon from "./AppIcon.vue";

const props = withDefaults(
  defineProps<{ open: boolean; title: string; subtitle?: string; wide?: boolean }>(),
  { wide: false },
);

const emit = defineEmits<{ close: [] }>();

const panel = ref<HTMLElement | null>(null);
const opener = ref<HTMLElement | null>(null);

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.stopPropagation();
    emit("close");
  }
}

watch(
  () => props.open,
  (open) => {
    document.documentElement.style.overflow = open ? "hidden" : "";
    if (open) {
      opener.value = document.activeElement as HTMLElement;
      requestAnimationFrame(() => {
        const focusable = panel.value?.querySelector<HTMLElement>(
          "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
        );
        (focusable ?? panel.value)?.focus({ preventScroll: true });
      });
    } else {
      opener.value?.focus?.({ preventScroll: true });
    }
  },
);

onMounted(() => document.addEventListener("keydown", onKey));
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKey);
  document.documentElement.style.overflow = "";
});
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="open" class="layer" @click.self="emit('close')">
        <div class="scrim" aria-hidden="true" />
        <div
          ref="panel"
          class="panel"
          :class="{ wide }"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          tabindex="-1"
        >
          <header class="grab" aria-hidden="true"><span class="bar" /></header>
          <header class="head">
            <div class="titles">
              <h2 class="t2">{{ title }}</h2>
              <p v-if="subtitle" class="sub">{{ subtitle }}</p>
            </div>
            <button class="x press" type="button" aria-label="Tutup" @click="emit('close')">
              <AppIcon name="tutup" :size="17" :stroke-width="1.8" />
            </button>
          </header>
          <div class="body"><slot /></div>
          <footer v-if="$slots.footer" class="foot"><slot name="footer" /></footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.layer {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.scrim {
  position: absolute;
  inset: 0;
  background: var(--scrim);
  backdrop-filter: blur(2px);
}

.panel {
  position: relative;
  display: flex;
  flex-direction: column;
  max-height: 88svh;
  background: var(--material-sheet);
  backdrop-filter: var(--blur-bar);
  border-radius: var(--r-2xl) var(--r-2xl) 0 0;
  box-shadow: var(--shadow-3);
  padding-bottom: var(--safe-b);
  overflow: clip;
}

.grab {
  display: flex;
  justify-content: center;
  padding-top: var(--s-2);
}

.bar {
  width: 2.25rem;
  height: 0.25rem;
  border-radius: var(--r-full);
  background: var(--hairline-strong);
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-4);
  padding: var(--s-3) var(--s-5) var(--s-4);
}

.t2 {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
}

.sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  margin-top: var(--s-1);
}

.x {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--r-full);
  background: var(--surface-sunken);
  color: var(--ink-2);
  flex: none;
}

.x:hover {
  color: var(--ink);
}

.body {
  padding: 0 var(--s-5) var(--s-5);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.foot {
  display: flex;
  gap: var(--s-3);
  padding: var(--s-4) var(--s-5);
  border-top: 1px solid var(--hairline);
}

@media (min-width: 768px) {
  .layer {
    justify-content: center;
    align-items: center;
    padding: var(--s-6);
  }

  .panel {
    width: min(30rem, 100%);
    max-height: 84svh;
    border-radius: var(--r-xl);
    padding-bottom: 0;
  }

  .wide {
    width: min(46rem, 100%);
  }

  /* The grab handle is a phone affordance; from tablet up the panel is a dialog
     and a centered close button already says how to leave. */
  .grab {
    display: none;
  }

  .head {
    padding-top: var(--s-5);
  }
}

/* Enter and exit along the same path: from below, and back to below. */
.sheet-enter-active .panel,
.sheet-leave-active .panel {
  transition:
    transform var(--t-base) var(--ease-out-soft),
    opacity var(--t-base) var(--ease-out-soft);
}

.sheet-enter-active .scrim,
.sheet-leave-active .scrim {
  transition: opacity var(--t-base) var(--ease-out-soft);
}

.sheet-enter-from .panel,
.sheet-leave-to .panel {
  transform: translateY(100%);
  opacity: 0.4;
}

.sheet-enter-from .scrim,
.sheet-leave-to .scrim {
  opacity: 0;
}

@media (min-width: 768px) {
  .sheet-enter-from .panel,
  .sheet-leave-to .panel {
    transform: scale(0.96) translateY(8px);
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sheet-enter-from .panel,
  .sheet-leave-to .panel {
    transform: none;
    opacity: 0;
  }
}
</style>
