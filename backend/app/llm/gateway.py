"""The only door to the model (ADR-0007, LLD 7.1): cap, retry, timeout, cost, budget, live/replay/record.

Budget is a reservation: under a Postgres advisory lock the gateway writes a call row priced at the
worst case (max_tokens out), commits, calls, then writes the actual cost. Concurrent runs and evals
therefore cannot overshoot the budget. Replay calls are logged at zero cost.
"""

import hashlib
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import Engine, text

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.paths import find_up

URL = "https://openrouter.ai/api/v1/chat/completions"
PRICING = {
    "anthropic/claude-haiku-4.5": (1, 5)
}  # micro-USD per input token, per output token (spike 2026-09-30)
RETRYABLE = {429, 500, 502, 503, 504}
BUDGET_LOCK = 4242


@dataclass(frozen=True)
class PromptRef:
    name: str
    version: int


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LlmResult:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micro_usd: int = 0
    replay_key: str = ""
    mode: str = "live"


def replay_key(
    prompt: PromptRef, model: str, messages: list[dict[str, Any]], tools: list[Any] | None, max_tokens: int
) -> str:
    canonical = json.dumps(
        {"model": model, "messages": messages, "tools": tools, "max_tokens": max_tokens},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"{prompt.name}@v{prompt.version}:{hashlib.sha256(canonical.encode()).hexdigest()[:24]}"


def cost(model: str, input_tokens: int, output_tokens: int) -> int:
    per_in, per_out = PRICING.get(model, (1, 5))
    return input_tokens * per_in + output_tokens * per_out


class Gateway:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], object] | None = None,
        fixtures_dir: Path | None = None,
    ) -> None:
        self.s = settings
        self.engine = engine
        self.http = httpx.Client(transport=transport, timeout=settings.llm_timeout_s)
        self.sleep = sleep or time.sleep
        self.fixtures = fixtures_dir or find_up("evals") / "fixtures"

    def complete(
        self,
        prompt: PromptRef,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
        max_tokens: int = 500,
        run_id: str | None = None,
    ) -> LlmResult:
        model = self.s.llm_model
        cap = min(max_tokens, self.s.max_tokens)  # REQ-094
        key = replay_key(prompt, model, messages, tools, cap)
        if self.s.llm_mode == "replay":
            result = self._replay(key)
            self._log(
                prompt, model, "replay", key, result.input_tokens, result.output_tokens, 0, run_id, None
            )
            return result
        estimate = len(json.dumps(messages, ensure_ascii=False)) // 3 + 1
        call_id = self._reserve(prompt, model, key, cost(model, estimate, cap), run_id)
        try:
            body = self._post(
                {
                    "model": model,
                    "messages": messages,
                    "max_tokens": cap,
                    **({"tools": tools} if tools else {}),
                }
            )
        except AppError as e:
            self._settle(call_id, 0, 0, 0, e.code)
            raise
        result = self._parse(body, key, model, self.s.llm_mode)
        self._settle(call_id, result.input_tokens, result.output_tokens, result.cost_micro_usd, None)
        if self.s.llm_mode == "record":
            self._write_fixture(key, body)
        return result

    def spent_micro_usd(self) -> int:
        with self.engine.connect() as c:
            return int(c.execute(text("SELECT COALESCE(SUM(cost_micro_usd), 0) FROM llm_calls")).scalar_one())

    # --- budget -------------------------------------------------------------------------------------
    def _reserve(self, prompt: PromptRef, model: str, key: str, worst: int, run_id: str | None) -> str:
        with self.engine.begin() as c:
            c.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": BUDGET_LOCK})
            spent = int(
                c.execute(text("SELECT COALESCE(SUM(cost_micro_usd), 0) FROM llm_calls")).scalar_one()
            )
            budget = c.execute(
                text("SELECT llm_budget_micro_usd FROM settings WHERE id = 1")
            ).scalar_one_or_none()
            if budget is None:
                budget = round(self.s.llm_budget_usd * 1_000_000)
            if spent + worst > budget:
                c.execute(
                    text("""INSERT INTO guardrail_events (check_name, code, agent_run_id, detail)
                    VALUES ('budget', 'BUDGET_EXHAUSTED', CAST(:r AS uuid), CAST(:d AS jsonb))"""),
                    {
                        "r": run_id,
                        "d": json.dumps({"spent": int(spent), "budget": int(budget), "worst": worst}),
                    },
                )
                call_id = None
            else:
                call_id = str(
                    c.execute(
                        text("""
                    INSERT INTO llm_calls (agent_run_id, prompt_name, prompt_version, model, mode, replay_key,
                                           cost_micro_usd)
                    VALUES (CAST(:r AS uuid), :n, :v, :m, :mode, :k, :c) RETURNING id"""),
                        {
                            "r": run_id,
                            "n": prompt.name,
                            "v": prompt.version,
                            "m": model,
                            "mode": self.s.llm_mode,
                            "k": key,
                            "c": worst,
                        },
                    ).scalar_one()
                )
        if call_id is None:  # raised after the block so the guardrail event commits
            raise AppError(
                ErrorCode.BUDGET_EXHAUSTED, "LLM budget spent. Raise it in Admin or switch to replay."
            )
        return call_id

    def _settle(self, call_id: str, tin: int, tout: int, actual: int, error: str | None) -> None:
        with self.engine.begin() as c:
            c.execute(
                text("""UPDATE llm_calls SET input_tokens = :i, output_tokens = :o, cost_micro_usd = :c,
                              error_code = :e WHERE id = CAST(:id AS uuid)"""),
                {"i": tin, "o": tout, "c": actual, "e": error, "id": call_id},
            )

    def _log(
        self,
        prompt: PromptRef,
        model: str,
        mode: str,
        key: str,
        tin: int,
        tout: int,
        c_: int,
        run_id: str | None,
        error: str | None,
    ) -> None:
        with self.engine.begin() as c:
            c.execute(
                text("""INSERT INTO llm_calls (agent_run_id, prompt_name, prompt_version, model, mode,
                              replay_key,
                              input_tokens, output_tokens, cost_micro_usd, error_code)
                              VALUES (CAST(:r AS uuid), :n, :v, :m, :mode, :k, :i, :o, :c, :e)"""),
                {
                    "r": run_id,
                    "n": prompt.name,
                    "v": prompt.version,
                    "m": model,
                    "mode": mode,
                    "k": key,
                    "i": tin,
                    "o": tout,
                    "c": c_,
                    "e": error,
                },
            )

    # --- transport ----------------------------------------------------------------------------------
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.s.openrouter_api_key}", "X-Title": "Collections Agent"}
        last = AppError(ErrorCode.LLM_UPSTREAM, "Cannot reach the model provider.")
        for attempt in range(3):
            if attempt:
                self.sleep(2 ** (attempt - 1) + random.random() * 0.25)  # noqa: S311  jitter, not security
            try:
                r = self.http.post(URL, json=payload, headers=headers)
            except httpx.TimeoutException as e:
                last = AppError(ErrorCode.LLM_TIMEOUT, "The model did not answer in time.")
                last.__cause__ = e
                continue
            except httpx.TransportError as e:
                last = AppError(ErrorCode.LLM_UPSTREAM, "Cannot reach the model provider.")
                last.__cause__ = e
                continue
            if r.status_code == 200:
                data: dict[str, Any] = r.json()
                return data
            last = AppError(ErrorCode.LLM_UPSTREAM, f"Model provider returned {r.status_code}.")
            if r.status_code not in RETRYABLE:
                raise last
        raise last

    @staticmethod
    def _parse(body: dict[str, Any], key: str, model: str, mode: str) -> LlmResult:
        try:
            msg = body["choices"][0]["message"]
            calls = [
                ToolCall(
                    c.get("id", ""),
                    c["function"]["name"],
                    json.loads(c["function"].get("arguments") or "{}"),
                )
                for c in msg.get("tool_calls") or []
            ]
        except (KeyError, IndexError, TypeError, ValueError) as e:  # truncated or malformed provider reply
            raise AppError(ErrorCode.LLM_UPSTREAM, "The model returned an unreadable response.") from e
        usage = body.get("usage") or {}
        tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        c_ = 0 if mode == "replay" else cost(model, tin, tout)
        return LlmResult(msg.get("content"), calls, tin, tout, c_, key, mode)

    # --- fixtures -----------------------------------------------------------------------------------
    def _fixture_path(self, key: str) -> Path:
        name, digest = key.split("@", 1)[0], key.split(":", 1)[1]
        return self.fixtures / name / f"{digest}.json"

    def _write_fixture(self, key: str, body: dict[str, Any]) -> None:
        p = self._fixture_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps({"replay_key": key, "response": body}, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def _replay(self, key: str) -> LlmResult:
        p = self._fixture_path(key)
        if not p.exists():
            raise AppError(
                ErrorCode.REPLAY_MISS, f"No replay fixture for {key}; record it with LLM_MODE=record."
            )
        body = json.loads(p.read_text(encoding="utf-8"))["response"]
        return self._parse(body, key, self.s.llm_model, "replay")
