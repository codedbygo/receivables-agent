/** HACK-009: the company Google account on the Admin page, and the queue of customer replies read from Gmail. */
import { useState } from "react";
import { z } from "zod";
import { Badge, Button, Empty, ErrorLine, Loading, Panel } from "@/components/kit";
import { href } from "../app/route";
import { api } from "../lib/api";
import { day } from "../lib/format";
import { useAction, useGoogle, useInbox } from "../lib/hooks";
import * as S from "../lib/schemas";

/** What the sign-in round trip said, read once from the URL Google sent the browser back to. */
function callbackNote(): { ok: boolean; text: string } | null {
  const q = new URLSearchParams(window.location.search);
  if (q.get("google") === "connected") return { ok: true, text: "Google is connected." };
  const err = q.get("google_error");
  return err ? { ok: false, text: err } : null;
}

export function GooglePanel({ isAdmin }: { isAdmin: boolean }) {
  const g = useGoogle();
  const [note] = useState(callbackNote);
  const connect = useAction(() => api("/google/connect", z.object({ url: z.string() }), { method: "POST" }));
  const disconnect = useAction(() => api("/google/disconnect", S.GoogleStatus, { method: "POST" }));
  const sync = useAction(() => api("/google/sync", S.GoogleSync, { method: "POST" }));
  if (g.isPending) return <Loading what="the Google connection" />;
  if (g.error) return <ErrorLine error={g.error} />;
  const s = g.data;
  return (
    <Panel
      title="Google (Gmail and Calendar)"
      action={s.connected ? <Badge value={`Connected: ${s.email}`} tone="ok" /> : <Badge value="Not connected" />}
    >
      {note && (
        <p role="status" className={`mb-3 rounded border px-3 py-2 ${note.ok ? "border-info bg-info-subtle text-info" : "border-danger/30 bg-danger-subtle text-danger"}`}>
          {note.text}
        </p>
      )}
      {!s.configured ? (
        <p>
          Google is not set up on the server. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_TOKEN_KEY and GOOGLE_REDIRECT_URI, then
          redeploy (README, Google).
        </p>
      ) : (
        <>
          <p className="mb-3">
            {s.connected
              ? `Promises and follow-ups go to ${s.email}'s calendar.`
              : "Connect the company Google account to put promises and follow-ups in its calendar."}{" "}
            {s.email_provider === "gmail"
              ? "Reminders are sent from Gmail and customer replies are read from it."
              : "Reminders still go out by SMTP (EMAIL_PROVIDER=gmail sends them from Gmail and reads replies)."}
          </p>
          <div className="flex flex-wrap gap-2">
            {isAdmin && !s.connected && (
              <Button variant="primary" busy={connect.isPending} onClick={() => connect.mutate(undefined, { onSuccess: (r) => (window.location.href = r.url) })}>
                Connect Google
              </Button>
            )}
            {s.connected && (
              <Button busy={sync.isPending} onClick={() => sync.mutate(undefined)}>
                Sync now
              </Button>
            )}
            {isAdmin && s.connected && (
              <Button variant="danger" busy={disconnect.isPending} onClick={() => disconnect.mutate(undefined)}>
                Disconnect
              </Button>
            )}
          </div>
          {sync.data && (
            <p role="status" className="mt-3">
              Calendar: {sync.data.calendar.created} added, {sync.data.calendar.removed} removed. New replies found: {sync.data.replies_found}.
            </p>
          )}
        </>
      )}
      <ErrorLine error={connect.error ?? disconnect.error ?? sync.error} />
    </Panel>
  );
}

export function IncomingReplies({ role }: { role: S.Role }) {
  const q = useInbox();
  const sync = useAction(() => api("/google/sync", S.GoogleSync, { method: "POST" }));
  const accept = useAction((id: string) => api(`/google/inbox/${id}/accept`, S.Reply, { method: "POST" }));
  const dismiss = useAction((id: string) => api(`/google/inbox/${id}/dismiss`, S.Inbound, { method: "POST" }));
  const canAct = role !== "viewer";
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-display text-display font-semibold">Incoming replies</h1>
        {canAct && (
          <Button busy={sync.isPending} onClick={() => sync.mutate(undefined)}>
            Check for replies
          </Button>
        )}
      </header>
      <p className="text-text-muted">
        Customer emails found in Gmail threads the app started. Accept one to record it as the customer's reply (it is then classified like a
        pasted reply); dismiss out-of-office and similar messages.
      </p>
      {sync.data && <p role="status">New replies found: {sync.data.replies_found}.</p>}
      <ErrorLine error={sync.error ?? accept.error ?? dismiss.error} />
      {accept.data && (
        <p role="status" className="rounded border border-info bg-info-subtle px-3 py-2 text-info">
          Recorded and classified as {accept.data.classification ?? "unclassified"}.
        </p>
      )}
      {q.isPending ? (
        <Loading what="incoming replies" />
      ) : q.error ? (
        <ErrorLine error={q.error} />
      ) : q.data.data.length === 0 ? (
        <Empty>No replies waiting. New ones appear here after a sync.</Empty>
      ) : (
        <ul aria-label="Incoming replies" className="space-y-3">
          {q.data.data.map((r) => (
            <li key={r.id} className="rounded border border-border bg-surface p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <a href={href({ page: "customer", id: r.customer_id })} className="font-semibold text-link underline-offset-4 hover:underline">
                  {r.customer_name}
                </a>
                <span className="text-sm text-text-muted">
                  {r.from_address} · {day(r.received_at.slice(0, 10))}
                </span>
              </div>
              <p className="mt-1 text-sm text-text-muted">In reply to: {r.message_subject}</p>
              <p className="mt-2 whitespace-pre-line">{r.body}</p>
              {canAct && (
                <div className="mt-3 flex gap-2">
                  <Button variant="primary" busy={accept.isPending && accept.variables === r.id} onClick={() => accept.mutate(r.id)}>
                    Accept<span className="sr-only"> reply from {r.customer_name}</span>
                  </Button>
                  <Button busy={dismiss.isPending && dismiss.variables === r.id} onClick={() => dismiss.mutate(r.id)}>
                    Dismiss<span className="sr-only"> reply from {r.customer_name}</span>
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
