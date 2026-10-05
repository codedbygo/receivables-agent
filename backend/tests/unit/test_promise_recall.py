"""HACK-003 F3: the recall line a follow-up carries passes the verifier only with the promise row's own figures.
Memory gives context; it cannot change a number."""

from datetime import date

from app.guardrails.verify import VerifyContext, verify

LINE = "On 30 Sep 2026, you mentioned that ₹3,00,000 would be paid on 05 Oct 2026. We have not received the payment yet."


def ctx(amounts: tuple[int, ...], dates: tuple[date, ...]) -> VerifyContext:
    return VerifyContext(
        customer="ABC Distributors",
        cited=(),
        invoices={},
        customer_names=("ABC Distributors",),
        today=date(2026, 10, 6),
        kind="followup",
        promise_amounts=amounts,
        promise_dates=dates,
    )


def test_the_recall_line_passes_with_the_promise_rows_figures() -> None:
    # promise_dates holds the promised date and the day the promise was logged (drafting.customer_state)
    report = verify(LINE, ctx((30_000_000,), (date(2026, 10, 5), date(2026, 9, 30))))
    assert report.ok, [c for c in report.checks if not c.ok]


def test_a_remembered_amount_that_is_not_the_promise_is_refused() -> None:
    report = verify(
        LINE.replace("₹3,00,000", "₹1,00,000"), ctx((30_000_000,), (date(2026, 10, 5), date(2026, 9, 30)))
    )
    assert "INVENTED_AMOUNT" in report.codes


def test_a_made_on_date_that_no_promise_row_has_is_refused() -> None:
    report = verify(LINE, ctx((30_000_000,), (date(2026, 10, 5),)))
    assert "DATE_MISMATCH" in report.codes
