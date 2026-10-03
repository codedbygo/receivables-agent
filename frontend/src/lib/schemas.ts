/** Zod schemas for every API response the console reads. Types are z.infer, never hand-written. */
import { z } from "zod";

const paise = z.number().int().nonnegative();
const nstr = z.string().nullable();

export const Role = z.enum(["admin", "collector", "viewer"]);
export const User = z.object({ id: z.string(), email: z.string(), display_name: z.string(), role: Role });

export const Band = z.enum(["HIGH", "MEDIUM", "LOW"]);
export const Reason = z.object({ code: z.string(), text: z.string() });

export const Customer = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string(),
  phone: z.string(),
  segment: z.string(),
  credit_terms_days: z.number(),
  outstanding_paise: paise,
  overdue_paise: paise,
  band: Band.nullable(),
  last_contact_at: nstr,
  next_action: nstr,
});

export const Invoice = z.object({
  id: z.string(),
  number: z.string(),
  invoice_date: z.string(),
  due_date: z.string(),
  amount_paise: paise,
  paid_paise: paise,
  remaining_paise: paise,
  status: z.enum(["unpaid", "partially_paid", "paid", "disputed"]),
  days_overdue: z.number(),
});

export const Priority = z.object({
  customer_id: z.string(),
  customer_name: z.string(),
  score: z.number(),
  band: Band,
  reasons: z.array(Reason),
});

export const Check = z.object({
  check: z.string(),
  token: z.string(),
  ok: z.boolean(),
  code: nstr.optional(),
  expected: nstr.optional(),
});

export const MessageStatus = z.enum(["draft", "pending_approval", "approved", "rejected", "sent", "failed"]);
export const Message = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  agent_run_id: nstr,
  kind: z.string(),
  channel: z.string(),
  tone: z.string(),
  status: MessageStatus,
  subject: z.string(),
  body: z.string(),
  version: z.number().int(),
  verified: z.boolean(),
  guardrail_report: z.array(Check),
  invoice_numbers: z.array(z.string()),
  rejected_reason: nstr,
  sent_at: nstr,
  last_error: nstr,
  created_at: z.string(),
});

export const Step = z.object({
  seq: z.number(),
  role: z.string(),
  tool_name: z.string(),
  arguments_redacted: z.record(z.unknown()),
  result_summary: z.string(),
  error_code: nstr,
});

export const Run = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  run_date: z.string(),
  trigger: z.string(),
  status: z.string(),
  outcome: nstr,
  tool_call_count: z.number(),
  action: nstr,
  channel: nstr,
  tone: nstr,
  reason: nstr,
  started_at: z.string(),
  finished_at: nstr,
  steps: z.array(Step),
});

export const RunBatch = z.object({
  run_date: z.string(),
  job_id: z.number().nullable(),
  queued: z.boolean(),
  run_ids: z.array(z.string()),
});

export const TimelineEvent = z.object({
  id: z.string(),
  occurred_at: z.string(),
  business_date: z.string(),
  kind: z.string(),
  actor: z.string(),
  actor_name: nstr,
  amount_paise: paise.nullable(),
  summary: z.string(),
  ref_type: nstr,
  ref_id: nstr,
});

export const Promise_ = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  amount_paise: paise,
  promised_date: z.string(),
  status: z.string(),
  invoice_ids: z.array(z.string()),
});

export const Dispute = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  invoice_id: z.string(),
  invoice_number: z.string(),
  reason: z.string(),
  status: z.string(),
  resolution_note: nstr,
});

export const Escalation = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  kind: z.string(),
  reason: z.string(),
  status: z.string(),
  created_at: z.string(),
});

export const Payment = z.object({
  id: z.string(),
  customer_id: nstr,
  amount_paise: paise,
  received_on: z.string(),
  reference: nstr,
  source: z.string(),
  match_status: z.string(),
});

export const Reply = z.object({
  id: z.string(),
  customer_id: z.string(),
  classification: nstr,
  amount_paise: paise.nullable(),
  stated_date: nstr,
  invoice_refs: z.array(z.string()),
  confidence: z.number().nullable(),
  recommended_action: nstr,
  needs_review: z.boolean(),
  agent_run_id: nstr,
});

const Row = z.object({ id: z.string(), customer_id: z.string().optional(), customer_name: z.string().optional() });

