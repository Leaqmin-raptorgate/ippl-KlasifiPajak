<script setup lang="ts">
/** Workspace overview. Every figure is a field from the dashboard or recap. */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppMeter from "@/components/ui/AppMeter.vue";
import AppPill from "@/components/ui/AppPill.vue";
import StatCard from "@/components/app/StatCard.vue";
import TransactionLedger from "@/components/app/TransactionLedger.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import { KATEGORI_LABEL } from "@/lib/domain";
import { bulanTahun, persen, rupiah, rupiahPlain, rupiahShort } from "@/lib/format";
import { usePajakStore } from "@/stores/pajak";
import { useTransaksiStore } from "@/stores/transaksi";

const store = useTransaksiStore();
const pajak = usePajakStore();
const router = useRouter();
const pdfPesan = ref("");

const pita = computed(() => pajak.dashboard?.thresholds.pita_500_juta);
const tahun = computed(() => pajak.dashboard?.thresholds.monitoring_current_year_cap_4_8m);
const lalu = computed(() => pajak.dashboard?.thresholds.eligibility_prior_year_cap_4_8m);
const pasal = computed(() => pajak.dashboard?.thresholds.pasal_58);

const rasioBebas = computed(() => {
  const band = pita.value;
  if (!band || band.limit_idr === 0) return 0;
  return band.ytd_usaha_omzet_idr / band.limit_idr;
});
const sudahLewati = computed(() =>
  pita.value
    ? pita.value.remaining_free_band_idr === 0 && pita.value.ytd_usaha_omzet_idr > 0
    : false,
);

const STATUS_LABEL: Record<string, string> = {
  scheme_eligible: "Memenuhi syarat",
  scheme_ineligible: "Tidak memenuhi syarat",
  unverifiable: "Belum dapat diperiksa",
};

const OVER_LABEL: Record<string, string> = {
  nihil: "Nihil",
  belum_diperhitungkan: "Belum diperhitungkan",
};

const statusSkema = computed(() => STATUS_LABEL[lalu.value?.status ?? ""] ?? "—");

const breakdown = computed(() => {
  const now = tahun.value;
  const months = pajak.dashboard?.monthly_summaries ?? [];
  const bukan = months.reduce((sum, row) => sum + row.non_object_omzet_idr, 0);
  return [
    { key: "usaha", label: KATEGORI_LABEL.usaha, total: now?.ytd_usaha_omzet_idr ?? 0 },
    {
      key: "pekerjaan_bebas",
      label: KATEGORI_LABEL.pekerjaan_bebas,
      total: now?.ytd_pekerjaan_bebas_omzet_idr ?? 0,
    },
    {
      key: "already_final",
      label: KATEGORI_LABEL.already_final,
      total: now?.ytd_already_final_omzet_idr ?? 0,
    },
    { key: "non_object", label: KATEGORI_LABEL.non_object, total: bukan },
  ];
});

const terbaru = computed(() => store.items.slice(0, 5));

onMounted(() => {
  void pajak.muat();
  void store.muat({ per_page: 5 }).catch(() => undefined);
});

function goto(id: string) {
  router.push(`/transaksi/${id}`);
}

async function unduh() {
  pdfPesan.value = "";
  try {
    await pajak.unduhPdf();
  } catch (error) {
    pdfPesan.value = error instanceof ApiFailure ? error.message : "Unduh gagal.";
    if (error instanceof ApiFailure && error.code === "PAID_SUBSCRIPTION_REQUIRED") {
      await router.push("/kuota");
    }
  }
}
</script>

