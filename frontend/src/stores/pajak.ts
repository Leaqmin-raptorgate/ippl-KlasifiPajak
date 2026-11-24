/** Dashboard, recap, and one active month snapshot. Figures are the API's; this store does not add them up into tax. */
import { defineStore } from "pinia";
import { ref } from "vue";
import { ApiFailure, api, apiBlob } from "@/lib/api";
import { CAPABILITIES } from "@/lib/capabilities";
import { TAX_YEAR } from "@/lib/domain";
import type { Dashboard, MonthSnapshot, Recap } from "@/lib/wire";

export const usePajakStore = defineStore("pajak", () => {
  const dashboard = ref<Dashboard | null>(null);
  const recap = ref<Recap | null>(null);
  const pesan = ref("");
  const recapPesan = ref("");
  /** Month token of the open trace sheet. Null when the sheet is closed. */
  const jejakBulan = ref<string | null>(null);
  const jejakCuplikan = ref<MonthSnapshot | null>(null);
  const jejakMemuat = ref(false);
  const jejakKode = ref("");
  const jejakPesan = ref("");
  let dimuat = false;
  let jejakUrutan = 0;

  async function muat(paksa = false) {
    if (dimuat && !paksa) return;
    pesan.value = "";
    try {
      dashboard.value = await api<Dashboard>(`/tax/dashboard?tax_year=${TAX_YEAR}`);
      dimuat = true;
    } catch (error) {
      dashboard.value = null;
      pesan.value = error instanceof ApiFailure ? error.message : "Ringkasan pajak belum tersedia.";
    }
    // Only ask for the recap when its route exists. A call that can only 404 is
    // noise in the network tab, and its message would otherwise surface as user
    // copy on a screen that has nothing to say about it.
    if (CAPABILITIES.workpaperExport) {
      try {
        recap.value = await api<Recap>(`/recap/${TAX_YEAR}`);
        recapPesan.value = "";
      } catch (error) {
        recap.value = null;
        recapPesan.value = error instanceof ApiFailure ? error.message : "Rekap belum tersedia.";
      }
    } else {
      recap.value = null;
      recapPesan.value = "";
    }
  }

  async function hitungUlang() {
    await api(`/tax/snapshots/${TAX_YEAR}/recalculate`, { method: "POST" });
    await muat(true);
  }

  function tandaiUsang() {
    dimuat = false;
  }

  /**
   * Open the active snapshot for one stored month (FR-47).
   * A response is kept only while its month is still the open sheet.
   */
  async function bukaJejakBulan(month: string) {
    const urutan = ++jejakUrutan;
    jejakBulan.value = month;
    jejakCuplikan.value = null;
    jejakKode.value = "";
    jejakPesan.value = "";
    jejakMemuat.value = true;
    try {
      const data = await api<MonthSnapshot>(
        `/tax/snapshots/${TAX_YEAR}/${encodeURIComponent(month)}`,
      );
      if (urutan !== jejakUrutan || jejakBulan.value !== month || data.month !== month) return;
      jejakCuplikan.value = data;
    } catch (error) {
      if (urutan !== jejakUrutan || jejakBulan.value !== month) return;
      jejakCuplikan.value = null;
      if (error instanceof ApiFailure) {
        jejakKode.value = error.code;
        jejakPesan.value = error.message;
      } else {
        jejakKode.value = "REQUEST_FAILED";
        jejakPesan.value = "Jejak bulan belum tersedia.";
      }
    } finally {
      if (urutan === jejakUrutan && jejakBulan.value === month) jejakMemuat.value = false;
    }
  }

  function tutupJejakBulan() {
    jejakUrutan += 1;
    jejakBulan.value = null;
    jejakCuplikan.value = null;
    jejakMemuat.value = false;
    jejakKode.value = "";
    jejakPesan.value = "";
  }

  async function unduhPdf() {
    const blob = await apiBlob(`/recap/${TAX_YEAR}/pdf`, { method: "POST" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `Workpaper_PPh_Final_${TAX_YEAR}.pdf`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return {
    dashboard,
    recap,
    pesan,
    recapPesan,
    jejakBulan,
    jejakCuplikan,
    jejakMemuat,
    jejakKode,
    jejakPesan,
    muat,
    hitungUlang,
    tandaiUsang,
    bukaJejakBulan,
    tutupJejakBulan,
    unduhPdf,
  };
});
