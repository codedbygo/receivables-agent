import { describe, expect, it } from "vitest";
import { authHeaders } from "./api";

describe("authHeaders", () => {
  it("sends the access code as a bearer token and never the role header", () => {
    expect(authHeaders("admin", "s3cret")).toEqual({ Authorization: "Bearer s3cret" });
  });

  it("falls back to the role header on a laptop, where there is no code", () => {
    expect(authHeaders("collector", "")).toEqual({ "X-Demo-Role": "collector" });
  });

  it("sends nothing when signed out", () => {
    expect(authHeaders(null, "")).toEqual({});
  });
});
