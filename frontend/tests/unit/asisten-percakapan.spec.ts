/** Assistant page: the conversation keeps every exchange of this visit, and can be cleared. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { ApiFailure } from "@/lib/api";
import AsistenPage from "@/pages/AsistenPage.vue";
import { useSessionStore } from "@/stores/session";

const apiMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: apiMock,
}));

const QUOTAS = {
  month_key: "2026-11",
  timezone: "Asia/Jakarta",
  reset_timestamp_utc: "2026-11-30T17:00:00Z",
  ai_classification: { used: 0, limit: 10, status: "active" },
  assistant_chat: { used: 1, limit: 15, status: "active" },
};

const CONSENTED_USER = {
  user_id: "usr_chat",
  email: "chat@example.test",
  username: "demo",
  ai_consent_at: "2026-11-08T09:14:33Z",
};

/** The answers the mocked assistant returns, in order. */
let balasan: Array<() => Promise<unknown>> = [];

function route(path: string): Promise<unknown> {
  if (path === "/quotas") return Promise.resolve(QUOTAS);
  if (path === "/assistant/query") {
    const next = balasan.shift();
    return next ? next() : Promise.reject(new Error("no reply queued"));
  }
  return Promise.reject(new Error(`unexpected ${path}`));
}

function jawab(teks: string, sisaKuota: number) {
  return () =>
    Promise.resolve({ answer: teks, citations: ["Pasal 17 ayat 2"], quota_remaining: sisaKuota });
}

const montados: VueWrapper[] = [];

function pasang() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.user = CONSENTED_USER as never;
  const wrapper = mount(AsistenPage, {
    attachTo: document.body,
    global: {
      plugins: [pinia],
      stubs: { AiConsentNote: true, WorkpaperNote: true },
    },
  });
  montados.push(wrapper);
  return wrapper;
}

async function tanya(wrapper: VueWrapper, teks: string) {
  await wrapper.get("textarea").setValue(teks);
  await wrapper.get("button.kirim").trigger("click");
  await flushPromises();
}

describe("asisten conversation", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    apiMock.mockReset();
    apiMock.mockImplementation((path: string) => route(path));
    balasan = [];
  });

  afterEach(() => {
    while (montados.length) montados.pop()?.unmount();
  });

  it("keeps every exchange of the visit, oldest first", async () => {
    balasan = [jawab("Jawaban pertama", 14), jawab("Jawaban kedua", 13)];
    const wrapper = pasang();
    await flushPromises();

    await tanya(wrapper, "Pertanyaan pertama");
    await tanya(wrapper, "Pertanyaan kedua");

    const teks = wrapper.findAll(".pesan-isi").map((p) => p.text());
    expect(teks).toEqual([
      "Pertanyaan pertama",
      "Jawaban pertama",
      "Pertanyaan kedua",
      "Jawaban kedua",
    ]);
    expect(wrapper.findAll(".pesan-anda")).toHaveLength(2);
    expect(wrapper.findAll(".pesan-asisten")).toHaveLength(2);
    expect(wrapper.text()).toContain("Pasal 17 ayat 2");
  });

  it("Hapus percakapan clears the in-memory list and hides itself", async () => {
    balasan = [jawab("Jawaban tunggal", 14)];
    const wrapper = pasang();
    await flushPromises();

    expect(wrapper.text()).not.toContain("Hapus percakapan");
    await tanya(wrapper, "Pertanyaan tunggal");
    expect(wrapper.findAll(".pesan")).toHaveLength(2);

    const hapus = wrapper.findAll("button").find((b) => b.text() === "Hapus percakapan");
    expect(hapus).toBeTruthy();
    await hapus!.trigger("click");
    await flushPromises();

    expect(wrapper.findAll(".pesan")).toHaveLength(0);
    expect(wrapper.find(".kosong").exists()).toBe(true);
    expect(wrapper.text()).not.toContain("Hapus percakapan");
  });

  it("attaches a failed question's error to that question", async () => {
    balasan = [
      jawab("Jawaban pertama", 14),
      () => Promise.reject(new ApiFailure(503, "UNAVAILABLE", "Asisten sedang tidak tersedia.")),
    ];
    const wrapper = pasang();
    await flushPromises();

    await tanya(wrapper, "Pertanyaan pertama");
    await tanya(wrapper, "Pertanyaan gagal");

    const giliranGagal = wrapper.findAll(".pesan-anda").at(1);
    expect(giliranGagal?.text()).toContain("Pertanyaan gagal");
    const notice = wrapper.get(".info-galat[role='alert']");
    expect(notice.text()).toBe("Asisten sedang tidak tersedia.");
    // The notice sits right after the failed question, before anything later.
    const thread = wrapper.get(".thread").element;
    const urutan = Array.from(thread.children);
    const indeksAnda = urutan.indexOf(giliranGagal!.element);
    expect(urutan[indeksAnda + 1]?.textContent?.trim()).toBe("Asisten sedang tidak tersedia.");
  });

  it("disables the send button while the answer is pending", async () => {
    let selesai: (value: unknown) => void = () => undefined;
    balasan = [() => new Promise((resolve) => (selesai = resolve))];
    const wrapper = pasang();
    await flushPromises();

    await wrapper.get("textarea").setValue("Pertanyaan menggantung");
    await wrapper.get("button.kirim").trigger("click");
    await flushPromises();

    expect(wrapper.get("button.kirim").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[role='status']").text()).toContain("Menyusun penjelasan");

    selesai({ answer: "Akhirnya", citations: [], quota_remaining: 14 });
    await flushPromises();
    expect(wrapper.text()).toContain("Akhirnya");
  });
});
