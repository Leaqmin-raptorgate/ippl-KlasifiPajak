<script setup lang="ts">
/**
 * Review-and-resolve screen for one transaction's classification: the evidence
 * it was read from, the verdict with its honest confidence, and the manual
 * override that can move it.
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppField from "@/components/ui/AppField.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppInput from "@/components/ui/AppInput.vue";
import AppMeter from "@/components/ui/AppMeter.vue";
import AppPill from "@/components/ui/AppPill.vue";
import AppSelect from "@/components/ui/AppSelect.vue";
import AppSheet from "@/components/ui/AppSheet.vue";
import SourceTag from "@/components/app/SourceTag.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import {
  KATEGORI_LABEL,
  PUBLIC_RULESET,
  SOURCE_CHANNEL_LABEL,
  SUMBER_LABEL,
  type Kategori,
  type Sumber,
} from "@/lib/domain";
import { persen, rupiah, rupiahPlain, tanggal, tanggalPanjang } from "@/lib/format";
import { usePajakStore } from "@/stores/pajak";
import { useTransaksiStore } from "@/stores/transaksi";

const store = useTransaksiStore();
const pajak = usePajakStore();
const route = useRoute();
const router = useRouter();

const id = computed(() => {
  const raw = route.params.id;
  return Array.isArray(raw) ? (raw[0] ?? "") : (raw ?? "");
});

const row = computed(() => store.byId(id.value));
const galat = ref("");
const stampId = computed(() => pajak.dashboard?.metadata.ruleset_id || PUBLIC_RULESET.id);
const stampDate = computed(
  () => pajak.dashboard?.metadata.effective_date || PUBLIC_RULESET.berlaku,
);
const batasBebas = computed(
  () => pajak.dashboard?.thresholds.pita_500_juta.limit_idr ?? PUBLIC_RULESET.bebasUsaha,
);
const plafon = computed(
  () =>
    pajak.dashboard?.thresholds.monitoring_current_year_cap_4_8m.limit_idr ??
    PUBLIC_RULESET.plafonUsaha,
);

function labelKategori(value?: string) {
  return value && value in KATEGORI_LABEL ? KATEGORI_LABEL[value as Kategori] : "—";
}

const TONE: Record<Kategori, "usaha" | "bebas" | "final" | "non"> = {
  usaha: "usaha",
  pekerjaan_bebas: "bebas",
  already_final: "final",
  non_object: "non",
};

const kategoriOpsi = (Object.keys(KATEGORI_LABEL) as Kategori[]).map((k) => ({
  value: k,
  label: KATEGORI_LABEL[k],
}));

const sheetTerbuka = ref(false);
const kategoriBaru = ref("");
const catatanBaru = ref("");
/** Set only by this screen, so the answered question can collapse instead of vanish. */
const klarifikasiSelesai = ref(false);

const adaKeyakinan = computed(() => typeof row.value?.classification?.confidence === "number");
const keyakinan = computed(() => row.value?.classification?.confidence ?? 0);
const keyakinanRendah = computed(() => keyakinan.value < 0.8);

function bukaSheet() {
  if (!row.value) return;
  kategoriBaru.value = row.value.category;
  catatanBaru.value = "";
  sheetTerbuka.value = true;
}

function tutupSheet() {
  sheetTerbuka.value = false;
}

async function terapkan() {
  if (!row.value || kategoriBaru.value === "") return;
  galat.value = "";
  try {
    await store.override(
      row.value.id,
      kategoriBaru.value as Kategori,
      catatanBaru.value.trim() || undefined,
    );
    sheetTerbuka.value = false;
    await pajak.muat(true);
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Override gagal.";
  }
}

async function jawab(category: Kategori) {
  if (!row.value) return;
  galat.value = "";
  try {
    await store.jawab(row.value.id, category);
    klarifikasiSelesai.value = true;
    await pajak.muat(true);
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Klarifikasi gagal.";
  }
}

async function hapus() {
  if (!row.value) return;
  if (!window.confirm("Hapus transaksi ini? Cuplikan bulan itu akan dihitung ulang.")) return;
  galat.value = "";
  try {
    await store.hapus(row.value.id);
    await router.push("/transaksi");
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Hapus gagal.";
  }
}