<template>
  <div class="page">
    <header class="lede">
      <div>
        <h2 class="t1">Omzet usaha tahun ini</h2>
        <p class="sub">
          Batas bebas pajak berlaku pada omzet usaha saja. Penghasilan pekerjaan bebas tidak ikut
          memakai batas ini.
        </p>
      </div>
      <div class="acts">
        <AppButton variant="outline" icon="unduh" @click="unduh">Unduh workpaper</AppButton>
        <AppButton to="/transaksi/baru" variant="primary" icon="tambah">
          Catat transaksi
        </AppButton>
      </div>
    </header>

    <AppCard class="hero">
      <div class="hero-grid">
        <div class="hero-main">
          <p class="eyebrow">Sisa omzet bebas pajak</p>
          <p v-if="pajak.pesan" class="basis" role="alert">{{ pajak.pesan }}</p>
          <p v-if="pdfPesan" class="basis" role="alert">{{ pdfPesan }}</p>
          <p class="big figure">{{ pita ? rupiah(pita.remaining_free_band_idr) : "—" }}</p>
          <p class="basis">
            dari {{ pita ? rupiah(pita.limit_idr) : "—" }} batas usaha
            <template v-if="pita?.split_month">
              · terbelah pada {{ bulanTahun(pita.split_month + "-01") }}
            </template>
          </p>
          <AppMeter
            v-if="pita"
            class="meter"
            :value="pita.ytd_usaha_omzet_idr"
            :max="pita.limit_idr"
            :label="`Omzet usaha ${rupiah(pita.ytd_usaha_omzet_idr)}`"
            :caption="persen(rasioBebas * 100, 0)"
          >
            <template v-if="pita.annotation">{{ pita.annotation }}</template>
            <template v-else-if="sudahLewati">Sisa pita bebas usaha adalah nol.</template>
            <template v-else>Pita ini hanya memakai omzet usaha.</template>
          </AppMeter>
        </div>

        <div class="hero-side">
          <p class="cap">Susunan seluruh omzet yang tercatat</p>

          <dl class="mix">
            <div v-for="b in breakdown" :key="b.key" class="mix-row">
              <dt>
                <AppPill
                  size="sm"
                  :label="b.label"
                  :tone="
                    b.key === 'usaha'
                      ? 'usaha'
                      : b.key === 'pekerjaan_bebas'
                        ? 'bebas'
                        : b.key === 'already_final'
                          ? 'final'
                          : 'non'
                  "
                />
              </dt>
              <dd class="figure">{{ rupiahPlain(b.total) }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </AppCard>

    <section class="stats" aria-label="Ringkasan">
      <div class="stat-grid kp-stagger">
        <StatCard
          label="Gabungan tahun berjalan"
          :value="tahun ? rupiahShort(tahun.ytd_combined_gross_idr) : '—'"
          :caption="pasal?.badge_label ?? 'Menunggu dasbor'"
          icon="transaksi"
        />
        <StatCard
          label="Omzet usaha"
          :value="tahun ? rupiahShort(tahun.ytd_usaha_omzet_idr) : '—'"
          caption="Dari cuplikan, bukan dari penjumlahan baris"
          icon="toko"
          tone="accent"
        />
        <StatCard
          label="Pekerjaan bebas"
          :value="tahun ? rupiahShort(tahun.ytd_pekerjaan_bebas_omzet_idr) : '—'"
          caption="Bukan dasar PPh final 0,5%. Tidak ada estimasi Pasal 17."
          icon="pena"
        />
        <StatCard
          label="Cap tahun lalu"
          :value="statusSkema"
          :caption="lalu ? rupiah(lalu.combined_prior_year_gross_idr) : 'Menunggu dasbor'"
          icon="helpCircle"
          :tone="lalu?.status === 'scheme_ineligible' ? 'warn' : 'default'"
        />
      </div>
    </section>

    <section v-if="pajak.dashboard" aria-labelledby="h-bulan">
      <div class="sec-head">
        <h3 id="h-bulan" class="t3">Cuplikan bulan</h3>
        <AppButton variant="ghost" size="sm" @click="pajak.hitungUlang()"
          >Hitung ulang yang usang</AppButton
        >
      </div>
      <AppCard flush>
        <ul class="mix">
          <li v-for="bulan in pajak.dashboard.monthly_summaries" :key="bulan.month" class="mix-row">
            <span>{{ bulanTahun(bulan.month + "-01") }}</span>
            <span class="figure">omzet {{ rupiahPlain(bulan.usaha_omzet_idr) }}</span>
            <span class="figure">pajak {{ rupiahPlain(bulan.tax_0_5_pct_idr) }}</span>
            <span class="figure">sisa {{ rupiahPlain(bulan.sisa_bayar_idr) }}</span>
            <AppPill
              size="sm"
              :label="OVER_LABEL[bulan.overwithheld_status] ?? bulan.overwithheld_status"
              :tone="bulan.overwithheld_status === 'nihil' ? 'neutral' : 'ask'"
            />
          </li>
        </ul>
      </AppCard>
      <p v-if="pajak.recap" class="sub">
        Rekap usaha {{ rupiah(pajak.recap.total_usaha_omzet_idr) }}, kena
        {{ rupiah(pajak.recap.total_porsi_kena_idr) }}, pajak
        {{ rupiah(pajak.recap.total_tax_0_5_pct_idr) }}, sisa
        {{ rupiah(pajak.recap.total_sisa_bayar_idr) }}. KAP/KJS {{ pajak.recap.kap_kjs }}.
      </p>
      <p v-else-if="pajak.recapPesan" class="sub">{{ pajak.recapPesan }}</p>
    </section>

    <section aria-labelledby="h-terbaru">
      <div class="sec-head">
        <h3 id="h-terbaru" class="t3">Transaksi terbaru</h3>
        <RouterLink to="/transaksi" class="more">
          Lihat semua
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M5 12h13M13 6l6 6-6 6"
              fill="none"
              stroke="currentColor"
              :stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </RouterLink>
      </div>
      <TransactionLedger :rows="terbaru" @open="goto" />
      <WorkpaperNote class="stamp" />
    </section>
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
  gap: var(--s-3);
}

