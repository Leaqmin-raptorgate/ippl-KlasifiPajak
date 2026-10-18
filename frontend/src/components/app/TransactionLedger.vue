<script setup lang="ts">
/**
 * Transaction ledger.
 *
 * One list, two readings. Below 1024px each row stacks: who, what, how much.
 * From 1024px the rows become aligned columns under a sticky header. Rendering
 * one DOM rather than two keeps the row order, the accessible name of each row,
 * and the keyboard order identical on every breakpoint.
 */
import { computed } from "vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppPill from "@/components/ui/AppPill.vue";
import SourceTag from "./SourceTag.vue";
import { KATEGORI_LABEL } from "@/lib/domain";
import { rupiahPlain, tanggalPendek } from "@/lib/format";
import type { Transaction } from "@/lib/wire";

const props = defineProps<{ rows: Transaction[] }>();

const TONE: Record<string, "usaha" | "bebas" | "final" | "non" | "ask"> = {
  usaha: "usaha",
  pekerjaan_bebas: "bebas",
  already_final: "final",
  non_object: "non",
};

const emit = defineEmits<{ open: [id: string] }>();

const anyPending = computed(() => props.rows.some((r) => r.classification?.requires_clarification));
</script>

<template>
  <div class="ledger" :class="{ flagged: anyPending }">
    <div class="head" aria-hidden="true">
      <span>Tanggal</span>
      <span>Klien dan keterangan</span>
      <span class="num">Nominal</span>
      <span>Kategori</span>
      <span>Sumber</span>
      <span />
    </div>

    <ul class="rows">
      <li v-for="r in rows" :key="r.id">
        <button
          class="row"
          type="button"
          :aria-label="`${r.client_name}, ${r.description}, ${rupiahPlain(r.amount_idr)} rupiah, ${KATEGORI_LABEL[r.category]}`"
          @click="emit('open', r.id)"
        >
          <span class="c date">
            <span class="d">{{ tanggalPendek(r.tx_date) }}</span>
          </span>

          <span class="c who">
            <span class="kl">{{ r.client_name }}</span>
            <span class="kt">{{ r.description }}</span>
            <span class="kb">
              <AppPill
                v-if="r.classification?.requires_clarification"
                tone="ask"
                label="Perlu klarifikasi"
                icon="helpCircle"
                size="sm"
                attention
              />
              <span v-if="r.invoice_no" class="npwp figure">{{ r.invoice_no }}</span>
            </span>
          </span>

          <span class="c amt num figure">{{ rupiahPlain(r.amount_idr) }}</span>

          <span class="c cat">
            <AppPill
              :tone="TONE[r.category]"
              :label="KATEGORI_LABEL[r.category]"
              :attention="Boolean(r.classification?.requires_clarification)"
              size="sm"
            />
          </span>

          <span class="c src"><SourceTag :sumber="r.source" /></span>

          <span class="c go"><AppIcon name="chevronRight" :size="16" :stroke-width="1.8" /></span>
        </button>
      </li>

      <li v-if="rows.length === 0" class="empty">
        Tidak ada transaksi yang cocok dengan filter ini.
      </li>
    </ul>
  </div>
</template>

<style scoped>
.ledger {
  --cols: minmax(0, 1fr);
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1);
  overflow: clip;
}

.head {
  display: none;
}

.rows {
  display: flex;
  flex-direction: column;
}

.row {
  display: grid;
  grid-template-areas:
    "who who"
    "amt cat"
    "src go";
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--s-2) var(--s-3);
  width: 100%;
  padding: var(--s-4);
  text-align: left;
  border-top: 1px solid var(--hairline);
  transition: background-color var(--t-fast) var(--ease-out-soft);
}

.rows > li:first-child .row {
  border-top: 0;
}

.row:hover {
  background: var(--surface-raised);
}

.row:active {
  background: var(--surface-sunken);
}

.c {
  min-width: 0;
}

.c.date {
  display: none;
}

