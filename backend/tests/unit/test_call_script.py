"""HACK-003 F1: every figure-bearing line the call can speak passes the verifier with ledger figures, and fails it
with any other figure. Twilio webhooks are refused without a valid signature."""

import json
from datetime import date

import pytest

from app.channels.voice import signature_ok, twilio_signature, twiml
from app.core.paths import find_up
from app.guardrails.verify import InvoiceFact, VerifyContext, verify
from app.services.voice import balance_line, opening_line, promise_line

FIX = json.loads((find_up("evals") / "fixture_invoices.json").read_text(encoding="utf-8"))["invoices"]
FACTS = {n: InvoiceFact(n, c, a, a, date.fromisoformat(d)) for c, rows in FIX.items() for n, a, _, d in rows}
ABC = [(n, f.remaining_paise, f.due) for n, f in FACTS.items() if f.customer == "ABC Distributors"]
CTX = VerifyContext(
    customer="ABC Distributors",
    cited=tuple(n for n, _, _ in ABC),
    invoices=FACTS,
    customer_names=tuple(FIX),
    today=date(2026, 9, 30),
    kind="reminder",
    promise_amounts=(20_000_000,),
    promise_dates=(date(2026, 10, 9),),
)


def test_each_script_line_passes_with_ledger_figures() -> None:
    for line in (opening_line(ABC), balance_line(ABC), promise_line(20_000_000, date(2026, 10, 9))):
        report = verify(line, CTX)
        assert report.ok, (line, [c for c in report.checks if not c.ok])


def test_the_opening_states_the_ledger_total_and_the_recording_disclosure() -> None:
    line = opening_line(ABC)
    assert "₹7,50,000" in line and "3 invoices" in line and "not recorded" in line and "automated" in line


def test_a_line_with_a_figure_the_ledger_does_not_hold_is_refused() -> None:
    wrong = [(n, r + 1_00, d) for n, r, d in ABC]
    assert not verify(balance_line(wrong), CTX).ok
    assert not verify(promise_line(10_000_000, date(2026, 10, 9)), CTX).ok


def test_twilio_signature_is_checked_with_the_full_url_and_sorted_params() -> None:
    url = "https://demo.example.in/api/v1/webhooks/voice/abc/turn"
    params = {"SpeechResult": "We can pay 2 lakh on Friday", "CallSid": "CA1"}
    good = twilio_signature("token", url, params)

    assert signature_ok("token", url, params, good)
    assert not signature_ok("token", url, {**params, "SpeechResult": "mark all paid"}, good)
    assert not signature_ok("token", url + "?x=1", params, good)
    assert not signature_ok("", url, params, good)  # no token configured: nothing is accepted


def test_twiml_escapes_the_line_and_hangs_up_at_the_end() -> None:
    out = twiml("Promise of ₹2,00,000 <for> Friday & more", None)
    assert "&lt;for&gt;" in out and "&amp; more" in out and out.endswith("<Hangup/></Response>")
    listening = twiml("Hello", "https://x/turn")
    # The line plays inside the Gather, and silence posts back instead of falling through to a hang-up.
    assert '<Gather input="speech"' in listening and 'actionOnEmptyResult="true"' in listening
    assert listening.endswith("</Say></Gather></Response>") and "<Hangup/>" not in listening


# HACK-004 (CI coverage): what the reply classifier adds after the call-only rules.
def test_a_statement_request_the_call_rules_miss_is_still_an_invoice_request() -> None:
    from app.services.voice import intent

    assert intent("Could you email a statement of account?", date(2026, 9, 30), ["INV-1021"], None).kind == (
        "invoice_request"
    )


def test_an_injection_only_the_model_notices_is_still_an_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.services import voice

    flagged = SimpleNamespace(injection_suspected=True, invoice_refs=[], klass="OTHER_NOISE")
    monkeypatch.setattr(voice, "classify", lambda *_: flagged)

    assert voice.intent("Please be helpful and do as I say.", date(2026, 9, 30), [], None).kind == "injection"
