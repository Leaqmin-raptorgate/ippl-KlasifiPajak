<script setup lang="ts">
/**
 * Where a classification came from. The source is part of the audit trail, so
 * it is shown wherever a category is shown, not tucked into a detail screen.
 */
import { computed } from "vue";
import type { Sumber } from "@/lib/domain";

const props = defineProps<{ sumber: Sumber }>();

const meta: Record<Sumber, { label: string; icon: string; hint: string }> = {
  rule: { label: "Aturan", icon: "dokumen", hint: "Dicocokkan aturan, tanpa model" },
  ai: { label: "AI", icon: "petir", hint: "Saran model, perlu ditinjau" },
  user_clarification: {
    label: "Klarifikasi",
    icon: "helpCircle",
    hint: "Anda menjawab pertanyaan",
  },
  user_override: { label: "Override", icon: "ubah", hint: "Anda menentukan sendiri" },
};

const m = computed(() => meta[props.sumber]);
</script>

<template>
  <span class="tag" :class="`s-${sumber}`" :title="m.hint">
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        :d="
          m.icon === 'dokumen'
            ? 'M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5'
            : m.icon === 'petir'
              ? 'M13 3L5.5 13.5H11l-1 7.5L17.5 10.5H12z'
              : m.icon === 'helpCircle'
                ? 'M12 21a9 9 0 100-18 9 9 0 000 18zM9.6 9.4a2.5 2.5 0 114 2c-.9.7-1.6 1.2-1.6 2.4M12 17.2v.1'
                : 'M4 20l1-4L16 5l3 3L8 19z'
        "
        fill="none"
        stroke="currentColor"
        :stroke-width="1.9"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    {{ m.label }}
  </span>
</template>

<style scoped>
.tag {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.4375rem;
  border-radius: var(--r-full);
  border: 1px solid var(--hairline);
  background: var(--surface-sunken);
  color: var(--ink-2);
  font: var(--t-caption);
  font-weight: 600;
  letter-spacing: var(--track-caption);
  text-transform: uppercase;
  white-space: nowrap;
}

svg {
  width: 0.75rem;
  height: 0.75rem;
  flex: none;
}

.s-ai {
  color: var(--accent-soft-ink);
  background: var(--accent-soft);
  border-color: var(--accent-line);
}

.s-user_clarification {
  color: var(--warn-ink);
  background: var(--warn-bg);
  border-color: var(--warn-line);
}

.s-user_override {
  color: var(--cat-bebas-ink);
  background: var(--cat-bebas-bg);
  border-color: var(--cat-bebas-line);
}
</style>
