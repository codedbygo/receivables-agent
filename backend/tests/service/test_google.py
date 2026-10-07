"""HACK-009 Google connection and Calendar sync over HTTP against Postgres, with Google faked at the httpx layer
(httpx.MockTransport): no test reaches Google."""

import base64
import email
import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.channels.email import ChannelError
from app.core.config import Settings
from app.core.errors import AppError
from app.services import approval, google, inbox
from app.services.demo import reset_demo, uid
from app.tools.registry import ToolContext, build_registry
from app.worker import runner

pytestmark = pytest.mark.integration
VIEWER = {"X-Demo-Role": "viewer"}
COLLECTOR = {"X-Demo-Role": "collector"}
ADMIN = {"X-Demo-Role": "admin"}
KEY = Fernet.generate_key().decode()
ACCOUNT = "collections@acme.example.com"


def settings(**extra: object) -> Settings:
    base: dict[str, object] = {
        "database_url": os.environ["DATABASE_URL"],
        "llm_mode": "replay",
        "session_secret": "s" * 32,
        "google_client_id": "cid",
        "google_client_secret": "csecret",
        "google_token_key": KEY,
        "google_redirect_uri": "https://ca.example.com/api/v1/google/callback",
    }
    return Settings.model_validate({**base, **extra})


class FakeGoogle:
    """Answers the token, userinfo, revoke and Calendar endpoints the app calls, and records each request."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bytes]] = []
        self.scope = " ".join(google.SCOPES)
        self.down = False
        self.events = 0
        self.threads: dict[str, list[dict[str, object]]] = {}
        self.fail: dict[str, int | str] = {}  # url prefix -> a status code to answer, or "down"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("down", request=request)
        url = str(request.url)
        self.calls.append((request.method, url, request.content))
        for prefix, outcome in self.fail.items():
            if url.startswith(prefix):
                if outcome == "down":
                    raise httpx.ConnectError("down", request=request)
                return httpx.Response(int(outcome), json={})
        form = parse_qs(request.content.decode()) if request.method == "POST" else {}
        if url == google.EXCHANGE_URL:
            if form.get("code") == ["good"]:
                return httpx.Response(
                    200, json={"access_token": "at", "refresh_token": "rt", "scope": self.scope}
                )
            if form.get("refresh_token") == ["rt"]:
                return httpx.Response(200, json={"access_token": "at2"})
            return httpx.Response(400, json={"error": "invalid_grant"})
        if url == google.USERINFO_URL:
            return httpx.Response(200, json={"email": ACCOUNT})
        if url.startswith(google.REVOKE_URL):
            return httpx.Response(200)
        if url == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send":
            return httpx.Response(200, json={"id": "g-sent", "threadId": "t1"})
        if url.startswith("https://gmail.googleapis.com/gmail/v1/users/me/threads/"):
            thread = url.split("/threads/")[1].split("?")[0]
            return httpx.Response(200, json={"id": thread, "messages": self.threads.get(thread, [])})
        if url.startswith("https://www.googleapis.com/calendar/v3/calendars/primary/events"):
            if request.method == "POST":
                self.events += 1
                return httpx.Response(200, json={"id": f"ev{self.events}"})
            return httpx.Response(204)
        return httpx.Response(404)

    def made(self, method: str, prefix: str) -> list[bytes]:
        return [body for m, u, body in self.calls if m == method and u.startswith(prefix)]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeGoogle:
    f = FakeGoogle()
    monkeypatch.setattr(google, "http", lambda: httpx.Client(transport=httpx.MockTransport(f)))
    return f


@pytest.fixture
def make_api(engine: Engine) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def make(**extra: object) -> TestClient:
        s = settings(**extra)
        reset_demo(engine, s)
        with engine.begin() as c:
            c.execute(text("DELETE FROM google_account"))
        c = TestClient(create_app(s), follow_redirects=False)
        c.__enter__()
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def connect(api: TestClient) -> httpx.Response:
    url = api.post("/api/v1/google/connect", headers=ADMIN).json()["url"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    return api.get("/api/v1/google/callback", params={"code": "good", "state": state})


def test_status_says_set_up_but_not_connected(make_api: Callable[..., TestClient]) -> None:
    api = make_api()

    r = api.get("/api/v1/google/status", headers=VIEWER)

    assert r.json() == {
        "configured": True,
        "connected": False,
        "email": None,
        "connected_at": None,
        "email_provider": "smtp",
    }


def test_connect_hands_an_admin_a_google_url_asking_for_every_permission(
    make_api: Callable[..., TestClient],
) -> None:
    api = make_api()

    r = api.post("/api/v1/google/connect", headers=ADMIN)

    q = parse_qs(urlsplit(r.json()["url"]).query)
    assert r.status_code == 200
    assert (q["client_id"], q["access_type"], q["prompt"]) == (["cid"], ["offline"], ["consent"])
    assert set(q["scope"][0].split()) == set(google.SCOPES)
    assert q["redirect_uri"] == ["https://ca.example.com/api/v1/google/callback"]


def test_only_an_admin_connects_and_only_when_google_is_set_up(make_api: Callable[..., TestClient]) -> None:
    assert make_api().post("/api/v1/google/connect", headers=COLLECTOR).status_code == 403
    r = make_api(google_client_id="").post("/api/v1/google/connect", headers=ADMIN)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "GOOGLE_NOT_CONFIGURED")


def test_the_callback_stores_the_refresh_token_encrypted(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()

    r = connect(api)

    assert (r.status_code, r.headers["location"]) == (303, "/?google=connected#/admin")
    with engine.connect() as c:
        row = c.execute(text("SELECT email, refresh_token_enc FROM google_account")).one()
    assert row.email == ACCOUNT
    assert "rt" not in row.refresh_token_enc
    assert Fernet(KEY.encode()).decrypt(row.refresh_token_enc.encode()) == b"rt"
    assert api.get("/api/v1/google/status", headers=VIEWER).json()["email"] == ACCOUNT


@pytest.mark.parametrize(
    "params",
    [
        {"code": "good", "state": "forged.123.abc.0000"},
        {"code": "bad", "state": "<real>"},
        {"error": "access_denied", "state": "<real>"},
    ],
)
def test_a_bad_callback_stores_nothing_and_says_why(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine, params: dict[str, str]
) -> None:
    api = make_api()
    real = parse_qs(urlsplit(api.post("/api/v1/google/connect", headers=ADMIN).json()["url"]).query)["state"][
        0
    ]

    r = api.get(
        "/api/v1/google/callback", params={k: real if v == "<real>" else v for k, v in params.items()}
    )

    assert r.status_code == 303 and r.headers["location"].startswith("/?google_error=")
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM google_account")).scalar_one() == 0


def test_an_expired_state_or_missing_permissions_are_refused(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()
    old = parse_qs(urlsplit(google.auth_url(settings(), uid("user", "x"), now=0)).query)["state"][0]
    expired = api.get("/api/v1/google/callback", params={"code": "good", "state": old})
    fake.scope = "openid email"
    partial = connect(api)

    assert "expired" in expired.headers["location"]
    assert "permission" in partial.headers["location"]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM google_account")).scalar_one() == 0


def test_disconnect_forgets_the_account_and_revokes_the_grant(
    make_api: Callable[..., TestClient], fake: FakeGoogle
) -> None:
    api = make_api()
    connect(api)

    r = api.post("/api/v1/google/disconnect", headers=ADMIN)

    assert r.json()["connected"] is False
    assert fake.made("POST", google.REVOKE_URL)
    assert api.post("/api/v1/google/disconnect", headers=ADMIN).status_code == 200  # twice is fine


def test_disconnect_survives_google_being_down(make_api: Callable[..., TestClient], fake: FakeGoogle) -> None:
    api = make_api()
    connect(api)
    fake.down = True

    assert api.post("/api/v1/google/disconnect", headers=ADMIN).json()["connected"] is False


def test_sync_puts_each_open_follow_up_and_promise_in_the_calendar_once(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()
    connect(api)
    abc = uid("customer", "ABC Distributors")
    with engine.begin() as c:
        c.execute(
            text("""INSERT INTO promises (customer_id, amount_paise, promised_date)
            VALUES (CAST(:c AS uuid), 30000000, DATE '2026-10-05')"""),
            {"c": abc},
        )
        open_tasks = c.execute(
            text("SELECT count(*) FROM follow_up_tasks WHERE status = 'open'")
        ).scalar_one()

    first = api.post("/api/v1/google/sync", headers=COLLECTOR)
    second = api.post("/api/v1/google/sync", headers=COLLECTOR)

    assert first.json() == {"calendar": {"created": open_tasks + 1, "removed": 0}, "replies_found": 0}
    assert second.json() == {"calendar": {"created": 0, "removed": 0}, "replies_found": 0}
    bodies = [b.decode() for b in fake.made("POST", "https://www.googleapis.com/calendar")]
    promise = next(b for b in bodies if "promised" in b)
    assert "ABC Distributors promised ₹3,00,000" in promise
    assert '"start":{"date":"2026-10-05"}' in promise and '"end":{"date":"2026-10-06"}' in promise
    assert f"https://ca.example.com/#/customers/{abc}" in promise


def test_a_closed_task_and_a_settled_promise_leave_the_calendar(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()
    connect(api)
    api.post("/api/v1/google/sync", headers=COLLECTOR)
    with engine.begin() as c:
        c.execute(text("UPDATE follow_up_tasks SET status = 'done', closed_at = now() WHERE status = 'open'"))

    r = api.post("/api/v1/google/sync", headers=COLLECTOR)

    assert r.json()["calendar"]["removed"] >= 1
    assert len(fake.made("DELETE", "https://www.googleapis.com/calendar")) == r.json()["calendar"]["removed"]
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM calendar_events")).scalar_one() == 0


@pytest.mark.parametrize(
    ("before", "code", "status"),
    [
        ("none", "GOOGLE_NOT_CONNECTED", 409),
        ("down", "GOOGLE_UPSTREAM", 503),
        ("revoked", "GOOGLE_NOT_CONNECTED", 409),
    ],
)
def test_sync_says_plainly_when_google_cannot_be_used(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine, before: str, code: str, status: int
) -> None:
    api = make_api()
    if before != "none":
        connect(api)
    fake.down = before == "down"
    if before == "revoked":  # Google says invalid_grant for a refresh token the user revoked
        with engine.begin() as c:
            enc = Fernet(KEY.encode()).encrypt(b"revoked").decode()
            c.execute(text("UPDATE google_account SET refresh_token_enc = :e"), {"e": enc})

    r = api.post("/api/v1/google/sync", headers=COLLECTOR)

    assert (r.status_code, r.json()["error"]["code"]) == (status, code)


def test_a_viewer_cannot_sync(make_api: Callable[..., TestClient]) -> None:
    assert make_api().post("/api/v1/google/sync", headers=VIEWER).status_code == 403


def test_a_token_stored_under_another_key_asks_to_connect_again(
    make_api: Callable[..., TestClient], fake: FakeGoogle
) -> None:
    connect(make_api())
    other = TestClient(create_app(settings(google_token_key=Fernet.generate_key().decode())))

    r = other.post("/api/v1/google/sync", headers=COLLECTOR)

    assert (r.status_code, r.json()["error"]["code"]) == (409, "GOOGLE_NOT_CONNECTED")


def test_a_malformed_key_is_reported_as_set_up_wrong(
    make_api: Callable[..., TestClient], fake: FakeGoogle
) -> None:
    r = connect(make_api(google_token_key="not-a-key"))

    assert "GOOGLE_TOKEN_KEY" in r.headers["location"]


def test_the_worker_syncs_every_5_minutes_only_while_connected(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()
    at = datetime(2026, 10, 7, 4, 7, tzinfo=UTC)
    runner.schedule(engine, at)
    with engine.connect() as c:
        before = c.execute(text("SELECT count(*) FROM jobs WHERE kind = 'google_sync'")).scalar_one()
    connect(api)
    runner.schedule(engine, at)
    runner.schedule(engine, at.replace(minute=9))  # same 5-minute window: no second job

    with engine.connect() as c:
        keys = c.execute(text("SELECT dedupe_key FROM jobs WHERE kind = 'google_sync'")).scalars().all()
    assert before == 0
    assert keys == ["2026-10-07T04:05:00+00:00"]
    handler = runner.handlers(engine, settings())["google_sync"]
    handler(engine, {})
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM calendar_events")).scalar_one() > 0


def test_the_worker_job_is_quiet_when_google_is_not_connected_but_not_when_it_is_down(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()
    handler = runner.handlers(engine, settings())["google_sync"]
    handler(engine, {})  # not connected: nothing to do
    connect(api)
    fake.down = True

    with pytest.raises(AppError):
        handler(engine, {})


def test_a_demo_reset_keeps_google_connected(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()
    connect(api)

    reset_demo(engine, settings())

    assert api.get("/api/v1/google/status", headers=VIEWER).json()["connected"] is True


# Gmail sending and incoming replies (HACK-009 parts 2 and 3)

PROSE = (
    "Dear Metro Wholesale,\n\nA gentle reminder that these invoices are now past due:\n\n{{invoice_table}}\n\n"
    "Total outstanding: {{total}}\n\nPlease let us know when we can expect payment.\n\nRegards,\nAccounts team"
)
METRO = uid("customer", "Metro Wholesale")


def b64(text_: str) -> str:
    return base64.urlsafe_b64encode(text_.encode()).decode().rstrip("=")


def reply(gid: str, sender: str, body: str, labels: tuple[str, ...] = ("INBOX",)) -> dict[str, object]:
    return {
        "id": gid,
        "labelIds": list(labels),
        "internalDate": "1790000000000",
        "snippet": body[:40],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": "Re: Overdue invoices"},
            ],
            "parts": [
                {"mimeType": "text/html", "body": {"data": b64("<p>html</p>")}},
                {"mimeType": "text/plain", "body": {"data": b64(body)}},
            ],
        },
    }


def send_reminder(api: TestClient, engine: Engine, s: Settings) -> str:
    """Draft, approve and deliver one reminder to Metro through the channel the settings choose."""
    mid = build_registry(engine).invoke(
        "draft_message",
        {"customer_id": METRO, "kind": "reminder", "prose": PROSE, "tone": "gentle"},
        ToolContext("ai", "agent"),
    )["data"]["message_id"]
    assert (
        api.post(f"/api/v1/messages/{mid}/approve", headers={**COLLECTOR, "If-Match": "1"}).status_code == 200
    )
    approval.deliver(engine, mid, runner.channels(s, engine))
    return str(mid)


def sent_mail(fake: FakeGoogle) -> email.message.Message:
    raw = json.loads(fake.made("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")[-1])[
        "raw"
    ]
    return email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_gmail_sends_from_the_connected_account_to_the_customer_and_keeps_the_thread(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api(email_provider="gmail")
    connect(api)

    mid = send_reminder(api, engine, settings(email_provider="gmail"))

    mail = sent_mail(fake)
    assert (mail["From"], mail["To"]) == (ACCOUNT, "accounts@metro-wholesale.example.in")
    with engine.connect() as c:
        row = c.execute(
            text("SELECT status, provider_ref FROM messages WHERE id = CAST(:m AS uuid)"), {"m": mid}
        ).one()
    assert (row.status, row.provider_ref) == ("sent", "t1")


def test_gmail_follows_the_redirect_rule_like_smtp(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api(email_provider="gmail", email_redirect_to="inbox@acme.example.com")
    connect(api)

    send_reminder(api, engine, settings(email_provider="gmail", email_redirect_to="inbox@acme.example.com"))

    mail = sent_mail(fake)
    assert mail["To"] == "inbox@acme.example.com"
    assert mail["Subject"].startswith("[demo to accounts@metro-wholesale.example.in]")


def test_gmail_without_a_connection_leaves_the_message_unsent_with_the_reason(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api(email_provider="gmail")

    with pytest.raises(ChannelError, match="GOOGLE_NOT_CONNECTED"):  # the job queue retries it
        send_reminder(api, engine, settings(email_provider="gmail"))

    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT status, last_error FROM messages WHERE customer_id = CAST(:c AS uuid) ORDER BY created_at DESC LIMIT 1"
            ),
            {"c": METRO},
        ).one()
    assert (row.status, row.last_error) == ("approved", "GOOGLE_NOT_CONNECTED")


def connected_with_a_reply(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> TestClient:
    api = make_api(email_provider="gmail")
    connect(api)
    send_reminder(api, engine, settings(email_provider="gmail"))
    fake.threads["t1"] = [
        reply("g-sent", ACCOUNT, "Dear Metro Wholesale, a gentle reminder", labels=("SENT",)),
        reply(
            "g-1",
            "Metro Accounts <ap@metro.example.com>",
            "We can pay ₹3 lakh on October 5 and the remainder later.\n\n"
            "On Wed, 30 Sep 2026 at 09:00, Accounts team <collections@acme.example.com>\nwrote:\n> Dear Metro",
        ),
        reply("g-2", f"Accounts <{ACCOUNT}>", "a note we sent from another device"),
    ]
    return api


def test_a_sync_queues_the_customers_reply_without_the_quoted_reminder(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = connected_with_a_reply(make_api, fake, engine)

    first = api.post("/api/v1/google/sync", headers=COLLECTOR)
    again = api.post("/api/v1/google/sync", headers=COLLECTOR)

    assert (first.json()["replies_found"], again.json()["replies_found"]) == (1, 0)
    queue = api.get("/api/v1/google/inbox", headers=VIEWER).json()["data"]
    assert len(queue) == 1
    item = queue[0]
    assert (item["customer_name"], item["from_address"]) == ("Metro Wholesale", "ap@metro.example.com")
    assert item["body"] == "We can pay ₹3 lakh on October 5 and the remainder later."


def test_accepting_a_reply_classifies_it_like_a_pasted_one(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = connected_with_a_reply(make_api, fake, engine)
    api.post("/api/v1/google/sync", headers=COLLECTOR)
    item = api.get("/api/v1/google/inbox", headers=VIEWER).json()["data"][0]

    r = api.post(f"/api/v1/google/inbox/{item['id']}/accept", headers=COLLECTOR)

    assert r.status_code == 200, r.text
    assert r.json()["classification"] == "PROMISE"
    assert api.get("/api/v1/google/inbox", headers=VIEWER).json()["data"] == []
    again = api.post(f"/api/v1/google/inbox/{item['id']}/accept", headers=COLLECTOR)
    assert (again.status_code, again.json()["error"]["message"]) == (409, "This reply was already accepted.")


def test_dismissing_a_reply_takes_it_off_the_queue_and_records_nothing(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = connected_with_a_reply(make_api, fake, engine)
    api.post("/api/v1/google/sync", headers=COLLECTOR)
    item = api.get("/api/v1/google/inbox", headers=VIEWER).json()["data"][0]
    with engine.connect() as c:
        before = c.execute(text("SELECT count(*) FROM replies")).scalar_one()

    r = api.post(f"/api/v1/google/inbox/{item['id']}/dismiss", headers=COLLECTOR)

    assert r.json()["status"] == "dismissed"
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM replies")).scalar_one() == before


def test_a_viewer_cannot_review_and_an_unknown_reply_is_404(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = connected_with_a_reply(make_api, fake, engine)
    api.post("/api/v1/google/sync", headers=COLLECTOR)
    item = api.get("/api/v1/google/inbox", headers=VIEWER).json()["data"][0]

    assert api.post(f"/api/v1/google/inbox/{item['id']}/accept", headers=VIEWER).status_code == 403
    assert api.post(f"/api/v1/google/inbox/{uid('x', 'y')}/dismiss", headers=COLLECTOR).status_code == 404


def test_the_worker_job_reads_replies_when_gmail_is_the_provider(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    connected_with_a_reply(make_api, fake, engine)

    runner.handlers(engine, settings(email_provider="gmail"))["google_sync"](engine, {})

    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM inbound_emails")).scalar_one() == 1


def test_a_reply_with_no_plain_text_falls_back_to_the_snippet(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = connected_with_a_reply(make_api, fake, engine)
    html_only = reply("g-3", "ap@metro.example.com", "Paid today, UTR 9981")
    html_only["payload"] = {
        "mimeType": "text/html",
        "headers": [{"name": "From", "value": "ap@metro.example.com"}],
    }
    fake.threads["t1"] = [html_only]

    api.post("/api/v1/google/sync", headers=COLLECTOR)

    assert api.get("/api/v1/google/inbox", headers=VIEWER).json()["data"][0]["body"] == "Paid today, UTR 9981"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Paid.\n\nOn Tue, 6 Oct 2026, A <a@x.in> wrote:\n> old", "Paid."),
        ("Paid.\n-----Original Message-----\nFrom: us", "Paid."),
        ("Paid.\n> quoted", "Paid."),
        ("Just text", "Just text"),
    ],
)
def test_only_the_new_text_of_a_reply_is_kept(body: str, expected: str) -> None:
    assert inbox.new_text(body) == expected


CAL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def test_the_real_http_client_has_a_timeout() -> None:
    with google.http() as c:
        assert c.timeout.connect == 10


@pytest.mark.parametrize("outcome", ["down", 200])
def test_connect_fails_cleanly_when_google_cannot_name_the_account(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine, outcome: int | str
) -> None:
    api = make_api()
    fake.fail[google.USERINFO_URL] = outcome  # unreachable, or an answer without an email

    r = connect(api)

    assert r.headers["location"].startswith("/?google_error=")
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM google_account")).scalar_one() == 0


@pytest.mark.parametrize(("outcome", "status"), [("down", 503), (500, 503)])
def test_a_calendar_failure_after_sign_in_is_reported(
    make_api: Callable[..., TestClient], fake: FakeGoogle, outcome: int | str, status: int
) -> None:
    api = make_api()
    connect(api)
    fake.fail[CAL] = outcome

    r = api.post("/api/v1/google/sync", headers=COLLECTOR)

    assert (r.status_code, r.json()["error"]["code"]) == (status, "GOOGLE_UPSTREAM")


def test_an_event_already_deleted_in_google_still_leaves_the_calendar_table(
    make_api: Callable[..., TestClient], fake: FakeGoogle, engine: Engine
) -> None:
    api = make_api()
    connect(api)
    api.post("/api/v1/google/sync", headers=COLLECTOR)
    with engine.begin() as c:
        c.execute(text("UPDATE follow_up_tasks SET status = 'done', closed_at = now() WHERE status = 'open'"))
    fake.fail[CAL + "/"] = 404  # someone deleted the events by hand

    r = api.post("/api/v1/google/sync", headers=COLLECTOR)

    assert r.status_code == 200 and r.json()["calendar"]["removed"] >= 1
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM calendar_events")).scalar_one() == 0
