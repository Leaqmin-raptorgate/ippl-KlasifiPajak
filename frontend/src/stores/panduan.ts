/** Static legal guidance returned for the signed-in profile and tax totals. */
import { defineStore } from "pinia";
import { ref } from "vue";
import { ApiFailure, api } from "@/lib/api";
import type { Guidance } from "@/lib/wire";

export const usePanduanStore = defineStore("panduan", () => {
  const panduan = ref<Guidance | null>(null);
  const pesan = ref("");

  async function muat() {
    pesan.value = "";
    try {
      panduan.value = await api<Guidance>("/guidance");
    } catch (error) {
      panduan.value = null;
      if (!(error instanceof ApiFailure && error.code === "PROFILE_NOT_FOUND")) {
        pesan.value = error instanceof ApiFailure ? error.message : "Panduan belum tersedia.";
      }
    }
  }

  function bersihkan() {
    panduan.value = null;
    pesan.value = "";
  }

  return { panduan, pesan, muat, bersihkan };
});
