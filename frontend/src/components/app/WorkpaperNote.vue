<script setup lang="ts">
/**
 * The workpaper stamp.
 *
 * A signed-in amount uses the dashboard metadata. The public prop is only the
 * academic ruleset identity, and it is not a calculated figure.
 */
import { computed } from "vue";
import { PUBLIC_RULESET } from "@/lib/domain";
import { tanggalPanjang } from "@/lib/format";
import { usePajakStore } from "@/stores/pajak";

const props = defineProps<{ publik?: boolean }>();
const pajak = usePajakStore();

const id = computed(
  () => pajak.dashboard?.metadata.ruleset_id || (props.publik ? PUBLIC_RULESET.id : ""),
);
const berlaku = computed(
  () => pajak.dashboard?.metadata.effective_date || (props.publik ? PUBLIC_RULESET.berlaku : ""),
);
</script>

<template>
  <p class="note">
    <span class="mark">Kertas kerja, bukan SPT</span>
    <template v-if="id && berlaku">
      <span class="sep" aria-hidden="true">·</span>
      <span class="id">ruleset {{ id }}</span>
      <span class="sep" aria-hidden="true">·</span>
      <span>berlaku {{ tanggalPanjang(berlaku) }}</span>
    </template>
    <template v-else>
      <span class="sep" aria-hidden="true">·</span>
      <span>ruleset belum dimuat</span>
    </template>
  </p>
</template>

<style scoped>
.note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem;
  font: var(--t-caption);
  letter-spacing: var(--track-caption);
  color: var(--ink-3);
}

.mark {
  font-weight: 600;
  color: var(--ink-2);
}

.id {
  font-family: var(--font-numeric);
}

.sep {
  opacity: 0.5;
}
</style>
