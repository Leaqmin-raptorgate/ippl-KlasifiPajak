/**
 * Single source for category / regulation copy shown as "Dasar hukum".
 *
 * The API v1.3.1 transaction endpoints do not return a `dasar_hukum` /
 * `legal_basis` field (checked §5.10–§5.19). Wording below is quoted
 * verbatim from SRS v2.7 § «Definisi dan Istilah» (glosarium table).
 * Do not invent citations beyond that table.
 */

import type { Kategori } from "@/lib/domain";

/** SRS v2.7 § Definisi dan Istilah — term «PP 20/2026». */
export const SRS_PP_20_2026_ISTILAH = "PP 20/2026" as const;

/** SRS v2.7 § Definisi dan Istilah — definition of «PP 20/2026». */
export const SRS_PP_20_2026_DEFINISI =
  'Perubahan atas PP 55/2022. Acuan batas kelayakan Rp 4,8 miliar (Pasal 57 ayat (1), "tidak melebihi") dan daftar wajib pajak yang boleh memakai skema. Bukan sumber pita Rp 500 juta: teks PP 20/2026 tidak mengubah Pasal 60.' as const;

/** SRS v2.7 § Definisi dan Istilah — category rows, verbatim. */
export const SRS_KATEGORI_DEFINISI = {
  usaha: "Omzet kegiatan usaha yang berpotensi masuk skema PP 20/2026.",
  pekerjaan_bebas: "Kegiatan profesional mandiri yang dikecualikan dari skema final 0,5%.",
  already_final:
    "Penghasilan yang telah dikenai PPh final berdasarkan ketentuan tersendiri, sehingga tidak masuk basis 0,5% (PP 55/2022 Pasal 56 ayat (3) huruf c). Untuk uji cap Pasal 58, hanya penghasilan final dari usaha atau pekerjaan bebas (jasa) yang dihitung; penghasilan final di luar usaha/pekerjaan bebas tidak dimasukkan ke bucket ini.",
  non_object:
    "Aliran kas yang bukan objek omzet: pengembalian, setor modal, transfer antar rekening.",
} as const satisfies Record<Kategori, string>;

/** Short labels for the dasar-hukum card title (term column of the same table). */
export const SRS_KATEGORI_ISTILAH: Record<Kategori, string> = {
  usaha: "Usaha",
  pekerjaan_bebas: "Pekerjaan bebas",
  already_final: "already_final",
  non_object: "bukan_omzet / non_object",
};

export interface DasarHukumCuplikan {
  judul: string;
  teks: string;
  rujukan: string;
}

const RUJUKAN = "SRS v2.7 · Definisi dan Istilah";

/**
 * Card copy for the classification screen. Clarification-pending rows use the
 * PP 20/2026 glossary definition (no API legal-basis field to prefer).
 */
export function dasarHukumUntuk(
  category: Kategori | undefined,
  perluKlarifikasi: boolean,
): DasarHukumCuplikan {
  if (perluKlarifikasi || category === undefined) {
    return {
      judul: `Penentuan kategori (${SRS_PP_20_2026_ISTILAH})`,
      teks: SRS_PP_20_2026_DEFINISI,
      rujukan: RUJUKAN,
    };
  }
  return {
    judul: SRS_KATEGORI_ISTILAH[category],
    teks: SRS_KATEGORI_DEFINISI[category],
    rujukan: RUJUKAN,
  };
}
