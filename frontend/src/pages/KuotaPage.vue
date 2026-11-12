<script setup lang="ts">
/** Quotas and the monthly plan. Numbers come from the API, not a local cap. */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppMeter from "@/components/ui/AppMeter.vue";
import AppPill from "@/components/ui/AppPill.vue";
import AppSegmented from "@/components/ui/AppSegmented.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import { CAPABILITIES } from "@/lib/capabilities";
import { PUBLIC_RULESET } from "@/lib/domain";
import { rupiah, tanggalPanjang } from "@/lib/format";
import { useKuotaStore } from "@/stores/kuota";
import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
const kuota = useKuotaStore();
const route = useRoute();
const galat = ref("");

const temaOpsi = [
  { value: "light", label: "Terang" },
  { value: "dark", label: "Gelap" },
];

const chat = computed(() => kuota.quotas?.assistant_chat);
const ai = computed(() => kuota.quotas?.ai_classification);
const rencana = computed(() => kuota.status?.available_plans?.[0]);
const harga = computed(() => (kuota.status ? rupiah(rencana.value?.price_idr ?? 25_000) : "—"));

function statusLabel(status?: string): string {
  if (status === "active") return "Aktif";
  if (status === "exhausted") return "Habis";
  return status || "—";
}

function statusPesanan(status: string): string {
  if (status === "pending") return "Menunggu bayar";
  if (status === "settlement") return "Lunas";
  if (status === "expire") return "Kedaluwarsa";
  if (status === "fail") return "Gagal";
  return status;
}

const ULANG_MAKS = 4;
const ULANG_JEDA_MS = 3000;
const mengonfirmasi = ref(false);
let pewaktu: ReturnType<typeof setTimeout> | null = null;

function hentikanUlang() {
  if (pewaktu) clearTimeout(pewaktu);
  pewaktu = null;
  mengonfirmasi.value = false;
}

/** The webhook settles a moment after the buyer returns: re-read a few times. */
function jadwalkanUlang(sisa: number) {
  if (kuota.berbayar || sisa <= 0) {
    hentikanUlang();
    return;
  }
  mengonfirmasi.value = true;
  pewaktu = setTimeout(async () => {
    pewaktu = null;
    await kuota.muat();
    jadwalkanUlang(sisa - 1);
  }, ULANG_JEDA_MS);
}

onMounted(async () => {
  await kuota.muat();
  if (route.name === "langganan-kembali") jadwalkanUlang(ULANG_MAKS);
});

onBeforeUnmount(hentikanUlang);

async function bayar() {
  galat.value = "";
  try {
    await kuota.buatPesanan(rencana.value?.plan_id || "monthly_25k");
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Pesanan gagal dibuat.";
  }
}

function gantiTema(nilai: string) {
  session.setTheme(nilai === "dark" ? "dark" : "light");
}
</script>

<template>
  <div class="page">
    <header class="lede">
      <div>
        <h2 class="t1">Kuota dan langganan</h2>
        <p class="sub">
          Kuota klasifikasi AI dan asisten. Tidak ada batas jumlah transaksi.
          <template v-if="route.name === 'langganan-kembali'">
            Status dibaca ulang setelah kembali dari gerbang.</template
          >
        </p>
      </div>
    </header>

    <section class="meter-grid kp-stagger" aria-label="Pemakaian bulan ini">
      <AppCard>
        <div class="angka">
          <p class="besar figure">{{ chat ? chat.used : "—" }}</p>
          <p class="dari">dari {{ chat ? chat.limit : "—" }} jawaban asisten</p>
        </div>
        <AppMeter
          v-if="chat"
          class="meter"
          :value="chat.used"
          :max="chat.limit"
          label="Jawaban asisten"
          :caption="statusLabel(chat.status)"
        >
          Reset
          {{ kuota.quotas ? tanggalPanjang(kuota.quotas.reset_timestamp_utc) : "belum dimuat" }} ({{
            kuota.quotas?.timezone
          }}).
        </AppMeter>
      </AppCard>

      <AppCard>
        <div class="angka">
          <p class="besar figure">{{ ai ? ai.used : "—" }}</p>
          <p class="dari">dari {{ ai ? ai.limit : "—" }} klasifikasi AI</p>
        </div>
        <AppMeter
          v-if="ai"
          class="meter"
          :value="ai.used"
          :max="ai.limit"
          label="Klasifikasi AI"
          :caption="statusLabel(ai.status)"
        >
          Habisnya kuota tidak menolak pencatatan transaksi. Baris tetap tersimpan dan menunggu
          klarifikasi.
        </AppMeter>
      </AppCard>
    </section>

    <section aria-labelledby="h-paket">
      <div class="sec-head">
        <div>
          <p class="u-eyebrow">Status akun</p>
          <h3 id="h-paket" class="t3">Tingkat akun dan paket</h3>
        </div>
      </div>

      <div class="plans">
        <AppCard class="plan" :class="{ on: kuota.berbayar }">
          <div class="plan-top">
            <h4 class="plan-nama">Akun {{ kuota.labelTier || "Gratis" }}</h4>
            <AppPill
              v-if="kuota.status"
              tone="accent"
              size="sm"
              :label="kuota.status.subscription_tier === 'berbayar' ? 'Berbayar' : 'Gratis'"
              icon="checkCircle"
            />
          </div>
          <div class="plan-harga">
            <template v-if="kuota.berbayar">
              <p class="harga figure">{{ harga }}</p>
              <p class="harga-cat">
                Paket aktif · 30 hari
                <template v-if="kuota.status?.valid_until_local">
                  · berlaku sampai {{ kuota.status.valid_until_local }}
                </template>
              </p>
            </template>
            <template v-else>
              <p class="harga figure">Rp 0</p>
              <p class="harga-cat">Tingkat gratis · pencatatan transaksi tanpa batas</p>
            </template>
          </div>
          <p v-if="kuota.pesan || galat || kuota.bayarPesan" class="plan-tag" role="alert">
            {{ galat || kuota.bayarPesan || kuota.pesan }}
          </p>
          <p v-if="mengonfirmasi && !kuota.berbayar" class="plan-tag" role="status">
            Pembayaran sedang dikonfirmasi...
          </p>
          <div v-if="CAPABILITIES.subscriptionPurchase" class="plan-cta">
            <p v-if="kuota.berbayar && kuota.status?.valid_until_utc" class="harga-cat">
              Berlaku sampai {{ tanggalPanjang(kuota.status.valid_until_utc) }}
            </p>
            <AppButton variant="primary" block :disabled="kuota.memproses" @click="bayar">{{
              kuota.memproses
                ? "Membuat tautan bayar…"
                : kuota.berbayar
                  ? "Perpanjang 30 hari"
                  : "Buat tautan bayar"
            }}</AppButton>
          </div>
          <p v-else-if="!kuota.berbayar" class="plan-tag">
            Paket berbayar ({{ harga }} / 30 hari) sedang disiapkan dan akan segera tersedia.
          </p>
          <ul v-if="CAPABILITIES.subscriptionPurchase && kuota.orders.length" class="fitur">
            <li v-for="order in kuota.orders" :key="order.order_id">
              <span class="fitur-label">{{ order.order_id }}</span>
              <span class="fitur-nilai"
                >{{ statusPesanan(order.status) }} · {{ rupiah(order.amount_idr) }}</span
              >
            </li>
          </ul>
          <p class="plan-kaki">
            Paket tidak mengubah tarif atau dasar perhitungan {{ PUBLIC_RULESET.nama }}.
          </p>
        </AppCard>
      </div>
    </section>

    <AppCard title="Tampilan" subtitle="Disimpan di perangkat ini dan berlaku untuk semua halaman.">
      <div class="tema">
        <span class="tema-ic">
          <AppIcon
            :name="session.theme === 'dark' ? 'bulan' : 'matahari'"
            :size="18"
            :stroke-width="1.7"
          />
        </span>
        <div class="tema-teks">
          <p class="tema-judul">
            {{ session.theme === "dark" ? "Mode gelap" : "Mode terang" }}
          </p>
          <p class="tema-sub">
            Mode gelap mengurangi cahaya saat dipakai pada malam hari. Kontras dan kebalikannya
            mengikuti setelan sistem serta aplikasi.
          </p>
        </div>
        <AppSegmented
          class="tema-seg"
          :model-value="session.theme"
          :options="temaOpsi"
          aria-label="Tampilan aplikasi"
          @update:model-value="gantiTema"
        />
      </div>
    </AppCard>

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

