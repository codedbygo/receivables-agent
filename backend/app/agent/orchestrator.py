"""The bounded agent (REQ-029 to REQ-035, LLD 4). One orchestrator, four roles, at most 4 tool calls per
customer per run, every step logged. Tone and channel are decided in code before the model is asked.

    start run -> tone, channel (code) -> loop: model turn -> one tool call via the registry (counted)
              -> ... -> final answer or limit -> outcome from what the run left behind

When the model is unavailable (no replay fixture, provider down, budget spent) the Collections role
falls back to a template draft through the same tools, and the run's reason says so.
"""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.core.clock import today
from app.core.db import make_sessionmaker, transaction
from app.core.errors import AppError
from app.llm.gateway import Gateway
from app.llm.prompts import load_prompt
from app.services.tone import select_tone
from app.tools.registry import Registry, ToolContext

Role = Literal["collections", "reply_understanding", "payment_verification", "escalation"]
Outcome = Literal["WAIT_FOR_APPROVAL", "ESCALATED", "STOPPED_LIMIT", "NO_ACTION", "FAILED"]
MAX_CALLS = 4
COLLECTIONS_TOOLS = frozenset(
    {
        "list_overdue",
        "get_customer_history",
        "get_invoice",
        "check_promise_status",
        "draft_message",
        "escalate",
    }  # no log_promise: promise amounts come only from parsed reply text (tenet 1)
)
TEMPLATES = {
    "gentle": "Dear {name},\n\nA gentle reminder that these invoices are now past due:\n\n{{{{invoice_table}}}}\n\n"
    "Total outstanding: {{{{total}}}}\n\nPlease let us know when we can expect payment.\n\nRegards,\nAccounts team",
    "firm": "Dear {name},\n\nOur records show these invoices past their due date:\n\n{{{{invoice_table}}}}\n\n"
    "Total outstanding: {{{{total}}}}\n\nCould you confirm a date for payment this week? If any invoice needs "
    "a correction, reply and we will look at it straight away.\n\nRegards,\nAccounts team",
    "final": "Dear {name},\n\nYour account needs to be settled. These invoices are well past due:\n\n"
    "{{{{invoice_table}}}}\n\nTotal outstanding: {{{{total}}}}\n\nPlease call us this week so we can agree a "
    "plan.\n\nRegards,\nAccounts team",
}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")


@dataclass
class RunResult:
    id: str
    outcome: Outcome
    tool_call_count: int
    tone: str
    channel: str
    reason: str | None


