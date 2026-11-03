<script setup lang="ts">
/**
 * Review-and-resolve screen for one transaction's classification: the evidence
 * it was read from, the verdict, and the manual override that can move it.
 *
 * The verdict branches on `classification.requires_clarification`, never on
 * `confidence`. A provisional row has no determination to report, only a
 * placeholder and a question waiting for an answer, so the question is the
 * primary card and the meter is not rendered at all.
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
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
import { ApiFailure, isAbortError } from "@/lib/api";
import { dasarHukumUntuk } from "@/lib/dasarHukum";
import { CAPABILITIES } from "@/lib/capabilities";
import {
  KATEGORI_LABEL,
  PUBLIC_RULESET,
  SOURCE_CHANNEL_LABEL,
  SUMBER_LABEL,
  type Kategori,
  type SourceChannel,
  type Sumber,
} from "@/lib/domain";
import {
  parseRupiah,
  persen,
  rupiah,
  rupiahPlain,
  tanggal,
  tanggalPanjang,
  tanggalWaktuJakarta,
} from "@/lib/format";
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
const galatOverride = ref("");
const galatKlarifikasi = ref("");
const stampId = computed(() => pajak.dashboard?.metadata.ruleset_id || PUBLIC_RULESET.id);
const stampDate = computed(
  () => pajak.dashboard?.metadata.effective_date || PUBLIC_RULESET.berlaku,
);
const batasBebas = computed(
  () => pajak.dashboard?.thresholds.pita_500_juta.limit_idr ?? PUBLIC_RULESET.bebasUsaha,
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
const sedangTerapkan = ref(false);
/** Set only by this screen, so the answered question can collapse instead of vanish. */
const klarifikasiSelesai = ref(false);
const sedangDijawab = ref(false);

const sheetHapusTerbuka = ref(false);
const sedangHapus = ref(false);
const galatHapus = ref("");

const kanalOpsi = (Object.keys(SOURCE_CHANNEL_LABEL) as SourceChannel[]).map((k) => ({
  value: k,
  label: SOURCE_CHANNEL_LABEL[k],
}));

const sheetUbahTerbuka = ref(false);
const sedangSimpanUbah = ref(false);
const galatUbah = ref("");
/** Per-field errors from API §2.5 `field_errors` / `details` (422). */
const galatUbahField = reactive<Record<string, string>>({});
const draftEdit = reactive({
  tx_date: "",
  client_name: "",
  description: "",
  amount_idr: "",
  invoice_no: "",
  withheld_tax_amount_idr: "0",
  source_channel: "other" as SourceChannel,
});

/** Guard state writes after this page unmounts (save/fetch race). */
const masihTerpasang = ref(true);
let simpanAbort: AbortController | null = null;
onBeforeUnmount(() => {
  masihTerpasang.value = false;
  simpanAbort?.abort();
  simpanAbort = null;
});

function bersihkanGalatUbah() {
  galatUbah.value = "";
  for (const key of Object.keys(galatUbahField)) delete galatUbahField[key];
}

function isiDraftDari(tx: {
  tx_date: string;
  client_name: string;
  description: string;
  amount_idr: number;
  invoice_no?: string | null;
  withheld_tax_amount_idr?: number | null;
  source_channel?: string | null;
}) {
  draftEdit.tx_date = tx.tx_date;
  draftEdit.client_name = tx.client_name;
  draftEdit.description = tx.description;
  draftEdit.amount_idr = String(tx.amount_idr);
  draftEdit.invoice_no = tx.invoice_no || "";
  draftEdit.withheld_tax_amount_idr = String(tx.withheld_tax_amount_idr || 0);
  draftEdit.source_channel = (tx.source_channel as SourceChannel) || "other";
}

function terapkanFieldErrors(errors: Record<string, string>) {
  for (const key of Object.keys(galatUbahField)) delete galatUbahField[key];
  for (const [key, msg] of Object.entries(errors)) {
    // Map nested FastAPI locs like "amount_idr" or "body.amount_idr"
    const field = key.includes(".") ? (key.split(".").pop() ?? key) : key;
    galatUbahField[field] = msg;
  }
}