onMounted(async () => {
  await pajak.muat();
  const found = await store.buka(id.value);
  if (!found) return;
  await store.muatKlarifikasi(found.id);
  await store.muatJejak(found.id);
});
</script>

<template>
  <div class="page">
    <div v-if="!row" class="col">
      <AppCard class="kosong">
        <div class="kosong-isi">
          <span class="kosong-ic"><AppIcon name="search" :size="22" /></span>
          <div>
            <p class="kosong-judul">Transaksi tidak ditemukan</p>
            <p class="kosong-sub">
              Tidak ada baris <span class="figure">{{ id || "—" }}</span> di daftar lokal ini. Baris
              bisa hilang kalau daftarnya dimuat ulang.
            </p>
          </div>
        </div>
        <AppButton to="/transaksi" variant="outline" icon="chevronLeft">
          Kembali ke daftar transaksi
        </AppButton>
      </AppCard>
    </div>

    <div v-else class="col">
      <header class="lede">
        <RouterLink to="/transaksi" class="back">
          <AppIcon name="chevronLeft" :size="16" :stroke-width="1.8" />
          Transaksi
        </RouterLink>
        <p class="u-eyebrow">{{ row.id }}</p>
        <h2 class="t1">{{ row.client_name }}</h2>
        <p class="sub">
          {{ tanggal(row.tx_date) }} ·
          <span class="figure">{{ rupiah(row.amount_idr) }}</span>
        </p>
      </header>

      <AppCard
        title="Bukti transaksi"
        subtitle="Fakta yang dicatat. Kategori dibaca dari fakta ini, bukan sebaliknya."
        inset
      >
        <dl class="dl">
          <div class="dl-row">
            <dt>Klien / lawan transaksi</dt>
            <dd>{{ row.client_name }}</dd>
          </div>
          <div class="dl-row">
            <dt>Deskripsi</dt>
            <dd>{{ row.description }}</dd>
          </div>
          <div class="dl-row">
            <dt>Saluran penjualan</dt>
            <dd>{{ SOURCE_CHANNEL_LABEL[row.source_channel] }}</dd>
          </div>
          <div class="dl-row utama">
            <dt>Nominal tercatat</dt>
            <dd>
              <span class="unit">Rp</span
              ><span class="figure">{{ rupiahPlain(row.amount_idr) }}</span>
            </dd>
          </div>
          <div v-if="row.invoice_no" class="dl-row">
            <dt>Nomor faktur / bukti potong</dt>
            <dd class="teks">{{ row.invoice_no }}</dd>
          </div>
          <div v-if="row.withheld_tax_amount_idr" class="dl-row">
            <dt>Pajak yang sudah dipotong</dt>
            <dd>
              <span class="unit">Rp</span
              ><span class="figure">{{ rupiahPlain(row.withheld_tax_amount_idr) }}</span>
            </dd>
          </div>
          <div class="dl-row">
            <dt>Ruleset</dt>
            <dd class="teks">{{ stampId }}</dd>
          </div>
          <div class="dl-row">
            <dt>Berlaku sejak</dt>
            <dd>{{ tanggalPanjang(stampDate) }}</dd>
          </div>
        </dl>
      </AppCard>

      <AppCard class="putusan">
        <div class="putusan-head">
          <p class="u-label">Kategori yang ditetapkan</p>
          <div class="putusan-nama">
            <span class="nama" :class="`i-${TONE[row.category]}`">
              {{ KATEGORI_LABEL[row.category] }}
            </span>
            <AppPill :label="KATEGORI_LABEL[row.category]" :tone="TONE[row.category]" />
            <SourceTag :sumber="row.source" />
          </div>
          <p class="asal">
            Kategori ini masuk lewat {{ SUMBER_LABEL[row.source] }}. Sumbernya selalu ikut
            ditampilkan, jadi bisa ditelusuri ke belakang.
          </p>
        </div>

        <p v-if="galat" class="catatan" role="alert">{{ galat }}</p>

        <div v-if="adaKeyakinan" class="keyakinan">
          <AppMeter
            :value="keyakinan * 100"
            :max="100"
            :warn-at="1"
            label="Keyakinan mesin atas kategori ini"
            :caption="persen(keyakinan * 100, 0)"
          />
          <p v-if="keyakinanRendah" class="tidak-yakin">
            Mesin hanya yakin {{ persen(keyakinan * 100, 0) }}. Keterangan pada baris ini belum
            membedakan pekerjaan yang dikerjakan sendiri dari pekerjaan yang lewat usaha, dan dua
            pembacaan itu berakhir pada skema yang berbeda. Angka dan kategori di halaman ini belum
            bisa dianggap final sebelum Anda menjawab pertanyaannya atau memindahkannya sendiri.
          </p>
          <p v-else class="yakin">
            Keyakinan {{ persen(keyakinan * 100, 0) }}. Kategori ini cocok dengan aturan yang dibaca
            mesin, tapi tetap tebakan — bukan penetapan yang sah.
          </p>
        </div>
        <p v-else class="yakin tanpa-meter">
          Kategori ini bukan dari tebakan mesin, jadi tidak ada tingkat keyakinan yang perlu
          ditampilkan.
        </p>
      </AppCard>

      <AppCard title="Dasar hukum" :subtitle="`Ringkasan bacaan ${PUBLIC_RULESET.nama} Pasal 56`">
        <blockquote class="kutip">
          <p>
            Pasal 56 memisahkan dua dasar pengenaan. Omzet usaha dari orang pribadi yang jumlahnya
            dalam satu tahun pajak tidak melebihi {{ rupiah(batasBebas) }} tidak dikenai PPh final;
            untuk bagian omzet usaha di atas jumlah itu berlaku tarif
            {{ PUBLIC_RULESET.tarifLabel }} sampai plafon {{ rupiah(plafon) }}. Penghasilan dari
            pekerjaan yang dikerjakan sendiri dibaca dari norma penghasil, bukan dari tarif.
          </p>
          <footer>
            Ringkasan bacaan dari {{ PUBLIC_RULESET.nama }} Pasal 56 · berlaku
            {{ tanggalPanjang(stampDate) }}
          </footer>
        </blockquote>
        <p class="kunci">
          Ini ringkasan untuk dibaca, bukan nasihat hukum dan bukan penetapan resmi. Untuk keputusan
          yang berakibat resmi, periksa penjelasan {{ PUBLIC_RULESET.nama }} dan aturan turunannya
          langsung.
        </p>
      </AppCard>

      <AppCard v-if="store.klarifikasi" class="tanya-card">
        <div class="tanya-head">
          <AppPill tone="ask" label="Perlu klarifikasi" icon="helpCircle" attention />
          <p class="tanya-judul">{{ store.klarifikasi.question }}</p>
          <p class="tanya-sub">Pilih satu kategori. Mesin tidak menebak setelah pertanyaan ini.</p>
        </div>
        <div class="jawab">
          <AppButton
            v-for="opsi in store.klarifikasi.options"
            :key="opsi.value"
            variant="outline"
            size="lg"
            @click="jawab(opsi.value)"
          >
            {{ opsi.label }}
          </AppButton>
        </div>
      </AppCard>

      <AppCard v-else-if="klarifikasiSelesai" class="selesai">
        <div class="selesai-isi">
          <span class="selesai-ic"
            ><AppIcon name="checkCircle" :size="18" :stroke-width="1.8"
          /></span>
          <div class="selesai-teks">
            <p class="selesai-judul">Pertanyaan sudah dijawab</p>
            <p class="selesai-sub">
              Baris ini sekarang tercatat sebagai {{ KATEGORI_LABEL[row.category] }}, dan sumbernya
              sudah berganti ke {{ SUMBER_LABEL[row.source] }}.
            </p>
          </div>
        </div>
      </AppCard>

      <AppCard
        title="Override manual"
        subtitle="Kalau mesin salah atau keterangan belum cukup, pindahkan sendiri."
      >
        <div class="override-isi">
          <AppButton variant="outline" icon="ubah" @click="bukaSheet">
            Ubah klasifikasi manual
          </AppButton>
          <AppButton variant="danger" icon="sampah" @click="hapus">Hapus</AppButton>
          <p class="override-note">
            Kategori yang Anda pilih akan menimpa tebakan mesin dan baris ini ditandai Override,
            beserta catatannya. Batas bebas usaha {{ rupiah(batasBebas) }} tidak ikut dipakai kalau
            barisnya berakhir di pekerjaan bebas.
          </p>
        </div>
      </AppCard>

      <AppCard v-if="store.jejak.length || store.jejakPesan" title="Jejak klasifikasi">
        <p v-if="store.jejakPesan">{{ store.jejakPesan }}</p>
        <ul v-else class="dl">
          <li v-for="(ev, i) in store.jejak" :key="i">
            {{ tanggal(ev.timestamp.slice(0, 10)) }} ·
            {{ SUMBER_LABEL[ev.source as Sumber] ?? ev.source }} ·
            <template v-if="ev.old_category">{{ labelKategori(ev.old_category) }} → </template>
            {{ labelKategori(ev.new_category || ev.assigned_category) }}
            <template v-if="ev.note"> · {{ ev.note }}</template>
          </li>
        </ul>
      </AppCard>

      <WorkpaperNote />

      <RouterLink to="/transaksi" class="kembali">
        <AppIcon name="chevronLeft" :size="16" :stroke-width="1.8" />
        Kembali ke daftar transaksi
      </RouterLink>
    </div>

    <AppSheet
      :open="sheetTerbuka"
      title="Ubah klasifikasi manual"
      subtitle="Empat kategori. Pilihan yang disimpan tercatat sebagai override oleh Anda."
      @close="tutupSheet"
    >
      <div class="sheet-fields">
        <AppField
          label="Kategori"
          for-id="kategori-override"
          hint="Pilih satu. Kategori sekarang diganti seluruhnya, bukan ditambahkan."
        >
          <AppSelect id="kategori-override" v-model="kategoriBaru" :options="kategoriOpsi" />
        </AppField>

        <AppField
          label="Catatan klasifikasi"
          for-id="catatan-override"
          optional
          hint="Alasan singkat supaya pilihan ini bisa ditelusuri ulang nanti."
        >
          <AppInput
            id="catatan-override"
            v-model="catatanBaru"
            placeholder="mis. ada dua karyawan tetap di usaha"
            autocomplete="off"
          />
        </AppField>
      </div>

      <template #footer>
        <div class="sheet-aksi">
          <AppButton variant="ghost" @click="tutupSheet">Batal</AppButton>
          <AppButton
            variant="primary"
            icon="check"
            :disabled="kategoriBaru === ''"
            @click="terapkan"
          >
            Terapkan override
          </AppButton>
        </div>
      </template>
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

