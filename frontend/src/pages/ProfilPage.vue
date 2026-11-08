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
import PanduanPanel from "@/components/app/PanduanPanel.vue";
import WorkpaperNote from "@/components/app/WorkpaperNote.vue";
import { ApiFailure } from "@/lib/api";
import { CAPABILITIES } from "@/lib/capabilities";
import { HAPUS_AKUN } from "@/lib/domain";
import { parseRupiah, rupiah, tanggalWaktuJakarta } from "@/lib/format";
import { useKuotaStore } from "@/stores/kuota";
import { useProfilStore } from "@/stores/profil";
import { usePanduanStore } from "@/stores/panduan";
import { useSessionStore } from "@/stores/session";
import type { ProfileUpdate } from "@/lib/wire";

const session = useSessionStore();
const profil = useProfilStore();
const panduan = usePanduanStore();
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
  spouse_tax_status: "unknown" as ProfileUpdate["spouse_tax_status"],
  has_selected_article_17: "",
  has_sole_proprietor_company: "",
  receives_salary: "",
  is_new_taxpayer_current_year: false,
  spouse_current_usaha_idr: "0",
  spouse_current_pekerjaan_bebas_idr: "0",
  spouse_current_already_final_idr: "0",
  prior_user_usaha_idr: "",
  prior_user_pekerjaan_bebas_idr: "",
  prior_user_already_final_idr: "",
  prior_spouse_usaha_idr: "",
  prior_spouse_pekerjaan_bebas_idr: "",
  prior_spouse_already_final_idr: "",
});

const nibOpsi = [
  { value: "unknown", label: "Belum diketahui" },
  { value: "no_nib", label: "Tidak punya NIB" },
  { value: "has_nib", label: "Punya NIB" },
];
const spouseTaxOptions = [
  { value: "unknown", label: "Belum tahu" },
  { value: "unmarried", label: "Tidak kawin" },
  { value: "separate", label: "Terpisah (PH/MT)" },
  { value: "joint", label: "Digabung" },
];
const jawabanOpsi = [
  { value: "", label: "Belum tahu" },
  { value: "yes", label: "Ya" },
  { value: "no", label: "Tidak" },
];

const FIELD_LABELS: Record<string, string> = {
  name: "Nama",
  nib_status: "Status NIB",
  nib_last_4: "Empat digit NIB",
  kbli_code: "KBLI",
  business_description: "Uraian usaha",
  marital_status: "Status perkawinan",
  spouse_aggregation_active: "Agregasi Pasal 58",
  is_new_taxpayer_current_year: "Wajib pajak baru",
  spouse_current_usaha_idr: "Omzet usaha pasangan tahun ini",
  spouse_current_pekerjaan_bebas_idr: "Pekerjaan bebas pasangan tahun ini",
  spouse_current_already_final_idr: "Final tersendiri pasangan tahun ini",
  prior_user_usaha_idr: "Usaha Anda tahun lalu",
  prior_user_pekerjaan_bebas_idr: "Pekerjaan bebas Anda tahun lalu",
  prior_user_already_final_idr: "Final tersendiri Anda tahun lalu",
  prior_spouse_usaha_idr: "Usaha pasangan tahun lalu",
  prior_spouse_pekerjaan_bebas_idr: "Pekerjaan bebas pasangan tahun lalu",
  prior_spouse_already_final_idr: "Final tersendiri pasangan tahun lalu",
};

function labelNib(status?: string, masked?: string | null): string {
  if (masked) return masked;
  if (status === "no_nib") return "Tidak punya NIB";
  if (status === "has_nib") return "Punya NIB";
  return "Belum diketahui";
}

function formatNilaiJejak(field: string, val?: string | null): string {
  if (!val || val === "kosong") return "kosong";
  if (field === "nib_status") {
    if (val === "no_nib") return "Tidak punya NIB";
    if (val === "has_nib") return "Punya NIB";
    if (val === "unknown") return "Belum diketahui";
  }
  if (field === "marital_status") {
    if (val === "yes") return "Kawin";
    if (val === "no") return "Tidak kawin";
    if (val === "unknown") return "Belum diketahui";
  }
  if (field === "spouse_aggregation_active" || field === "is_new_taxpayer_current_year") {
    if (val === "True" || val === "true") return "Ya";
    if (val === "False" || val === "false") return "Tidak";
  }
  if (field.endsWith("_idr") && /^[0-9]+$/.test(val)) {
    return rupiah(Number(val));
  }
  return val;
}

