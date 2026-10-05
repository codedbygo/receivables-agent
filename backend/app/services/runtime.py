"""The settings row the admin console reads and changes: kill switch, autonomy, budget, flags (US-01-008, US-01-009).
Changes are logged with the admin's user id; they belong to no customer, so they have no timeline event."""

import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode

log = logging.getLogger("settings")


class RuntimeSettings(BaseModel):
    demo_today: date
    sending_enabled: bool
    autonomy_mode: Literal["manual", "assisted", "trusted"]
    llm_budget_micro_usd: int
    llm_spent_micro_usd: int
    llm_mode: str
    feature_whatsapp: bool
    feature_voice: bool
    feature_payment_link: bool
    feature_trusted_mode: bool
    feature_sms: bool


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sending_enabled: bool | None = None
    autonomy_mode: Literal["manual", "assisted", "trusted"] | None = None
    llm_budget_micro_usd: int | None = None
    feature_whatsapp: bool | None = None
    feature_voice: bool | None = None
    feature_payment_link: bool | None = None
    feature_trusted_mode: bool | None = None
    feature_sms: bool | None = None


def read(session: Session, llm_mode: str) -> RuntimeSettings:
    r = (
        session.execute(
            text("""SELECT demo_today, sending_enabled, autonomy_mode, llm_budget_micro_usd,
        (SELECT COALESCE(SUM(cost_micro_usd), 0) FROM llm_calls) AS llm_spent_micro_usd, feature_whatsapp,
        feature_voice, feature_payment_link, feature_trusted_mode, feature_sms FROM settings WHERE id = 1""")
        )
        .mappings()
        .one()
    )
    return RuntimeSettings(**r, llm_mode=llm_mode)


def update(session: Session, patch: SettingsPatch, llm_mode: str, user_id: str) -> RuntimeSettings:
    changes = patch.model_dump(exclude_none=True)
    current = read(session, llm_mode)
    trusted_on = changes.get("feature_trusted_mode", current.feature_trusted_mode)
    if changes.get("autonomy_mode") == "trusted" and not trusted_on:
        raise AppError(ErrorCode.FEATURE_DISABLED, "Turn on the Trusted-mode flag first.")
    if not trusted_on and current.autonomy_mode == "trusted":
        changes["autonomy_mode"] = "manual"  # switching the flag off leaves no path to auto-send
    if changes:
        # Column names come from the model's fields, never from the request keys.
        sets = ", ".join(f"{k} = :{k}" for k in changes)
        session.execute(text(f"UPDATE settings SET {sets}, updated_at = now() WHERE id = 1"), changes)  # noqa: S608
        log.info("settings changed by user %s: %s", user_id, sorted(changes))
    return read(session, llm_mode)


def autonomy_mode(session: Session) -> str:
    return str(session.execute(text("SELECT autonomy_mode FROM settings WHERE id = 1")).scalar_one())