/* One reading column. The canvas may be wider than the text actually wants. */
.col {
  display: flex;
  flex-direction: column;
  gap: var(--s-6);
  width: 100%;
  max-width: 52rem;
  margin-inline: auto;
}

.back {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  min-height: 2.5rem;
  margin-block: calc(-1 * var(--s-2));
  font: var(--t-label);
  letter-spacing: var(--track-label);
  font-weight: 600;
  color: var(--ink-3);
  transition: color var(--t-fast) var(--ease-out-soft);
}

.back:hover {
  color: var(--ink);
}

.back svg {
  transition: transform var(--t-fast) var(--ease-out-soft);
}

.back:hover svg {
  transform: translateX(-2px);
}

.t1 {
  font: var(--t-title-1);
  letter-spacing: var(--track-title-1);
  margin-top: var(--s-2);
  overflow-wrap: anywhere;
}

.sub {
  font: var(--t-body);
  color: var(--ink-2);
  margin-top: var(--s-1);
}

.dl {
  display: flex;
  flex-direction: column;
}

.dl-row {
  display: grid;
  gap: var(--s-1);
  padding: var(--s-3) 0;
  border-top: 1px solid var(--hairline);
}

.dl-row:first-child {
  border-top: 0;
  padding-top: 0;
}

.dl dt {
  font: var(--t-label-sm);
  letter-spacing: var(--track-label-sm);
  color: var(--ink-3);
}

