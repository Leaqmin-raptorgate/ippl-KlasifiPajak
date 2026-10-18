/**
 * Transaction ledger. Rows are the last API page, not a local tax engine.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import { ApiFailure, api } from "@/lib/api";
import { TAX_YEAR } from "@/lib/domain";
import type { Kategori } from "@/lib/domain";
import type {
  AuditEvent,
  Clarification,
  Transaction,
  TransactionCreate,
  TransactionList,
} from "@/lib/wire";

export type { Kategori, Sumber, SourceChannel } from "@/lib/domain";
export { KATEGORI_LABEL, KATEGORI_RINGKAS, SOURCE_CHANNEL_LABEL, SUMBER_LABEL } from "@/lib/domain";

export interface DaftarQuery {
  page?: number;
  per_page?: number;
  month?: string;
  client_name?: string;
  invoice_no?: string;
}

export const useTransaksiStore = defineStore("transaksi", () => {
  const items = ref<Transaction[]>([]);
  const pagination = ref<TransactionList["pagination"] | null>(null);
  const pesan = ref("");
  const terpilih = ref<Transaction | null>(null);
  const klarifikasi = ref<Clarification | null>(null);
  const jejak = ref<AuditEvent[]>([]);
  const jejakPesan = ref("");

  async function muat(query: DaftarQuery = {}) {
    pesan.value = "";
    const params = new URLSearchParams({
      tax_year: String(TAX_YEAR),
      page: String(query.page ?? 1),
      per_page: String(query.per_page ?? 20),
    });
    if (query.month) params.set("month", query.month);
    if (query.client_name) params.set("client_name", query.client_name);
    if (query.invoice_no) params.set("invoice_no", query.invoice_no);
    const data = await api<TransactionList>(`/transactions?${params}`);
    items.value = data.items.map(normal);
    pagination.value = data.pagination;
  }

  function byId(id: string) {
    if (terpilih.value?.id === id) return terpilih.value;
    return items.value.find((row) => row.id === id);
  }

  async function buka(id: string) {
    const known = byId(id);
    if (known) {
      terpilih.value = known;
      return known;
    }
    await muat({ per_page: 100 });
    terpilih.value = items.value.find((row) => row.id === id) ?? null;
    return terpilih.value;
  }

  async function buat(body: TransactionCreate) {
    const row = normal(
      await api<Transaction>("/transactions", { method: "POST", body: JSON.stringify(body) }),
    );
    terpilih.value = row;
    return row;
  }

  async function ubah(id: string, body: TransactionCreate & { version: number }) {
    const row = normal(
      await api<Transaction>(`/transactions/${id}`, { method: "PUT", body: JSON.stringify(body) }),
    );
    terpilih.value = row;
    return row;
  }

  async function hapus(id: string) {
    await api(`/transactions/${id}`, { method: "DELETE" });
    items.value = items.value.filter((row) => row.id !== id);
    if (terpilih.value?.id === id) terpilih.value = null;
  }

  async function muatKlarifikasi(id: string) {
    try {
      klarifikasi.value = await api<Clarification>(`/transactions/${id}/clarification`);
    } catch (error) {
      klarifikasi.value = null;
      if (!(error instanceof ApiFailure) || error.status !== 404) throw error;
    }
  }

  async function jawab(id: string, category: Kategori) {
    const row = normal(
      await api<Transaction>(`/transactions/${id}/clarification`, {
        method: "POST",
        body: JSON.stringify({ category }),
      }),
    );
    terpilih.value = { ...byId(id), ...row, id };
    klarifikasi.value = null;
    return terpilih.value;
  }

  async function override(id: string, newCategory: Kategori, note?: string) {
    const row = normal(
      await api<Transaction>(`/transactions/${id}/override`, {
        method: "POST",
        body: JSON.stringify({ new_category: newCategory, note: note || undefined }),
      }),
    );
    terpilih.value = { ...byId(id), ...row, id };
    return terpilih.value;
  }

  async function muatJejak(id: string) {
    jejakPesan.value = "";
    try {
      const data = await api<{ events?: AuditEvent[] } | AuditEvent[]>(
        `/transactions/${id}/audit-trail`,
      );
      jejak.value = Array.isArray(data) ? data : (data.events ?? []);
    } catch (error) {
      jejak.value = [];
      jejakPesan.value = error instanceof ApiFailure ? error.message : "Jejak belum tersedia.";
    }
  }

  async function klasifikasiUlang(ids: string[]) {
    return api("/transactions/reclassify", {
      method: "POST",
      body: JSON.stringify({ transaction_ids: ids }),
    });
  }

  async function unggahStruk(file: File) {
    const body = new FormData();
    body.set("file", file);
    return api<{
      image_id: string;
      candidate_fields: {
        amount_idr?: number;
        tx_date?: string;
        client_name?: string;
        invoice_no?: string;
      };
    }>("/transactions/ocr-upload", { method: "POST", body });
  }

  async function konfirmasiStruk(imageId: string, fields: Record<string, unknown>) {
    const row = normal(
      await api<Transaction>("/transactions/ocr-confirm", {
        method: "POST",
        body: JSON.stringify({ image_id: imageId, ...fields }),
      }),
    );
    terpilih.value = row;
    return row;
  }

  return {
    items,
    pagination,
    pesan,
    terpilih,
    klarifikasi,
    jejak,
    jejakPesan,
    muat,
    byId,
    buka,
    buat,
    ubah,
    hapus,
    muatKlarifikasi,
    jawab,
    override,
    muatJejak,
    klasifikasiUlang,
    unggahStruk,
    konfirmasiStruk,
  };
});

function normal(row: Transaction): Transaction {
  const date = String(row.tx_date).slice(0, 10);
  const klas = row.classification;
  return {
    ...row,
    tx_date: date,
    category: (klas?.category ?? row.category) as Kategori,
    source: klas?.source ?? row.source,
  };
}
