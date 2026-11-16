/** The workspace's destination list, shared by the site header and its mobile menu. */

export interface Tujuan {
  to: string;
  label: string;
  /** Primary actions are not destinations, they are entry points. */
  action?: boolean;
}

export const TUJUAN: Tujuan[] = [
  { to: "/dasbor", label: "Pajak" },
  { to: "/transaksi", label: "Transaksi" },
  { to: "/transaksi/baru", label: "Tambah transaksi", action: true },
  { to: "/asisten", label: "Asisten" },
  { to: "/profil", label: "Profil" },
];

/** Reachable from the header and the account menu. */
export const TUJUAN_SEKUNDER: Tujuan[] = [{ to: "/kuota", label: "Kuota" }];

/** Header order: every destination once, in the order the owner reads them. */
export const NAVIGASI: Tujuan[] = [...TUJUAN, ...TUJUAN_SEKUNDER];
