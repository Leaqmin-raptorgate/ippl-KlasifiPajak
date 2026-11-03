/**
 * Single source for category / regulation copy shown as "Dasar hukum".
 *
 * Provides user-facing statutory citations and explanations for each
 * classification category and pending clarification states based on
 * PP 20/2026 jo. PP 55/2022.
 */

import { KATEGORI_LABEL, type Kategori } from "@/lib/domain";

export const KATEGORI_DASAR_HUKUM: Record<
  Kategori,
  { judul: string; teks: string; rujukan: string }
> = {
  usaha: {
    judul: "Omzet Usaha (PP 20/2026)",
    teks: "Omzet kegiatan usaha berpotensi masuk skema PPh final 0,5% sesuai PP 20/2026 Pasal 56. Bagian omzet usaha orang pribadi sampai dengan Rp 500 juta dalam satu tahun pajak tidak dikenai PPh berdasarkan PP 55/2022 Pasal 60 ayat (2) jo. UU PPh Pasal 7 ayat (2a).",
    rujukan: "PP 20/2026 Pasal 56 jo. PP 55/2022 Pasal 60 ayat (2)",
  },
  pekerjaan_bebas: {
    judul: "Pekerjaan Bebas (PP 55/2022)",
    teks: "Kegiatan profesional mandiri atau jasa tenaga ahli dikecualikan dari skema PPh final 0,5% peredaran usaha, dan dihitung menggunakan norma penghitungan neto (NPPN) atau tarif umum.",
    rujukan: "PP 55/2022 Pasal 56 ayat (3) huruf a jo. UU PPh Pasal 14",
  },
  already_final: {
    judul: "PPh Final Tersendiri (PP 55/2022)",
    teks: "Penghasilan yang telah dikenai PPh final berdasarkan ketentuan tersendiri tidak masuk basis peredaran usaha 0,5% agar tidak terjadi pengenaan pajak berganda.",
    rujukan: "PP 55/2022 Pasal 56 ayat (3) huruf c",
  },
  non_object: {
    judul: "Bukan Objek Pajak (UU PPh)",
    teks: "Aliran kas yang bukan objek omzet seperti pengembalian dana, setor modal, atau transfer antar-rekening sendiri dicatat untuk kebutuhan pembukuan dan tidak dikenai pajak penghasilan.",
    rujukan: "UU PPh Pasal 4 ayat (3) jo. PP 55/2022 Pasal 56 ayat (3) huruf d",
  },
};

export interface DasarHukumCuplikan {
  judul: string;
  teks: string;
  rujukan: string;
}

/**
 * Card copy for the classification screen.
 */
export function dasarHukumUntuk(
  category: Kategori | undefined,
  perluKlarifikasi: boolean,
): DasarHukumCuplikan {
  if (perluKlarifikasi || category === undefined) {
    return {
      judul: "Penentuan Kategori Transaksi",
      teks: "Sebelum perlakuan pajak dapat dihitung, transaksi harus dipastikan apakah berasal dari peredaran usaha, pekerjaan bebas, objek final tersendiri, atau bukan objek pajak.",
      rujukan: "PP 20/2026 jo. PP 55/2022 Pasal 56",
    };
  }
  const info = KATEGORI_DASAR_HUKUM[category];
  return {
    judul: KATEGORI_LABEL[category] ?? info.judul,
    teks: info.teks,
    rujukan: info.rujukan,
  };
}
