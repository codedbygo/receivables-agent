"""HACK-011 (ADR-0019): people sign in with a password or Google and get a session cookie; an admin manages them.
Google is faked at the httpx layer (httpx.MockTransport): no test reaches Google."""

import os
import time
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, text

from app.api.main import create_app
from app.core.config import Settings
from app.core.errors import AppError
from app.services import google
from app.services.auth import DEMO_PASSWORD, MAX_FAILED, SESSION_COOKIE
from app.services.demo import reset_demo

pytestmark = pytest.mark.integration
SCRIPT = {"Authorization": "Bearer script-token"}  # ADMIN_TOKEN: signs in as the demo admin
PASSWORD = "a long enough password"


def settings(**extra: object) -> Settings:
    base: dict[str, object] = {
        "database_url": os.environ["DATABASE_URL"],
        "llm_mode": "replay",
        "demo_open_roles": False,
        "admin_token": "script-token",
        "session_secret": "s" * 32,
        "google_client_id": "cid",
        "google_client_secret": "csecret",
        "google_redirect_uri": "https://ca.example.com/api/v1/google/callback",
    }
    return Settings.model_validate({**base, **extra})


@pytest.fixture
def make_api(engine: Engine) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def make(**extra: object) -> TestClient:
        s = settings(**extra)
        reset_demo(engine, s)
        # https: the session cookie is Secure, and the test client sends it over https only.
        c = TestClient(create_app(s), base_url="https://testserver", follow_redirects=False)
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.close()


def email() -> str:
    return f"p-{uuid.uuid4().hex[:8]}@acme.example.com"


def add(api: TestClient, role: str = "collector", password: str | None = PASSWORD) -> dict[str, object]:
    who = email()
    body: dict[str, object] = {"email": who, "display_name": "Ravi", "role": role}
    if password:
        body["password"] = password
    r = api.post("/api/v1/users", json=body, headers=SCRIPT)
    assert r.status_code == 201, r.text
    out: dict[str, object] = r.json()
    return out


def sign_in(api: TestClient, who: object, password: str = PASSWORD) -> Response:
    return api.post("/api/v1/auth/login", json={"email": who, "password": password})


def test_a_person_signs_in_with_a_password_and_out_again(make_api: Callable[..., TestClient]) -> None:
    api = make_api()
    person = add(api)

    r = sign_in(api, str(person["email"]).upper())  # the email matches whatever its case

    assert r.status_code == 200 and r.json()["display_name"] == "Ravi"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie and "path=/api" in cookie
    me = api.get("/api/v1/auth/me").json()
    assert (me["email"], me["role"]) == (person["email"], "collector")
    assert api.post("/api/v1/auth/logout").status_code == 204
    assert api.get("/api/v1/auth/me").status_code == 401


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(
    make_api: Callable[..., TestClient],
) -> None:
    api = make_api()
    person = add(api)

    wrong, unknown = sign_in(api, person["email"], "not it at all"), sign_in(api, email())

    assert wrong.status_code == unknown.status_code == 401
    assert (
        wrong.json()["error"]["message"]
        == unknown.json()["error"]["message"]
        == "Email or password is wrong."
    )
    assert SESSION_COOKIE not in api.cookies


def test_wrong_passwords_lock_the_account_and_the_right_one_waits(
    make_api: Callable[..., TestClient], engine: Engine
) -> None:
    api = make_api()
    person = add(api)

    for _ in range(MAX_FAILED):
        assert sign_in(api, person["email"], "wrong password").status_code == 401
    locked = sign_in(api, person["email"])

    assert locked.status_code == 429 and "Too many wrong passwords" in locked.json()["error"]["message"]
    with engine.begin() as conn:  # the lock ends; the count then starts again from a right password
        conn.execute(text("UPDATE users SET locked_until = now() WHERE email = :e"), {"e": person["email"]})
    assert sign_in(api, person["email"]).status_code == 200


def test_the_demo_accounts_are_refused_when_hosted_and_sign_in_on_a_laptop(
    make_api: Callable[..., TestClient],
) -> None:
    hosted = make_api()
    assert sign_in(hosted, "admin@example.in", DEMO_PASSWORD).status_code == 401

    laptop = make_api(demo_open_roles=True)
    assert sign_in(laptop, "admin@example.in", DEMO_PASSWORD).status_code == 200


def test_a_switched_off_person_loses_their_session_at_once(make_api: Callable[..., TestClient]) -> None:
    api = make_api()
    person = add(api)
    sign_in(api, person["email"])

    off = api.patch(f"/api/v1/users/{person['id']}", json={"active": False}, headers=SCRIPT)

    assert off.status_code == 200 and off.json()["active"] is False
    api.cookies.clear()  # the script's own request had no cookie; check the person's old one fails
    assert api.get("/api/v1/auth/me").status_code == 401
    assert sign_in(api, person["email"]).status_code == 401


