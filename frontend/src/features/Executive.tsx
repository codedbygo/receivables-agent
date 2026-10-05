/** CFO view (HACK-003 F8): receivables, collections, risk and what needs attention. Every figure comes from the API,
 * which computes it from the ledger; the definitions are shown under the figures. */
import { href } from "../app/route";
import { BarList, Badge, ErrorLine, Figure, Loading, Panel, WhyFactors } from "../components/ui";
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
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-display font-semibold">CFO view</h1>
        <p className="text-text-muted">
          As of <span className="num font-semibold text-text">{day(e.today)}</span>, computed from the ledger
        </p>
      </header>

      <div className="grid grid-cols-2 gap-6 rounded border border-border bg-surface p-4 lg:grid-cols-4">
        <Figure label="Total receivables" value={inr(k.total_receivables_paise)} />
        <Figure label="Overdue" value={inr(k.overdue_paise)} />
        <Figure label="Collected this month" value={inr(k.collected_this_month_paise)} />
        <Figure label="At risk" value={inr(k.at_risk_paise)} />
        <Figure label="Promises due today" value={inr(k.promises_due_today_paise)} />
        <Figure label="Missed promises" value={inr(k.missed_promises_paise)} />
        <Figure label="Collection rate" value={k.collection_rate_pct === null ? "n/a" : `${k.collection_rate_pct}%`} />
      </div>

      <Panel title="What needs attention today?">
        {e.attention.length === 0 ? (
          <p className="text-text-muted">Nothing overdue.</p>
        ) : (
          <ul className="divide-y divide-border">
            {e.attention.map((a) => (
              <li key={a.customer_id} className="py-2">
                <Badge value={a.severity === "red" ? "Act today" : "Watch"} tone={a.severity === "red" ? "bad" : "wait"} />{" "}
                <a href={href({ page: "customer", id: a.customer_id })} className="font-semibold text-link underline">
                  {a.customer_name}
                </a>{" "}
                <span className="text-text-muted">{a.headline}</span>
                <details className="mt-1 text-label">
                  <summary className="cursor-pointer text-link">Why?</summary>
                  <WhyFactors factors={a.factors} score={a.score} />
                </details>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
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

      <Panel title="How each figure is computed">
        <dl className="grid gap-2 md:grid-cols-2">
          {Object.entries(e.definitions).map(([key, text]) => (
            <div key={key}>
              <dt className="font-semibold">{key.replaceAll("_", " ")}</dt>
              <dd className="text-label text-text-muted">{text}</dd>
            </div>
          ))}
        </dl>
      </Panel>
    </div>
  );
}
