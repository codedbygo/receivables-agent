/** AI voice calls on the customer page (HACK-003 F1). Every AI line was rendered from the ledger and verified before it
 * was spoken; the customer's words only choose a fixed intent. A web call rings no phone: the customer talks into this
 * browser's microphone (hands-free, transcribed on the server) or types. */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Globe, Phone, PhoneCall } from "lucide-react";
import { Badge, Button, Dialog, Empty, ErrorLine, Panel } from "@/components/kit";
import { Button as UIButton } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  return (
    <Panel title="Voice calls">
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

/** The page-header Call button: on the phone (Twilio) or in this browser. The live call opens in a dialog. */
export function CallMenu({ customerId }: { customerId: string }) {
  const [callId, setCallId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const start = useAction((via: "phone" | "web") =>
    api("/calls", S.Call, { method: "POST", body: { customer_id: customerId, via } }),
  );
  const call = useQuery({
    queryKey: ["call", callId],
    queryFn: () => api(`/calls/${callId}`, S.Call),
    enabled: callId !== null,
  });
  const begin = (via: "phone" | "web") => {
    setCallId(null);
    setOpen(true);
    start.mutate(via, { onSuccess: (c) => setCallId(c.id) });
  };
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <UIButton variant="default">
            <PhoneCall aria-hidden /> Call
          </UIButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => begin("phone")}>
            <Phone aria-hidden /> Call on phone
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => begin("web")}>
            <Globe aria-hidden /> Call in browser
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog title="Voice call" open={open} onClose={() => setOpen(false)}>
        {start.isPending && <p role="status">Starting the call…</p>}
        <ErrorLine error={start.error ?? call.error} />
        {call.data && <CallView call={call.data} canAct live />}
      </Dialog>
    </>
  );
}

/** Hands-free web call (ADR-0019). The browser records one utterance at a time, ends it after a short silence,
 * and posts it to /calls/{id}/audio, where a local Whisper model turns it into text. While the agent speaks the
 * microphone is not recorded, so the agent never hears itself. */
type Phase = "off" | "listening" | "thinking" | "speaking";
const SPEECH_RMS = 0.03; // ponytail: one fixed loudness threshold; calibrate per microphone if rooms are noisy
const END_SILENCE_MS = 800;
const NO_SPEECH_MS = 10_000;
const MAX_UTTERANCE_MS = 30_000;
type Live = { stream: MediaStream; ctx: AudioContext; analyser: AnalyserNode; rec?: MediaRecorder; timer?: number };

function release(l: Live | null) {
  if (!l) return;
  window.clearInterval(l.timer);
  if (l.rec?.state === "recording") l.rec.stop();
  l.stream.getTracks().forEach((t) => t.stop());
  void l.ctx.close();
}

/** Runs fn once the browser has finished speaking (polled: Chrome's onend is unreliable on long lines). */
function afterSpeech(fn: () => void) {
  const synth = window.speechSynthesis;
  const t = window.setInterval(() => {
    if (!synth.speaking && !synth.pending) {
      window.clearInterval(t);
      fn();
    }
  }, 150);
}

function useHandsFree(send: (audio: Blob) => Promise<S.Call>, onReply: (call: S.Call) => void) {
  const [phase, setPhase] = useState<Phase>("off");
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const live = useRef<Live | null>(null);
  useEffect(
    () => () => {
      release(live.current);
      live.current = null;
    },
    [],
  );
  const stop = () => {
    release(live.current);
    live.current = null;
    setPhase("off");
    setLevel(0);
  };
  const listen = (l: Live) => {
    if (live.current !== l) return;
    setPhase("listening");
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(l.stream);
    l.rec = rec;
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    rec.onstop = () => {
      if (live.current !== l) return;
      setPhase("thinking");
      setLevel(0);
      send(new Blob(chunks, { type: rec.mimeType }))
        .then((call) => {
          if (live.current !== l) return;
          onReply(call);
          if (call.status !== "in_progress") return stop();
          setPhase("speaking");
          afterSpeech(() => listen(l));
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : "The call could not continue.");
          stop();
        });
    };
    const buf = new Float32Array(l.analyser.fftSize);
    const started = performance.now();
    let spoke = 0;
    let lastLoud = 0;
    rec.start();
    l.timer = window.setInterval(() => {
      l.analyser.getFloatTimeDomainData(buf);
      const rms = Math.sqrt(buf.reduce((a, v) => a + v * v, 0) / buf.length);
      setLevel(Math.min(100, Math.round(rms * 400)));
      const now = performance.now();
      if (rms > SPEECH_RMS) {
        lastLoud = now;
        spoke ||= now;
      }
      const done = spoke
        ? now - lastLoud > END_SILENCE_MS || now - spoke > MAX_UTTERANCE_MS
        : now - started > NO_SPEECH_MS;
      if (done) {
        window.clearInterval(l.timer);
        rec.stop();
      }
    }, 50);
  };
  const start = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const l: Live = { stream, ctx, analyser };
      live.current = l;
      setPhase("speaking");
      afterSpeech(() => listen(l)); // let the agent finish its line first
    } catch {
      setError("The microphone is blocked or missing: allow it from the icon left of the address bar, then try again.");
    }
  };
  return { phase, level, error, start, stop };
}

