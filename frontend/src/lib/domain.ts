/**
 * Labels and the academic ruleset identity.
 *
 * `PUBLIC_RULESET` is the published identity of `pp20-2026-academic-1` for
 * unauthenticated copy. It is not a calculation. A signed-in figure comes from
 * `GET /tax/dashboard` or `GET /recap/{tax_year}`.
 */

export const TAX_YEAR = 2026;

export type Kategori = "usaha" | "pekerjaan_bebas" | "already_final" | "non_object";
export type Sumber = "rule" | "ai" | "user_clarification" | "user_override";
export type SourceChannel = "marketplace" | "corporate_client" | "retail" | "other";

export const KATEGORI_LABEL: Record<Kategori, string> = {
  usaha: "Usaha",
  pekerjaan_bebas: "Pekerjaan bebas",
  already_final: "Final tersendiri",
  non_object: "Bukan objek",
};

export const KATEGORI_RINGKAS: Record<Kategori, string> = {
  usaha: "Usaha",
  pekerjaan_bebas: "Pekerjaan bebas",
  already_final: "Final",
  non_object: "Bukan objek",
};

export const SUMBER_LABEL: Record<Sumber, string> = {
  rule: "Aturan",
  ai: "AI",
  user_clarification: "Klarifikasi",
  user_override: "Override",
};

export const SOURCE_CHANNEL_LABEL: Record<SourceChannel, string> = {
  marketplace: "Marketplace",
  corporate_client: "Klien perusahaan",
  retail: "Ritel",
  other: "Lainnya",
};

export const PUBLIC_RULESET = {
  id: "pp20-2026-academic-1",
  nama: "PP 20/2026",
  berlaku: "2026-09-26",
  bebasUsaha: 500_000_000,
  plafonUsaha: 4_800_000_000,
  tarifLabel: "0,5%",
} as const;

export const HAPUS_AKUN = "HAPUS AKUN SAYA";