/* ---- Current usage --------------------------------------------------- */

.meter-grid {
  display: grid;
  gap: var(--s-4);
  grid-template-columns: 1fr;
}

@media (min-width: 768px) {
  .meter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--s-6);
  }
}

.angka {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--s-2);
}

.besar {
  font: var(--t-figure);
  letter-spacing: -0.02em;
}

@media (min-width: 768px) {
  .besar {
    font-size: 1.75rem;
  }
}

.dari {
  font: var(--t-body-sm);
  color: var(--ink-3);
}

.meter {
  margin-top: var(--s-5);
}

/* ---- Plans ------------------------------------------------------------ */

.sec-head {
  margin-bottom: var(--s-4);
}

.t3 {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  margin-top: var(--s-1);
}

.plans {
  display: grid;
  gap: var(--s-4);
  grid-template-columns: 1fr;
}

@media (min-width: 768px) {
  .plans {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--s-6);
  }
}

.plan {
  display: flex;
  flex-direction: column;
  border-color: var(--hairline-strong);
}

.plan.on {
  border-color: var(--accent-line);
}

.plan :deep(.body) {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  flex: 1;
}

.plan-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
}

.plan-nama {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
}

.plan-harga {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.harga {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
}

.harga-cat {
  font: var(--t-caption);
  color: var(--ink-3);
  line-height: 1.45;
}

.plan-tag {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}

.fitur {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--hairline);
}

.fitur li {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--hairline);
  color: var(--accent);
}

.fitur li.off {
  color: var(--ink-3);
}

.fitur-label {
  font: var(--t-body-sm);
  color: var(--ink);
  flex: 1;
  min-width: 0;
}

.fitur-nilai {
  font: var(--t-body-sm);
  color: var(--ink-2);
  text-align: right;
  flex: none;
  max-width: 45%;
}

.fitur li.off .fitur-nilai {
  color: var(--ink-3);
}

.plan-cta {
  margin-top: auto;
}

.plan-kaki {
  font: var(--t-caption);
  color: var(--ink-3);
  line-height: 1.45;
  padding-top: var(--s-3);
  border-top: 1px solid var(--hairline);
}

.demo {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
  margin-top: var(--s-4);
}

/* ---- Appearance ------------------------------------------------------- */

.tema {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: var(--s-4);
}

.tema-ic {
  display: grid;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  flex: none;
  border-radius: var(--r-md);
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
}

.tema-teks {
  flex: 1 1 14rem;
  min-width: 0;
}

.tema-judul {
  font: var(--t-label);
  font-weight: 600;
  letter-spacing: var(--track-label);
  color: var(--ink);
}

.tema-sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.45;
  margin-top: var(--s-1);
}

.tema-seg {
  flex: 1 1 100%;
}

@media (min-width: 560px) {
  .tema-seg {
    flex: 0 1 11rem;
    margin-left: auto;
  }
}
</style>
