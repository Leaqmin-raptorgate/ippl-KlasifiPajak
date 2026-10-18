<script setup lang="ts">
/** Year profile, devices, and account deletion. Entity type is orang pribadi only. */
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";
import AppCard from "@/components/ui/AppCard.vue";
import AppField from "@/components/ui/AppField.vue";
import AppIcon from "@/components/ui/AppIcon.vue";
import AppInput from "@/components/ui/AppInput.vue";
import AppPill from "@/components/ui/AppPill.vue";
import AppSegmented from "@/components/ui/AppSegmented.vue";
import AppSelect from "@/components/ui/AppSelect.vue";
import AppSheet from "@/components/ui/AppSheet.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import { HAPUS_AKUN } from "@/lib/domain";
import { parseRupiah } from "@/lib/format";
import { useKuotaStore } from "@/stores/kuota";
import { useProfilStore } from "@/stores/profil";
import { useSessionStore } from "@/stores/session";
import type { ProfileUpdate } from "@/lib/wire";

const session = useSessionStore();
const profil = useProfilStore();
const kuota = useKuotaStore();
const router = useRouter();

const inisial = computed(
  () => (profil.profile?.name || session.tampilanNama).trim().charAt(0).toUpperCase() || "?",
);
const labelTier = computed(() => kuota.labelTier || "Status belum tersedia");

const temaOpsi = [
  { value: "light", label: "Terang" },
  { value: "dark", label: "Gelap" },
];

const sedangUbah = ref(false);
const galat = ref("");
const draft = reactive({
  name: "",
  nib_status: "unknown",
  nib_last_4: "",
  kbli_code: "",
  business_description: "",
  marital_status: "unknown",
  spouse_aggregation_active: false,
  is_new_taxpayer_current_year: false,
  spouse_current_usaha_idr: "0",
  spouse_current_pekerjaan_bebas_idr: "0",
  spouse_current_already_final_idr: "0",
  prior_user_usaha_idr: "0",
  prior_user_pekerjaan_bebas_idr: "0",
  prior_user_already_final_idr: "0",
  prior_spouse_usaha_idr: "0",
  prior_spouse_pekerjaan_bebas_idr: "0",
  prior_spouse_already_final_idr: "0",
});

const nibOpsi = [
  { value: "unknown", label: "Belum diketahui" },
  { value: "no_nib", label: "Tidak punya NIB" },
  { value: "has_nib", label: "Punya NIB" },
];
const kawinOpsi = [
  { value: "unknown", label: "Belum diketahui" },
  { value: "no", label: "Tidak" },
  { value: "yes", label: "Ya" },
];

const baris = computed(() => {
  const p = profil.profile;
  if (!p) return [];
  return [
    { key: "name", label: "Nama", nilai: p.name || "Belum diisi" },
    { key: "entity", label: "Jenis wajib pajak", nilai: "Orang pribadi" },
    { key: "nib", label: "Status NIB", nilai: p.nib_masked || p.nib_status },
    { key: "kbli", label: "KBLI", nilai: p.kbli_code || "Belum diisi" },
    { key: "usaha", label: "Uraian usaha", nilai: p.business_description || "Belum diisi" },
    { key: "kawin", label: "Status perkawinan", nilai: p.marital_status },
    {
      key: "pasal",
      label: "Agregasi Pasal 58",
      nilai: p.spouse_aggregation_active ? "Ya" : "Tidak",
    },
  ];
});

function uang(nilai: number) {
  return String(nilai);
}