def test_only_an_admin_manages_people_and_cannot_remove_their_own_access(
    make_api: Callable[..., TestClient],
) -> None:
    api = make_api()
    collector, admin = add(api), add(api, role="admin")

    sign_in(api, collector["email"])
    assert api.get("/api/v1/users").status_code == 403
    sign_in(api, admin["email"])
    listed = api.get("/api/v1/users").json()["data"]
    mine = api.patch(f"/api/v1/users/{admin['id']}", json={"role": "viewer"})
    again = api.post(
        "/api/v1/users", json={"email": collector["email"], "display_name": "Copy", "role": "viewer"}
    )

    assert any(p["email"] == collector["email"] and p["has_password"] for p in listed)
    assert mine.status_code == 422 and "your own admin access" in mine.json()["error"]["message"]
    assert again.status_code == 422 and "already has that email" in again.json()["error"]["message"]


def test_an_admin_sets_a_new_password_which_also_unlocks(make_api: Callable[..., TestClient]) -> None:
    api = make_api()
    person = add(api)
    for _ in range(MAX_FAILED):
        sign_in(api, person["email"], "wrong password")

    api.patch(f"/api/v1/users/{person['id']}", json={"password": "a brand new password"}, headers=SCRIPT)

    assert sign_in(api, person["email"], "a brand new password").status_code == 200


class FakeGoogle:
    def __init__(self) -> None:
        self.userinfo: dict[str, object] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == google.EXCHANGE_URL:
            return httpx.Response(200, json={"access_token": "at", "scope": "openid email"})
        if str(request.url) == google.USERINFO_URL:
            return httpx.Response(200, json=self.userinfo)
        return httpx.Response(404)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeGoogle:
    f = FakeGoogle()
    monkeypatch.setattr(google, "http", lambda: httpx.Client(transport=httpx.MockTransport(f)))
    return f


def google_round_trip(api: TestClient) -> Response:
    start = api.get("/api/v1/auth/google")
    q = parse_qs(urlsplit(start.headers["location"]).query)
    assert q["scope"] == ["openid email"] and "access_type" not in q  # sign-in asks for the email only
    return api.get("/api/v1/google/callback", params={"code": "c", "state": q["state"][0]})


def test_google_signs_in_an_active_person_by_verified_email(
    make_api: Callable[..., TestClient], fake: FakeGoogle
) -> None:
    api = make_api()
    person = add(api, password=None)  # Google only
    fake.userinfo = {"email": person["email"], "email_verified": True}

    r = google_round_trip(api)

    assert r.status_code == 303 and r.headers["location"] == "/#/"
    assert api.get("/api/v1/auth/me").json()["email"] == person["email"]
    assert sign_in(api, person["email"], "any password at all").status_code == 401  # nothing to guess


def test_google_refuses_an_email_nobody_added(make_api: Callable[..., TestClient], fake: FakeGoogle) -> None:
    api = make_api()
    fake.userinfo = {"email": email(), "email_verified": True}

    r = google_round_trip(api)

    assert r.status_code == 303 and "has%20no%20access" in r.headers["location"]
    assert api.get("/api/v1/auth/me").status_code == 401


def test_google_refuses_an_email_it_has_not_verified(
    make_api: Callable[..., TestClient], fake: FakeGoogle
) -> None:
    api = make_api()
    person = add(api, password=None)
    fake.userinfo = {"email": person["email"], "email_verified": False}

    r = google_round_trip(api)

    assert r.status_code == 303 and r.headers["location"].startswith("/?signin_error=")
    assert api.get("/api/v1/auth/me").status_code == 401


def test_a_mailbox_connect_state_never_signs_anyone_in() -> None:
    s = settings()
    connect_state = google._state(s, str(uuid.uuid4()), time.time())  # what Connect Google hands an admin

    with pytest.raises(AppError, match="not valid"):
        google.login_email(s, "c", connect_state)


def test_the_bootstrap_admin_is_created_once_and_not_brought_back(
    make_api: Callable[..., TestClient], fake: FakeGoogle
) -> None:
    boss = email()
    api = make_api(bootstrap_admin_email=boss)
    fake.userinfo = {"email": boss, "email_verified": True}

    google_round_trip(api)
    me = api.get("/api/v1/auth/me").json()
    assert (me["email"], me["role"]) == (boss, "admin")

    api.patch(f"/api/v1/users/{me['id']}", json={"active": False}, headers=SCRIPT)
    api.cookies.clear()
    google_round_trip(api)
    assert api.get("/api/v1/auth/me").status_code == 401
