/**
 * The consent checkbox shows the sentence from API spec §5.34.
 * The text, including line breaks and the bullet, is asserted literally.
 */
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import AiConsentNote from "@/components/app/AiConsentNote.vue";

const TEKS_PERSETUJUAN = [
  "Saya menyetujui pengiriman data ke layanan AI di luar aplikasi, hanya untuk fitur yang saya pakai:",
  "• Klasifikasi: deskripsi transaksi, nominal, nama klien (hanya jika berbentuk badan usaha), status NIB, kode KBLI, dan kategori transaksi sebelumnya.",
  "• Baca struk (OCR): seluruh foto struk, termasuk apa pun yang tercetak di dalamnya. Metadata foto dihapus.",
  "• Asisten: pertanyaan yang saya ketik, serta tanggal, nominal dan kategori transaksi, data profil pajak (termasuk status pasangan dan angka peredaran), dan ringkasan bulanan. Deskripsi transaksi, nomor faktur dan nama klien tidak dikirim ke asisten.",
  "Saya dapat mencabut persetujuan kapan saja di Profil. Fitur AI tidak dapat dipakai tanpa persetujuan ini.",
].join("\n");

describe("AiConsentNote", () => {
  it("shows the exact consent sentence", () => {
    setActivePinia(createPinia());
    const wrapper = mount(AiConsentNote);
    expect(wrapper.get(".naskah").text()).toBe(TEKS_PERSETUJUAN);
    expect(TEKS_PERSETUJUAN).toContain("• ");
    expect(TEKS_PERSETUJUAN).not.toContain("di luar negeri");
  });
});
