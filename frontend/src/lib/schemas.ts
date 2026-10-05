/** Zod schemas for every API response the console reads. Types are z.infer, never hand-written. */
import { z } from "zod";

const paise = z.number().int().nonnegative();
const nstr = z.string().nullable();

export const Role = z.enum(["admin", "collector", "viewer"]);
export const User = z.object({ id: z.string(), email: z.string(), display_name: z.string(), role: Role });

export const Band = z.enum(["HIGH", "MEDIUM", "LOW"]);
export const Reason = z.object({ code: z.string(), text: z.string() });
/** One scored input and the points it added (HACK-003 F4): decision factors, never model reasoning. */
export const Factor = z.object({ code: z.string(), label: z.string(), value: z.string(), points: z.number(), rule: z.string() });

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
  factors: z.array(Factor).default([]),
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
  simulated: z.boolean().default(false),
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
  status: z.enum(["open", "assigned", "investigating", "resolved"]),
  resolution_note: nstr,
  category: z.string().default("other"),
  assigned_team: nstr.default(null),
});

/** HACK-003 F5: a follow-up task for a missed or partly kept promise; every figure from the ledger. */
export const FollowUp = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  promise_id: z.string(),
  kind: z.enum(["missed_promise", "partial_promise"]),
  status: z.enum(["open", "done", "cancelled"]),
  due_on: z.string(),
  recommended_action: z.string(),
  promised_paise: paise,
  promised_date: z.string(),
  received_paise: paise,
  promise_status: z.string(),
  message_id: nstr,
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
      z.object({ customer_id: z.string(), customer_name: z.string(), score: z.number(), band: Band, reasons: z.array(Reason), factors: z.array(Factor).default([]) }),
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
  feature_sms: z.boolean().default(false),
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
export type Invoice = z.infer<typeof Invoice>;
export type Priority = z.infer<typeof Priority>;
export type Message = z.infer<typeof Message>;
export type Check = z.infer<typeof Check>;
export type Run = z.infer<typeof Run>;
export type TimelineEvent = z.infer<typeof TimelineEvent>;
export type Dashboard = z.infer<typeof Dashboard>;
export type Settings = z.infer<typeof Settings>;
export type EvalReport = z.infer<typeof EvalReport>;
export type Dispute = z.infer<typeof Dispute>;
export type FollowUp = z.infer<typeof FollowUp>;

/** HACK-003 F8: CFO dashboard. Every figure is computed by the API from the ledger. */
const Point = z.object({ label: z.string(), value: z.number().int() });
export const Executive = z.object({
  today: z.string(),
  kpis: z.object({
    total_receivables_paise: paise,
    overdue_paise: paise,
    collected_this_month_paise: paise,
    at_risk_paise: paise,
    promises_due_today_paise: paise,
    missed_promises_paise: paise,
    collection_rate_pct: z.number().int().nullable(),
  }),
  definitions: z.record(z.string(), z.string()),
  ageing: z.array(Point),
  collections_by_week: z.array(Point),
  overdue_trend: z.array(Point),
  promise_outcomes: z.array(Point),
  risk_distribution: z.array(Point),
  collections_by_channel: z.array(Point),
  disputes_by_status: z.array(Point),
  expected_collections: z.array(Point),
  attention: z.array(
    z.object({
      customer_id: z.string(),
      customer_name: z.string(),
      severity: z.enum(["red", "amber"]),
      score: z.number().int(),
      headline: z.string(),
      factors: z.array(Factor),
    }),
  ),
});

/** HACK-003 AI Safety Center: counts of real events, with what each count is made of. */
export const Safety = z.object({
  messages_checked: z.number().int(),
  messages_passed: z.number().int(),
  guardrail_failures: z.number().int(),
  incorrect_amounts_blocked: z.number().int(),
  prompt_attacks_blocked: z.number().int(),
  human_approvals: z.number().int(),
  human_rejections: z.number().int(),
  automatic_approvals: z.number().int(),
  automatic_sends: z.number().int(),
  send_gate_refusals: z.number().int(),
  tool_calls_refused: z.number().int(),
  kill_switch: z.string(),
  autonomy_mode: z.string(),
  llm_spent_micro_usd: z.number().int(),
  llm_budget_micro_usd: z.number().int(),
  by_code: z.array(z.object({ check_name: z.string(), code: z.string(), count: z.number().int() })),
  sources: z.record(z.string(), z.string()),
});

/** HACK-003 F2: which channel next, and the factors behind it. */
export const ChannelPlan = z.object({
  preferred_channel: nstr,
  last_channel: nstr,
  last_contact_on: nstr,
  response_status: z.enum(["never contacted", "no response", "replied"]),
  cadence_day: z.number().int(),
  recommended_channel: z.string(),
  draft_channel: z.enum(["email", "whatsapp", "sms"]),
  next_step_channel: nstr,
  next_step_on: nstr,
  factors: z.array(z.string()),
});

/** HACK-003 F3: interaction history from rows; notes are internal and never reach the model or the portal. */
export const Memory = z.object({
  customer_id: z.string(),
  items: z.array(
    z.object({
      on: z.string(),
      kind: z.string(),
      source: z.string(),
      summary: z.string(),
      amount_paise: paise.nullable(),
      channel: nstr,
    }),
  ),
  promise_recall: nstr,
  notes: z.array(z.object({ id: z.string(), body: z.string(), author: nstr, created_at: z.string() })),
});
export const Note = z.object({ id: z.string(), body: z.string(), author: nstr, created_at: z.string() });
export type ChannelPlan = z.infer<typeof ChannelPlan>;

/** HACK-003 F1: an AI voice call. `simulated` comes from the provider: no phone rang when it is true. */
export const Call = z.object({
  id: z.string(),
  customer_id: z.string(),
  customer_name: z.string(),
  provider: z.string(),
  simulated: z.boolean(),
  status: z.enum(["requested", "in_progress", "completed", "failed", "no_answer", "wrong_number"]),
  state: z.string(),
  outcome: nstr,
  summary: nstr,
  follow_up_on: nstr,
  promise_id: nstr,
  dispute_id: nstr,
  started_at: z.string(),
  ended_at: nstr,
  turns: z.array(z.object({ seq: z.number().int(), speaker: z.enum(["ai", "customer"]), text: z.string(), intent: nstr })),
});
export type Call = z.infer<typeof Call>;

/** HACK-003 F6: the public portal. Only these fields exist on the API side too (allow-listed). */
export const PortalView = z.object({
  customer_name: z.string(),
  outstanding_paise: paise,
  invoices: z.array(
    z.object({
      number: z.string(),
      invoice_date: z.string(),
      due_date: z.string(),
      remaining_paise: paise,
      status: z.enum(["open", "overdue", "under review"]),
    }),
  ),
  promises: z.array(z.object({ amount_paise: paise, promised_date: z.string() })),
  pay_now_available: z.boolean(),
  payment_simulated: z.boolean(),
  expires_at: z.string(),
});
export const PortalAck = z.object({ ok: z.boolean(), message: z.string() });
export const PortalLink = z.object({ token: z.string(), path: z.string(), expires_at: z.string() });
