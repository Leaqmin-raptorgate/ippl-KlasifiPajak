<script setup lang="ts">
/** Workspace overview. Every figure is a field from the dashboard, a month snapshot, or the recap. */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppMeter from "@/components/ui/AppMeter.vue";
import AppPill from "@/components/ui/AppPill.vue";
import AppSheet from "@/components/ui/AppSheet.vue";
import StatCard from "@/components/app/StatCard.vue";
import TransactionLedger from "@/components/app/TransactionLedger.vue";
import PanduanPanel from "@/components/app/PanduanPanel.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import { CAPABILITIES } from "@/lib/capabilities";
import { KATEGORI_LABEL } from "@/lib/domain";
import { bulanTahun, persen, rupiah, rupiahPlain, rupiahShort, tanggalPanjang } from "@/lib/format";
import { usePajakStore } from "@/stores/pajak";
import { usePanduanStore } from "@/stores/panduan";
import { useSessionStore } from "@/stores/session";
import { useTransaksiStore } from "@/stores/transaksi";
import type { MonthSummary } from "@/lib/wire";

/** A table row: one month, or the folded run of empty months at the start of the year. */
type BarisBulan =
  | { kind: "bulan"; key: string; bulan: MonthSummary }
  | { kind: "ringkas"; key: string; awal: string; akhir: string; tahun: string };

const store = useTransaksiStore();
const pajak = usePajakStore();
const panduan = usePanduanStore();
const session = useSessionStore();
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
/** Real share of the Rp4,8 M cap, not the warning threshold (`cap_warning_percent`). */
const persenGabungan = computed(() => {
  const now = tahun.value;
  if (!now || now.limit_idr === 0) return 0;
  return Math.round((now.ytd_combined_gross_idr * 100) / now.limit_idr);
});
/**
 * The API sends a remaining free band of 0 when the prior-year check does not
 * pass. That 0 is "not computed", so the hero shows a dash and the reason.
 */
const sisaTidakDihitung = computed(
  () => lalu.value?.status === "unverifiable" || lalu.value?.status === "scheme_ineligible",
);
const alasanSisa = computed(() =>
  lalu.value?.status === "unverifiable"
    ? "Isi peredaran bruto tahun lalu di Profil untuk menghitung sisa."
    : "Skema PPh final 0,5% tidak berlaku, jadi tidak ada sisa pita bebas.",
);
const sudahLewati = computed(() =>
  pita.value
    ? pita.value.remaining_free_band_idr === 0 && pita.value.ytd_usaha_omzet_idr > 0
    : false,
);
/**
 * Turnover still parked on provisional rows. The engine's band stays exactly as
 * it was computed; this only qualifies how much of it is still unconfirmed.
 */
const omzetBelumTerklasifikasi = computed(() => pita.value?.provisional_omzet_idr ?? 0);

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
const alasanSkema = computed(() => {
  const alasanApi = pajak.dashboard?.monthly_summaries.find(
    (bulan) => bulan.annotation,
  )?.annotation;
  if (alasanApi) return alasanApi;
  if (lalu.value?.status === "scheme_ineligible") {
    return `Omzet gabungan tahun lalu ${rupiah(lalu.value.combined_prior_year_gross_idr)} melampaui batas ${rupiah(lalu.value.limit_idr)}.`;
  }
  if (lalu.value?.status === "unverifiable") {
    return "Data omzet tahun lalu belum lengkap, sehingga batas kelayakan belum dapat diperiksa.";
  }
  return "";
});
const skemaTidakDihitung = computed(
  () => lalu.value?.status === "scheme_ineligible" || lalu.value?.status === "unverifiable",
);
/** The PDF still prints PPh as 0 for a year that cannot be checked. */
const bolehUnduh = computed(
  () => CAPABILITIES.workpaperExport && lalu.value?.status !== "unverifiable",
);

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

/** A month with no turnover, no tax and no nihil-free figure: nothing to show. */
function bulanKosong(bulan: MonthSummary): boolean {
  return (
    bulan.overwithheld_status === "nihil" &&
    [
      bulan.usaha_omzet_idr,
      bulan.porsi_bebas_idr,
      bulan.porsi_kena_idr,
      bulan.tax_0_5_pct_idr,
      bulan.withheld_tax_idr,
      bulan.sisa_bayar_idr,
      bulan.overwithheld_excess_idr,
      bulan.pekerjaan_bebas_omzet_idr,
      bulan.already_final_omzet_idr,
      bulan.non_object_omzet_idr,
    ].every((nilai) => nilai === 0)
  );
}

