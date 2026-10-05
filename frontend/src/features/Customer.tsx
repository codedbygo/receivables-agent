/** S-07 Customer with S-09 Record reply and S-10 Resolve dispute (US-00-001, US-00-004, US-00-016, US-00-022). */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Badge,
  BandBadge,
  Button,
  Dialog,
  Empty,
  ErrorLine,
  Field,
  Figure,
  inputClass,
  Loading,
  Panel,
  Table,
  td,
  tdNum,
  WhyFactors,
} from "../components/ui";
import { api } from "../lib/api";
import { CallsPanel } from "./Calls";
import { ContactPanel, MemoryPanel } from "./Contact";
import { FollowUpCard } from "./FollowUps";
import { day, inr, stamp } from "../lib/format";
import { useAction, useCustomer, useSettings } from "../lib/hooks";
import * as S from "../lib/schemas";
import { RunDialog } from "./RunDialog";

const ACTOR: Record<string, string> = { ai: "AI", human: "Human", system: "System", customer: "Customer" };
const ICON: Record<string, string> = {
  invoice_due: "📄",
  drafted: "✎",
  guardrail_passed: "✓",
  guardrail_failed: "✗",
  approved: "✔",
  edited: "✎",
  rejected: "✗",
  sent: "✉",
  send_failed: "⚠",
  reply_received: "↩",
  classified: "◆",
  promise_logged: "🤝",
  payment_received: "₹",
  promise_fulfilled: "✓",
  promise_partially_fulfilled: "◐",
  promise_missed: "⚠",
  dispute_opened: "⚑",
  dispute_resolved: "✓",
  dispute_assigned: "→",
  dispute_investigating: "🔍",
  followup_created: "⏰",
  followup_closed: "✓",
  escalated: "⤴",
  escalation_resolved: "✓",
};

