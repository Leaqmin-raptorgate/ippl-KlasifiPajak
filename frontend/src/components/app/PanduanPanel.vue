<script setup lang="ts">
/** Cited static guidance selected by the server for this profile and its totals. */
import AppCard from "@/components/ui/AppCard.vue";
import { tanggalPanjang } from "@/lib/format";
import { usePanduanStore } from "@/stores/panduan";

const store = usePanduanStore();
</script>

<template>
  <AppCard v-if="store.panduan" title="Panduan untuk profil Anda">
    <p class="stamp">
      Ruleset {{ store.panduan.ruleset_id }} · berlaku
      {{ tanggalPanjang(store.panduan.effective_date) }}
    </p>
    <ul v-if="store.panduan.items.length" class="items">
      <li v-for="item in store.panduan.items" :key="item.id" class="item">
        <p>{{ item.text }}</p>
        <p class="citation">Rujukan: {{ item.citation }}</p>
      </li>
    </ul>
    <p v-else class="empty">Belum ada panduan tambahan untuk profil dan data saat ini.</p>
    <p class="disclaimer">{{ store.panduan.disclaimer }}</p>
  </AppCard>
  <p v-else-if="store.pesan" class="error" role="status">{{ store.pesan }}</p>
</template>

<style scoped>
.stamp,
.citation,
.empty {
  color: var(--ink-3);
  font: var(--t-caption);
}

.items {
  display: grid;
  gap: var(--s-3);
  margin: var(--s-3) 0 0;
  padding-left: 1.25rem;
}

.item p {
  margin: 0;
}

.item .citation {
  margin-top: var(--s-1);
}

.disclaimer {
  margin: var(--s-4) 0 0;
  padding-top: var(--s-3);
  border-top: 1px solid var(--hairline);
  color: var(--ink-2);
  font: var(--t-caption);
}

.error {
  color: var(--ink-3);
  font: var(--t-caption);
}
</style>
