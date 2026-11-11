/**
 * Session store hydrates AI consent from GET /auth/me (FR-27).
 * A non-null ai_consent_at means consented; null means not.
 * HTTP is mocked; no network.
 */
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

import { useSessionStore } from "@/stores/session";

const STAMP = "2026-11-08T09:14:33Z";

function me(aiConsentAt: string | null) {
  return {
    user_id: "usr_consent",
    email: "consent@example.test",
    username: "consentuser",
    ai_consent_at: aiConsentAt,
  };
}

describe("session store AI consent from /auth/me", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    apiMock.mockReset();
  });

  it("treats a non-null ai_consent_at as consented after muat()", async () => {
    apiMock.mockResolvedValueOnce(me(STAMP));
    const session = useSessionStore();

    expect(session.persetujuanAi).toBe(false);
    await session.muat();

    expect(apiMock.mock.calls.map((call) => call[0])).toEqual(["/auth/me"]);
    expect(session.persetujuanAi).toBe(true);
    expect(session.user?.ai_consent_at).toBe(STAMP);
  });

  it("treats a null ai_consent_at as not consented after muat()", async () => {
    apiMock.mockResolvedValueOnce(me(null));
    const session = useSessionStore();

    await session.muat();

    expect(apiMock.mock.calls.map((call) => call[0])).toEqual(["/auth/me"]);
    expect(session.persetujuanAi).toBe(false);
    expect(session.user?.ai_consent_at).toBeNull();
  });

  it("reloads a non-null ai_consent_at as consented after login", async () => {
    apiMock.mockResolvedValueOnce({ user_id: "usr_consent", expires_at: STAMP, token: null });
    apiMock.mockResolvedValueOnce(me(STAMP));
    const session = useSessionStore();

    await session.masuk("consent@example.test", "PasswordMinimal10");

    expect(apiMock.mock.calls.map((call) => call[0])).toEqual(["/auth/login", "/auth/me"]);
    expect(session.persetujuanAi).toBe(true);
    expect(session.user?.ai_consent_at).toBe(STAMP);
  });

  it("reloads a null ai_consent_at as not consented after login", async () => {
    apiMock.mockResolvedValueOnce({ user_id: "usr_consent", expires_at: STAMP, token: null });
    apiMock.mockResolvedValueOnce(me(null));
    const session = useSessionStore();
    session.user = {
      user_id: "u",
      email: "a@b.test",
      username: "a",
      ai_consent_at: "2026-11-01T00:00:00Z",
    };

    await session.masuk("consent@example.test", "PasswordMinimal10");

    expect(apiMock.mock.calls.map((call) => call[0])).toEqual(["/auth/login", "/auth/me"]);
    expect(session.persetujuanAi).toBe(false);
    expect(session.user?.ai_consent_at).toBeNull();
  });
});
