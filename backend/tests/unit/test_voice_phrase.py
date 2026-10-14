"""Web calls: the model phrases an agent line but never writes a figure. Figures are masked as [[n]] and put back
by code; any reply that drops, repeats or invents a figure falls back to the code-written line."""

from typing import Any

from app.core.errors import AppError, ErrorCode
from app.llm.gateway import LlmResult
from app.services.voice import phrase

LINE = "Thank you. I have noted ₹2,00,000 by 17 Oct 2026 against INV-3002. Shall I send the details?"


class Fake:
    def __init__(self, reply: str | None = None, fail: bool = False) -> None:
        self.reply, self.fail, self.seen = reply, fail, ""

    def complete(self, prompt: Any, messages: list[dict[str, Any]], **_: Any) -> LlmResult:
        self.seen = messages[0]["content"]
        if self.fail:
            raise AppError(ErrorCode.REPLAY_MISS, "no fixture")
        return LlmResult(text=self.reply)


def run(reply: str | None = None, fail: bool = False) -> tuple[str, str]:
    g = Fake(reply, fail)
    return phrase(LINE, "Customer: we can pay two lakh by Friday", g), g.seen  # type: ignore[arg-type]  # duck-typed gateway


def test_the_model_sees_tokens_only_and_code_puts_the_figures_back() -> None:
    out, seen = run("Great, so that's [[1]] by [[2]] for [[3]]. Would you like the details sent over?")
    assert "₹" not in seen.split("<next_line>")[1] and "[[1]]" in seen
    assert (
        out == "Great, so that's ₹2,00,000 by 17 Oct 2026 for INV-3002. Would you like the details sent over?"
    )


def test_a_reply_that_drops_repeats_or_invents_a_figure_falls_back() -> None:
    for bad in (
        "Great, [[1]] by [[2]].",  # drops INV
        "[[1]] [[1]] by [[2]] for [[3]].",  # repeats
        "[[1]] by [[2]] for [[3]], or 50,000 now?",  # its own digits
        "₹5 off: [[1]] by [[2]] for [[3]].",  # its own currency
        "",
    ):
        assert run(bad)[0] == LINE, bad


def test_any_model_failure_returns_the_code_line() -> None:
    assert run(fail=True)[0] == LINE
