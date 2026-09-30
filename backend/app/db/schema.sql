-- Schema for the AI Receivables Collections Agent (HACK-001).
-- Generated from one spec with data-dictionary.csv and data-model.md; migration 0001 applies this file.
BEGIN;

-- Serves US-01-007, US-00-009
CREATE TABLE users (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  email text NOT NULL,
  display_name text NOT NULL,
  role text NOT NULL,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_users PRIMARY KEY (id),
  CONSTRAINT chk_users_role CHECK (role IN ('admin','collector','viewer'))
);
COMMENT ON TABLE users IS 'A person who signs in to the console with one role.';
COMMENT ON COLUMN users.id IS 'Surrogate key.';
COMMENT ON COLUMN users.email IS 'Sign-in name.';
COMMENT ON COLUMN users.display_name IS 'Name shown as the actor on timeline events.';
COMMENT ON COLUMN users.role IS 'admin, collector or viewer.';
COMMENT ON COLUMN users.password_hash IS 'Password hash (argon2 or bcrypt).';
COMMENT ON COLUMN users.created_at IS 'When the row was written.';
CREATE UNIQUE INDEX uq_users_email ON users (lower(email));

-- Serves US-01-007
CREATE TABLE sessions (
  id text NOT NULL,
  user_id uuid NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_sessions PRIMARY KEY (id),
  CONSTRAINT fk_sessions_user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
COMMENT ON TABLE sessions IS 'A server-side session for one signed-in user.';
COMMENT ON COLUMN sessions.id IS 'SHA-256 of the session cookie value.';
COMMENT ON COLUMN sessions.user_id IS 'Who is signed in.';
COMMENT ON COLUMN sessions.expires_at IS 'When the session stops working.';
COMMENT ON COLUMN sessions.created_at IS 'When the row was written.';
CREATE INDEX idx_sessions_user_id ON sessions (user_id);

-- Serves US-01-002, US-01-004, US-01-006, US-01-016
CREATE TABLE settings (
  id smallint NOT NULL DEFAULT 1,
  demo_today date NOT NULL,
  sending_enabled boolean NOT NULL DEFAULT true,
  autonomy_mode text NOT NULL DEFAULT 'manual',
  llm_budget_micro_usd bigint NOT NULL DEFAULT 2000000,
  feature_whatsapp boolean NOT NULL DEFAULT false,
  feature_voice boolean NOT NULL DEFAULT false,
  feature_payment_link boolean NOT NULL DEFAULT false,
  feature_trusted_mode boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_settings PRIMARY KEY (id),
  CONSTRAINT chk_settings_singleton CHECK (id = 1),
  CONSTRAINT chk_settings_autonomy_mode CHECK (autonomy_mode IN ('manual','assisted','trusted')),
  CONSTRAINT chk_settings_budget_nonneg CHECK (llm_budget_micro_usd >= 0)
);
COMMENT ON TABLE settings IS 'The single row of runtime settings shared by api, mcp and worker.';
COMMENT ON COLUMN settings.id IS 'Always 1; the table is a singleton.';
COMMENT ON COLUMN settings.demo_today IS 'The business date every computation uses.';
COMMENT ON COLUMN settings.sending_enabled IS 'Kill switch: false blocks every send path.';
COMMENT ON COLUMN settings.autonomy_mode IS 'manual, assisted or trusted.';
COMMENT ON COLUMN settings.llm_budget_micro_usd IS 'LLM budget in micro-dollars.';
COMMENT ON COLUMN settings.feature_whatsapp IS 'WhatsApp channel on; seeded from FEATURE_WHATSAPP.';
COMMENT ON COLUMN settings.feature_voice IS 'Prepare Call on; seeded from FEATURE_VOICE.';
COMMENT ON COLUMN settings.feature_payment_link IS 'Payment link page on; seeded from FEATURE_PAYMENT_LINK.';
COMMENT ON COLUMN settings.feature_trusted_mode IS 'Trusted autonomy allowed.';
COMMENT ON COLUMN settings.updated_at IS 'Last change to the row.';

-- Serves US-00-001, US-00-002, US-00-004, US-01-003
CREATE TABLE customers (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  email text NOT NULL,
  phone text NOT NULL,
  segment text NOT NULL,
  credit_terms_days integer NOT NULL DEFAULT 30,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_customers PRIMARY KEY (id),
  CONSTRAINT chk_customers_segment CHECK (segment IN ('enterprise','mid_market','sme')),
  CONSTRAINT chk_customers_name_not_blank CHECK (btrim(name) <> ''),
  CONSTRAINT chk_customers_credit_terms CHECK (credit_terms_days BETWEEN 0 AND 365)
);
COMMENT ON TABLE customers IS 'A B2B buyer that owes the business money.';
COMMENT ON COLUMN customers.id IS 'Surrogate key.';
COMMENT ON COLUMN customers.name IS 'Business name, e.g. ABC Distributors.';
COMMENT ON COLUMN customers.email IS 'Address reminders are sent to (example.in in seed).';
COMMENT ON COLUMN customers.phone IS 'Phone for WhatsApp and calls.';
COMMENT ON COLUMN customers.segment IS 'enterprise, mid_market or sme.';
COMMENT ON COLUMN customers.credit_terms_days IS 'Agreed days to pay.';
COMMENT ON COLUMN customers.created_at IS 'When the row was written.';
CREATE UNIQUE INDEX uq_customers_name ON customers (lower(name));

-- Serves US-00-001, US-00-005, US-00-006, US-00-016, US-00-019
CREATE TABLE invoices (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  number text NOT NULL,
  invoice_date date NOT NULL,
  due_date date NOT NULL,
  amount_paise bigint NOT NULL,
  status text NOT NULL DEFAULT 'unpaid',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_invoices PRIMARY KEY (id),
  CONSTRAINT fk_invoices_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT chk_invoices_status CHECK (status IN ('unpaid','partially_paid','paid','disputed')),
  CONSTRAINT chk_invoices_amount_positive CHECK (amount_paise > 0),
  CONSTRAINT chk_invoices_dates CHECK (due_date >= invoice_date),
  CONSTRAINT chk_invoices_number_shape CHECK (number ~ '^INV-[0-9]+$')
);
COMMENT ON TABLE invoices IS 'One invoice raised on a customer; the unit every reminder cites.';
COMMENT ON COLUMN invoices.id IS 'Surrogate key.';
COMMENT ON COLUMN invoices.customer_id IS 'Who owes it.';
COMMENT ON COLUMN invoices.number IS 'Invoice number, e.g. INV-1021.';
COMMENT ON COLUMN invoices.invoice_date IS 'Date issued.';
COMMENT ON COLUMN invoices.due_date IS 'Date payment is due.';
COMMENT ON COLUMN invoices.amount_paise IS 'Invoice amount in paise.';
COMMENT ON COLUMN invoices.status IS 'unpaid, partially_paid, paid or disputed; written only by allocation and dispute services.';
COMMENT ON COLUMN invoices.created_at IS 'When the row was written.';
COMMENT ON COLUMN invoices.updated_at IS 'Last change to the row.';
CREATE UNIQUE INDEX uq_invoices_number ON invoices (number);
CREATE INDEX idx_invoices_customer_id_due_date ON invoices (customer_id, due_date);
CREATE INDEX idx_invoices_open_due_date ON invoices (due_date) WHERE status <> 'paid';

-- Serves US-00-017, US-00-018, US-00-019, US-03-004
CREATE TABLE payments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid,
  amount_paise bigint NOT NULL,
  received_on date NOT NULL,
  reference text,
  source text NOT NULL,
  bank_event_id text,
  match_status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_payments PRIMARY KEY (id),
  CONSTRAINT fk_payments_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT chk_payments_amount_positive CHECK (amount_paise > 0),
  CONSTRAINT chk_payments_source CHECK (source IN ('bank_feed','payment_link','manual')),
  CONSTRAINT chk_payments_match_status CHECK (match_status IN ('matched','needs_verification')),
  CONSTRAINT chk_payments_matched_has_customer CHECK (match_status <> 'matched' OR customer_id IS NOT NULL),
  CONSTRAINT chk_payments_bank_event CHECK (source <> 'bank_feed' OR bank_event_id IS NOT NULL)
);
COMMENT ON TABLE payments IS 'Money received, from the bank feed, the payment link or entered by a collector.';
COMMENT ON COLUMN payments.id IS 'Surrogate key.';
COMMENT ON COLUMN payments.customer_id IS 'Matched customer; null while it needs human verification.';
COMMENT ON COLUMN payments.amount_paise IS 'Amount received in paise.';
COMMENT ON COLUMN payments.received_on IS 'Business date the money arrived: clock.today() at ingest, never the webhook timestamp.';
COMMENT ON COLUMN payments.reference IS 'Bank or UTR reference text.';
COMMENT ON COLUMN payments.source IS 'bank_feed, payment_link or manual.';
COMMENT ON COLUMN payments.bank_event_id IS 'Bank feed event id for idempotency.';
COMMENT ON COLUMN payments.match_status IS 'matched or needs_verification.';
COMMENT ON COLUMN payments.created_at IS 'When the row was written.';
CREATE UNIQUE INDEX uq_payments_bank_event_id ON payments (bank_event_id) WHERE bank_event_id IS NOT NULL;
CREATE INDEX idx_payments_customer_id_received_on ON payments (customer_id, received_on);

