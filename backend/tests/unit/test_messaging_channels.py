"""HACK-003 F2: SMS and WhatsApp providers. Twilio is real only with credentials; otherwise a labelled simulator."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.channels.email import ChannelError, Outbound
from app.channels.messaging import (
    AndroidSmsGatewayChannel,
    SimulatedChannel,
    TwilioMessagingChannel,
    messaging_channels,
)
from app.channels.voice import TwilioVoice
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


# HACK-004 (CI coverage): every way a provider can fail is retryable or final, never silent.
def unreachable(_: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no route to host")


def test_twilio_unreachable_is_retryable() -> None:
    with pytest.raises(ChannelError) as e:
        twilio(httpx.MockTransport(unreachable)).send(OUT)

    assert (e.value.code, e.value.retryable) == ("PROVIDER_UNAVAILABLE", True)


def gateway(handler: httpx.MockTransport) -> AndroidSmsGatewayChannel:
    return AndroidSmsGatewayChannel(
        "http://192.168.1.20:8080", "sms", "pw", client=httpx.Client(transport=handler)
    )


@pytest.mark.parametrize(
    ("respond", "code", "retryable"),
    [
        (unreachable, "PROVIDER_UNAVAILABLE", True),  # the phone is off or off the network
        (lambda _: httpx.Response(503), "PROVIDER_UNAVAILABLE", True),
        (lambda _: httpx.Response(401), "PROVIDER_REJECTED_401", False),
    ],
)
def test_the_android_gateway_failures_are_retryable_or_final(
    respond: Callable[[httpx.Request], httpx.Response], code: str, retryable: bool
) -> None:
    with pytest.raises(ChannelError) as e:
        gateway(httpx.MockTransport(respond)).send(OUT)

    assert (e.value.code, e.value.retryable) == (code, retryable)


def twilio_voice(handler: httpx.MockTransport) -> TwilioVoice:
    s = Settings(
        twilio_account_sid="AC1",
        twilio_auth_token="t",
        twilio_from_number="+15550001111",
        voice_public_base_url="https://demo.example.in/",
    )
    return TwilioVoice(s, client=httpx.Client(transport=handler))


def test_twilio_voice_places_the_call_with_signed_webhook_urls() -> None:
    seen: list[httpx.Request] = []

    def ok(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"sid": "CA9"})

    assert twilio_voice(httpx.MockTransport(ok)).place("call-1", "+91-9800000001") == "CA9"
    form = dict(httpx.QueryParams(seen[0].content.decode()))
    assert form["To"] == "+919800000001"
    assert form["Url"] == "https://demo.example.in/api/v1/webhooks/voice/call-1/turn"
    assert form["StatusCallback"] == "https://demo.example.in/api/v1/webhooks/voice/call-1/status"


@pytest.mark.parametrize(
    ("respond", "code", "retryable"),
    [
        (unreachable, "PROVIDER_UNAVAILABLE", True),
        (lambda _: httpx.Response(500), "PROVIDER_REJECTED_500", True),
        (lambda _: httpx.Response(400), "PROVIDER_REJECTED_400", False),
    ],
)
def test_twilio_voice_failures_are_retryable_or_final(
    respond: Callable[[httpx.Request], httpx.Response], code: str, retryable: bool
) -> None:
    with pytest.raises(ChannelError) as e:
        twilio_voice(httpx.MockTransport(respond)).place("call-1", "+91-9800000001")

    assert (e.value.code, e.value.retryable) == (code, retryable)
