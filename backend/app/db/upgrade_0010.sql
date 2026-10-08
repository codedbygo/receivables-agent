-- HACK-011: a person signs in with an email and password or with Google (ADR-0019). An admin turns people off
-- instead of deleting them, so their past actions keep a name; repeated wrong passwords lock the account a while.
ALTER TABLE users ADD COLUMN active boolean NOT NULL DEFAULT true;
ALTER TABLE users ADD COLUMN failed_logins integer NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN locked_until timestamptz;
COMMENT ON COLUMN users.active IS 'False: cannot sign in, and every session ends; the row stays for the audit trail.';
COMMENT ON COLUMN users.failed_logins IS 'Wrong passwords in a row; reset by a successful sign-in.';
COMMENT ON COLUMN users.locked_until IS 'Password sign-in refused until then, after too many wrong passwords.';
COMMENT ON COLUMN users.password_hash IS 'scrypt$<salt hex>$<hash hex>, or ! for a Google-only person (no password matches).';
