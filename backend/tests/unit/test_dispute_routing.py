"""HACK-003 F7: dispute categories are rules over the customer's words, routing is a fixed policy table, and the
lifecycle only moves forward through the allowed steps."""

import pytest

from app.agent.classify import dispute_category
from app.guardrails.verify import policy
from app.services.disputes import CATEGORIES, can_move, team_for


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Invoice says 50 units but we received 40.", "wrong_quantity"),
        ("You billed at Rs 450 but the agreed rate is 400", "wrong_price"),
        ("INV-1021 and INV-1034 are the same order, charged twice", "duplicate_invoice"),
        ("We never received the consignment", "missing_delivery"),
        ("The installation service was poor and the technician never came back", "service_issue"),
        ("This is not as per our contract terms", "contract_issue"),
        ("The GST number on the invoice is wrong", "invoice_error"),
        ("Please call me", "other"),
    ],
)
def test_each_category_has_a_rule(text: str, category: str) -> None:
    assert dispute_category(text) == category


def test_every_category_routes_to_a_team() -> None:
    routing = policy().dispute_routing
    assert set(routing) == set(CATEGORIES)
    assert team_for("wrong_quantity") == "operations"
    assert team_for("missing_delivery") == "operations"
    assert team_for("wrong_price") == "billing"
    assert team_for("invoice_error") == "billing"
    assert team_for("contract_issue") == "legal_contracts"


@pytest.mark.parametrize(
    ("a", "b", "ok"),
    [
        ("open", "assigned", True),
        ("assigned", "investigating", True),
        ("investigating", "resolved", True),
        ("assigned", "assigned", True),  # reassign to another team
        ("open", "resolved", True),
        ("resolved", "open", False),
        ("resolved", "investigating", False),
        ("investigating", "open", False),
        ("investigating", "assigned", False),
    ],
)
def test_allowed_moves(a: str, b: str, ok: bool) -> None:
    assert can_move(a, b) is ok


def test_no_automatic_resolution_is_configured() -> None:
    assert policy().dispute_auto_resolve == ()
