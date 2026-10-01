"""MCP server over the tool registry (ADR-0004). python -m app.mcp --stdio (Claude Code) or
python -m app.mcp [--port 8001] (streamable HTTP, bearer MCP_TOKEN required; empty token refuses all)."""

import argparse
import asyncio
import hmac
import json
import sys
from typing import Any

import anyio
import mcp.types as t
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.db import make_engine
from app.core.logging import configure
from app.tools.registry import Registry, ToolContext, build_registry


def make_server(registry: Registry) -> Server[Any]:
    async def list_tools(_ctx: Any, _params: Any) -> t.ListToolsResult:
        return t.ListToolsResult(
            tools=[
                t.Tool(
                    name=tool.name, description=tool.description, input_schema=tool.input.model_json_schema()
                )
                for tool in registry.tools.values()
            ]
        )

    async def call_tool(_ctx: Any, params: t.CallToolRequestParams) -> t.CallToolResult:
        # MCP clients act as the collector role with the timeline actor "ai" (HLD section 9)
        ctx = ToolContext(actor="ai", source="mcp")
        out = await anyio.to_thread.run_sync(registry.invoke, params.name, dict(params.arguments or {}), ctx)
        return t.CallToolResult(
            content=[t.TextContent(type="text", text=json.dumps(out, ensure_ascii=False))],
            structured_content=out,
            is_error=not out["ok"],
        )

    return Server("collections-agent", version="1.0.0", on_list_tools=list_tools, on_call_tool=call_tool)


class BearerAuth:
    """Refuses every HTTP request without the exact bearer token; an unset token refuses all (fail closed)."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app, self.token = app, token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            given = headers.get(b"authorization", b"").decode()
            if not self.token or not hmac.compare_digest(given, f"Bearer {self.token}"):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": b'{"error":{"code":"UNAUTHORIZED"}}'})
                return
        await self.app(scope, receive, send)


def main() -> None:
    configure(get_settings().log_level, sys.stderr)
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    settings = get_settings()
    server = make_server(build_registry(make_engine(settings.database_url)))
    if args.stdio:

        async def run() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        asyncio.run(run())
    else:
        app = BearerAuth(server.streamable_http_app(host=args.host), settings.mcp_token)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