export function CustomerPage({ id, role }: { id: string; role: S.Role }) {
  const q = useCustomer(id);
  const flags = useSettings().data;
  const [runId, setRunId] = useState<string | null>(null);
  const [callPrep, setCallPrep] = useState(false);
  const [replyTo, setReplyTo] = useState<S.Message | null>(null);
  const [resolving, setResolving] = useState<{ id: string; invoice: string } | null>(null);
  const run = useAction(() => api("/runs", S.RunBatch, { method: "POST", body: { customer_ids: [id] } }));
  const resend = useAction((mid: string) => api(`/messages/${mid}/resend`, S.Message, { method: "POST" }));
  const link = useAction((number: string) =>
    api(`/invoices/${number}/pay-link`, S.PayLinkToken, { method: "POST" }),
  );
  const check = useAction((pid: string) =>
    api(`/promises/${pid}/check-payment`, S.PromiseCheckResult, { method: "POST" }),
  );
  if (q.isPending) return <Loading what="the customer" />;
  if (q.error) return <ErrorLine error={q.error} />;
  const { customer: c, invoices, priority, timeline, nextAction, runs, promises, disputes, messages, followUps } = q.data;
  const oldest = Math.max(0, ...invoices.filter((i) => i.remaining_paise > 0).map((i) => i.days_overdue));
  const canAct = role !== "viewer";
  const lastSent = messages.find((m) => m.status === "sent") ?? null;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="font-display text-display font-semibold">{c.name}</h1>
          <p className="text-text-muted">
            {c.segment.replaceAll("_", " ")} · {c.credit_terms_days}-day terms · {c.email} · {c.phone}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {role === "admin" && (
            <Button
              variant="primary"
              busy={run.isPending}
              onClick={() => run.mutate(undefined, { onSuccess: (r) => setRunId(r.run_ids[0] ?? null) })}
            >
              Run agent now
            </Button>
          )}
          {canAct && lastSent && <Button onClick={() => setReplyTo(lastSent)}>Record a reply</Button>}
          {canAct && flags?.feature_voice && <Button onClick={() => setCallPrep(true)}>Prepare call</Button>}
        </div>
      </header>
      <ErrorLine error={run.error ?? resend.error ?? check.error ?? link.error} />
      {link.data && (
        <p role="status" className="rounded border border-info bg-info-subtle px-3 py-2 break-all text-info">
          SIMULATED payment link for {link.data.invoice_number}:{" "}
          <a className="underline" href={`#/pay/${link.data.token}`} target="_blank" rel="noreferrer">
            {`${window.location.origin}/#/pay/${link.data.token}`}
          </a>
        </p>
      )}
      {check.data && (
        <p role="status" className="rounded border border-info bg-info-subtle px-3 py-2 text-info">
          {check.data.message}
        </p>
      )}

      <div className="grid grid-cols-2 gap-6 rounded border border-border bg-surface p-4 lg:grid-cols-4">
        <Figure label="Outstanding" value={inr(c.outstanding_paise)} hint={`${inr(c.overdue_paise)} overdue`} />
        <Figure label="Oldest overdue" value={`${oldest} days`} />
        <Figure
          label="Priority"
          value={
            <>
              {priority.score} <BandBadge band={priority.band} />
            </>
          }
        />
        <Figure label="Next action" value={<span className="text-title">{nextAction}</span>} />
      </div>

      <ContactPanel customerId={id} canAct={canAct} />

      <Panel title={`Why is this customer ${priority.band} priority?`}>
        <WhyFactors factors={priority.factors} score={priority.score} />
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Timeline">
          {timeline.length === 0 ? (
            <Empty>Nothing has happened for this customer yet.</Empty>
          ) : (
            <ol className="space-y-3 border-l-2 border-border pl-6">
              {timeline.map((e) => (
                <li key={e.id} className="relative">
                  <span
                    aria-hidden
                    className="absolute -left-9 flex size-6 items-center justify-center rounded-full border border-border bg-surface text-label"
                  >
                    {ICON[e.kind] ?? "•"}
                  </span>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-semibold">{e.summary}</span>
                    {e.amount_paise !== null && <span className="num font-semibold">{inr(e.amount_paise)}</span>}
                  </div>
                  <div className="text-label text-text-muted">
                    {ACTOR[e.actor] ?? e.actor}
                    {e.actor_name ? ` (${e.actor_name})` : ""} · {e.kind.replaceAll("_", " ")} · {stamp(e.occurred_at)}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel title="Invoices">
            <Table head={["Invoice", "Due", "Remaining", "Status"]} numeric={[2]}>
              {invoices.map((i) => (
                <tr key={i.id}>
                  <td className={`${td} font-mono`}>{i.number}</td>
                  <td className={td}>
                    {day(i.due_date)}
                    {i.days_overdue > 0 && i.remaining_paise > 0 && (
                      <span className="block text-label text-danger">{i.days_overdue} days overdue</span>
                    )}
                  </td>
                  <td className={tdNum}>{inr(i.remaining_paise)}</td>
                  <td className={td}>
                    <Badge value={i.status} />
                    {canAct && flags?.feature_payment_link && i.remaining_paise > 0 && (
                      <button type="button" className="mt-1 block text-label text-link underline" onClick={() => link.mutate(i.number)}>
                        Payment link
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </Table>
            <p className="num mt-2 border-t-4 border-double border-border-strong pt-2 text-right font-semibold">
              Total outstanding {inr(c.outstanding_paise)}
            </p>
          </Panel>

          {followUps.some((f) => f.status === "open") && (
            <Panel title="Follow-ups">
              <div className="space-y-3">
                {followUps
                  .filter((f) => f.status === "open")
                  .map((f) => (
                    <FollowUpCard key={f.id} f={f} canAct={canAct} />
                  ))}
              </div>
            </Panel>
          )}

          <Panel title="Promises">
            {promises.length === 0 ? (
              <Empty>No promises recorded.</Empty>
            ) : (
              <ul className="divide-y divide-border">
                {promises.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span>
                      <span className="num font-semibold">{inr(p.amount_paise)}</span> by {day(p.promised_date)}
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge value={p.status} />
                      {canAct && p.status === "pending" && (
                        <Button onClick={() => check.mutate(p.id)} busy={check.isPending}>
                          Check payment
                        </Button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Disputes">
            {disputes.length === 0 ? (
              <Empty>No disputes.</Empty>
            ) : (
              <ul className="divide-y divide-border">
                {disputes.map((d) => (
                  <DisputeItem
                    key={d.id}
                    d={d}
                    canAct={canAct}
                    onResolve={() => setResolving({ id: d.id, invoice: d.invoice_number })}
                  />
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <CallsPanel customerId={id} canAct={canAct} voiceOn={Boolean(flags?.feature_voice)} />

      <MemoryPanel customerId={id} canAct={canAct} />

      <Panel title="Messages">
        {messages.length === 0 ? (
          <Empty>No messages yet. Run the agent to draft a reminder.</Empty>
        ) : (
          <Table head={["Subject", "Kind", "Status", "Sent", "Action"]}>
            {messages.map((m) => (
              <tr key={m.id}>
                <td className={td}>{m.subject}</td>
                <td className={td}>
                  {m.kind.replaceAll("_", " ")} · {m.tone} · {m.channel}
                  {m.status === "sent" && (
                    <span className="ml-1">
                      <Badge value={m.simulated ? "SIMULATED" : "REAL"} tone={m.simulated ? "wait" : "ok"} />
                    </span>
                  )}
                </td>
                <td className={td}>
                  <Badge value={m.status} />
                  {m.last_error && <span className="block font-mono text-label text-danger">{m.last_error}</span>}
                </td>
                <td className={td}>{m.sent_at ? stamp(m.sent_at) : "Not sent"}</td>
                <td className={td}>
                  {canAct && m.status === "sent" && <Button onClick={() => setReplyTo(m)}>Record reply</Button>}
                  {canAct && m.status === "failed" && <Button onClick={() => resend.mutate(m.id)}>Resend</Button>}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>

      <Panel title="Agent runs">
        {runs.length === 0 ? (
          <Empty>The agent has not run for this customer.</Empty>
        ) : (
          <Table head={["Started", "Trigger", "Outcome", "Tool calls", "Trajectory"]} numeric={[3]}>
            {runs.map((r) => (
              <tr key={r.id}>
                <td className={td}>{stamp(r.started_at)}</td>
                <td className={td}>{r.trigger}</td>
                <td className={td}>{r.outcome ? <Badge value={r.outcome} /> : "Running"}</td>
                <td className={tdNum}>{r.tool_call_count} of 4</td>
                <td className={td}>
                  <Button onClick={() => setRunId(r.id)}>View</Button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>

      {replyTo && <ReplyDialog message={replyTo} onClose={() => setReplyTo(null)} onRun={setRunId} />}
      {callPrep && <CallPrepDialog customerId={id} onClose={() => setCallPrep(false)} />}
      {resolving && <ResolveDialog dispute={resolving} onClose={() => setResolving(null)} />}
      <RunDialog runId={runId} onClose={() => setRunId(null)} />
    </div>
  );
}

function ReplyDialog({
  message,
  onClose,
  onRun,
}: {
  message: S.Message;
  onClose: () => void;
  onRun: (id: string) => void;
}) {
  const [body, setBody] = useState("");
  const send = useAction(() => api("/replies", S.Reply, { method: "POST", body: { message_id: message.id, body } }));
  const r = send.data;
  return (
    <Dialog title={`Customer reply to “${message.subject}”`} open onClose={onClose}>
      {r ? (
        <div className="space-y-3">
          <p>
            Classified as <Badge value={r.classification ?? "unclassified"} tone="info" />
            {r.confidence !== null && <span className="num text-text-muted"> confidence {r.confidence.toFixed(2)}</span>}
          </p>
          <dl className="grid grid-cols-2 gap-1 text-label">
            <dt className="text-text-muted">Amount</dt>
            <dd className="num">{r.amount_paise !== null ? inr(r.amount_paise) : "None"}</dd>
            <dt className="text-text-muted">Date</dt>
            <dd>{r.stated_date ? day(r.stated_date) : "None"}</dd>
            <dt className="text-text-muted">Invoices</dt>
            <dd className="font-mono">{r.invoice_refs.join(", ") || "None"}</dd>
            <dt className="text-text-muted">Action</dt>
            <dd>
              {r.recommended_action?.replaceAll("_", " ") ?? "None"}
              {r.needs_review ? " (needs a human)" : ""}
            </dd>
          </dl>
          <p className="text-label text-text-muted">
            Amounts and dates were parsed and checked in code; the reply text is treated as untrusted.
          </p>
          <div className="flex justify-end gap-2">
            {r.agent_run_id && (
              <Button
                onClick={() => {
                  onRun(r.agent_run_id ?? "");
                  onClose();
                }}
              >
                View run
              </Button>
            )}
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send.mutate(undefined);
          }}
        >
          <Field label="Paste what the customer wrote">
            <textarea
              className={`${inputClass} h-40`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
              maxLength={5000}
              autoFocus
            />
          </Field>
          <ErrorLine error={send.error} />
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" busy={send.isPending} disabled={!body.trim()}>
              Record and classify
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

const STEPS = ["open", "assigned", "investigating", "resolved"] as const;
const TEAM: Record<string, string> = {
  billing: "Billing",
  operations: "Operations",
  sales: "Sales",
  legal_contracts: "Legal and contracts",
  collections: "Collections",
};

/** HACK-003 F7: category and team come from fixed rules; people move the dispute on and only people resolve it. */
function DisputeItem({ d, canAct, onResolve }: { d: S.Dispute; canAct: boolean; onResolve: () => void }) {
  const move = useAction((to: "assigned" | "investigating") =>
    api(`/disputes/${d.id}/transition`, S.Dispute, { method: "POST", body: { to } }),
  );
  const at = STEPS.indexOf(d.status);
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono">{d.invoice_number}</span>
        <span className="flex flex-wrap gap-1">
          <Badge value={d.category.replaceAll("_", " ")} tone="info" />
          {d.assigned_team && <Badge value={TEAM[d.assigned_team] ?? d.assigned_team} tone="plain" />}
        </span>
      </div>
      <ol className="mt-1 flex flex-wrap gap-1 text-label" aria-label="Dispute status">
        {STEPS.map((step, i) => (
          <li
            key={step}
            aria-current={i === at ? "step" : undefined}
            className={`rounded border px-2 ${i <= at ? "border-accent bg-accent-subtle font-semibold" : "border-border text-text-muted"}`}
          >
            {step.toUpperCase()}
          </li>
        ))}
      </ol>
      <p className="mt-1 text-label whitespace-pre-line text-text-muted">{d.reason}</p>
      <details className="text-label">
        <summary className="cursor-pointer text-link">Why this team?</summary>
        <p className="text-text-muted">
          Category {d.category.replaceAll("_", " ")} from fixed rules over the customer&apos;s words; routed by the policy
          table dispute_routing to {TEAM[d.assigned_team ?? "collections"]}. The AI never resolves a dispute.
        </p>
      </details>
      {d.resolution_note && <p className="text-label">Resolved: {d.resolution_note}</p>}
      {canAct && d.status !== "resolved" && (
        <div className="mt-1 flex flex-wrap gap-2">
          {d.status !== "investigating" && (
            <Button onClick={() => move.mutate("investigating")} busy={move.isPending}>
              Start investigation
            </Button>
          )}
          <Button onClick={onResolve}>Resolve</Button>
        </div>
      )}
      <ErrorLine error={move.error} />
    </li>
  );
}

function ResolveDialog({ dispute, onClose }: { dispute: { id: string; invoice: string }; onClose: () => void }) {
  const [note, setNote] = useState("");
  const resolve = useAction(() =>
    api(`/disputes/${dispute.id}/resolve`, S.DisputeResolved, { method: "POST", body: { note: note.trim() } }),
  );
  return (
    <Dialog title={`Resolve the dispute on ${dispute.invoice}`} open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          resolve.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <Field label="Resolution note (shown on the timeline; reminders on this invoice resume)">
          <input
            className={inputClass}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            required
            maxLength={500}
            autoFocus
          />
        </Field>
        <ErrorLine error={resolve.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={resolve.isPending} disabled={!note.trim()}>
            Resolve dispute
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/** Prepare Call (US-00-025): a sheet only; no call is placed. */
function CallPrepDialog({ customerId, onClose }: { customerId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["call-prep", customerId], queryFn: () => api(`/customers/${customerId}/call-prep`, S.CallPrep) });
  return (
    <Dialog title="Prepare call" open onClose={onClose}>
      {q.isPending && <Loading what="the call sheet" />}
      <ErrorLine error={q.error} />
      {q.data && (
        <div className="space-y-4">
          <p className="font-semibold">{q.data.summary}</p>
          <ol className="list-decimal space-y-1 pl-5">
            {q.data.talking_points.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ol>
          <p className={q.data.verified ? "text-success" : "text-danger"}>
            {q.data.verified ? "✓ Every figure on this sheet matches the ledger" : "Error: a figure on this sheet does not match the ledger"}
          </p>
          <p className="text-label text-text-muted">Call sheet only: no call is placed (voice is simulated).</p>
          <div className="text-right">
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