-- Serves US-00-001, US-00-019
CREATE TABLE payment_allocations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  payment_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  amount_paise bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_payment_allocations PRIMARY KEY (id),
  CONSTRAINT fk_payment_allocations_payment_id FOREIGN KEY (payment_id) REFERENCES payments (id) ON DELETE CASCADE,
  CONSTRAINT fk_payment_allocations_invoice_id FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT,
  CONSTRAINT chk_payment_allocations_amount_positive CHECK (amount_paise > 0)
);
COMMENT ON TABLE payment_allocations IS 'The part of a payment applied to one invoice.';
COMMENT ON COLUMN payment_allocations.id IS 'Surrogate key.';
COMMENT ON COLUMN payment_allocations.payment_id IS 'The payment being applied.';
COMMENT ON COLUMN payment_allocations.invoice_id IS 'The invoice it pays.';
COMMENT ON COLUMN payment_allocations.amount_paise IS 'Amount applied in paise.';
COMMENT ON COLUMN payment_allocations.created_at IS 'When the row was written.';
CREATE UNIQUE INDEX uq_payment_allocations_payment_invoice ON payment_allocations (payment_id, invoice_id);
CREATE INDEX idx_payment_allocations_invoice_id ON payment_allocations (invoice_id);

-- Serves US-01-001, US-00-008, US-01-011
CREATE TABLE agent_runs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  run_date date NOT NULL,
  trigger text NOT NULL,
  status text NOT NULL DEFAULT 'running',
  outcome text,
  tool_call_count smallint NOT NULL DEFAULT 0,
  action text,
  channel text,
  tone text,
  reason text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  CONSTRAINT pk_agent_runs PRIMARY KEY (id),
  CONSTRAINT fk_agent_runs_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT chk_agent_runs_trigger CHECK (trigger IN ('scheduled','manual','reply','payment')),
  CONSTRAINT chk_agent_runs_status CHECK (status IN ('running','finished')),
  CONSTRAINT chk_agent_runs_outcome CHECK (outcome IS NULL OR outcome IN ('WAIT_FOR_APPROVAL','ESCALATED','STOPPED_LIMIT','NO_ACTION','FAILED')),
  CONSTRAINT chk_agent_runs_tool_limit CHECK (tool_call_count BETWEEN 0 AND 4),
  CONSTRAINT chk_agent_runs_finished CHECK ((status = 'finished') = (outcome IS NOT NULL AND finished_at IS NOT NULL)),
  CONSTRAINT chk_agent_runs_channel CHECK (channel IS NULL OR channel IN ('email','whatsapp','voice')),
  CONSTRAINT chk_agent_runs_tone CHECK (tone IS NULL OR tone IN ('gentle','firm','final'))
);
COMMENT ON TABLE agent_runs IS 'One bounded orchestrator run for one customer.';
COMMENT ON COLUMN agent_runs.id IS 'Surrogate key.';
COMMENT ON COLUMN agent_runs.customer_id IS 'The customer the run is about.';
COMMENT ON COLUMN agent_runs.run_date IS 'Demo-clock date the run belongs to.';
COMMENT ON COLUMN agent_runs.trigger IS 'scheduled, manual, reply or payment.';
COMMENT ON COLUMN agent_runs.status IS 'running or finished.';
COMMENT ON COLUMN agent_runs.outcome IS 'WAIT_FOR_APPROVAL, ESCALATED, STOPPED_LIMIT, NO_ACTION or FAILED.';
COMMENT ON COLUMN agent_runs.tool_call_count IS 'Tool calls made.';
COMMENT ON COLUMN agent_runs.action IS 'Action selected, e.g. send_reminder.';
COMMENT ON COLUMN agent_runs.channel IS 'Channel selected.';
COMMENT ON COLUMN agent_runs.tone IS 'Tone selected by code.';
COMMENT ON COLUMN agent_runs.reason IS 'Why the action or stop.';
COMMENT ON COLUMN agent_runs.started_at IS 'Start time.';
COMMENT ON COLUMN agent_runs.finished_at IS 'End time.';
CREATE UNIQUE INDEX uq_agent_runs_scheduled_per_day ON agent_runs (customer_id, run_date) WHERE trigger = 'scheduled';
CREATE UNIQUE INDEX uq_agent_runs_running_customer ON agent_runs (customer_id) WHERE status = 'running';
CREATE INDEX idx_agent_runs_customer_id_started_at ON agent_runs (customer_id, started_at);