const baris = computed(() => {
  const p = profil.profile;
  if (!p) return [];
  return [
    { key: "name", label: "Nama", nilai: p.name || "Belum diisi" },
    { key: "entity", label: "Jenis wajib pajak", nilai: "Orang pribadi" },
    { key: "nib", label: "Status NIB", nilai: labelNib(p.nib_status, p.nib_masked) },
    { key: "kbli", label: "KBLI", nilai: p.kbli_code || "Belum diisi" },
    { key: "usaha", label: "Uraian usaha", nilai: p.business_description || "Belum diisi" },
    {
      key: "kawin",
      label: "Status perpajakan pasangan",
      nilai:
        spouseTaxOptions.find((option) => option.value === p.spouse_tax_status)?.label ??
        "Belum tahu",
    },
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
  draft.spouse_tax_status = p?.spouse_tax_status || "unknown";
  draft.has_selected_article_17 =
    p?.has_selected_article_17 == null ? "" : p.has_selected_article_17 ? "yes" : "no";
  draft.has_sole_proprietor_company =
    p?.has_sole_proprietor_company == null ? "" : p.has_sole_proprietor_company ? "yes" : "no";
  draft.receives_salary = p?.receives_salary == null ? "" : p.receives_salary ? "yes" : "no";
  draft.is_new_taxpayer_current_year = p?.is_new_taxpayer_current_year ?? false;
  draft.spouse_current_usaha_idr = uang(p?.spouse_current_usaha_idr ?? 0);
  draft.spouse_current_pekerjaan_bebas_idr = uang(p?.spouse_current_pekerjaan_bebas_idr ?? 0);
  draft.spouse_current_already_final_idr = uang(p?.spouse_current_already_final_idr ?? 0);
  draft.prior_user_usaha_idr = p?.prior_user_usaha_idr == null ? "" : uang(p.prior_user_usaha_idr);
  draft.prior_user_pekerjaan_bebas_idr =
    p?.prior_user_pekerjaan_bebas_idr == null ? "" : uang(p.prior_user_pekerjaan_bebas_idr);
  draft.prior_user_already_final_idr =
    p?.prior_user_already_final_idr == null ? "" : uang(p.prior_user_already_final_idr);
  draft.prior_spouse_usaha_idr =
    p?.prior_spouse_usaha_idr == null ? "" : uang(p.prior_spouse_usaha_idr);
  draft.prior_spouse_pekerjaan_bebas_idr =
    p?.prior_spouse_pekerjaan_bebas_idr == null ? "" : uang(p.prior_spouse_pekerjaan_bebas_idr);
  draft.prior_spouse_already_final_idr =
    p?.prior_spouse_already_final_idr == null ? "" : uang(p.prior_spouse_already_final_idr);
  sedangUbah.value = true;
}

function angka(raw: string) {
  return parseRupiah(raw) ?? 0;
}

function nilaiIdr(raw: string) {
  return raw.trim() === "" ? null : angka(raw);
}

function booleanJawaban(raw: string): boolean | null {
  if (raw === "yes") return true;
  if (raw === "no") return false;
  return null;
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
    marital_status: profil.profile?.marital_status ?? "unknown",
    spouse_tax_status: draft.spouse_tax_status,
    spouse_aggregation_active: draft.spouse_tax_status === "separate",
    has_selected_article_17: booleanJawaban(draft.has_selected_article_17),
    has_sole_proprietor_company: booleanJawaban(draft.has_sole_proprietor_company),
    receives_salary: booleanJawaban(draft.receives_salary),
    is_new_taxpayer_current_year: draft.is_new_taxpayer_current_year,
    spouse_current_usaha_idr: angka(draft.spouse_current_usaha_idr),
    spouse_current_pekerjaan_bebas_idr: angka(draft.spouse_current_pekerjaan_bebas_idr),
    spouse_current_already_final_idr: angka(draft.spouse_current_already_final_idr),
    prior_user_usaha_idr: nilaiIdr(draft.prior_user_usaha_idr),
    prior_user_pekerjaan_bebas_idr: nilaiIdr(draft.prior_user_pekerjaan_bebas_idr),
    prior_user_already_final_idr: nilaiIdr(draft.prior_user_already_final_idr),
    prior_spouse_usaha_idr: nilaiIdr(draft.prior_spouse_usaha_idr),
    prior_spouse_pekerjaan_bebas_idr: nilaiIdr(draft.prior_spouse_pekerjaan_bebas_idr),
    prior_spouse_already_final_idr: nilaiIdr(draft.prior_spouse_already_final_idr),
  };
  try {
    await profil.simpan(body);
    if (session.user) await panduan.muat();
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
/** Shown inside the sheet the moment the typed phrase stops matching. */
const konfirmasiGagal = computed(() =>
  konfirmasi.value.length > 0 && !bisaHapus.value
    ? `Ketikan persis ${HAPUS_AKUN}, huruf kapital semua.`
    : "",
);

onMounted(() => {
  void profil.muat().then(() => {
    if (session.user && profil.profile) void panduan.muat();
    else panduan.bersihkan();
  });
  void kuota.muat();
  // The device list reads /auth/sessions, so it is only fetched while the block
  // that renders it exists.
  if (CAPABILITIES.activeSessions) void profil.muatSesi();
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

      <template v-if="!sedangUbah && baris.length">
        <dl class="baca">
          <div v-for="b in baris" :key="b.key" class="baca-row">
            <dt class="u-label">{{ b.label }}</dt>
            <dd class="nilai figure">{{ b.nilai }}</dd>
          </div>
        </dl>
        <div v-if="profil.profile?.audit_trail.length" class="riwayat">
          <p class="u-label riwayat-judul">Riwayat perubahan</p>
          <ul class="baca">
            <li v-for="(jejak, i) in profil.profile.audit_trail" :key="i" class="baca-row">
              <span class="u-label">{{ FIELD_LABELS[jejak.field] || jejak.field }}</span>
              <span>
                {{ formatNilaiJejak(jejak.field, jejak.old_value) }} →
                {{ formatNilaiJejak(jejak.field, jejak.new_value) }}
              </span>
            </li>
          </ul>
        </div>
      </template>

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
          label="Status perpajakan pasangan"
          for-id="p-status-pasangan"
          hint="Pilih belum tahu jika belum yakin. Hanya PH/MT yang mengaktifkan agregasi Pasal 58."
        >
          <AppSelect
            id="p-status-pasangan"
            v-model="draft.spouse_tax_status"
            :options="spouseTaxOptions"
          />
        </AppField>
        <AppField
          label="Memilih tarif umum Pasal 17?"
          for-id="p-pasal17"
          hint="Belum tahu dapat dibiarkan kosong."
        >
          <AppSelect
            id="p-pasal17"
            v-model="draft.has_selected_article_17"
            :options="jawabanOpsi"
          />
        </AppField>
        <AppField
          label="Memiliki Perseroan Perorangan?"
          for-id="p-ptperorangan"
          hint="Belum tahu dapat dibiarkan kosong."
        >
          <AppSelect
            id="p-ptperorangan"
            v-model="draft.has_sole_proprietor_company"
            :options="jawabanOpsi"
          />
        </AppField>
        <AppField
          label="Menerima gaji sebagai pegawai?"
          for-id="p-gaji"
          hint="Belum tahu dapat dibiarkan kosong."
        >
          <AppSelect id="p-gaji" v-model="draft.receives_salary" :options="jawabanOpsi" />
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
            <input v-model="draft.is_new_taxpayer_current_year" type="checkbox" />
            Wajib pajak baru tahun ini
          </label>
        </p>
      </div>
    </AppCard>

    <PanduanPanel v-if="profil.profile" />

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

    <!-- Both rows need a route that is not there yet, so the card only renders
         while at least one of them is on; an empty security card says nothing. -->
    <AppCard
      v-if="CAPABILITIES.passwordReset || CAPABILITIES.activeSessions"
      title="Keamanan"
      subtitle="Sesi perangkat ini. Keluar hanya membatalkan sesi yang sedang dipakai."
    >
      <div class="baris-grup">
        <div v-if="CAPABILITIES.passwordReset" class="baris-tunggal">
          <div class="baris-teks">
            <p class="baris-judul">Kata sandi</p>
            <p class="baris-sub">Atur ulang lewat surel. Token tidak disimpan di peramban.</p>
          </div>
          <AppButton to="/atur-ulang" variant="outline" size="sm" icon="kunci">
            Atur ulang kata sandi
          </AppButton>
        </div>

        <div v-if="CAPABILITIES.activeSessions" class="baris-tunggal">
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

      <div v-if="CAPABILITIES.activeSessions && catatanKeamanan === 'perangkat'" class="kunci">
        <div v-for="s in profil.sesi" :key="s.id" class="kunci-row">
          <span>
            {{ s.device_label }}
            <span class="kunci-sub">{{ tanggalWaktuJakarta(s.last_seen_at) }}</span>
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
      :error="konfirmasiGagal ? konfirmasiGagal : galat"
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
              ? `Ketik persis ${HAPUS_AKUN}, huruf kapital semua.`
              : 'Tiga kata huruf kapital semua, persis seperti contoh di atas.'
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
      </div>

      <div v-else class="sheet-done">
        <AppIcon name="checkCircle" :size="20" :stroke-width="1.8" />
        <p>
          Seluruh data profil, transaksi, citra, dan cuplikan pajak Anda telah dihapus secara
          permanen.
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

.riwayat {
  margin-top: var(--s-5);
  padding-top: var(--s-4);
  border-top: 1px solid var(--hairline);
}

.riwayat-judul {
  margin-bottom: var(--s-3);
  font-weight: 600;
  color: var(--ink-2);
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
