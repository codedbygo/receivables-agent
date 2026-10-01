from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings


def client(db_ok: bool) -> TestClient:
    app = create_app(Settings(database_url="postgresql+psycopg://x:x@nowhere:1/x"))
    app.state.check_db = lambda: db_ok
    return TestClient(app)


# TC-0264 (AC-US-01-014-1)
def test_healthz_is_ok_without_dependencies() -> None:
    r = client(db_ok=False).get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {}}


# TC-0264 (AC-US-01-014-1)
def test_readyz_names_the_failing_dependency() -> None:
    r = client(db_ok=False).get("/api/v1/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "checks": {"database": "unavailable"}}


def test_readyz_ok_when_database_answers() -> None:
    r = client(db_ok=True).get("/api/v1/readyz")
    assert r.status_code == 200
    assert r.json()["checks"] == {"database": "ok"}


def test_every_response_carries_a_request_id() -> None:
    r = client(db_ok=True).get("/api/v1/healthz", headers={"X-Request-Id": "req_test1"})
    assert r.headers["X-Request-Id"] == "req_test1"
    assert client(db_ok=True).get("/api/v1/healthz").headers["X-Request-Id"].startswith("req_")


def test_app_error_uses_the_shared_envelope() -> None:
    from app.core.errors import AppError, ErrorCode

    app = create_app(Settings(database_url="postgresql+psycopg://x:x@nowhere:1/x"))

    @app.get("/boom")
    def boom() -> None:
        raise AppError(ErrorCode.STALE_DRAFT, "This draft changed in another tab. Reload the draft.")

    r = TestClient(app).get("/boom", headers={"X-Request-Id": "req_e1"})
    assert r.status_code == 409
    assert r.json() == {
        "error": {
            "code": "STALE_DRAFT",
            "message": "This draft changed in another tab. Reload the draft.",
            "details": [],
            "request_id": "req_e1",
        }
    }


def test_a_foreign_host_header_is_refused() -> None:
    # Security review 2026-10-01: DNS rebinding sends the operator's browser here under an attacker's hostname.
    r = client(True).get("/api/v1/healthz", headers={"Host": "attacker.example"})

    assert r.status_code == 400
