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

  it("reads the CFO view and the AI Safety Center (HACK-003)", () => {
    expect(parse("#/executive")).toEqual({ page: "executive" });
    expect(parse("#/safety")).toEqual({ page: "safety" });
  });

  it("reads the incoming replies queue (HACK-009)", () => {
    expect(parse("#/inbox")).toEqual({ page: "inbox" });
  });

  it("reads a portal token and refuses a malformed one (HACK-003)", () => {
    const token = "Abc_def-1234567890abcdef1234567890ABCDEF12";
    expect(parse(`#/portal/${token}`)).toEqual({ page: "portal", token });
    expect(parse("#/portal/short")).toEqual({ page: "today" });
    expect(parse("#/portal/bad%20token%20with%20spaces%20xxxxxxx")).toEqual({ page: "today" });
  });

  it("falls back to Today for anything unknown or malformed", () => {
    expect(parse("#/customers/not-a-uuid")).toEqual({ page: "customers" });
    expect(parse("#/nowhere")).toEqual({ page: "today" });
    expect(parse("")).toEqual({ page: "today" });
  });
});