const tampilSemuaBulan = ref(false);

/**
 * Leading empty months of the year, collapsed into one line. Only runs of two or
 * more are folded. Months with data always show. Not applied when the scheme
 * result is not computed, because a zero there means "unknown", not "no turnover".
 */
const bulanKosongAwal = computed(() => {
  if (skemaTidakDihitung.value) return 0;
  const semua = pajak.dashboard?.monthly_summaries ?? [];
  const tahun = semua[0]?.month.slice(0, 4);
  let n = 0;
  for (const bulan of semua) {
    if (bulan.month.slice(0, 4) !== tahun || !bulanKosong(bulan)) break;
    n += 1;
  }
  return n >= 2 ? n : 0;
});

const daftarBulan = computed<BarisBulan[]>(() => {
  const semua = pajak.dashboard?.monthly_summaries ?? [];
  const semuaBaris: BarisBulan[] = semua.map((bulan) => ({
    kind: "bulan",
    key: bulan.month,
    bulan,
  }));
  const n = bulanKosongAwal.value;
  if (n === 0 || tampilSemuaBulan.value) return semuaBaris;
  const pertama = semua[0];
  const terakhir = semua[n - 1];
  if (!pertama || !terakhir) return semuaBaris;
  return [
    {
      kind: "ringkas",
      key: `ringkas-${pertama.month}`,
      awal: namaBulanPendek(pertama.month),
      akhir: namaBulanPendek(terakhir.month),
      tahun: pertama.month.slice(0, 4),
    },
    ...semuaBaris.slice(n),
  ];
});

function namaBulanPendek(bulanIso: string): string {
  return bulanTahun(`${bulanIso}-01`).split(" ")[0] ?? bulanIso;
}

