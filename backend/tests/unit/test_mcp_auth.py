"""The MCP HTTP transport's bearer check (threat model: MCP over HTTP). Fails closed: an unset token
refuses every request; only the exact token reaches the server."""

import asyncio

from starlette.types import Message, Receive, Scope, Send

from app.mcp.__main__ import BearerAuth


def call(token: str, header: str | None) -> tuple[int, bool]:
    reached: list[bool] = []

    async def inner(_scope: Scope, _receive: Receive, send: Send) -> None:
        reached.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    headers = [(b"authorization", header.encode())] if header is not None else []
    asyncio.run(BearerAuth(inner, token)({"type": "http", "headers": headers}, receive, send))
    return int(sent[0]["status"]), bool(reached)


def test_the_exact_token_reaches_the_server() -> None:
    assert call("s3cret", "Bearer s3cret") == (200, True)


def test_a_wrong_or_missing_token_is_refused() -> None:
    assert call("s3cret", "Bearer nope") == (401, False)
    assert call("s3cret", None) == (401, False)


def test_an_unset_token_refuses_everyone_even_an_empty_bearer() -> None:
    assert call("", "Bearer ") == (401, False)
    assert call("", None) == (401, False)