.dl dd {
  font: var(--t-body);
  color: var(--ink);
  overflow-wrap: anywhere;
}

.dl .teks {
  font-family: var(--font-numeric);
  letter-spacing: -0.01em;
}

.unit {
  color: var(--ink-3);
  margin-right: 0.25rem;
}

@media (min-width: 620px) {
  .dl-row {
    grid-template-columns: minmax(0, 15rem) minmax(0, 1fr);
    gap: var(--s-4);
    align-items: baseline;
  }
}

.utama dd {
  display: flex;
  align-items: baseline;
  gap: 0.25rem;
  font: var(--t-figure-sm);
  font-weight: 600;
}

.putusan {
  border-color: var(--hairline-strong);
}

.putusan-head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}

.putusan-nama {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-3);
}

.nama {
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.i-usaha {
  color: var(--cat-usaha-ink);
}

.i-bebas {
  color: var(--cat-bebas-ink);
}

.i-final {
  color: var(--cat-final-ink);
}

.i-non {
  color: var(--cat-non-ink);
}

.asal {
  font: var(--t-body-sm);
  color: var(--ink-2);
  max-width: 40rem;
}

.catatan {
  display: flex;
  align-items: flex-start;
  gap: var(--s-2);
  margin-top: var(--s-4);
  padding: var(--s-3);
  border-radius: var(--r-md);
  background: var(--surface-sunken);
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}

.catatan svg {
  margin-top: 0.125rem;
  color: var(--ink-3);
  flex: none;
}

.keyakinan {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-5);
  padding-top: var(--s-5);
  border-top: 1px solid var(--hairline);
}

