import { describe, expect, it } from "vitest";
import { rupeesToPaise } from "../lib/format";

describe("rupeesToPaise", () => {
  it("turns typed rupees into integer paise without floating point", () => {
    expect(rupeesToPaise("300000")).toBe(30_000_000);
    expect(rupeesToPaise("3,00,000")).toBe(30_000_000);
    expect(rupeesToPaise("96500.5")).toBe(9_650_050);
    expect(rupeesToPaise("0.29")).toBe(29);
  });

  it("refuses anything that is not a positive amount with at most two decimals", () => {
    expect(rupeesToPaise("")).toBeNull();
    expect(rupeesToPaise("0")).toBeNull();
    expect(rupeesToPaise("-5")).toBeNull();
    expect(rupeesToPaise("3 lakh")).toBeNull();
    expect(rupeesToPaise("1.005")).toBeNull();
  });
});
