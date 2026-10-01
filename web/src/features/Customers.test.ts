import { describe, expect, it } from "vitest";
import type { Customer } from "../lib/schemas";
import { COLUMNS, sortCustomers } from "./Customers";

const row = (name: string, outstanding: number, band: Customer["band"], last: string | null): Customer => ({
  id: name,
  name,
  email: "",
  phone: "",
  segment: "sme",
  credit_terms_days: 30,
  outstanding_paise: outstanding,
  overdue_paise: outstanding,
  band,
  last_contact_at: last,
  next_action: null,
});

const rows = [
  row("Metro", 9_650_000, "LOW", null),
  row("ABC", 75_000_000, "HIGH", "2026-09-01"),
  row("Kumar", 124_000_000, "HIGH", "2026-08-01"),
];
const names = (r: Customer[]) => r.map((c) => c.name);

describe("sortCustomers", () => {
  // TC-0157 (AC-US-00-026-1): the list shows every column and sorts by each
  it("has the seven columns the CRM list needs", () => {
    expect(COLUMNS.map((c) => c.label)).toEqual([
      "Customer", "Segment", "Outstanding", "Overdue", "Priority", "Last contact", "Next action",
    ]);
  });

  it("sorts by priority band by default, then by outstanding", () => {
    expect(names(sortCustomers(rows, 4, true))).toEqual(["Kumar", "ABC", "Metro"]);
  });

  it("sorts by any column in either direction", () => {
    expect(names(sortCustomers(rows, 0, true))).toEqual(["ABC", "Kumar", "Metro"]);
    expect(names(sortCustomers(rows, 2, false))).toEqual(["Kumar", "ABC", "Metro"]);
    expect(names(sortCustomers(rows, 5, true))).toEqual(["Metro", "Kumar", "ABC"]);
  });
});
