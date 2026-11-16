<script setup lang="ts">
/**
 * Sheet / dialog.
 *
 * A centred dialog at every width. It is not a bottom sheet: the site is a
 * conventional page, and a dialog is the honest container for a focused task.
 * It fades in and out; nothing slides or scales.
 *
 * The scrim is the only thing that blocks input, and it dismisses on tap. There
 * is no busy state to wait out, so nothing ever locks the user mid-transition.
 *
 * `error` is rendered inside the panel, above the footer, so a failed action
 * cannot hide behind the scrim. It is a controlled prop: the owner clears it
 * when the sheet closes, and again when it reopens.
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import AppIcon from "./AppIcon.vue";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    subtitle?: string;
    wide?: boolean;
    error?: string;
  }>(),
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
          <p v-if="error" class="err" role="alert">{{ error }}</p>
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
  align-items: center;
  justify-content: center;
  padding: var(--s-4);
}

.scrim {
  position: absolute;
  inset: 0;
  background: var(--scrim);
}

.panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(30rem, 100%);
  max-height: 84svh;
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-2);
  overflow: clip;
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

.err {
  margin: 0 var(--s-5) var(--s-5);
  padding: var(--s-3);
  border: 1px solid var(--cat-ask-line);
  border-radius: var(--r-md);
  background: var(--cat-ask-bg);
  color: var(--cat-ask-ink);
  font: var(--t-body-sm);
  line-height: 1.45;
}

.wide {
  width: min(46rem, 100%);
}

/* Fade only: the dialog and its scrim share one short opacity transition. */
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity var(--t-fast) linear;
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}
</style>