function mulaiUbah() {
  const p = profil.profile;
  draft.name = p?.name ?? "";
  draft.nib_status = p?.nib_status || "unknown";
  draft.nib_last_4 = "";
  draft.kbli_code = p?.kbli_code ?? "";
  draft.business_description = p?.business_description ?? "";
  draft.marital_status = p?.marital_status || "unknown";
  draft.spouse_aggregation_active = p?.spouse_aggregation_active ?? false;
  draft.is_new_taxpayer_current_year = p?.is_new_taxpayer_current_year ?? false;
  draft.spouse_current_usaha_idr = uang(p?.spouse_current_usaha_idr ?? 0);
  draft.spouse_current_pekerjaan_bebas_idr = uang(p?.spouse_current_pekerjaan_bebas_idr ?? 0);
  draft.spouse_current_already_final_idr = uang(p?.spouse_current_already_final_idr ?? 0);
  draft.prior_user_usaha_idr = uang(p?.prior_user_usaha_idr ?? 0);
  draft.prior_user_pekerjaan_bebas_idr = uang(p?.prior_user_pekerjaan_bebas_idr ?? 0);
  draft.prior_user_already_final_idr = uang(p?.prior_user_already_final_idr ?? 0);
  draft.prior_spouse_usaha_idr = uang(p?.prior_spouse_usaha_idr ?? 0);
  draft.prior_spouse_pekerjaan_bebas_idr = uang(p?.prior_spouse_pekerjaan_bebas_idr ?? 0);
  draft.prior_spouse_already_final_idr = uang(p?.prior_spouse_already_final_idr ?? 0);
  sedangUbah.value = true;
}

function angka(raw: string) {
  return parseRupiah(raw) ?? 0;
}

async function simpanData() {
  galat.value = "";
  const body: ProfileUpdate = {
    version: profil.profile?.version ?? 1,
    name: draft.name.trim(),
    entity_type: "orang_pribadi",
    nib_status: draft.nib_status,
    nib_last_4: draft.nib_status === "has_nib" ? draft.nib_last_4 : null,
    kbli_code: draft.kbli_code.trim(),
    business_description: draft.business_description.trim(),
    marital_status: draft.marital_status,
    spouse_aggregation_active: draft.spouse_aggregation_active,
    is_new_taxpayer_current_year: draft.is_new_taxpayer_current_year,
    spouse_current_usaha_idr: angka(draft.spouse_current_usaha_idr),
    spouse_current_pekerjaan_bebas_idr: angka(draft.spouse_current_pekerjaan_bebas_idr),
    spouse_current_already_final_idr: angka(draft.spouse_current_already_final_idr),
    prior_user_usaha_idr: angka(draft.prior_user_usaha_idr),
    prior_user_pekerjaan_bebas_idr: angka(draft.prior_user_pekerjaan_bebas_idr),
    prior_user_already_final_idr: angka(draft.prior_user_already_final_idr),
    prior_spouse_usaha_idr: angka(draft.prior_spouse_usaha_idr),
    prior_spouse_pekerjaan_bebas_idr: angka(draft.prior_spouse_pekerjaan_bebas_idr),
    prior_spouse_already_final_idr: angka(draft.prior_spouse_already_final_idr),
  };
  try {
    await profil.simpan(body);
    sedangUbah.value = false;
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Simpan gagal.";
  }
}

function batalUbah() {
  sedangUbah.value = false;
}

function gantiTema(nilai: string) {
  session.setTheme(nilai === "dark" ? "dark" : "light");
}

const catatanKeamanan = ref("");
const sheetBuka = ref(false);
const konfirmasi = ref("");
const sudahDiconfirmasi = ref(false);
const bisaHapus = computed(() => konfirmasi.value === HAPUS_AKUN);

onMounted(() => {
  void profil.muat();
  void kuota.muat();
  void profil.muatSesi();
});

function bukaSheet() {
  konfirmasi.value = "";
  sudahDiconfirmasi.value = false;
  sheetBuka.value = true;
}

function tutupSheet() {
  sheetBuka.value = false;
}

async function jalankanHapus() {
  galat.value = "";
  try {
    await profil.hapusAkun();
    await session.keluar();
    sudahDiconfirmasi.value = true;
    await router.push("/");
  } catch (error) {
    galat.value = error instanceof ApiFailure ? error.message : "Hapus akun gagal.";
  }
}
</script>

