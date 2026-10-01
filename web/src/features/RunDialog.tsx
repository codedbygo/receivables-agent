/** S-08 Agent run: the trajectory, step by step, with redacted arguments (US-00-008). */
import { Badge, Dialog, ErrorLine, Loading, Table, td } from "../components/ui";
import { stamp } from "../lib/format";
import { useRun } from "../lib/hooks";

export function RunDialog({ runId, onClose }: { runId: string | null; onClose: () => void }) {
  const q = useRun(runId);
  return (
    <Dialog title="Agent run" open={runId !== null} onClose={onClose}>
      {q.isPending && <Loading what="the run" />}
      <ErrorLine error={q.error} />
      {q.data && (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-label md:grid-cols-4">
            <dt className="text-text-muted">Customer</dt>
            <dd>{q.data.customer_name}</dd>
            <dt className="text-text-muted">Outcome</dt>
            <dd>{q.data.outcome ? <Badge value={q.data.outcome} /> : "Running"}</dd>
            <dt className="text-text-muted">Tool calls</dt>
            <dd className="num">{q.data.tool_call_count} of 4</dd>
            <dt className="text-text-muted">Trigger</dt>
            <dd>{q.data.trigger}</dd>
            <dt className="text-text-muted">Tone, channel</dt>
            <dd>{[q.data.tone, q.data.channel].filter(Boolean).join(", ") || "None"}</dd>
            <dt className="text-text-muted">Started</dt>
            <dd>{stamp(q.data.started_at)}</dd>
          </dl>
          {q.data.reason && <p className="whitespace-pre-line text-text-muted">Reason: {q.data.reason}</p>}
          <Table head={["#", "Role", "Tool", "Arguments (redacted)", "Result"]}>
            {q.data.steps.map((s) => (
              <tr key={s.seq}>
                <td className={td}>{s.seq}</td>
                <td className={td}>{s.role.replaceAll("_", " ")}</td>
                <td className={`${td} font-mono`}>{s.tool_name}</td>
                <td className={`${td} font-mono text-label break-all`}>{JSON.stringify(s.arguments_redacted)}</td>
                <td className={td}>
                  {s.error_code ? <span className="font-mono text-danger">{s.error_code}</span> : null}{" "}
                  <span className="text-label break-all">{s.result_summary}</span>
                </td>
              </tr>
            ))}
          </Table>
          <div className="text-right">
            <button type="button" onClick={onClose} className="text-link underline">Close</button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
