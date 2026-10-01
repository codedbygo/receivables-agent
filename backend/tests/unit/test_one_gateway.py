"""AC-US-01-008-1: only the gateway talks to OpenRouter."""

from pathlib import Path

APP = Path(__file__).parents[2] / "app"


# TC-0237 (AC-US-01-008-1)
def test_only_the_gateway_mentions_openrouter() -> None:
    offenders = [
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if "openrouter.ai" in p.read_text(encoding="utf-8") and p != APP / "llm" / "gateway.py"
    ]
    assert offenders == []