onMounted(() => {
  void pajak.muat().then(() => {
    if (session.user && pajak.dashboard) void panduan.muat();
    else panduan.bersihkan();
  });
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

function labelStatusCuplikan(status: string): string {
  if (status === "berlaku") return "Berlaku";
  if (status === "usang") return "Usang";
  return status;
}

/** The open sheet's snapshot, ignored when it is no longer the selected month. */
const jejakCuplikan = computed(() => {
  const cuplikan = pajak.jejakCuplikan;
  if (!pajak.jejakBulan || !cuplikan || cuplikan.month !== pajak.jejakBulan) return null;
  return cuplikan;
});

const jejakGalat = computed(() =>
  !pajak.jejakMemuat && pajak.jejakKode && pajak.jejakKode !== "SNAPSHOT_NOT_FOUND"
    ? pajak.jejakPesan
    : "",
);

const jejakBaris = computed(() => {
  const cuplikan = jejakCuplikan.value;
  if (!cuplikan) return [];
  const tidakDihitung =
    cuplikan.scheme_eligibility_status === "scheme_ineligible" ||
    cuplikan.scheme_eligibility_status === "unverifiable";
  const baris: { field: string; label: string; value: string }[] = [
    { field: "month", label: "Bulan", value: bulanTahun(`${cuplikan.month}-01`) },
    { field: "usaha_omzet_idr", label: "Omzet usaha", value: rupiah(cuplikan.usaha_omzet_idr) },
    { field: "porsi_bebas_idr", label: "Porsi bebas", value: rupiah(cuplikan.porsi_bebas_idr) },
    { field: "porsi_kena_idr", label: "Porsi kena", value: rupiah(cuplikan.porsi_kena_idr) },
    {
      field: "tax_0_5_pct_idr",
      label: "Pajak 0,5%",
      value: tidakDihitung ? "Tidak dihitung di sini" : rupiah(cuplikan.tax_0_5_pct_idr),
    },
    {
      field: "withheld_tax_idr",
      label: "Pajak dipotong",
      value: rupiah(cuplikan.withheld_tax_idr),
    },
    {
      field: "sisa_bayar_idr",
      label: "Kurang bayar",
      value: tidakDihitung ? "Tidak dihitung di sini" : rupiah(cuplikan.sisa_bayar_idr),
    },
    {
      field: "overwithheld_excess_idr",
      label: "Lebih potong",
      value: tidakDihitung ? "Tidak dihitung di sini" : rupiah(cuplikan.overwithheld_excess_idr),
    },
    {
      field: "overwithheld_status",
      label: "Status lebih potong",
      value: tidakDihitung
        ? "Tidak dihitung di sini"
        : (OVER_LABEL[cuplikan.overwithheld_status] ?? cuplikan.overwithheld_status),
    },
    {
      field: "pekerjaan_bebas_omzet_idr",
      label: "Omzet pekerjaan bebas",
      value: rupiah(cuplikan.pekerjaan_bebas_omzet_idr),
    },
    {
      field: "already_final_omzet_idr",
      label: "Omzet final tersendiri",
      value: rupiah(cuplikan.already_final_omzet_idr),
    },
    {
      field: "non_object_omzet_idr",
      label: "Omzet bukan objek",
      value: rupiah(cuplikan.non_object_omzet_idr),
    },
    { field: "input_hash", label: "Hash masukan", value: cuplikan.input_hash },
    { field: "ruleset_id", label: "Ruleset", value: cuplikan.ruleset_id },
    {
      field: "effective_date",
      label: "Berlaku",
      value: tanggalPanjang(cuplikan.effective_date),
    },
    { field: "version", label: "Versi", value: String(cuplikan.version) },
    { field: "status", label: "Status", value: labelStatusCuplikan(cuplikan.status) },
  ];
  if (cuplikan.rounding_rule) {
    baris.push({ field: "rounding_rule", label: "Pembulatan", value: cuplikan.rounding_rule });
  }
  if (cuplikan.scheme_eligibility_status) {
    baris.push({
      field: "scheme_eligibility_status",
      label: "Kelayakan skema",
      value: STATUS_LABEL[cuplikan.scheme_eligibility_status] ?? cuplikan.scheme_eligibility_status,
    });
  }
  const catatan =
    cuplikan.annotation ||
    (cuplikan.scheme_eligibility_status === "scheme_ineligible"
      ? "Skema PPh Final 0,5% tidak berlaku."
      : cuplikan.scheme_eligibility_status === "unverifiable"
        ? "Data omzet tahun lalu belum lengkap, sehingga batas kelayakan belum dapat diperiksa."
        : "");
  if (catatan) {
    baris.push({ field: "annotation", label: "Catatan", value: catatan });
  }
  return baris;
});

onBeforeUnmount(() => {
  pajak.tutupJejakBulan();
});
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
        <AppButton v-if="!pajak.dashboard" to="/profil" variant="primary" icon="profil">
          Buat profil tahun pajak
        </AppButton>
        <AppButton v-else-if="bolehUnduh" variant="outline" icon="unduh" @click="unduh">
          Unduh workpaper
        </AppButton>
        <AppButton
          to="/transaksi/baru"
          :variant="pajak.dashboard ? 'primary' : 'outline'"
          icon="tambah"
        >
          Catat transaksi
        </AppButton>
      </div>
    </header>

    <AppCard class="hero">
      <div class="hero-grid">
        <div class="hero-main">
          <p class="eyebrow">Sisa omzet bebas pajak</p>
          <div v-if="!pajak.dashboard && pajak.pesan" class="onboarding-box">
            <p class="onboarding-teks" role="alert">{{ pajak.pesan }}</p>
            <AppButton to="/profil" variant="primary" size="sm" icon="profil">
              Buat profil sekarang
            </AppButton>
          </div>
          <p v-if="pdfPesan" class="basis" role="alert">{{ pdfPesan }}</p>
          <p class="big figure">
            {{ pita && !sisaTidakDihitung ? rupiah(pita.remaining_free_band_idr) : "—" }}
          </p>
          <p v-if="pita && sisaTidakDihitung" class="basis sisa-alasan">
            {{ alasanSisa }}
            <RouterLink v-if="lalu?.status === 'unverifiable'" to="/profil">Buka Profil</RouterLink>
          </p>
          <p class="basis">
            dari {{ pita ? rupiah(pita.limit_idr) : "—" }} batas usaha
            <template v-if="pita?.split_month">
              · terbelah pada {{ bulanTahun(pita.split_month + "-01") }}
            </template>
          </p>
          <div v-if="omzetBelumTerklasifikasi > 0" class="belum-wrap">
            <p class="belum">
              Dari {{ pita ? rupiah(pita.ytd_usaha_omzet_idr) : "—" }} omzet usaha di pita ini,
              {{ rupiah(omzetBelumTerklasifikasi) }} masih belum terklasifikasi. Menjawab
              baris-baris itu akan mengubah angka di atas.
            </p>
            <AppButton
              to="/transaksi?kategori=pending"
              variant="outline"
              size="sm"
              icon="helpCircle"
            >
              Jawab pertanyaan
            </AppButton>
          </div>
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

    <AppCard v-if="tahun?.cap_warning" class="cap-warning" role="status">
      <p class="cap-warning-title">Omzet gabungan mendekati batas tahun berjalan</p>
      <p>
        Omzet gabungan tercatat {{ rupiah(tahun.ytd_combined_gross_idr) }} atau
        {{ persenGabungan }}% dari batas {{ rupiah(tahun.limit_idr) }}. Peringatan ini tidak
        mengubah status kelayakan atau angka pajak.
      </p>
    </AppCard>

    <AppCard v-if="lalu?.status === 'unverifiable'" class="cap-warning" role="status">
      <p class="cap-warning-title">Data omzet tahun lalu belum lengkap</p>
      <p>
        Batas kelayakan skema PPh final 0,5% belum dapat diperiksa karena omzet tahun lalu belum
        diisi. Lengkapi profil tahun pajak untuk memastikan skema yang berlaku.
      </p>
      <div class="unverifiable-act">
        <AppButton to="/profil" variant="outline" size="sm" icon="profil">
          Lengkapi data profil
        </AppButton>
      </div>
    </AppCard>

    <section class="stats" aria-label="Ringkasan">
      <div class="stat-grid">
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
          label="Kelayakan skema (omzet lalu)"
          :value="statusSkema"
          value-kind="text"
          :caption="
            alasanSkema ||
            (lalu
              ? `Omzet gabungan: ${rupiah(lalu.combined_prior_year_gross_idr)}`
              : 'Menunggu dasbor')
          "
          icon="helpCircle"
          :tone="skemaTidakDihitung ? 'warn' : 'default'"
        />
      </div>
    </section>

    <PanduanPanel v-if="pajak.dashboard" />

    <section v-if="pajak.dashboard" aria-labelledby="h-bulan">
      <div class="sec-head">
        <h3 id="h-bulan" class="t3">Cuplikan bulan</h3>
        <AppButton variant="ghost" size="sm" @click="pajak.hitungUlang()"
          >Hitung ulang yang usang</AppButton
        >
      </div>
      <AppCard flush>
        <table id="tabel-bulan" class="tabel">
          <caption class="sr-only">
            Omzet, pajak, dan kurang bayar per bulan
          </caption>
          <thead>
            <tr>
              <th scope="col">Bulan</th>
              <th scope="col" class="num">Omzet usaha</th>
              <th scope="col" class="num">Pajak</th>
              <th scope="col" class="num">Kurang bayar</th>
              <th scope="col">Status</th>
              <th scope="col">Jejak</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="baris in daftarBulan" :key="baris.key">
              <tr v-if="baris.kind === 'ringkas'" class="ringkas">
                <td colspan="6">
                  {{ baris.awal }} - {{ baris.akhir }} {{ baris.tahun }}: tidak ada omzet yang
                  terhitung
                </td>
              </tr>
              <tr v-else>
                <th scope="row" class="bulan">{{ bulanTahun(baris.bulan.month + "-01") }}</th>
                <td class="num" data-label="Omzet usaha">
                  {{ rupiahPlain(baris.bulan.usaha_omzet_idr) }}
                </td>
                <template v-if="skemaTidakDihitung">
                  <td class="num muted" data-label="Pajak">Tidak dihitung di sini</td>
                  <td class="num" data-label="Kurang bayar">—</td>
                  <td class="muted" data-label="Status">{{ alasanSkema }}</td>
                </template>
                <template v-else>
                  <td class="num" data-label="Pajak">
                    {{ rupiahPlain(baris.bulan.tax_0_5_pct_idr) }}
                  </td>
                  <td class="num" data-label="Kurang bayar">
                    {{ rupiahPlain(baris.bulan.sisa_bayar_idr) }}
                  </td>
                  <td data-label="Status">
                    <AppPill
                      size="sm"
                      :label="
                        OVER_LABEL[baris.bulan.overwithheld_status] ??
                        baris.bulan.overwithheld_status
                      "
                      :tone="baris.bulan.overwithheld_status === 'nihil' ? 'neutral' : 'ask'"
                    />
                  </td>
                </template>
                <td data-label="Jejak">
                  <AppButton
                    variant="ghost"
                    size="sm"
                    :data-month="baris.bulan.month"
                    @click="pajak.bukaJejakBulan(baris.bulan.month)"
                  >
                    Lihat jejak
                  </AppButton>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </AppCard>
      <div v-if="bulanKosongAwal > 0" class="tabel-aksi">
        <AppButton
          variant="ghost"
          size="sm"
          aria-controls="tabel-bulan"
          :aria-expanded="tampilSemuaBulan ? 'true' : 'false'"
          @click="tampilSemuaBulan = !tampilSemuaBulan"
        >
          {{ tampilSemuaBulan ? "Sembunyikan bulan kosong" : "Tampilkan semua bulan" }}
        </AppButton>
      </div>
      <p v-if="CAPABILITIES.workpaperExport && pajak.recap && !skemaTidakDihitung" class="sub">
        Rekap usaha {{ rupiah(pajak.recap.total_usaha_omzet_idr) }}, kena
        {{ rupiah(pajak.recap.total_porsi_kena_idr) }}, pajak
        {{ rupiah(pajak.recap.total_tax_0_5_pct_idr) }}, sisa
        {{ rupiah(pajak.recap.total_sisa_bayar_idr) }}. KAP/KJS {{ pajak.recap.kap_kjs }}.
      </p>
      <p v-else-if="CAPABILITIES.workpaperExport && pajak.recapPesan" class="sub">
        {{ pajak.recapPesan }}
      </p>
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
      <TransactionLedger
        :rows="terbaru"
        empty-text="Belum ada transaksi yang tercatat tahun ini."
        @open="goto"
      />
      <WorkpaperNote class="stamp" />
    </section>

    <AppSheet
      :open="pajak.jejakBulan !== null"
      title="Jejak cuplikan"
      :subtitle="pajak.jejakBulan ? bulanTahun(pajak.jejakBulan + '-01') : ''"
      wide
      :error="jejakGalat"
      @close="pajak.tutupJejakBulan()"
    >
      <p v-if="pajak.jejakMemuat" class="jejak-muat">Memuat jejak bulan.</p>
      <div v-else-if="pajak.jejakKode === 'SNAPSHOT_NOT_FOUND'" class="jejak-kosong">
        <p class="jejak-kosong-judul">Belum ada cuplikan</p>
        <p>{{ pajak.jejakPesan }}</p>
      </div>
      <dl v-else-if="jejakBaris.length" class="jejak">
        <div v-for="bidang in jejakBaris" :key="bidang.field" class="jejak-row">
          <dt>{{ bidang.label }}</dt>
          <dd :class="{ hash: bidang.field === 'input_hash' }" :data-field="bidang.field">
            {{ bidang.value }}
          </dd>
        </div>
      </dl>
      <WorkpaperNote
        v-if="!pajak.jejakMemuat && jejakCuplikan"
        class="jejak-stamp"
        :ruleset-id="jejakCuplikan.ruleset_id"
        :effective-date="jejakCuplikan.effective_date"
      />
      <p
        v-if="!pajak.jejakMemuat && jejakCuplikan?.disclaimer"
        class="jejak-disclaimer"
        data-field="disclaimer"
      >
        {{ jejakCuplikan.disclaimer }}
      </p>
    </AppSheet>
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

/* The shell's h1 names the page; this h2 names the figures under it. */
.t1 {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
}

.sub {
  font: var(--t-body);
  color: var(--ink-2);
  max-width: 34rem;
  margin-top: var(--s-2);
}

.t3 {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
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

.belum {
  font: var(--t-body-sm);
  color: var(--cat-ask-ink);
  line-height: 1.45;
}

.belum-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-2);
  margin-top: var(--s-2);
  padding: var(--s-3);
  border-radius: var(--r-md);
  background: var(--cat-ask-bg);
  border: 1px solid var(--cat-ask-line);
}

.onboarding-box {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-3);
  margin-top: var(--s-3);
  padding: var(--s-4);
  border-radius: var(--r-md);
  background: var(--surface-sunken);
  border: 1px solid var(--hairline-strong);
}

