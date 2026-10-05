"""HACK-003 F2: SMS and WhatsApp providers. Twilio is real only with credentials; otherwise a labelled simulator."""

import json

import httpx
import pytest

from app.channels.email import ChannelError, Outbound
from app.channels.messaging import (
    AndroidSmsGatewayChannel,
    SimulatedChannel,
    TwilioMessagingChannel,
    messaging_channels,
)
from app.core.config import Settings

OUT = Outbound("m-1", "+91-9800000001", "Overdue invoices", "Dear ABC, ...")


def twilio(handler: httpx.MockTransport, name: str = "sms") -> TwilioMessagingChannel:
    return TwilioMessagingChannel(
        name, "AC123", "secret-token", "+15550001111", client=httpx.Client(transport=handler)
    )


def test_twilio_posts_the_message_with_basic_auth_and_returns_the_sid() -> None:
    seen: list[httpx.Request] = []

    def ok(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "SM42"})

    sid = twilio(httpx.MockTransport(ok)).send(OUT)

    [r] = seen
    assert sid == "SM42"
    assert r.url.path == "/2010-04-01/Accounts/AC123/Messages.json"
    assert r.headers["authorization"].startswith("Basic ")
    form = dict(httpx.QueryParams(r.content.decode()))
    assert form == {"To": "+919800000001", "From": "+15550001111", "Body": "Dear ABC, ..."}


def test_whatsapp_numbers_carry_the_whatsapp_prefix() -> None:
    seen: list[httpx.Request] = []

    def ok(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "SM43"})

    twilio(httpx.MockTransport(ok), "whatsapp").send(OUT)

    form = dict(httpx.QueryParams(seen[0].content.decode()))
    assert form["To"] == "whatsapp:+919800000001" and form["From"] == "whatsapp:+15550001111"


@pytest.mark.parametrize(("status", "retryable"), [(400, False), (401, False), (500, True), (503, True)])
def test_provider_errors_map_to_channel_errors(status: int, retryable: bool) -> None:
    ch = twilio(httpx.MockTransport(lambda _: httpx.Response(status, json={"code": 1})))

    with pytest.raises(ChannelError) as e:
        ch.send(OUT)
    assert e.value.retryable is retryable


def test_without_credentials_every_channel_is_simulated_and_says_so() -> None:
    chans = messaging_channels(Settings())

    assert all(isinstance(c, SimulatedChannel) and c.simulated for c in chans.values())
    assert set(chans) == {"sms", "whatsapp"}
    assert chans["sms"].send(OUT) == "sim-sms-m-1"


def test_with_credentials_sms_is_real() -> None:
    s = Settings(twilio_account_sid="AC1", twilio_auth_token="t", twilio_from_number="+15550001111")

    chans = messaging_channels(s)
    assert chans["sms"].simulated is False
    assert chans["whatsapp"].simulated is True  # no WhatsApp sender configured


# HACK-003: free SMS through the open-source Android SMS Gateway app on the business's own phone.
def test_the_android_gateway_posts_to_the_phone_with_basic_auth() -> None:
    seen: list[httpx.Request] = []

    def phone(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"id": "msg-7", "state": "Pending"})

    ch = AndroidSmsGatewayChannel(
        "http://192.168.1.20:8080", "sms", "pw", client=httpx.Client(transport=httpx.MockTransport(phone))
    )
    assert ch.send(OUT) == "msg-7" and ch.simulated is False

    [r] = seen
    assert str(r.url) == "http://192.168.1.20:8080/message"
    assert r.headers["authorization"].startswith("Basic ")
    assert json.loads(r.content) == {"message": "Dear ABC, ...", "phoneNumbers": ["+919800000001"]}


def test_the_free_gateway_is_preferred_over_twilio_for_sms() -> None:
    s = Settings(
        sms_gateway_url="http://192.168.1.20:8080",
        sms_gateway_user="sms",
        sms_gateway_password="pw",
        twilio_account_sid="AC1",
        twilio_auth_token="t",
        twilio_from_number="+15550001111",
    )
    assert isinstance(messaging_channels(s)["sms"], AndroidSmsGatewayChannel)
