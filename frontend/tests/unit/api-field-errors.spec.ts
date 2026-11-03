/**
 * TC-FE-API-01: exercises real `api()` JSON to ApiFailure.fieldErrors mapping.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiFailure, api } from "@/lib/api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api() field_errors parsing", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("422: maps body.field_errors onto ApiFailure.fieldErrors", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: { code: "VALIDATION_ERROR", message: "Periksa isian yang ditandai." },
        field_errors: {
          tx_date: "Tanggal tidak valid",
          amount_idr: "Jumlah wajib diisi",
        },
      }),
    );

    const err = await api("/transactions/tx-1", { method: "PUT", body: "{}" }).catch((e) => e);

    expect(err).toBeInstanceOf(ApiFailure);
    expect(err).toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "Periksa isian yang ditandai.",
      fieldErrors: {
        tx_date: "Tanggal tidak valid",
        amount_idr: "Jumlah wajib diisi",
      },
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("422: absent field_errors yields empty fieldErrors", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: { code: "VALIDATION_ERROR", message: "Periksa isian." },
      }),
    );

    const err = await api("/transactions/tx-1", { method: "PUT", body: "{}" }).catch((e) => e);

    expect(err).toBeInstanceOf(ApiFailure);
    expect(err.fieldErrors).toEqual({});
  });

  it("422: null / non-object field_errors yields empty fieldErrors", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: { code: "VALIDATION_ERROR", message: "Periksa isian." },
        field_errors: null,
      }),
    );

    const err = await api("/transactions/tx-1", { method: "PUT", body: "{}" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiFailure);
    expect(err.fieldErrors).toEqual({});
  });

  it("422: drops non-string field_errors values", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: { code: "VALIDATION_ERROR", message: "Periksa isian." },
        field_errors: {
          tx_date: "Tanggal tidak valid",
          amount_idr: 42,
          nested: { msg: "nope" },
          flag: true,
        },
      }),
    );

    const err = await api("/transactions/tx-1", { method: "PUT", body: "{}" }).catch((e) => e);

    expect(err).toBeInstanceOf(ApiFailure);
    expect(err.fieldErrors).toEqual({ tx_date: "Tanggal tidak valid" });
  });
});
