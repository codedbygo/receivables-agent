/** CFO view (HACK-003 F8): receivables, collections, risk and what needs attention. Every figure comes from the API,
 * which computes it from the ledger; the definitions are shown under the figures. */
import { href } from "../app/route";
import { CalendarDays } from "lucide-react";
import { BarList, Badge, Definitions, Empty, ErrorLine, Loading, MetaChip, PageHeader, Panel, StatStrip, WhyFactors } from "@/components/kit";
import { day, inr } from "../lib/format";
import { useExecutive } from "../lib/hooks";

const count = (v: number) => String(v);

export function Executive() {
  const q = useExecutive();
  if (q.isPending) return <Loading what="the CFO view" />;
  if (q.isError) return <ErrorLine error={q.error} />;
  const e = q.data;
  const k = e.kpis;
  return (
    <div className="space-y-6">
      <PageHeader title="CFO view" description="Receivables, collections and risk at a glance.">
        <MetaChip icon={CalendarDays} label="As of" value={day(e.today)} />
      </PageHeader>

      <StatStrip
        stats={[
          { label: "Total receivables", value: inr(k.total_receivables_paise) },
          { label: "Overdue", value: inr(k.overdue_paise) },
          { label: "Collected this month", value: inr(k.collected_this_month_paise) },
          { label: "Collection rate", value: k.collection_rate_pct === null ? "n/a" : `${k.collection_rate_pct}%` },
        ]}
      />
      <StatStrip
        stats={[
          { label: "At risk", value: inr(k.at_risk_paise), alert: k.at_risk_paise > 0 },
          { label: "Promises due today", value: inr(k.promises_due_today_paise) },
          { label: "Missed promises", value: inr(k.missed_promises_paise), alert: k.missed_promises_paise > 0 },
        ]}
      />

      <Panel title="What needs attention today?">
        {e.attention.length === 0 ? (
          <Empty>Nothing overdue.</Empty>
        ) : (
          <ul className="-my-1 divide-y">
            {e.attention.map((a) => (
              <li key={a.customer_id} className="py-3">
                <span className="flex flex-wrap items-center gap-2">
                  <Badge value={a.severity === "red" ? "Act today" : "Watch"} tone={a.severity === "red" ? "bad" : "wait"} />
                  <a
                    href={href({ page: "customer", id: a.customer_id })}
                    className="font-semibold text-foreground underline-offset-4 hover:text-primary hover:underline"
                  >
                    {a.customer_name}
                  </a>
                  <span className="text-sm text-muted-foreground">{a.headline}</span>
                </span>
                <details className="mt-1 text-label">
                  <summary className="cursor-pointer text-link">Why?</summary>
                  <WhyFactors factors={a.factors} score={a.score} />
                </details>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Receivables ageing">
          <BarList data={e.ageing} format={inr} />
        </Panel>
        <Panel title="Collections by week">
          <BarList data={e.collections_by_week} format={inr} />
        </Panel>
        <Panel title="Overdue trend (week end)">
          <BarList data={e.overdue_trend} format={inr} />
        </Panel>
        <Panel title="Expected collections (pending promises)">
          <BarList data={e.expected_collections} format={inr} />
        </Panel>
        <Panel title="Promise outcomes">
          <BarList data={e.promise_outcomes} format={count} />
        </Panel>
        <Panel title="Customer risk distribution">
          <BarList data={e.risk_distribution} format={count} />
        </Panel>
        <Panel title="Collections by last contact channel">
          <BarList data={e.collections_by_channel} format={inr} />
        </Panel>
        <Panel title="Disputes by status">
          <BarList data={e.disputes_by_status} format={count} />
        </Panel>
      </div>

      <Definitions title="How each figure is computed from the ledger" entries={e.definitions} />
    </div>
  );
}
