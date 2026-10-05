DELETE FROM timeline_events WHERE kind IN ('dispute_assigned','dispute_investigating');
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced'));
UPDATE disputes SET status = 'open' WHERE status IN ('assigned','investigating');
DROP INDEX uq_disputes_active_invoice;
CREATE UNIQUE INDEX uq_disputes_open_invoice ON disputes (invoice_id) WHERE status = 'open';
ALTER TABLE disputes DROP CONSTRAINT chk_disputes_status;
ALTER TABLE disputes ADD CONSTRAINT chk_disputes_status CHECK (status IN ('open','resolved'));
ALTER TABLE disputes DROP COLUMN updated_at, DROP COLUMN assigned_to, DROP COLUMN assigned_team, DROP COLUMN category;
