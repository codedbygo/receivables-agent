/** HACK-003 F2 and F3 on the customer page: which channel next (with its reasons), the customer's preferences
 * and consent, and the interaction memory with internal notes. */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { Badge, Button, Dialog, Empty, ErrorLine, Field, Figure, inputClass, Loading, Panel } from "../components/ui";
import { api } from "../lib/api";
import { day, inr } from "../lib/format";
import { useAction } from "../lib/hooks";
import * as S from "../lib/schemas";

const LABEL: Record<string, string> = {
  email: "Email",
  whatsapp: "WhatsApp",
  sms: "SMS",
  voice: "Voice call",
  human: "A person",
};
const label = (c: string | null) => (c ? (LABEL[c] ?? c) : "None yet");

export function ContactPanel({ customerId, canAct }: { customerId: string; canAct: boolean }) {
  const q = useQuery({
    queryKey: ["channels", customerId],
    queryFn: () => api(`/customers/${customerId}/channels`, S.ChannelPlan),
  });
  const [editing, setEditing] = useState(false);
  if (q.isPending) return <Loading what="the channel plan" />;
  if (q.isError) return <ErrorLine error={q.error} />;
  const p = q.data;
  return (
    <Panel title="Contact" action={canAct ? <Button onClick={() => setEditing(true)}>Preferences</Button> : undefined}>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <Figure label="Preferred" value={<span className="text-title">{label(p.preferred_channel)}</span>} />
        <Figure label="Last contacted" value={<span className="text-title">{label(p.last_channel)}</span>} />
        <Figure
          label="Last contact"
          value={<span className="text-title">{p.last_contact_on ? day(p.last_contact_on) : "Never"}</span>}
        />
        <Figure label="Response" value={<span className="text-title capitalize">{p.response_status}</span>} />
        <Figure
          label="Next recommended"
          value={<span className="text-title">{label(p.recommended_channel)}</span>}
          hint={p.next_step_channel && p.next_step_on ? `then ${label(p.next_step_channel)} on ${day(p.next_step_on)}` : undefined}
        />
      </div>
      <details className="mt-2 text-label">
        <summary className="cursor-pointer text-link">Why this channel?</summary>
        <ul className="mt-1 list-disc pl-5 text-text-muted">
          {p.factors.map((f) => (
            <li key={f}>{f}</li>
          ))}
          <li>Nothing is sent on any channel until a person approves it and sending is on.</li>
        </ul>
      </details>
      {canAct && <PortalLinkControl customerId={customerId} />}
      {editing && <PreferencesDialog customerId={customerId} plan={p} onClose={() => setEditing(false)} />}
    </Panel>
  );
}

