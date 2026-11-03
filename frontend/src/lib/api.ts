/**
 * Cookie client for `/api/v1`.
 *
 * The browser never sends `X-Client-Type` and never stores a JWT. A 401 is
 * reported to the session handler; the caller still receives the error.
 *
 * Error envelope format:
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
 * Collect field errors from the API response payload.
 * Accepts `field_errors`, `error.details`, or `details` maps, and falls back to
 * FastAPI detail arrays with `{ loc, msg }`.
 */
function collectFieldErrors(
  body: Record<string, unknown> | null,
  error: Record<string, unknown> | null,
): Record<string, string> {
  const fromSpec =
    asStringMapOrNull(body?.field_errors) ??
    asStringMapOrNull(error?.field_errors) ??
    asStringMapOrNull(error?.details) ??
    asStringMapOrNull(body?.details);
  if (fromSpec) return fromSpec;

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

function asStringMapOrNull(value: unknown): Record<string, string> | null {
  const record = asRecord(value);
  if (!record) return null;
  const out: Record<string, string> = {};
  for (const [key, item] of Object.entries(record)) {
    if (typeof item === "string" && item.length > 0) out[key] = item;
  }
  return Object.keys(out).length > 0 ? out : null;
}

/**
 * Map server field errors to a reactive form errors object.
 * Strips confirmed_ prefix so OCR confirmation errors bind to standard fields.
 */
export function terapkanFieldErrors(
  errors: Record<string, string>,
  target: Record<string, string>,
): void {
  for (const key of Object.keys(target)) delete target[key];
  for (const [key, msg] of Object.entries(errors)) {
    const field = (key.includes(".") ? (key.split(".").pop() ?? key) : key).replace(
      /^confirmed_/,
      "",
    );
    target[field] = msg;
  }
}
