<script setup lang="ts">
/** Capture form for one income transaction: the fields, and what classification will do with them. */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppField from "@/components/ui/AppField.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppInput from "@/components/ui/AppInput.vue";
import AppPill from "@/components/ui/AppPill.vue";
import AppSelect from "@/components/ui/AppSelect.vue";
import SourceTag from "@/components/app/SourceTag.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import {
  KATEGORI_LABEL,
  PUBLIC_RULESET,
  SOURCE_CHANNEL_LABEL,
  SUMBER_LABEL,
  type Kategori,
  type SourceChannel,
  type Sumber,
} from "@/lib/domain";
import { parseRupiah, rupiah } from "@/lib/format";
import { useKuotaStore } from "@/stores/kuota";
import { useProfilStore } from "@/stores/profil";
import { useTransaksiStore } from "@/stores/transaksi";

const store = useTransaksiStore();
const profil = useProfilStore();
const kuota = useKuotaStore();
const router = useRouter();

const tanggalTransaksi = ref(hariIni());
const klien = ref("");
const keterangan = ref("");
const nominal = ref("");
const faktur = ref("");
const dipotong = ref("");
const kanal = ref<SourceChannel>("other");
const sudahCobaSimpan = ref(false);
const galatSimpan = ref("");
const sibuk = ref(false);
const berkas = ref<File | null>(null);
const imageId = ref("");

const kanalOpsi = (Object.keys(SOURCE_CHANNEL_LABEL) as SourceChannel[]).map((k) => ({
  value: k,
  label: SOURCE_CHANNEL_LABEL[k],
}));

const sumberOpsi = Object.keys(SUMBER_LABEL) as Sumber[];

/** How each of the four categories is read, with its figures read from the ruleset. */
const CARA_MEMBACA: Record<Kategori, string> = {
  usaha: `Omzet usaha. Batas bebas pajak ${rupiah(PUBLIC_RULESET.bebasUsaha)} dalam satu tahun, di atasnya tarif ${PUBLIC_RULESET.tarifLabel} berlaku sampai plafon ${rupiah(PUBLIC_RULESET.plafonUsaha)}.`,
  pekerjaan_bebas:
    "Penghasilan pekerjaan yang dikerjakan sendiri atas nama pribadi. Dihitung dengan norma, bukan dengan tarif, dan tidak memakai batas bebas usaha.",
  already_final:
    "Pajak sudah dipotong lawan transaksi sebelum uang diterima. Yang dicatat di baris ini adalah bukti potongnya.",
  non_object:
    "Bukan penghasilan. Modal, pengembalian deposit, atau pemindahan dana antar rekening sendiri masuk ke sini dan tidak menambah omzet.",
};

const TONE: Record<Kategori, "usaha" | "bebas" | "final" | "non"> = {
  usaha: "usaha",
  pekerjaan_bebas: "bebas",
  already_final: "final",
  non_object: "non",
};

const panduan = (Object.keys(KATEGORI_LABEL) as Kategori[]).map((k) => ({
  key: k,
  label: KATEGORI_LABEL[k],
  tone: TONE[k],
  teks: CARA_MEMBACA[k],
}));

const nominalAngka = computed(() => parseRupiah(nominal.value));
const dipotongAngka = computed(() =>
  dipotong.value.trim() === "" ? 0 : parseRupiah(dipotong.value),
);

/** An empty untouched field stays quiet; anything typed is checked as it is typed. */
const galatTanggal = computed(() =>
  tanggalTransaksi.value || !sudahCobaSimpan.value ? "" : "Tanggal transaksi wajib diisi.",
);

const galatKlien = computed(() =>
  klien.value.trim() || !sudahCobaSimpan.value ? "" : "Nama klien wajib diisi.",
);

const galatNominal = computed(() => {
  if (nominal.value === "" && !sudahCobaSimpan.value) return "";
  if (nominal.value === "") return "Nominal bruto wajib diisi.";
  if (nominalAngka.value === null) return "Nominal harus angka bulat saja, misalnya 12500000.";
  if (nominalAngka.value <= 0) return "Nominal harus lebih besar dari nol.";
  return "";
});

