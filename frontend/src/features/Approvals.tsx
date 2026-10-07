/** S-03 Approvals with S-04 Edit and S-05 Reject (US-00-009, US-00-010, US-01-016).
Every draft shows its guardrail report; edited text is verified again by the API before it is saved. */
import { useEffect, useState } from "react";
import { href } from "../app/route";
import { Badge, Button, Dialog, Empty, ErrorLine, Field, inputClass, Loading, Panel } from "../components/kit";
import { api } from "../lib/api";
import { day, inr, stamp } from "../lib/format";
import { useAction, useCustomer, useMessages, useSettings } from "../lib/hooks";
import * as S from "../lib/schemas";
import { RunDialog } from "./RunDialog";

export function Approvals({ role }: { role: S.Role }) {
  const q = useMessages("pending_approval");
  const settings = useSettings();
  const [picked, setPicked] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"edit" | "reject" | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [confirmBatch, setConfirmBatch] = useState(false); // HACK-004: a batch sends to many customers at once
  const queue = q.data?.data ?? [];
  const current = queue.find((m) => m.id === picked) ?? queue[0] ?? null;
  const canAct = role !== "viewer";

  const approve = useAction((m: S.Message) =>
    api(`/messages/${m.id}/approve`, S.Message, { method: "POST", headers: { "If-Match": String(m.version) } }),
  );
  // Each draft at the version on screen: one changed since it was shown refuses the batch (STALE_DRAFT).
  const batch = useAction((ms: S.Message[]) =>
    api("/messages/approve-batch", S.page(S.Message), {
      method: "POST",
      body: { messages: ms.map((m) => ({ id: m.id, version: m.version })) },
    }),
  );

  // Keyboard: J/K move, A approve, E edit, R reject (DESIGN.md). Synchronises with the document, not state.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (dialog || runId || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.metaKey || e.ctrlKey || e.altKey || !current) return;
      const i = queue.indexOf(current);
      const k = e.key.toLowerCase();
      if (k === "j") setPicked(queue[Math.min(i + 1, queue.length - 1)]?.id ?? null);
      else if (k === "k") setPicked(queue[Math.max(i - 1, 0)]?.id ?? null);
      else if (k === "a" && canAct && current.verified) approve.mutate(current);
      else if (k === "e" && canAct) setDialog("edit");
      else if (k === "r" && canAct) setDialog("reject");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (q.isPending) return <Loading what="the approval queue" />;
  if (q.error) return <ErrorLine error={q.error} />;
  const assisted = settings.data?.autonomy_mode === "assisted";

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-display font-semibold">Approvals</h1>
        {assisted && canAct && queue.length > 0 && (
          <Button onClick={() => setConfirmBatch(true)} busy={batch.isPending}>
            Approve all verified ({queue.filter((m) => m.verified).length})
          </Button>
        )}
      </header>
      <Dialog title="Approve and send these drafts?" open={confirmBatch} onClose={() => setConfirmBatch(false)}>
        <p>Each draft below goes to its customer as soon as sending is on. This cannot be undone.</p>
        <ul className="my-3 list-disc pl-5">
          {queue
            .filter((m) => m.verified)
            .map((m) => (
              <li key={m.id}>
                {m.customer_name}: {m.subject} ({m.channel})
              </li>
            ))}
        </ul>
        <div className="flex justify-end gap-2">
          <Button onClick={() => setConfirmBatch(false)}>Cancel</Button>
          <Button
            variant="primary"
            busy={batch.isPending}
            onClick={() => {
              setConfirmBatch(false);
              batch.mutate(queue.filter((m) => m.verified));
            }}
          >
            Approve and send {queue.filter((m) => m.verified).length}
          </Button>
        </div>
      </Dialog>
      <ErrorLine error={approve.error ?? batch.error} />
      {settings.data && !settings.data.sending_enabled && (
        <p role="status" className="rounded border border-warning bg-warning-subtle px-3 py-2 text-warning">
          Sending is paused by the kill switch. Approved messages wait until an admin turns sending back on.
        </p>
      )}
      {queue.length === 0 ? (
        <Empty>No drafts wait for approval. The next run adds them here.</Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[20rem_1fr_18rem]">
          <ul aria-label="Drafts" className="divide-y divide-border rounded border border-border bg-surface">
            {queue.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  aria-current={m.id === current?.id ? "true" : undefined}
                  onClick={() => setPicked(m.id)}
                  className="block min-h-11 w-full px-3 py-2 text-left hover:bg-bg-subtle aria-[current=true]:bg-accent-subtle"
                >
                  <span className="block font-semibold">{m.customer_name}</span>
                  <span className="text-label text-text-muted">
                    {m.kind.replaceAll("_", " ")} · {m.tone} · {m.invoice_numbers.join(", ") || "no invoices"}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {current && (
            <article className="min-w-0 rounded-xl border bg-card p-5 shadow-xs">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <a className="font-semibold font-medium text-link underline-offset-4 hover:underline" href={href({ page: "customer", id: current.customer_id })}>
                  {current.customer_name}
                </a>
                <Badge value={current.status} />
                <span className="text-label text-text-muted">
                  v{current.version} · {current.channel} · drafted {stamp(current.created_at)}
                </span>
              </div>
              <h2 className="mb-3 font-display text-title font-semibold">{current.subject}</h2>
              <div className="num rounded border border-border bg-bg p-4 font-mono text-label whitespace-pre-line">
                {current.body}
              </div>
              {canAct && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button variant="primary" kbd="A" onClick={() => approve.mutate(current)} busy={approve.isPending} disabled={!current.verified}>
                    Approve
                  </Button>
                  <Button kbd="E" onClick={() => setDialog("edit")}>Edit</Button>
                  <Button variant="danger" kbd="R" onClick={() => setDialog("reject")}>Reject</Button>
                  {current.agent_run_id && <Button onClick={() => setRunId(current.agent_run_id)}>View run</Button>}
                </div>
              )}
            </article>
          )}

          {current && <DraftContext customerId={current.customer_id} />}
          {current && <GuardrailReport checks={current.guardrail_report} verified={current.verified} key={current.id + current.version} />}
        </div>
      )}
      {current && dialog === "edit" && <EditDialog message={current} onClose={() => setDialog(null)} />}
      {current && dialog === "reject" && <RejectDialog message={current} onClose={() => setDialog(null)} />}
      <RunDialog runId={runId} onClose={() => setRunId(null)} />
    </div>
  );
}

