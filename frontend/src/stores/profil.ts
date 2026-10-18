/** Year profile, active sessions, and account deletion. */
import { defineStore } from "pinia";
import { ref } from "vue";
import { ApiFailure, api } from "@/lib/api";
import { HAPUS_AKUN, TAX_YEAR } from "@/lib/domain";
import type { Profile, ProfileUpdate, SessionItem } from "@/lib/wire";

export const useProfilStore = defineStore("profil", () => {
  const profile = ref<Profile | null>(null);
  const belumAda = ref(false);
  const sesi = ref<SessionItem[]>([]);
  const pesan = ref("");
  const sesiPesan = ref("");
  let dimuat = false;

  async function muat(paksa = false) {
    if (dimuat && !paksa) return;
    pesan.value = "";
    try {
      profile.value = await api<Profile>(`/profiles/${TAX_YEAR}`);
      belumAda.value = false;
      dimuat = true;
    } catch (error) {
      profile.value = null;
      belumAda.value = error instanceof ApiFailure && error.code === "PROFILE_NOT_FOUND";
      pesan.value = error instanceof ApiFailure && !belumAda.value ? error.message : "";
      dimuat = belumAda.value;
    }
  }

  async function simpan(body: ProfileUpdate) {
    pesan.value = "";
    try {
      profile.value = await api<Profile>(`/profiles/${TAX_YEAR}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      belumAda.value = false;
      dimuat = true;
    } catch (error) {
      if (error instanceof ApiFailure && error.code === "VERSION_CONFLICT") await muat(true);
      throw error;
    }
  }

  async function muatSesi() {
    sesiPesan.value = "";
    try {
      const data = await api<{ items: SessionItem[] }>("/auth/sessions");
      sesi.value = data.items;
    } catch (error) {
      sesi.value = [];
      sesiPesan.value =
        error instanceof ApiFailure ? error.message : "Daftar perangkat belum tersedia.";
    }
  }

  async function cabut(id: string) {
    await api(`/auth/sessions/${id}`, { method: "DELETE" });
    await muatSesi();
  }

  async function cabutLain() {
    await api("/auth/sessions", { method: "DELETE" });
    await muatSesi();
  }

  async function hapusAkun() {
    await api("/account", {
      method: "DELETE",
      body: JSON.stringify({ confirmation: HAPUS_AKUN }),
    });
    profile.value = null;
  }

  return {
    profile,
    belumAda,
    sesi,
    pesan,
    sesiPesan,
    muat,
    simpan,
    muatSesi,
    cabut,
    cabutLain,
    hapusAkun,
  };
});
