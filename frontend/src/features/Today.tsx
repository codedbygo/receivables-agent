/** S-02 Today: totals, "What needs my attention today?" and ageing (US-00-003, US-00-020, US-00-021).
 * Order follows the work: the four headline figures, then the attention queue, then the portfolio trends. */
import { AlertTriangle, ArrowRight, CalendarDays, Flame, Handshake, Scale, Send, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { href } from "@/app/route";
import { ColumnChart, ProportionBar, type Bar } from "@/components/charts";
import {
  Badge,
  BandBadge,
  Button,
  Empty,
  ErrorLine,
  Loading,
  MetaChip,
  PageHeader,
  Panel,
  StatStrip,
  WhyFactors,
} from "@/components/kit";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { day, inr } from "@/lib/format";
import { useAction, useCustomers, useDashboard, useFollowUps, usePayments } from "@/lib/hooks";
import * as S from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { FollowUpCard } from "./FollowUps";

const link = (id: string | undefined) => (id ? href({ page: "customer", id }) : undefined);
const name = "font-semibold text-foreground underline-offset-4 hover:text-primary hover:underline";

export function Today() {
  const q = useDashboard();
  const followUps = useFollowUps();
  const customers = useCustomers();
  const payments = usePayments();
  if (q.isPending) return <Loading what="today's figures" />;
  if (q.error) return <ErrorLine error={q.error} />;
  const d = q.data;
  const a = d.attention;
  const fus = followUps.data?.data ?? [];
  const weeks = weekly(payments.data?.data ?? []);
  const peakWeek = weeks.reduce<Bar | undefined>((m, w) => (!m || w.value > m.value ? w : m), undefined);
  const ageing: Bar[] = [
    ["0 to 30 d", d.ageing.d0_30_paise],
    ["31 to 60 d", d.ageing.d31_60_paise],
    ["61 to 90 d", d.ageing.d61_90_paise],
    ["Over 90 d", d.ageing.d90_plus_paise],
  ].map(([label, v]) => ({ label: String(label), value: Number(v), display: inr(Number(v)) }));
  const promiseCount = a.todays_promises.length + a.missed_promises.length + a.approved_ready.length + a.needs_verification.length;
  const issueCount = a.disputes.length + a.escalations.length;

  return (
    <div className="space-y-8">
      <PageHeader title="Today" description="Who needs attention, and why.">
        <MetaChip icon={CalendarDays} label="Demo date" value={day(d.today)} />
      </PageHeader>

      <StatStrip
        stats={[
          { label: "Total outstanding", value: inr(d.total_outstanding_paise) },
          { label: "Total overdue", value: inr(d.total_overdue_paise), hint: `${d.customers_overdue} customers overdue` },
          {
            label: "Pending approvals",
            value: d.pending_approvals,
            hint: (
              <a className="inline-flex items-center gap-1 font-medium text-primary hover:underline" href={href({ page: "approvals" })}>
                Open the queue <ArrowRight aria-hidden className="size-3.5" />
              </a>
            ),
          },
          { label: "High-risk customers", value: d.high_risk_customers, alert: d.high_risk_customers > 0 },
        ]}
      />

      <section aria-labelledby="attention" className="rounded-xl border bg-card shadow-xs">
        <Tabs defaultValue="priority" className="gap-0">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-5 pt-4">
            <h2 id="attention" className="pb-3 text-base font-semibold">
              What needs my attention today?
            </h2>
            <div className="-mb-px max-w-full overflow-x-auto">
              <TabsList variant="line" className="h-10">
                <AttentionTab value="priority" icon={Flame} label="High priority" n={a.high_priority.length} />
                <AttentionTab value="promises" icon={Handshake} label="Promises" n={promiseCount} alert={a.missed_promises.length > 0} />
                <AttentionTab value="issues" icon={Scale} label="Disputes" n={issueCount} alert={issueCount > 0} />
                {fus.length > 0 && <AttentionTab value="followups" icon={AlertTriangle} label="Follow-ups" n={fus.length} alert />}
              </TabsList>
            </div>
          </div>

          <TabsContent value="priority" className="px-5 py-2">
            {a.high_priority.length === 0 ? (
              <Empty icon={Flame}>No customer is in the HIGH band.</Empty>
            ) : (
              <ul className="divide-y">
                {a.high_priority.map((p) => (
                  <li key={p.customer_id} className="py-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <a href={link(p.customer_id)} className={cn(name, "truncate")}>
                          {p.customer_name}
                        </a>
                        <BandBadge band={p.band} />
                      </span>
                      <ScoreMeter score={p.score} />
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">{p.reasons.map((r) => r.text).join(" · ")}</p>
                    {p.factors.length > 0 && (
                      <details className="mt-1 text-sm">
                        <summary className="cursor-pointer text-link">Why?</summary>
                        <WhyFactors factors={p.factors} score={p.score} />
                      </details>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>

          <TabsContent value="promises" className="px-5 py-2">
            {promiseCount === 0 ? (
              <Empty icon={Handshake}>No promise is due or missed and nothing is waiting to send.</Empty>
            ) : (
              <ul className="divide-y">
                {a.missed_promises.map((p) => (
                  <Row key={p.id} icon={AlertTriangle} tone="bg-warning-subtle text-warning" end={<span className="num font-semibold">{inr(p.amount_paise)}</span>}>
                    <a href={link(p.customer_id)} className={name}>
                      {p.customer_name}
                    </a>
                    <span className="block text-sm text-muted-foreground">Missed: promised for {day(p.promised_date)}</span>
                  </Row>
                ))}
                {a.todays_promises.map((p) => (
                  <Row
                    key={p.id}
                    icon={Handshake}
                    tone="bg-info-subtle text-info"
                    end={
                      <span className="flex items-center gap-3">
                        <span className="num font-semibold">{inr(p.amount_paise)}</span>
                        {p.status === "pending" ? <CheckPayment promiseId={p.id} /> : <Badge value={p.status} />}
                      </span>
                    }
                  >
                    <a href={link(p.customer_id)} className={name}>
                      {p.customer_name}
                    </a>
                    <span className="block text-sm text-muted-foreground">Due today</span>
                  </Row>
                ))}
                {a.approved_ready.map((m) => (
                  <Row key={m.id} icon={Send} tone="bg-primary-subtle text-primary">
                    <span className="font-semibold">{m.customer_name}</span>
                    <span className="block text-sm text-muted-foreground">Approved, sending: {m.subject}</span>
                  </Row>
                ))}
                {a.needs_verification.map((p) => (
                  <Row key={p.id} icon={Scale} tone="bg-muted text-muted-foreground" end={<span className="num font-semibold">{inr(p.amount_paise)}</span>}>
                    <span className="font-semibold">Unmatched credit</span>
                    <span className="block text-sm text-muted-foreground">
                      {p.reference ?? "No reference"}: needs a human to match it (Admin)
                    </span>
                  </Row>
                ))}
              </ul>
            )}
          </TabsContent>

          <TabsContent value="issues" className="px-5 py-2">
            {issueCount === 0 ? (
              <Empty icon={Scale}>Nothing waits for a human.</Empty>
            ) : (
              <ul className="divide-y">
                {a.disputes.map((x) => (
                  <li key={x.id} className="py-3.5">
                    <span className="flex flex-wrap items-center gap-2">
                      <Badge value="Dispute" tone="bad" />
                      <a href={link(x.customer_id)} className={name}>
                        {x.customer_name}
                      </a>
                      <span className="rounded bg-muted px-1.5 font-mono text-sm">{x.invoice_number}</span>
                    </span>
                    <p className="mt-1 text-sm whitespace-pre-line text-muted-foreground">{x.reason}</p>
                  </li>
                ))}
                {a.escalations.map((x) => (
                  <li key={x.id} className="py-3.5">
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
          </TabsContent>

          {fus.length > 0 && (
            <TabsContent value="followups" className="grid grid-cols-1 gap-3 p-5 lg:grid-cols-2">
              {fus.map((f) => (
                <FollowUpCard key={f.id} f={f} canAct={false} showCustomer />
              ))}
            </TabsContent>
          )}
        </Tabs>
      </section>

      <section aria-labelledby="portfolio" className="space-y-4">
        <h2 id="portfolio" className="text-title font-semibold tracking-tight">
          Portfolio
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
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
                <p className="mt-1 text-xs text-muted-foreground">Latest 30 bank credits, summed by week.</p>
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
        <p className="text-xs text-muted-foreground">Every figure on this page is computed from the ledger, never by the model.</p>
      </section>
    </div>
  );
}

function AttentionTab({ value, icon: Icon, label, n, alert }: { value: string; icon: LucideIcon; label: string; n: number; alert?: boolean }) {
  return (
    <TabsTrigger value={value} className="px-3">
      <Icon aria-hidden />
      {label}
      <span
        className={cn(
          "num rounded-full px-1.5 text-xs font-semibold",
          n > 0 && alert ? "bg-danger-subtle text-danger" : "bg-muted text-muted-foreground",
        )}
      >
        {n}
      </span>
    </TabsTrigger>
  );
}

/** One attention line: a tinted icon, what it is, and an optional figure or action on the right. */
function Row({ icon: Icon, tone, end, children }: { icon: LucideIcon; tone: string; end?: ReactNode; children: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3.5">
      <span className="flex min-w-0 items-center gap-3">
        <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg", tone)}>
          <Icon aria-hidden className="size-4" />
        </span>
        <span className="min-w-0">{children}</span>
      </span>
      {end}
    </li>
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
