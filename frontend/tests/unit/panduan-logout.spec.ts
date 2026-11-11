/** Logout clears guidance so the next session does not keep it. */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const apiMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: (...args: unknown[]) => apiMock(...args),
  };
});

import { usePanduanStore } from "@/stores/panduan";
import { useSessionStore } from "@/stores/session";

describe("panduan store on logout", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    apiMock.mockReset();
    apiMock.mockResolvedValue({ revoked: true });
  });

  it("clears guidance and its message when the session logs out", async () => {
    const panduan = usePanduanStore();
    panduan.panduan = {
      ruleset_id: "pp20-2026",
      effective_date: "2026-01-01",
      disclaimer: "Bukan SPT resmi.",
      items: [],
    };
    panduan.pesan = "sisa dari sesi tadi";

    await useSessionStore().keluar();

    expect(apiMock).toHaveBeenCalledWith("/auth/logout", { method: "POST" });
    expect(panduan.panduan).toBeNull();
    expect(panduan.pesan).toBe("");
  });
});