const galatPajak = computed(() =>
  dipotongAngka.value === null ? "Pajak dipotong harus angka bulat saja, misalnya 3750000." : "",
);

const galatFaktur = computed(() => "");

function hariIni(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta" }).format(new Date());
}

onMounted(async () => {
  await profil.muat();
  await kuota.muat();
  if (profil.belumAda) {
    galatSimpan.value =
      "Status NIB untuk tahun pajak berjalan harus diisi sebelum mencatat transaksi pertama.";
  }
});

function pilihBukti() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/jpeg,image/png";
  input.onchange = () => {
    berkas.value = input.files?.[0] ?? null;
    void unggah();
  };
  input.click();
}

async function unggah() {
  if (!berkas.value) return;
  galatSimpan.value = "";
  try {
    const hasil = await store.unggahStruk(berkas.value);
    imageId.value = hasil.image_id;
    const calon = hasil.candidate_fields;
    if (calon.amount_idr) nominal.value = String(calon.amount_idr);
    if (calon.tx_date) tanggalTransaksi.value = calon.tx_date;
    if (calon.client_name) klien.value = calon.client_name;
    if (calon.invoice_no) faktur.value = calon.invoice_no;
  } catch (error) {
    imageId.value = "";
    galatSimpan.value = error instanceof ApiFailure ? error.message : "Unggah gagal.";
    if (error instanceof ApiFailure && error.code === "PAID_SUBSCRIPTION_REQUIRED") {
      await router.push("/kuota");
    }
  }
}

function batal() {
  router.back();
}

async function simpan() {
  sudahCobaSimpan.value = true;
  galatSimpan.value = "";
  const nilai = nominalAngka.value;
  const pajak = dipotongAngka.value;
  if (!tanggalTransaksi.value || klien.value.trim() === "") return;
  if (nilai === null || nilai <= 0 || pajak === null) return;
  if (profil.belumAda) return;
  sibuk.value = true;
  try {
    const fields = {
      amount_idr: nilai,
      tx_date: tanggalTransaksi.value,
      client_name: klien.value.trim(),
      description: keterangan.value.trim(),
      invoice_no: faktur.value.trim() || undefined,
      withheld_tax_amount_idr: pajak,
      source_channel: kanal.value,
    };
    const row = imageId.value
      ? await store.konfirmasiStruk(imageId.value, {
          confirmed_amount_idr: nilai,
          confirmed_tx_date: tanggalTransaksi.value,
          confirmed_client_name: klien.value.trim(),
          confirmed_description: keterangan.value.trim(),
          confirmed_invoice_no: faktur.value.trim(),
          withheld_tax_amount_idr: pajak,
          source_channel: kanal.value,
        })
      : await store.buat(fields);
    await router.push(`/transaksi/${row.id}`);
  } catch (error) {
    galatSimpan.value = error instanceof ApiFailure ? error.message : "Simpan gagal.";
  } finally {
    sibuk.value = false;
  }
}
</script>

