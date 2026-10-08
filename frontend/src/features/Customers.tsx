/** S-06 Customers: the CRM list, sortable by each column (US-00-026, US-00-002). */
import { useState } from "react";
import { href } from "../app/route";
import { ArrowDown, ArrowUp, MoreHorizontal, Plus, Search, Trash2, Upload, Users } from "lucide-react";
import { BandBadge, Button, Empty, ErrorLine, inputClass, Loading, PageHeader, td, tdNum } from "../components/kit";
import { Button as UIButton } from "../components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../components/ui/dropdown-menu";
import { cn } from "../lib/utils";
import { day, inr } from "../lib/format";
import { useCustomers } from "../lib/hooks";
import type { Customer, Role } from "../lib/schemas";
import { CustomerDialog, DeleteCustomerDialog, ImportDialog } from "./Directory";

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

export function Customers({ role }: { role: Role }) {
  const q = useCustomers();
  const [find, setFind] = useState("");
  const [dialog, setDialog] = useState<"add" | "upload" | null>(null);
  const [deleting, setDeleting] = useState<Customer | null>(null);
  const canAct = role !== "viewer";
  const canDelete = role === "admin";
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
      <PageHeader
        title="Customers"
        description={`${q.data.data.length} distributors, highest priority first.`}
      >
        {canAct && (
          <>
            <Button icon={Upload} onClick={() => setDialog("upload")}>
              Upload CSV
            </Button>
            <Button variant="primary" icon={Plus} onClick={() => setDialog("add")}>
              Add distributor
            </Button>
          </>
        )}
      </PageHeader>
      {dialog === "add" && <CustomerDialog onClose={() => setDialog(null)} />}
      {dialog === "upload" && <ImportDialog onClose={() => setDialog(null)} />}
      {deleting && <DeleteCustomerDialog customer={deleting} onClose={() => setDeleting(null)} />}
      <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <label className="relative w-full sm:w-72">
            <span className="sr-only">Find a customer</span>
            <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              className={cn(inputClass, "pl-9")}
              placeholder="Find a customer"
              value={find}
              onChange={(e) => setFind(e.target.value)}
            />
          </label>
          {needle && (
            <span role="status" className="text-sm text-muted-foreground">
              {rows.length} of {q.data.data.length} shown
            </span>
          )}
        </div>
      {rows.length === 0 ? (
        <Empty icon={Users}>No customer matches “{find.trim()}”.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-muted/50">
              <tr className="border-b text-xs tracking-wide text-muted-foreground uppercase">
                {COLUMNS.map((c, i) => (
                  <th
                    key={c.label}
                    scope="col"
                    aria-sort={sort.col === i ? (sort.asc ? "ascending" : "descending") : "none"}
                    className={cn("px-3 py-1 font-semibold first:pl-4", c.numeric && "text-right")}
                  >
                    <button
                      type="button"
                      className={cn("inline-flex min-h-9 items-center gap-1 uppercase hover:text-foreground", sort.col === i && "text-foreground")}
                      onClick={() => setSort({ col: i, asc: sort.col === i ? !sort.asc : !c.numeric })}
                    >
                      {c.label}
                      {sort.col === i && (sort.asc ? <ArrowUp aria-hidden className="size-3.5" /> : <ArrowDown aria-hidden className="size-3.5" />)}
                    </button>
                  </th>
                ))}
                {canDelete && (
                  <th scope="col" className="w-12 px-3 py-1 font-semibold">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="transition-colors hover:bg-muted/50">
                  <td className={cn(td, "pl-4")}>
                    <a href={href({ page: "customer", id: c.id })} className="font-semibold text-foreground underline-offset-4 hover:text-primary hover:underline">
                      {c.name}
                    </a>
                  </td>
                  <td className={cn(td, "text-muted-foreground capitalize")}>{c.segment.replaceAll("_", " ")}</td>
                  <td className={tdNum}>{inr(c.outstanding_paise)}</td>
                  <td className={tdNum}>{inr(c.overdue_paise)}</td>
                  <td className={td}>
                    <BandBadge band={c.band} />
                  </td>
                  <td className={cn(td, "whitespace-nowrap text-muted-foreground")}>{c.last_contact_at ? day(c.last_contact_at) : "Never"}</td>
                  <td className={cn(td, "max-w-xs")}>{c.next_action ?? "None"}</td>
                  {canDelete && (
                    <td className={cn(td, "py-1.5 text-right")}>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <UIButton variant="ghost" size="icon" className="size-8" aria-label={`Actions for ${c.name}`}>
                            <MoreHorizontal aria-hidden />
                          </UIButton>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(c)}>
                            <Trash2 aria-hidden /> Delete customer
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </div>
    </div>
  );
}
