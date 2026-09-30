@AGENTS.md

# CLAUDE.md

Claude Code specifics for this repository; the standard is AGENTS.md above.
Loaded into every session: keep this file under 40 lines.

```
Repository:   receivables-agent (CollectionsAgentPlatform; Server/API + web)
Stack:        Python 3.12, FastAPI, SQLAlchemy 2, Alembic, mcp 2.x (backend/);
              React 19 + Vite (web/, P0 step 13)
Databases:    PostgreSQL 17 (compose service postgres)
Entrypoint:   backend/app/api/main.py (create_app); mcp and worker to come
Run, test:    make up, make test; gate: make check
Git host:     github (codedbygo/receivables-agent)
Tracker:      none (BEARING_TRACKER; none is valid)
Trunk:        develop, then main; the engineer pushes both directly
```

The Bearing plugin's hooks format and lint each edited file (`make
check-file` when the Makefile has it), add the task id from the branch,
refuse push, amend, rebase, merge, release and deploy commands, send you
back once when files you changed have not passed `make check`, and restore
the branch state and the user's last requests after compaction.
Permissions are in `.claude/settings.json`; `.claude/settings.local.json` may
add to them but must not loosen the deny list.

Plan mode for anything over three files or touching a schema, contract or
auth. On a third failed approach, stop and say so. Bound shell output with
`| tail -40`.

## Things the agent gets wrong in this repository

Add a line each time a mistake repeats; delete lines that stop applying.

- The ledger computes every number; the model never writes an amount, total or date (tenets, docs/architecture/tenets.md).
- `uv` here is a snap and does not start inside the Claude Code sandbox; run make with `UV=<pip-installed uv>` in the sandbox.
- Anything matching `.env` in a command is blocked by the secret guard; write `.env.example` with the editor.
