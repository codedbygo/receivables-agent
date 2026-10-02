"""Access codes per role for a hosted demo (audit finding 1): the role comes from a secret, never from a
header anyone can type. Open roles (the header) are for a laptop and refuse to start on a public host."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.services.auth import check_auth_config, role_for_token

CODES = {"admin_token": "a-code", "collector_token": "c-code", "viewer_token": "v-code"}


def settings(**kw: str) -> Settings:
    base = {"database_url": "postgresql+psycopg://x:x@nowhere:1/x", "demo_open_roles": False}
    return Settings.model_validate(base | kw)


def test_each_code_maps_to_its_own_role() -> None:
    s = settings(**CODES)
    assert [role_for_token(s, c) for c in ("a-code", "c-code", "v-code")] == ["admin", "collector", "viewer"]


def test_wrong_or_empty_code_maps_to_no_role() -> None:
    s = settings(admin_token="a-code")
    assert role_for_token(s, "nope") is None
    assert role_for_token(s, "") is None  # an unset collector code must not match an empty bearer


def test_open_roles_refuse_to_start_on_a_public_host() -> None:
    s = Settings(demo_open_roles=True, allowed_hosts="localhost,demo.example.in")
    with pytest.raises(RuntimeError, match="DEMO_OPEN_ROLES"):
        check_auth_config(s)


def test_closed_roles_with_no_codes_refuse_to_start() -> None:
    with pytest.raises(RuntimeError, match="ADMIN_TOKEN"):
        check_auth_config(settings())


def test_codes_on_a_public_host_and_open_roles_on_loopback_are_allowed() -> None:
    check_auth_config(settings(allowed_hosts="demo.example.in", **CODES))
    check_auth_config(Settings(demo_open_roles=True, allowed_hosts="localhost,127.0.0.1"))


def test_the_role_header_no_longer_signs_anyone_in_when_roles_are_closed() -> None:
    app = create_app(settings(allowed_hosts="testserver", **CODES))
    c = TestClient(app)
    assert c.get("/api/v1/customers", headers={"X-Demo-Role": "admin"}).status_code == 401
    assert c.get("/api/v1/customers", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/v1/customers").status_code == 401
