"""Prompt registry (LLD 3.1b rule): only declared variables are filled; drafting placeholders pass through."""

import pytest

from app.llm.prompts import load_prompt


def test_draft_prompt_fills_declared_variables_and_keeps_placeholders() -> None:
    p = load_prompt("draft_reminder", 1)

    out = p.render(
        customer_json='{"name": "ABC Distributors"}', tone="firm", kind="reminder", today="30 Sep 2026"
    )

    assert p.ref.name == "draft_reminder" and p.ref.version == 1 and p.max_tokens == 500
    assert '{"name": "ABC Distributors"}' in out and "Tone: firm" in out
    assert "{{invoice_table}}" in out and "{{total}}" in out
    assert "{{tone}}" not in out and "---" not in out.splitlines()[0]


def test_missing_required_variable_is_refused() -> None:
    with pytest.raises(ValueError, match="today"):
        load_prompt("classify_reply", 1).render(reply_text="hi", open_invoices="none")


def test_over_long_variable_is_refused() -> None:
    with pytest.raises(ValueError, match="reply_text"):
        load_prompt("classify_reply", 1).render(
            reply_text="x" * 5001, today="30 Sep 2026", open_invoices="none"
        )


def test_enum_variable_is_checked() -> None:
    with pytest.raises(ValueError, match="tone"):
        load_prompt("draft_reminder", 1).render(customer_json="{}", tone="angry", kind="reminder", today="x")
