-- HACK-003 F3: internal notes a collector keeps about a customer. Never sent to the model or the portal.
CREATE TABLE customer_notes (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  author_id uuid,
  body text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_customer_notes PRIMARY KEY (id),
  CONSTRAINT fk_customer_notes_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
  CONSTRAINT fk_customer_notes_author_id FOREIGN KEY (author_id) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT chk_customer_notes_body CHECK (btrim(body) <> '' AND length(body) <= 2000)
);
COMMENT ON TABLE customer_notes IS 'Internal collector notes; shown to signed-in roles only.';
CREATE INDEX idx_customer_notes_customer_id_created_at ON customer_notes (customer_id, created_at);
CREATE INDEX idx_customer_notes_author_id ON customer_notes (author_id);
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced','dispute_assigned','dispute_investigating','followup_created','followup_closed','contact_preferences_changed','note_added'));