-- Serves US-00-008, US-01-011
CREATE TABLE agent_steps (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  agent_run_id uuid NOT NULL,
  seq smallint NOT NULL,
  role text NOT NULL,
  tool_name text NOT NULL,
  arguments_redacted jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_summary text NOT NULL,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_agent_steps PRIMARY KEY (id),
  CONSTRAINT fk_agent_steps_agent_run_id FOREIGN KEY (agent_run_id) REFERENCES agent_runs (id) ON DELETE CASCADE,
  CONSTRAINT chk_agent_steps_seq CHECK (seq BETWEEN 1 AND 4),
  CONSTRAINT chk_agent_steps_role CHECK (role IN ('collections','reply_understanding','payment_verification','escalation'))
);
COMMENT ON TABLE agent_steps IS 'One tool call inside a run, with redacted arguments.';
COMMENT ON COLUMN agent_steps.id IS 'Surrogate key.';
COMMENT ON COLUMN agent_steps.agent_run_id IS 'The run.';
COMMENT ON COLUMN agent_steps.seq IS 'Order within the run, 1 to 4.';
COMMENT ON COLUMN agent_steps.role IS 'collections, reply_understanding, payment_verification or escalation.';
COMMENT ON COLUMN agent_steps.tool_name IS 'Tool called.';
COMMENT ON COLUMN agent_steps.arguments_redacted IS 'Arguments with PII replaced by [redacted:*].';
COMMENT ON COLUMN agent_steps.result_summary IS 'One-line result.';
COMMENT ON COLUMN agent_steps.error_code IS 'Typed error code when the tool failed.';
COMMENT ON COLUMN agent_steps.created_at IS 'When the row was written.';
CREATE UNIQUE INDEX uq_agent_steps_run_seq ON agent_steps (agent_run_id, seq);

