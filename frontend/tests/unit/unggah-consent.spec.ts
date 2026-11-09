/**
 * A receipt chosen before consent stays selected.
 * Ticking the box uploads that same file.
 */
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import TransaksiBaruPage from "@/pages/TransaksiBaruPage.vue";
import { useKuotaStore } from "@/stores/kuota";
import { useProfilStore } from "@/stores/profil";
import { useSessionStore } from "@/stores/session";
import { useTransaksiStore } from "@/stores/transaksi";

describe("receipt upload without consent", () => {
  it("keeps the chosen file and uploads it after the box is ticked", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    vi.spyOn(useProfilStore(), "muat").mockResolvedValue(undefined);
    vi.spyOn(useKuotaStore(), "muat").mockResolvedValue(undefined);
    const upload = vi.spyOn(useTransaksiStore(), "unggahStruk").mockResolvedValue({
      image_id: "img-1",
      candidate_fields: {},
    });
    const session = useSessionStore();
    session.persetujuanAi = false;

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: TransaksiBaruPage },
        { path: "/kuota", component: { template: "<div />" } },
        { path: "/transaksi/:id", component: { template: "<div />" } },
        { path: "/profil", component: { template: "<div />" } },
      ],
    });
    await router.push("/");
    await router.isReady();

    const wrapper = mount(TransaksiBaruPage, {
      global: { plugins: [pinia, router], stubs: { AppIcon: true } },
    });
    await flushPromises();

    const realCreate = document.createElement.bind(document);
    const input = realCreate("input");
    const spy = vi.spyOn(document, "createElement").mockImplementation(((tag: string) => {
      if (tag === "input") return input;
      return realCreate(tag);
    }) as typeof document.createElement);
    await wrapper.get(".drop").trigger("click");
    spy.mockRestore();

    const file = new File(["jpeg"], "struk.jpg", { type: "image/jpeg" });
    Object.defineProperty(input, "files", { configurable: true, value: [file] });
    input.onchange?.(new Event("change"));
    await flushPromises();

    expect(upload).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Persetujuan pemrosesan AI diperlukan");

    session.persetujuanAi = true;
    await flushPromises();

    expect(upload).toHaveBeenCalledOnce();
    const chosen = upload.mock.calls[0]?.[0];
    expect(chosen).toBeInstanceOf(File);
    expect(chosen?.name).toBe(file.name);
    expect(chosen?.type).toBe(file.type);
    expect(chosen?.size).toBe(file.size);
  });
});
