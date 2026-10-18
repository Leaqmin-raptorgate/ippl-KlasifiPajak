/** Cookie session. Theme stays on this device; the account does not. */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { ApiFailure, api } from "@/lib/api";
import type { Me } from "@/lib/wire";

export type Theme = "light" | "dark";

const THEME_KEY = "kp-theme";

export const useSessionStore = defineStore("session", () => {
  const user = ref<Me | null>(null);
  const siap = ref(false);
  const sesiBerakhir = ref(false);
  const pesan = ref("");
  const theme = ref<Theme>(readTheme());
  let muatJanji: Promise<void> | null = null;

  const tampilanNama = computed(() => user.value?.username ?? "");
  const inisial = computed(() => tampilanNama.value.trim().charAt(0).toUpperCase() || "?");

  async function muat() {
    if (siap.value) return;
    if (muatJanji) return muatJanji;
    muatJanji = (async () => {
      try {
        user.value = await api<Me>("/auth/me");
        sesiBerakhir.value = false;
      } catch (error) {
        user.value = null;
        if (
          error instanceof ApiFailure &&
          (error.code === "session_expired" || error.code === "session_revoked")
        ) {
          sesiBerakhir.value = true;
        }
      } finally {
        siap.value = true;
        muatJanji = null;
      }
    })();
    return muatJanji;
  }

  function jatuh(code: string) {
    user.value = null;
    siap.value = true;
    sesiBerakhir.value = code === "session_expired" || code === "session_revoked";
  }

  async function masuk(identifier: string, password: string) {
    pesan.value = "";
    await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    });
    siap.value = false;
    sesiBerakhir.value = false;
    await muat();
  }

  async function daftar(email: string, username: string, password: string) {
    pesan.value = "";
    await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    });
  }

  async function keluar() {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      /* a dead cookie still leaves the shell */
    }
    user.value = null;
    siap.value = true;
    sesiBerakhir.value = false;
  }

  async function mintaReset(email: string) {
    return api<{ message: string }>("/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  async function konfirmasiReset(token: string, newPassword: string) {
    return api<{ message: string }>("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  }

  function setTheme(next: Theme) {
    theme.value = next;
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* private mode: appearance simply does not persist */
    }
  }

  function toggleTheme() {
    setTheme(theme.value === "dark" ? "light" : "dark");
  }

  return {
    user,
    siap,
    sesiBerakhir,
    pesan,
    theme,
    tampilanNama,
    inisial,
    muat,
    jatuh,
    masuk,
    daftar,
    keluar,
    mintaReset,
    konfirmasiReset,
    setTheme,
    toggleTheme,
  };
});

function readTheme(): Theme {
  const attr = document.documentElement.dataset.theme;
  return attr === "dark" ? "dark" : "light";
}

export function watchSystemTheme() {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", (e) => {
    try {
      if (localStorage.getItem(THEME_KEY)) return;
    } catch {
      /* ignore */
    }
    document.documentElement.dataset.theme = e.matches ? "dark" : "light";
  });
}
