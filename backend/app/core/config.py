"""Settings from the environment (LLD section 7). Runtime switches (kill switch,
autonomy, budget, feature flags, demo date) are seed values; the settings row
in Postgres is what processes read at runtime."""

from functools import lru_cache
from typing import Literal

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
    mailhog_ui_url: str = "http://localhost:8025"
    demo_today: str = "2026-09-30"
    tz: str = "Asia/Kolkata"
    sending_enabled: bool = True
    autonomy_mode: Literal["manual", "assisted", "trusted"] = "manual"
    # Host headers the API answers to; anything else (DNS rebinding) gets 400. "testserver" is the test client.
    allowed_hosts: str = "localhost,127.0.0.1,api,testserver"
    admin_token: str = ""
    feature_whatsapp: bool = False
    feature_voice: bool = False
    feature_payment_link: bool = False
    feature_trusted_mode: bool = False
    bank_webhook_secret: str = ""
    mcp_token: str = ""
    session_secret: str = ""
    classify_min_confidence: float = 0.75
    log_level: str = "INFO"

    @property
    def max_tokens(self) -> int:
        return min(self.llm_max_tokens, 500)  # REQ-094: never above 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
