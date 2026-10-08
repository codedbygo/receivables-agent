/** AI Safety Center (HACK-003): counts of real guardrail, approval and send events. No figure here is estimated. */
import { Badge, Definitions, Empty, ErrorLine, Loading, PageHeader, Panel, StatStrip, Table, td, tdNum } from "@/components/kit";
import { useSafety } from "../lib/hooks";

export function SafetyCenter() {
  const q = useSafety();
  if (q.isPending) return <Loading what="the safety center" />;
  if (q.isError) return <ErrorLine error={q.error} />;
  const s = q.data;
  const usd = (micro: number) => `$${(micro / 1_000_000).toFixed(2)}`;
  return (
    <div className="space-y-6">
      <PageHeader title="AI Safety" description="Live counts from the guardrail log, approvals and sends. Nothing here is simulated." />

      <section aria-labelledby="guardrails" className="space-y-3">
        <h2 id="guardrails" className="text-sm font-semibold text-muted-foreground">Guardrails</h2>
        <StatStrip
          stats={[
            { label: "Messages checked", value: s.messages_checked, hint: `${s.messages_passed} passed every check` },
            { label: "Incorrect amounts blocked", value: s.incorrect_amounts_blocked },
            { label: "Prompt attacks blocked", value: s.prompt_attacks_blocked },
            { label: "Guardrail events", value: s.guardrail_failures },
          ]}
        />
      </section>
      <section aria-labelledby="approvals-sends" className="space-y-3">
        <h2 id="approvals-sends" className="text-sm font-semibold text-muted-foreground">Approvals and sends</h2>
        <StatStrip
          stats={[
            { label: "Human approvals", value: s.human_approvals, hint: `${s.human_rejections} rejected` },
            { label: "Automatic approvals", value: s.automatic_approvals, hint: "Trusted mode allow-list" },
            { label: "Automatic sends", value: s.automatic_sends },
            { label: "Send-gate refusals", value: s.send_gate_refusals },
          ]}
        />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Controls">
          <dl className="-my-1 divide-y text-sm">
            <div className="flex items-center justify-between gap-2 py-2.5">
              <dt className="text-muted-foreground">Kill switch</dt>
              <dd>
                <Badge value={s.kill_switch} tone={s.kill_switch.startsWith("READY") ? "ok" : "bad"} />
              </dd>
            </div>
            <div className="flex items-center justify-between gap-2 py-2.5">
              <dt className="text-muted-foreground">Autonomy mode</dt>
              <dd className="font-semibold capitalize">{s.autonomy_mode}</dd>
            </div>
            <div className="flex items-center justify-between gap-2 py-2.5">
              <dt className="text-muted-foreground">Tool calls refused by the registry</dt>
              <dd className="num">{s.tool_calls_refused}</dd>
            </div>
            <div className="flex items-center justify-between gap-2 py-2.5">
              <dt className="text-muted-foreground">Model spend</dt>
              <dd className="num">
                {usd(s.llm_spent_micro_usd)} of {usd(s.llm_budget_micro_usd)}
              </dd>
            </div>
          </dl>
          <p className="mt-3 text-label text-text-muted">The admin pauses all sending from the Admin page.</p>
        </Panel>
        <Panel title="Guardrail events by code">
          {s.by_code.length === 0 ? (
            <Empty>No guardrail events yet.</Empty>
          ) : (
            <Table head={["Check", "Code", "Count"]} numeric={[2]}>
              {s.by_code.map((c) => (
                <tr key={`${c.check_name}-${c.code}`}>
                  <td className={td}>{c.check_name}</td>
                  <td className={`${td} font-mono text-danger`}>{c.code}</td>
                  <td className={tdNum}>{c.count}</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      </div>

      <Definitions title="What each count is made of" entries={s.sources} />
    </div>
  );
}
