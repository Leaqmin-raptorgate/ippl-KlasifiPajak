/**
 * The consent checkbox shows the sentence from API spec §5.34.
 * The text, including line breaks and the bullet, is asserted literally.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { ApiFailure } from "@/lib/api";

const apiMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: (...args: unknown[]) => apiMock(...args),
  };
});

import AiConsentNote from "@/components/app/AiConsentNote.vue";
import { useSessionStore } from "@/stores/session";

const TEKS_PERSETUJUAN = [
  "Saya menyetujui pengiriman data ke layanan AI di luar aplikasi, hanya untuk fitur yang saya pakai:",
  "• Klasifikasi: deskripsi transaksi, nominal, nama klien (hanya jika berbentuk badan usaha), status NIB, kode KBLI, dan kategori transaksi sebelumnya.",
  "• Baca struk (OCR): seluruh foto struk, termasuk apa pun yang tercetak di dalamnya. Metadata foto dihapus.",
  "• Asisten: pertanyaan yang saya ketik, serta tanggal, nominal dan kategori transaksi, data profil pajak (termasuk status pasangan dan angka peredaran), dan ringkasan bulanan. Deskripsi transaksi, nomor faktur dan nama klien tidak dikirim ke asisten.",
  "Saya dapat mencabut persetujuan kapan saja di Profil. Fitur AI tidak dapat dipakai tanpa persetujuan ini.",
].join("\n");

describe("AiConsentNote", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    apiMock.mockReset();
  });

  it("shows the exact consent sentence", () => {
    const wrapper = mount(AiConsentNote);
    expect(wrapper.get(".naskah").text()).toBe(TEKS_PERSETUJUAN);
    expect(wrapper.get(".naskah").text()).toContain("• ");
    expect(wrapper.get(".naskah").text()).not.toContain("di luar negeri");
  });

  it("restores the checkbox and shows the message when saving consent fails", async () => {
    const session = useSessionStore();
    session.persetujuanAi = true;
    const wrapper = mount(AiConsentNote);
    const box = wrapper.get<HTMLInputElement>("input[type='checkbox']");
    expect(box.element.checked).toBe(true);

    apiMock.mockRejectedValueOnce(new ApiFailure(500, "UPSTREAM", "Persetujuan belum tersimpan."));
    await box.setValue(false);
    await flushPromises();

    expect(box.element.checked).toBe(true);
    expect(wrapper.get("[role='alert']").text()).toBe("Persetujuan belum tersimpan.");
    expect(apiMock).toHaveBeenCalledWith("/ai-consent", {
      method: "PUT",
      body: JSON.stringify({ consent: false }),
    });
  });
});
