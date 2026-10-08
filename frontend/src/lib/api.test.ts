import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ApiError, api } from "./api";

describe("credentials", () => {
  afterEach(() => vi.unstubAllGlobals());

  // HACK-011: the console sends its session cookie; a public page (portal, pay link) never does.
  it("sends the session cookie to the API and leaves it off for a public page", async () => {
    const seen: RequestInit[] = [];
    vi.stubGlobal("fetch", async (_url: string, init: RequestInit) => {
      seen.push(init);
      return new Response("{}", { status: 200 });
    });

    await api("/auth/me", z.object({}));
    await api("/portal/t", z.object({}), { anonymous: true });

    expect(seen.map((i) => i.credentials)).toEqual(["same-origin", "omit"]);
    expect(seen.every((i) => !("Authorization" in (i.headers as Record<string, string>)))).toBe(true);
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