const PHASE: Record<Phase, string> = {
  off: "",
  listening: "Listening… speak now",
  thinking: "Thinking…",
  speaking: "Agent speaking…",
};

function speak(line: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(line);
  u.lang = "en-IN";
  window.speechSynthesis.speak(u);
}

/** `live` is the call dialog: it speaks aloud by default and goes quiet when closed. The history list on the
 * customer page never speaks on its own; there a collector ticks "Speak AI lines" to hear new lines. */
function CallView({ call, canAct, live: inDialog = false }: { call: S.Call; canAct: boolean; live?: boolean }) {
  const [said, setSaid] = useState("");
  const [voice, setVoice] = useState(inDialog && call.simulated);
  useEffect(() => (inDialog ? () => window.speechSynthesis.cancel() : undefined), [inDialog]);
  const turn = useAction((text: string) => api(`/calls/${call.id}/turns`, S.Call, { method: "POST", body: { text } }));
  const audio = useAction((clip: Blob) => api(`/calls/${call.id}/audio`, S.Call, { method: "POST", body: clip }));
  const lastAi = [...call.turns].reverse().find((t) => t.speaker === "ai");
  // Outside the dialog, lines already on screen are history: only lines that arrive later are read out.
  const spoken = useRef<number>(inDialog ? 0 : (lastAi?.seq ?? 0));
  useEffect(() => {
    // Read each new AI line aloud once while browser voice is on (the default on a web call).
    if (voice && lastAi && lastAi.seq > spoken.current) {
      spoken.current = lastAi.seq;
      speak(lastAi.text);
    }
  }, [voice, lastAi]);
  const hands = useHandsFree(audio.mutateAsync, (c) => {
    // Speak the reply at once, so the next listen waits for it (the effect above would speak a render later).
    const ai = [...c.turns].reverse().find((t) => t.speaker === "ai");
    if (voice && ai && ai.seq > spoken.current) {
      spoken.current = ai.seq;
      speak(ai.text);
    }
  });
  const end = useAction(() => api(`/calls/${call.id}/end`, S.Call, { method: "POST" }));
  const live = call.status === "in_progress";
  return (
    <article className="rounded-lg border bg-muted/30 p-4" aria-label={`Call started ${stamp(call.started_at)}`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{stamp(call.started_at)}</span>
          <Badge value={call.simulated ? "Web call: browser voice, no phone" : "REAL call (Twilio)"} tone={call.simulated ? "wait" : "ok"} />
          <Badge value={call.status.replace("_", " ")} tone={live ? "info" : "plain"} />
          {call.outcome && <Badge value={call.outcome.replaceAll("_", " ")} />}
        </span>
        {live && canAct && (
          <Button
            onClick={() => {
              hands.stop();
              window.speechSynthesis.cancel();
              end.mutate(undefined);
            }}
            busy={end.isPending}
          >
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
          {hands.phase === "off" ? (
            <Button variant="primary" onClick={() => void hands.start()}>
              Start talking
            </Button>
          ) : (
            <Button onClick={hands.stop}>Stop talking</Button>
          )}
          {hands.phase !== "off" && (
            <span role="status" className="flex items-center gap-2 font-semibold">
              {PHASE[hands.phase]}
              {hands.phase === "listening" && (
                <span aria-hidden className="h-1.5 w-16 overflow-hidden rounded bg-muted">
                  <span className="block h-full bg-primary" style={{ width: `${hands.level}%` }} />
                </span>
              )}
            </span>
          )}
        </div>
      )}
      {hands.error && (
        <p role="status" className="mt-1 text-label text-danger">
          {hands.error}
        </p>
      )}
      <ErrorLine error={turn.error ?? audio.error ?? end.error} />
    </article>
  );
}
