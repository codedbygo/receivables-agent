# Spike: mcp-python-transports

Date: 2026-09-30   Timebox: 0.5 h, used 0.5 h (07:52 to 08:25 UTC, most of it a slow `uv pip install`)
Stopped because: answered
Location: `.scratch/spike-mcp/` (deleted)
Prior work: none

## Question

Can one Python MCP server object, from the current `mcp` SDK, serve the same tool over stdio and streamable HTTP, with schema validation rejecting bad input on both?

## Answered looks like

A client lists the tool and gets a correct result over each transport, and a call with a wrong argument type returns an error result on each.

## Operative inputs

- Python 3.12.3 (this machine), `mcp` 2.2.0 (latest on PyPI on 2026-09-30, installed by `uv pip install mcp`).
- Brief: stdio for Claude Code, streamable HTTP for the app (Phase 3).

## Answer

yes: `MCPServer` with one `@tool()` function served both transports via `run(transport="stdio")` and `run(transport="streamable-http")` (default `127.0.0.1:8000/mcp`); a string for an `int` argument returned `is_error=True` on both.

## Findings

| Time (UTC) | Finding | Evidence |
| --- | --- | --- |
| 08:10 | Latest SDK is 2.x; `mcp.server.fastmcp` raises on import in 2.x | `ModuleNotFoundError: ... FastMCP was renamed to MCPServer (from mcp.server.mcpserver import MCPServer)` |
| 08:12 | Client helper renamed and yields two streams, not three | `streamable_http_client(url, *, http_client=None, terminate_on_close=True)`; `ValueError: not enough values to unpack (expected 3, got 2)` |
| 08:15 | Result and tool models use snake_case fields | `'Tool' object has no attribute 'inputSchema'. Did you mean: 'input_schema'?`; same for `is_error` |
| 08:20 | Both transports: valid call succeeds, bad type rejected | `bad is_error True Error executing tool add: 1 validation error for addArguments` (stdio and http) |
| 08:20 | A tool returning a bare `dict` has `structured_content=None`; typed structured output needs a declared return model | `ok None` |
| 08:20 | SDK validation errors are free text, not typed codes | same output line |

Measured on: laptop.

## Not run or not measured

- Mounting `MCPServer.streamable_http_app()` inside FastAPI (the method exists; not exercised).
- Claude Code registration against the stdio server (`claude mcp add`); not run from inside this session.
- Auth on the HTTP transport.

## Tried and discarded

- v1-style code (`FastMCP`, `streamablehttp_client`, camelCase fields): does not run on 2.x.

## Recommendation

adopt `mcp>=2.2,<3` with `MCPServer`, pinned in the lockfile, and return Pydantic models from every tool.

Reasoning: both transports work from one server object, so the app and Claude Code share one tool registry. Because the SDK's own validation errors are free text, each tool validates with its own Pydantic model and returns a typed `{ok: false, error: {code, message}}` result so the brief's typed error codes hold on both transports.

## Follow-up

- Task: "Tool registry: Pydantic in/out models, typed error envelope, served by MCPServer over stdio and HTTP" (tracker: none)
- ADR needed: yes (MCP SDK and transport, Phase 3)

## Throwaway

`.scratch/spike-mcp/` deleted after this document was written.