<template>
  <div class="page">
    <header class="lede">
      <div>
        <h2 class="t1">Catat transaksi pendapatan</h2>
        <p class="sub">
          Isi apa yang benar-benar terjadi di lapangan. Kategori, tarif, dan batas bebas tidak
          dipilih di sini: klasifikasi berjalan otomatis setelah transaksi disimpan.
        </p>
      </div>
    </header>

    <div class="grid">
      <AppCard
        as="form"
        novalidate
        title="Detail transaksi"
        subtitle="Kolom bertanda bintang wajib diisi."
        @submit.prevent="simpan"
      >
        <div class="fields">
          <AppField label="Tanggal transaksi" class="wajib" for-id="tanggal" :error="galatTanggal">
            <AppInput
              id="tanggal"
              v-model="tanggalTransaksi"
              type="date"
              required
              :invalid="!!galatTanggal"
            />
          </AppField>

          <AppField
            label="Nama klien atau lawan transaksi"
            class="wajib"
            for-id="klien"
            :error="galatKlien"
          >
            <AppInput
              id="klien"
              v-model="klien"
              required
              :invalid="!!galatKlien"
              placeholder="mis. PT Maju Bersama"
              autocomplete="off"
            />
          </AppField>

          <AppField
            label="Deskripsi layanan atau barang"
            for-id="deskripsi"
            hint="Tulis yang dibaca klasifikasi: barang atau jasa apa, berapa banyak, dan untuk siapa."
          >
            <textarea
              id="deskripsi"
              v-model="keterangan"
              class="ta"
              rows="3"
              placeholder="mis. Penjualan 100 pcs merchandise custom"
            />
          </AppField>

          <div class="pair">
            <AppField
              label="Nominal bruto (omzet tercatat)"
              class="wajib"
              for-id="nominal"
              hint="Bruto sebelum dipotong lawan transaksi."
              :error="galatNominal"
            >
              <AppInput
                id="nominal"
                v-model="nominal"
                mono
                inputmode="numeric"
                required
                :invalid="!!galatNominal"
                placeholder="12500000"
              >
                <template #pre>Rp</template>
              </AppInput>
            </AppField>

            <AppField
              label="Nomor faktur atau bukti potong"
              for-id="faktur"
              optional
              hint="Dipakai untuk menemukan nomor yang sama tercatat dua kali."
              :error="galatFaktur"
            >
              <AppInput
                id="faktur"
                v-model="faktur"
                :invalid="!!galatFaktur"
                placeholder="mis. INV-2026-018"
                autocomplete="off"
              />
            </AppField>
          </div>

          <AppField
            label="Pajak yang sudah dipotong lawan transaksi"
            for-id="dipotong"
            optional
            hint="Isi hanya bila potongannya benar-benar sudah diterima."
            :error="galatPajak"
          >
            <AppInput
              id="dipotong"
              v-model="dipotong"
              mono
              inputmode="numeric"
              placeholder="0"
              :invalid="!!galatPajak"
            >
              <template #pre>Rp</template>
            </AppInput>
          </AppField>

          <AppField label="Saluran penjualan" for-id="kanal">
            <AppSelect id="kanal" v-model="kanal" :options="kanalOpsi" />
          </AppField>

          <AppField label="Bukti pendukung">
            <div
              class="drop"
              role="button"
              tabindex="0"
              aria-describedby="catatan-bukti"
              @click="pilihBukti"
              @keydown.enter.prevent="pilihBukti"
              @keydown.space.prevent="pilihBukti"
            >
              <span class="drop-ic"><AppIcon name="unggah" :size="22" /></span>
              <span class="drop-title">Unggah bukti transaksi</span>
              <span class="drop-sub">Foto struk, JPEG atau PNG, maksimal 8 MB</span>
              <span id="catatan-bukti" class="drop-note">
                {{
                  kuota.berbayar
                    ? "Kolom di atas terisi dari foto, lalu perlu Anda periksa sebelum disimpan."
                    : "Unggah struk hanya untuk akun berbayar aktif. Berkas tidak menjadi transaksi."
                }}
              </span>
            </div>
          </AppField>

          <p v-if="galatSimpan" class="kunci" role="alert">{{ galatSimpan }}</p>
          <div class="aksi u-hairline-top">
            <AppButton variant="ghost" size="lg" @click="batal">Batal</AppButton>
            <AppButton
              type="submit"
              variant="primary"
              size="lg"
              icon="checkCircle"
              :disabled="sibuk"
            >
              Simpan dan klasifikasikan
            </AppButton>
          </div>
        </div>
      </AppCard>

      <aside class="aside">
        <AppCard
          title="Empat kategori"
          subtitle="Klasifikasi memilih satu, tidak ada kategori kelima."
        >
          <ol class="panduan">
            <li v-for="p in panduan" :key="p.key">
              <AppPill size="sm" :label="p.label" :tone="p.tone" />
              <p>{{ p.teks }}</p>
            </li>
          </ol>
          <p class="kunci">
            Batas bebas {{ rupiah(PUBLIC_RULESET.bebasUsaha) }} per {{ PUBLIC_RULESET.nama }} hanya
            berlaku pada omzet usaha. Pekerjaan bebas tidak memakainya, jadi sisa batas bukan sisa
            seluruh penghasilan.
          </p>
        </AppCard>

        <AppCard
          title="Asal kategori"
          subtitle="Sumbernya selalu ditampilkan berdampingan dengan kategorinya."
        >
          <div class="tag-row">
            <SourceTag v-for="s in sumberOpsi" :key="s" :sumber="s" />
          </div>
          <p class="kunci">
            Kalau keterangan belum cukup untuk dipastikan, barisnya menunggu jawaban Anda dan
            ditandai perlu klarifikasi.
          </p>
        </AppCard>

        <WorkpaperNote />
      </aside>
    </div>
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

