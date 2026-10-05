/** S-16 Evaluation: the numbers from the last `make eval`, never typed by hand (US-01-010 to US-01-012). */
import { Badge, Empty, ErrorLine, Figure, Loading, Panel, Table, td } from "../components/kit";
import { ApiError } from "../lib/api";
import { stamp } from "../lib/format";
import { useEval } from "../lib/hooks";

const pct = (s: { passed: number; total: number }) => `${s.passed}/${s.total}`;

export function Evaluation() {
  const q = useEval();
  if (q.isPending) return <Loading what="the evaluation" />;
  if (q.error instanceof ApiError && q.error.code === "NOT_FOUND") {
    return <Empty>No evaluation has run yet. Run make eval, then reload.</Empty>;
  }
  if (q.error) return <ErrorLine error={q.error} />;
  const r = q.data;
  const replies = r.replies;
  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-display text-display font-semibold">Evaluation</h1>
        <p className="text-text-muted">
          Generated {stamp(r.generated_at)} by <span className="font-mono">{r.command}</span> with{" "}
          <span className="font-mono">LLM_MODE={r.mode}</span>. Classifier:{" "}
          {Object.entries(replies.source)
            .map(([k, v]) => `${k} ${v}`)
            .join(", ")}
          .
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Figure label="Classification" value={pct(replies.class)} hint="40 labelled replies" />
        <Figure label="Amount extraction" value={pct(replies.amount)} />
        <Figure label="Date extraction" value={pct(replies.date)} />
        <Figure label="Expected action" value={pct(replies.action)} />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Figure label="Red team rejected" value={pct(r.red_team)} hint="invented amounts, wrong totals, threats" />
        <Figure label="Golden drafts pass" value={pct(r.golden)} />
        {r.scenarios && <Figure label="Trajectory scenarios" value={pct(r.scenarios)} />}
      </div>

      {r.scenarios && (
        <Panel title="Trajectory scenarios">
          <Table head={["Scenario", "Result", "Class", "Tools", "Outcome"]}>
            {r.scenarios.results.map((s) => (
              <tr key={s.id}>
                <td className={`${td} font-mono`}>{s.id}</td>
                <td className={td}>
                  <Badge value={s.ok ? "pass" : "fail"} tone={s.ok ? "ok" : "bad"} />
                </td>
                <td className={td}>{s.actual.class ?? "None"}</td>
                <td className={`${td} font-mono text-label`}>{s.actual.tools.join(" → ") || "none"}</td>
                <td className={td}>
                  <Badge value={s.actual.outcome} />
                </td>
              </tr>
            ))}
          </Table>
        </Panel>
      )}

      <Panel title="Reply misses">
        {(["class", "action", "amount", "date"] as const).every((k) => replies[k].failures.length === 0) ? (
          <Empty>Every labelled reply matched.</Empty>
        ) : (
          <Table head={["Metric", "Reply", "Expected", "Actual"]}>
            {(["class", "action", "amount", "date"] as const).flatMap((k) =>
              replies[k].failures.map((f, i) => (
                <tr key={`${k}-${i}`}>
                  <td className={td}>{k}</td>
                  <td className={`${td} font-mono`}>{String(f.id)}</td>
                  <td className={td}>{String(f.expected)}</td>
                  <td className={td}>{String(f.actual)}</td>
                </tr>
              )),
            )}
          </Table>
        )}
      </Panel>
    </div>
  );
}