.who {
  grid-area: who;
  display: flex;
  flex-direction: column;
  gap: 0.1875rem;
}

.kl {
  font: var(--t-label);
  font-weight: 600;
  letter-spacing: var(--track-label);
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kt {
  font: var(--t-body-sm);
  color: var(--ink-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.kb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  margin-top: 0.1875rem;
}

.npwp {
  font-size: 0.6875rem;
  color: var(--ink-3);
  letter-spacing: 0.01em;
}

.note-line {
  font: var(--t-caption);
  color: var(--ink-3);
  font-style: italic;
}

.amt {
  grid-area: amt;
  font-size: var(--t-figure-sm);
  letter-spacing: -0.015em;
  text-align: right;
  color: var(--ink);
  white-space: nowrap;
}

.cat {
  grid-area: cat;
  justify-self: end;
}

.src {
  grid-area: src;
}

.go {
  grid-area: go;
  justify-self: end;
  color: var(--ink-3);
  transition: transform var(--t-fast) var(--ease-out-soft);
}

.row:hover .go {
  transform: translateX(2px);
}

.empty {
  padding: var(--s-10) var(--s-5);
  text-align: center;
  color: var(--ink-3);
  font: var(--t-body);
}

/* A row that is waiting on an answer says so before anything else, with a rail
   rather than a colour change alone. */
.flagged .row:has(.t-ask) {
  box-shadow: inset 3px 0 0 var(--cat-ask-ink);
}

/* ---- Tablet: two columns still, but with the date back in the row ---------- */
@media (min-width: 640px) {
  .row {
    grid-template-areas:
      "date who amt"
      "date cat src";
    grid-template-columns: 4.25rem minmax(0, 1fr) auto;
    row-gap: var(--s-3);
  }

  .c.date {
    grid-area: date;
    display: flex;
    flex-direction: column;
    align-self: start;
    gap: 0.0625rem;
    padding-top: 0.125rem;
  }

  .d {
    font: var(--t-label-sm);
    font-weight: 600;
    color: var(--ink-2);
    white-space: nowrap;
  }

  .t {
    font-size: 0.6875rem;
    color: var(--ink-3);
  }

  .who {
    align-self: start;
  }

  .amt {
    align-self: start;
    font-size: var(--t-figure-sm);
  }

  .cat {
    align-self: start;
    justify-self: start;
  }

  .src {
    align-self: center;
    justify-self: end;
  }

  .go {
    display: none;
  }
}

/* ---- Desktop: the ledger proper ------------------------------------------- */
@media (min-width: 1024px) {
  .head {
    display: grid;
    grid-template-columns: 5.5rem minmax(0, 1fr) 9rem 10.5rem 6.5rem 1.5rem;
    gap: var(--s-4);
    padding: var(--s-3) var(--s-5);
    background: var(--surface-sunken);
    border-bottom: 1px solid var(--hairline);
    font: var(--t-caption);
    font-weight: 600;
    letter-spacing: var(--track-caption);
    text-transform: uppercase;
    color: var(--ink-3);
  }

  .head .num {
    text-align: right;
  }

  .row {
    grid-template-areas: "date who amt cat src go";
    grid-template-columns: 5.5rem minmax(0, 1fr) 9rem 10.5rem 6.5rem 1.5rem;
    gap: var(--s-4);
    align-items: center;
    padding: var(--s-3) var(--s-5);
    min-height: 3.5rem;
  }

  .c.date {
    display: flex;
    flex-direction: row;
    align-items: baseline;
    gap: 0.375rem;
  }

  .cat,
  .src {
    align-self: center;
  }

  .src {
    justify-self: start;
  }

  .go {
    display: block;
    justify-self: end;
    opacity: 0;
  }

  .row:hover .go,
  .row:focus-visible .go {
    opacity: 1;
  }

  .kt {
    -webkit-line-clamp: 1;
    line-clamp: 1;
  }
}
</style>
