/** Dashboard and recap. Figures are the API's; this store does not add them up into tax. */
import { defineStore } from "pinia";
import { ref } from "vue";
import { ApiFailure, api, apiBlob } from "@/lib/api";
import { TAX_YEAR } from "@/lib/domain";
import type { Dashboard, Recap } from "@/lib/wire";

export const usePajakStore = defineStore("pajak", () => {
  const dashboard = ref<Dashboard | null>(null);
  const recap = ref<Recap | null>(null);
  const pesan = ref("");
  const recapPesan = ref("");
  let dimuat = false;

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
    try {
      recap.value = await api<Recap>(`/recap/${TAX_YEAR}`);
      recapPesan.value = "";
    } catch (error) {
      recap.value = null;
      recapPesan.value = error instanceof ApiFailure ? error.message : "Rekap belum tersedia.";
    }
  }

  async function hitungUlang() {
    await api(`/tax/snapshots/${TAX_YEAR}/recalculate`, { method: "POST" });
    await muat(true);
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

  return { dashboard, recap, pesan, recapPesan, muat, hitungUlang, unduhPdf };
});
