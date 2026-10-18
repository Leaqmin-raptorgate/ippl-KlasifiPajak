/**
 * Icon geometry.
 *
 * Inline stroked paths rather than an icon webfont: no extra request, no
 * flash of unstyled glyphs, and stroke weight stays optically even next to
 * text at every size.
 */

export const ICON_PATHS = {
  dasbor: "M4 4h6v6H4zM14 4h6v4h-6zM14 12h6v8h-6zM4 14h6v6H4z",
  transaksi: "M4 6h16M4 12h11M4 18h7M17.5 16.5l2.5 2.5 4-4.5",
  tambah: "M12 5v14M5 12h14",
  asisten:
    "M12 3l1.6 4.6L18 9l-4.4 1.5L12 15l-1.6-4.5L6 9l4.4-1.4zM18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z",
  profil: "M12 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM5 20a7 7 0 0114 0",
  kuota: "M4 17a8 8 0 1116 0M12 13l4-3",
  chevronRight: "M9 5l7 7-7 7",
  chevronDown: "M5 9l7 7 7-7",
  chevronLeft: "M15 5l-7 7 7 7",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
  filter: "M4 6h16M7 12h10M10 18h4",
  arrowRight: "M5 12h13M13 6l6 6-6 6",
  arrowUpRight: "M8 16L16 8M9 8h7v7",
  unduh: "M12 4v10M8 11l4 4 4-4M5 19h14",
  check: "M5 12.5l4.5 4.5L19 7",
  checkCircle: "M12 21a9 9 0 100-18 9 9 0 000 18zM8.5 12.2l2.4 2.4 4.6-5",
  helpCircle:
    "M12 21a9 9 0 100-18 9 9 0 000 18zM9.6 9.4a2.5 2.5 0 114 2c-.9.7-1.6 1.2-1.6 2.4M12 17.2v.1",
  shield: "M12 3l7 3v5.5c0 4.3-2.9 8-7 9.5-4.1-1.5-7-5.2-7-9.5V6z",
  dokumen: "M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5",
  toko: "M4 9h16v11H4zM4 9l1.6-5h12.8L20 9M9 20v-6h6v6",
  pena: "M4 20l1-4L16 5l3 3L8 19zM14.5 6.5l3 3",
  persen:
    "M6.5 18.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM17.5 10.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM18 6L6 18",
  tukar: "M4 8h13M14 5l3 3-3 3M20 16H7M10 13l-3 3 3 3",
  sampah: "M5 7h14M10 7V5h4v2M6 7l1 13h10l1-13M10 11v6M14 11v6",
  ubah: "M4 20l1-4L16 5l3 3L8 19zM14.5 6.5l3 3",
  unggah: "M12 16V6M8 9l4-4 4 4M5 19h14",
  bulan: "M20 14.5A8.5 8.5 0 019.5 4a8.5 8.5 0 1010.5 10.5z",
  matahari:
    "M12 17a5 5 0 100-10 5 5 0 000 10zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  menu: "M4 7h16M4 12h16M4 17h16",
  tutup: "M6 6l12 12M18 6L6 18",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v5M12 7.6v.1",
  kunci: "M7 11V8a5 5 0 0110 0v3M5.5 11h13v9h-13z",
  petir: "M13 3L5.5 13.5H11l-1 7.5L17.5 10.5H12z",
  pemisahan: "M12 4v16M7 8l-3 4 3 4M17 8l3 4-3 4",
  logout: "M14 5H7v14h7M17 8l4 4-4 4M21 12h-9",
  plusCircle: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 8v8M8 12h8",
  obrolan: "M20 12a7 7 0 01-7 7H8l-4 2 1-4.5A7 7 0 1113 5a7 7 0 017 7z",
} as const;

export type IconName = keyof typeof ICON_PATHS;

/** Icon names a caller may pass without a cast, while keeping `IconName` complete. */
export type IconProp = IconName | (string & {});