export const Dashboard = z.object({
  today: z.string(),
  total_outstanding_paise: paise,
  total_overdue_paise: paise,
  customers_overdue: z.number(),
  todays_promises: z.number(),
  missed_promises: z.number(),
  open_disputes: z.number(),
  pending_approvals: z.number(),
  high_risk_customers: z.number(),
  open_escalations: z.number(),
  ageing: z.object({ d0_30_paise: paise, d31_60_paise: paise, d61_90_paise: paise, d90_plus_paise: paise }),
  attention: z.object({
    high_priority: z.array(
      z.object({ customer_id: z.string(), customer_name: z.string(), score: z.number(), band: Band, reasons: z.array(Reason) }),
    ),
    missed_promises: z.array(Row.extend({ amount_paise: paise, promised_date: z.string() })),
    disputes: z.array(Row.extend({ invoice_number: z.string(), reason: z.string() })),
    approved_ready: z.array(Row.extend({ subject: z.string() })),
    needs_verification: z.array(Row.extend({ amount_paise: paise, reference: nstr, received_on: z.string() })),
    todays_promises: z.array(Row.extend({ amount_paise: paise, promised_date: z.string(), status: z.string() })),
    escalations: z.array(Row.extend({ kind: z.string(), reason: z.string() })),
  }),
});

export const Settings = z.object({
  demo_today: z.string(),
  sending_enabled: z.boolean(),
  autonomy_mode: z.enum(["manual", "assisted", "trusted"]),
  llm_budget_micro_usd: z.number(),
  llm_spent_micro_usd: z.number(),
  llm_mode: z.string(),
  feature_whatsapp: z.boolean(),
  feature_voice: z.boolean(),
  feature_payment_link: z.boolean(),
  feature_trusted_mode: z.boolean(),
});

export const GuardrailEvent = z.object({
  id: z.string(),
  check_name: z.string(),
  code: z.string(),
  customer_id: nstr,
  message_id: nstr,
  created_at: z.string(),
});

const Score = z.object({
  total: z.number(),
  passed: z.number(),
  rate: z.number(),
  failures: z.array(z.record(z.unknown())),
});
export const EvalReport = z.object({
  generated_at: z.string(),
  mode: z.string(),
  command: z.string(),
  replies: z.object({ class: Score, action: Score, amount: Score, date: Score, source: z.record(z.number()) }),
  red_team: Score,
  golden: Score,
  scenarios: Score.extend({
    results: z.array(
      z.object({
        id: z.string(),
        ok: z.boolean(),
        actual: z.object({ class: nstr, tools: z.array(z.string()), outcome: z.string() }),
      }),
    ),
  }).nullable(),
});

export const PromiseCheckResult = z.object({
  promise: Promise_,
  matched_payment_ids: z.array(z.string()),
  message: z.string(),
});
export const DisputeResolved = z.object({ id: z.string(), status: z.string() });
export const ClockOut = z.object({ demo_today: z.string() });
export const ResetOut = z.object({ reset: z.boolean(), demo_today: z.string() });
export const PaymentOut = Payment.extend({
  allocations: z.array(z.object({ invoice_id: z.string(), invoice_number: z.string(), amount_paise: paise })),
});

export const PayLink = z.object({
  invoice_number: z.string(),
  customer_name: z.string(),
  amount_paise: paise,
  simulated: z.literal(true),
});
export const PayLinkToken = z.object({ token: z.string(), invoice_number: z.string() });
export const CallPrep = z.object({
  customer: Customer,
  summary: z.string(),
  invoices: z.array(Invoice),
  promises: z.array(Promise_),
  talking_points: z.array(z.string()),
  verified: z.boolean(),
  checks: z.array(Check),
});

export const page = <T extends z.ZodTypeAny>(item: T) => z.object({ data: z.array(item) });

export type Role = z.infer<typeof Role>;
export type User = z.infer<typeof User>;
export type Customer = z.infer<typeof Customer>;
export type Payment = z.infer<typeof Payment>;
export type Invoice = z.infer<typeof Invoice>;
export type Priority = z.infer<typeof Priority>;
export type Message = z.infer<typeof Message>;
export type Check = z.infer<typeof Check>;
export type Run = z.infer<typeof Run>;
export type TimelineEvent = z.infer<typeof TimelineEvent>;
export type Dashboard = z.infer<typeof Dashboard>;
export type Settings = z.infer<typeof Settings>;
export type EvalReport = z.infer<typeof EvalReport>;
