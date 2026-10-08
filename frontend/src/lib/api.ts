/** The one way the console talks to the API: the session cookie, error envelope, schema-checked responses. */
import { z } from "zod";

// HACK-011: sign-in is a session cookie now. Forget the role and access code that earlier builds stored.
try {
  localStorage.removeItem("ca.role");
  sessionStorage.removeItem("ca.code");
} catch {
  // storage blocked or absent (private mode, tests): nothing was stored either
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

/** anonymous: a public page (the customer portal) never sends a staff member's session cookie. */
type Init = { method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"; body?: unknown; headers?: Record<string, string>; anonymous?: boolean };

export async function api<T extends z.ZodTypeAny>(path: string, schema: T, init: Init = {}): Promise<z.infer<T>> {
  const res = await fetch(`/api/v1${path}`, {
    method: init.method ?? "GET",
    credentials: init.anonymous ? "omit" : "same-origin",
    headers: {
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