.grid {
  display: grid;
  gap: var(--s-6);
}

@media (min-width: 1024px) {
  .grid {
    grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
    gap: var(--s-8);
    align-items: start;
  }
}

.fields {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.pair {
  display: grid;
  gap: var(--s-5);
}

@media (min-width: 640px) {
  .pair {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.wajib :deep(label)::after {
  content: " *";
  color: var(--cat-ask-ink);
  font-weight: 700;
}

/* Same shell as AppInput, so a textarea does not read as a different control. */
.ta {
  width: 100%;
  min-height: 2.75rem;
  padding: 0.6875rem var(--s-3);
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--r-md);
  font: var(--t-body);
  letter-spacing: var(--track-body);
  resize: vertical;
  transition:
    border-color var(--t-fast) var(--ease-out-soft),
    box-shadow var(--t-fast) var(--ease-out-soft);
}

.ta::placeholder {
  color: var(--ink-3);
}

.ta:focus {
  border-color: var(--focus);
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--focus) 20%, transparent);
}

/* A phone must not zoom the page when the field is focused. */
@media (max-width: 767px) {
  .ta {
    font-size: 1rem;
    line-height: 1.45;
  }
}

.drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-1);
  padding: var(--s-6) var(--s-5);
  text-align: center;
  background: var(--surface-sunken);
  border: 1px dashed var(--hairline-strong);
  border-radius: var(--r-lg);
  color: var(--ink-3);
  cursor: pointer;
  transition:
    background-color var(--t-fast) var(--ease-out-soft),
    border-color var(--t-fast) var(--ease-out-soft);
}

.drop:hover {
  background: var(--surface-raised);
  border-color: var(--accent-line);
}

.drop-ic {
  color: var(--ink-3);
}

.drop-title {
  font: var(--t-label);
  font-weight: 600;
  letter-spacing: var(--track-label);
  color: var(--ink);
}

.drop-sub {
  font: var(--t-body-sm);
  color: var(--ink-2);
}

.drop-note {
  font: var(--t-caption);
  letter-spacing: var(--track-caption);
  color: var(--ink-3);
  max-width: 26rem;
  margin-top: var(--s-2);
}

.aksi {
  position: sticky;
  bottom: var(--s-3);
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3);
  margin: 0 calc(-1 * var(--s-5)) calc(-1 * var(--s-5));
  padding: var(--s-4) var(--s-5) var(--s-5);
  background: var(--surface);
  border-radius: 0 0 var(--r-lg) var(--r-lg);
}

/* On a phone the floating tab bar owns the bottom edge of the screen. */
@media (max-width: 767px) {
  .aksi {
    bottom: calc(var(--tabbar-h) + var(--safe-b) + var(--s-3));
  }
}

.aksi > * {
  flex: 1 1 auto;
}

@media (min-width: 640px) {
  .aksi {
    justify-content: flex-end;
  }

  .aksi > * {
    flex: none;
  }
}

.aside {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.panduan {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}

.panduan li {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-2);
}

.panduan p {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}

.kunci {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
  margin-top: var(--s-4);
  padding-top: var(--s-4);
  border-top: 1px solid var(--hairline);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
</style>