-- Serves US-00-005, US-00-009, US-00-010, US-00-011, US-01-002, US-00-024
CREATE TABLE messages (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  agent_run_id uuid,
  kind text NOT NULL,
  channel text NOT NULL,
  tone text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  subject text NOT NULL,
  body text NOT NULL,
  version integer NOT NULL DEFAULT 1,
  verified_version integer,
  guardrail_report jsonb,
  approved_by uuid,
  approved_at timestamptz,
  rejected_reason text,
  sent_at timestamptz,
  send_attempts smallint NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_messages PRIMARY KEY (id),
  CONSTRAINT fk_messages_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT fk_messages_agent_run_id FOREIGN KEY (agent_run_id) REFERENCES agent_runs (id) ON DELETE SET NULL,
  CONSTRAINT fk_messages_approved_by FOREIGN KEY (approved_by) REFERENCES users (id) ON DELETE RESTRICT,
  CONSTRAINT chk_messages_status CHECK (status IN ('draft','pending_approval','approved','rejected','sent','failed')),
  CONSTRAINT chk_messages_kind CHECK (kind IN ('reminder','followup','statement','dispute_ack')),
  CONSTRAINT chk_messages_channel CHECK (channel IN ('email','whatsapp','voice')),
  CONSTRAINT chk_messages_tone CHECK (tone IN ('gentle','firm','final')),
  CONSTRAINT chk_messages_rejected_reason CHECK (status <> 'rejected' OR (rejected_reason IS NOT NULL AND btrim(rejected_reason) <> '')),
  CONSTRAINT chk_messages_approved_verified CHECK (status NOT IN ('approved','sent') OR verified_version = version),
  CONSTRAINT chk_messages_sent_at CHECK ((status = 'sent') = (sent_at IS NOT NULL))
);
COMMENT ON TABLE messages IS 'A drafted, approved, sent or rejected outbound message.';
COMMENT ON COLUMN messages.id IS 'Surrogate key.';
COMMENT ON COLUMN messages.customer_id IS 'Recipient customer.';
COMMENT ON COLUMN messages.agent_run_id IS 'Run that drafted it; null for statement drafts from the UI.';
COMMENT ON COLUMN messages.kind IS 'reminder, followup, statement or dispute_ack.';
COMMENT ON COLUMN messages.channel IS 'email, whatsapp or voice.';
COMMENT ON COLUMN messages.tone IS 'gentle, firm or final.';
COMMENT ON COLUMN messages.status IS 'draft, pending_approval, approved, rejected, sent or failed.';
COMMENT ON COLUMN messages.subject IS 'Email subject (names the customer).';
COMMENT ON COLUMN messages.body IS 'Final text after placeholders were filled.';
COMMENT ON COLUMN messages.version IS 'Incremented on every edit.';
COMMENT ON COLUMN messages.verified_version IS 'Version that last passed guardrails.';
COMMENT ON COLUMN messages.guardrail_report IS 'Per-token verification result shown in the queue.';
COMMENT ON COLUMN messages.approved_by IS 'Who approved.';
COMMENT ON COLUMN messages.approved_at IS 'When approved.';
COMMENT ON COLUMN messages.rejected_reason IS 'Why rejected.';
COMMENT ON COLUMN messages.sent_at IS 'When delivered to the channel.';
COMMENT ON COLUMN messages.send_attempts IS 'Delivery attempts.';
COMMENT ON COLUMN messages.last_error IS 'Last delivery error code; IN_FLIGHT while a send is claimed, UNCONFIRMED if the worker died mid-send.';
COMMENT ON COLUMN messages.created_at IS 'When the row was written.';
COMMENT ON COLUMN messages.updated_at IS 'Last change to the row.';
CREATE INDEX idx_messages_status_created_at ON messages (status, created_at) WHERE status IN ('pending_approval','approved');
CREATE INDEX idx_messages_customer_id_created_at ON messages (customer_id, created_at);
CREATE INDEX idx_messages_agent_run_id ON messages (agent_run_id);

