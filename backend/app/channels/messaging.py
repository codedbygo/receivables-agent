"""SMS and WhatsApp (HACK-003 F2). SMS: the free, open-source Android SMS Gateway when configured, else Twilio, else
a simulator that says it is one. WhatsApp: Twilio or the simulator (no free, compliant open-source route). Every channel carries `simulated`, which the send path stores on the message and shows in the console."""

import re

import httpx

from app.channels.email import ChannelError, MessageChannel, Outbound
from app.core.config import Settings

TWILIO_API = "https://api.twilio.com/2010-04-01"
TIMEOUT_S = 10.0


def e164(phone: str) -> str:
    """'+91-98000 00001' -> '+919800000001'; the seed and most ledgers keep separators."""
    return "+" + re.sub(r"\D", "", phone)


class SimulatedChannel:
    """Records nothing outside the database and contacts nobody; the message row is marked simulated."""

    simulated = True

    def __init__(self, name: str) -> None:
        self.name = name

    def send(self, message: Outbound) -> str:
        return f"sim-{self.name}-{message.message_id}"


class TwilioMessagingChannel:
    simulated = False

    def __init__(
        self, name: str, account_sid: str, auth_token: str, from_: str, client: httpx.Client | None = None
    ) -> None:
        self.name, self.sid, self.token, self.from_ = name, account_sid, auth_token, from_
        self.client = client or httpx.Client(timeout=TIMEOUT_S)

    def _addr(self, number: str) -> str:
        return f"whatsapp:{e164(number)}" if self.name == "whatsapp" else e164(number)

    def send(self, message: Outbound) -> str:
        try:
            r = self.client.post(
                f"{TWILIO_API}/Accounts/{self.sid}/Messages.json",
                data={"To": self._addr(message.to), "From": self._addr(self.from_), "Body": message.body},
                auth=(self.sid, self.token),
                timeout=TIMEOUT_S,
            )
        except httpx.HTTPError as e:
            raise ChannelError("PROVIDER_UNAVAILABLE", retryable=True) from e
        if r.status_code >= 500 or r.status_code == 429:
            raise ChannelError("PROVIDER_UNAVAILABLE", retryable=True)
        if (
            r.status_code >= 400
        ):  # bad number, no consent at the provider, bad credentials: a person must look
            raise ChannelError(f"PROVIDER_REJECTED_{r.status_code}", retryable=False)
        return str(r.json().get("sid", ""))


class AndroidSmsGatewayChannel:
    """Free, open-source SMS: the Android SMS Gateway app (local server mode) sends from the business's own SIM."""

    name = "sms"
    simulated = False

    def __init__(self, base_url: str, user: str, password: str, client: httpx.Client | None = None) -> None:
        self.url = base_url.rstrip("/") + "/message"
        self.auth = (user, password)
        self.client = client or httpx.Client(timeout=TIMEOUT_S)

    def send(self, message: Outbound) -> str:
        try:
            r = self.client.post(
                self.url,
                json={"message": message.body, "phoneNumbers": [e164(message.to)]},
                auth=self.auth,
                timeout=TIMEOUT_S,
            )
        except httpx.HTTPError as e:  # the phone is off, asleep or off the network
            raise ChannelError("PROVIDER_UNAVAILABLE", retryable=True) from e
        if r.status_code >= 500:
            raise ChannelError("PROVIDER_UNAVAILABLE", retryable=True)
        if r.status_code >= 400:
            raise ChannelError(f"PROVIDER_REJECTED_{r.status_code}", retryable=False)
        return str(r.json().get("id", ""))


def messaging_channels(s: Settings) -> dict[str, MessageChannel]:
    creds = bool(s.twilio_account_sid and s.twilio_auth_token)
    sms: MessageChannel
    if s.sms_gateway_url:  # free and open source first
        sms = AndroidSmsGatewayChannel(s.sms_gateway_url, s.sms_gateway_user, s.sms_gateway_password)
    elif creds and s.twilio_from_number:
        sms = TwilioMessagingChannel("sms", s.twilio_account_sid, s.twilio_auth_token, s.twilio_from_number)
    else:
        sms = SimulatedChannel("sms")
    wa: MessageChannel = (
        TwilioMessagingChannel("whatsapp", s.twilio_account_sid, s.twilio_auth_token, s.twilio_whatsapp_from)
        if creds and s.twilio_whatsapp_from
        else SimulatedChannel("whatsapp")
    )
    return {"sms": sms, "whatsapp": wa}
