/** The site header's mobile menu is a disclosure: it opens, closes, and follows the route. */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { nextTick } from "vue";
import AppSiteHeader from "@/components/app/AppSiteHeader.vue";

function buatRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div />" } },
      { path: "/dasbor", component: { template: "<div />" } },
      { path: "/transaksi", component: { template: "<div />" } },
      { path: "/transaksi/baru", component: { template: "<div />" } },
      { path: "/asisten", component: { template: "<div />" } },
      { path: "/profil", component: { template: "<div />" } },
      { path: "/kuota", component: { template: "<div />" } },
    ],
  });
}

describe("AppSiteHeader mobile menu", () => {
  let wrapper: VueWrapper;
  let router: ReturnType<typeof buatRouter>;

  beforeEach(async () => {
    setActivePinia(createPinia());
    router = buatRouter();
    await router.push("/dasbor");
    await router.isReady();
    wrapper = mount(AppSiteHeader, {
      attachTo: document.body,
      global: { plugins: [router] },
    });
  });

  afterEach(() => {
    wrapper.unmount();
  });

  it("starts closed, with aria-expanded false and a hidden panel", () => {
    const menu = wrapper.get("button.menu-btn");
    expect(menu.attributes("aria-expanded")).toBe("false");
    expect(menu.attributes("aria-controls")).toBe("menu-utama");
    expect(wrapper.get("#menu-utama").isVisible()).toBe(false);
  });

  it("opens on click and links the button to the panel", async () => {
    const menu = wrapper.get("button.menu-btn");
    await menu.trigger("click");

    expect(menu.attributes("aria-expanded")).toBe("true");
    expect(wrapper.get("#menu-utama").isVisible()).toBe(true);
  });

  it("closes on a second click of the same button", async () => {
    const menu = wrapper.get("button.menu-btn");
    await menu.trigger("click");
    await menu.trigger("click");

    expect(menu.attributes("aria-expanded")).toBe("false");
    expect(wrapper.get("#menu-utama").isVisible()).toBe(false);
  });

  it("closes on Escape and returns focus to the menu button", async () => {
    const menu = wrapper.get("button.menu-btn");
    await menu.trigger("click");

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();

    expect(menu.attributes("aria-expanded")).toBe("false");
    expect(wrapper.get("#menu-utama").isVisible()).toBe(false);
    expect(document.activeElement).toBe(menu.element);
  });

  it("closes when the route changes", async () => {
    const menu = wrapper.get("button.menu-btn");
    await menu.trigger("click");
    expect(menu.attributes("aria-expanded")).toBe("true");

    await router.push("/transaksi");
    await nextTick();

    expect(menu.attributes("aria-expanded")).toBe("false");
    expect(wrapper.get("#menu-utama").isVisible()).toBe(false);
  });

  it("opens the account menu and closes it on Escape", async () => {
    const akun = wrapper.get("button.avatar");
    expect(akun.attributes("aria-expanded")).toBe("false");

    await akun.trigger("click");
    expect(akun.attributes("aria-expanded")).toBe("true");
    expect(wrapper.get("#menu-akun").isVisible()).toBe(true);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();
    expect(akun.attributes("aria-expanded")).toBe("false");
  });

  it("marks the current destination in the header navigation", () => {
    const current = wrapper.findAll("nav.nav a[aria-current='page']");
    expect(current).toHaveLength(1);
    expect(current[0].text()).toBe("Pajak");
  });
});