-- Serves US-00-005, US-00-016
CREATE TABLE message_invoices (
  message_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  CONSTRAINT pk_message_invoices PRIMARY KEY (message_id, invoice_id),
  CONSTRAINT fk_message_invoices_message_id FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
  CONSTRAINT fk_message_invoices_invoice_id FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT
);
COMMENT ON TABLE message_invoices IS 'The invoices a draft covers.';
COMMENT ON COLUMN message_invoices.message_id IS 'The message.';
COMMENT ON COLUMN message_invoices.invoice_id IS 'A cited invoice.';
CREATE INDEX idx_message_invoices_invoice_id ON message_invoices (invoice_id);

-- Serves US-03-001, US-00-012, US-00-013
CREATE TABLE replies (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  message_id uuid,
  body text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  classification text,
  amount_paise bigint,
  stated_date date,
  invoice_refs text[] NOT NULL DEFAULT '{}',
  confidence numeric(3,2),
  recommended_action text,
  needs_review boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_replies PRIMARY KEY (id),
  CONSTRAINT fk_replies_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT fk_replies_message_id FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE SET NULL,
  CONSTRAINT chk_replies_classification CHECK (classification IS NULL OR classification IN ('PROMISE','PART_PAYMENT','DISPUTE','STATEMENT_REQUEST','PAYMENT_CONFIRMATION','NO_INTENT_UNCLEAR','OTHER_NOISE')),
  CONSTRAINT chk_replies_confidence CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  CONSTRAINT chk_replies_amount_positive CHECK (amount_paise IS NULL OR amount_paise > 0)
);
COMMENT ON TABLE replies IS 'A customer''s reply and its classification.';
COMMENT ON COLUMN replies.id IS 'Surrogate key.';
COMMENT ON COLUMN replies.customer_id IS 'Who replied.';
COMMENT ON COLUMN replies.message_id IS 'Message it answers; null for seeded history.';
COMMENT ON COLUMN replies.body IS 'Reply text, untrusted.';
COMMENT ON COLUMN replies.received_at IS 'When it arrived.';
COMMENT ON COLUMN replies.classification IS 'One of the seven classes, null until classified.';
COMMENT ON COLUMN replies.amount_paise IS 'Amount parsed in code from the text.';
COMMENT ON COLUMN replies.stated_date IS 'Date resolved against the demo clock.';
COMMENT ON COLUMN replies.invoice_refs IS 'Invoice numbers mentioned.';
COMMENT ON COLUMN replies.confidence IS 'Classifier confidence 0.00 to 1.00.';
COMMENT ON COLUMN replies.recommended_action IS 'Next action chosen by code.';
COMMENT ON COLUMN replies.needs_review IS 'True when routed to a human.';
COMMENT ON COLUMN replies.created_at IS 'When the row was written.';
CREATE INDEX idx_replies_customer_id_received_at ON replies (customer_id, received_at);
CREATE INDEX idx_replies_message_id ON replies (message_id);

-- Serves US-00-014, US-00-020, US-00-021
CREATE TABLE promises (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  reply_id uuid,
  amount_paise bigint NOT NULL,
  promised_date date NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_promises PRIMARY KEY (id),
  CONSTRAINT fk_promises_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT fk_promises_reply_id FOREIGN KEY (reply_id) REFERENCES replies (id) ON DELETE SET NULL,
  CONSTRAINT chk_promises_status CHECK (status IN ('pending','fulfilled','partially_fulfilled','missed')),
  CONSTRAINT chk_promises_amount_positive CHECK (amount_paise > 0),
  CONSTRAINT chk_promises_resolved CHECK ((status = 'pending') = (resolved_at IS NULL))
);
COMMENT ON TABLE promises IS 'A customer''s commitment to pay an amount by a date.';
COMMENT ON COLUMN promises.id IS 'Surrogate key.';
COMMENT ON COLUMN promises.customer_id IS 'Who promised.';
COMMENT ON COLUMN promises.reply_id IS 'Reply it came from; null for seeded history.';
COMMENT ON COLUMN promises.amount_paise IS 'Promised amount in paise.';
COMMENT ON COLUMN promises.promised_date IS 'Date promised.';
COMMENT ON COLUMN promises.status IS 'pending, fulfilled, partially_fulfilled or missed.';
COMMENT ON COLUMN promises.resolved_at IS 'When the promise check settled it.';
COMMENT ON COLUMN promises.created_at IS 'When the row was written.';
CREATE INDEX idx_promises_status_promised_date ON promises (status, promised_date);
CREATE INDEX idx_promises_customer_id ON promises (customer_id);

-- Serves US-00-014
CREATE TABLE promise_invoices (
  promise_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  CONSTRAINT pk_promise_invoices PRIMARY KEY (promise_id, invoice_id),
  CONSTRAINT fk_promise_invoices_promise_id FOREIGN KEY (promise_id) REFERENCES promises (id) ON DELETE CASCADE,
  CONSTRAINT fk_promise_invoices_invoice_id FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT
);
COMMENT ON TABLE promise_invoices IS 'Link from a promise to the invoices it pays.';
COMMENT ON COLUMN promise_invoices.promise_id IS 'The promise.';
COMMENT ON COLUMN promise_invoices.invoice_id IS 'A covered invoice.';
CREATE INDEX idx_promise_invoices_invoice_id ON promise_invoices (invoice_id);

