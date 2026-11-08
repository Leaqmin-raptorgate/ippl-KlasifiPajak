/** FR-03 and FR-48: onboarding keeps unknown answers and prior-year blanks. */
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import type { Profile } from "@/lib/wire";
import ProfilPage from "@/pages/ProfilPage.vue";
import { useKuotaStore } from "@/stores/kuota";
import { useProfilStore } from "@/stores/profil";

async function mountProfile(existing = false, newTaxpayer: boolean | null = false) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const profil = useProfilStore();
  if (existing) {
    profil.profile = {
      id: "profile-1",
      user_id: "user-1",
      tax_year: 2026,
      version: 1,
      name: "Contoh",
      entity_type: "orang_pribadi",
      nib_status: "no_nib",
      nib_masked: null,
      kbli_code: "",
      business_description: "",
      marital_status: "unknown",
      spouse_tax_status: "unknown",
      spouse_aggregation_active: false,
      is_new_taxpayer_current_year: newTaxpayer,
      spouse_current_usaha_idr: 0,
      spouse_current_pekerjaan_bebas_idr: 0,
      spouse_current_already_final_idr: 0,
      prior_user_usaha_idr: null,
      prior_user_pekerjaan_bebas_idr: null,
      prior_user_already_final_idr: null,
      prior_spouse_usaha_idr: null,
      prior_spouse_pekerjaan_bebas_idr: null,
      prior_spouse_already_final_idr: null,
      audit_trail: [],
    } as unknown as Profile;
  }
  vi.spyOn(profil, "muat").mockResolvedValue(undefined);
  vi.spyOn(profil, "muatSesi").mockResolvedValue(undefined);
  const save = vi.spyOn(profil, "simpan").mockResolvedValue(undefined);
  vi.spyOn(useKuotaStore(), "muat").mockResolvedValue(undefined);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: ProfilPage }],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(ProfilPage, {
    global: {
      plugins: [pinia, router],
      stubs: { AppIcon: true, WorkpaperNote: true, Teleport: true },
    },
  });
  await flushPromises();
  const edit = wrapper
    .findAll("button")
    .find((button) => /^(Ubah|Buat profil)$/.test(button.text()));
  expect(edit).toBeTruthy();
  await edit!.trigger("click");
  return { wrapper, save };
}

function spouseSelect(wrapper: Awaited<ReturnType<typeof mountProfile>>["wrapper"]) {
  return wrapper.findAll("select").find((select) => {
    const values = select.findAll("option").map((option) => option.attributes("value"));
    return ["unmarried", "separate", "joint", "unknown"].every((value) => values.includes(value));
  });
}

describe("FR-48 spouse and prior-year answers", () => {
  it.each([
    ["unmarried", false],
    ["separate", true],
    ["joint", false],
    ["unknown", false],
  ])("saves spouse answer %s and its aggregation %s", async (status, aggregation) => {
    const { wrapper, save } = await mountProfile();
    const select = spouseSelect(wrapper);
    expect(select).toBeTruthy();
    await select!.setValue(status);
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Simpan")!
      .trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledOnce();
    const payload = save.mock.calls[0]![0] as unknown as Record<string, unknown>;
    expect(payload.spouse_tax_status).toBe(status);
    expect(payload.spouse_aggregation_active).toBe(aggregation);
    for (const owner of ["user", "spouse"]) {
      for (const category of ["usaha", "pekerjaan_bebas", "already_final"]) {
        expect(payload[`prior_${owner}_${category}_idr`]).toBeNull();
      }
    }
  });

  it("keeps existing blank prior-year values null when editing", async () => {
    const { wrapper, save } = await mountProfile(true);
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Simpan")!
      .trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledOnce();
    const payload = save.mock.calls[0]![0] as unknown as Record<string, unknown>;
    expect(payload.spouse_tax_status).toBe("unknown");
    expect(payload.is_new_taxpayer_current_year).toBe(false);
    for (const owner of ["user", "spouse"]) {
      for (const category of ["usaha", "pekerjaan_bebas", "already_final"]) {
        expect(payload[`prior_${owner}_${category}_idr`]).toBeNull();
      }
    }
  });

  it("shows error and prevents save when rupiah input contains invalid characters", async () => {
    const { wrapper, save } = await mountProfile();
    const input = wrapper.find("#p-pu");
    expect(input.exists()).toBe(true);
    await input.setValue("bukan-angka");
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Simpan")!
      .trigger("click");
    await flushPromises();
    expect(save).not.toHaveBeenCalled();
    const alert = wrapper.find("[role='alert']");
    expect(alert.exists()).toBe(true);
    expect(alert.text()).toContain("tidak valid");
  });

  it("keeps a loaded unanswered new-taxpayer answer null on save", async () => {
    const { wrapper, save } = await mountProfile(true, null);
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Simpan")!
      .trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledOnce();
    const payload = save.mock.calls[0]![0] as unknown as Record<string, unknown>;
    expect(payload.is_new_taxpayer_current_year).toBeNull();
  });

  it("sends true when the loaded new-taxpayer answer is yes", async () => {
    const { wrapper, save } = await mountProfile(true, true);
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Simpan")!
      .trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledOnce();
    const payload = save.mock.calls[0]![0] as unknown as Record<string, unknown>;
    expect(payload.is_new_taxpayer_current_year).toBe(true);
  });

  it("sends null when a first profile leaves the new-taxpayer answer blank", async () => {
    const { wrapper, save } = await mountProfile(false);
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Simpan")!
      .trigger("click");
    await flushPromises();
    expect(save).toHaveBeenCalledOnce();
    const payload = save.mock.calls[0]![0] as unknown as Record<string, unknown>;
    expect(payload.is_new_taxpayer_current_year).toBeNull();
  });
});
