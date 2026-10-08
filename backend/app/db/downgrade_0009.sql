DELETE FROM jobs WHERE kind = 'google_sync';
ALTER TABLE jobs DROP CONSTRAINT chk_jobs_kind;
ALTER TABLE jobs ADD CONSTRAINT chk_jobs_kind CHECK (kind IN ('daily_run','promise_check','send_message'));
DROP TABLE calendar_events;
DROP TABLE inbound_emails;
DROP INDEX idx_messages_provider_ref;
ALTER TABLE messages DROP COLUMN provider_ref;
DROP TABLE google_account;
