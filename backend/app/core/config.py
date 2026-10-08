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
    # HACK-003: "ollama" runs a free, open-source model on this machine (no key, no cost); "openrouter" is hosted.
    llm_provider: Literal["openrouter", "ollama"] = "openrouter"
    ollama_base_url: str = "http://localhost:11434"
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
    # Optional (ADR-0017): when set, every message goes to this inbox instead of the customer, except the allow-list.
    email_redirect_to: str = ""
    # HACK-007: comma-separated addresses that may receive real mail despite the redirect (your own test inboxes).
    email_allow_real: str = ""
    # HACK-009 (ADR-0018): "gmail" sends through the connected company Google account instead of SMTP.
    email_provider: Literal["smtp", "gmail"] = "smtp"
    # The Google Cloud OAuth client and the key that encrypts the stored refresh token (Fernet, base64).
    google_client_id: str = ""
    google_client_secret: str = ""
    google_token_key: str = ""
    # Exactly the redirect URI registered on the OAuth client, e.g. https://<host>/api/v1/google/callback.
    google_redirect_uri: str = ""
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
    # Scripts (smoke run) sign in as an admin with "Authorization: Bearer <ADMIN_TOKEN>"; empty disables it.
    # People sign in with a password or Google (ADR-0019).
    admin_token: str = ""
    # The first admin of a hosted deployment: created when this email first signs in with Google, or with
    # BOOTSTRAP_ADMIN_PASSWORD. Clear both once real admins exist.
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    # The X-Demo-Role header signs anyone in as that role: for a laptop only (refused on a public host).
    demo_open_roles: bool = False
    feature_whatsapp: bool = False
    feature_voice: bool = False
    feature_payment_link: bool = False
    feature_trusted_mode: bool = False
    feature_sms: bool = False
    # HACK-003 F1/F2: Twilio for SMS, WhatsApp and voice. Unset means the SIMULATED provider is used, and labelled.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_whatsapp_from: str = ""
    # Free SMS (HACK-003): the open-source Android SMS Gateway app on a phone with a SIM, local server mode.
    # When set it is used for SMS before Twilio. Example: http://192.168.1.20:8080
    sms_gateway_url: str = ""
    sms_gateway_user: str = ""
    sms_gateway_password: str = ""
    # Public https base URL Twilio calls back for voice webhooks (e.g. https://demo.example.in). Voice is real only
    # with this and the Twilio credentials and number; the signature on every webhook is checked against it.
    voice_public_base_url: str = ""
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
