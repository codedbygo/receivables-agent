"""HACK-003 F6: the portal's public surface. Its response models carry only allow-listed fields, the token is never
stored, and malformed tokens are refused before any database work."""

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.config import Settings
from app.services.portal import PortalAck, PortalInvoice, PortalPromise, PortalView, _hash

ALLOWED_VIEW = {
    "customer_name",
    "outstanding_paise",
    "invoices",
    "promises",
    "pay_now_available",
    "payment_simulated",
    "expires_at",
}


def test_the_public_view_exposes_only_allow_listed_fields() -> None:
    assert set(PortalView.model_fields) == ALLOWED_VIEW
    assert set(PortalInvoice.model_fields) == {
        "number",
        "invoice_date",
        "due_date",
        "remaining_paise",
        "status",
    }
    assert set(PortalPromise.model_fields) == {"amount_paise", "promised_date"}
    assert set(PortalAck.model_fields) == {"ok", "message"}
    banned = (
        "note",
        "score",
        "band",
        "reason",
        "factor",
        "timeline",
        "customer_id",
        "email",
        "phone",
        "risk",
    )
    every = str(PortalView.model_json_schema())
    assert not any(b in every for b in banned)


def test_only_the_hash_of_a_token_is_kept() -> None:
    h = _hash("tok")
    assert len(h) == 64 and "tok" not in h


def test_malformed_tokens_are_refused_at_the_boundary() -> None:
    app = create_app(Settings(database_url="postgresql+psycopg://u@127.0.0.1:1/none"))
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/api/v1/portal/short").status_code == 422
        assert c.get("/api/v1/portal/" + "a" * 101).status_code == 422
        assert c.get("/api/v1/portal/abc%27%3B%20DROP%20TABLE%20invoices%3B--xxxxxxxx").status_code == 422
