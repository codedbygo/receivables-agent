-- HACK-009: one connected company Google account, Gmail threads on sent messages, incoming replies awaiting
-- review, and the Google Calendar events kept in step with promises and follow-up tasks (ADR-0018).
CREATE TABLE google_account (
  id smallint NOT NULL DEFAULT 1,
  email text NOT NULL,
  refresh_token_enc text NOT NULL,
  scopes text NOT NULL,
  connected_by uuid,
  connected_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_google_account PRIMARY KEY (id),
  CONSTRAINT chk_google_account_single CHECK (id = 1),
  CONSTRAINT fk_google_account_connected_by FOREIGN KEY (connected_by) REFERENCES users (id) ON DELETE SET NULL
);
COMMENT ON TABLE google_account IS 'The one company Google account the app sends from, reads replies from and writes calendar events to.';
COMMENT ON COLUMN google_account.refresh_token_enc IS 'Fernet-encrypted refresh token (GOOGLE_TOKEN_KEY); never stored or logged in clear.';

ALTER TABLE messages ADD COLUMN provider_ref text;
COMMENT ON COLUMN messages.provider_ref IS 'The provider''s id for the sent message; for Gmail, the thread id replies are matched on.';
CREATE INDEX idx_messages_provider_ref ON messages (provider_ref) WHERE provider_ref IS NOT NULL;

CREATE TABLE inbound_emails (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  gmail_message_id text NOT NULL,
  message_id uuid NOT NULL,
  customer_id uuid NOT NULL,
  from_address text NOT NULL,
  subject text NOT NULL,
  body text NOT NULL,
  received_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  reply_id uuid,
  reviewed_by uuid,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_inbound_emails PRIMARY KEY (id),
  CONSTRAINT uq_inbound_emails_gmail_message_id UNIQUE (gmail_message_id),
  CONSTRAINT fk_inbound_emails_message_id FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
  CONSTRAINT fk_inbound_emails_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
  CONSTRAINT fk_inbound_emails_reply_id FOREIGN KEY (reply_id) REFERENCES replies (id) ON DELETE SET NULL,
  CONSTRAINT fk_inbound_emails_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT chk_inbound_emails_status CHECK (status IN ('pending','accepted','dismissed'))
);
COMMENT ON TABLE inbound_emails IS 'A customer email found in a Gmail thread the app started, waiting for a collector to accept or dismiss it.';
CREATE INDEX idx_inbound_emails_pending ON inbound_emails (received_at) WHERE status = 'pending';

CREATE TABLE calendar_events (
  ref_type text NOT NULL,
  ref_id uuid NOT NULL,
  customer_id uuid NOT NULL,
  google_event_id text NOT NULL,
  synced_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_calendar_events PRIMARY KEY (ref_type, ref_id),
  CONSTRAINT fk_calendar_events_customer_id FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
  CONSTRAINT chk_calendar_events_ref_type CHECK (ref_type IN ('promise','follow_up'))
);
COMMENT ON TABLE calendar_events IS 'The Google Calendar event that stands for one open promise or follow-up task.';

ALTER TABLE jobs DROP CONSTRAINT chk_jobs_kind;
ALTER TABLE jobs ADD CONSTRAINT chk_jobs_kind CHECK (kind IN ('daily_run','promise_check','send_message','google_sync'));
