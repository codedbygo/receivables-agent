import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ApiError, api, authHeaders } from "./api";

describe("authHeaders", () => {
  it("sends the access code as a bearer token, with the role header beside it", () => {
    // A hosted API reads only the code and ignores the header; a laptop API (DEMO_OPEN_ROLES) reads only the
    // header. Sending both means a code the browser's password manager filled in cannot lock a laptop user out.
    expect(authHeaders("admin", "s3cret")).toEqual({ Authorization: "Bearer s3cret", "X-Demo-Role": "admin" });
  });

  it("never sends the role header without a role", () => {
    expect(authHeaders(null, "s3cret")).toEqual({ Authorization: "Bearer s3cret" });
  });

  it("falls back to the role header on a laptop, where there is no code", () => {
    expect(authHeaders("collector", "")).toEqual({ "X-Demo-Role": "collector" });
  });

  it("sends nothing when signed out", () => {
    expect(authHeaders(null, "")).toEqual({});
  });
});

describe("api errors", () => {
  const storage = { getItem: () => null, setItem: () => undefined, removeItem: () => undefined };
  const answer = (status: number, body: unknown) => {
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal("sessionStorage", storage);
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify(body), { status, headers: { "X-Request-Id": "req_1" } }));
  };
  afterEach(() => vi.unstubAllGlobals());

  // HACK-007: a form field FastAPI rejects before any handler runs used to read "The server did not answer as expected."
  it("turns a request that fails the API's schema into a validation error naming each field", async () => {
    answer(422, { detail: [{ loc: ["body", "email"], msg: "Value error, Enter an email address like accounts@example.com." }] });

    const err = await api("/customers", z.object({})).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("VALIDATION_ERROR");
    expect((err as ApiError).details).toEqual([{ field: "email", reason: "Enter an email address like accounts@example.com." }]);
  });

  it("keeps the details of the API's own error envelope", async () => {
    answer(422, { error: { code: "VALIDATION_ERROR", message: "1 row(s) need fixing", details: [{ field: "row 3", reason: "bad" }] } });

    const err = (await api("/customers/import", z.object({})).catch((e: unknown) => e)) as ApiError;

    expect([err.message, err.details, err.requestId]).toEqual(["1 row(s) need fixing", [{ field: "row 3", reason: "bad" }], "req_1"]);
  });
});