/** Older payloads carry no classification at all; that reads as classified, not as 0%. */
const klasifikasi = computed(() => row.value?.classification);
const perluJawab = computed(() => klasifikasi.value?.requires_clarification === true);

/** SRS v2.7 § Definisi dan Istilah — see `@/lib/dasarHukum`. */
const dasarHukum = computed(() => dasarHukumUntuk(row.value?.category, perluJawab.value === true));

/** A human set this category, so there is no rule-match score to show. */
const dariManusia = computed(() => row.value?.source !== "rule");

/**
 * The classifier's match strength, as a percentage. Null when the payload
 * carried no confidence, and null when a person set the category: a confident
 * answer is not a rule that matched, and labelling it as one is a false claim
 * about how the figure was reached.
 */
const keyakinanPersen = computed(() => {
  if (dariManusia.value) return null;
  const nilai = klasifikasi.value?.confidence;
  return typeof nilai === "number" ? nilai * 100 : null;
});

function bukaSheet() {
  if (!row.value) return;
  kategoriBaru.value = row.value.category;
  catatanBaru.value = "";
  galatOverride.value = "";
  sheetTerbuka.value = true;
}

function tutupSheet() {
  sheetTerbuka.value = false;
  galatOverride.value = "";
}

function bukaSheetUbah() {
  if (!row.value) return;
  isiDraftDari(row.value);
  bersihkanGalatUbah();
  sheetUbahTerbuka.value = true;
}

function tutupSheetUbah() {
  sheetUbahTerbuka.value = false;
  bersihkanGalatUbah();
}

async function simpanUbah() {
  if (!row.value || sedangSimpanUbah.value) return;
  const nilai = parseRupiah(draftEdit.amount_idr);
  if (nilai === null || nilai <= 0) {
    galatUbah.value = "Nominal bruto harus angka positif.";
    return;
  }
  if (!draftEdit.client_name.trim() || !draftEdit.tx_date) {
    galatUbah.value = "Nama klien dan tanggal transaksi wajib diisi.";
    return;
  }
  const pajakPotong =
    draftEdit.withheld_tax_amount_idr.trim() === ""
      ? 0
      : (parseRupiah(draftEdit.withheld_tax_amount_idr) ?? 0);
  sedangSimpanUbah.value = true;
  bersihkanGalatUbah();
  simpanAbort?.abort();
  simpanAbort = new AbortController();
  const signal = simpanAbort.signal;
  const txId = row.value.id;
  const version = row.value.version;
  try {
    const updated = await store.ubah(
      txId,
      {
        amount_idr: nilai,
        tx_date: draftEdit.tx_date,
        client_name: draftEdit.client_name.trim(),
        description: draftEdit.description.trim(),
        invoice_no: draftEdit.invoice_no.trim() || undefined,
        withheld_tax_amount_idr: pajakPotong,
        source_channel: draftEdit.source_channel,
        version,
      },
      { signal },
    );
    if (!masihTerpasang.value) return;
    sheetUbahTerbuka.value = false;
    if (updated.classification?.requires_clarification) {
      await muatPertanyaan(updated.id);
    }
    if (!masihTerpasang.value) return;
    if (CAPABILITIES.auditTrail) await store.muatJejak(updated.id);
    if (!masihTerpasang.value) return;
    await pajak.muat(true);
  } catch (error) {
    if (!masihTerpasang.value || isAbortError(error)) return;
    // API Spec v1.3.1 §2.5 / §5.12: VERSION_CONFLICT → re-GET latest version, refresh form+store.
    if (error instanceof ApiFailure && error.code === "VERSION_CONFLICT") {
      try {
        const fresh = await store.muatSatu(txId);
        if (!masihTerpasang.value) return;
        isiDraftDari(fresh);
        galatUbah.value =
          error.message ||
          "Versi data sudah berubah. Form diisi ulang dari data terbaru; periksa lalu simpan lagi.";
      } catch (reloadError) {
        if (!masihTerpasang.value || isAbortError(reloadError)) return;
        galatUbah.value =
          reloadError instanceof ApiFailure
            ? reloadError.message
            : error.message || "Versi bentrok; gagal memuat ulang transaksi.";
      }
      return;
    }
    if (error instanceof ApiFailure && Object.keys(error.fieldErrors).length > 0) {
      terapkanFieldErrors(error.fieldErrors);
      galatUbah.value = error.message || "Periksa isian yang ditandai.";
      return;
    }
    galatUbah.value =
      error instanceof ApiFailure ? error.message : "Gagal menyimpan perubahan transaksi.";
  } finally {
    if (masihTerpasang.value) sedangSimpanUbah.value = false;
  }
}

