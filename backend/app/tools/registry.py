"""The tool registry (ADR-0005, LLD 3.5): one set of schema-checked tools, used in-process by the
orchestrator and served by MCP. Every call returns {ok: true, data} or {ok: false, error: {code, message}}."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.agent.classify import classify
from app.core.clock import today
from app.core.db import make_sessionmaker, transaction
from app.core.errors import AppError, ErrorCode
from app.llm.gateway import Gateway
from app.services import approval, collections, drafting, ledger, payments
from app.services.priority import Reason, top

FORBIDDEN_FIELDS = {"sql", "query", "raw"}  # REQ-042


@dataclass
class ToolContext:
    actor: Literal["ai", "human", "system"]
    source: Literal["agent", "mcp"]
    run_id: str | None = None
    allowed: frozenset[str] | None = None
    max_calls: int | None = None
    calls: int = 0


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input: type[In]
    output: type[BaseModel]
    fn: Callable[[Session, ToolContext, Any], BaseModel]


# --- inputs and outputs ------------------------------------------------------------------------------
class ListOverdueIn(In):
    limit: int = Field(15, ge=1, le=50)


class OverdueCustomer(BaseModel):
    customer_id: str
    name: str
    score: int
    band: str
    reasons: list[Reason]
    overdue_paise: int


class ListOverdueOut(BaseModel):
    customers: list[OverdueCustomer]


class CustomerIn(In):
    customer_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class LogPromiseIn(CustomerIn):
    amount_paise: int = Field(gt=0)
    promised_date: date
    invoice_numbers: list[str] | None = Field(None, max_length=20)
    reply_id: str | None = None


class LogDisputeIn(CustomerIn):
    invoice_number: str = Field(pattern=r"^INV-\d+$")
    reason: str = Field(min_length=1, max_length=200)
    reply_id: str | None = None


class EscalateIn(CustomerIn):
    kind: collections.EscalationKind
    reason: str = Field(min_length=1, max_length=300)
    dispute_id: str | None = None
    reply_id: str | None = None
    payment_id: str | None = None


class DraftMessageIn(CustomerIn):
    kind: drafting.Kind
    prose: str = Field(min_length=1, max_length=4000)
    tone: Literal["gentle", "firm", "final"]
    channel: Literal["email", "whatsapp", "voice"] = "email"
    invoice_numbers: list[str] | None = Field(None, max_length=20)


class SendMessageIn(In):
    message_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class SendMessageOut(BaseModel):
    message_id: str
    queued: bool


class InvoiceIn(In):
    invoice_number: str = Field(pattern=r"^INV-\d+$")


class InvoiceOut(ledger.Invoice):
    customer_id: str


class PromisesOut(BaseModel):
    promises: list[collections.PromiseOut]


class FollowupIn(CustomerIn):
    prose: str = Field(min_length=1, max_length=4000)


class RecordPaymentIn(CustomerIn):
    bank_event_id: str = Field(min_length=1, max_length=100)


class ClassifyIn(In):
    reply_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class ClassifyOut(BaseModel):
    classification: str
    amount_paise: int | None
    stated_date: date | None
    invoice_refs: list[str]
    confidence: float
    injection_suspected: bool
    source: str


# --- implementations --------------------------------------------------------------------------------
def _list_overdue(s: Session, _: ToolContext, i: ListOverdueIn) -> ListOverdueOut:
    ranked = top(s, today(s), i.limit)
    overdue = {c.id: c.overdue_paise for c in ledger.list_customers(s, today(s))}
    return ListOverdueOut(
        customers=[
            OverdueCustomer(
                customer_id=cid,
                name=name,
                score=p.score,
                band=p.band,
                reasons=p.reasons,
                overdue_paise=overdue.get(cid, 0),
            )
            for cid, name, p in ranked
        ]
    )


def _history(s: Session, _: ToolContext, i: CustomerIn) -> collections.History:
    return collections.history(s, i.customer_id)


def _customer(s: Session, _: ToolContext, i: CustomerIn) -> ledger.Customer:
    return ledger.get_customer(s, today(s), i.customer_id)


def _log_promise(s: Session, _: ToolContext, i: LogPromiseIn) -> collections.PromiseOut:
    return collections.log_promise(
        s, i.customer_id, i.amount_paise, i.promised_date, i.invoice_numbers, i.reply_id
    )


def _log_dispute(s: Session, _: ToolContext, i: LogDisputeIn) -> collections.DisputeOut:
    return collections.log_dispute(s, i.customer_id, i.invoice_number, i.reason, i.reply_id)


def _escalate(s: Session, _: ToolContext, i: EscalateIn) -> collections.EscalationOut:
    return collections.escalate(s, i.customer_id, i.kind, i.reason, i.dispute_id, i.reply_id, i.payment_id)


def _draft(s: Session, ctx: ToolContext, i: DraftMessageIn) -> drafting.DraftOut:
    out = drafting.draft_message(
        s, i.customer_id, i.kind, i.prose, i.tone, i.channel, i.invoice_numbers, ctx.run_id
    )
    if out.status == "pending_approval" and approval.trusted_approve(s, out.message_id):
        out.status = "approved"
    return out


def _send(s: Session, _: ToolContext, i: SendMessageIn) -> SendMessageOut:
    return SendMessageOut(message_id=i.message_id, queued=approval.request_send(s, i.message_id) is not None)


def _get_invoice(s: Session, _: ToolContext, i: InvoiceIn) -> InvoiceOut:
    cid = s.execute(
        text("SELECT customer_id::text FROM invoices WHERE number = :n"), {"n": i.invoice_number}
    ).scalar()
    if cid is None:
        raise AppError(ErrorCode.INVOICE_NOT_FOUND, f"{i.invoice_number} does not exist.")
    inv = next(x for x in ledger.customer_invoices(s, today(s), cid) if x.number == i.invoice_number)
    return InvoiceOut(**inv.model_dump(), customer_id=cid)


def _promise_status(s: Session, _: ToolContext, i: CustomerIn) -> PromisesOut:
    payments.evaluate_promises(s, i.customer_id)
    return PromisesOut(promises=collections.history(s, i.customer_id).promises)


def _followup(s: Session, ctx: ToolContext, i: FollowupIn) -> drafting.DraftOut:
    return drafting.draft_message(s, i.customer_id, "followup", i.prose, "gentle", "email", None, ctx.run_id)


def _record_payment(s: Session, _: ToolContext, i: RecordPaymentIn) -> payments.Payment:
    pid = s.execute(
        text("SELECT id::text FROM payments WHERE bank_event_id = :e"), {"e": i.bank_event_id}
    ).scalar()
    if pid is None:  # a claim is not evidence (REQ-078)
        raise AppError(ErrorCode.NO_LEDGER_EVIDENCE, "No bank credit with that id is in the ledger.")
    p = payments.get_payment(s, pid)
    if p.customer_id not in (None, i.customer_id):
        raise AppError(ErrorCode.NO_LEDGER_EVIDENCE, "That credit belongs to another customer.")
    return payments.match_payment(s, pid, i.customer_id) if p.customer_id is None else p


TOOLS = [
    Tool(
        "list_overdue",
        "Customers to chase today, highest priority first, with the reasons.",
        ListOverdueIn,
        ListOverdueOut,
        _list_overdue,
    ),
    Tool(
        "get_customer_history",
        "Invoices, promises, disputes and recent message and reply summaries.",
        CustomerIn,
        collections.History,
        _history,
    ),
    Tool(
        "get_customer",
        "One customer with outstanding and overdue amounts.",
        CustomerIn,
        ledger.Customer,
        _customer,
    ),
    Tool(
        "log_promise",
        "Record a promise to pay an amount by a date.",
        LogPromiseIn,
        collections.PromiseOut,
        _log_promise,
    ),
    Tool(
        "log_dispute",
        "Record a dispute on one invoice; the invoice stops being chased.",
        LogDisputeIn,
        collections.DisputeOut,
        _log_dispute,
    ),
    Tool(
        "draft_message",
        "Save a draft: write prose with {{invoice_table}} and {{total}}; the system fills the "
        "figures from the ledger and verifies the text. Never type amounts, totals or due dates.",
        DraftMessageIn,
        drafting.DraftOut,
        _draft,
    ),
    Tool(
        "send_message",
        "Send an approved message. Refused unless a human approved it and sending is on.",
        SendMessageIn,
        SendMessageOut,
        _send,
    ),
    Tool("get_invoice", "One invoice with its balance.", InvoiceIn, InvoiceOut, _get_invoice),
    Tool(
        "check_promise_status",
        "Settle and list a customer's promises against the ledger.",
        CustomerIn,
        PromisesOut,
        _promise_status,
    ),
    Tool(
        "create_followup",
        "Draft a follow-up with {{invoice_table}} and {{total}}.",
        FollowupIn,
        drafting.DraftOut,
        _followup,
    ),
    Tool(
        "record_payment",
        "Attach a bank credit already in the ledger to a customer; never creates a payment.",
        RecordPaymentIn,
        payments.Payment,
        _record_payment,
    ),
    Tool("escalate", "Hand a case to a human collector.", EscalateIn, collections.EscalationOut, _escalate),
]


class Registry:
    def __init__(self, engine: Engine, tools: list[Tool], gateway: Gateway | None = None) -> None:
        self.engine = engine
        self.gateway = gateway
        self.sessions = make_sessionmaker(engine)
        self.tools = {t.name: t for t in tools}

    def invoke(self, name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        if ctx.max_calls is not None and ctx.calls >= ctx.max_calls:
            return self._guard(ctx, ErrorCode.TOOL_LIMIT, f"tool-call limit {ctx.max_calls} reached", name)
        ctx.calls += 1
        tool = self.tools.get(name)
        if tool is None or (ctx.allowed is not None and name not in ctx.allowed):
            return self._guard(ctx, ErrorCode.TOOL_NOT_ALLOWED, f"{name} is not available here", name)
        bad = FORBIDDEN_FIELDS & set(args)
        if bad:
            self._guard(ctx, ErrorCode.DIRECT_DB_ATTEMPT, f"field {sorted(bad)[0]} refused", name)
            return _err(ErrorCode.VALIDATION_ERROR, f"unknown field {sorted(bad)[0]}")
        try:
            parsed = tool.input.model_validate(args)
        except ValidationError as e:
            return _err(
                ErrorCode.VALIDATION_ERROR,
                "invalid input",
                [{"field": ".".join(map(str, x["loc"])), "reason": x["msg"]} for x in e.errors()],
            )
        try:
            with transaction(self.sessions) as s:
                out = tool.fn(s, ctx, parsed)
        except AppError as e:
            return _err(e.code, e.message, e.details)
        return {"ok": True, "data": tool.output.model_validate(out.model_dump()).model_dump(mode="json")}

    def _guard(self, ctx: ToolContext, code: ErrorCode, message: str, tool: str) -> dict[str, Any]:
        with self.engine.begin() as c:
            c.execute(
                text("""INSERT INTO guardrail_events (check_name, code, agent_run_id, detail)
                              VALUES ('tools', :code, CAST(:r AS uuid), CAST(:d AS jsonb))"""),
                {"code": code, "r": ctx.run_id, "d": json.dumps({"tool": tool, "source": ctx.source})},
            )
        return _err(code, message)


def _err(code: ErrorCode, message: str, details: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code.value, "message": message, **({"details": details} if details else {})},
    }


def build_registry(engine: Engine, gateway: Gateway | None = None) -> Registry:
    """classify_reply needs the gateway; without one it uses the rules classifier."""
    reg = Registry(engine, TOOLS, gateway)

    def _classify(s: Session, _: ToolContext, i: ClassifyIn) -> ClassifyOut:
        body = s.execute(
            text("SELECT body FROM replies WHERE id = CAST(:r AS uuid)"), {"r": i.reply_id}
        ).scalar()
        if body is None:
            raise AppError(ErrorCode.NOT_FOUND, "Reply not found.")
        c = classify(body, today(s), [], reg.gateway)
        return ClassifyOut(
            classification=c.klass,
            amount_paise=c.amount_paise,
            stated_date=c.stated_date,
            invoice_refs=list(c.invoice_refs),
            confidence=c.confidence,
            injection_suspected=c.injection_suspected,
            source=c.source,
        )

    reg.tools["classify_reply"] = Tool(
        "classify_reply", "Classify a stored reply without acting on it.", ClassifyIn, ClassifyOut, _classify
    )
    return reg
