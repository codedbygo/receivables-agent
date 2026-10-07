/** AI Safety Center (HACK-003): counts of real guardrail, approval and send events. No figure here is estimated. */
import { Badge, ErrorLine, Figure, Loading, Panel, Table, td, tdNum } from "@/components/kit";
import { useSafety } from "../lib/hooks";

export function SafetyCenter() {
  const q = useSafety();
  if (q.isPending) return <Loading what="the safety center" />;
  if (q.isError) return <ErrorLine error={q.error} />;
  const s = q.data;
  const usd = (micro: number) => `$${(micro / 1_000_000).toFixed(2)}`;
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-display font-semibold">AI Safety</h1>
        <p className="text-text-muted">Live counts from the guardrail log, approvals and sends. Nothing here is simulated.</p>
      </header>

      <div className="grid grid-cols-2 gap-6 rounded border border-border bg-surface p-4 lg:grid-cols-4">
        <Figure label="Messages checked" value={s.messages_checked} hint={`${s.messages_passed} passed every check`} />
        <Figure label="Incorrect amounts blocked" value={s.incorrect_amounts_blocked} />
        <Figure label="Prompt attacks blocked" value={s.prompt_attacks_blocked} />
        <Figure label="Guardrail events" value={s.guardrail_failures} />
        <Figure label="Human approvals" value={s.human_approvals} hint={`${s.human_rejections} rejected`} />
        <Figure label="Automatic approvals" value={s.automatic_approvals} hint="Trusted mode allow-list" />
        <Figure label="Automatic sends" value={s.automatic_sends} />
        <Figure label="Send-gate refusals" value={s.send_gate_refusals} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Controls">
          <dl className="space-y-2">
            <div className="flex justify-between gap-2">
              <dt>Kill switch</dt>
              <dd>
                <Badge value={s.kill_switch} tone={s.kill_switch.startsWith("READY") ? "ok" : "bad"} />
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Autonomy mode</dt>
              <dd className="font-semibold capitalize">{s.autonomy_mode}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Tool calls refused by the registry</dt>
              <dd className="num">{s.tool_calls_refused}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Model spend</dt>
              <dd className="num">
                {usd(s.llm_spent_micro_usd)} of {usd(s.llm_budget_micro_usd)}
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-label text-text-muted">The admin pauses all sending from the Admin page.</p>
        </Panel>
        <Panel title="Guardrail events by code">
          {s.by_code.length === 0 ? (
            <p className="text-text-muted">No guardrail events yet.</p>
          ) : (
            <Table head={["Check", "Code", "Count"]} numeric={[2]}>
              {s.by_code.map((c) => (
                <tr key={`${c.check_name}-${c.code}`}>
                  <td className={td}>{c.check_name}</td>
                  <td className={td}>{c.code}</td>
                  <td className={tdNum}>{c.count}</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      </div>

      <Panel title="What each count is made of">
        <dl className="grid gap-2 md:grid-cols-2">
          {Object.entries(s.sources).map(([key, text]) => (
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
