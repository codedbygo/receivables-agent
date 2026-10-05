"""US-00-009 to US-00-011, US-01-002: approve, edit, reject, send once, kill switch, crash safety."""

import os
import socketserver
import threading
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.channels.email import ChannelError, EmailChannel, Outbound
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services import approval
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry
from app.worker.jobs import reap, run_once

pytestmark = pytest.mark.integration
ABC = uid("customer", "ABC Distributors")
PROSE = (
    "Dear ABC Distributors,\n\nThese invoices are past due:\n\n{{invoice_table}}\n\nTotal outstanding: {{total}}"
    "\n\nCould you confirm a payment date this week?\n\nRegards,\nAccounts team"
)


class FakeChannel:
    name = "email"
    simulated = False  # stands in for the real SMTP channel

    def __init__(self, fail: int = 0) -> None:
        self.sent: list[Outbound] = []
        self.fail = fail

    def send(self, message: Outbound) -> str:
        if self.fail:
            self.fail -= 1
            raise ChannelError("SMTP_UNAVAILABLE", retryable=True)
        self.sent.append(message)
        return "ok"


@pytest.fixture
def draft_id(engine: Engine) -> str:
    reset_demo(engine, Settings(database_url=os.environ["DATABASE_URL"]))
    out = build_registry(engine).invoke(
        "draft_message",
        {"customer_id": ABC, "kind": "reminder", "prose": PROSE, "tone": "firm"},
        ToolContext(actor="ai", source="agent"),
    )
    return str(out["data"]["message_id"])


def tx(engine: Engine) -> Session:
    return Session(bind=engine)


def worker(engine: Engine, channel: FakeChannel) -> str | None:
    return run_once(
        engine, {"send_message": lambda e, p: approval.deliver(e, p["message_id"], {"email": channel})}
    )


def one(engine: Engine, sql: str) -> object:
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


def approve(engine: Engine, mid: str, version: int | None = 1) -> approval.Message:
    with tx(engine) as s, s.begin():
        return approval.approve(s, mid, version, None)


# TC-0198 (AC-US-00-011-1), TC-0199 (AC-US-00-011-2)
def test_approve_then_worker_sends_exactly_once(engine: Engine, draft_id: str) -> None:
    ch = FakeChannel()
    approve(engine, draft_id)
    approve(engine, draft_id)  # double click

    worker(engine, ch)
    worker(engine, ch)

    assert len(ch.sent) == 1 and ch.sent[0].to == "accounts@abc-distributors.example.in"
    assert "₹7,50,000" in ch.sent[0].body
    assert one(engine, f"SELECT status FROM messages WHERE id = '{draft_id}'") == "sent"
    assert one(engine, f"SELECT count(*) FROM jobs WHERE dedupe_key = '{draft_id}'") == 1


def test_stale_version_is_refused(engine: Engine, draft_id: str) -> None:
    with pytest.raises(AppError) as e:
        approve(engine, draft_id, version=7)

    assert e.value.code == ErrorCode.STALE_DRAFT


# TC-0196 (AC-US-00-010-1)
def test_edit_with_a_wrong_amount_is_refused_and_text_kept(engine: Engine, draft_id: str) -> None:
    with tx(engine) as s:
        body = approval.get_message(s, draft_id).body
    with pytest.raises(AppError) as e, tx(engine) as s, s.begin():
        approval.edit(s, draft_id, "Overdue invoices", body.replace("₹4,00,000", "₹4,50,000"), 1, None)

    assert e.value.code == ErrorCode.AMOUNT_MISMATCH
    assert "₹4,00,000" in e.value.message
    assert one(engine, f"SELECT version FROM messages WHERE id = '{draft_id}'") == 1


# TC-0197 (AC-US-00-010-2)
def test_valid_edit_is_reverified_and_can_be_approved(engine: Engine, draft_id: str) -> None:
    with tx(engine) as s:
        body = approval.get_message(s, draft_id).body
    with tx(engine) as s, s.begin():
        m = approval.edit(s, draft_id, "Overdue invoices", body.replace("this week", "by Friday"), 1, None)

    assert (m.version, m.verified) == (2, True)
    assert approve(engine, draft_id, 2).status == "approved"


# TC-0194 (AC-US-00-009-3)
def test_reject_needs_a_reason(engine: Engine, draft_id: str) -> None:
    with pytest.raises(AppError) as e, tx(engine) as s, s.begin():
        approval.reject(s, draft_id, "  ", None)

    assert e.value.code == ErrorCode.REASON_REQUIRED


# TC-0201 (AC-US-01-002-3)
def test_kill_switch_holds_the_send_until_turned_off(engine: Engine, draft_id: str) -> None:
    ch = FakeChannel()
    approve(engine, draft_id)
    with engine.begin() as c:
        c.execute(text("UPDATE settings SET sending_enabled = false"))

    worker(engine, ch)

    assert ch.sent == []
    assert one(engine, "SELECT count(*) FROM guardrail_events WHERE code = 'SENDING_DISABLED'") == 1
    with engine.begin() as c:
        c.execute(text("UPDATE settings SET sending_enabled = true"))
        c.execute(text("UPDATE jobs SET run_at = now()"))
    worker(engine, ch)
    assert len(ch.sent) == 1


