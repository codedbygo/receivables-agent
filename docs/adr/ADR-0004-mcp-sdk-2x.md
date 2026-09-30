# ADR-0004: Use the MCP Python SDK 2.x with stdio and streamable HTTP

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: mcp
- Reversibility: cheap: tools are plain functions behind a registry

## Context

The brief requires an MCP server with stdio for Claude Code and streamable HTTP for the app. The spike showed mcp 2.2.0 (`MCPServer`) serves one tool over both transports and rejects bad input on both; v1 names (`FastMCP`, `streamablehttp_client`) fail on 2.x.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| mcp>=2.2,<3 with MCPServer (chosen) | newer API; fewer examples online | n/a |
| mcp<2 (v1 API) | pins to an older line; would need a migration later | code copied from v1 examples |

## Decision

We will pin mcp>=2.2,<3 and serve one tool registry with MCPServer over stdio and streamable HTTP (bearer MCP_TOKEN on HTTP), because the spike proved it here.

## Consequences

Each tool returns a Pydantic model and a typed error envelope, since SDK validation errors are free text.

## Commits us to

mcp 2.x
