/** Dasbor monthly table: leading empty months fold into one line, and a toggle shows them. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { nextTick } from "vue";
import { ApiFailure } from "@/lib/api";
import type { Dashboard, MonthSnapshot, MonthSummary } from "@/lib/wire";
import DasborPage from "@/pages/DasborPage.vue";
import { usePajakStore } from "@/stores/pajak";
import { useTransaksiStore } from "@/stores/transaksi";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: (path: string, init?: RequestInit) =>
      init === undefined ? apiMock(path) : apiMock(path, init),
  };
});

function bulanKosong(month: string): MonthSummary {
  return {
    month,
    scheme_eligibility_status: "scheme_eligible",
    usaha_omzet_idr: 0,
    porsi_bebas_idr: 0,
    porsi_kena_idr: 0,
    tax_0_5_pct_idr: 0,
    withheld_tax_idr: 0,
    sisa_bayar_idr: 0,
    overwithheld_excess_idr: 0,
    overwithheld_status: "nihil",
    pekerjaan_bebas_omzet_idr: 0,
    already_final_omzet_idr: 0,
    non_object_omzet_idr: 0,
    input_hash: "test",
  };
}

/** Jan-Sep empty, Oct with turnover, Nov-Dec empty again. */
function bulanTahun2026(): MonthSummary[] {
  return Array.from({ length: 12 }, (_, i) => {
    const month = `2026-${String(i + 1).padStart(2, "0")}`;
    const bulan = bulanKosong(month);
    if (month === "2026-10") {
      return {
        ...bulan,
        usaha_omzet_idr: 12_000_000,
        tax_0_5_pct_idr: 60_000,
        sisa_bayar_idr: 60_000,
        overwithheld_status: "belum_diperhitungkan",
      };
    }
    return bulan;
  });
}

const HASH_OKT = "v2:7737310876e2cf5a1421f459652437b9e781b18b18b7c7b8d00eabdb7c71378d";
const HASH_NOV = "v2:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const HASH_JAN = "v2:0000000000000000000000000000000000000000000000000000000000000000";
const HASH_LAMA = "v2:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const DISCLAIMER = "DOKUMEN KERJA (WORKPAPER) — BUKAN SPT RESMI DAN BUKAN PRODUK DJP/CORETAX.";

function cuplikan(month: string, overrides: Partial<MonthSnapshot> = {}): MonthSnapshot {
  return {
    month,
    version: 2,
    status: "berlaku",
    ruleset_id: "ruleset-bulan",
    effective_date: "2026-09-26",
    rounding_rule: "floor",
    scheme_eligibility_status: "scheme_eligible",
    next_year_ineligible: false,
    prior_year_resolution_source: "prior_year",
    input_hash: HASH_OKT,
    usaha_omzet_idr: 12_000_000,
    porsi_bebas_idr: 12_000_000,
    porsi_kena_idr: 0,
    tax_0_5_pct_idr: 60_000,
    withheld_tax_idr: 0,
    sisa_bayar_idr: 60_000,
    overwithheld_excess_idr: 0,
    overwithheld_status: "nihil",
    pekerjaan_bebas_omzet_idr: 0,
    already_final_omzet_idr: 0,
    non_object_omzet_idr: 0,
    annotation: "Pita bebas masih utuh.",
    disclaimer: DISCLAIMER,
    ...overrides,
  };
}

function tertunda<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

let terpasang: VueWrapper | null = null;

afterEach(() => {
  terpasang?.unmount();
  terpasang = null;
  document.documentElement.style.overflow = "";
  window.happyDOM.setViewport({ width: 1024, height: 768 });
  window.innerWidth = 1024;
  window.innerHeight = 768;
});