-- Serves US-00-016
CREATE TABLE disputes (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  reply_id uuid,
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  resolution_note text,
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_disputes PRIMARY KEY (id),
  CONSTRAINT fk_disputes_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT fk_disputes_invoice_id FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT,
  CONSTRAINT fk_disputes_reply_id FOREIGN KEY (reply_id) REFERENCES replies (id) ON DELETE SET NULL,
  CONSTRAINT chk_disputes_status CHECK (status IN ('open','resolved')),
  CONSTRAINT chk_disputes_resolved CHECK ((status = 'resolved') = (resolved_at IS NOT NULL))
);
COMMENT ON TABLE disputes IS 'A customer''s contest of one invoice.';
COMMENT ON COLUMN disputes.id IS 'Surrogate key.';
COMMENT ON COLUMN disputes.customer_id IS 'Who disputes.';
COMMENT ON COLUMN disputes.invoice_id IS 'The invoice disputed.';
COMMENT ON COLUMN disputes.reply_id IS 'Reply that raised it.';
COMMENT ON COLUMN disputes.reason IS 'Reason in a short phrase, e.g. quantity mismatch.';
COMMENT ON COLUMN disputes.status IS 'open or resolved.';
COMMENT ON COLUMN disputes.resolution_note IS 'How it was resolved.';
COMMENT ON COLUMN disputes.resolved_at IS 'When resolved.';
COMMENT ON COLUMN disputes.created_at IS 'When the row was written.';
CREATE UNIQUE INDEX uq_disputes_open_invoice ON disputes (invoice_id) WHERE status = 'open';
CREATE INDEX idx_disputes_customer_id ON disputes (customer_id);

-- Serves US-00-016, US-00-012, US-00-013, US-00-017, US-00-018
CREATE TABLE escalations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  kind text NOT NULL,
  reason text NOT NULL,
  dispute_id uuid,
  reply_id uuid,
  payment_id uuid,
  status text NOT NULL DEFAULT 'open',
  resolved_by uuid,
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_escalations PRIMARY KEY (id),
  CONSTRAINT fk_escalations_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT fk_escalations_dispute_id FOREIGN KEY (dispute_id) REFERENCES disputes (id) ON DELETE SET NULL,
  CONSTRAINT fk_escalations_reply_id FOREIGN KEY (reply_id) REFERENCES replies (id) ON DELETE SET NULL,
  CONSTRAINT fk_escalations_payment_id FOREIGN KEY (payment_id) REFERENCES payments (id) ON DELETE SET NULL,
  CONSTRAINT fk_escalations_resolved_by FOREIGN KEY (resolved_by) REFERENCES users (id) ON DELETE RESTRICT,
  CONSTRAINT chk_escalations_kind CHECK (kind IN ('dispute','low_confidence','injection_suspected','claim_not_found','payment_needs_verification')),
  CONSTRAINT chk_escalations_status CHECK (status IN ('open','resolved')),
  CONSTRAINT chk_escalations_resolved CHECK ((status = 'resolved') = (resolved_at IS NOT NULL))
);
COMMENT ON TABLE escalations IS 'A case handed to a human.';
COMMENT ON COLUMN escalations.id IS 'Surrogate key.';
COMMENT ON COLUMN escalations.customer_id IS 'Customer concerned.';
COMMENT ON COLUMN escalations.kind IS 'dispute, low_confidence, injection_suspected, claim_not_found or payment_needs_verification.';
COMMENT ON COLUMN escalations.reason IS 'Human-readable reason.';
COMMENT ON COLUMN escalations.dispute_id IS 'Source dispute.';
COMMENT ON COLUMN escalations.reply_id IS 'Source reply.';
COMMENT ON COLUMN escalations.payment_id IS 'Source payment.';
COMMENT ON COLUMN escalations.status IS 'open or resolved.';
COMMENT ON COLUMN escalations.resolved_by IS 'Who closed it.';
COMMENT ON COLUMN escalations.resolved_at IS 'When closed.';
COMMENT ON COLUMN escalations.created_at IS 'When the row was written.';
CREATE INDEX idx_escalations_status_created_at ON escalations (status, created_at) WHERE status = 'open';
CREATE INDEX idx_escalations_customer_id ON escalations (customer_id);
CREATE INDEX idx_escalations_dispute_id ON escalations (dispute_id);
CREATE INDEX idx_escalations_reply_id ON escalations (reply_id);
CREATE INDEX idx_escalations_payment_id ON escalations (payment_id);

