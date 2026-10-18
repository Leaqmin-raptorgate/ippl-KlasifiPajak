<script setup lang="ts">
/** Ledger screen: every captured transaction, searchable and filterable in place. */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppField from "@/components/ui/AppField.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppInput from "@/components/ui/AppInput.vue";
import AppSegmented from "@/components/ui/AppSegmented.vue";
import AppSelect from "@/components/ui/AppSelect.vue";
import TransactionLedger from "@/components/app/TransactionLedger.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import { KATEGORI_LABEL, KATEGORI_RINGKAS, type Kategori } from "@/lib/domain";
import { useTransaksiStore } from "@/stores/transaksi";
import { bulanTahun, rupiah } from "@/lib/format";

const store = useTransaksiStore();
const router = useRouter();

const cari = ref("");
const kategori = ref("all");
const bulan = ref("all");
const galat = ref("");

const kategoriOpsi = computed(() => [
  { value: "all", label: "Semua" },
  ...(Object.keys(KATEGORI_LABEL) as Kategori[]).map((k) => ({
    value: k,
    label: KATEGORI_RINGKAS[k],
  })),
]);

const bulanOpsi = [
  { value: "all", label: "Semua bulan" },
  ...Array.from({ length: 12 }, (_, i) => {
    const key = `2026-${String(i + 1).padStart(2, "0")}`;
    return { value: key, label: bulanTahun(`${key}-01`) };
  }),
];

const hasil = computed(() =>
  store.items.filter((row) => kategori.value === "all" || row.category === kategori.value),
);

const totalHasil = computed(() => hasil.value.reduce((sum, row) => sum + row.amount_idr, 0));

const adaFilter = computed(
  () => cari.value !== "" || kategori.value !== "all" || bulan.value !== "all",
);

async function muat() {
  galat.value = "";
  try {
    await store.muat({
      client_name: cari.value.trim() || undefined,
      month: bulan.value === "all" ? undefined : bulan.value,
    });
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Daftar gagal dimuat.";
  }
}

function bersihkanFilter() {
  cari.value = "";
  kategori.value = "all";
  bulan.value = "all";
  void muat();
}

async function klasifikasiUlang() {
  galat.value = "";
  const ids = hasil.value.map((row) => row.id);
  if (ids.length === 0) return;
  try {
    await store.klasifikasiUlang(ids);
    await muat();
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Klasifikasi ulang gagal.";
  }
}

onMounted(() => {
  void muat();
});

function goto(id: string) {
  router.push(`/transaksi/${id}`);
}
</script>

<template>
  <div class="page">
    <header class="lede">
      <div>
        <h2 class="t1">Daftar transaksi</h2>
        <p class="sub">
          Satu baris satu transaksi, lengkap dengan kategori dan sumber klasifikasinya. Buka satu
          baris untuk melihat hasil dan alasan di baliknya.
        </p>
      </div>
      <div class="acts">
        <AppButton variant="outline" class="ekspor" @click="klasifikasiUlang">
          <span class="ekspor-label">Klasifikasi ulang</span>
        </AppButton>
        <AppButton to="/transaksi/baru" variant="primary" icon="tambah">
          Tambah transaksi
        </AppButton>
      </div>
    </header>

    <p v-if="galat" class="sub" role="alert">{{ galat }}</p>

    <AppCard flush>
      <div class="filter">
        <AppField label="Cari transaksi" for-id="cari">
          <AppInput id="cari" v-model="cari" placeholder="Nama klien" @change="() => muat()">
            <template #pre><AppIcon name="search" :size="16" /></template>
          </AppInput>
        </AppField>

        <AppField label="Bulan" for-id="bulan">
          <AppSelect
            id="bulan"
            v-model="bulan"
            :options="bulanOpsi"
            @update:model-value="() => muat()"
          />
        </AppField>

        <div class="kat">
          <p class="u-label">Kategori</p>
          <div class="kat-scroll">
            <AppSegmented
              class="kat-seg"
              v-model="kategori"
              :options="kategoriOpsi"
              aria-label="Saring menurut kategori"
            />
          </div>
        </div>
      </div>
    </AppCard>

    <section aria-label="Daftar transaksi">
      <div class="baris-atasan">
        <p class="count">
          Menampilkan {{ hasil.length }} dari
          {{ store.pagination?.total_items ?? hasil.length }} transaksi
          <template v-if="hasil.length">
            <span class="sep" aria-hidden="true">·</span>
            <span class="jumlah figure">{{ rupiah(totalHasil) }}</span>
          </template>
        </p>
        <AppButton v-if="adaFilter" variant="ghost" icon="tutup" @click="bersihkanFilter">
          Bersihkan filter
        </AppButton>
      </div>

      <TransactionLedger :rows="hasil" @open="goto" />
      <div v-if="store.pagination && store.pagination.total_pages > 1" class="baris-atasan">
        <AppButton
          variant="ghost"
          :disabled="store.pagination.current_page <= 1"
          @click="
            store.muat({
              page: store.pagination.current_page - 1,
              month: bulan === 'all' ? undefined : bulan,
              client_name: cari.trim() || undefined,
            })
          "
        >
          Sebelumnya
        </AppButton>
        <p class="count">
          Halaman {{ store.pagination.current_page }} dari {{ store.pagination.total_pages }}
        </p>
        <AppButton
          variant="ghost"
          :disabled="store.pagination.current_page >= store.pagination.total_pages"
          @click="
            store.muat({
              page: store.pagination.current_page + 1,
              month: bulan === 'all' ? undefined : bulan,
              client_name: cari.trim() || undefined,
            })
          "
        >
          Berikutnya
        </AppButton>
      </div>
    </section>

    <WorkpaperNote />
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  max-width: var(--canvas-max);
  margin-inline: auto;
}

