"""Dispute lifecycle and routing (HACK-003 F7): OPEN -> ASSIGNED -> INVESTIGATING -> RESOLVED.

The category comes from rules over the customer's words, the team from the fixed table in policy dispute_routing.
Only a signed-in person resolves a dispute: no tool and no AI actor can call transition() with 'resolved'."""

from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.guardrails.verify import policy
from app.services.timeline import record

Status = Literal["open", "assigned", "investigating", "resolved"]
CATEGORIES = (
    "invoice_error",
    "wrong_quantity",
    "wrong_price",
    "duplicate_invoice",
    "missing_delivery",
    "service_issue",
    "contract_issue",
    "other",
)
TEAMS = ("billing", "operations", "sales", "legal_contracts", "collections")
TEAM_LABEL = {
    "billing": "Billing",
    "operations": "Operations",
    "sales": "Sales",
    "legal_contracts": "Legal and contracts",
    "collections": "Collections",
}
MOVES: dict[str, frozenset[str]] = {
    "open": frozenset({"assigned", "resolved"}),
    "assigned": frozenset({"assigned", "investigating", "resolved"}),
    "investigating": frozenset({"resolved"}),
    "resolved": frozenset(),
}
ACTIVE = "status <> 'resolved'"  # every query that means "dispute still blocks collection" uses this


def can_move(current: str, to: str) -> bool:
    return to in MOVES.get(current, frozenset())


def team_for(category: str) -> str:
    return policy().dispute_routing.get(category, "collections")


class Routing(BaseModel):
    category: str
    team: str
    rule: str


def route(category: str) -> Routing:
    """The deterministic routing decision and the rule behind it, for the timeline and the Why? panel."""
    cat = category if category in CATEGORIES else "other"
    team = team_for(cat)
    return Routing(category=cat, team=team, rule=f"policy dispute_routing: {cat} -> {team}")


def transition(
    session: Session,
    dispute_id: str,
    to: Literal["assigned", "investigating"],
    user_id: str,
    note: str | None = None,
    team: str | None = None,
) -> str:
    """A collector assigns or starts investigating a dispute. Returns the customer id. Resolving has one path,
    collections.resolve_dispute, which needs a note and restores the invoice status from its balance."""
    row = session.execute(
        text("""SELECT customer_id::text, status, assigned_team, (SELECT number FROM invoices i
        WHERE i.id = d.invoice_id) AS number FROM disputes d WHERE id = CAST(:d AS uuid) FOR UPDATE"""),
        {"d": dispute_id},
    ).first()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Dispute not found.")
    if not can_move(row.status, to):
        raise AppError(ErrorCode.VALIDATION_ERROR, f"A {row.status} dispute cannot move to {to}.")
    if team is not None and team not in TEAMS:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Unknown team {team}.")
    new_team = team or row.assigned_team or "collections"
    session.execute(
        text("""UPDATE disputes SET status = :s, assigned_team = :t, assigned_to = CASE WHEN :s = 'investigating'
        THEN CAST(:u AS uuid) ELSE assigned_to END, updated_at = now() WHERE id = CAST(:d AS uuid)"""),
        {"s": to, "t": new_team, "u": user_id, "d": dispute_id},
    )
    summary = (
        f"Dispute on {row.number} assigned to {TEAM_LABEL[new_team]}"
        if to == "assigned"
        else f"Dispute on {row.number} under investigation ({TEAM_LABEL[new_team]})"
    )
    if note and note.strip():
        summary += f": {note.strip()[:80]}"
    record(
        session,
        row.customer_id,
        "dispute_assigned" if to == "assigned" else "dispute_investigating",
        "human",
        summary,
        ref_type="dispute",
        ref_id=dispute_id,
        actor_user_id=user_id,
    )
    return str(row.customer_id)
