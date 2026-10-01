"""FastAPI app factory: request ids, health and readiness (US-01-014)."""

import logging
import secrets
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.agent.orchestrator import Orchestrator
from app.api.deps import require
from app.api.routers import admin, ledger, messages, records
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker, ping
from app.core.errors import AppError, ErrorCode
from app.llm.gateway import Gateway
from app.tools.registry import build_registry

log = logging.getLogger("api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if not settings.bank_webhook_secret:
        # No configured secret: a random one per process. The admin "simulate credit" path signs with it, and
        # an outside caller cannot forge a credit (the webhook still fails closed for them).
        settings = settings.model_copy(update={"bank_webhook_secret": secrets.token_hex(32)})
    if not settings.session_secret:  # signs payment links; links die with the process, which suits the demo
        settings = settings.model_copy(update={"session_secret": secrets.token_hex(32)})
    app = FastAPI(title="Collections Agent API", version="1.0.0")
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=[h for h in settings.allowed_hosts.split(",") if h]
    )
    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = make_sessionmaker(engine)
    app.state.check_db = lambda: ping(engine)
    gateway = Gateway(settings, engine)
    app.state.orchestrator = Orchestrator(engine, gateway, build_registry(engine, gateway))

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("X-Request-Id") or f"req_{secrets.token_hex(6)}"
        request.state.request_id = rid
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        # Method, path (ids only), status and time: never a body, a query string or a header value.
        log.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled", exc_info=exc, extra={"request_id": getattr(request.state, "request_id", "")})
        # Anything unnamed is a 500 with the request id; the message never leaks internals.
        return _error(request, 500, ErrorCode.INTERNAL, "Unexpected error. Quote the request id.", [])

    api = APIRouter(prefix="/api/v1")

    @api.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"status": "ok", "checks": {}}

    @api.get("/readyz")
    def readyz() -> JSONResponse:
        ok = bool(app.state.check_db())
        body = {
            "status": "ok" if ok else "unavailable",
            "checks": {"database": "ok" if ok else "unavailable"},
        }
        return JSONResponse(body, status_code=200 if ok else 503)

    api.include_router(ledger.router, dependencies=[Depends(require("viewer", "collector", "admin"))])
    for r in (messages.router, records.router, admin.router):
        api.include_router(r)
    app.include_router(api)
    return app


def _error(
    request: Request, status: int, code: str, message: str, details: list[dict[str, str]]
) -> JSONResponse:
    rid = getattr(request.state, "request_id", "")
    body = {"error": {"code": code, "message": message, "details": details, "request_id": rid}}
    return JSONResponse(body, status_code=status, headers={"X-Request-Id": rid})
