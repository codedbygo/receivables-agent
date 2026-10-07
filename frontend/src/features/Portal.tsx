/** Customer payment portal (HACK-003 F6). Public: the link is the only credential and shows one customer's open
 * invoices. Promise, dispute and help requests become real records for a collector; Pay Now is SIMULATED. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Badge, Button, ErrorLine, Field, inputClass, Loading, Table, td, tdNum } from "@/components/kit";
import { api } from "../lib/api";
import { day, inr, rupeesToPaise } from "../lib/format";
import * as S from "../lib/schemas";

type Action = "promise" | "dispute" | "help" | null;

export function Portal({ token }: { token: string }) {
  const qc = useQueryClient();
  const key = ["portal", token];
  const view = useQuery({
    queryKey: key,
    queryFn: () => api(`/portal/${token}`, S.PortalView, { anonymous: true }),
    retry: false,
  });
  const [open, setOpen] = useState<Action>(null);
  const [done, setDone] = useState<string | null>(null);
  const post = (path: string, body: unknown) =>
    api(`/portal/${token}/${path}`, S.PortalAck, { method: "POST", body, anonymous: true });
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body: unknown }) => post(path, body),
    onSuccess: (r) => {
      setDone(r.message);
      setOpen(null);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });

  if (view.isPending) return <Shell><Loading what="your account" /></Shell>;
  if (view.isError)
    return (
      <Shell>
        <ErrorLine error={view.error} plain />
      </Shell>
    );
  const v = view.data;
  const disputable = v.invoices.filter((i) => i.status !== "under review");
  return (
    <Shell>
      <header className="mb-6">
        <p className="text-text-muted">Account statement for</p>
        <h1 className="font-display text-display font-semibold">{v.customer_name}</h1>
        <p className="mt-2 text-text-muted">Outstanding</p>
        <p className="num font-display text-figure font-semibold">{inr(v.outstanding_paise)}</p>
      </header>

      {done && (
        <p role="status" className="mb-4 rounded border border-success bg-success-subtle px-3 py-2 font-semibold text-success">
          {done}
        </p>
      )}

      <section aria-label="Invoices" className="rounded border border-border bg-surface p-4">
        <Table head={["Invoice", "Due", "Amount due", "Status", ""]} numeric={[2]}>
          {v.invoices.map((i) => (
            <tr key={i.number}>
              <td className={`${td} font-mono`}>{i.number}</td>
              <td className={td}>{day(i.due_date)}</td>
              <td className={tdNum}>{inr(i.remaining_paise)}</td>
              <td className={td}>
                <Badge value={i.status} tone={i.status === "overdue" ? "bad" : i.status === "under review" ? "info" : "plain"} />
              </td>
              <td className={td}>
                {v.pay_now_available && i.status !== "under review" && (
                  <Button onClick={() => act.mutate({ path: "pay", body: { invoice_number: i.number } })} busy={act.isPending}>
                    Pay now{v.payment_simulated ? " (simulated)" : ""}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </Table>
        {v.promises.length > 0 && (
          <p className="mt-3 text-label text-text-muted">
            Your promises: {v.promises.map((p) => `${inr(p.amount_paise)} by ${day(p.promised_date)}`).join(", ")}
          </p>
        )}
      </section>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => setOpen("promise")}>
          Promise to pay
        </Button>
        <Button onClick={() => setOpen("dispute")} disabled={disputable.length === 0}>
          Raise a dispute
        </Button>
        <Button onClick={() => setOpen("help")}>Request help</Button>
      </div>
      <ErrorLine error={act.error} plain />

      {open === "promise" && (
        <PromiseForm max={v.outstanding_paise} busy={act.isPending} onCancel={() => setOpen(null)} onSubmit={(body) => act.mutate({ path: "promise", body })} />
      )}
      {open === "dispute" && (
        <TextForm
          title="Raise a dispute"
          invoices={disputable.map((i) => i.number)}
          label="What is wrong? (for example: invoice says 50 units but we received 40)"
          busy={act.isPending}
          onCancel={() => setOpen(null)}
          onSubmit={(invoice, description) => act.mutate({ path: "dispute", body: { invoice_number: invoice, description } })}
        />
      )}
      {open === "help" && (
        <TextForm
          title="Request help"
          label="How can we help?"
          busy={act.isPending}
          onCancel={() => setOpen(null)}
          onSubmit={(_, message) => act.mutate({ path: "help", body: { message } })}
        />
      )}
      <p className="mt-8 text-label text-text-muted">This secure link expires on {day(v.expires_at)}. Do not forward it.</p>
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <p role="note" className="mb-6 rounded border border-warning bg-warning-subtle px-4 py-2 text-center text-label font-semibold text-warning">
        Demo portal: Pay Now is SIMULATED and no money moves. Promises, disputes and help requests are recorded.
      </p>
      {children}
    </main>
  );
}

/** The promised amount in paise, or null when it is not a positive amount within the outstanding balance. */
export function promisePaise(text: string, max: number): number | null {
  const paise = rupeesToPaise(text);
  return paise !== null && paise <= max ? paise : null;
}

function PromiseForm({
  max,
  busy,
  onCancel,
  onSubmit,
}: {
  max: number;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: { amount_paise: number; promised_date: string }) => void;
}) {
  const [rupees, setRupees] = useState("");
  const [on, setOn] = useState("");
  const paise = promisePaise(rupees, max);
  const valid = paise !== null && on !== "";
  return (
    <form
      className="mt-4 space-y-3 rounded border border-border bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (paise !== null && on !== "") onSubmit({ amount_paise: paise, promised_date: on });
      }}
    >
      <h2 className="font-semibold">Promise to pay</h2>
      <Field label={`Amount in rupees (up to ${inr(max)})`}>
        <input className={inputClass} inputMode="decimal" value={rupees} onChange={(e) => setRupees(e.target.value)} required />
      </Field>
      {rupees && paise === null && (
        <p className="text-danger">Error: enter rupees up to {inr(max)}, with at most two decimals.</p>
      )}
      <Field label="Payment date">
        <input className={inputClass} type="date" value={on} onChange={(e) => setOn(e.target.value)} required />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" busy={busy} disabled={!valid}>
          Confirm promise
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function TextForm({
  title,
  label,
  invoices,
  busy,
  onCancel,
  onSubmit,
}: {
  title: string;
  label: string;
  invoices?: string[];
  busy: boolean;
  onCancel: () => void;
  onSubmit: (invoice: string, text: string) => void;
}) {
  const [invoice, setInvoice] = useState(invoices?.[0] ?? "");
  const [text, setText] = useState("");
  return (
    <form
      className="mt-4 space-y-3 rounded border border-border bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(invoice, text.trim());
      }}
    >
      <h2 className="font-semibold">{title}</h2>
      {invoices && (
        <Field label="Invoice">
          <select className={inputClass} value={invoice} onChange={(e) => setInvoice(e.target.value)}>
            {invoices.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </Field>
      )}
      <Field label={label}>
        <textarea className={inputClass} rows={3} maxLength={500} value={text} onChange={(e) => setText(e.target.value)} required />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" busy={busy} disabled={!text.trim()}>
          Send
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