.lede {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--s-4);
  flex-wrap: wrap;
}

.t1 {
  font: var(--t-title-1);
  letter-spacing: var(--track-title-1);
}

.sub {
  font: var(--t-body);
  color: var(--ink-2);
  max-width: 34rem;
  margin-top: var(--s-2);
}

.acts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3);
}

/* Content-sized basis, so two actions stack on a phone instead of pushing the
   page sideways. */
.acts > * {
  flex: 1 1 auto;
}

/* The export label is the first thing to go on a phone; the icon still says
   what it is, and the primary action keeps the width it needs. */
@media (max-width: 519px) {
  .acts > :first-child {
    flex: 0 0 auto;
  }

  .ekspor-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}

@media (min-width: 640px) {
  .acts > * {
    flex: none;
  }
}

/* A phone wants 40px targets; the md button is 38px. */
@media (max-width: 639px) {
  .acts > *,
  .baris-atasan > * {
    height: 2.5rem;
  }
}

.filter {
  display: grid;
  gap: var(--s-3);
  padding: var(--s-4) var(--s-5) var(--s-5);
}

@media (min-width: 640px) {
  .filter {
    grid-template-columns: minmax(0, 1fr) minmax(9.5rem, 12rem);
    gap: var(--s-4);
  }

  .kat {
    grid-column: 1 / -1;
  }
}

/* Three labelled controls on one line: search grows, the month keeps its size,
   and the category switch takes whatever is left. */
@media (min-width: 1024px) {
  .filter {
    grid-template-columns: minmax(0, 1fr) minmax(9.5rem, 12rem) minmax(0, 2fr);
    align-items: end;
  }

  .kat {
    grid-column: auto;
  }
}

.kat {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}

/* Five category names do not fit a phone in one row, so the switch scrolls
   sideways there instead of cutting every label down to three letters. */
.kat-scroll {
  overflow-x: auto;
  overscroll-behavior-x: contain;
  scrollbar-width: none;
  /* The set of categories is wider than a phone, so the control scrolls. Fade
     the trailing edge instead of cutting a chip in half: the cut chip is what
     tells the reader there is more to swipe to. */
  mask-image: linear-gradient(to right, #000 calc(100% - 1.25rem), transparent 100%);
}

@media (min-width: 640px) {
  .kat-scroll {
    mask-image: none;
  }
}

.kat-scroll::-webkit-scrollbar {
  display: none;
}

@media (max-width: 639px) {
  .kat-seg {
    min-width: 45rem;
  }
}

.baris-atasan {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  flex-wrap: wrap;
  margin-bottom: var(--s-4);
}

.count {
  font: var(--t-body-sm);
  color: var(--ink-3);
}

.jumlah {
  color: var(--ink-2);
}

.sep {
  margin-inline: var(--s-2);
  opacity: 0.5;
}
</style>
