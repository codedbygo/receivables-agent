DELETE FROM timeline_events WHERE kind = 'note_added';
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced','dispute_assigned','dispute_investigating','followup_created','followup_closed','contact_preferences_changed'));
DROP TABLE customer_notes;
