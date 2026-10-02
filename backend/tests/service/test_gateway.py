"""US-01-008, US-01-009: one gateway, capped, retried, replayable, budgeted. No network: httpx MockTransport."""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.llm.gateway import Gateway, PromptRef, replay_key

pytestmark = pytest.mark.integration
PROMPT = PromptRef(name="classify_reply", version=1)
MSGS = [{"role": "user", "content": "We can pay ₹3 lakh on October 5."}]


def ok_body(
    content: str = '{"class":"PROMISE"}', prompt: int = 2000, completion: int = 500
) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }


class Stub:
    """Scripted OpenRouter: a list of (status, body) returned in order; records requests."""

    def __init__(self, *responses: tuple[int, dict[str, object]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        status, body = self.responses.pop(0)
        return httpx.Response(status, json=body)


@pytest.fixture
def clean(engine: Engine) -> Engine:
    with engine.begin() as c:
        c.execute(text("DELETE FROM guardrail_events; DELETE FROM llm_calls"))
        c.execute(
            text("""INSERT INTO settings (id, demo_today, llm_budget_micro_usd) VALUES (1, DATE '2026-09-30', 2000000)
                          ON CONFLICT (id) DO UPDATE SET llm_budget_micro_usd = 2000000""")
        )
    return engine


def gateway(
    engine: Engine, stub: Stub, tmp_path: Path, mode: str = "live", **kw: object
) -> tuple[Gateway, list[float]]:
    slept: list[float] = []
    settings = Settings(llm_mode=mode, openrouter_api_key="test-key", **kw)  # type: ignore[arg-type]
    gw = Gateway(
        settings, engine, transport=httpx.MockTransport(stub), sleep=slept.append, fixtures_dir=tmp_path
    )
    return gw, slept


# TC-0237 (AC-US-01-008-1), TC-0238 (AC-US-01-008-2)
def test_max_tokens_is_capped_at_500(clean: Engine, tmp_path: Path) -> None:
    stub = Stub((200, ok_body()))
    gw, _ = gateway(clean, stub, tmp_path, llm_max_tokens=900)

    gw.complete(PROMPT, MSGS, max_tokens=2000)

    assert stub.requests[0]["max_tokens"] == 500
    assert stub.requests[0]["model"] == "anthropic/claude-haiku-4.5"


# TC-0239 (AC-US-01-008-3)
def test_retries_429_then_succeeds_with_growing_delays(clean: Engine, tmp_path: Path) -> None:
    stub = Stub((429, {}), (429, {}), (200, ok_body()))
    gw, slept = gateway(clean, stub, tmp_path)

    result = gw.complete(PROMPT, MSGS)

    assert result.text == '{"class":"PROMISE"}'
    assert len(slept) == 2 and slept[0] < slept[1]


def test_gives_up_after_three_tries_with_llm_upstream(clean: Engine, tmp_path: Path) -> None:
    gw, _ = gateway(clean, Stub((503, {}), (503, {}), (503, {})), tmp_path)

    with pytest.raises(AppError) as e:
        gw.complete(PROMPT, MSGS)

    assert e.value.code == ErrorCode.LLM_UPSTREAM


# TC-0242 (AC-US-01-009-1), TC-0243 (AC-US-01-009-2)
def test_cost_and_tokens_are_logged_and_totalled(clean: Engine, tmp_path: Path) -> None:
    gw, _ = gateway(clean, Stub((200, ok_body()), (200, ok_body(prompt=100, completion=10))), tmp_path)

    first = gw.complete(PROMPT, MSGS)
    gw.complete(PROMPT, MSGS)

    assert first.cost_micro_usd == 4_500  # 2,000 in x $1/MTok + 500 out x $5/MTok = $0.0045
    with clean.connect() as c:
        rows = c.execute(
            text("SELECT input_tokens, output_tokens, cost_micro_usd FROM llm_calls ORDER BY created_at")
        ).all()
    assert [tuple(r) for r in rows] == [(2000, 500, 4500), (100, 10, 150)]
    assert gw.spent_micro_usd() == 4_650


# TC-0244 (AC-US-01-009-3)
def test_budget_exhausted_refuses_without_calling_out(clean: Engine, tmp_path: Path) -> None:
    with clean.begin() as c:
        c.execute(text("UPDATE settings SET llm_budget_micro_usd = 10000"))
        c.execute(
            text("""INSERT INTO llm_calls (prompt_name, prompt_version, model, mode, replay_key, cost_micro_usd)
                          VALUES ('x', 1, 'm', 'live', 'k', 10000)""")
        )
    stub = Stub()
    gw, _ = gateway(clean, stub, tmp_path)

    with pytest.raises(AppError) as e:
        gw.complete(PROMPT, MSGS)

    assert e.value.code == ErrorCode.BUDGET_EXHAUSTED
    assert stub.requests == []
    with clean.connect() as c:
        assert c.execute(text("SELECT code FROM guardrail_events")).scalar_one() == "BUDGET_EXHAUSTED"


# TC-0240 (AC-US-01-008-4), TC-0245 (AC-US-01-009-4)
def test_record_then_replay_without_network(clean: Engine, tmp_path: Path) -> None:
    rec, _ = gateway(clean, Stub((200, ok_body())), tmp_path, mode="record")
    recorded = rec.complete(PROMPT, MSGS)
    replay, _ = gateway(clean, Stub(), tmp_path, mode="replay")

    again = replay.complete(PROMPT, MSGS)

    assert again.text == recorded.text
    assert again.cost_micro_usd == 0 and again.mode == "replay"
    assert (tmp_path / "classify_reply" / f"{recorded.replay_key.split(':')[1]}.json").exists()


# TC-0241 (AC-US-01-008-5)
def test_replay_miss_names_the_key_and_never_calls_out(clean: Engine, tmp_path: Path) -> None:
    stub = Stub()
    gw, _ = gateway(clean, stub, tmp_path, mode="replay")

    with pytest.raises(AppError) as e:
        gw.complete(PROMPT, MSGS)

    assert e.value.code == ErrorCode.REPLAY_MISS
    assert replay_key(PROMPT, "anthropic/claude-haiku-4.5", MSGS, None, 500) in e.value.message
    assert stub.requests == []


def test_tool_calls_are_returned_parsed(clean: Engine, tmp_path: Path) -> None:
    body = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "get_customer_history",
                                "arguments": '{"customer_id": "abc"}',
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    gw, _ = gateway(clean, Stub((200, body)), tmp_path)

    result = gw.complete(
        PROMPT, MSGS, tools=[{"type": "function", "function": {"name": "get_customer_history"}}]
    )

    assert [(t.name, t.arguments) for t in result.tool_calls] == [
        ("get_customer_history", {"customer_id": "abc"})
    ]


def raising(error: Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (httpx.ReadTimeout("slow"), ErrorCode.LLM_TIMEOUT),
        (httpx.ConnectError("refused"), ErrorCode.LLM_UPSTREAM),
    ],
)
def test_a_model_that_never_answers_is_tried_three_times_then_named(
    clean: Engine, tmp_path: Path, error: Exception, code: ErrorCode
) -> None:
    slept: list[float] = []
    settings = Settings(llm_mode="live", openrouter_api_key="test-key")
    gw = Gateway(settings, clean, transport=raising(error), sleep=slept.append, fixtures_dir=tmp_path)

    with pytest.raises(AppError) as e:
        gw.complete(PROMPT, MSGS)

    assert e.value.code == code
    assert len(slept) == 2 and slept[0] < slept[1]


def test_without_a_settings_row_the_configured_budget_applies(clean: Engine, tmp_path: Path) -> None:
    with clean.begin() as c:
        c.execute(text("DELETE FROM settings"))
    gw, _ = gateway(clean, Stub((200, ok_body())), tmp_path, llm_budget_usd=0.0)

    with pytest.raises(AppError) as e:
        gw.complete(PROMPT, MSGS)

    assert e.value.code == ErrorCode.BUDGET_EXHAUSTED


def test_a_request_the_provider_refuses_is_not_retried(clean: Engine, tmp_path: Path) -> None:
    gw, slept = gateway(clean, Stub((400, {})), tmp_path)

    with pytest.raises(AppError) as e:
        gw.complete(PROMPT, MSGS)

    assert e.value.code == ErrorCode.LLM_UPSTREAM and slept == []
