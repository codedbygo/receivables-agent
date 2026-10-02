"""REQ-120: .env.example documents every variable the code reads, and holds no secret value."""

import re

from app.core.config import Settings
from app.core.paths import find_up

SECRETS = (
    "OPENROUTER_API_KEY",
    "ADMIN_TOKEN",
    "COLLECTOR_TOKEN",
    "VIEWER_TOKEN",
    "BANK_WEBHOOK_SECRET",
    "MCP_TOKEN",
    "SESSION_SECRET",
)


# TC-0263 (AC-US-01-013-4): every setting is listed; secret values are empty placeholders.
def test_env_example_lists_every_setting_and_no_secret_value() -> None:
    lines = (find_up("evals").parent / ".env.example").read_text(encoding="utf-8").splitlines()
    entries = dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))
    settings = {name.upper() for name in Settings.model_fields}
    assert settings <= set(entries), settings - set(entries)
    assert all(entries[name] == "" for name in SECRETS)
    assert not any(re.search(r"sk-or-[A-Za-z0-9-]{20,}", line) for line in lines)
