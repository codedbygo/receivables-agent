/** S-11 Admin with S-12 Simulate bank credit, S-13 Reset demo and S-14 Advance clock
(US-01-001, US-01-002, US-01-004, US-01-005, US-01-006, US-01-008, US-01-009). */
import { Activity, CalendarDays, Cpu, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { href } from "@/app/route";
import { Badge, Button, Dialog, Empty, ErrorLine, Field, inputClass, Loading, MetaChip, Notice, PageHeader, Panel, Table, td, tdNum } from "@/components/kit";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { day, inr, rupeesToPaise, stamp } from "@/lib/format";
import { GooglePanel } from "./Google";
import { PeoplePanel } from "./People";
import { useAction, useCustomers, useGuardrailEvents, usePayments, useRuns, useSettings } from "@/lib/hooks";
import * as S from "@/lib/schemas";
import { RunDialog } from "./RunDialog";

type Open = "credit" | "reset" | "clock" | null;

const FLAGS = [
  ["feature_whatsapp", "WhatsApp (simulated unless Twilio is configured)"],
  ["feature_sms", "SMS (simulated unless Twilio is configured)"],
  ["feature_voice", "Voice calls and Prepare Call (simulated unless Twilio is configured)"],
  ["feature_payment_link", "Simulated payment link"],
  ["feature_trusted_mode", "Trusted mode"],
] as const;

const usd = (micro: number) => `$${(micro / 1_000_000).toFixed(4)}`;

export function Admin() {
  const s = useSettings();
  const runs = useRuns();
  const events = useGuardrailEvents();
  const pays = usePayments();
  const [open, setOpen] = useState<Open>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const patch = useAction((body: Partial<S.Settings>) =>
    api("/admin/settings", S.Settings, { method: "PATCH", body }),
  );
  const dailyRun = useAction(() => api("/runs", S.RunBatch, { method: "POST", body: {} }));
  if (s.isPending) return <Loading what="settings" />;
  if (s.error) return <ErrorLine error={s.error} />;
  const cfg = s.data;

  return (
    <div className="space-y-6">
      <PageHeader title="Admin" description="Sending, autonomy, budget and the demo controls.">
        <MetaChip icon={CalendarDays} label="Demo date" value={day(cfg.demo_today)} />
        <MetaChip icon={Cpu} label="LLM mode" value={cfg.llm_mode} mono />
      </PageHeader>
      <ErrorLine error={patch.error ?? dailyRun.error} />

      <Tabs defaultValue="controls" className="gap-6">
        <TabsList>
          <TabsTrigger value="controls">
            <SlidersHorizontal aria-hidden /> Controls
          </TabsTrigger>
          <TabsTrigger value="activity">
            <Activity aria-hidden /> Activity
          </TabsTrigger>
        </TabsList>
        <TabsContent value="controls" className="space-y-6">
      <PeoplePanel />
      <GooglePanel isAdmin />
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Kill switch">
          <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-3">
            <span className="flex items-center gap-2 font-semibold" role="status">
              <span aria-hidden className={cn("size-2 rounded-full", cfg.sending_enabled ? "bg-success" : "bg-danger")} />
              {cfg.sending_enabled ? "Sending is on" : "Sending is paused: no send path works"}
            </span>
          </div>
          <div className="mt-3">
            <Button
              variant={cfg.sending_enabled ? "danger" : "primary"}
              busy={patch.isPending}
              onClick={() => patch.mutate({ sending_enabled: !cfg.sending_enabled })}
            >
              {cfg.sending_enabled ? "Pause all sending" : "Turn sending back on"}
            </Button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">Analysis and drafting continue while sending is paused.</p>
        </Panel>

        <Panel title="Autonomy">
          <RadioGroup
            aria-label="Autonomy mode"
            value={cfg.autonomy_mode}
            onValueChange={(m) => patch.mutate({ autonomy_mode: m as S.Settings["autonomy_mode"] })}
            className="gap-2"
          >
            {(["manual", "assisted", "trusted"] as const).map((m) => {
              const off = m === "trusted" && !cfg.feature_trusted_mode;
              return (
                <label
                  key={m}
                  className={cn(
                    "flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors hover:bg-accent has-data-[state=checked]:border-primary has-data-[state=checked]:bg-primary-subtle",
                    off && "cursor-not-allowed bg-muted",
                  )}
                >
                  <RadioGroupItem value={m} disabled={off} />
                  <span className="min-w-0">
                    <span className="block font-semibold capitalize">{m}</span>
                    <span className="block text-sm text-muted-foreground">
                      {m === "manual" && "every message approved one by one"}
                      {m === "assisted" && "batch approval of verified drafts"}
                      {m === "trusted" && (cfg.feature_trusted_mode ? "allow-listed gentle reminders auto-send" : "flag off")}
                    </span>
                  </span>
                </label>
              );
            })}
          </RadioGroup>
        </Panel>

        <Panel title="LLM spend">
          <p className="num text-2xl font-semibold tracking-tight">{usd(cfg.llm_spent_micro_usd)}</p>
          <p className="num text-sm text-muted-foreground">of {usd(cfg.llm_budget_micro_usd)} budget</p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.min(100, (cfg.llm_spent_micro_usd / Math.max(1, cfg.llm_budget_micro_usd)) * 100)}%` }}
            />
          </div>
          <p className="mt-3 text-sm text-muted-foreground">Calls are refused once the budget is spent; drafting falls back to templates.</p>
        </Panel>
      </div>

      <Panel title="Feature flags (P2, off by default)">
        <ul className="grid gap-3 md:grid-cols-2">
          {FLAGS.map(([key, label]) => (
            <li key={key}>
              <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-lg border px-3 py-2 hover:bg-accent">
                <span>
                  <span className="block font-semibold">{label}</span>
                  <span className="block text-sm text-muted-foreground">{cfg[key] ? "on" : "off"}</span>
                </span>
                <Switch checked={cfg[key]} onCheckedChange={() => patch.mutate({ [key]: !cfg[key] })} />
              </label>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Demo tools">
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => dailyRun.mutate(undefined)} busy={dailyRun.isPending}>
            Queue today's daily run
          </Button>
          <Button onClick={() => setOpen("clock")}>Advance the clock</Button>
          <Button onClick={() => setOpen("credit")}>Simulate a bank credit</Button>
          <Button variant="danger" onClick={() => setOpen("reset")}>Reset demo data</Button>
        </div>
        {dailyRun.data && (
          <div className="mt-3">
            <Notice tone="success">
              {dailyRun.data.queued
                ? `Daily run for ${day(dailyRun.data.run_date)} queued; the worker picks it up.`
                : `Today's daily run was already queued.`}
            </Notice>
          </div>
        )}
      </Panel>

        </TabsContent>
        <TabsContent value="activity" className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Recent runs">
          {runs.isPending ? (
            <Loading what="runs" />
          ) : !runs.data?.data.length ? (
            <Empty>No runs yet.</Empty>
          ) : (
            <Table head={["Customer", "Outcome", "Calls", "Started"]} numeric={[2]}>
              {runs.data.data.map((r) => (
                <tr key={r.id}>
                  <td className={td}>
                    <button type="button" className="font-medium text-link underline-offset-4 hover:underline" onClick={() => setRunId(r.id)}>
                      {r.customer_name}
                    </button>
                  </td>
                  <td className={td}>{r.outcome ? <Badge value={r.outcome} /> : "Running"}</td>
                  <td className={tdNum}>{r.tool_call_count}</td>
                  <td className={td}>{stamp(r.started_at)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
        <Panel title="Guardrail events">
          {events.isPending ? (
            <Loading what="guardrail events" />
          ) : !events.data?.data.length ? (
            <Empty>No guardrail has fired.</Empty>
          ) : (
            <Table head={["Check", "Code", "When"]}>
              {events.data.data.map((e) => (
                <tr key={e.id}>
                  <td className={td}>{e.check_name}</td>
                  <td className={`${td} font-mono text-danger`}>{e.code}</td>
                  <td className={td}>{stamp(e.created_at)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      </div>

      <Panel title="Payments">
        {pays.isPending ? (
          <Loading what="payments" />
        ) : !pays.data?.data.length ? (
          <Empty>No payments recorded.</Empty>
        ) : (
          <Table head={["Received", "Reference", "Amount", "Match", "Customer"]} numeric={[2]}>
            {pays.data.data.map((p) => (
              <tr key={p.id}>
                <td className={td}>{day(p.received_on)}</td>
                <td className={`${td} font-mono`}>{p.reference ?? "None"}</td>
                <td className={tdNum}>{inr(p.amount_paise)}</td>
                <td className={td}>
                  <Badge value={p.match_status} />
                </td>
                <td className={td}>
                  {p.customer_id ? (
                    <a className="font-medium text-link underline-offset-4 hover:underline" href={href({ page: "customer", id: p.customer_id })}>
                      Open
                    </a>
                  ) : (
                    "Needs a human"
                  )}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
        </TabsContent>
      </Tabs>

      {open === "clock" && <ClockDialog onClose={() => setOpen(null)} today={cfg.demo_today} />}
      {open === "credit" && <CreditDialog onClose={() => setOpen(null)} />}
      {open === "reset" && <ResetDialog onClose={() => setOpen(null)} />}
      <RunDialog runId={runId} onClose={() => setRunId(null)} />
    </div>
  );
}

function ClockDialog({ onClose, today }: { onClose: () => void; today: string }) {
  const [days, setDays] = useState(5);
  const go = useAction(() =>
    api("/admin/clock/advance", S.ClockOut, { method: "POST", body: { days } }),
  );
  return (
    <Dialog title="Advance the demo clock" open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          go.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <p className="mb-3 text-text-muted">
          Today is {day(today)}. Promises due on or before the new date are checked against the ledger.
        </p>
        <Field label="Days to advance (1 to 60)">
          <input
            type="number"
            min={1}
            max={60}
            className={`${inputClass} num`}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            required
          />
        </Field>
        <ErrorLine error={go.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={go.isPending}>
            Advance {days} days
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function CreditDialog({ onClose }: { onClose: () => void }) {
  const customers = useCustomers();
  const [customer, setCustomer] = useState("");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const paise = rupeesToPaise(amount);
  const post = useAction(() =>
    api("/admin/simulate/bank-credit", S.PaymentOut, {
      method: "POST",
      body: { customer_id: customer, amount_paise: paise, reference: reference.trim() },
    }),
  );
  return (
    <Dialog title="Simulate a bank credit (SIMULATED)" open onClose={onClose}>
      {post.data ? (
        <div className="space-y-3">
          <p role="status">
            Credit of <span className="num font-semibold">{inr(post.data.amount_paise)}</span> recorded:{" "}
            <Badge value={post.data.match_status} />
          </p>
          {post.data.allocations.length > 0 && (
            <ul className="text-label">
              {post.data.allocations.map((a) => (
                <li key={a.invoice_id}>
                  <span className="font-mono">{a.invoice_number}</span> <span className="num">{inr(a.amount_paise)}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="text-right">
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            post.mutate(undefined);
          }}
        >
          <p className="mb-3 text-text-muted">
            Signed server-side and sent through the real bank webhook handler, which matches and allocates it.
          </p>
          <Field label="Customer">
            <select className={inputClass} value={customer} onChange={(e) => setCustomer(e.target.value)} required>
              <option value="">Choose a customer</option>
              {customers.data?.data.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({inr(c.outstanding_paise)} outstanding)
                </option>
              ))}
            </select>
          </Field>
          <Field label="Amount in rupees (for example 300000)">
            <input className={`${inputClass} num`} value={amount} onChange={(e) => setAmount(e.target.value)} required />
          </Field>
          {amount && paise === null && <p className="mb-3 text-danger">Error: enter rupees with at most two decimals.</p>}
          {paise !== null && <p className="num mb-3 text-text-muted">That is {inr(paise)}.</p>}
          <Field label="Bank reference">
            <input
              className={inputClass}
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              required
              maxLength={100}
              placeholder="NEFT UTR 4411"
            />
          </Field>
          <ErrorLine error={post.error} />
          <div className="mt-4 flex justify-end gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" busy={post.isPending} disabled={!customer || paise === null || !reference.trim()}>
              Post credit
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

function ResetDialog({ onClose }: { onClose: () => void }) {
  const reset = useAction(() => api("/admin/reset", S.ResetOut, { method: "POST" }));
  return (
    <Dialog title="Reset demo data?" open onClose={onClose}>
      <p className="mb-4">
        Every customer, invoice, message, reply, payment and run goes back to the start of the ABC Distributors
        story. Users and LLM spend are kept. This cannot be undone.
      </p>
      <ErrorLine error={reset.error} />
      <div className="flex justify-end gap-2">
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="danger"
          busy={reset.isPending}
          onClick={() =>
            reset.mutate(undefined, {
              onSuccess: () => {
                onClose();
                window.location.hash = "#/today";
              },
            })
          }
        >
          Reset demo data
        </Button>
      </div>
    </Dialog>
  );
}
