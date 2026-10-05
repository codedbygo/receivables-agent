import { describe, expect, it } from "vitest";
import { authHeaders } from "./api";

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
