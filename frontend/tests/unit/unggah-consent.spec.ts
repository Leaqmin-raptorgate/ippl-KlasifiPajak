/**
 * A receipt chosen before consent stays selected.
 * Ticking the box uploads that same file.
 */
import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { ApiFailure } from "@/lib/api";
import KuotaPage from "@/pages/KuotaPage.vue";
import TransaksiBaruPage from "@/pages/TransaksiBaruPage.vue";
import { useKuotaStore } from "@/stores/kuota";
import { useProfilStore } from "@/stores/profil";
import { useSessionStore } from "@/stores/session";
import { useTransaksiStore } from "@/stores/transaksi";

const PAID = {
  subscription_tier: "berbayar",
  paid_flag: true,
  valid_until_utc: null,
  valid_until_local: null,
  available_plans: [],
};

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
    useKuotaStore().status = PAID;
    session.user = { user_id: "u", email: "a@b.test", username: "a", ai_consent_at: null };

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

    session.user = {
      user_id: "u",
      email: "a@b.test",
      username: "a",
      ai_consent_at: "2026-11-01T00:00:00Z",
    };
    await flushPromises();

    expect(upload).toHaveBeenCalledOnce();
    const chosen = upload.mock.calls[0]?.[0];
    expect(chosen).toBeInstanceOf(File);
    expect(chosen?.name).toBe(file.name);
    expect(chosen?.type).toBe(file.type);
    expect(chosen?.size).toBe(file.size);
  });

  it("never confirms a previous upload after consent is withdrawn and another file is picked (R18-W4)", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    vi.spyOn(useProfilStore(), "muat").mockResolvedValue(undefined);
    vi.spyOn(useKuotaStore(), "muat").mockResolvedValue(undefined);
    useKuotaStore().status = PAID;
    const store = useTransaksiStore();
    const upload = vi.spyOn(store, "unggahStruk").mockResolvedValue({
      image_id: "img-A",
      candidate_fields: {},
    });
    const confirm = vi.spyOn(store, "konfirmasiStruk");
    const create = vi.spyOn(store, "buat").mockResolvedValue({ id: "tx-1" } as never);
    const session = useSessionStore();
    session.user = {
      user_id: "u",
      email: "a@b.test",
      username: "a",
      ai_consent_at: "2026-11-01T00:00:00Z",
    };

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

    async function pick(file: File) {
      const realCreate = document.createElement.bind(document);
      const input = realCreate("input");
      const spy = vi
        .spyOn(document, "createElement")
        .mockImplementation(((tag: string) =>
          tag === "input" ? input : realCreate(tag)) as typeof document.createElement);
      await wrapper.get(".drop").trigger("click");
      spy.mockRestore();
      Object.defineProperty(input, "files", { configurable: true, value: [file] });
      input.onchange?.(new Event("change"));
      await flushPromises();
    }

    await pick(new File(["a"], "a.jpg", { type: "image/jpeg" }));
    expect(upload).toHaveBeenCalledTimes(1);

    session.user = { ...session.user!, ai_consent_at: null };
    await pick(new File(["b"], "b.jpg", { type: "image/jpeg" }));
    expect(upload).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("Persetujuan pemrosesan AI diperlukan");

    await wrapper.get("#tanggal").setValue("2026-11-05");
    await wrapper.get("#klien").setValue("PT Contoh");
    await wrapper.get("#nominal").setValue("1000000");
    await wrapper.get("#dipotong").setValue("0");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(confirm).not.toHaveBeenCalled();
    expect(create).toHaveBeenCalledOnce();
  });

  it("explains inline that a free account cannot upload and does not redirect (R18-W5)", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    vi.spyOn(useProfilStore(), "muat").mockResolvedValue(undefined);
    vi.spyOn(useKuotaStore(), "muat").mockResolvedValue(undefined);
    const upload = vi.spyOn(useTransaksiStore(), "unggahStruk");
    useSessionStore().user = {
      user_id: "u",
      email: "a@b.test",
      username: "a",
      ai_consent_at: "2026-11-01T00:00:00Z",
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: TransaksiBaruPage },
        { path: "/kuota", component: { template: "<div />" } },
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
    const spy = vi
      .spyOn(document, "createElement")
      .mockImplementation(((tag: string) =>
        tag === "input" ? input : realCreate(tag)) as typeof document.createElement);
    await wrapper.get(".drop").trigger("click");
    spy.mockRestore();
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [new File(["a"], "a.jpg", { type: "image/jpeg" })],
    });
    input.onchange?.(new Event("change"));
    await flushPromises();

    expect(upload).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("hanya untuk akun berbayar aktif");
    expect(router.currentRoute.value.path).toBe("/");
  });

  it("links a blocked free-account upload to the paid-plan notice", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    vi.spyOn(useProfilStore(), "muat").mockResolvedValue(undefined);
    vi.spyOn(useKuotaStore(), "muat").mockResolvedValue(undefined);
    const upload = vi.spyOn(useTransaksiStore(), "unggahStruk");
    useSessionStore().user = {
      user_id: "u",
      email: "a@b.test",
      username: "a",
      ai_consent_at: "2026-11-01T00:00:00Z",
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: TransaksiBaruPage },
        { path: "/kuota", name: "kuota", component: KuotaPage },
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
    const spy = vi
      .spyOn(document, "createElement")
      .mockImplementation(((tag: string) =>
        tag === "input" ? input : realCreate(tag)) as typeof document.createElement);
    await wrapper.get(".drop").trigger("click");
    spy.mockRestore();
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [new File(["a"], "a.jpg", { type: "image/jpeg" })],
    });
    input.onchange?.(new Event("change"));
    await flushPromises();

    expect(upload).not.toHaveBeenCalled();
    const galat = wrapper.get(".kunci");
    expect(galat.attributes("role")).toBe("alert");
    expect(galat.isVisible()).toBe(true);
    expect(galat.text().replace(/\s+/g, " ").trim()).toBe(
      "Unggah struk hanya untuk akun berbayar aktif. Isi transaksi secara manual, atau lihat paket di halaman Kuota.",
    );
    const href = galat.get("a").attributes("href");
    expect(href).toBe("/kuota?alasan=ocr_berbayar");

    await router.push(href!);
    const kuota = mount(KuotaPage, {
      global: { plugins: [pinia, router], stubs: { AppIcon: true } },
    });
    await flushPromises();
    expect(kuota.get(".alasan-notice").text()).toContain(
      "Unggah struk hanya untuk akun berbayar aktif",
    );
    kuota.unmount();
  });

  it("offers the upgrade link and refreshes quotas when server rejects OCR for inactive plan", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    vi.spyOn(useProfilStore(), "muat").mockResolvedValue(undefined);
    const kuotaStore = useKuotaStore();
    kuotaStore.status = PAID;
    const muatKuota = vi.spyOn(kuotaStore, "muat").mockResolvedValue(undefined);
    const upload = vi
      .spyOn(useTransaksiStore(), "unggahStruk")
      .mockRejectedValue(
        new ApiFailure(403, "PAID_SUBSCRIPTION_REQUIRED", "Langganan berbayar sudah berakhir."),
      );
    useSessionStore().user = {
      user_id: "u",
      email: "a@b.test",
      username: "a",
      ai_consent_at: "2026-11-01T00:00:00Z",
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: TransaksiBaruPage },
        { path: "/kuota", name: "kuota", component: KuotaPage },
        { path: "/profil", component: { template: "<div />" } },
      ],
    });
    await router.push("/");
    await router.isReady();
    const wrapper = mount(TransaksiBaruPage, {
      global: { plugins: [pinia, router], stubs: { AppIcon: true } },
    });
    await flushPromises();
    muatKuota.mockClear();

    const realCreate = document.createElement.bind(document);
    const input = realCreate("input");
    const spy = vi
      .spyOn(document, "createElement")
      .mockImplementation(((tag: string) =>
        tag === "input" ? input : realCreate(tag)) as typeof document.createElement);
    await wrapper.get(".drop").trigger("click");
    spy.mockRestore();
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [new File(["a"], "a.jpg", { type: "image/jpeg" })],
    });
    input.onchange?.(new Event("change"));
    await flushPromises();

    expect(upload).toHaveBeenCalledOnce();
    expect(muatKuota).toHaveBeenCalledWith(true);
    const galat = wrapper.get(".kunci");
    expect(galat.attributes("role")).toBe("alert");
    expect(galat.get("a").attributes("href")).toBe("/kuota?alasan=ocr_berbayar");
  });

  it("keeps the OCR upgrade link visible when tax profile is missing", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const profil = useProfilStore();
    profil.belumAda = true;
    vi.spyOn(profil, "muat").mockResolvedValue(undefined);
    vi.spyOn(useKuotaStore(), "muat").mockResolvedValue(undefined);
    const upload = vi.spyOn(useTransaksiStore(), "unggahStruk");
    useSessionStore().user = {
      user_id: "u",
      email: "a@b.test",
      username: "a",
      ai_consent_at: "2026-11-01T00:00:00Z",
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: TransaksiBaruPage },
        { path: "/kuota", name: "kuota", component: KuotaPage },
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
    const spy = vi
      .spyOn(document, "createElement")
      .mockImplementation(((tag: string) =>
        tag === "input" ? input : realCreate(tag)) as typeof document.createElement);
    await wrapper.get(".drop").trigger("click");
    spy.mockRestore();
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [new File(["a"], "a.jpg", { type: "image/jpeg" })],
    });
    input.onchange?.(new Event("change"));
    await flushPromises();

    expect(upload).not.toHaveBeenCalled();
    expect(wrapper.find(".peringatan-profil").exists()).toBe(true);
    const galat = wrapper.get(".kunci");
    expect(galat.isVisible()).toBe(true);
    expect(galat.get("a").attributes("href")).toBe("/kuota?alasan=ocr_berbayar");
    const submit = wrapper.get("button[type='submit']");
    expect((submit.element as HTMLButtonElement).disabled).toBe(true);
  });
});