def redact(value: Any) -> Any:
    """PII out of logged arguments (REQ-036): emails, phones and free text over 200 characters."""
    if isinstance(value, dict):
        return {
            k: ("[redacted:text]" if k in ("body", "reply_text") else redact(v)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        v = EMAIL.sub("[redacted:email]", value)
        v = PHONE.sub("[redacted:phone]", v)
        return v if len(v) <= 200 else v[:200] + "…"
    return value


class Orchestrator:
    def __init__(self, engine: Engine, gateway: Gateway, registry: Registry) -> None:
        self.engine, self.gateway, self.registry = engine, gateway, registry
        self.sessions = make_sessionmaker(engine)

    # --- run bookkeeping -----------------------------------------------------------------------------
    def _start(self, customer_id: str, trigger: str) -> tuple[str, Any] | None:
        try:
            with transaction(self.sessions) as s:
                d = today(s)
                run_id: str = s.execute(
                    text("""INSERT INTO agent_runs (customer_id, run_date, trigger)
                    VALUES (CAST(:c AS uuid), :d, :t) RETURNING id::text"""),
                    {"c": customer_id, "d": d, "t": trigger},
                ).scalar_one()
                return str(run_id), d
        except IntegrityError:
            return None  # a run is already active, or today's scheduled run exists (AC-US-01-001-5, -7)

    def _step(
        self, run_id: str, seq: int, role: Role, tool: str, args: dict[str, Any], out: dict[str, Any]
    ) -> None:
        summary = "ok" if out.get("ok") else f"{out['error']['code']}: {out['error']['message']}"
        if out.get("ok"):
            data = out["data"]
            summary = (
                json.dumps(
                    {k: data[k] for k in list(data)[:3] if not isinstance(data[k], (list, dict))}, default=str
                )[:200]
                or "ok"
            )
        with self.engine.begin() as c:
            c.execute(
                text("""INSERT INTO agent_steps (agent_run_id, seq, role, tool_name, arguments_redacted,
                              result_summary, error_code) VALUES (CAST(:r AS uuid), :s, :role, :t, CAST(:a AS jsonb),
                              :sum, :e)"""),
                {
                    "r": run_id,
                    "s": seq,
                    "role": role,
                    "t": tool,
                    "a": json.dumps(redact(args), default=str),
                    "sum": summary,
                    "e": None if out.get("ok") else out["error"]["code"],
                },
            )

    @contextmanager
    def failing(self, run_id: str) -> Iterator[None]:
        """Any error between _start and _finish ends the run as FAILED, so the customer is not blocked forever."""
        try:
            yield
        except BaseException as e:
            self._finish(run_id, "FAILED", 0, None, None, None, f"internal error ({type(e).__name__})")
            raise

    def _finish(
        self,
        run_id: str,
        outcome: Outcome,
        calls: int,
        tone: str | None,
        channel: str | None,
        action: str | None,
        reason: str | None,
    ) -> None:
        with self.engine.begin() as c:
            c.execute(
                text("""UPDATE agent_runs SET status = 'finished', outcome = :o, tool_call_count = :n,
                tone = :tone, channel = :ch, action = :a, reason = :r, finished_at = now() WHERE id = CAST(:id AS uuid)"""),
                {
                    "o": outcome,
                    "n": calls,
                    "tone": tone,
                    "ch": channel,
                    "a": action,
                    "r": reason,
                    "id": run_id,
                },
            )

    def _outcome(self, run_id: str) -> Outcome:
        with self.engine.connect() as c:
            # A human must act on an escalation even when an acknowledgement draft also waits (HLD Flow B).
            if c.execute(
                text("""SELECT 1 FROM agent_steps WHERE agent_run_id = CAST(:r AS uuid) AND tool_name = 'escalate'
                                 AND error_code IS NULL"""),
                {"r": run_id},
            ).scalar():
                return "ESCALATED"
            if c.execute(
                text(
                    "SELECT 1 FROM messages WHERE agent_run_id = CAST(:r AS uuid) AND status = 'pending_approval'"
                ),
                {"r": run_id},
            ).scalar():
                return "WAIT_FOR_APPROVAL"
        return "NO_ACTION"

    def invoke(
        self, run_id: str, ctx: ToolContext, role: Role, tool: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """One counted tool call, logged as a step. Returns the registry envelope."""
        before = ctx.calls
        out = self.registry.invoke(tool, args, ctx)
        if ctx.calls > before:
            self._step(run_id, ctx.calls, role, tool, args, out)
        return out

    # --- the Collections role -------------------------------------------------------------------------
    def _tone(self, customer_id: str) -> tuple[str, str]:
        with self.sessions() as s:
            d = today(s)
            r = s.execute(
                text("""SELECT
                COALESCE(MAX(CAST(:d AS date) - i.due_date) FILTER (WHERE i.due_date < :d AND b.remaining_paise > 0
                         AND i.status <> 'disputed'), 0) AS oldest,
                (SELECT count(*) FROM promises p WHERE p.customer_id = c.id AND p.status = 'missed') AS missed,
                (SELECT count(*) FROM messages m WHERE m.customer_id = c.id AND m.status = 'sent'
                         AND m.sent_at >= CAST(:since AS date)) AS recent
                FROM customers c LEFT JOIN invoices i ON i.customer_id = c.id
                LEFT JOIN invoice_balances b ON b.invoice_id = i.id WHERE c.id = CAST(:c AS uuid) GROUP BY c.id"""),
                {"d": d, "since": d - timedelta(days=14), "c": customer_id},
            ).one()
        return select_tone(r.oldest, r.missed, r.recent > 0), "email"  # WhatsApp choice lands with US-00-024

    def run_collections(self, customer_id: str, trigger: str) -> RunResult | None:
        started = self._start(customer_id, trigger)
        if started is None:
            return None
        run_id, d = started
        with self.failing(run_id):
            tone, channel = self._tone(customer_id)
            ctx = ToolContext(
                actor="ai", source="agent", run_id=run_id, allowed=COLLECTIONS_TOOLS, max_calls=MAX_CALLS
            )
            reason: str | None = None
            try:
                reason = self._model_loop(run_id, ctx, customer_id, tone, channel, d)
            except AppError as e:
                reason = f"model unavailable ({e.code}); template used"
                self._template(run_id, ctx, customer_id, tone, channel)
            outcome: Outcome = (
                "STOPPED_LIMIT" if reason and reason.startswith("tool-call limit") else self._outcome(run_id)
            )
            self._finish(
                run_id,
                outcome,
                ctx.calls,
                tone,
                channel,
                "send_reminder" if outcome == "WAIT_FOR_APPROVAL" else None,
                reason or f"{tone} {channel} reminder",
            )
        return RunResult(run_id, outcome, ctx.calls, tone, channel, reason or f"{tone} {channel} reminder")

    def _model_loop(
        self, run_id: str, ctx: ToolContext, customer_id: str, tone: str, channel: str, d: Any
    ) -> str | None:
        prompt = load_prompt("draft_reminder", 1)
        with self.sessions() as s:
            name = s.execute(
                text("SELECT name FROM customers WHERE id = CAST(:c AS uuid)"), {"c": customer_id}
            ).scalar()
        system = prompt.render(
            customer_json=json.dumps({"customer_id": customer_id, "name": name}),
            tone=tone,
            kind="reminder",
            today=f"{d:%d %b %Y}",
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Prepare the reminder."},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input.model_json_schema(),
                },
            }
            for t in self.registry.tools.values()
            if t.name in COLLECTIONS_TOOLS
        ]
        for _ in range(MAX_CALLS + 1):
            result = self.gateway.complete(prompt.ref, messages, tools=tools, run_id=run_id)
            if not result.tool_calls:
                return None
            call = result.tool_calls[0]
            args = dict(call.arguments)
            if "customer_id" in args:  # the run's customer, never one the model names
                args["customer_id"] = customer_id
            if call.name == "draft_message":  # tone and channel are the business's, not the model's
                args.update({"tone": tone, "channel": channel})
                if (
                    args.get("kind") == "dispute_ack"
                ):  # that kind skips the disputed-invoice rule: code's, not the model's
                    args["kind"] = "reminder"
            out = self.invoke(run_id, ctx, "collections", call.name, args)
            if not out["ok"] and out["error"]["code"] == "TOOL_LIMIT":
                return f"tool-call limit {MAX_CALLS} reached"
            messages += [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(out, default=str)[:4000]},
            ]
        return f"tool-call limit {MAX_CALLS} reached"

    def _template(self, run_id: str, ctx: ToolContext, customer_id: str, tone: str, channel: str) -> None:
        hist = self.invoke(run_id, ctx, "collections", "get_customer_history", {"customer_id": customer_id})
        if not hist["ok"]:
            return
        name = hist["data"]["customer"]["name"]
        open_ = [i for i in hist["data"]["invoices"] if i["remaining_paise"] > 0]
        if open_ and all(i["status"] == "disputed" for i in open_):
            reason = "Every open invoice is disputed; reminders are paused until a collector resolves it"
            self.invoke(
                run_id,
                ctx,
                "escalation",
                "escalate",
                {"customer_id": customer_id, "kind": "dispute", "reason": reason},
            )
            return
        self.invoke(
            run_id,
            ctx,
            "collections",
            "draft_message",
            {
                "customer_id": customer_id,
                "kind": "reminder",
                "prose": TEMPLATES[tone].format(name=name),
                "tone": tone,
                "channel": channel,
            },
        )
