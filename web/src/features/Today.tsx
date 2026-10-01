/** S-02 Today: totals, ageing and "What needs my attention today?" (US-00-003, US-00-020, US-00-021). */
import { href } from "../app/route";
import { Badge, BandBadge, Button, Empty, ErrorLine, Figure, Loading, Panel } from "../components/ui";
import { api } from "../lib/api";
import { day, inr } from "../lib/format";
import { useAction, useDashboard } from "../lib/hooks";
import * as S from "../lib/schemas";

const link = (id: string | undefined) => (id ? href({ page: "customer", id }) : undefined);

export function Today() {
  const q = useDashboard();
  if (q.isPending) return <Loading what="today's figures" />;
  if (q.error) return <ErrorLine error={q.error} />;
  const d = q.data;
  const a = d.attention;
  const ageing = [
    ["0 to 30 days", d.ageing.d0_30_paise],
    ["31 to 60 days", d.ageing.d31_60_paise],
    ["61 to 90 days", d.ageing.d61_90_paise],
    ["Over 90 days", d.ageing.d90_plus_paise],
  ] as const;
  const maxAge = Math.max(1, ...ageing.map(([, v]) => v));
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-display font-semibold">Today</h1>
        <p className="text-text-muted">
          Demo date <span className="num font-semibold text-text">{day(d.today)}</span>
        </p>
      </header>

      <div className="grid grid-cols-2 gap-6 rounded border border-border bg-surface p-4 lg:grid-cols-4">
        <Figure label="Total outstanding" value={inr(d.total_outstanding_paise)} />
        <Figure label="Total overdue" value={inr(d.total_overdue_paise)} hint={`${d.customers_overdue} customers overdue`} />
        <Figure label="Pending approvals" value={d.pending_approvals} hint={<a className="text-link underline" href="#/approvals">Open the queue</a>} />
        <Figure label="High-risk customers" value={d.high_risk_customers} />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Count label="Today's promises" n={d.todays_promises} />
        <Count label="Missed promises" n={d.missed_promises} />
        <Count label="Open disputes" n={d.open_disputes} />
        <Count label="Open escalations" n={d.open_escalations} />
      </div>

      <h2 className="font-display text-heading font-semibold">What needs my attention today?</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="High priority">
          {a.high_priority.length === 0 ? (
            <Empty>No customer is in the HIGH band.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {a.high_priority.map((p) => (
                <li key={p.customer_id} className="py-2">
                  <a href={link(p.customer_id)} className="font-semibold text-link underline">{p.customer_name}</a>{" "}
                  <BandBadge band={p.band} /> <span className="num text-text-muted">score {p.score}</span>
                  <p className="text-label text-text-muted">{p.reasons.map((r) => r.text).join(" · ")}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Missed promises">
          {a.missed_promises.length === 0 ? (
            <Empty>No missed promises.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {a.missed_promises.map((p) => (
                <li key={p.id} className="flex justify-between gap-2 py-2">
                  <span>
                    <span aria-hidden>⚠ </span>
                    <a href={link(p.customer_id)} className="text-link underline">{p.customer_name}</a> promised for{" "}
                    {day(p.promised_date)}
                  </span>
                  <span className="num">{inr(p.amount_paise)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Disputes and escalations">
          {a.disputes.length + a.escalations.length === 0 ? (
            <Empty>Nothing waits for a human.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {a.disputes.map((x) => (
                <li key={x.id} className="py-2">
                  <a href={link(x.customer_id)} className="text-link underline">{x.customer_name}</a> disputes{" "}
                  <span className="font-mono">{x.invoice_number}</span>
                  <p className="text-label whitespace-pre-line text-text-muted">{x.reason}</p>
                </li>
              ))}
              {a.escalations.map((x) => (
                <li key={x.id} className="py-2">
                  <a href={link(x.customer_id)} className="text-link underline">{x.customer_name}</a>: {x.reason}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Today's promises and ready reminders">
          {a.todays_promises.length + a.approved_ready.length + a.needs_verification.length === 0 ? (
            <Empty>No promise is due today and nothing is waiting to send.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {a.todays_promises.map((p) => (
                <li key={p.id} className="flex justify-between gap-2 py-2">
                  <a href={link(p.customer_id)} className="text-link underline">{p.customer_name}</a>
                  <span className="flex items-center gap-2">
                    <span className="num">{inr(p.amount_paise)} due today</span>
                    {p.status === "pending" ? <CheckPayment promiseId={p.id} /> : <Badge value={p.status} />}
                  </span>
                </li>
              ))}
              {a.approved_ready.map((m) => (
                <li key={m.id} className="py-2">Approved, sending: {m.customer_name}, {m.subject}</li>
              ))}
              {a.needs_verification.map((p) => (
                <li key={p.id} className="py-2">
                  Credit {inr(p.amount_paise)} ({p.reference ?? "no reference"}) needs a human to match it (Admin)
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Ageing of overdue amounts">
        <ul className="space-y-2">
          {ageing.map(([label, v]) => (
            <li key={label} className="grid grid-cols-[8rem_1fr_8rem] items-center gap-3">
              <span className="text-text-muted">{label}</span>
              <span className="h-3 rounded bg-bg-subtle" aria-hidden>
                <span className="block h-3 rounded bg-accent" style={{ width: `${(v / maxAge) * 100}%` }} />
              </span>
              <span className="num text-right">{inr(v)}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

/** US-00-021: settles the promise against the ledger; the answer replaces the button, no page reload. */
function CheckPayment({ promiseId }: { promiseId: string }) {
  const check = useAction(() => api(`/promises/${promiseId}/check-payment`, S.PromiseCheckResult, { method: "POST" }));
  if (check.data) {
    return (
      <span role="status" className={check.data.promise.status === "fulfilled" ? "text-success" : "text-text-muted"}>
        {check.data.promise.status === "fulfilled" ? "Fulfilled" : check.data.message}
      </span>
    );
  }
  return (
    <>
      <Button onClick={() => check.mutate(undefined)} busy={check.isPending}>
        Check payment
      </Button>
      <ErrorLine error={check.error} />
    </>
  );
}

function Count({ label, n }: { label: string; n: number }) {
  return (
    <div className="rounded border border-border bg-surface p-3">
      <div className="text-label text-text-muted">{label}</div>
      <div className="num font-display text-heading font-semibold">{n}</div>
    </div>
  );
}
