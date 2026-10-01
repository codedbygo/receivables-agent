"""REQ-048 to REQ-053, REQ-103: every red-team draft is rejected with its code; every golden draft passes.
Vectors are evals/redteam.yaml and evals/golden.yaml; ledger facts from evals/fixture_invoices.json."""

import json
from datetime import date

import pytest
import yaml

from app.core.paths import find_up
from app.guardrails.verify import InvoiceFact, VerifyContext, verify

EVALS = find_up("evals")
FIX = json.loads((EVALS / "fixture_invoices.json").read_text(encoding="utf-8"))["invoices"]
FACTS = {
    number: InvoiceFact(
        number=number, customer=cust, amount_paise=amt, remaining_paise=amt, due=date.fromisoformat(due)
    )
    for cust, rows in FIX.items()
    for number, amt, _issued, due in rows
}
NAMES = tuple(FIX)
RED = yaml.safe_load((EVALS / "redteam.yaml").read_text(encoding="utf-8"))["cases"]
GOLD = yaml.safe_load((EVALS / "golden.yaml").read_text(encoding="utf-8"))["cases"]


def ctx(case: dict[str, object]) -> VerifyContext:
    return VerifyContext(
        customer=str(case["customer"]),
        cited=tuple(case["invoices"]),  # type: ignore[arg-type]
        invoices=FACTS,
        customer_names=NAMES,
        today=date(2026, 9, 30),
        kind=str(case.get("kind", "reminder")),
    )

    # US-00-006, US-00-007 (seven TONE_UNSAFE cases), US-01-012


@pytest.mark.parametrize("case", RED, ids=[c["id"] for c in RED])
# TC-0182 (AC-US-00-006-2), TC-0183 (AC-US-00-006-3), TC-0184 (AC-US-00-006-4), TC-0185 (AC-US-00-006-5), TC-0187 (AC-US-00-007-1)
def test_red_team_draft_is_rejected_with_its_code(case: dict[str, object]) -> None:
    report = verify(str(case["text"]), ctx(case))

    assert not report.ok
    assert case["expect_code"] in report.codes, (case["why"], report.codes)


@pytest.mark.parametrize("case", GOLD, ids=[c["id"] for c in GOLD])
# TC-0259 (AC-US-01-012-2)
def test_golden_draft_passes(case: dict[str, object]) -> None:
    report = verify(str(case["text"]), ctx(case))

    assert report.ok, [c for c in report.checks if not c.ok]


# TC-0195 (AC-US-00-009-5)
def test_report_lists_every_token_checked() -> None:
    report = verify(str(GOLD[0]["text"]), ctx(GOLD[0]))

    tokens = {(c.check, c.token) for c in report.checks}
    assert {
        ("invoice", "INV-1021"),
        ("amount", "₹4,00,000"),
        ("total", "₹7,50,000"),
        ("date", "11 Sep 2026"),
        ("customer", "ABC Distributors"),
    } <= tokens
    assert all(c.ok for c in report.checks)


# TC-0188 (AC-US-00-007-2)
def test_legal_phrase_on_the_allow_list_passes() -> None:
    text = str(GOLD[0]["text"]).replace("Could you", "Otherwise we will initiate legal action. Could you")

    assert "TONE_UNSAFE" in verify(text, ctx(GOLD[0])).codes
    assert verify(text, ctx(GOLD[0]), legal_allow=("we will initiate legal action",)).ok
