/** AI voice calls on the customer page (HACK-003 F1). Every AI line was rendered from the ledger and verified before it
 * was spoken; the customer's words only choose a fixed intent. A SIMULATED call rings no phone: a collector types the
 * customer's side to test the flow. */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Badge, Button, Empty, ErrorLine, Panel } from "@/components/kit";
import { api } from "../lib/api";
import { stamp } from "../lib/format";
import { useAction } from "../lib/hooks";
import * as S from "../lib/schemas";

const INTENT: Record<string, string> = {
  promise: "Promise to pay: amount and date parsed from the customer's words; logged as a promise",
  dispute: "Dispute: invoice named by the customer, category by fixed rules, routed by policy",
  invoice_request: "Invoice request: a statement draft now waits for approval",
  payment_link: "Payment link request: handed to a collector",
  payment_claim: "Claims to have paid: checked against the bank feed, never marked paid on the claim",
  wrong_number: "Wrong number: escalated to fix the contact details",
  unavailable: "Unavailable: call again tomorrow",
  balance_question: "Asked about the balance: answered from the ledger",
  injection: "Instruction-like speech: ignored, escalated, logged in the Safety Center",
  yes: "Yes",
  no: "No",
  other: "Not clear: asked again (at most twice)",
};

export function CallsPanel({ customerId, canAct, voiceOn }: { customerId: string; canAct: boolean; voiceOn: boolean }) {
  const calls = useQuery({
    queryKey: ["calls", customerId],
    queryFn: () => api(`/calls?filter[customer_id]=${customerId}`, S.page(S.Call)),
  });
  const start = useAction(() => api("/calls", S.Call, { method: "POST", body: { customer_id: customerId } }));
  const active = calls.data?.data.find((c) => c.status === "in_progress");
  return (
    <Panel
      title="Voice calls"
      action={
        canAct && voiceOn && !active ? (
          <Button variant="primary" onClick={() => start.mutate(undefined)} busy={start.isPending}>
            Call with AI
          </Button>
        ) : undefined
      }
    >
      <ErrorLine error={start.error} />
      {!voiceOn && <p className="text-text-muted">Voice calls are switched off (Admin, feature flags).</p>}
      {calls.isPending ? null : calls.isError ? (
        <ErrorLine error={calls.error} />
      ) : calls.data.data.length === 0 ? (
        <Empty>No calls yet.</Empty>
      ) : (
        <div className="space-y-4">
          {calls.data.data.map((c) => (
            <CallView key={c.id} call={c} canAct={canAct} />
          ))}
        </div>
      )}
    </Panel>
  );
}

/** The browser's built-in speech recognition (Web Speech API): free, no account. Chrome and Edge have it. */
type Recognition = {
  lang: string;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type RecognitionCtor = new () => Recognition;
const SpeechRecognitionCtor: RecognitionCtor | undefined =
  typeof window === "undefined"
    ? undefined
    : ((window as unknown as Record<string, RecognitionCtor | undefined>).SpeechRecognition ??
      (window as unknown as Record<string, RecognitionCtor | undefined>).webkitSpeechRecognition);

function speak(line: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(line);
  u.lang = "en-IN";
  window.speechSynthesis.speak(u);
}

function CallView({ call, canAct }: { call: S.Call; canAct: boolean }) {
  const [said, setSaid] = useState("");
  const [voice, setVoice] = useState(false);
  const [listening, setListening] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const turn = useAction((text: string) => api(`/calls/${call.id}/turns`, S.Call, { method: "POST", body: { text } }));
  const lastAi = [...call.turns].reverse().find((t) => t.speaker === "ai");
  const spoken = useRef<number>(0);
  useEffect(() => {
    // Read each new AI line aloud once, only when the collector switched browser voice on.
    if (voice && lastAi && lastAi.seq > spoken.current) {
      spoken.current = lastAi.seq;
      speak(lastAi.text);
    }
  }, [voice, lastAi]);
  const listen = () => {
    if (!SpeechRecognitionCtor) return;
    const r = new SpeechRecognitionCtor();
    r.lang = "en-IN";
    r.interimResults = false;
    r.onresult = (e) => {
      const text = e.results[0]?.[0]?.transcript ?? "";
      if (text.trim()) turn.mutate(text.trim());
    };
    r.onend = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };
  const end = useAction(() => api(`/calls/${call.id}/end`, S.Call, { method: "POST" }));
  const live = call.status === "in_progress";
  return (
    <article className="rounded-lg border bg-muted/30 p-4" aria-label={`Call started ${stamp(call.started_at)}`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{stamp(call.started_at)}</span>
          <Badge value={call.simulated ? "SIMULATED: no phone rang" : "REAL call (Twilio)"} tone={call.simulated ? "wait" : "ok"} />
          <Badge value={call.status.replace("_", " ")} tone={live ? "info" : "plain"} />
          {call.outcome && <Badge value={call.outcome.replaceAll("_", " ")} />}
        </span>
        {live && canAct && (
          <Button onClick={() => end.mutate(undefined)} busy={end.isPending}>
            End call
          </Button>
        )}
      </header>
      <ol className="mt-2 space-y-1" aria-live="polite">
        {call.turns.map((t) => (
          <li key={t.seq} className={t.speaker === "ai" ? "" : "pl-6"}>
            <span className="text-label font-semibold text-text-muted">{t.speaker === "ai" ? "AI assistant" : "Customer"}: </span>
            <span className="whitespace-pre-line">{t.text}</span>
            {t.intent && (
              <details className="text-label">
                <summary className="cursor-pointer text-link">Why? ({t.intent.replaceAll("_", " ")})</summary>
                <p className="text-text-muted">{INTENT[t.intent] ?? t.intent}</p>
              </details>
            )}
          </li>
        ))}
      </ol>
      {call.summary && <p className="mt-2 rounded bg-bg-subtle px-3 py-2">{call.summary}</p>}
      {live && canAct && call.simulated && (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            turn.mutate(said.trim(), { onSuccess: () => setSaid("") });
          }}
        >
          <label className="sr-only" htmlFor={`say-${call.id}`}>
            What the customer says
          </label>
          <input
            id={`say-${call.id}`}
            className="min-w-0 flex-1 rounded-md border border-input bg-transparent px-3 py-1.5 text-sm"
            value={said}
            onChange={(e) => setSaid(e.target.value)}
            maxLength={2000}
            placeholder='Customer says, e.g. "We can pay ₹2 lakh this Friday."'
          />
          <Button type="submit" busy={turn.isPending} disabled={!said.trim()}>
            Send
          </Button>
        </form>
      )}
      {live && canAct && call.simulated && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-label">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={voice} onChange={(e) => setVoice(e.target.checked)} />
            Speak AI lines in this browser
          </label>
          {SpeechRecognitionCtor ? (
            <Button onClick={listening ? () => rec.current?.stop() : listen} busy={turn.isPending}>
              {listening ? "Stop listening" : "Speak as the customer"}
            </Button>
          ) : (
            <span className="text-text-muted">Speech input needs Chrome or Edge; type instead.</span>
          )}
          <span className="text-text-muted">Free browser voice (Web Speech API); no phone line is used.</span>
        </div>
      )}
      <ErrorLine error={turn.error ?? end.error} />
    </article>
  );
}