def test_send_path_refuses_an_unapproved_message(engine: Engine, draft_id: str) -> None:
    out = build_registry(engine).invoke(
        "send_message", {"message_id": draft_id}, ToolContext(actor="ai", source="mcp")
    )

    assert out["error"]["code"] == "NOT_APPROVED"
    assert one(engine, "SELECT count(*) FROM guardrail_events WHERE code = 'NOT_APPROVED'") == 1


# TC-0200 (AC-US-00-011-3)
def test_smtp_down_retries_then_sends(engine: Engine, draft_id: str) -> None:
    ch = FakeChannel(fail=1)
    approve(engine, draft_id)

    worker(engine, ch)
    assert one(engine, f"SELECT last_error FROM messages WHERE id = '{draft_id}'") == "SMTP_UNAVAILABLE"
    with engine.begin() as c:
        c.execute(text("UPDATE jobs SET run_at = now()"))
    worker(engine, ch)

    assert len(ch.sent) == 1


def test_crash_mid_send_is_unconfirmed_never_resent(engine: Engine, draft_id: str) -> None:
    approve(engine, draft_id)
    with engine.begin() as c:  # the worker claimed and died before marking sent
        c.execute(
            text(f"UPDATE messages SET last_error = 'IN_FLIGHT', send_attempts = 1 WHERE id = '{draft_id}'")
        )
        c.execute(text("UPDATE jobs SET status = 'running', locked_at = now() - interval '10 minutes'"))

    reap(engine)
    worker(engine, FakeChannel())

    assert (
        one(engine, f"SELECT status || '/' || last_error FROM messages WHERE id = '{draft_id}'")
        == "failed/UNCONFIRMED"
    )


class _SMTP(socketserver.StreamRequestHandler):
    received: list[bytes] = []

    def handle(self) -> None:
        self.wfile.write(b"220 fake\r\n")
        data = False
        while line := self.rfile.readline():
            if data:
                if line == b".\r\n":
                    data = False
                    self.wfile.write(b"250 queued\r\n")
                else:
                    _SMTP.received.append(line)
                continue
            cmd = line[:4].upper()
            if cmd == b"DATA":
                data = True
                self.wfile.write(b"354 go\r\n")
            elif cmd == b"QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"250 ok\r\n")


@pytest.fixture
def smtp() -> Iterator[int]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SMTP)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


def test_email_channel_speaks_smtp(smtp: int) -> None:
    EmailChannel("127.0.0.1", smtp).send(
        Outbound("m1", "a@x.example.in", "Overdue invoices", "₹7,50,000 due")
    )

    raw = b"".join(_SMTP.received).decode()
    assert "Subject: Overdue invoices" in raw and "Message-ID: <m1@collections.local>" in raw


def test_email_channel_down_is_retryable() -> None:
    with pytest.raises(ChannelError) as e:
        EmailChannel("127.0.0.1", 1).send(Outbound("m1", "a@x", "s", "b"))

    assert e.value.retryable and e.value.code == "SMTP_UNAVAILABLE"


def test_edited_subject_is_verified_too(engine: Engine, draft_id: str) -> None:
    # Review 2026-10-01: only the body was re-verified, so an invented amount in the subject went out.
    with tx(engine) as s:
        body = approval.get_message(s, draft_id).body
    with pytest.raises(AppError) as e, tx(engine) as s, s.begin():
        approval.edit(s, draft_id, "Pay ₹9,99,999 today", body, 1, None)

    assert e.value.code == ErrorCode.INVENTED_AMOUNT


def test_edit_citing_a_now_disputed_invoice_is_refused(engine: Engine, draft_id: str) -> None:
    # Review 2026-10-01: the edit context left out open disputes, which drafting checks.
    with engine.begin() as c:
        c.execute(
            text(f"""INSERT INTO disputes (customer_id, invoice_id, reason)
            SELECT '{ABC}', id, 'quantity mismatch' FROM invoices WHERE number = 'INV-1047'""")
        )
    with tx(engine) as s:
        body = approval.get_message(s, draft_id).body
    with pytest.raises(AppError) as e, tx(engine) as s, s.begin():
        approval.edit(s, draft_id, "Overdue invoices", body, 1, None)

    assert e.value.code == ErrorCode.INVOICE_DISPUTED


def test_gate_refusal_fails_the_message_so_it_can_be_resent(engine: Engine, draft_id: str) -> None:
    # Review 2026-10-01: a dispute opened after approval left the message 'approved' and the job dead.
    ch = FakeChannel()
    approve(engine, draft_id)
    with engine.begin() as c:
        c.execute(
            text(f"""INSERT INTO disputes (customer_id, invoice_id, reason)
            SELECT '{ABC}', id, 'quantity mismatch' FROM invoices WHERE number = 'INV-1047'""")
        )

    worker(engine, ch)

    assert not ch.sent
    assert one(engine, f"SELECT status || '/' || last_error FROM messages WHERE id = '{draft_id}'") == (
        "failed/INVOICE_DISPUTED"
    )
    assert one(engine, f"SELECT status FROM jobs WHERE dedupe_key = '{draft_id}'") == "done"
