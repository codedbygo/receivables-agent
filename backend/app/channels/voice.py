"""Voice providers (HACK-003 F1). Twilio places a real call when configured; otherwise the simulator, where a
collector types what the customer says. Calls are never recorded: no Record parameter is ever sent."""

import base64
import hashlib
import hmac
from typing import Protocol
from xml.sax.saxutils import escape

import httpx

from app.channels.email import ChannelError
from app.channels.messaging import TIMEOUT_S, TWILIO_API, e164
from app.core.config import Settings


class VoiceProvider(Protocol):
    name: str
    simulated: bool

    def place(self, call_id: str, to: str) -> str: ...


class SimulatedVoice:
    name = "simulated"
    simulated = True

    def place(self, call_id: str, to: str) -> str:
        return f"sim-call-{call_id}"


class TwilioVoice:
    name = "twilio"
    simulated = False

    def __init__(self, s: Settings, client: httpx.Client | None = None) -> None:
        self.sid, self.token, self.from_ = s.twilio_account_sid, s.twilio_auth_token, s.twilio_from_number
        self.base = s.voice_public_base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=TIMEOUT_S)

    def place(self, call_id: str, to: str) -> str:
        hook = f"{self.base}/api/v1/webhooks/voice/{call_id}"
        try:
            r = self.client.post(
                f"{TWILIO_API}/Accounts/{self.sid}/Calls.json",
                data={
                    "To": e164(to),
                    "From": e164(self.from_),
                    "Url": f"{hook}/turn",
                    "Method": "POST",
                    "StatusCallback": f"{hook}/status",
                    "StatusCallbackEvent": "completed",
                },
                auth=(self.sid, self.token),
                timeout=TIMEOUT_S,
            )
        except httpx.HTTPError as e:
            raise ChannelError("PROVIDER_UNAVAILABLE", retryable=True) from e
        if r.status_code >= 400:
            raise ChannelError(f"PROVIDER_REJECTED_{r.status_code}", retryable=r.status_code >= 500)
        return str(r.json().get("sid", ""))


def voice_provider(s: Settings) -> VoiceProvider:
    real = s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number and s.voice_public_base_url
    return TwilioVoice(s) if real else SimulatedVoice()


def twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Twilio's X-Twilio-Signature: base64 HMAC-SHA1 of the full URL followed by each POST key and value, sorted."""
    payload = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def signature_ok(auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    return bool(auth_token) and hmac.compare_digest(
        twilio_signature(auth_token, url, params), signature or ""
    )


def twiml(line: str, gather_url: str | None) -> str:
    """Say the line; then listen for speech (posting to gather_url) or hang up."""
    say = f'<Say voice="Polly.Aditi" language="en-IN">{escape(line)}</Say>'
    tail = (
        f'<Gather input="speech" language="en-IN" speechTimeout="auto" action="{escape(gather_url)}" method="POST"/>'
        if gather_url
        else "<Hangup/>"
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{say}{tail}</Response>'