function PreferencesDialog({ customerId, plan, onClose }: { customerId: string; plan: S.ChannelPlan; onClose: () => void }) {
  const [preferred, setPreferred] = useState(plan.preferred_channel ?? "email");
  const [consent, setConsent] = useState({ whatsapp: false, sms: false, voice: false });
  const save = useAction(() =>
    api(`/customers/${customerId}/contact-preferences`, S.ChannelPlan, {
      method: "PUT",
      body: { preferred_channel: preferred, consent },
    }),
  );
  return (
    <Dialog title="Contact preferences" open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <fieldset className="space-y-1">
          <legend className="font-semibold">The customer agreed to (email is always on)</legend>
          {(["whatsapp", "sms", "voice"] as const).map((c) => (
            <label key={c} className="flex items-center gap-2">
              <input type="checkbox" checked={consent[c]} onChange={(e) => setConsent({ ...consent, [c]: e.target.checked })} />
              {LABEL[c]}
            </label>
          ))}
        </fieldset>
        <Field label="Preferred channel">
          <select className={inputClass} value={preferred} onChange={(e) => setPreferred(e.target.value)}>
            {["email", "whatsapp", "sms", "voice"].map((c) => (
              <option key={c} value={c}>
                {LABEL[c]}
              </option>
            ))}
          </select>
        </Field>
        <ErrorLine error={save.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function MemoryPanel({ customerId, canAct }: { customerId: string; canAct: boolean }) {
  const q = useQuery({ queryKey: ["memory", customerId], queryFn: () => api(`/customers/${customerId}/memory`, S.Memory) });
  const [note, setNote] = useState("");
  const add = useAction(() => api(`/customers/${customerId}/notes`, S.Note, { method: "POST", body: { body: note.trim() } }));
  if (q.isPending) return <Loading what="the customer memory" />;
  if (q.isError) return <ErrorLine error={q.error} />;
  const m = q.data;
  return (
    <Panel title="Customer memory">
      {m.promise_recall && (
        <p className="mb-3 rounded border border-warning bg-warning-subtle px-3 py-2">
          <span className="font-semibold">What the AI will remind them of: </span>
          {m.promise_recall}
        </p>
      )}
      {m.items.length === 0 ? (
        <Empty>No interactions yet.</Empty>
      ) : (
        <ol className="max-h-72 space-y-1 overflow-y-auto">
          {m.items.map((i, n) => (
            <li key={`${i.on}-${i.kind}-${n}`} className="flex flex-wrap gap-2">
              <span className="num w-24 text-text-muted">{day(i.on)}</span>
              <Badge value={i.source} tone="plain" />
              <span>{i.summary}</span>
              {i.channel && <span className="text-text-muted">via {label(i.channel)}</span>}
              {i.amount_paise !== null && <span className="num font-semibold">{inr(i.amount_paise)}</span>}
            </li>
          ))}
        </ol>
      )}
      <p className="mt-2 text-label text-text-muted">
        Built from ledger rows and fixed summaries. The AI reads this list without the customer&apos;s own words and
        without the notes below; amounts always come from the ledger.
      </p>
      <h3 className="mt-4 font-semibold">Internal notes</h3>
      {m.notes.length === 0 ? (
        <p className="text-text-muted">No notes.</p>
      ) : (
        <ul className="divide-y divide-border">
          {m.notes.map((n) => (
            <li key={n.id} className="py-1">
              <p className="whitespace-pre-line">{n.body}</p>
              <p className="text-label text-text-muted">{n.author ?? "Unknown"}</p>
            </li>
          ))}
        </ul>
      )}
      {canAct && (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined, { onSuccess: () => setNote("") });
          }}
        >
          <label className="sr-only" htmlFor={`note-${customerId}`}>
            New internal note
          </label>
          <input
            id={`note-${customerId}`}
            className={inputClass}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
            placeholder="Internal note (never sent to the customer or the AI)"
          />
          <Button type="submit" busy={add.isPending} disabled={!note.trim()}>
            Add
          </Button>
        </form>
      )}
      <ErrorLine error={add.error} />
    </Panel>
  );
}

/** HACK-003 F6: a 7-day link to the customer portal. The token is shown once; only its hash is stored. */
function PortalLinkControl({ customerId }: { customerId: string }) {
  const create = useAction(() => api(`/customers/${customerId}/portal-link`, S.PortalLink, { method: "POST" }));
  const revoke = useAction(() =>
    api(`/customers/${customerId}/portal-links/revoke`, z.object({ revoked: z.number() }), { method: "POST" }),
  );
  const url = create.data ? `${window.location.origin}/${create.data.path}` : null;
  return (
    <div className="mt-3 border-t border-border pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">Customer portal</span>
        <Button onClick={() => create.mutate(undefined)} busy={create.isPending}>
          Create link
        </Button>
        <Button onClick={() => revoke.mutate(undefined)} busy={revoke.isPending}>
          Revoke all links
        </Button>
        {revoke.data && <span className="text-label text-text-muted">{revoke.data.revoked} revoked</span>}
      </div>
      {url && create.data && (
        <p className="mt-2 text-label">
          Send this link to the customer (shown once, valid until {day(create.data.expires_at)}):{" "}
          <a className="break-all font-mono text-link underline" href={url}>
            {url}
          </a>
        </p>
      )}
      <ErrorLine error={create.error ?? revoke.error} />
    </div>
  );
}
