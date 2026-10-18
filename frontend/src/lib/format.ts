/**
 * Formatting helpers for money, dates and rates.
 *
 * Rupiah is an integer unit with no minor unit, so everything here is integer
 * arithmetic. Never a float, matching the engine's money type.
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

const MONTHS_LONG = [
  "Januari",
  "Februari",
  "Maret",
  "April",
  "Mei",
  "Juni",
  "Juli",
  "Agustus",
  "September",
  "Oktober",
  "November",
  "Desember",
];

/** `27500000` -> `Rp 27.500.000` */
export function rupiah(value: number): string {
  return `Rp ${group(Math.max(0, Math.trunc(value)))}`;
}

/** The figure alone, no symbol, for cells whose column already carries one. */
export function rupiahPlain(value: number): string {
  return group(Math.max(0, Math.trunc(value)));
}

function group(value: number): string {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** Compact form for dense summaries: `Rp 27,5 jt`, `Rp 1,2 M`. */
export function rupiahShort(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `Rp ${trim(value / 1_000_000_000)} M`;
  if (abs >= 1_000_000) return `Rp ${trim(value / 1_000_000)} jt`;
  if (abs >= 1_000) return `Rp ${trim(value / 1_000)} rb`;
  return rupiah(value);
}

function trim(value: number): string {
  const fixed = value.toFixed(1);
  return fixed.endsWith(".0") ? fixed.slice(0, -2) : fixed;
}

/** `2026-10-24` -> `24 Okt 2026` */
export function tanggal(iso: string): string {
  const d = parseIso(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export function tanggalPanjang(iso: string): string {
  const d = parseIso(iso);
  return `${d.getDate()} ${MONTHS_LONG[d.getMonth()]} ${d.getFullYear()}`;
}

export function tanggalPendek(iso: string): string {
  const d = parseIso(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** `2026-10-01` -> `Okt 2026` */
export function bulanTahun(iso: string): string {
  const d = parseIso(iso);
  return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** `2026-10-24T09:42` -> `09.42` */
export function jam(iso: string): string {
  const [h, m] = iso.split("T")[1]?.split(":") ?? ["00", "00"];
  return `${h}.${m}`;
}

export function persen(value: number, digits = 1): string {
  return `${value.toFixed(digits).replace(".", ",")}%`;
}

/** Parse `YYYY-MM-DD` as a local calendar date, not a UTC instant. */
export function parseIso(iso: string): Date {
  const [y, m, d] = iso.split("T")[0].split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

/** Typed separators are stripped. A decimal part is rejected: rupiah has no minor unit. */
export function parseRupiah(raw: string): number | null {
  const teks = raw.trim();
  if (/[.,]\d{1,2}$/.test(teks)) return null;
  const angka = teks.replace(/[.,\s_]/g, "");
  if (angka.length === 0 || /[^0-9]/.test(angka)) return null;
  const nilai = Number(angka);
  return Number.isSafeInteger(nilai) ? nilai : null;
}

export { MONTHS, MONTHS_LONG };
