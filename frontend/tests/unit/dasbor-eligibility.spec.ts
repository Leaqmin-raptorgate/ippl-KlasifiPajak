/** FR-19: eligibility prevents a zero tax figure from appearing as calculated. */
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Dashboard } from "@/lib/wire";
import DasborPage from "@/pages/DasborPage.vue";
import { usePajakStore } from "@/stores/pajak";
import { useTransaksiStore } from "@/stores/transaksi";

async function renderDashboard(
  status: string,
  tweak?: (dashboard: Dashboard) => void,
) {
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
        ytd_usaha_omzet_idr: 0,
        remaining_free_band_idr: 0,
        provisional_omzet_idr: 0,
        split_month: null,
        annotation: "",
      },
      eligibility_prior_year_cap_4_8m: {
        limit_idr: 4_800_000_000,
        combined_prior_year_gross_idr: 0,
        resolution_source: "unverifiable",
        status,
      },
      monitoring_current_year_cap_4_8m: {
        limit_idr: 4_800_000_000,
        ytd_usaha_omzet_idr: 0,
        ytd_pekerjaan_bebas_omzet_idr: 0,
        ytd_already_final_omzet_idr: 0,
        spouse_current_year_usaha_omzet_idr: 0,
        spouse_current_year_pekerjaan_bebas_omzet_idr: 0,
        spouse_current_year_already_final_omzet_idr: 0,
        ytd_combined_gross_idr: 0,
        provisional_usaha_omzet_idr: 0,
        next_year_ineligible: false,
      },
      pasal_58: { spouse_aggregation_active: false, badge_label: "" },
    },
    monthly_summaries: [
      {
        month: "2026-01",
        scheme_eligibility_status: status,
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
      },
    ],
  } as Dashboard;
  tweak?.(pajak.dashboard);
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
      stubs: { AppIcon: true, WorkpaperNote: true, TransactionLedger: true },
    },
  });
  await flushPromises();
  return wrapper;
}

describe("FR-19 dashboard eligibility", () => {
  it.each([
    ["scheme_ineligible", /tidak memenuhi syarat|melampaui|melewati/i],
    ["unverifiable", /belum.*(lengkap|diperiksa)|tidak.*(lengkap|diketahui)/i],
  ])("explains why tax is not calculated for %s", async (status, reason) => {
    const wrapper = await renderDashboard(status);
    expect(wrapper.text().toLowerCase()).toContain("tidak dihitung di sini");
    expect(wrapper.text()).toMatch(reason);
    expect(wrapper.text()).not.toMatch(/pajak\s+(?:Rp\s*)?0\b/i);
  });

  it("renders call to action to profile when status is unverifiable", async () => {
    const wrapper = await renderDashboard("unverifiable");
    expect(wrapper.text()).toContain("Data omzet tahun lalu belum lengkap");
    const cta = wrapper
      .findAllComponents({ name: "AppButton" })
      .find((btn) => btn.props("to") === "/profil");
    expect(cta).toBeTruthy();
  });

  it("hides the workpaper button when the year is unverifiable", async () => {
    const unverifiable = await renderDashboard("unverifiable");
    const eligible = await renderDashboard("scheme_eligible");
    expect(unverifiable.text()).toContain("Cuplikan bulan");
    expect(unverifiable.text()).not.toContain("Unduh workpaper");
    expect(eligible.text()).toContain("Unduh workpaper");
  });

  it("labels scheme_ineligible and unverifiable differently", async () => {
    const ineligible = await renderDashboard("scheme_ineligible");
    const unverifiable = await renderDashboard("unverifiable");
    expect(nilaiKelayakan(ineligible)).toBe("Tidak memenuhi syarat");
    expect(nilaiKelayakan(unverifiable)).toBe("Belum dapat diperiksa");
  });
});

describe("dashboard figures (R18-W1, R18-W6)", () => {
  it("shows the real share of the Rp4,8 M cap, not the warning threshold", async () => {
    const wrapper = await renderDashboard("scheme_eligible", (dashboard) => {
      const now = dashboard.thresholds.monitoring_current_year_cap_4_8m;
      now.ytd_combined_gross_idr = 4_600_000_000;
      now.cap_warning = true;
      now.cap_warning_percent = 80;
    });
    expect(wrapper.text()).toContain("96%");
    expect(wrapper.text()).not.toContain("80% dari batas");
  });

  it("shows a dash and the reason instead of Rp 0 when the prior year is unverifiable", async () => {
    const wrapper = await renderDashboard("unverifiable");
    const hero = wrapper.get(".hero");
    expect(hero.get(".big").text()).toBe("—");
    expect(hero.text()).toContain("Isi peredaran bruto tahun lalu di Profil");
  });

  it("still shows the remaining band when the year is eligible", async () => {
    const wrapper = await renderDashboard("scheme_eligible", (dashboard) => {
      dashboard.thresholds.pita_500_juta.remaining_free_band_idr = 120_000_000;
    });
    expect(wrapper.get(".hero .big").text()).toContain("120.000.000");
  });
});

function nilaiKelayakan(wrapper: Awaited<ReturnType<typeof renderDashboard>>) {
  const card = wrapper.findAll(".stat").find((item) => item.text().includes("Kelayakan skema"));
  return card?.get(".val").text() ?? "";
}
