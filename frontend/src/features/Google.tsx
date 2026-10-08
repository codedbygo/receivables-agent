/** HACK-009: the company Google account on the Admin page, and the queue of customer replies read from Gmail. */
import { useState } from "react";
import { z } from "zod";
import { MailOpen, RefreshCw } from "lucide-react";
import { Badge, Button, Empty, ErrorLine, Loading, Notice, PageHeader, Panel } from "@/components/kit";
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
        <div className="mb-3">
          <Notice tone={note.ok ? "success" : "danger"}>{note.text}</Notice>
        </div>
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
      <PageHeader
        title="Incoming replies"
        description="Customer emails from Gmail threads the app started. Accept to record and classify; dismiss out-of-office and similar."
      >
        {canAct && (
          <Button icon={RefreshCw} busy={sync.isPending} onClick={() => sync.mutate(undefined)}>
            Check for replies
          </Button>
        )}
      </PageHeader>
      {sync.data && <Notice>New replies found: {sync.data.replies_found}.</Notice>}
      <ErrorLine error={sync.error ?? accept.error ?? dismiss.error} />
      {accept.data && (
        <Notice tone="success">Recorded and classified as {accept.data.classification ?? "unclassified"}.</Notice>
      )}
      {q.isPending ? (
        <Loading what="incoming replies" />
      ) : q.error ? (
        <ErrorLine error={q.error} />
      ) : q.data.data.length === 0 ? (
        <div className="rounded-xl border bg-card shadow-xs">
          <Empty icon={MailOpen}>No replies waiting. New ones appear here after a sync.</Empty>
        </div>
      ) : (
        <ul aria-label="Incoming replies" className="space-y-3">
          {q.data.data.map((r) => (
            <li key={r.id} className="rounded-xl border bg-card p-5 shadow-xs">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <a href={href({ page: "customer", id: r.customer_id })} className="font-semibold text-foreground underline-offset-4 hover:text-primary hover:underline">
                  {r.customer_name}
                </a>
                <span className="text-sm text-text-muted">
                  {r.from_address} · {day(r.received_at.slice(0, 10))}
                </span>
              </div>
              <p className="mt-1 text-sm text-text-muted">In reply to: {r.message_subject}</p>
              <p className="mt-3 rounded-lg bg-muted/40 p-4 text-sm leading-relaxed whitespace-pre-line">{r.body}</p>
              {canAct && (
                <div className="mt-4 flex gap-2">
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
