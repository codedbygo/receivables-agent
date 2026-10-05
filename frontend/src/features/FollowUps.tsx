/** Missed-promise follow-ups (HACK-003 F5): promised, date and received come from the ledger; the recommended
 * action and the reasons are rules, never model output. Closing one needs a note. */
import { useState } from "react";
import { href } from "../app/route";
import { Badge, Button, Dialog, ErrorLine, Field, inputClass } from "../components/ui";
import { api } from "../lib/api";
import { day, inr } from "../lib/format";
import { useAction } from "../lib/hooks";
import * as S from "../lib/schemas";

type FollowUp = S.FollowUp;

export function FollowUpCard({ f, canAct, showCustomer }: { f: FollowUp; canAct: boolean; showCustomer?: boolean }) {
  const [closing, setClosing] = useState(false);
  const title = f.kind === "missed_promise" ? "Missed promise" : "Promise partly kept";
  return (
    <article className="rounded border border-danger bg-surface p-3" aria-label={`${title}, ${f.customer_name}`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">
          {title}
          {showCustomer && (
            <>
              {": "}
              <a href={href({ page: "customer", id: f.customer_id })} className="text-link underline">
                {f.customer_name}
              </a>
            </>
          )}
        </h3>
        <Badge value={f.promise_status.replace("_", " ").toUpperCase()} tone="bad" />
      </header>
      <dl className="mt-2 grid grid-cols-3 gap-2">
        <div>
          <dt className="text-label text-text-muted">Promised</dt>
          <dd className="num font-semibold">{inr(f.promised_paise)}</dd>
        </div>
        <div>
          <dt className="text-label text-text-muted">Promise date</dt>
          <dd className="num">{day(f.promised_date)}</dd>
        </div>
        <div>
          <dt className="text-label text-text-muted">Received</dt>
          <dd className="num">{inr(f.received_paise)}</dd>
        </div>
      </dl>
      <p className="mt-2">
        <span className="text-label text-text-muted">Recommended action: </span>
        {f.recommended_action}
      </p>
      <details className="mt-1 text-label">
        <summary className="cursor-pointer text-link">Why?</summary>
        <ul className="mt-1 list-disc pl-5 text-text-muted">
          <li>
            The promise of {inr(f.promised_paise)} was due on {day(f.promised_date)}; matched payments received by then
            total {inr(f.received_paise)}.
          </li>
          <li>Rule: a promise whose date has passed without full payment is missed or partly kept (no grace days).</li>
          <li>
            {f.message_id
              ? "A follow-up draft is waiting in Approvals; nothing is sent until a person approves it."
              : "In Manual mode only the task is created; run the agent or write to the customer from here."}
          </li>
        </ul>
      </details>
      {f.status === "open" && (
        <div className="mt-2 flex flex-wrap gap-2">
          {f.message_id && (
            <a className="text-link underline" href={href({ page: "approvals" })}>
              Review the follow-up draft
            </a>
          )}
          {canAct && <Button onClick={() => setClosing(true)}>Mark done</Button>}
        </div>
      )}
      {closing && <CloseDialog f={f} onClose={() => setClosing(false)} />}
    </article>
  );
}

function CloseDialog({ f, onClose }: { f: FollowUp; onClose: () => void }) {
  const [note, setNote] = useState("");
  const close = useAction(() =>
    api(`/follow-ups/${f.id}/close`, S.FollowUp, { method: "POST", body: { status: "done", note: note.trim() } }),
  );
  return (
    <Dialog title={`Close the follow-up for ${f.customer_name}`} open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          close.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <Field label="What happened (shown on the timeline)">
          <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} required maxLength={500} autoFocus />
        </Field>
        <ErrorLine error={close.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={close.isPending} disabled={!note.trim()}>
            Mark done
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
