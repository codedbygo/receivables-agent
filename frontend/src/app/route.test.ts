import { describe, expect, it } from "vitest";
import { parse } from "./route";

describe("parse", () => {
  it("reads a customer page by id", () => {
    expect(parse("#/customers/0192b1c2-7f3a-7c4e-9a1b-2c3d4e5f6a7b")).toEqual({
      page: "customer",
      id: "0192b1c2-7f3a-7c4e-9a1b-2c3d4e5f6a7b",
    });
  });

  it("reads a payment link token and refuses a malformed one", () => {
    const token = "INV-1034.1791454863.0123456789abcdef0123456789abcdef";
    expect(parse(`#/pay/${token}`)).toEqual({ page: "pay", token });
    expect(parse("#/pay/INV-1034.nope")).toEqual({ page: "today" });
    expect(parse("#/pay/INV-1034.0123456789abcdef0123456789abcdef")).toEqual({ page: "today" }); // no expiry segment
  });

  it("falls back to Today for anything unknown or malformed", () => {
    expect(parse("#/customers/not-a-uuid")).toEqual({ page: "customers" });
    expect(parse("#/nowhere")).toEqual({ page: "today" });
    expect(parse("")).toEqual({ page: "today" });
  });
});
