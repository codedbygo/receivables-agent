"""Every state change writes a TimelineEvent in the same transaction (REQ-081, tenet 3)."""

from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import today

Actor = Literal["ai", "human", "system", "customer"]


def record(
    session: Session,
    customer_id: str,
    kind: str,
    actor: Actor,
    summary: str,
    *,
    amount_paise: int | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    actor_user_id: str | None = None,
) -> None:
    session.execute(
        text("""INSERT INTO timeline_events (customer_id, business_date, kind, actor, actor_user_id, amount_paise,
                                             ref_type, ref_id, summary)
                VALUES (CAST(:c AS uuid), :d, :k, :a, CAST(:u AS uuid), :amt, :rt, CAST(:rid AS uuid), :s)"""),
        {
            "c": customer_id,
            "d": today(session),
            "k": kind,
            "a": actor,
            "u": actor_user_id,
            "amt": amount_paise,
            "rt": ref_type,
            "rid": ref_id,
            "s": summary,
        },
    )