.onboarding-teks {
  font: var(--t-body);
  color: var(--ink);
  line-height: 1.4;
}

.cap-warning {
  border-color: var(--cat-ask-line);
  background: var(--cat-ask-bg);
  color: var(--cat-ask-ink);
}

.cap-warning-title {
  margin-bottom: var(--s-1);
  font-weight: 650;
}

.unverifiable-act {
  margin-top: var(--s-3);
}

.meter {
  margin-top: var(--s-5);
}

/* The threshold bar is the one figure that must be read at a glance: a taller
   track, and no grow-in animation (the shared meter's is longer than a fade). */
.meter :deep(.track) {
  height: 0.75rem;
}

.meter :deep(.fill) {
  animation: none;
}

.meter :deep(.cap) {
  font-variant-numeric: tabular-nums;
  font-size: var(--t-label);
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

/* Monthly table. A real table from 640px; below that each row stacks into
   labelled lines (the header row is still in the DOM for assistive tech). */
.tabel-wrap {
  overflow-x: auto;
}

.tabel {
  width: 100%;
  border-collapse: collapse;
  font: var(--t-body);
  color: var(--ink);
}

.tabel th,
.tabel td {
  padding: var(--s-3) var(--s-4);
  text-align: left;
  vertical-align: middle;
  border-bottom: 1px solid var(--hairline);
}

.tabel tbody tr:last-child th,
.tabel tbody tr:last-child td {
  border-bottom: 0;
}

.tabel thead th {
  font: var(--t-label-sm);
  letter-spacing: var(--track-label-sm);
  font-weight: 600;
  color: var(--ink-2);
  white-space: nowrap;
}

.tabel .num {
  text-align: right;
}

.tabel td {
  font-size: var(--t-body-sm);
  color: var(--ink-2);
}

.tabel td.num {
  font-size: var(--t-body);
  color: var(--ink);
}

.tabel th.bulan {
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
}

.tabel .muted {
  color: var(--ink-2);
}

.tabel .ringkas td {
  font: var(--t-body-sm);
  color: var(--ink-2);
}

.tabel-aksi {
  margin-top: var(--s-3);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

.tabel td::before {
  display: none;
}

/* Small buttons keep a 44px phone target. */
@media (max-width: 639px) {
  .page :deep(.s-sm) {
    --btn-h: 2.75rem;
  }

  .tabel thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .tabel,
  .tabel tbody,
  .tabel tr,
  .tabel th,
  .tabel td {
    display: block;
    width: 100%;
  }

  .tabel tr {
    padding: var(--s-3) var(--s-4);
    border-bottom: 1px solid var(--hairline);
  }

  .tabel tbody tr:last-child {
    border-bottom: 0;
  }

  .tabel th,
  .tabel td {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-3);
    padding: var(--s-1) 0;
    border-bottom: 0;
    text-align: left;
  }

  .tabel th.bulan {
    margin-bottom: var(--s-1);
    font: var(--t-body);
  }

  .tabel td::before {
    display: block;
    flex: none;
    content: attr(data-label);
    font: var(--t-body-sm);
    color: var(--ink-3);
  }
}

.mix-row dd {
  font-size: var(--t-body);
  color: var(--ink);
  white-space: nowrap;
}

/* One column on a phone, two from 640px, four where a row of four fits. */
.stat-grid {
  display: grid;
  gap: var(--s-3);
  grid-template-columns: minmax(0, 1fr);
}

@media (min-width: 640px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--s-4);
  }
}

