# ADR-0005: Run the agent as plain orchestrator code over an in-process tool registry

- Status: Accepted
- Date: 2026-09-30
- Task: HACK-001
- Deciders: Savitha Sista (engineer; approved the Phase 3 recommendations by replying "continue")
- Area: agent orchestration
- Reversibility: cheap

## Context

The brief asks for plain orchestrator code with a 4-call bound, four logical roles and no heavy framework. The same tools must be served over MCP to external clients.

## What else was considered

| Option | Why not | Would suit |
| --- | --- | --- |
| Plain orchestrator calling the shared tool registry in-process (chosen) | must count calls in its own wrapper | n/a |
| Orchestrator as an MCP client over HTTP | extra hop and failure mode, slower tests | an agent running in another process or host |
| An agent framework | brief says no heavy framework | a larger multi-agent product |

## Decision

We will write the orchestrator as plain Python that calls the same registry MCPServer serves, with identical validation, because it removes a network hop and keeps tests fast (eng review A3).

## Consequences

Reply classification runs with no tools at all (eng review A10).

## Commits us to

none beyond ADR-0001 and ADR-0004