async function renderDasbor(
  bulan: MonthSummary[],
  opsi: {
    lampirkan?: boolean;
    metadata?: { ruleset_id: string; effective_date: string; disclaimer?: string };
  } = {},
) {
  terpasang?.unmount();
  const pinia = createPinia();
  setActivePinia(pinia);
  const pajak = usePajakStore();
  pajak.dashboard = {
    metadata: {
      ruleset_id: opsi.metadata?.ruleset_id ?? "test",
      effective_date: opsi.metadata?.effective_date ?? "2026-01-01",
      rounding_rule: "floor",
      disclaimer: opsi.metadata?.disclaimer ?? "workpaper",
    },
    thresholds: {
      pita_500_juta: {
        limit_idr: 500_000_000,
        ytd_usaha_omzet_idr: 12_000_000,
        remaining_free_band_idr: 488_000_000,
        provisional_omzet_idr: 0,
        split_month: null,
        annotation: "",
      },
      eligibility_prior_year_cap_4_8m: {
        limit_idr: 4_800_000_000,
        combined_prior_year_gross_idr: 0,
        resolution_source: "prior_year",
        status: "scheme_eligible",
      },
      monitoring_current_year_cap_4_8m: {
        limit_idr: 4_800_000_000,
        ytd_usaha_omzet_idr: 12_000_000,
        ytd_pekerjaan_bebas_omzet_idr: 0,
        ytd_already_final_omzet_idr: 0,
        spouse_current_year_usaha_omzet_idr: 0,
        spouse_current_year_pekerjaan_bebas_omzet_idr: 0,
        spouse_current_year_already_final_omzet_idr: 0,
        ytd_combined_gross_idr: 12_000_000,
        provisional_usaha_omzet_idr: 0,
        next_year_ineligible: false,
      },
      pasal_58: { spouse_aggregation_active: false, badge_label: "" },
    },
    monthly_summaries: bulan,
  } as unknown as Dashboard;
  vi.spyOn(pajak, "muat").mockResolvedValue(undefined);
  vi.spyOn(useTransaksiStore(), "muat").mockResolvedValue(undefined);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: DasborPage },
      { path: "/transaksi", component: { template: "<div />" } },
      { path: "/transaksi/baru", component: { template: "<div />" } },
      { path: "/profil", component: { template: "<div />" } },
      { path: "/kuota", component: { template: "<div />" } },
    ],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(DasborPage, {
    attachTo: opsi.lampirkan ? document.body : undefined,
    global: {
      plugins: [pinia, router],
      stubs: { AppIcon: true, TransactionLedger: true, PanduanPanel: true },
    },
  });
  terpasang = wrapper;
  await flushPromises();
  return { wrapper, pajak };
}

function dialog(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>("[role='dialog']");
}

function bidang(field: string): string {
  return document.body.querySelector(`[data-field='${field}']`)?.textContent?.trim() ?? "";
}

async function tungguFrame() {
  await flushPromises();
  await nextTick();
  await new Promise((resolve) => setImmediate(resolve));
}

async function bukaJejak(wrapper: VueWrapper, month: string) {
  const tombol = wrapper.get(`[data-month='${month}']`);
  (tombol.element as HTMLButtonElement).focus();
  await tombol.trigger("click");
  await tungguFrame();
  return tombol;
}

describe("dasbor monthly table", () => {
  it("folds the leading empty months into one line, and months with data stay", async () => {
    const { wrapper } = await renderDasbor(bulanTahun2026());
    const baris = wrapper.findAll("tbody tr");

    expect(wrapper.get(".tabel tr.ringkas").text()).toBe(
      "Jan - Sep 2026: tidak ada omzet yang terhitung",
    );
    // One folded line, Oct, then Nov and Dec.
    expect(baris).toHaveLength(4);
    expect(wrapper.text()).toContain("Okt 2026");
  });

  it("the toggle expands every month and reports its state", async () => {
    const { wrapper } = await renderDasbor(bulanTahun2026());
    const tombol = () => wrapper.findAll("button").find((b) => b.text().includes("bulan"))!;

    expect(tombol().text()).toBe("Tampilkan semua bulan");
    expect(tombol().attributes("aria-expanded")).toBe("false");

    await tombol().trigger("click");
    await flushPromises();

    expect(wrapper.findAll("tbody tr")).toHaveLength(12);
    expect(wrapper.find(".tabel tr.ringkas").exists()).toBe(false);
    expect(tombol().attributes("aria-expanded")).toBe("true");
    expect(tombol().text()).toBe("Sembunyikan bulan kosong");
  });

  it("does not fold when there is no leading run of two or more empty months", async () => {
    const bulan = bulanTahun2026();
    bulan[0] = { ...bulan[0]!, usaha_omzet_idr: 1_000_000 };
    const { wrapper } = await renderDasbor(bulan);

    expect(wrapper.find(".tabel tr.ringkas").exists()).toBe(false);
    expect(wrapper.findAll("tbody tr")).toHaveLength(12);
  });
});