.acts > * {
  flex: 1;
}

@media (min-width: 640px) {
  .acts > * {
    flex: none;
  }
}

.hero-grid {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
}

@media (min-width: 900px) {
  .hero-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
    gap: var(--s-8);
  }
}

.eyebrow {
  font: var(--t-caption);
  font-weight: 600;
  letter-spacing: var(--track-caption);
  text-transform: uppercase;
  color: var(--ink-3);
}

.big {
  font-size: clamp(1.875rem, 5vw, 2.5rem);
  line-height: 1.1;
  letter-spacing: -0.028em;
  font-weight: 600;
  margin-top: var(--s-2);
}

.basis {
  font: var(--t-body-sm);
  color: var(--ink-3);
  margin-top: var(--s-1);
}

.meter {
  margin-top: var(--s-5);
}

.cap {
  font: var(--t-caption);
  letter-spacing: var(--track-caption);
  color: var(--ink-3);
  text-transform: uppercase;
  font-weight: 600;
}

.mix {
  display: flex;
  flex-direction: column;
  margin-top: var(--s-3);
  border-top: 1px solid var(--hairline);
}

.mix-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--hairline);
}

.mix-row:last-child {
  border-bottom: 0;
}

.mix-row dd {
  font-size: var(--t-body);
  color: var(--ink);
  white-space: nowrap;
}

.stat-grid {
  display: grid;
  gap: var(--s-3);
  grid-template-columns: 1fr;
}

@media (min-width: 520px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1100px) {
  .stat-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  margin-bottom: var(--s-4);
}

.more {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  /* The text is small, so the padding is what carries the touch target. */
  min-height: 2.75rem;
  padding-inline: var(--s-2);
  margin-inline: calc(var(--s-2) * -1);
  font: var(--t-label);
  letter-spacing: var(--track-label);
  color: var(--accent);
  font-weight: 600;
  white-space: nowrap;
}

.more svg {
  width: 0.9375rem;
  height: 0.9375rem;
  transition: transform var(--t-fast) var(--ease-out-soft);
}

.more:hover svg {
  transform: translateX(2px);
}

.stamp {
  margin-top: var(--s-3);
}
</style>
