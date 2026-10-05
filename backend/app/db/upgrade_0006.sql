-- HACK-003 F1: voice calls placed by the AI collections assistant, and what was said on them (speech to text only;
-- calls are not recorded).
CREATE TABLE calls (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  requested_by uuid,
  provider text NOT NULL,
  simulated boolean NOT NULL,
  status text NOT NULL DEFAULT 'requested',
  state text NOT NULL DEFAULT 'opening',
  outcome text,
  provider_call_id text,
  promise_id uuid,
  dispute_id uuid,
  summary text,
  follow_up_on date,
  unclear_turns smallint NOT NULL DEFAULT 0,
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  CONSTRAINT pk_calls PRIMARY KEY (id),
  CONSTRAINT fk_calls_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT,
  CONSTRAINT fk_calls_requested_by FOREIGN KEY (requested_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT fk_calls_promise_id FOREIGN KEY (promise_id) REFERENCES promises (id) ON DELETE SET NULL,
  CONSTRAINT fk_calls_dispute_id FOREIGN KEY (dispute_id) REFERENCES disputes (id) ON DELETE SET NULL,
  CONSTRAINT chk_calls_status CHECK (status IN ('requested','in_progress','completed','failed','no_answer','wrong_number')),
  CONSTRAINT chk_calls_state CHECK (state IN ('opening','listening','offered_details','ended')),
  CONSTRAINT chk_calls_outcome CHECK (outcome IS NULL OR outcome IN ('promise','dispute','invoice_request',
    'payment_link_request','payment_claim','wrong_number','unavailable','escalated','no_commitment','failed')),
  CONSTRAINT chk_calls_ended CHECK ((status IN ('requested','in_progress')) = (ended_at IS NULL))
);
COMMENT ON TABLE calls IS 'A voice call by the collections assistant; simulated says whether a real phone rang.';
CREATE UNIQUE INDEX uq_calls_active_customer ON calls (customer_id) WHERE status IN ('requested','in_progress');
CREATE UNIQUE INDEX uq_calls_provider_call_id ON calls (provider_call_id) WHERE provider_call_id IS NOT NULL;
CREATE INDEX idx_calls_customer_id_started_at ON calls (customer_id, started_at);
CREATE INDEX idx_calls_requested_by ON calls (requested_by);
CREATE INDEX idx_calls_promise_id ON calls (promise_id);
CREATE INDEX idx_calls_dispute_id ON calls (dispute_id);
CREATE TABLE call_turns (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  call_id uuid NOT NULL,
  seq smallint NOT NULL,
  speaker text NOT NULL,
  text text NOT NULL,
  intent text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_call_turns PRIMARY KEY (id),
  CONSTRAINT fk_call_turns_call_id FOREIGN KEY (call_id) REFERENCES calls (id) ON DELETE CASCADE,
  CONSTRAINT chk_call_turns_speaker CHECK (speaker IN ('ai','customer')),
  CONSTRAINT chk_call_turns_text CHECK (length(text) <= 2000),
  CONSTRAINT chk_call_turns_seq CHECK (seq BETWEEN 1 AND 40)
);
COMMENT ON TABLE call_turns IS 'Each line of a call: the AI line (rendered by code, verified) or the customer speech-to-text.';
CREATE UNIQUE INDEX uq_call_turns_call_seq ON call_turns (call_id, seq);
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced','dispute_assigned','dispute_investigating','followup_created','followup_closed','contact_preferences_changed','note_added','call_requested','call_completed','call_failed'));
