COMMENT ON COLUMN users.password_hash IS 'Password hash (argon2 or bcrypt).';
ALTER TABLE users DROP COLUMN locked_until;
ALTER TABLE users DROP COLUMN failed_logins;
ALTER TABLE users DROP COLUMN active;