<template>
  <div class="page">
    <header class="lede">
      <span class="avatar" aria-hidden="true">{{ inisial }}</span>
      <div class="ident">
        <h2 class="t1">{{ profil.profile?.name || session.tampilanNama }}</h2>
        <p class="sub">{{ session.user?.email }}</p>
      </div>
      <AppPill class="tier" tone="accent" size="sm" :label="labelTier" icon="pembisahan" />
    </header>

    <AppCard
      title="Profil tahun pajak"
      subtitle="Orang pribadi saja. NIB disimpan empat digit terakhir, ditampilkan tertutup."
    >
      <template #actions>
        <AppButton v-if="!sedangUbah" variant="ghost" size="sm" icon="ubah" @click="mulaiUbah">
          {{ profil.profile ? "Ubah" : "Buat profil" }}
        </AppButton>
      </template>

      <p v-if="profil.belumAda && !sedangUbah" class="demo-cat">
        Profil tahun ini belum dibuat. Isi status NIB sebelum mencatat transaksi.
      </p>
      <p v-if="galat" class="demo-cat" role="alert">{{ galat }}</p>
      <dl v-if="!sedangUbah && baris.length" class="baca">
        <div v-for="b in baris" :key="b.key" class="baca-row">
          <dt class="u-label">{{ b.label }}</dt>
          <dd class="nilai figure">{{ b.nilai }}</dd>
        </div>
      </dl>
      <ul v-if="profil.profile?.audit_trail.length" class="baca">
        <li v-for="(jejak, i) in profil.profile.audit_trail" :key="i" class="baca-row">
          <span class="u-label">{{ jejak.field }}</span>
          <span>{{ jejak.old_value || "kosong" }} → {{ jejak.new_value || "kosong" }}</span>
        </li>
      </ul>

      <div v-else class="form">
        <AppField label="Nama" for-id="p-nama">
          <AppInput id="p-nama" v-model="draft.name" />
        </AppField>
        <AppField label="Status NIB" for-id="p-nib">
          <AppSelect id="p-nib" v-model="draft.nib_status" :options="nibOpsi" />
        </AppField>
        <AppField
          v-if="draft.nib_status === 'has_nib'"
          label="Empat digit terakhir NIB"
          for-id="p-nib4"
          hint="Hanya empat digit. NIB utuh tidak disimpan."
        >
          <AppInput id="p-nib4" v-model="draft.nib_last_4" mono maxlength="4" inputmode="numeric" />
        </AppField>
        <AppField label="KBLI" for-id="p-kbli">
          <AppInput id="p-kbli" v-model="draft.kbli_code" />
        </AppField>
        <AppField label="Uraian usaha" for-id="p-usaha">
          <AppInput id="p-usaha" v-model="draft.business_description" />
        </AppField>
        <AppField
          label="Status perkawinan"
          for-id="p-kawin"
          hint="Terpisah dari agregasi Pasal 58."
        >
          <AppSelect id="p-kawin" v-model="draft.marital_status" :options="kawinOpsi" />
        </AppField>
        <AppField label="Omzet usaha pasangan tahun ini" for-id="p-su">
          <AppInput id="p-su" v-model="draft.spouse_current_usaha_idr" mono inputmode="numeric" />
        </AppField>
        <AppField label="Pekerjaan bebas pasangan tahun ini" for-id="p-sp">
          <AppInput
            id="p-sp"
            v-model="draft.spouse_current_pekerjaan_bebas_idr"
            mono
            inputmode="numeric"
          />
        </AppField>
        <AppField label="Final tersendiri pasangan tahun ini" for-id="p-sf">
          <AppInput
            id="p-sf"
            v-model="draft.spouse_current_already_final_idr"
            mono
            inputmode="numeric"
          />
        </AppField>
        <AppField label="Usaha Anda tahun lalu" for-id="p-pu">
          <AppInput id="p-pu" v-model="draft.prior_user_usaha_idr" mono inputmode="numeric" />
        </AppField>
        <AppField label="Pekerjaan bebas Anda tahun lalu" for-id="p-pp">
          <AppInput
            id="p-pp"
            v-model="draft.prior_user_pekerjaan_bebas_idr"
            mono
            inputmode="numeric"
          />
        </AppField>
        <AppField label="Final tersendiri Anda tahun lalu" for-id="p-pf">
          <AppInput
            id="p-pf"
            v-model="draft.prior_user_already_final_idr"
            mono
            inputmode="numeric"
          />
        </AppField>
        <AppField label="Usaha pasangan tahun lalu" for-id="p-psu">
          <AppInput id="p-psu" v-model="draft.prior_spouse_usaha_idr" mono inputmode="numeric" />
        </AppField>
        <AppField label="Pekerjaan bebas pasangan tahun lalu" for-id="p-psp">
          <AppInput
            id="p-psp"
            v-model="draft.prior_spouse_pekerjaan_bebas_idr"
            mono
            inputmode="numeric"
          />
        </AppField>
        <AppField label="Final tersendiri pasangan tahun lalu" for-id="p-psf">
          <AppInput
            id="p-psf"
            v-model="draft.prior_spouse_already_final_idr"
            mono
            inputmode="numeric"
          />
        </AppField>

        <div class="aksi">
          <AppButton variant="ghost" @click="batalUbah">Batal</AppButton>
          <AppButton variant="primary" icon="check" @click="simpanData">Simpan</AppButton>
        </div>
        <p class="demo-cat">
          <label>
            <input v-model="draft.spouse_aggregation_active" type="checkbox" />
            Agregasi Pasal 58 aktif
          </label>
          <label>
            <input v-model="draft.is_new_taxpayer_current_year" type="checkbox" />
            Wajib pajak baru tahun ini
          </label>
        </p>
      </div>
    </AppCard>

    <AppCard title="Preferensi" subtitle="Berlaku untuk akun ini di perangkat ini.">
      <div class="tema">
        <span class="tema-ic">
          <AppIcon
            :name="session.theme === 'dark' ? 'bulan' : 'matahari'"
            :size="18"
            :stroke-width="1.7"
          />
        </span>
        <div class="tema-teks">
          <p class="baris-judul">{{ session.theme === "dark" ? "Mode gelap" : "Mode terang" }}</p>
          <p class="baris-sub">Pilihan yang sama ada di halaman Kuota dan langganan.</p>
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

    <AppCard
      title="Keamanan"
      subtitle="Sesi perangkat ini. Keluar hanya membatalkan sesi yang sedang dipakai."
    >
      <div class="baris-grup">
        <div class="baris-tunggal">
          <div class="baris-teks">
            <p class="baris-judul">Kata sandi</p>
            <p class="baris-sub">Atur ulang lewat surel. Token tidak disimpan di peramban.</p>
          </div>
          <AppButton to="/atur-ulang" variant="outline" size="sm" icon="kunci">
            Atur ulang kata sandi
          </AppButton>
        </div>

        <div class="baris-tunggal">
          <div class="baris-teks">
            <p class="baris-judul">Perangkat aktif</p>
            <p class="baris-sub">
              {{ profil.sesiPesan || "Perangkat yang masih punya sesi aktif." }}
            </p>
          </div>
          <AppButton
            variant="outline"
            size="sm"
            icon="shield"
            @click="catatanKeamanan = 'perangkat'"
          >
            Kelola perangkat
          </AppButton>
        </div>
      </div>

      <div v-if="catatanKeamanan === 'perangkat'" class="kunci">
        <div v-for="s in profil.sesi" :key="s.id" class="kunci-row">
          <span>
            {{ s.device_label }}
            <span class="kunci-sub">{{ s.last_seen_at }}</span>
          </span>
          <AppPill v-if="s.current" size="sm" label="Perangkat ini" tone="usaha" />
          <AppButton v-else variant="ghost" size="sm" @click="profil.cabut(s.id)">Cabut</AppButton>
        </div>
        <AppButton variant="outline" size="sm" @click="profil.cabutLain()">
          Keluar dari semua perangkat lain
        </AppButton>
      </div>
    </AppCard>

    <AppCard
      title="Zona berbahaya"
      subtitle="Menghapus profil, transaksi, citra, dan cuplikan. Pesanan pembayaran tetap tanpa identitas."
      class="bahaya"
    >
      <div class="bahaya-row">
        <div class="baris-teks">
          <p class="baris-judul">Hapus akun dan semua data</p>
          <p class="baris-sub">
            Ketik teks konfirmasi persis seperti yang diminta. Tindakan ini permanen.
          </p>
        </div>
        <AppButton variant="danger" icon="sampah" @click="bukaSheet"> Hapus akun </AppButton>
      </div>
    </AppCard>

    <WorkpaperNote />

    <AppSheet
      v-model:open="sheetBuka"
      title="Hapus akun dan semua data?"
      :subtitle="`Ketik ${HAPUS_AKUN} untuk membuka tombol penghapusan.`"
      @close="tutupSheet"
    >
      <p v-if="!sudahDiconfirmasi" class="sheet-teks">
        Semua transaksi yang tercatat, seluruh kertas kerja, dan jawaban klarifikasi Anda akan
        hilang permanen. Data yang sudah diunduh sebelumnya tidak ikut terhapus dari perangkat Anda.
      </p>

      <div v-if="!sudahDiconfirmasi" class="sheet-form">
        <AppField
          :label="`Ketik ${HAPUS_AKUN}`"
          for-id="konfirmasi-hapus"
          :hint="
            konfirmasi
              ? 'Harus huruf kapital semua, tanpa spasi di tengah.'
              : 'Lima huruf kapital, tanpa spasi.'
          "
        >
          <AppInput
            id="konfirmasi-hapus"
            v-model="konfirmasi"
            autocomplete="off"
            :placeholder="HAPUS_AKUN"
            :invalid="konfirmasi.length > 0 && !bisaHapus"
          />
        </AppField>
        <p v-if="galat" class="sheet-cat" role="alert">{{ galat }}</p>
      </div>

      <div v-else class="sheet-done">
        <AppIcon name="checkCircle" :size="20" :stroke-width="1.8" />
        <p>
          Demo selesai di sini. Tidak ada akun, transaksi, atau kertas kerja yang dihapus, karena
          aplikasi ini menyimpan semuanya di memori peramban dan memuat ulang saat ditutup.
        </p>
      </div>

      <template #footer>
        <AppButton v-if="!sudahDiconfirmasi" variant="ghost" @click="tutupSheet">Batal</AppButton>
        <AppButton
          v-if="!sudahDiconfirmasi"
          variant="danger"
          :disabled="!bisaHapus"
          @click="jalankanHapus"
        >
          Hapus permanen
        </AppButton>
        <AppButton v-else variant="primary" @click="tutupSheet">Tutup</AppButton>
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