-- Serves US-00-006, US-00-007, US-01-002, US-01-006, US-01-012
CREATE TABLE guardrail_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  check_name text NOT NULL,
  code text NOT NULL,
  customer_id uuid,
  message_id uuid,
  agent_run_id uuid,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_guardrail_events PRIMARY KEY (id),
  CONSTRAINT fk_guardrail_events_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE SET NULL,
  CONSTRAINT fk_guardrail_events_message_id FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE SET NULL,
  CONSTRAINT fk_guardrail_events_agent_run_id FOREIGN KEY (agent_run_id) REFERENCES agent_runs (id) ON DELETE SET NULL
);
COMMENT ON TABLE guardrail_events IS 'A record of one guardrail refusal.';
COMMENT ON COLUMN guardrail_events.id IS 'Surrogate key.';
COMMENT ON COLUMN guardrail_events.check_name IS 'Which check refused, e.g. amount.';
COMMENT ON COLUMN guardrail_events.code IS 'Typed error code, e.g. AMOUNT_MISMATCH.';
COMMENT ON COLUMN guardrail_events.customer_id IS 'Customer concerned, if any.';
COMMENT ON COLUMN guardrail_events.message_id IS 'Message concerned, if any.';
COMMENT ON COLUMN guardrail_events.agent_run_id IS 'Run concerned, if any.';
COMMENT ON COLUMN guardrail_events.detail IS 'Offending token and expected value, no PII bodies.';
COMMENT ON COLUMN guardrail_events.created_at IS 'When the row was written.';
CREATE INDEX idx_guardrail_events_created_at ON guardrail_events (created_at);
CREATE INDEX idx_guardrail_events_customer_id ON guardrail_events (customer_id);
CREATE INDEX idx_guardrail_events_message_id ON guardrail_events (message_id);
CREATE INDEX idx_guardrail_events_agent_run_id ON guardrail_events (agent_run_id);

-- Serves US-01-008, US-01-009
CREATE TABLE llm_calls (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  agent_run_id uuid,
  prompt_name text NOT NULL,
  prompt_version integer NOT NULL,
  model text NOT NULL,
  mode text NOT NULL,
  replay_key text NOT NULL,
  input_tokens integer NOT NULL DEFAULT 0,
  output_tokens integer NOT NULL DEFAULT 0,
  cost_micro_usd bigint NOT NULL DEFAULT 0,
  latency_ms integer,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_llm_calls PRIMARY KEY (id),
  CONSTRAINT fk_llm_calls_agent_run_id FOREIGN KEY (agent_run_id) REFERENCES agent_runs (id) ON DELETE SET NULL,
  CONSTRAINT chk_llm_calls_mode CHECK (mode IN ('live','replay','record')),
  CONSTRAINT chk_llm_calls_nonneg CHECK (input_tokens >= 0 AND output_tokens >= 0 AND cost_micro_usd >= 0)
);
COMMENT ON TABLE llm_calls IS 'One model call through the gateway with tokens and cost.';
COMMENT ON COLUMN llm_calls.id IS 'Surrogate key.';
COMMENT ON COLUMN llm_calls.agent_run_id IS 'Run that made the call; null for evals.';
COMMENT ON COLUMN llm_calls.prompt_name IS 'Prompt registry name.';
COMMENT ON COLUMN llm_calls.prompt_version IS 'Prompt version.';
COMMENT ON COLUMN llm_calls.model IS 'Model id used.';
COMMENT ON COLUMN llm_calls.mode IS 'live, replay or record.';
COMMENT ON COLUMN llm_calls.replay_key IS 'name@vN:sha256 of normalised input.';
COMMENT ON COLUMN llm_calls.input_tokens IS 'Prompt tokens.';
COMMENT ON COLUMN llm_calls.output_tokens IS 'Completion tokens.';
COMMENT ON COLUMN llm_calls.cost_micro_usd IS 'Cost in micro-dollars (integer).';
COMMENT ON COLUMN llm_calls.latency_ms IS 'Wall time.';
COMMENT ON COLUMN llm_calls.error_code IS 'LLM_UPSTREAM, LLM_TIMEOUT, BUDGET_EXHAUSTED or REPLAY_MISS.';
COMMENT ON COLUMN llm_calls.created_at IS 'When the row was written.';
CREATE INDEX idx_llm_calls_created_at ON llm_calls (created_at);
CREATE INDEX idx_llm_calls_agent_run_id ON llm_calls (agent_run_id);

