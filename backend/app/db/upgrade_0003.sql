-- HACK-003 F5: a follow-up task for every missed or partly kept promise.
CREATE TABLE follow_up_tasks (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  promise_id uuid NOT NULL,
  kind text NOT NULL,
  due_on date NOT NULL,
  status text NOT NULL DEFAULT 'open',
  recommended_action text NOT NULL,
  message_id uuid,
  closed_by uuid,
  closed_at timestamptz,
  close_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_follow_up_tasks PRIMARY KEY (id),
  CONSTRAINT fk_follow_up_tasks_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT fk_follow_up_tasks_promise_id FOREIGN KEY (promise_id) REFERENCES promises (id) ON DELETE CASCADE,
  CONSTRAINT fk_follow_up_tasks_message_id FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE SET NULL,
  CONSTRAINT fk_follow_up_tasks_closed_by FOREIGN KEY (closed_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT chk_follow_up_tasks_kind CHECK (kind IN ('missed_promise','partial_promise')),
  CONSTRAINT chk_follow_up_tasks_status CHECK (status IN ('open','done','cancelled')),
  CONSTRAINT chk_follow_up_tasks_closed CHECK ((status = 'open') = (closed_at IS NULL))
);
COMMENT ON TABLE follow_up_tasks IS 'Work a collector owes a customer after a promise was missed or partly kept.';
CREATE UNIQUE INDEX uq_follow_up_tasks_promise_id ON follow_up_tasks (promise_id);
CREATE INDEX idx_follow_up_tasks_customer_id ON follow_up_tasks (customer_id);
CREATE INDEX idx_follow_up_tasks_open_due_on ON follow_up_tasks (due_on) WHERE status = 'open';
CREATE INDEX idx_follow_up_tasks_message_id ON follow_up_tasks (message_id);
CREATE INDEX idx_follow_up_tasks_closed_by ON follow_up_tasks (closed_by);
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced','dispute_assigned','dispute_investigating','followup_created','followup_closed'));