@media (min-width: 1024px) {
  .stat-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.sec-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2) var(--s-4);
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
}

.stamp {
  margin-top: var(--s-3);
}

.jejak {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  min-width: 0;
}

.jejak-row {
  display: grid;
  grid-template-columns: minmax(0, 9.5rem) minmax(0, 1fr);
  gap: var(--s-1) var(--s-3);
  min-width: 0;
}

.jejak-row dt {
  font: var(--t-caption);
  letter-spacing: var(--track-caption);
  color: var(--ink-3);
}

.jejak-row dd {
  min-width: 0;
  color: var(--ink);
  font: var(--t-body-sm);
  font-variant-numeric: tabular-nums;
}

.jejak-row dd.hash {
  font-family: var(--font-numeric);
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-all;
}

.jejak-muat,
.jejak-kosong,
.jejak-disclaimer {
  font: var(--t-body-sm);
  color: var(--ink-2);
  min-width: 0;
  overflow-wrap: anywhere;
}

.jejak-kosong-judul {
  font: var(--t-body);
  color: var(--ink);
  font-weight: 600;
  margin-bottom: var(--s-1);
}

.jejak-stamp {
  margin-top: var(--s-4);
}

.jejak-disclaimer {
  margin-top: var(--s-2);
}

@media (max-width: 639px) {
  .jejak-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
