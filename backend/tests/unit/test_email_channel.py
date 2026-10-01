"""Review 2026-10-01: an SMTP error after the server accepted the message must not make the worker retry."""

import smtplib

import pytest

from app.channels.email import ChannelError, EmailChannel, Outbound


class FakeSMTP:
    def __init__(self, *_a: object, **_k: object) -> None:
        self.accepted = 0

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *_a: object) -> None:
        raise OSError("timed out in QUIT")

    def send_message(self, _m: object) -> None:
        if FAIL_BEFORE:
            raise smtplib.SMTPConnectError(421, "busy")
        self.accepted += 1


FAIL_BEFORE = False
OUT = Outbound("m1", "a@example.in", "Subject", "Body")


def test_error_after_accept_is_treated_as_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    assert EmailChannel("h", 1).send(OUT).startswith("<m1@")


def test_error_before_accept_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setitem(globals(), "FAIL_BEFORE", True)

    with pytest.raises(ChannelError) as e:
        EmailChannel("h", 1).send(OUT)

    assert e.value.retryable
