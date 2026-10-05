-- HACK-003 F6: links to the customer payment portal. Only the SHA-256 of the token is stored.
CREATE TABLE portal_links (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL,
  token_sha256 text NOT NULL,
  created_by uuid,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  writes smallint NOT NULL DEFAULT 0,
  last_used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_portal_links PRIMARY KEY (id),
  CONSTRAINT fk_portal_links_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
  CONSTRAINT fk_portal_links_created_by FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT chk_portal_links_token CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT chk_portal_links_writes CHECK (writes BETWEEN 0 AND 20)
);
COMMENT ON TABLE portal_links IS 'A signed-link session for one customer; expires, can be revoked, capped at 20 writes.';
CREATE UNIQUE INDEX uq_portal_links_token_sha256 ON portal_links (token_sha256);
CREATE INDEX idx_portal_links_customer_id ON portal_links (customer_id);
CREATE INDEX idx_portal_links_created_by ON portal_links (created_by);
ALTER TABLE timeline_events DROP CONSTRAINT chk_timeline_events_kind;
ALTER TABLE timeline_events ADD CONSTRAINT chk_timeline_events_kind CHECK (kind IN ('invoice_due','reminder_drafted','guardrail_passed','guardrail_failed','approved','edited','rejected','sent','send_failed','reply_received','classified','promise_logged','payment_received','payment_matched','promise_fulfilled','promise_partially_fulfilled','promise_missed','dispute_opened','dispute_resolved','escalation_created','escalation_resolved','clock_advanced','dispute_assigned','dispute_investigating','followup_created','followup_closed','contact_preferences_changed','note_added','call_requested','call_completed','call_failed','portal_link_created','portal_link_revoked'));