.tidak-yakin {
  padding: var(--s-3) var(--s-4);
  border: 1px solid var(--warn-line);
  border-radius: var(--r-md);
  background: var(--warn-bg);
  color: var(--warn-ink);
  font: var(--t-body-sm);
  line-height: 1.5;
}

.yakin {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}

.tanpa-meter {
  margin-top: var(--s-5);
  padding-top: var(--s-5);
  border-top: 1px solid var(--hairline);
}

.kutip {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-4);
  padding-left: var(--s-5);
  border-left: 2px solid var(--accent-line);
  background: var(--surface-sunken);
  border-radius: 0 var(--r-md) var(--r-md) 0;
}

.kutip p {
  font: var(--t-body);
  color: var(--ink);
  line-height: 1.55;
}

.kutip footer {
  font: var(--t-caption);
  letter-spacing: var(--track-caption);
  color: var(--ink-3);
  text-transform: uppercase;
}

.kunci {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
  margin-top: var(--s-4);
}

.tanya-card {
  border-color: var(--cat-ask-line);
}

.tanya-head {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-3);
}

.tanya-judul {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  font-weight: 600;
  line-height: 1.4;
  text-wrap: balance;
}

.tanya-sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}

.jawab {
  display: grid;
  gap: var(--s-3);
  margin-top: var(--s-5);
}

@media (min-width: 480px) {
  .jawab {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.selesai-isi {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
}

.selesai-ic {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  flex: none;
  border-radius: var(--r-full);
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
}

.selesai-judul {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  font-weight: 600;
}

.selesai-sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
  margin-top: var(--s-1);
}

.override-isi {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-3);
}

.override-note {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}

.sheet-fields {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.sheet-aksi {
  display: flex;
  flex: 1;
  gap: var(--s-3);
}

.sheet-aksi > * {
  flex: 1 1 auto;
}

@media (min-width: 480px) {
  .sheet-aksi {
    justify-content: flex-end;
  }

  .sheet-aksi > * {
    flex: none;
  }
}

.kosong-isi {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  margin-bottom: var(--s-5);
}

.kosong-ic {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  flex: none;
  border-radius: var(--r-full);
  background: var(--surface-sunken);
  color: var(--ink-3);
}

.kosong-judul {
  font: var(--t-title-3);
  letter-spacing: var(--track-title-3);
  font-weight: 600;
}

.kosong-sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
  margin-top: var(--s-1);
}

.kembali {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 0.25rem;
  min-height: 2.5rem;
  font: var(--t-label);
  letter-spacing: var(--track-label);
  font-weight: 600;
  color: var(--accent);
}

.kembali svg {
  transition: transform var(--t-fast) var(--ease-out-soft);
}

.kembali:hover svg {
  transform: translateX(-2px);
}
</style>
