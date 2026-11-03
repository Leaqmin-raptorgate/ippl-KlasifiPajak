/**
 * Unit tests for transaction edit (PUT /transactions/{id}).
 * API contract: docs/api §5.12 — body includes `version`; 409 VERSION_CONFLICT;
 * 422 field validation. HTTP is mocked; no network.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { ApiFailure } from "@/lib/api";
import type { Transaction, TransactionCreate } from "@/lib/wire";

const apiMock = vi.fn();
const tandaiUsang = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: (...args: unknown[]) => apiMock(...args),
  };
});

vi.mock("@/stores/pajak", () => ({
  usePajakStore: () => ({ tandaiUsang }),
}));

import { useTransaksiStore } from "@/stores/transaksi";

function sampleRow(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: "tx-001",
    version: 3,
    tx_date: "2026-03-10",
    client_name: "PT Sumber",
    invoice_no: "INV-1",
    amount_idr: 1_000_000,
    withheld_tax_amount_idr: 0,
    source_channel: "other",
    category: "usaha",
    source: "rule",
    description: "Jasa desain",
    classification: {
      category: "usaha",
      source: "rule",
      confidence: 0.9,
      rule_id: "r1",
      requires_clarification: false,
    },
    ...overrides,
  };
}

function editBody(version = 3): TransactionCreate & { version: number } {
  return {
    amount_idr: 2_000_000,
    tx_date: "2026-03-11",
    client_name: "PT Sumber Baru",
    description: "Jasa desain revisi",
    invoice_no: "INV-1",
    withheld_tax_amount_idr: 0,
    source_channel: "other",
    version,
  };
}

describe("useTransaksiStore.ubah (PUT /transactions/{id})", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    apiMock.mockReset();
    tandaiUsang.mockReset();
  });

  it("200: successful save updates terpilih/items and marks pajak stale", async () => {
    const store = useTransaksiStore();
    const original = sampleRow();
    store.items = [original];
    store.terpilih = original;

    const saved = sampleRow({
      version: 4,
      amount_idr: 2_000_000,
      tx_date: "2026-03-11",
      client_name: "PT Sumber Baru",
      description: "Jasa desain revisi",
    });
    apiMock.mockResolvedValueOnce(saved);

    const result = await store.ubah("tx-001", editBody(3));

    expect(apiMock).toHaveBeenCalledWith(
      "/transactions/tx-001",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(editBody(3)),
      }),
    );
    expect(result.version).toBe(4);
    expect(result.amount_idr).toBe(2_000_000);
    expect(store.terpilih?.version).toBe(4);
    expect(store.items[0]?.client_name).toBe("PT Sumber Baru");
    expect(tandaiUsang).toHaveBeenCalledOnce();
  });

  it("PUT payload includes the optimistic-concurrency version precondition", async () => {
    const store = useTransaksiStore();
    apiMock.mockResolvedValueOnce(sampleRow({ version: 8 }));

    await store.ubah("tx-001", editBody(7));

    const [, init] = apiMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { version: number };
    expect(body.version).toBe(7);
  });

  it("409 VERSION_CONFLICT: does not overwrite local row; rethrows ApiFailure", async () => {
    const store = useTransaksiStore();
    const original = sampleRow({ client_name: "Lokal Lama", version: 3 });
    store.items = [original];
    store.terpilih = original;

    const conflict = new ApiFailure(
      409,
      "VERSION_CONFLICT",
      "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi.",
    );
    apiMock.mockRejectedValueOnce(conflict);

    await expect(store.ubah("tx-001", editBody(3))).rejects.toMatchObject({
      status: 409,
      code: "VERSION_CONFLICT",
      message: "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi.",
    });

    expect(store.terpilih?.client_name).toBe("Lokal Lama");
    expect(store.terpilih?.version).toBe(3);
    expect(store.items[0]?.client_name).toBe("Lokal Lama");
    expect(tandaiUsang).not.toHaveBeenCalled();
  });

  it("409: store does not auto-reload the row (caller must show message / reload)", async () => {
    // Contrast: profil.simpan calls muat(true) on VERSION_CONFLICT.
    // transaksi.ubah currently only rethrows — document actual behaviour.
    const store = useTransaksiStore();
    store.items = [sampleRow()];
    const muatSpy = vi.spyOn(store, "muat");
    apiMock.mockRejectedValueOnce(
      new ApiFailure(
        409,
        "VERSION_CONFLICT",
        "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi.",
      ),
    );

    await expect(store.ubah("tx-001", editBody(3))).rejects.toBeInstanceOf(ApiFailure);
    expect(muatSpy).not.toHaveBeenCalled();
  });

  it("422: surfaces ApiFailure with field_errors and leaves local data intact", async () => {
    const store = useTransaksiStore();
    const original = sampleRow({ amount_idr: 1_000_000 });
    store.items = [original];
    store.terpilih = original;

    const invalid = new ApiFailure(
      422,
      "INVALID_DATE_RANGE",
      "Tanggal transaksi di luar tahun pajak 2026.",
      {
        tx_date: "Tanggal transaksi di luar tahun pajak 2026.",
      },
    );
    apiMock.mockRejectedValueOnce(invalid);

    await expect(store.ubah("tx-001", editBody(3))).rejects.toMatchObject({
      status: 422,
      fieldErrors: { tx_date: "Tanggal transaksi di luar tahun pajak 2026." },
    });
    expect(store.terpilih?.amount_idr).toBe(1_000_000);
    expect(tandaiUsang).not.toHaveBeenCalled();
  });
});
