"""Settings from the environment (LLD section 7). Runtime switches (kill switch,
autonomy, budget, feature flags, demo date) are seed values; the settings row
in Postgres is what processes read at runtime."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+psycopg://collections:collections@localhost:5432/collections"
    openrouter_api_key: str = ""
    llm_model: str = "anthropic/claude-haiku-4.5"
    llm_mode: Literal["live", "replay", "record"] = "replay"
    llm_budget_usd: float = 2.00
    llm_max_tokens: int = 500
    llm_timeout_s: float = 20.0
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    # Authenticated SMTP for the hosted demo (ADR-0016); empty user means the local Mailpit, no login.
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    smtp_from: str = ""
    # With real SMTP every message goes to this inbox, never to the seeded customers (startup refuses without).
    email_redirect_to: str = ""
    # Serverless (ADR-0015): send right after approval instead of waiting for a worker; a cron tick runs jobs.
    send_inline: bool = False
    cron_secret: str = ""
    mailhog_ui_url: str = "http://localhost:8025"
    demo_today: str = "2026-09-30"
    tz: str = "Asia/Kolkata"
    sending_enabled: bool = True
    autonomy_mode: Literal["manual", "assisted", "trusted"] = "manual"
    # Host headers the API answers to; anything else (DNS rebinding) gets 400. "testserver" is the test client.
    allowed_hosts: str = "localhost,127.0.0.1,api,testserver"
    # Access codes, one per role, sent as "Authorization: Bearer <code>". An empty code disables that role.
    admin_token: str = ""
    collector_token: str = ""
    viewer_token: str = ""
    # The X-Demo-Role header signs anyone in as that role: for a laptop only (refused on a public host).
    demo_open_roles: bool = False
    feature_whatsapp: bool = False
    feature_voice: bool = False
    feature_payment_link: bool = False
    feature_trusted_mode: bool = False
    bank_webhook_secret: str = ""
    mcp_token: str = ""
    session_secret: str = ""
    classify_min_confidence: float = 0.75
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, url: str) -> str:
        """Neon and Vercel give postgres:// or postgresql://; the app always uses the psycopg 3 driver."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @property
    def max_tokens(self) -> int:
        return min(self.llm_max_tokens, 500)  # REQ-094: never above 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
