-- HACK-003 F2: SMS beside email, WhatsApp and voice; real or simulated per message; channel preference and consent.
ALTER TABLE messages DROP CONSTRAINT chk_messages_channel;
ALTER TABLE messages ADD CONSTRAINT chk_messages_channel CHECK (channel IN ('email','whatsapp','sms','voice'));
ALTER TABLE messages ADD COLUMN simulated boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN messages.simulated IS 'True when the provider that sent it was a simulator, not a real one.';
ALTER TABLE agent_runs DROP CONSTRAINT chk_agent_runs_channel;
ALTER TABLE agent_runs ADD CONSTRAINT chk_agent_runs_channel CHECK (channel IS NULL OR channel IN ('email','whatsapp','sms','voice'));
ALTER TABLE customers
  ADD COLUMN preferred_channel text,
  ADD COLUMN contact_consent jsonb NOT NULL DEFAULT '{"email": true}'::jsonb,
  ADD CONSTRAINT chk_customers_preferred_channel CHECK (preferred_channel IS NULL
    OR preferred_channel IN ('email','whatsapp','sms','voice'));
COMMENT ON COLUMN customers.preferred_channel IS 'Channel the customer asked us to use; null for none.';
COMMENT ON COLUMN customers.contact_consent IS 'Per channel opt-in, e.g. {"email": true, "whatsapp": true}.';
ALTER TABLE settings ADD COLUMN feature_sms boolean NOT NULL DEFAULT false;
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced','dispute_assigned','dispute_investigating','followup_created','followup_closed','contact_preferences_changed'));