async function terapkan() {
  if (!row.value || kategoriBaru.value === "" || sedangTerapkan.value) return;
  sedangTerapkan.value = true;
  galatOverride.value = "";
  try {
    await store.override(
      row.value.id,
      kategoriBaru.value as Kategori,
      catatanBaru.value.trim() || undefined,
    );
    sheetTerbuka.value = false;
    galatOverride.value = "";
    if (CAPABILITIES.auditTrail) await store.muatJejak(row.value.id);
    await pajak.muat(true);
  } catch (error) {
    galatOverride.value = error instanceof ApiFailure ? error.message : "Override gagal.";
  } finally {
    sedangTerapkan.value = false;
  }
}

async function jawab(category: Kategori) {
  if (!row.value || sedangDijawab.value) return;
  sedangDijawab.value = true;
  galatKlarifikasi.value = "";
  try {
    await store.jawab(row.value.id, category);
    klarifikasiSelesai.value = true;
    if (CAPABILITIES.auditTrail) await store.muatJejak(row.value.id);
    await pajak.muat(true);
  } catch (error) {
    galatKlarifikasi.value = error instanceof ApiFailure ? error.message : "Klarifikasi gagal.";
  } finally {
    sedangDijawab.value = false;
  }
}

/**
 * A 404 means there is no question, which is not a failure: the store clears
 * itself and the card renders nothing. Anything else is reported on the card.
 */
async function muatPertanyaan(transactionId: string) {
  galatKlarifikasi.value = "";
  try {
    await store.muatKlarifikasi(transactionId);
  } catch (error) {
    galatKlarifikasi.value =
      error instanceof ApiFailure ? error.message : "Pertanyaan belum bisa dimuat.";
  }
}

function konfirmasiHapus() {
  galatHapus.value = "";
  sheetHapusTerbuka.value = true;
}

function tutupSheetHapus() {
  sheetHapusTerbuka.value = false;
  galatHapus.value = "";
}

async function eksekusiHapus() {
  if (!row.value || sedangHapus.value) return;
  sedangHapus.value = true;
  galatHapus.value = "";
  try {
    await store.hapus(row.value.id);
    sheetHapusTerbuka.value = false;
    await router.push("/transaksi");
  } catch (error) {
    galatHapus.value = error instanceof ApiFailure ? error.message : "Hapus transaksi gagal.";
  } finally {
    sedangHapus.value = false;
  }
}