/* ---- Identity ---------------------------------------------------------- */

.lede {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-4);
}

.avatar {
  display: grid;
  place-items: center;
  width: 3rem;
  height: 3rem;
  flex: none;
  border-radius: var(--r-full);
  background: var(--accent-soft);
  color: var(--accent-soft-ink);
  border: 1px solid var(--accent-line);
  font: var(--t-title-2);
  letter-spacing: var(--track-title-2);
  font-weight: 600;
}

.ident {
  flex: 1 1 12rem;
  min-width: 0;
}

.t1 {
  font: var(--t-title-1);
  letter-spacing: var(--track-title-1);
}

.sub {
  font: var(--t-body);
  color: var(--ink-2);
  margin-top: var(--s-1);
}

.tier {
  flex: none;
}

@media (min-width: 560px) {
  .tier {
    margin-left: auto;
  }
}

/* ---- Read-only rows ---------------------------------------------------- */

.baca {
  display: flex;
  flex-direction: column;
}

.baca-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-4);
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--hairline);
}

.baca-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.baca-row:first-child {
  padding-top: 0;
}

.nilai {
  font: var(--t-body);
  color: var(--ink);
  text-align: right;
  overflow-wrap: anywhere;
}

/* ---- Edit mode --------------------------------------------------------- */

