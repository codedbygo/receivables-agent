/** S-06 Customers: the CRM list, sortable by each column (US-00-026, US-00-002). */
import { useState } from "react";
import { href } from "../app/route";
import { BandBadge, Empty, ErrorLine, inputClass, Loading, td, tdNum } from "../components/ui";
import { day, inr } from "../lib/format";
import { useCustomers } from "../lib/hooks";
import type { Customer } from "../lib/schemas";

const BAND: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

type Column = { label: string; value: (c: Customer) => string | number; numeric?: boolean };

export const COLUMNS: Column[] = [
  { label: "Customer", value: (c) => c.name.toLowerCase() },
  { label: "Segment", value: (c) => c.segment },
  { label: "Outstanding", value: (c) => c.outstanding_paise, numeric: true },
  { label: "Overdue", value: (c) => c.overdue_paise, numeric: true },
  { label: "Priority", value: (c) => BAND[c.band ?? ""] ?? 3 },
  { label: "Last contact", value: (c) => c.last_contact_at ?? "" },
  { label: "Next action", value: (c) => c.next_action ?? "" },
];

/** Stable sort by one column; ties keep the priority order (band, then outstanding). */
export function sortCustomers(rows: Customer[], col: number, asc: boolean): Customer[] {
  const pick = COLUMNS[col]?.value ?? COLUMNS[0]!.value;
  const base = [...rows].sort(
    (a, b) => (BAND[a.band ?? ""] ?? 3) - (BAND[b.band ?? ""] ?? 3) || b.outstanding_paise - a.outstanding_paise,
  );
  return base.sort((a, b) => {
    const x = pick(a);
    const y = pick(b);
    return (x < y ? -1 : x > y ? 1 : 0) * (asc ? 1 : -1);
  });
}

export function Customers() {
  const q = useCustomers();
  const [find, setFind] = useState("");
  const [sort, setSort] = useState<{ col: number; asc: boolean }>({ col: 4, asc: true });
  if (q.isPending) return <Loading what="customers" />;
  if (q.error) return <ErrorLine error={q.error} />;
  const needle = find.trim().toLowerCase();
  const rows = sortCustomers(
    q.data.data.filter((c) => !needle || c.name.toLowerCase().includes(needle)),
    sort.col,
    sort.asc,
  );
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-display font-semibold">Customers</h1>
        <label className="w-72">
          <span className="sr-only">Find a customer</span>
          <input
            className={inputClass}
            placeholder="Find a customer"
            value={find}
            onChange={(e) => setFind(e.target.value)}
          />
        </label>
      </header>
      {rows.length === 0 ? (
        <Empty>No customer matches “{find.trim()}”.</Empty>
      ) : (
        <div className="overflow-x-auto rounded border border-border bg-surface">
          <table className="w-full border-collapse text-left">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-border-strong text-label text-text-muted uppercase">
                {COLUMNS.map((c, i) => (
                  <th
                    key={c.label}
                    scope="col"
                    aria-sort={sort.col === i ? (sort.asc ? "ascending" : "descending") : "none"}
                    className={`px-2 py-2 font-semibold ${c.numeric ? "text-right" : ""}`}
                  >
                    <button
                      type="button"
                      className="min-h-9 uppercase hover:text-text"
                      onClick={() => setSort({ col: i, asc: sort.col === i ? !sort.asc : !c.numeric })}
                    >
                      {c.label}
                      <span aria-hidden> {sort.col === i ? (sort.asc ? "▲" : "▼") : ""}</span>
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="hover:bg-bg-subtle">
                  <td className={td}>
                    <a href={href({ page: "customer", id: c.id })} className="font-semibold text-link underline">
                      {c.name}
                    </a>
                  </td>
                  <td className={td}>{c.segment.replaceAll("_", " ")}</td>
                  <td className={tdNum}>{inr(c.outstanding_paise)}</td>
                  <td className={tdNum}>{inr(c.overdue_paise)}</td>
                  <td className={td}>
                    <BandBadge band={c.band} />
                  </td>
                  <td className={td}>{c.last_contact_at ? day(c.last_contact_at) : "Never"}</td>
                  <td className={td}>{c.next_action ?? "None"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
