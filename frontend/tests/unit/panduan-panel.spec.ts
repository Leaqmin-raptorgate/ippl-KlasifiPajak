/** PanduanPanel renders the guidance store and nothing else. */
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import PanduanPanel from "@/components/app/PanduanPanel.vue";
import { usePanduanStore } from "@/stores/panduan";
import type { Guidance } from "@/lib/wire";

function mountPanel(siapkan?: (store: ReturnType<typeof usePanduanStore>) => void) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const store = usePanduanStore();
  siapkan?.(store);
  const wrapper = mount(PanduanPanel, { global: { plugins: [pinia] } });
  return { store, wrapper };
}

const CONTOH: Guidance = {
  ruleset_id: "pp20-2026",
  effective_date: "2026-01-01",
  disclaimer: "Bukan SPT resmi.",
  items: [{ id: "a", text: "Kalimat panduan.", citation: "Pasal 58" }],
};

describe("PanduanPanel", () => {
  it("shows the ruleset, the item, and the disclaimer", () => {
    const { wrapper } = mountPanel((store) => {
      store.panduan = CONTOH;
    });
    expect(wrapper.text()).toContain("Panduan untuk profil Anda");
    expect(wrapper.text()).toContain("pp20-2026");
    expect(wrapper.text()).toContain("Kalimat panduan.");
    expect(wrapper.text()).toContain("Rujukan: Pasal 58");
    expect(wrapper.text()).toContain("Bukan SPT resmi.");
  });

  it("says when this profile has no extra guidance", () => {
    const { wrapper } = mountPanel((store) => {
      store.panduan = { ...CONTOH, items: [] };
    });
    expect(wrapper.text()).toContain("Belum ada panduan tambahan untuk profil dan data saat ini.");
  });

  it("shows the store message when guidance is missing", () => {
    const { wrapper } = mountPanel((store) => {
      store.pesan = "Panduan belum tersedia.";
    });
    expect(wrapper.text()).toContain("Panduan belum tersedia.");
    expect(wrapper.text()).not.toContain("Panduan untuk profil Anda");
  });

  it("renders nothing when the store is empty", () => {
    const { wrapper } = mountPanel();
    expect(wrapper.text()).toBe("");
  });
});
