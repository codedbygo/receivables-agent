"""AC-US-03-002-1: the same tools, with the same schemas, over stdio and streamable HTTP."""

import asyncio
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from app.core.config import Settings
from app.services.demo import reset_demo, uid

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).parents[2]
TOKEN = "test-mcp-token"  # noqa: S105  test value


async def _use(session: ClientSession) -> tuple[dict[str, object], object]:
    await session.initialize()
    tools = await session.list_tools()
    schemas = {t.name: t.input_schema for t in tools.tools}
    r = await session.call_tool("get_customer", {"customer_id": uid("customer", "ABC Distributors")})
    return schemas, r.structured_content


def _stdio() -> tuple[dict[str, object], object]:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp", "--stdio"], cwd=str(BACKEND), env={**os.environ}
    )

    async def go() -> tuple[dict[str, object], object]:
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            return await _use(s)

    return asyncio.run(go())


@pytest.fixture(scope="module")
def http_url(engine) -> Iterator[str]:  # type: ignore[no-untyped-def]
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp", "--port", str(port)],
        cwd=BACKEND,  # noqa: S603
        env={**os.environ, "MCP_TOKEN": TOKEN},
    )
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(100):
        try:
            httpx.get(url, timeout=0.2)
            break
        except httpx.TransportError:
            time.sleep(0.1)  # waiting for a subprocess to bind, not a test assertion delay
    yield url
    proc.terminate()
    proc.wait(5)


def _http(url: str, token: str) -> tuple[dict[str, object], object]:
    async def go() -> tuple[dict[str, object], object]:
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as client:
            async with streamable_http_client(url, http_client=client) as (r, w), ClientSession(r, w) as s:  # type: ignore[arg-type]
                return await _use(s)

    return asyncio.run(go())


# TC-0246 (AC-US-03-002-1)
def test_both_transports_list_the_same_tools_and_answer(http_url: str) -> None:
    stdio_schemas, stdio_abc = _stdio()
    http_schemas, http_abc = _http(http_url, TOKEN)

    assert stdio_schemas == http_schemas
    assert {"list_overdue", "get_customer_history", "log_promise", "log_dispute", "escalate"} <= set(
        stdio_schemas
    )
    assert stdio_abc == http_abc
    assert stdio_abc["data"]["outstanding_paise"] == 75_000_000  # type: ignore[index]


def test_http_without_the_token_is_refused(http_url: str) -> None:
    r = httpx.post(
        http_url,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Accept": "application/json, text/event-stream"},
    )

    assert r.status_code == 401
