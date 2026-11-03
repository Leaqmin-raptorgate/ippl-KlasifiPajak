/**
 * Cookie client for `/api/v1`.
 *
 * The browser never sends `X-Client-Type` and never stores a JWT. A 401 is
 * reported to the session handler; the caller still receives the error.
 *
 * Error envelope: API Spec v1.3.1 §2.5 —
 * `{ "error": { "code", "message" }, "field_errors"?: { [field]: string } }`.
 * `field_errors` (and `error.details` when shaped the same way) map to
 * per-field form errors. Unknown shapes fall back to a generic message.
 */

export class ApiFailure extends Error {
  status: number;
  code: string;
  fieldErrors: Record<string, string>;

  constructor(status: number, code: string, message: string, fieldErrors?: Record<string, string>) {
    super(message);
    this.name = "ApiFailure";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors ?? {};
  }
}

type LossHandler = (code: string) => void;

let onLoss: LossHandler | null = null;

export function bindSessionLoss(handler: LossHandler) {
  onLoss = handler;
}

function base(): string {
  const root = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";
  return `${root}/api/v1`;
}

export function isUnavailable(error: unknown): boolean {
  return error instanceof ApiFailure && error.code === "ROUTE_UNAVAILABLE";
}

/** True when fetch was aborted (unmount / AbortController). */
export function isAbortError(error: unknown): boolean {
  if (error instanceof DOMException && error.name === "AbortError") return true;
  if (error instanceof Error && error.name === "AbortError") return true;
  return false;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${base()}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 204) return undefined as T;
  const payload = await readJson(response);
  if (!response.ok) throw fail(response.status, payload);
  return payload as T;
}

export async function apiBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const response = await fetch(`${base()}${path}`, {
    ...init,
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await readJson(response);
    throw fail(response.status, payload);
  }
  return response.blob();
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function fail(status: number, payload: unknown): ApiFailure {
  const body = asRecord(payload);
  const error = asRecord(body?.error);
  const code =
    typeof error?.code === "string"
      ? error.code
      : status === 404
        ? "ROUTE_UNAVAILABLE"
        : "REQUEST_FAILED";
  const message =
    typeof error?.message === "string"
      ? error.message
      : "Permintaan gagal. Muat ulang, lalu coba lagi.";
  const fieldErrors = collectFieldErrors(body, error);
  if (status === 401) onLoss?.(code);
  return new ApiFailure(status, code, message, fieldErrors);
}

/**
 * API Spec v1.3.1 §2.5: `field_errors` is an object of field → Indonesian text.
 * Also accept `error.details` when it has the same shape. Fallback: FastAPI
 * `detail: [{ loc, msg }]` arrays become a best-effort map; unknown entries
 * are skipped so the caller can show the generic `message`.
 */
function collectFieldErrors(
  body: Record<string, unknown> | null,
  error: Record<string, unknown> | null,
): Record<string, string> {
  const fromSpec =
    asStringMap(body?.field_errors) ||
    asStringMap(error?.field_errors) ||
    asStringMap(error?.details) ||
    asStringMap(body?.details);
  if (Object.keys(fromSpec).length > 0) return fromSpec;

  const detail = body?.detail;
  if (!Array.isArray(detail)) return {};
  const out: Record<string, string> = {};
  for (const item of detail) {
    const row = asRecord(item);
    if (!row) continue;
    const loc = Array.isArray(row.loc)
      ? row.loc.filter((part) => part !== "body" && typeof part === "string").join(".")
      : "";
    const msg = typeof row.msg === "string" ? row.msg : "";
    if (loc && msg) out[loc] = msg;
  }
  return out;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function asStringMap(value: unknown): Record<string, string> {
  const record = asRecord(value);
  if (!record) return {};
  const out: Record<string, string> = {};
  for (const [key, item] of Object.entries(record)) {
    if (typeof item === "string" && item.length > 0) out[key] = item;
  }
  return out;
}
