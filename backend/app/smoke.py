"""Post-deploy smoke checks (brief 9.3 step 6): python -m app.smoke against a running stack.

Resets the demo data first and last, so the ABC story is ready afterwards. Every check prints one line;
the exit status is 0 only when all pass. Settings come from the environment:
SMOKE_BASE_URL (http://localhost:8080), ADMIN_TOKEN (else the laptop role header), MCP_URL
(http://127.0.0.1:8001/mcp) with MCP_TOKEN, MAILPIT_URL (http://localhost:8025) with MAILPIT_UI_AUTH.
"""

import asyncio
import os
import sys
import time
from collections.abc import Callable

import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.services.demo import uid

ABC = uid("customer", "ABC Distributors")
ABC_OUTSTANDING_PAISE = 75_000_000  # ₹7,50,000 at the start of the story (seed)
Check = Callable[[httpx.Client], str]


def headers() -> dict[str, str]:
    token = os.environ.get("ADMIN_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {"X-Demo-Role": "admin"}


def ok(r: httpx.Response, status: int = 200) -> dict[str, object]:
    if r.status_code != status:
        raise AssertionError(f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:200]}")
    body: dict[str, object] = r.json()
    return body


def health(c: httpx.Client) -> str:
    ok(c.get("/api/v1/healthz"))
    ok(c.get("/api/v1/readyz"))
    return "healthz and readyz answer 200"


def reset(c: httpx.Client) -> str:
    ok(c.post("/api/v1/admin/reset", headers=headers()))
    return "demo data at the start of the ABC story"


def dashboard(c: httpx.Client) -> str:
    d = ok(c.get("/api/v1/dashboard", headers=headers()))
    abc = ok(c.get(f"/api/v1/customers/{ABC}", headers=headers()))
    assert abc["outstanding_paise"] == ABC_OUTSTANDING_PAISE, abc["outstanding_paise"]
    assert (
        isinstance(d["total_outstanding_paise"], int) and d["total_outstanding_paise"] > ABC_OUTSTANDING_PAISE
    )
    return f"dashboard totals served; ABC outstanding {ABC_OUTSTANDING_PAISE} paise"


def mcp_list_overdue(_c: httpx.Client) -> str:
    url = os.environ.get("MCP_URL", "http://127.0.0.1:8001/mcp")
    auth = {"Authorization": f"Bearer {os.environ.get('MCP_TOKEN', '')}"}

    async def go() -> object:
        async with (
            httpx2.AsyncClient(headers=auth) as client,  # the MCP client library is built on httpx2
            streamable_http_client(url, http_client=client) as (r, w, *_),
            ClientSession(r, w) as s,
        ):
            await s.initialize()
            out = await s.call_tool("list_overdue", {"limit": 15})
            return out.structured_content

    out = asyncio.run(go())
    assert isinstance(out, dict) and out.get("ok"), out
    data = out["data"]
    rows = data.get("customers") if isinstance(data, dict) else data
    assert isinstance(rows, list) and len(rows) == 15, rows
    return "MCP list_overdue returns the top 15"


def _abc_draft(c: httpx.Client) -> dict[str, object]:
    ok(c.post("/api/v1/runs", json={"customer_ids": [ABC]}, headers=headers()), 202)
    page = ok(
        c.get(
            "/api/v1/messages",
            params={"filter[customer_id]": ABC, "filter[status]": "pending_approval"},
            headers=headers(),
        )
    )
    drafts = page["data"]
    assert isinstance(drafts, list) and drafts, "the run left no draft for ABC"
    draft: dict[str, object] = drafts[0]
    return draft


def kill_switch_and_mail(c: httpx.Client) -> str:
    """Kill switch on: an approved message cannot be sent. Off: the worker delivers it to the mail catcher."""
    ok(c.patch("/api/v1/admin/settings", json={"sending_enabled": False}, headers=headers()))
    try:
        m = _abc_draft(c)
        h = {**headers(), "If-Match": str(m["version"])}
        ok(c.post(f"/api/v1/messages/{m['id']}/approve", headers=h))
        for _ in range(5):  # the worker polls every 2 s; the message must stay unsent while sending is off
            status = ok(c.get(f"/api/v1/messages/{m['id']}", headers=headers()))["status"]
            assert status == "approved", f"sent while the kill switch was on: {status}"
            time.sleep(1)  # watching the worker, not a test delay
    finally:
        ok(c.patch("/api/v1/admin/settings", json={"sending_enabled": True}, headers=headers()))
    mail = os.environ.get("MAILPIT_URL", "http://localhost:8025")
    user, _, password = os.environ.get("MAILPIT_UI_AUTH", "").partition(":")
    auth = httpx.BasicAuth(user, password) if user else None
    for _ in range(30):  # the worker polls; give it up to 30 s
        msgs = httpx.get(f"{mail}/api/v1/messages", auth=auth, timeout=5).json().get("messages") or []
        if any("ABC" in str(x.get("To")) or "abc" in str(x.get("To")).lower() for x in msgs):
            return "kill switch blocked the send; with sending on the email reached the mail catcher"
        time.sleep(1)  # polling the worker, not a test delay
    raise AssertionError("no email to ABC Distributors in the mail catcher after 30 s")


# What a failing check raises: a failed assertion, an HTTP or socket error, a malformed body, an MCP task group.
SMOKE_FAILURES = (
    AssertionError,
    OSError,
    ValueError,
    KeyError,
    TypeError,
    httpx.HTTPError,
    httpx2.HTTPError,
    ExceptionGroup,
)
CHECKS: list[Check] = [health, reset, dashboard, mcp_list_overdue, kill_switch_and_mail, reset]


def run(client: httpx.Client, checks: list[Check] = CHECKS) -> bool:
    passed = True
    for check in checks:
        try:
            print(f"smoke: pass  {check.__name__}: {check(client)}")
        except SMOKE_FAILURES as e:  # every failure is reported, then the run fails
            passed = False
            print(f"smoke: FAIL  {check.__name__}: {e}")
    return passed


def main() -> None:
    base = os.environ.get("SMOKE_BASE_URL", "http://localhost:8080")
    with httpx.Client(base_url=base, timeout=90) as client:
        sys.exit(0 if run(client) else 1)


if __name__ == "__main__":
    main()
