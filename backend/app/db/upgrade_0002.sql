-- HACK-003 F7: dispute lifecycle open -> assigned -> investigating -> resolved, category and routing.
ALTER TABLE disputes
  ADD COLUMN category text NOT NULL DEFAULT 'other',
  ADD COLUMN assigned_team text,
  ADD COLUMN assigned_to uuid,
  ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
  ADD CONSTRAINT fk_disputes_assigned_to FOREIGN KEY (assigned_to) REFERENCES users (id) ON DELETE SET NULL,
  ADD CONSTRAINT chk_disputes_category CHECK (category IN ('invoice_error','wrong_quantity','wrong_price',
    'duplicate_invoice','missing_delivery','service_issue','contract_issue','other')),
  ADD CONSTRAINT chk_disputes_team CHECK (assigned_team IS NULL OR assigned_team IN ('billing','operations','sales',
    'legal_contracts','collections'));
ALTER TABLE disputes DROP CONSTRAINT chk_disputes_status;
ALTER TABLE disputes ADD CONSTRAINT chk_disputes_status CHECK (status IN ('open','assigned','investigating','resolved'));
DROP INDEX uq_disputes_open_invoice;
CREATE UNIQUE INDEX uq_disputes_active_invoice ON disputes (invoice_id) WHERE status <> 'resolved';
CREATE INDEX idx_disputes_assigned_to ON disputes (assigned_to);
COMMENT ON COLUMN disputes.category IS 'One of eight categories, from rules over the customer text.';
COMMENT ON COLUMN disputes.assigned_team IS 'Team the dispute is routed to (policy dispute_routing).';
COMMENT ON COLUMN disputes.assigned_to IS 'Person investigating, when one has picked it up.';
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced','dispute_assigned','dispute_investigating'));
