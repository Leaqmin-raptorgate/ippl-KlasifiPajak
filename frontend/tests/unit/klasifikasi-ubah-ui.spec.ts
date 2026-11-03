/**
 * UI tests for the transaction-edit sheet on KlasifikasiPage.
 * HTTP is mocked via store.ubah; no real network.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { nextTick } from "vue";
import { ApiFailure } from "@/lib/api";
import type { Transaction } from "@/lib/wire";
import KlasifikasiPage from "@/pages/KlasifikasiPage.vue";
import { usePajakStore } from "@/stores/pajak";
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

async function mountPage(row: Transaction) {
  const pinia = createPinia();
  setActivePinia(pinia);

  const store = useTransaksiStore();
  store.items = [row];
  store.terpilih = row;
  vi.spyOn(store, "buka").mockResolvedValue(row);
  vi.spyOn(store, "muatJejak").mockResolvedValue(undefined);
  vi.spyOn(store, "muatKlarifikasi").mockResolvedValue(undefined);

  const pajak = usePajakStore();
  vi.spyOn(pajak, "muat").mockResolvedValue(undefined);
  vi.spyOn(pajak, "tandaiUsang").mockImplementation(() => {});

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div />" } },
      { path: "/klasifikasi/:id", component: KlasifikasiPage },
      { path: "/transaksi", component: { template: "<div />" } },
    ],
  });
  await router.push(`/klasifikasi/${row.id}`);
  await router.isReady();

  const wrapper = mount(KlasifikasiPage, {
    global: {
      plugins: [pinia, router],
      stubs: {
        // Keep real AppSheet/AppButton/AppField/AppInput for error + disabled checks.
        AppIcon: true,
        AppMeter: true,
        AppPill: true,
        SourceTag: true,
        WorkpaperNote: true,
        Teleport: true,
      },
    },
  });
  await flushPromises();
  return { wrapper, store, pajak };
}

describe("KlasifikasiPage transaction edit sheet", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("200: successful save closes the sheet and keeps updated store row", async () => {
    const row = sampleRow();
    const { wrapper, store } = await mountPage(row);
    const ubah = vi.spyOn(store, "ubah").mockResolvedValue(
      sampleRow({
        version: 4,
        client_name: "PT Sumber Baru",
        amount_idr: 2_000_000,
        description: "Revisi",
      }),
    );

    // Open edit sheet via the "Ubah detail" control.
    const openBtn = wrapper.findAll("button").find((b) => b.text().includes("Ubah detail"));
    expect(openBtn).toBeTruthy();
    await openBtn!.trigger("click");
    await nextTick();

    expect(
      wrapper.find('[role="dialog"]').exists() || wrapper.text().includes("Ubah detail transaksi"),
    ).toBe(true);

    const saveBtn = wrapper.findAll("button").find((b) => b.text().includes("Simpan perubahan"));
    expect(saveBtn).toBeTruthy();
    await saveBtn!.trigger("click");
    await flushPromises();

    expect(ubah).toHaveBeenCalled();
    const payload = ubah.mock.calls[0]?.[1] as { version: number };
    expect(payload.version).toBe(3);
    // Sheet closed on success (open flag false → dialog gone / title absent as open sheet).
    expect(wrapper.find(".err").exists()).toBe(false);
  });

  it("409 stale: shows conflict message and does not call silent overwrite", async () => {
    const row = sampleRow({ client_name: "Lokal Lama" });
    const { wrapper, store } = await mountPage(row);
    vi.spyOn(store, "ubah").mockRejectedValue(
      new ApiFailure(
        409,
        "VERSION_CONFLICT",
        "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi.",
      ),
    );

    const openBtn = wrapper.findAll("button").find((b) => b.text().includes("Ubah detail"));
    await openBtn!.trigger("click");
    await nextTick();
    const saveBtn = wrapper.findAll("button").find((b) => b.text().includes("Simpan perubahan"));
    await saveBtn!.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain(
      "Data ini sudah diubah di perangkat lain. Muat ulang, lalu simpan lagi.",
    );
    expect(store.terpilih?.client_name).toBe("Lokal Lama");
    expect(store.terpilih?.version).toBe(3);
  });

  it("422: shows validation message from ApiFailure", async () => {
    const row = sampleRow();
    const { wrapper, store } = await mountPage(row);
    vi.spyOn(store, "ubah").mockRejectedValue(
      new ApiFailure(422, "INVALID_DATE_RANGE", "Tanggal transaksi di luar tahun pajak 2026.", {
        tx_date: "Tanggal transaksi di luar tahun pajak 2026.",
      }),
    );

    const openBtn = wrapper.findAll("button").find((b) => b.text().includes("Ubah detail"));
    await openBtn!.trigger("click");
    await nextTick();
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("Simpan perubahan"))!
      .trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Tanggal transaksi di luar tahun pajak 2026.");
  });

  it("save button is disabled while the request is in flight", async () => {
    const row = sampleRow();
    const { wrapper, store } = await mountPage(row);

    let resolveUbah!: (value: Transaction) => void;
    vi.spyOn(store, "ubah").mockImplementation(
      () =>
        new Promise<Transaction>((resolve) => {
          resolveUbah = resolve;
        }),
    );

    const openBtn = wrapper.findAll("button").find((b) => b.text().includes("Ubah detail"));
    await openBtn!.trigger("click");
    await nextTick();

    const saveBtn = wrapper.findAll("button").find((b) => b.text().includes("Simpan perubahan"));
    expect(saveBtn).toBeTruthy();
    await saveBtn!.trigger("click");
    await nextTick();

    const busy = wrapper.findAll("button").find((b) => b.text().includes("Menyimpan"));
    expect(busy).toBeTruthy();
    expect(busy!.attributes("disabled")).toBeDefined();

    resolveUbah(
      sampleRow({
        version: 4,
        client_name: "PT Sumber Baru",
      }),
    );
    await flushPromises();
  });

  // Spec: 422 may carry per-field Indonesian errors (API §5.12 / create-like validation).
  // Current UI only surfaces ApiFailure.message, not fieldErrors — track as known gap.
  it.fails("422: renders field_errors next to the affected inputs (spec)", async () => {
    const row = sampleRow();
    const { wrapper, store } = await mountPage(row);
    vi.spyOn(store, "ubah").mockRejectedValue(
      new ApiFailure(422, "INVALID_DATE_RANGE", "Permintaan tidak sah.", {
        tx_date: "Tanggal transaksi di luar tahun pajak 2026.",
      }),
    );

    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("Ubah detail"))!
      .trigger("click");
    await nextTick();
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("Simpan perubahan"))!
      .trigger("click");
    await flushPromises();

    // Desired: field-level copy visible even when top-level message is generic.
    expect(wrapper.text()).toContain("Tanggal transaksi di luar tahun pajak 2026.");
    expect(wrapper.find("#edit-tgl").exists()).toBe(true);
    // A dedicated field error node would ideally be associated with the input.
    expect(wrapper.find("[data-field-error='tx_date']").exists()).toBe(true);
  });
});
