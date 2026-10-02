import { describe, expect, it } from "vitest";
import { day, inr, stamp } from "./format";

// US-00-023: INR amounts and Indian dates read the same in every screen and theme
describe("inr", () => {
  // TC-0268 (AC-US-00-023-1)
  it("groups by Indian lakhs and crores", () => {
    expect(inr(75_000_000)).toBe("₹7,50,000");
    expect(inr(2_500_000_000)).toBe("₹2,50,00,000");
    expect(inr(1_500_000)).toBe("₹15,000");
    expect(inr(0)).toBe("₹0");
  });

  it("shows paise only when not zero", () => {
    expect(inr(9_650_050)).toBe("₹96,500.50");
    expect(inr(105)).toBe("₹1.05");
  });

  it("refuses to format a value that is not integer paise", () => {
    expect(inr(1.5)).toBe("₹—");
    expect(inr(-100)).toBe("₹—");
  });
});

describe("dates", () => {
  // TC-0270 (AC-US-00-023-3)
  it("formats a business date as written", () => {
    expect(day("2026-10-05")).toBe("05 Oct 2026");
  });

  it("formats a timestamp in India time", () => {
    expect(stamp("2026-09-30T20:00:00+00:00")).toBe("01 Oct 2026, 01:30");
  });
});
