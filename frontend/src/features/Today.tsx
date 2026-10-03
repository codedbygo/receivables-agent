/** S-02 Today: totals, ageing and "What needs my attention today?" (US-00-003, US-00-020, US-00-021). */
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CalendarDays,
  Clock,
  Flame,
  Gavel,
  IndianRupee,
  Inbox,
  Scale,
  Send,
  type LucideIcon,
} from "lucide-react";
import { href } from "@/app/route";
import { ColumnChart, ProportionBar, type Bar } from "@/components/charts";
import { Badge, BandBadge, Button, Empty, ErrorLine, Figure, Loading, PageHeader, Panel } from "@/components/kit";
import { api } from "@/lib/api";
import { day, inr } from "@/lib/format";
import { useAction, useCustomers, useDashboard, usePayments } from "@/lib/hooks";
import * as S from "@/lib/schemas";
import { cn } from "@/lib/utils";

const link = (id: string | undefined) => (id ? href({ page: "customer", id }) : undefined);
const name = "font-semibold text-foreground underline-offset-4 hover:text-primary hover:underline";

export function Today() {
  const q = useDashboard();
  const customers = useCustomers();
  const payments = usePayments();
  if (q.isPending) return <Loading what="today's figures" />;
  if (q.error) return <ErrorLine error={q.error} />;
  const d = q.data;
  const a = d.attention;
  const weeks = weekly(payments.data?.data ?? []);
  const peakWeek = weeks.reduce<Bar | undefined>((m, w) => (!m || w.value > m.value ? w : m), undefined);
  const ageing: Bar[] = [
    ["0 to 30 d", d.ageing.d0_30_paise],
    ["31 to 60 d", d.ageing.d31_60_paise],
    ["61 to 90 d", d.ageing.d61_90_paise],
    ["Over 90 d", d.ageing.d90_plus_paise],
  ].map(([label, v]) => ({ label: String(label), value: Number(v), display: inr(Number(v)) }));
  return (
    <div className="space-y-8">
      <PageHeader title="Today" description="Who needs attention, and why. Every figure is computed from the ledger.">
        <span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-sm shadow-xs">
          <CalendarDays aria-hidden className="size-4 text-primary" />
          <span className="text-muted-foreground">Demo date</span>
          <span className="num font-semibold">{day(d.today)}</span>
        </span>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Figure label="Total outstanding" value={inr(d.total_outstanding_paise)} icon={IndianRupee} />
        <Figure
          label="Total overdue"
          value={inr(d.total_overdue_paise)}
          hint={`${d.customers_overdue} customers overdue`}
          icon={Clock}
          tone="warning"
        />
        <Figure
          label="Pending approvals"
          value={d.pending_approvals}
          hint={
            <a className="inline-flex items-center gap-1 font-medium text-primary hover:underline" href="#/approvals">
              Open the queue <ArrowRight aria-hidden className="size-3.5" />
            </a>
          }
          icon={Inbox}
          tone="info"
        />
        <Figure label="High-risk customers" value={d.high_risk_customers} icon={Flame} tone="danger" />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Count label="Today's promises" n={d.todays_promises} icon={CalendarClock} />
        <Count label="Missed promises" n={d.missed_promises} icon={AlertTriangle} alert={d.missed_promises > 0} />
        <Count label="Open disputes" n={d.open_disputes} icon={Scale} alert={d.open_disputes > 0} />
        <Count label="Open escalations" n={d.open_escalations} icon={Gavel} alert={d.open_escalations > 0} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Ageing of overdue amounts">
          <ColumnChart
            data={ageing}
            caption="Overdue amount by age bucket"
            labels="all"
            tones={["bg-primary/35", "bg-primary/55", "bg-primary/80", "bg-primary"]}
          />
        </Panel>
        <Panel title="Credits received by week">
          {payments.isPending ? (
            <Loading what="credits" />
          ) : !payments.data?.data.length ? (
            <Empty>No credits received yet.</Empty>
          ) : (
            <>
              <ColumnChart data={weeks} caption="Credits received per week, latest 30 credits" labels="none" />
              {peakWeek && (
                <p className="mt-3 text-sm">
                  Peak week of {peakWeek.label}: <span className="num font-semibold">{peakWeek.display}</span>
                </p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">Latest 30 bank credits, summed by week from the ledger.</p>
            </>
          )}
        </Panel>
        <Panel title="Customers by priority band">
          {customers.isPending ? (
            <Loading what="customers" />
          ) : (
            <ProportionBar data={bands(customers.data?.data ?? [])} caption="Customers per priority band" unit="customers" />
          )}
        </Panel>
      </div>

      <section className="space-y-4">
        <h2 className="text-heading font-semibold tracking-tight">What needs my attention today?</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="High priority" action={<Badge value={`${a.high_priority.length} customers`} tone="HIGH" />}>
            {a.high_priority.length === 0 ? (
              <Empty>No customer is in the HIGH band.</Empty>
            ) : (
              <ul className="-my-1 divide-y">
                {a.high_priority.map((p) => (
                  <li key={p.customer_id} className="py-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <a href={link(p.customer_id)} className={cn(name, "truncate")}>
                          {p.customer_name}
                        </a>
                        <BandBadge band={p.band} />
                      </span>
                      <ScoreMeter score={p.score} />
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">{p.reasons.map((r) => r.text).join(" · ")}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Missed promises">
            {a.missed_promises.length === 0 ? (
              <Empty>No missed promises.</Empty>
            ) : (
              <ul className="-my-1 divide-y">
                {a.missed_promises.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 py-3">
                    <span className="flex min-w-0 items-center gap-3">
                      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-warning-subtle text-warning">
                        <span aria-hidden>⚠</span>
                      </span>
                      <span className="min-w-0">
                        <a href={link(p.customer_id)} className={name}>
                          {p.customer_name}
                        </a>
                        <span className="block text-sm text-muted-foreground">promised for {day(p.promised_date)}</span>
                      </span>
                    </span>
                    <span className="num font-semibold">{inr(p.amount_paise)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Disputes and escalations">
            {a.disputes.length + a.escalations.length === 0 ? (
              <Empty>Nothing waits for a human.</Empty>
            ) : (
              <ul className="-my-1 divide-y">
                {a.disputes.map((x) => (
                  <li key={x.id} className="py-3">
                    <span className="flex flex-wrap items-center gap-2">
                      <Badge value="Dispute" tone="bad" />
                      <a href={link(x.customer_id)} className={name}>
                        {x.customer_name}
                      </a>
                      <span className="text-muted-foreground">disputes</span>
                      <span className="rounded bg-muted px-1.5 font-mono text-sm">{x.invoice_number}</span>
                    </span>
                    <p className="mt-1 text-sm whitespace-pre-line text-muted-foreground">{x.reason}</p>
                  </li>
                ))}
                {a.escalations.map((x) => (
                  <li key={x.id} className="py-3">
                    <span className="flex flex-wrap items-center gap-2">
                      <Badge value="Escalated" tone="wait" />
                      <a href={link(x.customer_id)} className={name}>
                        {x.customer_name}
                      </a>
                    </span>
                    <p className="mt-1 text-sm text-muted-foreground">{x.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Today's promises and ready reminders">
            {a.todays_promises.length + a.approved_ready.length + a.needs_verification.length === 0 ? (
              <Empty>No promise is due today and nothing is waiting to send.</Empty>
            ) : (
              <ul className="-my-1 divide-y">
                {a.todays_promises.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <a href={link(p.customer_id)} className={name}>
                      {p.customer_name}
                    </a>
                    <span className="flex items-center gap-3">
                      <span className="num text-sm">{inr(p.amount_paise)} due today</span>
                      {p.status === "pending" ? <CheckPayment promiseId={p.id} /> : <Badge value={p.status} />}
                    </span>
                  </li>
                ))}
                {a.approved_ready.map((m) => (
                  <li key={m.id} className="flex items-center gap-2 py-3 text-sm">
                    <Send aria-hidden className="size-4 text-info" />
                    Approved, sending: {m.customer_name}, {m.subject}
                  </li>
                ))}
                {a.needs_verification.map((p) => (
                  <li key={p.id} className="py-3 text-sm">
                    Credit {inr(p.amount_paise)} ({p.reference ?? "no reference"}) needs a human to match it (Admin)
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </section>

    </div>
  );
}

/** The priority score (0 to 100) as a small bar beside the number; the number stays the reading. */
function ScoreMeter({ score }: { score: number }) {
  return (
    <span className="flex shrink-0 items-center gap-2">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted" aria-hidden>
        <span className="block h-full rounded-full bg-danger" style={{ width: `${Math.min(100, score)}%` }} />
      </span>
      <span className="num text-sm text-muted-foreground">score {score}</span>
    </span>
  );
}

/** US-00-021: settles the promise against the ledger; the answer replaces the button, no page reload. */
function CheckPayment({ promiseId }: { promiseId: string }) {
  const check = useAction(() => api(`/promises/${promiseId}/check-payment`, S.PromiseCheckResult, { method: "POST" }));
  if (check.data) {
    return (
      <span
        role="status"
        className={check.data.promise.status === "fulfilled" ? "text-sm font-medium text-success" : "text-sm text-muted-foreground"}
      >
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

function Count({ label, n, icon: Icon, alert }: { label: string; n: number; icon: LucideIcon; alert?: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card p-4 shadow-xs">
      <span
        className={cn(
          "grid size-10 shrink-0 place-items-center rounded-lg",
          alert ? "bg-danger-subtle text-danger" : "bg-muted text-muted-foreground",
        )}
      >
        <Icon aria-hidden className="size-5" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm text-muted-foreground">{label}</span>
        <span className="num block text-xl font-semibold">{n}</span>
      </span>
    </div>
  );
}

/** Credits summed per week (weeks start on Monday), oldest first. */
function weekly(pays: S.Payment[]): Bar[] {
  const byWeek = new Map<string, number>();
  for (const p of pays) {
    const d = new Date(`${p.received_on}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    const week = d.toISOString().slice(0, 10);
    byWeek.set(week, (byWeek.get(week) ?? 0) + p.amount_paise);
  }
  return [...byWeek]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([week, v]) => ({ label: day(week).slice(0, 6), value: v, display: inr(v) }));
}

function bands(customers: S.Customer[]) {
  const n = (band: string | null) => customers.filter((c) => c.band === band).length;
  return [
    { label: "High", value: n("HIGH"), tone: "bg-danger" },
    { label: "Medium", value: n("MEDIUM"), tone: "bg-warning" },
    { label: "Low", value: n("LOW"), tone: "bg-info" },
    { label: "Not overdue", value: n(null), tone: "bg-muted-foreground/40" },
  ];
}