.form {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.aksi {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3);
}

.aksi > * {
  flex: 1 1 auto;
}

@media (min-width: 560px) {
  .aksi {
    justify-content: flex-end;
  }

  .aksi > * {
    flex: none;
  }
}

.demo-cat {
  font: var(--t-caption);
  color: var(--ink-3);
  line-height: 1.45;
}

/* ---- Rows with a trailing control -------------------------------------- */

.baris-grup {
  display: flex;
  flex-direction: column;
  margin-top: var(--s-5);
  border-top: 1px solid var(--hairline);
}

.baris-tunggal {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  padding: var(--s-4) 0;
  border-bottom: 1px solid var(--hairline);
}

.baris-tunggal:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.baris-teks {
  flex: 1 1 12rem;
  min-width: 0;
}

.baris-judul {
  font: var(--t-label);
  font-weight: 600;
  letter-spacing: var(--track-label);
  color: var(--ink);
}

.baris-sub {
  font: var(--t-body-sm);
  color: var(--ink-3);
  line-height: 1.45;
  margin-top: var(--s-1);
}

/* ---- Switch ------------------------------------------------------------ */

.sw {
  position: relative;
  flex: none;
  width: 2.75rem;
  /* The button box is the hit area, so it carries the full touch height while
     the track inside it stays the optical size. */
  height: 2.75rem;
  display: grid;
  place-items: center;
  border-radius: var(--r-full);
}

