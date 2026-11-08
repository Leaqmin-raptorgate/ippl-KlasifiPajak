/** Two overlapping submits of a new transaction call create once. */
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import TransaksiBaruPage from "@/pages/TransaksiBaruPage.vue";
import { useKuotaStore } from "@/stores/kuota";
import { useProfilStore } from "@/stores/profil";
import { useTransaksiStore } from "@/stores/transaksi";

describe("TransaksiBaruPage.simpan", () => {
  it("sends one create when two submits overlap", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const profil = useProfilStore();
    vi.spyOn(profil, "muat").mockResolvedValue(undefined);
    vi.spyOn(useKuotaStore(), "muat").mockResolvedValue(undefined);
    let release: (row: { id: string }) => void = () => {};
    const pending = new Promise<{ id: string }>((resolve) => {
      release = resolve;
    });
    const buat = vi.spyOn(useTransaksiStore(), "buat").mockImplementation(() => pending as never);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: TransaksiBaruPage },
        { path: "/transaksi/:id", component: { template: "<div />" } },
      ],
    });
    await router.push("/");
    await router.isReady();
    const wrapper = mount(TransaksiBaruPage, { global: { plugins: [pinia, router] } });
    await flushPromises();

    await wrapper.get("#klien").setValue("PT Maju Bersama");
    await wrapper.get("#nominal").setValue("125000");
    const form = wrapper.get("form");
    const first = form.trigger("submit");
    const second = form.trigger("submit");
    await flushPromises();
    expect(buat).toHaveBeenCalledTimes(1);

    release({ id: "tx-new" });
    await Promise.all([first, second]);
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/transaksi/tx-new");
  });
});