-- Serves US-00-022, US-00-004
CREATE TABLE timeline_events (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  business_date date NOT NULL,
  kind text NOT NULL,
  actor text NOT NULL,
  actor_user_id uuid,
  amount_paise bigint,
  ref_type text,
  ref_id uuid,
  summary text NOT NULL,
  CONSTRAINT pk_timeline_events PRIMARY KEY (id),
  CONSTRAINT fk_timeline_events_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
  CONSTRAINT fk_timeline_events_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT chk_timeline_events_actor CHECK (actor IN ('ai','human','system','customer')),
  CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced')),
  CONSTRAINT chk_timeline_events_ref CHECK ((ref_type IS NULL) = (ref_id IS NULL))
);
COMMENT ON TABLE timeline_events IS 'One state change about a customer, for the timeline.';
COMMENT ON COLUMN timeline_events.id IS 'Surrogate key.';
COMMENT ON COLUMN timeline_events.customer_id IS 'Whose timeline.';
COMMENT ON COLUMN timeline_events.occurred_at IS 'Wall time of the change.';
COMMENT ON COLUMN timeline_events.business_date IS 'Demo-clock date of the change.';
COMMENT ON COLUMN timeline_events.kind IS 'Event kind from the REQ-081 list.';
COMMENT ON COLUMN timeline_events.actor IS 'ai, human, system or customer.';
COMMENT ON COLUMN timeline_events.actor_user_id IS 'Human actor.';
COMMENT ON COLUMN timeline_events.amount_paise IS 'Amount shown on the event.';
COMMENT ON COLUMN timeline_events.ref_type IS 'Kind of the related record.';
COMMENT ON COLUMN timeline_events.ref_id IS 'Id of the related record.';
COMMENT ON COLUMN timeline_events.summary IS 'One-line text, no reply bodies.';
CREATE INDEX idx_timeline_events_customer_id_occurred_at ON timeline_events (customer_id, occurred_at);
CREATE INDEX idx_timeline_events_actor_user_id ON timeline_events (actor_user_id);

-- Serves US-01-001, US-00-011, US-00-020
CREATE TABLE jobs (
  id bigint NOT NULL GENERATED ALWAYS AS IDENTITY,
  kind text NOT NULL,
  dedupe_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'queued',
  attempts smallint NOT NULL DEFAULT 0,
  max_attempts smallint NOT NULL DEFAULT 5,
  run_at timestamptz NOT NULL DEFAULT now(),
  locked_at timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_jobs PRIMARY KEY (id),
  CONSTRAINT chk_jobs_kind CHECK (kind IN ('daily_run','promise_check','send_message')),
  CONSTRAINT chk_jobs_status CHECK (status IN ('queued','running','done','dead')),
  CONSTRAINT chk_jobs_attempts CHECK (attempts BETWEEN 0 AND max_attempts)
);
COMMENT ON TABLE jobs IS 'One unit of background work for the worker.';
COMMENT ON COLUMN jobs.id IS 'Job id.';
COMMENT ON COLUMN jobs.kind IS 'daily_run, promise_check or send_message.';
COMMENT ON COLUMN jobs.dedupe_key IS 'run date or message id.';
COMMENT ON COLUMN jobs.payload IS 'Job arguments (ids only).';
COMMENT ON COLUMN jobs.status IS 'queued, running, done or dead.';
COMMENT ON COLUMN jobs.attempts IS 'Attempts so far.';
COMMENT ON COLUMN jobs.max_attempts IS 'Attempts allowed: 5 means the first try plus 4 retries.';
COMMENT ON COLUMN jobs.run_at IS 'Earliest time to run (backoff).';
COMMENT ON COLUMN jobs.locked_at IS 'When a worker took it.';
COMMENT ON COLUMN jobs.last_error IS 'Last error code.';
COMMENT ON COLUMN jobs.created_at IS 'When the row was written.';
CREATE UNIQUE INDEX uq_jobs_kind_dedupe_key ON jobs (kind, dedupe_key);
CREATE INDEX idx_jobs_status_run_at ON jobs (run_at) WHERE status = 'queued';

-- Serves US-03-001, US-01-005, US-00-017, US-03-004
CREATE TABLE idempotency_keys (
  key text NOT NULL,
  route text NOT NULL,
  request_sha256 text NOT NULL,
  status_code smallint NOT NULL,
  response_body jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_idempotency_keys PRIMARY KEY (key, route),
  CONSTRAINT chk_idempotency_keys_status CHECK (status_code BETWEEN 200 AND 599)
);
COMMENT ON TABLE idempotency_keys IS 'The stored response for a POST replayed with the same Idempotency-Key.';
COMMENT ON COLUMN idempotency_keys.key IS 'Client-supplied Idempotency-Key.';
COMMENT ON COLUMN idempotency_keys.route IS 'Method and path template the key was used on.';
COMMENT ON COLUMN idempotency_keys.request_sha256 IS 'Hash of the request body.';
COMMENT ON COLUMN idempotency_keys.status_code IS 'First response status.';
COMMENT ON COLUMN idempotency_keys.response_body IS 'First response body (ids and codes, no PII bodies).';
COMMENT ON COLUMN idempotency_keys.created_at IS 'When the row was written.';

-- Derived balances: amount paid and remaining per invoice (REQ-008, eng review A6).
CREATE VIEW invoice_balances AS
SELECT i.id AS invoice_id, i.customer_id, i.amount_paise,
       COALESCE(SUM(a.amount_paise), 0)::bigint AS paid_paise,
       (i.amount_paise - COALESCE(SUM(a.amount_paise), 0))::bigint AS remaining_paise
FROM invoices i LEFT JOIN payment_allocations a ON a.invoice_id = i.id
GROUP BY i.id;

COMMIT;