/** What the approver decides with (brief 4.11): outstanding, open invoices with days overdue, why this customer. */
function DraftContext({ customerId }: { customerId: string }) {
  const q = useCustomer(customerId);
  if (!q.data) return <Loading what="the customer's ledger" />;
  const { customer, invoices, priority } = q.data;
  return (
    <Panel title="Draft context">
      <p className="num font-semibold">Outstanding {inr(customer.outstanding_paise)}</p>
      <ul className="mt-2 space-y-1 text-label">
        {invoices
          .filter((i) => i.remaining_paise > 0)
          .map((i) => (
            <li key={i.id} className="flex flex-wrap justify-between gap-2">
              <span className="font-mono">{i.number}</span>
              <span className="num">{inr(i.remaining_paise)}</span>
              <span className={i.days_overdue > 0 ? "text-danger" : "text-text-muted"}>
                {i.days_overdue > 0 ? `${i.days_overdue} days overdue` : `due ${day(i.due_date)}`}
              </span>
            </li>
          ))}
      </ul>
      <p className="mt-3 font-semibold">
        Priority {priority.score} {priority.band}
      </p>
      <ul className="list-disc pl-5 text-label">
        {priority.reasons.map((r) => (
          <li key={r.code}>{r.text}</li>
        ))}
      </ul>
    </Panel>
  );
}

export function GuardrailReport({ checks, verified }: { checks: S.Check[]; verified: boolean }) {
  return (
    <aside aria-label="Guardrail report" className="rounded-xl border bg-card p-5 shadow-xs">
      <h2 className="mb-2 font-display text-title font-semibold">Guardrail report</h2>
      <p className={`mb-3 font-semibold ${verified ? "text-success" : "text-danger"}`}>
        {verified ? "✓ Every figure matches the ledger" : "Error: this text has not passed the guardrails"}
      </p>
      <ul className="space-y-1 text-label">
        {checks.map((c, i) => (
          <li key={`${c.check}-${c.token}-${i}`} className="tick flex gap-2" style={{ animationDelay: `${i * 60}ms` }}>
            <span aria-hidden className={c.ok ? "text-success" : "text-danger"}>{c.ok ? "✓" : "✗"}</span>
            <span className="min-w-0">
              <span className="text-text-muted">{c.check}</span> <span className="num font-mono">{c.token}</span>{" "}
              {c.ok ? (
                <span className="text-success">matches ledger</span>
              ) : (
                <span className="text-danger">
                  <span className="font-mono">{c.code}</span>
                  {c.expected ? ` (ledger: ${c.expected})` : ""}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function EditDialog({ message, onClose }: { message: S.Message; onClose: () => void }) {
  const whatsapp = useSettings().data?.feature_whatsapp ?? false;
  const [channel, setChannel] = useState(message.channel === "whatsapp" ? "whatsapp" : "email");
  const [subject, setSubject] = useState(message.subject);
  const [body, setBody] = useState(message.body);
  const save = useAction(() =>
    api(`/messages/${message.id}`, S.Message, {
      method: "PATCH",
      body: { subject: subject.trim(), body, ...(whatsapp ? { channel } : {}) },
      headers: { "If-Match": String(message.version) },
    }),
  );
  return (
    <Dialog title={`Edit draft for ${message.customer_name}`} open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <Field label="Subject">
          <input className={inputClass} value={subject} onChange={(e) => setSubject(e.target.value)} required maxLength={200} />
        </Field>
        {whatsapp && (
          <Field label="Channel">
            <select className={inputClass} value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="email">Email</option>
              <option value="whatsapp">WhatsApp (simulated)</option>
            </select>
          </Field>
        )}
        <Field label="Message (every amount, invoice and date is checked against the ledger on save)">
          <textarea className={`${inputClass} num h-72 font-mono text-label`} value={body} onChange={(e) => setBody(e.target.value)} required maxLength={5000} />
        </Field>
        <ErrorLine error={save.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={save.isPending}>Save and re-verify</Button>
        </div>
      </form>
    </Dialog>
  );
}

function RejectDialog({ message, onClose }: { message: S.Message; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const reject = useAction(() =>
    api(`/messages/${message.id}/reject`, S.Message, { method: "POST", body: { reason: reason.trim() } }),
  );
  return (
    <Dialog title={`Reject draft for ${message.customer_name}`} open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          reject.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <Field label="Reason (the next run can learn from it)">
          <input className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} required maxLength={500} autoFocus />
        </Field>
        <ErrorLine error={reject.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="danger" busy={reject.isPending} disabled={!reason.trim()}>Reject draft</Button>
        </div>
      </form>
    </Dialog>
  );
}
