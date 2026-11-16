/** Dasbor monthly table: leading empty months fold into one line, and a toggle shows them. */
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Dashboard, MonthSummary } from "@/lib/wire";
import DasborPage from "@/pages/DasborPage.vue";
import { usePajakStore } from "@/stores/pajak";
import { useTransaksiStore } from "@/stores/transaksi";

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

async function renderDasbor(bulan: MonthSummary[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const pajak = usePajakStore();
  pajak.dashboard = {
    metadata: {
      ruleset_id: "test",
      effective_date: "2026-01-01",
      rounding_rule: "floor",
      disclaimer: "workpaper",
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
    routes: [{ path: "/", component: DasborPage }],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(DasborPage, {
    global: {
      plugins: [pinia, router],
      stubs: { AppIcon: true, WorkpaperNote: true, TransactionLedger: true, PanduanPanel: true },
    },
  });
  await flushPromises();
  return wrapper;
}

describe("dasbor monthly table", () => {
  it("folds the leading empty months into one line, and months with data stay", async () => {
    const wrapper = await renderDasbor(bulanTahun2026());
    const baris = wrapper.findAll("tbody tr");

    expect(wrapper.get(".tabel tr.ringkas").text()).toBe("Jan - Sep 2026: belum ada omzet");
    // One folded line, Oct, then Nov and Dec.
    expect(baris).toHaveLength(4);
    expect(wrapper.text()).toContain("Okt 2026");
  });

  it("the toggle expands every month and reports its state", async () => {
    const wrapper = await renderDasbor(bulanTahun2026());
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
    const wrapper = await renderDasbor(bulan);

    expect(wrapper.find(".tabel tr.ringkas").exists()).toBe(false);
    expect(wrapper.findAll("tbody tr")).toHaveLength(12);
  });
});