describe("dasbor month trace (FR-47)", () => {
  afterEach(() => {
    apiMock.mockReset();
  });

  function sematkanSempit() {
    window.happyDOM.setViewport({ width: 390, height: 844 });
    window.innerWidth = 390;
    window.innerHeight = 844;
  }

  it("shows a loading state, then the active snapshot figures and provenance", async () => {
    const tertundaOk = tertunda<MonthSnapshot>();
    apiMock.mockReturnValue(tertundaOk.promise);
    const { wrapper } = await renderDasbor(bulanTahun2026(), { lampirkan: true });

    expect(wrapper.find("[data-month='2026-10']").text()).toBe("Lihat jejak");
    expect(wrapper.find(".tabel tr.ringkas").text()).not.toContain("Lihat jejak");

    await bukaJejak(wrapper, "2026-10");
    expect(apiMock).toHaveBeenCalledWith("/tax/snapshots/2026/2026-10");
    const terbuka = dialog();
    expect(terbuka).not.toBeNull();
    expect(terbuka?.textContent).toContain("Memuat jejak bulan.");
    expect(terbuka?.textContent).not.toContain(HASH_OKT);
    expect(document.body.querySelector("[role='alert']")).toBeNull();

    tertundaOk.resolve(
      cuplikan("2026-10", {
        overwithheld_status: "belum_diperhitungkan",
        overwithheld_excess_idr: 5_000,
      }),
    );
    await tungguFrame();

    expect(bidang("month")).toBe("Okt 2026");
    expect(bidang("usaha_omzet_idr")).toBe("Rp 12.000.000");
    expect(bidang("porsi_bebas_idr")).toBe("Rp 12.000.000");
    expect(bidang("porsi_kena_idr")).toBe("Rp 0");
    expect(bidang("tax_0_5_pct_idr")).toBe("Rp 60.000");
    expect(bidang("withheld_tax_idr")).toBe("Rp 0");
    expect(bidang("sisa_bayar_idr")).toBe("Rp 60.000");
    expect(bidang("overwithheld_excess_idr")).toBe("Rp 5.000");
    expect(bidang("overwithheld_status")).toBe("Belum diperhitungkan");
    expect(bidang("pekerjaan_bebas_omzet_idr")).toBe("Rp 0");
    expect(bidang("already_final_omzet_idr")).toBe("Rp 0");
    expect(bidang("non_object_omzet_idr")).toBe("Rp 0");
    expect(bidang("input_hash")).toBe(HASH_OKT);
    expect(bidang("ruleset_id")).toBe("ruleset-bulan");
    expect(bidang("effective_date")).toBe("26 September 2026");
    expect(bidang("version")).toBe("2");
    expect(bidang("status")).toBe("Berlaku");
    expect(bidang("rounding_rule")).toBe("floor");
    expect(bidang("scheme_eligibility_status")).toBe("Memenuhi syarat");
    expect(bidang("annotation")).toBe("Pita bebas masih utuh.");
    expect(bidang("disclaimer")).toBe(DISCLAIMER);
    expect(document.body.querySelector("[role='alert']")).toBeNull();
  });

  it("traces a zero-activity month only after the leading empty group is expanded", async () => {
    apiMock.mockResolvedValue(
      cuplikan("2026-01", {
        version: 1,
        ruleset_id: "ruleset-januari",
        input_hash: HASH_JAN,
        usaha_omzet_idr: 0,
        porsi_bebas_idr: 0,
        tax_0_5_pct_idr: 0,
        sisa_bayar_idr: 0,
        annotation: "",
      }),
    );
    const { wrapper } = await renderDasbor(bulanTahun2026(), { lampirkan: true });

    expect(wrapper.find("[data-month='2026-01']").exists()).toBe(false);
    expect(wrapper.find("[data-month='2026-11']").exists()).toBe(true);
    expect(wrapper.findAll("[data-month]")).toHaveLength(3);

    const tombol = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Tampilkan semua bulan"));
    expect(tombol).toBeTruthy();
    await tombol!.trigger("click");
    await flushPromises();

    expect(wrapper.findAll("[data-month]")).toHaveLength(12);
    expect(wrapper.get("[data-month='2026-01']").text()).toBe("Lihat jejak");
    await bukaJejak(wrapper, "2026-01");

    expect(apiMock).toHaveBeenCalledWith("/tax/snapshots/2026/2026-01");
    expect(bidang("month")).toBe("Jan 2026");
    expect(bidang("usaha_omzet_idr")).toBe("Rp 0");
    expect(bidang("tax_0_5_pct_idr")).toBe("Rp 0");
    expect(bidang("input_hash")).toBe(HASH_JAN);
    expect(bidang("ruleset_id")).toBe("ruleset-januari");
    expect(document.body.querySelector("[data-field='annotation']")).toBeNull();
    expect(bidang("disclaimer")).toBe(DISCLAIMER);
  });

  it("renders SNAPSHOT_NOT_FOUND as an empty state, not an alert", async () => {
    apiMock.mockRejectedValue(
      new ApiFailure(404, "SNAPSHOT_NOT_FOUND", "Cuplikan bulan yang diminta tidak ada."),
    );
    const { wrapper } = await renderDasbor(bulanTahun2026(), { lampirkan: true });
    await bukaJejak(wrapper, "2026-10");

    expect(dialog()).not.toBeNull();
    expect(document.body.querySelector(".jejak-kosong")?.textContent).toContain(
      "Belum ada cuplikan",
    );
    expect(document.body.textContent).toContain("Cuplikan bulan yang diminta tidak ada.");
    expect(document.body.querySelector("[role='alert']")).toBeNull();
    expect(bidang("input_hash")).toBe("");
  });

  it("shows a different request error without the empty state", async () => {
    apiMock.mockRejectedValue(
      new ApiFailure(503, "ROUTE_UNAVAILABLE", "Layanan belum tersambung."),
    );
    const { wrapper } = await renderDasbor(bulanTahun2026(), { lampirkan: true });
    await bukaJejak(wrapper, "2026-10");

    expect(dialog()).not.toBeNull();
    expect(document.body.querySelector(".jejak-kosong")).toBeNull();
    expect(document.body.querySelector("[role='alert']")?.textContent).toContain(
      "Layanan belum tersambung.",
    );
  });

  it("keeps the dashboard stamp on the page, shows the month stamp in the sheet, and drops late responses", async () => {
    const oktober = tertunda<MonthSnapshot>();
    const november = tertunda<MonthSnapshot>();
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith("/2026-10")) return oktober.promise;
      if (path.endsWith("/2026-11")) return november.promise;
      return Promise.reject(new Error(path));
    });
    const { wrapper } = await renderDasbor(bulanTahun2026(), {
      lampirkan: true,
      metadata: {
        ruleset_id: "pp20-dasbor",
        effective_date: "2026-01-15",
        disclaimer: "cap dasbor, bukan cap bulan",
      },
    });
    const pageNote = () => wrapper.get(".stamp").text();
    const sheetNote = () => dialog()?.querySelector(".jejak-stamp")?.textContent ?? "";

    expect(pageNote()).toContain("ruleset pp20-dasbor");
    expect(pageNote()).toContain("15 Januari 2026");
    expect(pageNote()).not.toContain("pp20-bulan-oktober");
    expect(pageNote()).not.toContain("pp20-bulan-november");

    await bukaJejak(wrapper, "2026-10");
    expect(pageNote()).toContain("ruleset pp20-dasbor");
    expect(sheetNote()).toBe("");

    await bukaJejak(wrapper, "2026-11");
    oktober.resolve(
      cuplikan("2026-10", {
        ruleset_id: "pp20-bulan-oktober",
        input_hash: HASH_LAMA,
        effective_date: "2026-03-01",
      }),
    );
    await tungguFrame();

    expect(document.body.textContent).not.toContain(HASH_LAMA);
    expect(document.body.textContent).not.toContain("pp20-bulan-oktober");
    expect(pageNote()).toContain("ruleset pp20-dasbor");
    expect(pageNote()).toContain("15 Januari 2026");
    expect(sheetNote()).toBe("");
    expect(dialog()?.textContent).toContain("Memuat jejak bulan.");

    november.resolve(
      cuplikan("2026-11", {
        ruleset_id: "pp20-bulan-november",
        effective_date: "2026-09-26",
        input_hash: HASH_NOV,
        usaha_omzet_idr: 0,
        tax_0_5_pct_idr: 0,
        sisa_bayar_idr: 0,
      }),
    );
    await tungguFrame();

    expect(bidang("input_hash")).toBe(HASH_NOV);
    expect(bidang("ruleset_id")).toBe("pp20-bulan-november");
    expect(bidang("month")).toBe("Nov 2026");
    expect(sheetNote()).toContain("ruleset pp20-bulan-november");
    expect(sheetNote()).toContain("26 September 2026");
    expect(pageNote()).toContain("ruleset pp20-dasbor");
    expect(pageNote()).toContain("15 Januari 2026");
    expect(pageNote()).not.toContain("pp20-bulan-november");
    expect(pageNote()).not.toContain("26 September 2026");
    expect(document.body.textContent).not.toContain(HASH_LAMA);
    expect(document.body.textContent).not.toContain("pp20-bulan-oktober");

    const susulan = tertunda<MonthSnapshot>();
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith("/2026-10")) return susulan.promise;
      return Promise.reject(new Error(path));
    });
    await bukaJejak(wrapper, "2026-10");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await tungguFrame();
    susulan.resolve(
      cuplikan("2026-10", {
        ruleset_id: "pp20-terlambat",
        effective_date: "2026-04-02",
        input_hash: HASH_LAMA,
      }),
    );
    await tungguFrame();

    expect(dialog()).toBeNull();
    expect(document.body.textContent).not.toContain(HASH_LAMA);
    expect(document.body.textContent).not.toContain("pp20-terlambat");
    expect(pageNote()).toContain("ruleset pp20-dasbor");
    expect(pageNote()).toContain("15 Januari 2026");
    expect(pageNote()).not.toContain("pp20-bulan-november");
    expect(pageNote()).not.toContain("2 April 2026");
  });

  it.each([
    [
      "scheme_ineligible",
      "Tidak memenuhi syarat",
      "Fasilitas PPh Final 0,5% tidak berlaku (peredaran bruto tahun lalu melebihi Rp 4,8 miliar).",
    ],
    [
      "unverifiable",
      "Belum dapat diperiksa",
      "Data omzet tahun lalu belum lengkap, sehingga batas kelayakan belum dapat diperiksa.",
    ],
  ])(
    "shows 'Tidak dihitung di sini' and the snapshot reason when %s",
    async (status, labelStatus, annotation) => {
      apiMock.mockResolvedValue(
        cuplikan("2026-10", {
          scheme_eligibility_status: status,
          tax_0_5_pct_idr: 0,
          sisa_bayar_idr: 0,
          annotation,
        }),
      );
      const { wrapper } = await renderDasbor(bulanTahun2026(), { lampirkan: true });
      await bukaJejak(wrapper, "2026-10");

      expect(bidang("scheme_eligibility_status")).toBe(labelStatus);
      expect(bidang("tax_0_5_pct_idr")).toBe("Tidak dihitung di sini");
      expect(bidang("sisa_bayar_idr")).toBe("Tidak dihitung di sini");
      expect(bidang("annotation")).toBe(annotation);
    },
  );

  it("is keyboard-reachable, moves focus into the sheet, and returns focus on close", async () => {
    apiMock.mockResolvedValue(cuplikan("2026-10"));
    const { wrapper } = await renderDasbor(bulanTahun2026(), { lampirkan: true });
    const tombol = wrapper.get("[data-month='2026-10']");

    expect(tombol.element.tagName).toBe("BUTTON");
    expect((tombol.element as HTMLButtonElement).disabled).toBe(false);
    expect(tombol.element.tabIndex).toBeGreaterThanOrEqual(0);
    (tombol.element as HTMLButtonElement).focus();
    expect(document.activeElement).toBe(tombol.element);

    await tombol.trigger("keydown", { key: "Enter" });
    await tombol.trigger("click");
    await tungguFrame();

    const terbuka = dialog();
    expect(terbuka).not.toBeNull();
    expect(terbuka?.contains(document.activeElement)).toBe(true);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await tungguFrame();

    expect(dialog()).toBeNull();
    expect(document.activeElement).toBe(tombol.element);
  });

  it("keeps the full hash and ruleset exposed at a narrow viewport", async () => {
    // Unit-level only: happy-dom has no browser layout tool in this session.
    sematkanSempit();
    expect(window.innerWidth).toBe(390);
    apiMock.mockResolvedValue(cuplikan("2026-10", { ruleset_id: "ruleset-sempit" }));
    const { wrapper } = await renderDasbor(bulanTahun2026(), { lampirkan: true });
    await bukaJejak(wrapper, "2026-10");

    const hash = document.body.querySelector<HTMLElement>("[data-field='input_hash']");
    const ruleset = document.body.querySelector<HTMLElement>("[data-field='ruleset_id']");
    expect(hash).not.toBeNull();
    expect(ruleset).not.toBeNull();
    expect(hash?.textContent?.trim()).toBe(HASH_OKT);
    expect(hash?.textContent).not.toContain("…");
    expect(ruleset?.textContent?.trim()).toBe("ruleset-sempit");
    expect(dialog()?.contains(hash ?? null)).toBe(true);
    expect(dialog()?.contains(ruleset ?? null)).toBe(true);

    const gayaHash = window.getComputedStyle(hash as HTMLElement);
    const gayaRuleset = window.getComputedStyle(ruleset as HTMLElement);
    expect(gayaHash.display).not.toBe("none");
    expect(gayaRuleset.display).not.toBe("none");
    expect(gayaHash.visibility).not.toBe("hidden");
    expect(gayaRuleset.visibility).not.toBe("hidden");
    expect(gayaHash.textOverflow).not.toBe("ellipsis");
    expect(gayaHash.whiteSpace).not.toBe("nowrap");
    expect(hash?.classList.contains("hash")).toBe(true);
  });
});
