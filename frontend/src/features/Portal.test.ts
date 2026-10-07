import { describe, expect, it } from "vitest";
import { promisePaise } from "./Portal";

// HACK-004 (QA ISSUE-006): the form stripped every non-digit, so "-500" became a ₹500 promise.
describe("promisePaise", () => {
  it("refuses a negative amount instead of dropping the sign", () => {
    expect(promisePaise("-500", 75_000_000)).toBeNull();
  });

  it("keeps the decimal point, so paise are not multiplied by a hundred", () => {
    expect(promisePaise("2000.50", 75_000_000)).toBe(200_050);
  });

  it("refuses an amount above the outstanding balance", () => {
    expect(promisePaise("750000.01", 75_000_000)).toBeNull();
  });

  it("accepts the full balance written with lakh commas", () => {
    expect(promisePaise("7,50,000", 75_000_000)).toBe(75_000_000);
  });
});