onMounted(async () => {
  await pajak.muat();
  const found = await store.buka(id.value);
  if (!found) return;
  if (found.classification?.requires_clarification) await muatPertanyaan(found.id);
  // The trail reads /transactions/{id}/audit-trail, so it is only fetched while
  // the section that renders it exists.
  if (CAPABILITIES.auditTrail) await store.muatJejak(found.id);
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
              Transaksi ini tidak ditemukan atau sudah dihapus dari akun Anda.
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
        <template #actions>
          <AppButton variant="ghost" size="sm" icon="ubah" @click="bukaSheetUbah">
            Ubah detail
          </AppButton>
        </template>
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
            <span class="nama" :class="perluJawab ? 'i-belum' : `i-${TONE[row.category]}`">
              {{ perluJawab ? "Belum terklasifikasi" : KATEGORI_LABEL[row.category] }}
            </span>
            <AppPill
              v-if="perluJawab"
              tone="ask"
              label="Perlu klarifikasi"
              icon="helpCircle"
              attention
            />
            <SourceTag v-if="!perluJawab" :sumber="row.source" />
          </div>
          <p v-if="perluJawab" class="asal">
            Tidak ada aturan yang cocok pada keterangan baris ini, jadi
            {{ KATEGORI_LABEL[row.category] }} hanya kategori sementara. Angka
            <span class="figure">{{ rupiah(row.amount_idr) }}</span> masih menunggu jawaban Anda;
            begitu kategorinya ditetapkan, mesin menghitung ulang.
          </p>
          <p v-else class="asal">
            Kategori ini masuk lewat {{ SUMBER_LABEL[row.source] }}. Sumbernya selalu ikut
            ditampilkan, jadi bisa ditelusuri ke belakang.
          </p>
        </div>

        <p v-if="galat" class="catatan" role="alert">{{ galat }}</p>

        <div v-if="perluJawab" class="menunggu">
          <p class="menunggu-judul">Angka ini belum final</p>
          <p class="yakin">
            Omzet dan pajak baris ini dihitung sebagai {{ KATEGORI_LABEL[row.category] }} sementara.
            Selama pertanyaan di bawah belum dijawab, perlakuan pajaknya bisa berubah karena
            pekerjaan yang dikerjakan sendiri dan pekerjaan yang lewat usaha berakhir pada skema
            yang berbeda.
          </p>
        </div>
        <div v-else-if="keyakinanPersen !== null" class="keyakinan">
          <AppMeter
            :value="keyakinanPersen"
            :max="100"
            :warn-at="1"
            label="Kecocokan dengan aturan"
            :caption="persen(keyakinanPersen, 0)"
          />
          <p class="yakin">
            Kategori ini cocok dengan aturan kata kunci yang membaca keterangan baris. Angka di
            meter adalah kadar kecocokan aturan itu, bukan perkiraan model.
          </p>
        </div>
        <p v-else-if="dariManusia" class="yakin tanpa-meter">
          Kategori ini Anda tetapkan sendiri
          {{
            row.source === "user_clarification"
              ? "lewat jawaban klarifikasi"
              : "lewat override manual"
          }}, bukan hasil pencocokan aturan. Karena itu tidak ada angka kecocokan yang ditampilkan
          di sini; yang tercatat adalah pilihan Anda beserta waktunya.
        </p>
        <p v-else class="yakin tanpa-meter">
          Kategori ini tidak membawa tingkat kecocokan dari mesin, jadi tidak ada angka yang perlu
          ditampilkan.
        </p>
      </AppCard>

      <AppCard v-if="store.klarifikasi || (perluJawab && galatKlarifikasi)" class="tanya-card">
        <div class="tanya-head">
          <AppPill tone="ask" label="Belum terklasifikasi" icon="helpCircle" attention />
          <p v-if="store.klarifikasi" class="tanya-judul">{{ store.klarifikasi.question }}</p>
          <p v-else class="tanya-judul">Pertanyaannya belum termuat.</p>
          <p v-if="store.klarifikasi" class="tanya-sub">
            Pilih satu kategori. Sesudah Anda memilih, mesin berhenti menebak dan memakai pilihan
            itu.
          </p>
        </div>
        <p v-if="galatKlarifikasi" class="tanya-galat" role="alert">{{ galatKlarifikasi }}</p>
        <div v-if="store.klarifikasi" class="jawab">
          <AppButton
            v-for="opsi in store.klarifikasi.options"
            :key="opsi.value"
            variant="outline"
            size="lg"
            :disabled="sedangDijawab"
            @click="jawab(opsi.value)"
          >
            {{ opsi.label }}
          </AppButton>
        </div>
      </AppCard>

      <AppCard title="Dasar hukum" :subtitle="dasarHukum.judul">
        <blockquote class="kutip">
          <p>{{ dasarHukum.teks }}</p>
          <footer>{{ dasarHukum.rujukan }}</footer>
        </blockquote>
        <p class="kunci">
          Ini ringkasan untuk dibaca, bukan nasihat hukum dan bukan penetapan resmi. Untuk keputusan
          yang berakibat resmi, periksa penjelasan {{ PUBLIC_RULESET.nama }} dan aturan turunannya
          langsung.
        </p>
      </AppCard>

      <AppCard v-if="klarifikasiSelesai && !store.klarifikasi" class="selesai">
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
        v-if="CAPABILITIES.manualOverride || CAPABILITIES.deleteTransaction"
        title="Override manual"
        subtitle="Kalau mesin salah atau keterangan belum cukup, pindahkan sendiri."
      >
        <div class="override-isi">
          <div class="aksi-grup">
            <AppButton
              v-if="CAPABILITIES.manualOverride"
              variant="outline"
              icon="ubah"
              @click="bukaSheet"
            >
              Ubah klasifikasi manual
            </AppButton>
            <AppButton
              v-if="CAPABILITIES.deleteTransaction"
              variant="danger"
              icon="sampah"
              @click="konfirmasiHapus"
            >
              Hapus transaksi
            </AppButton>
          </div>
          <p class="override-note">
            Kategori yang Anda pilih akan menimpa tebakan mesin dan baris ini ditandai Override,
            beserta catatannya. Batas bebas usaha {{ rupiah(batasBebas) }} tidak ikut dipakai kalau
            barisnya berakhir di pekerjaan bebas.
          </p>
        </div>
      </AppCard>

      <AppCard
        v-if="CAPABILITIES.auditTrail && (store.jejak.length || store.jejakPesan)"
        title="Jejak klasifikasi"
      >
        <p v-if="store.jejakPesan">{{ store.jejakPesan }}</p>
        <ul v-else class="dl">
          <li v-for="(ev, i) in store.jejak" :key="i">
            {{ tanggalWaktuJakarta(ev.timestamp) }} ·
            {{ SUMBER_LABEL[ev.source as Sumber] ?? ev.source }} ·
            <template
              v-if="
                ev.old_category && ev.old_category !== (ev.new_category || ev.assigned_category)
              "
            >
              {{ labelKategori(ev.old_category) }} →
            </template>
            {{ labelKategori(ev.new_category || ev.assigned_category) }}
            <template
              v-if="
                ev.old_category && ev.old_category === (ev.new_category || ev.assigned_category)
              "
            >
              (dicek ulang)
            </template>
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

    <!-- Edit Transaction Sheet -->
    <AppSheet
      :open="sheetUbahTerbuka"
      title="Ubah detail transaksi"
      subtitle="Perubahan nilai atau tanggal akan memicu evaluasi klasifikasi dan cuplikan bulan terkait."
      :error="galatUbah"
      @close="tutupSheetUbah"
    >
      <div class="sheet-fields">
        <AppField
          label="Tanggal transaksi"
          for-id="edit-tgl"
          required
          :error="galatUbahField.tx_date"
        >
          <AppInput id="edit-tgl" v-model="draftEdit.tx_date" type="date" required />
        </AppField>
        <AppField
          label="Nama klien atau lawan transaksi"
          for-id="edit-klien"
          required
          :error="galatUbahField.client_name"
        >
          <AppInput id="edit-klien" v-model="draftEdit.client_name" required />
        </AppField>
        <AppField
          label="Deskripsi layanan atau barang"
          for-id="edit-deskripsi"
          :error="galatUbahField.description"
        >
          <AppInput id="edit-deskripsi" v-model="draftEdit.description" />
        </AppField>
        <AppField
          label="Nominal bruto"
          for-id="edit-nominal"
          required
          :error="galatUbahField.amount_idr"
        >
          <AppInput
            id="edit-nominal"
            v-model="draftEdit.amount_idr"
            mono
            inputmode="numeric"
            required
          />
        </AppField>
        <AppField
          label="Nomor faktur / bukti potong"
          for-id="edit-faktur"
          optional
          :error="galatUbahField.invoice_no"
        >
          <AppInput id="edit-faktur" v-model="draftEdit.invoice_no" />
        </AppField>
        <AppField
          label="Pajak yang sudah dipotong"
          for-id="edit-pajak"
          optional
          :error="galatUbahField.withheld_tax_amount_idr"
        >
          <AppInput
            id="edit-pajak"
            v-model="draftEdit.withheld_tax_amount_idr"
            mono
            inputmode="numeric"
          />
        </AppField>
        <AppField
          label="Saluran penjualan"
          for-id="edit-kanal"
          :error="galatUbahField.source_channel"
        >
          <AppSelect id="edit-kanal" v-model="draftEdit.source_channel" :options="kanalOpsi" />
        </AppField>
      </div>

      <template #footer>
        <div class="sheet-aksi">
          <AppButton variant="ghost" @click="tutupSheetUbah">Batal</AppButton>
          <AppButton
            variant="primary"
            icon="check"
            :disabled="sedangSimpanUbah"
            @click="simpanUbah"
          >
            {{ sedangSimpanUbah ? "Menyimpan…" : "Simpan perubahan" }}
          </AppButton>
        </div>
      </template>
    </AppSheet>

    <!-- Delete Confirmation Sheet -->
    <AppSheet
      :open="sheetHapusTerbuka"
      title="Hapus transaksi ini?"
      :subtitle="`Transaksi ${row?.client_name} sebesar ${row ? rupiah(row.amount_idr) : '—'} akan dihapus permanen.`"
      :error="galatHapus"
      @close="tutupSheetHapus"
    >
      <p class="sheet-teks">
        Cuplikan bulan untuk tanggal transaksi ini akan dihitung ulang secara otomatis. Tindakan ini
        tidak dapat dibatalkan.
      </p>
      <template #footer>
        <div class="sheet-aksi">
          <AppButton variant="ghost" @click="tutupSheetHapus">Batal</AppButton>
          <AppButton variant="danger" icon="sampah" :disabled="sedangHapus" @click="eksekusiHapus">
            {{ sedangHapus ? "Menghapus…" : "Hapus permanen" }}
          </AppButton>
        </div>
      </template>
    </AppSheet>

    <!-- Manual Override Sheet -->
    <AppSheet
      v-if="CAPABILITIES.manualOverride"
      :open="sheetTerbuka"
      title="Ubah klasifikasi manual"
      subtitle="Empat kategori. Pilihan yang disimpan tercatat sebagai override oleh Anda."
      :error="galatOverride"
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
            :disabled="kategoriBaru === '' || sedangTerapkan"
            @click="terapkan"
          >
            {{ sedangTerapkan ? "Menerapkan…" : "Terapkan override" }}
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

/* A provisional category is a placeholder, so it never wears a settled
   category's ink. */
.i-belum {
  color: var(--cat-ask-ink);
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

.menunggu {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-5);
  padding-top: var(--s-5);
  border-top: 1px solid var(--hairline);
}

.menunggu-judul {
  font: var(--t-label);
  letter-spacing: var(--track-label);
  font-weight: 600;
  color: var(--cat-ask-ink);
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

.tanya-galat {
  margin-top: var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--cat-ask-line);
  border-radius: var(--r-md);
  background: var(--cat-ask-bg);
  color: var(--cat-ask-ink);
  font: var(--t-body-sm);
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
  width: 100%;
}

.aksi-grup {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3);
  width: 100%;
}

.sheet-teks {
  font: var(--t-body);
  color: var(--ink);
  line-height: 1.5;
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
