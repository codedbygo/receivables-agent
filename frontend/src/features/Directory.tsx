/** HACK-007: collectors add and edit distributors, add invoices and upload a CSV of both; an admin deletes. */
import { useState } from "react";
import { Button, Dialog, ErrorLine, Field, inputClass } from "@/components/kit";
import { href } from "../app/route";
import { api } from "../lib/api";
import { rupeesToPaise } from "../lib/format";
import { useAction } from "../lib/hooks";
import * as S from "../lib/schemas";

const SEGMENTS = [
  ["sme", "SME"],
  ["mid_market", "Mid market"],
  ["enterprise", "Enterprise"],
] as const;

export const CSV_COLUMNS =
  "customer_name,email,phone,segment,credit_terms_days,invoice_number,invoice_date,due_date,amount_rupees";
const CSV_EXAMPLE = "Riya Traders,riya@example.com,+919800000000,sme,30,INV-5001,2026-09-01,2026-09-20,125000";

function Actions({ onClose, busy, submit }: { onClose: () => void; busy: boolean; submit: string }) {
  return (
    <div className="mt-4 flex justify-end gap-2">
      <Button onClick={onClose}>Cancel</Button>
      <Button type="submit" variant="primary" busy={busy}>
        {submit}
      </Button>
    </div>
  );
}

/** Create (no customer given) or edit. A new customer opens on their page, ready for an invoice. */
export function CustomerDialog({ customer, onClose }: { customer?: S.Customer; onClose: () => void }) {
  const [form, setForm] = useState({
    name: customer?.name ?? "",
    email: customer?.email ?? "",
    phone: customer?.phone ?? "",
    segment: customer?.segment ?? "sme",
    credit_terms_days: String(customer?.credit_terms_days ?? 30),
  });
  const body = { ...form, credit_terms_days: Number(form.credit_terms_days) };
  const save = useAction(() =>
    customer
      ? api(`/customers/${customer.id}`, S.Customer, { method: "PATCH", body })
      : api("/customers", S.Customer, { method: "POST", body }),
  );
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  return (
    <Dialog title={customer ? `Edit ${customer.name}` : "Add distributor"} open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined, {
            onSuccess: (c) => {
              onClose();
              if (!customer) window.location.hash = href({ page: "customer", id: c.id });
            },
          });
        }}
      >
        <Field label="Business name">
          <input className={inputClass} required maxLength={200} value={form.name} onChange={set("name")} />
        </Field>
        <Field label="Email (reminders go here)">
          <input className={inputClass} type="email" required maxLength={254} value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Phone">
          <input className={inputClass} type="tel" maxLength={30} value={form.phone} onChange={set("phone")} />
        </Field>
        <Field label="Segment">
          <select className={inputClass} value={form.segment} onChange={set("segment")}>
            {SEGMENTS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Credit terms (days to pay)">
          <input
            className={inputClass}
            type="number"
            min={0}
            max={365}
            required
            value={form.credit_terms_days}
            onChange={set("credit_terms_days")}
          />
        </Field>
        <ErrorLine error={save.error} />
        <Actions onClose={onClose} busy={save.isPending} submit={customer ? "Save" : "Add distributor"} />
      </form>
    </Dialog>
  );
}

export function InvoiceDialog({ customerId, onClose }: { customerId: string; onClose: () => void }) {
  const [form, setForm] = useState({ number: "INV-", invoice_date: "", due_date: "", amount: "" });
  const [amountError, setAmountError] = useState("");
  const save = useAction((amount_paise: number) =>
    api(`/customers/${customerId}/invoices`, S.Invoice, {
      method: "POST",
      body: { number: form.number.trim(), invoice_date: form.invoice_date, due_date: form.due_date, amount_paise },
    }),
  );
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  return (
    <Dialog title="Add invoice" open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const paise = rupeesToPaise(form.amount);
          setAmountError(paise === null ? "Enter an amount in rupees above zero, for example 125000 or 1,25,000.50." : "");
          if (paise !== null) save.mutate(paise, { onSuccess: onClose });
        }}
      >
        <Field label="Invoice number (INV- and digits)">
          <input className={inputClass} required pattern="INV-\d{1,12}" value={form.number} onChange={set("number")} />
        </Field>
        <div className="grid gap-x-4 sm:grid-cols-2">
          <Field label="Invoice date">
            <input className={inputClass} type="date" required value={form.invoice_date} onChange={set("invoice_date")} />
          </Field>
          <Field label="Due date">
            <input
              className={inputClass}
              type="date"
              required
              min={form.invoice_date || undefined}
              value={form.due_date}
              onChange={set("due_date")}
            />
          </Field>
        </div>
        <Field label="Amount in ₹">
          <input className={inputClass} inputMode="decimal" required value={form.amount} onChange={set("amount")} />
        </Field>
        {amountError && (
          <p role="alert" className="text-danger">
            {amountError}
          </p>
        )}
        <ErrorLine error={save.error} />
        <Actions onClose={onClose} busy={save.isPending} submit="Add invoice" />
      </form>
    </Dialog>
  );
}

export function ImportDialog({ onClose }: { onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const upload = useAction(async (f: File) =>
    api("/customers/import", S.Imported, { method: "POST", body: { csv: await f.text() } }),
  );
  return (
    <Dialog title="Upload distributors and invoices" open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (file) upload.mutate(file);
        }}
      >
        <p className="mb-2">One row per invoice. A new name creates the distributor; a name you already have gets the invoice.</p>
        <p className="mb-1 font-medium">Columns, in this header row:</p>
        <pre className="mb-2 overflow-x-auto rounded bg-bg-subtle p-2 text-xs">{`${CSV_COLUMNS}\n${CSV_EXAMPLE}`}</pre>
        <p className="mb-4 text-sm text-text-muted">
          Dates are YYYY-MM-DD, amounts are rupees. If any row is wrong nothing is saved and the rows to fix are listed. Up to 500 rows.
        </p>
        <Field label="CSV file">
          <input
            className={inputClass}
            type="file"
            accept=".csv,text/csv"
            required
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              upload.reset();
            }}
          />
        </Field>
        <ErrorLine error={upload.error} />
        {upload.data && (
          <p role="status" className="rounded border border-info bg-info-subtle px-3 py-2 text-info">
            Uploaded: {upload.data.customers_created} new distributor(s), {upload.data.invoices_added} invoice(s) added.
          </p>
        )}
        {upload.data ? (
          <div className="mt-4 flex justify-end">
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        ) : (
          <Actions onClose={onClose} busy={upload.isPending} submit="Upload" />
        )}
      </form>
    </Dialog>
  );
}

export function DeleteCustomerDialog({
  customer,
  onClose,
  onDeleted,
}: {
  customer: { id: string; name: string };
  onClose: () => void;
  onDeleted?: () => void;
}) {
  const remove = useAction(() => api(`/customers/${customer.id}`, S.Deleted, { method: "DELETE" }));
  return (
    <Dialog title={`Delete ${customer.name}?`} open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          remove.mutate(undefined, {
            onSuccess: () => {
              onClose();
              onDeleted?.();
            },
          });
        }}
      >
        <p>
          This removes {customer.name} and everything recorded about them: invoices, payments, messages, replies, promises, disputes,
          calls, notes and the timeline. It cannot be undone. Resetting the demo data brings back only the 10 seeded distributors.
        </p>
        <ErrorLine error={remove.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="danger" busy={remove.isPending}>
            Delete {customer.name}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
