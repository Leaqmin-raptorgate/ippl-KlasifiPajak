/** The workspace's destination list, shared by the sidebar and the tab bar. */

export interface Tujuan {
  to: string;
  label: string;
  short: string;
  icon: string;
  /** Primary actions are not destinations, they are entry points. */
  action?: boolean;
}

export const TUJUAN: Tujuan[] = [
  { to: "/dasbor", label: "Pajak", short: "Pajak", icon: "dasbor" },
  { to: "/transaksi", label: "Transaksi", short: "Transaksi", icon: "transaksi" },
  { to: "/transaksi/baru", label: "Tambah", short: "Tambah", icon: "tambah", action: true },
  { to: "/asisten", label: "Asisten", short: "Asisten", icon: "asisten" },
  { to: "/profil", label: "Profil", short: "Profil", icon: "profil" },
];

/** Reachable from the sidebar and the account menu, but not worth a tab slot. */
export const TUJUAN_SEKUNDER: Tujuan[] = [
  { to: "/kuota", label: "Kuota dan langganan", short: "Kuota", icon: "kuota" },
];
