/** The workspace shell loads quota, profile and dashboard once, and survives a failed profile read. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { ApiFailure } from "@/lib/api";
import AppShell from "@/components/app/AppShell.vue";

const apiMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: apiMock,
}));

const paths = () => apiMock.mock.calls.map(([path]) => String(path));

async function pasang(profileError: ApiFailure) {
  apiMock.mockImplementation((path: string) => {
    if (path.startsWith("/profiles/")) return Promise.reject(profileError);
    return Promise.reject(new ApiFailure(503, "UNAVAILABLE", "Belum tersedia."));
  });
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<p>halaman</p>" } }],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(AppShell, {
    global: {
      plugins: [pinia, router],
      stubs: { AppSidebar: true, AppTopBar: true, AppTabBar: true },
    },
  });
  await flushPromises();
  return wrapper;
}

describe("AppShell first loads", () => {
  afterEach(() => apiMock.mockReset());

  it("still asks for the dashboard when the profile read fails with a server error", async () => {
    const wrapper = await pasang(new ApiFailure(503, "SERVICE_UNAVAILABLE", "Layanan sibuk."));
    expect(paths().some((p) => p.startsWith("/tax/dashboard"))).toBe(true);
    wrapper.unmount();
  });

  it("skips the dashboard when the profile does not exist yet", async () => {
    const wrapper = await pasang(new ApiFailure(404, "PROFILE_NOT_FOUND", "Profil belum ada."));
    expect(paths().some((p) => p.startsWith("/tax/dashboard"))).toBe(false);
    wrapper.unmount();
  });
});