.sw-track {
  position: relative;
  width: 100%;
  height: 1.625rem;
  border-radius: var(--r-full);
  border: 1px solid var(--hairline-strong);
  background: var(--surface-sunken);
  transition:
    background-color var(--t-base) var(--ease-out-soft),
    border-color var(--t-base) var(--ease-out-soft);
}

.knob {
  position: absolute;
  top: 50%;
  left: 0.125rem;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: var(--r-full);
  background: var(--surface);
  box-shadow: var(--shadow-1);
  transform: translate(0, -50%);
  transition: transform var(--t-base) var(--ease-spring);
}

.sw[aria-checked="true"] .sw-track {
  background: var(--accent);
  border-color: var(--accent);
}

.sw[aria-checked="true"] .knob {
  transform: translate(1.25rem, -50%);
}

@media (prefers-reduced-motion: reduce) {
  .knob {
    transition: none;
  }
}

/* ---- Appearance -------------------------------------------------------- */

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
  flex: 1 1 12rem;
  min-width: 0;
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

/* ---- Security detail --------------------------------------------------- */

.kunci {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--hairline);
}

.kunci-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--hairline);
  font: var(--t-body-sm);
  color: var(--ink);
}

.kunci-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.kunci-sub {
  display: block;
  font: var(--t-caption);
  color: var(--ink-3);
  margin-top: var(--s-1);
}

/* ---- Danger ------------------------------------------------------------ */

.bahaya {
  border-color: var(--cat-ask-line);
}

.bahaya-row {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: var(--s-4);
}

.bahaya-row .baris-teks {
  flex: 1 1 14rem;
}

@media (min-width: 560px) {
  .bahaya-row {
    flex-wrap: nowrap;
  }
}

/* ---- Sheet ------------------------------------------------------------- */

.sheet-teks {
  font: var(--t-body);
  color: var(--ink-2);
  line-height: 1.55;
}

.sheet-form {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  margin-top: var(--s-5);
}

.sheet-cat {
  font: var(--t-caption);
  color: var(--ink-3);
  line-height: 1.45;
}

.sheet-done {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  color: var(--accent);
}

.sheet-done p {
  font: var(--t-body-sm);
  color: var(--ink-2);
  line-height: 1.5;
}
</style>
