/** Subscription purchase on the Kuota page: order, redirect, errors, history. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { ApiFailure } from "@/lib/api";
import KuotaPage from "@/pages/KuotaPage.vue";
import { useKuotaStore } from "@/stores/kuota";

const apiMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: apiMock,
}));

const QUOTAS = {
  month_key: "2026-11",
  timezone: "Asia/Jakarta",
  reset_timestamp_utc: "2026-11-30T17:00:00Z",
  ai_classification: { used: 1, limit: 10, status: "active" },
  assistant_chat: { used: 2, limit: 15, status: "active" },
};
const STATUS = {
  subscription_tier: "gratis",
  paid_flag: false,
  valid_until_utc: null,
  valid_until_local: null,
  available_plans: [{ plan_id: "monthly_25k", duration_days: 30, price_idr: 25000 }],
};
const PENDING = {
  order_id: "ord_1",
  plan_id: "monthly_25k",
  amount_idr: 25000,
  status: "pending",
  payment_url: "https://gateway.example.com/pay/ord_1",
};

let orders: unknown[] = [];
let post: (() => Promise<unknown>) | null = null;

function route(path: string, init?: RequestInit): Promise<unknown> {
  if (path === "/quotas") return Promise.resolve(QUOTAS);
  if (path === "/subscriptions/status") return Promise.resolve(STATUS);
  if (path === "/subscriptions/orders" && init?.method === "POST") return post!();
  if (path === "/subscriptions/orders") return Promise.resolve({ items: orders });
  return Promise.reject(new Error(`unexpected ${path}`));
}

const posts = () => apiMock.mock.calls.filter(([, init]) => init?.method === "POST");

async function pasang(path = "/kuota") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/kuota", name: "kuota", component: KuotaPage },
      { path: "/langganan/kembali", name: "langganan-kembali", component: KuotaPage },
    ],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(KuotaPage, { global: { plugins: [pinia, router] } });
  await flushPromises();
  return wrapper;
}

describe("KuotaPage subscription purchase", () => {
  const assign = vi.fn();

  beforeEach(() => {
    orders = [];
    post = null;
    assign.mockReset();
    apiMock.mockReset();
    apiMock.mockImplementation(route);
    vi.stubGlobal("location", { ...window.location, assign });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates one order and redirects to payment_url", async () => {
    post = () => Promise.resolve(PENDING);
    const wrapper = await pasang();
    await wrapper.get(".plan-cta button").trigger("click");
    await flushPromises();
    expect(posts()).toHaveLength(1);
    expect(JSON.parse(posts()[0][1].body)).toEqual({ plan_id: "monthly_25k" });
    expect(assign).toHaveBeenCalledWith(PENDING.payment_url);
  });

  it("shows the 503 message inline and does not redirect", async () => {
    const pesan = "Layanan pembayaran belum tersedia. Coba lagi nanti.";
    post = () => Promise.reject(new ApiFailure(503, "PAYMENT_GATEWAY_UNAVAILABLE", pesan));
    const wrapper = await pasang();
    await wrapper.get(".plan-cta button").trigger("click");
    await flushPromises();
    expect(wrapper.get("[role=alert]").text()).toBe(pesan);
    expect(assign).not.toHaveBeenCalled();
  });

  it("explains an order that is no longer pending and re-reads the list", async () => {
    post = () => {
      orders = [{ ...PENDING, status: "settlement", payment_url: undefined }];
      return Promise.resolve({ ...PENDING, status: "settlement", payment_url: undefined });
    };
    const wrapper = await pasang();
    await wrapper.get(".plan-cta button").trigger("click");
    await flushPromises();
    expect(assign).not.toHaveBeenCalled();
    expect(wrapper.get("[role=alert]").text()).toContain("tidak menunggu pembayaran");
    expect(wrapper.text()).toContain("Lunas");
  });

  it("creates one order when two submits overlap", async () => {
    let release: (order: unknown) => void = () => {};
    post = () => new Promise((resolve) => (release = resolve));
    const wrapper = await pasang();
    const button = wrapper.get(".plan-cta button");
    const first = button.trigger("click");
    const second = button.trigger("click");
    await flushPromises();
    expect(posts()).toHaveLength(1);
    expect(button.attributes("disabled")).toBeDefined();
    // The store also joins a call that bypasses the disabled button.
    const kuota = useKuotaStore();
    void kuota.buatPesanan().catch(() => {});
    expect(posts()).toHaveLength(1);

    release(PENDING);
    await Promise.all([first, second]);
    await flushPromises();
    expect(assign).toHaveBeenCalledTimes(1);
    expect(button.attributes("disabled")).toBeDefined();
  });

  it("keeps the button disabled after a successful redirect", async () => {
    post = () => Promise.resolve(PENDING);
    const wrapper = await pasang();
    const button = wrapper.get(".plan-cta button");
    await button.trigger("click");
    await flushPromises();
    expect(assign).toHaveBeenCalledTimes(1);
    expect(button.attributes("disabled")).toBeDefined();
    await button.trigger("click");
    await flushPromises();
    expect(posts()).toHaveLength(1);
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it("says the link is not ready for a pending order without payment_url", async () => {
    post = () => Promise.resolve({ ...PENDING, payment_url: undefined });
    const wrapper = await pasang();
    await wrapper.get(".plan-cta button").trigger("click");
    await flushPromises();
    expect(assign).not.toHaveBeenCalled();
    const teks = wrapper.get("[role=alert]").text();
    expect(teks).toContain("Tautan bayar belum siap");
    expect(teks).not.toContain("tidak menunggu pembayaran");
    expect(wrapper.get(".plan-cta button").attributes("disabled")).toBeUndefined();
  });

  it("renders the order list on the return route", async () => {
    orders = [
      { ...PENDING, order_id: "ord_2", status: "settlement", payment_url: undefined },
      { ...PENDING, order_id: "ord_1", status: "expire", payment_url: undefined },
    ];
    const wrapper = await pasang("/langganan/kembali");
    const text = wrapper.get(".fitur").text();
    expect(text).toContain("ord_2");
    expect(text).toContain("Lunas · Rp");
    expect(text).toContain("ord_1");
    expect(text).toContain("Kedaluwarsa");
    expect(wrapper.text()).toContain("Status dibaca ulang");
  });
});
