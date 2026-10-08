/** The one way the console talks to the API: access code, error envelope, schema-checked responses. */
import { z } from "zod";
import type { Role } from "./schemas";

const ROLE_KEY = "ca.role";

export function storedRole(): Role | null {
  const r = localStorage.getItem(ROLE_KEY);
  return r === "admin" || r === "collector" || r === "viewer" ? r : null;
}

export function storeRole(role: Role | null): void {
  if (role) localStorage.setItem(ROLE_KEY, role);
  else localStorage.removeItem(ROLE_KEY);
}

const CODE_KEY = "ca.code";

/** The access code lives in sessionStorage: it goes when the tab closes. */
export function storedCode(): string {
  return sessionStorage.getItem(CODE_KEY) ?? "";
}

export function storeCode(code: string): void {
  if (code) sessionStorage.setItem(CODE_KEY, code);
  else sessionStorage.removeItem(CODE_KEY);
}

/** The access code (hosted demo) and the role header (laptop, DEMO_OPEN_ROLES). The API reads exactly one of them
 * for its mode and ignores the other, so a code autofilled by a password manager cannot lock out a laptop user, and
 * the header grants nothing on a hosted API. */
export function authHeaders(role: Role | null, code: string): Record<string, string> {
  return {
    ...(code ? { Authorization: `Bearer ${code}` } : {}),
    ...(role ? { "X-Demo-Role": role } : {}),
  };
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly details: { field: string; reason: string }[] = [],
  ) {
    super(message);
  }
}

/** FastAPI's own body for a request that fails its schema, before any handler runs. */
const Invalid = z.object({ detail: z.array(z.object({ loc: z.array(z.union([z.string(), z.number()])), msg: z.string() })) });

const Envelope = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    request_id: z.string().optional(),
    details: z.array(z.object({ field: z.string(), reason: z.string() })).optional(),
  }),
});

/** anonymous: a public page (the customer portal) never sends a staff member's stored credentials. */
type Init = { method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"; body?: unknown; headers?: Record<string, string>; anonymous?: boolean };

export async function api<T extends z.ZodTypeAny>(path: string, schema: T, init: Init = {}): Promise<z.infer<T>> {
  const role = storedRole();
  const res = await fetch(`/api/v1${path}`, {
    method: init.method ?? "GET",
    headers: {
      ...(init.anonymous ? {} : authHeaders(role, storedCode())),
      ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const json: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const env = Envelope.safeParse(json);
    const rid = res.headers.get("X-Request-Id") ?? "";
    if (env.success) throw new ApiError(res.status, env.data.error.code, env.data.error.message, rid, env.data.error.details);
    const invalid = Invalid.safeParse(json);
    if (invalid.success) {
      const details = invalid.data.detail.map((d) => ({
        field: d.loc.filter((x) => x !== "body").join("."),
        reason: d.msg.replace(/^Value error, /, ""),
      }));
      throw new ApiError(res.status, "VALIDATION_ERROR", "Some fields need fixing:", rid, details);
    }
    throw new ApiError(res.status, "HTTP_" + res.status, "The server did not answer as expected.", rid);
  }
  return schema.parse(json);
}
