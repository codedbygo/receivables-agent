"""Who may call the API (ADR-0019): people sign in with a password or Google; ADMIN_TOKEN signs scripts in;
the role header counts on a laptop only, and open roles refuse to start on a public host."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.services.auth import UNUSABLE_HASH, check_auth_config, hash_password, is_admin_token, verify_password


def settings(**kw: str) -> Settings:
    base = {"database_url": "postgresql+psycopg://x:x@nowhere:1/x", "demo_open_roles": False}
    return Settings.model_validate(base | kw)


def test_only_the_admin_token_signs_a_script_in() -> None:
    s = settings(admin_token="a-code")
    assert is_admin_token(s, "a-code")
    assert not is_admin_token(s, "nope")
    assert not is_admin_token(settings(), "")  # an unset token must not match an empty bearer


def test_a_password_matches_only_its_own_hash() -> None:
    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("correct horse batterY", stored)
    assert not verify_password("", UNUSABLE_HASH)  # a Google-only person has no password
    assert not verify_password("x", "scrypt$zz$zz") and not verify_password("x", "bcrypt$00$00")


def test_open_roles_refuse_to_start_on_a_public_host() -> None:
    s = Settings(demo_open_roles=True, allowed_hosts="localhost,demo.example.in")
    with pytest.raises(RuntimeError, match="DEMO_OPEN_ROLES"):
        check_auth_config(s)


def test_a_public_host_with_closed_roles_and_open_roles_on_loopback_are_allowed() -> None:
    check_auth_config(settings(allowed_hosts="demo.example.in"))
    check_auth_config(Settings(demo_open_roles=True, allowed_hosts="localhost,127.0.0.1"))


def test_the_role_header_no_longer_signs_anyone_in_when_roles_are_closed() -> None:
    app = create_app(settings(allowed_hosts="testserver", admin_token="a-code"))
    c = TestClient(app)
    assert c.get("/api/v1/customers", headers={"X-Demo-Role": "admin"}).status_code == 401
    assert c.get("/api/v1/customers", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/v1/customers").status_code == 401
